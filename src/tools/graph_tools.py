"""Deterministic Agent Tools and Graph Algorithm Traversals for FalkorDB.

Implements the 5 core tools required by Track 03:
1. find_counterpart_expert(topic, company)
2. detect_policy_conflicts(domain)
3. find_redundant_systems()
4. trace_decision_lineage(system_name)
5. get_warm_intro_path(person_a, person_b)

Every tool returns:
- A clear text answer with citations and evidence
- A structured Subgraph JSON (nodes and edges traversed) for UI visualization
"""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
from src.config import settings
from src.utils.logger import logger
from src.db.client import db_client


class SubgraphNode(BaseModel):
    id: str
    name: str
    label: str
    company_origin: str = "Unknown"
    properties: Dict[str, Any] = Field(default_factory=dict)


class SubgraphEdge(BaseModel):
    source: str
    target: str
    rel_type: str
    properties: Dict[str, Any] = Field(default_factory=dict)


class Subgraph(BaseModel):
    nodes: List[SubgraphNode] = Field(default_factory=list)
    edges: List[SubgraphEdge] = Field(default_factory=list)

    def add_node(self, node_id: str, name: str, label: str, company: str, props: Dict[str, Any] = None):
        if not any(n.id == node_id for n in self.nodes):
            self.nodes.append(
                SubgraphNode(
                    id=node_id,
                    name=name,
                    label=label,
                    company_origin=company,
                    properties=props or {},
                )
            )

    def add_edge(self, source: str, target: str, rel_type: str, props: Dict[str, Any] = None):
        if not any(e.source == source and e.target == target and e.rel_type == rel_type for e in self.edges):
            self.edges.append(
                SubgraphEdge(
                    source=source,
                    target=target,
                    rel_type=rel_type,
                    properties=props or {},
                )
            )


class ToolResult(BaseModel):
    tool_name: str
    status: str = "success"
    text_answer: str
    details: Dict[str, Any] = Field(default_factory=dict)
    subgraph: Subgraph


class GraphAgentTools:
    """Deterministic tool execution layer querying FalkorDB."""

    def __init__(self, graph_name: str = None):
        self.graph_name = graph_name or settings.graph_merged

    def _get_graph(self):
        return db_client.get_graph(self.graph_name)

    def find_counterpart_expert(self, topic: str, company: str = "Vaultly") -> ToolResult:
        """Identifies the actual subject-matter experts in the specified company

        based on PR reviews, incident resolutions, authored RFCs, and PageRank.
        """
        graph = self._get_graph()
        subgraph = Subgraph()
        topic_lower = topic.lower()

        query = """
            MATCH (p:Person {company_origin: $company})
            OPTIONAL MATCH (p)-[:AUTHORED]->(doc:Document)
            OPTIONAL MATCH (p)-[:RESOLVED]->(tkt:Ticket)
            OPTIONAL MATCH (p)-[:OWNS]->(s:System)
            RETURN p.id, p.name, p.role, p.email, p.pagerank, p.company_origin,
                   collect(DISTINCT {id: doc.id, title: doc.title, excerpt: doc.excerpt}) as docs,
                   collect(DISTINCT {id: tkt.id, title: tkt.title, severity: tkt.severity}) as tickets,
                   collect(DISTINCT {id: s.id, name: s.name, domain: s.domain}) as systems
            ORDER BY p.pagerank DESC
        """
        res = graph.query(query, {"company": company})

        candidates = []
        for row in res.result_set:
            p_id, name, role, email, pagerank, co, docs, tickets, systems = row
            docs = [d for d in docs if d.get("id")]
            tickets = [t for t in tickets if t.get("id")]
            systems = [s for s in systems if s.get("id")]

            # Compute topic relevance score
            relevance_matches = 0
            matching_evidence = []

            for d in docs:
                if topic_lower in d.get("title", "").lower() or topic_lower in d.get("excerpt", "").lower():
                    relevance_matches += 2
                    matching_evidence.append(f"Authored '{d.get('title')}'")
            for t in tickets:
                if topic_lower in t.get("title", "").lower():
                    relevance_matches += 2
                    matching_evidence.append(f"Resolved Incident '{t.get('title')}' ({t.get('severity')})")
            for s in systems:
                if topic_lower in s.get("name", "").lower() or topic_lower in s.get("domain", "").lower():
                    relevance_matches += 1
                    matching_evidence.append(f"Owns system '{s.get('name')}'")

            score = (pagerank or 0.5) + (0.2 * relevance_matches)

            candidates.append({
                "person_id": p_id,
                "name": name,
                "role": role,
                "email": email,
                "pagerank": pagerank,
                "relevance_score": round(score, 2),
                "evidence": matching_evidence,
                "docs": docs,
                "tickets": tickets,
                "systems": systems,
            })

        # Sort by relevance score
        candidates.sort(key=lambda c: c["relevance_score"], reverse=True)
        top_expert = candidates[0] if candidates else None

        if top_expert:
            # Build Subgraph
            subgraph.add_node(
                top_expert["person_id"],
                top_expert["name"],
                "Person",
                company,
                {"role": top_expert["role"], "pagerank": top_expert["pagerank"]},
            )
            for d in top_expert["docs"]:
                subgraph.add_node(d["id"], d["title"], "Document", company)
                subgraph.add_edge(top_expert["person_id"], d["id"], "AUTHORED")
            for t in top_expert["tickets"]:
                subgraph.add_node(t["id"], t["title"], "Ticket", company, {"severity": t.get("severity")})
                subgraph.add_edge(top_expert["person_id"], t["id"], "RESOLVED")
            for s in top_expert["systems"]:
                subgraph.add_node(s["id"], s["name"], "System", company, {"domain": s.get("domain")})
                subgraph.add_edge(top_expert["person_id"], s["id"], "OWNS")

            evidence_str = "\n".join(f"  - {e}" for e in top_expert["evidence"]) if top_expert["evidence"] else "  - Top PageRank SME based on system architecture ownership"
            text_answer = (
                f"### Top SME Counterpart: **{top_expert['name']}** ({top_expert['role']} at {company})\n\n"
                f"- **Email**: `{top_expert['email']}`\n"
                f"- **PageRank Influence**: `{top_expert['pagerank']}` (Ranked #1 for '{topic}')\n"
                f"- **Demonstrated Proof of Expertise**:\n{evidence_str}\n\n"
                f"Recommended next step: Reach out directly on Slack or schedule an architectural alignment sync."
            )
        else:
            text_answer = f"No counterpart experts found in company '{company}' for topic '{topic}'."

        return ToolResult(
            tool_name="find_counterpart_expert",
            text_answer=text_answer,
            details={"candidates": candidates[:3]},
            subgraph=subgraph,
        )

    def detect_policy_conflicts(self, domain: Optional[str] = None) -> ToolResult:
        """Connects conflicting compliance, security, and retention policies

        and traces them back to source RFCs and audit documents.
        """
        graph = self._get_graph()
        subgraph = Subgraph()

        domain_filter = "AND (toLower(p1.domain) CONTAINS toLower($domain) OR toLower(p2.domain) CONTAINS toLower($domain))" if domain else ""
        query = f"""
            MATCH (p1:Policy)-[r:CONFLICTS_WITH]-(p2:Policy)
            WHERE p1.id < p2.id
              AND coalesce(r.status, 'ACTIVE') <> 'RESOLVED'
              AND coalesce(p1.status, 'ACTIVE') <> 'DEPRECATED'
              AND coalesce(p2.status, 'ACTIVE') <> 'DEPRECATED'
            {domain_filter}
            OPTIONAL MATCH (p1)-[:DERIVED_FROM]->(doc1:Document)
            OPTIONAL MATCH (p2)-[:DERIVED_FROM]->(doc2:Document)
            RETURN p1.id, p1.name, p1.domain, p1.description, p1.effective_date, p1.authority_level, p1.source, p1.company_origin,
                   p2.id, p2.name, p2.domain, p2.description, p2.effective_date, p2.authority_level, p2.source, p2.company_origin,
                   r.severity, r.reason,
                   collect(DISTINCT {{id: doc1.id, title: doc1.title, url: doc1.url, excerpt: doc1.excerpt}}) as docs1,
                   collect(DISTINCT {{id: doc2.id, title: doc2.title, url: doc2.url, excerpt: doc2.excerpt}}) as docs2
        """
        res = graph.query(query, {"domain": domain or ""})

        if not res.result_set:
            # Check if any conflicts were resolved via M&A mutations
            resolved_res = graph.query("""
                MATCH (p1:Policy)-[r:CONFLICTS_WITH]-(p2:Policy)
                WHERE p1.id < p2.id
                  AND (r.status = 'RESOLVED' OR p1.status = 'DEPRECATED' OR p2.status = 'DEPRECATED')
                RETURN count(r) as resolved_count
            """)
            resolved_count = resolved_res.result_set[0][0] if resolved_res.result_set else 0
            info = f" ({resolved_count} conflict(s) previously resolved via M&A mutations)." if resolved_count > 0 else "."
            domain_label = f" for domain '{domain}'" if domain else ""

            return ToolResult(
                tool_name="detect_policy_conflicts",
                text_answer=f"### M&A Policy & Compliance Conflicts: 0 Active Conflicts Detected{domain_label}\n\nAll policy domains are currently compliant, aligned, or superseded by unified standards{info}",
                details={"conflicts": []},
                subgraph=subgraph,
            )

        conflicts = []
        text_lines = [f"### M&A Policy & Compliance Conflicts Detected ({len(res.result_set)} Found)\n"]

        for idx, row in enumerate(res.result_set, 1):
            (
                p1_id, p1_name, p1_domain, p1_desc, p1_eff, p1_auth, p1_src, p1_co,
                p2_id, p2_name, p2_domain, p2_desc, p2_eff, p2_auth, p2_src, p2_co,
                sev, reason,
                docs1, docs2,
            ) = row

            docs1 = [d for d in docs1 if d.get("id")]
            docs2 = [d for d in docs2 if d.get("id")]

            d1 = docs1[0] if docs1 else {}
            d2 = docs2[0] if docs2 else {}

            conflicts.append({
                "policy_a": {"id": p1_id, "name": p1_name, "company": p1_co, "date": p1_eff, "authority": p1_auth, "desc": p1_desc},
                "policy_b": {"id": p2_id, "name": p2_name, "company": p2_co, "date": p2_eff, "authority": p2_auth, "desc": p2_desc},
                "severity": sev,
                "reason": reason,
                "source_doc_a": d1,
                "source_doc_b": d2,
            })

            # Add to subgraph
            subgraph.add_node(p1_id, p1_name, "Policy", p1_co, {"domain": p1_domain, "effective_date": p1_eff, "authority": p1_auth})
            subgraph.add_node(p2_id, p2_name, "Policy", p2_co, {"domain": p2_domain, "effective_date": p2_eff, "authority": p2_auth})
            subgraph.add_edge(p1_id, p2_id, "CONFLICTS_WITH", {"severity": sev, "reason": reason})

            for d in docs1:
                subgraph.add_node(d["id"], d["title"], "Document", p1_co, {"url": d.get("url")})
                subgraph.add_edge(p1_id, d["id"], "DERIVED_FROM")
            for d in docs2:
                subgraph.add_node(d["id"], d["title"], "Document", p2_co, {"url": d.get("url")})
                subgraph.add_edge(p2_id, d["id"], "DERIVED_FROM")

            d1_title = d1.get("title") or p1_src
            d1_url = d1.get("url") or "#"
            d2_title = d2.get("title") or p2_src
            d2_url = d2.get("url") or "#"

            text_lines.append(
                f"#### Conflict #{idx}: {p1_name} vs. {p2_name} `[{sev}]`\n"
                f"- **Domain**: `{p1_domain}`\n"
                f"- **{p1_co} Rule** ({p1_eff}, {p1_auth}): *\"{p1_desc}\"*\n"
                f"  - Source Document: [{d1_title}]({d1_url})\n"
                f"- **{p2_co} Rule** ({p2_eff}, {p2_auth}): *\"{p2_desc}\"*\n"
                f"  - Source Document: [{d2_title}]({d2_url})\n"
                f"- **Conflict Reason**: {reason}\n"
            )

        return ToolResult(
            tool_name="detect_policy_conflicts",
            text_answer="\n".join(text_lines),
            details={"conflicts": conflicts},
            subgraph=subgraph,
        )

    def find_redundant_systems(self) -> ToolResult:
        """Exposes redundant systems across companies detected via hybrid vector + graph resolution."""
        graph = self._get_graph()
        subgraph = Subgraph()

        query = """
            MATCH (s1:System)-[r:REDUNDANT_WITH]-(s2:System)
            WHERE s1.id < s2.id
            OPTIONAL MATCH (p1:Person)-[:OWNS]->(s1)
            OPTIONAL MATCH (p2:Person)-[:OWNS]->(s2)
            OPTIONAL MATCH (s1)-[:CALLS]->(ext:ExternalAPI)<-[:CALLS]-(s2)
            RETURN s1.id, s1.name, s1.domain, s1.tech, s1.company_origin,
                   s2.id, s2.name, s2.domain, s2.tech, s2.company_origin,
                   r.similarity, r.reason,
                   collect(DISTINCT {id: p1.id, name: p1.name, role: p1.role}) as owners_1,
                   collect(DISTINCT {id: p2.id, name: p2.name, role: p2.role}) as owners_2,
                   collect(DISTINCT {id: ext.id, name: ext.name}) as shared_apis
        """
        res = graph.query(query)

        redundancies = []
        text_lines = [f"### Redundant Microservices Detected Across Merged Companies ({len(res.result_set)} Clusters)\n"]

        for idx, row in enumerate(res.result_set, 1):
            (
                s1_id, s1_name, s1_dom, s1_tech, s1_co,
                s2_id, s2_name, s2_dom, s2_tech, s2_co,
                sim, reason,
                owners_1, owners_2, shared_apis,
            ) = row

            owners_1 = [o for o in owners_1 if o.get("id")]
            owners_2 = [o for o in owners_2 if o.get("id")]
            shared_apis = [a for a in shared_apis if a.get("id")]

            redundancies.append({
                "system_a": {"id": s1_id, "name": s1_name, "company": s1_co, "tech": s1_tech, "domain": s1_dom},
                "system_b": {"id": s2_id, "name": s2_name, "company": s2_co, "tech": s2_tech, "domain": s2_dom},
                "similarity": sim,
                "reason": reason,
                "owners_a": owners_1,
                "owners_b": owners_2,
                "shared_apis": shared_apis,
            })

            # Subgraph
            subgraph.add_node(s1_id, s1_name, "System", s1_co, {"domain": s1_dom, "tech": s1_tech})
            subgraph.add_node(s2_id, s2_name, "System", s2_co, {"domain": s2_dom, "tech": s2_tech})
            subgraph.add_edge(s1_id, s2_id, "REDUNDANT_WITH", {"similarity": sim, "reason": reason})

            for o in owners_1:
                subgraph.add_node(o["id"], o["name"], "Person", s1_co, {"role": o.get("role")})
                subgraph.add_edge(o["id"], s1_id, "OWNS")
            for o in owners_2:
                subgraph.add_node(o["id"], o["name"], "Person", s2_co, {"role": o.get("role")})
                subgraph.add_edge(o["id"], s2_id, "OWNS")
            for a in shared_apis:
                subgraph.add_node(a["id"], a["name"], "ExternalAPI", "External")
                subgraph.add_edge(s1_id, a["id"], "CALLS")
                subgraph.add_edge(s2_id, a["id"], "CALLS")

            owner1_names = ", ".join(o["name"] for o in owners_1) or "Unassigned"
            owner2_names = ", ".join(o["name"] for o in owners_2) or "Unassigned"
            shared_str = f" | Shared APIs: {', '.join(a['name'] for a in shared_apis)}" if shared_apis else ""

            text_lines.append(
                f"#### Redundancy #{idx}: **{s1_name}** ({s1_co}) <-> **{s2_name}** ({s2_co})\n"
                f"- **Confidence Score**: `{sim:.2f}`\n"

                f"- **{s1_co} Stack**: `{s1_tech}` (Owner: {owner1_names})\n"
                f"- **{s2_co} Stack**: `{s2_tech}` (Owner: {owner2_names})\n"
                f"- **Resolution Evidence**: {reason}{shared_str}\n"
            )

        return ToolResult(
            tool_name="find_redundant_systems",
            text_answer="\n".join(text_lines),
            details={"redundant_systems": redundancies},
            subgraph=subgraph,
        )

    def trace_decision_lineage(self, system_name: str) -> ToolResult:
        """Traces the decisions governing a given system, conflicting decisions in the counterpart,

        and references back to Slack threads, RFCs, and Jira tickets.
        """
        graph = self._get_graph()
        subgraph = Subgraph()

        query = """
            MATCH (s:System)
            WHERE toLower(s.name) = toLower($name) OR toLower(s.id) CONTAINS toLower($name)
            WITH s LIMIT 1
            OPTIONAL MATCH (s)-[:GOVERNED_BY]->(d:Decision)
            OPTIONAL MATCH (d)-[r_conf:CONFLICTS_WITH]-(dc:Decision)
            OPTIONAL MATCH (d)-[:DERIVED_FROM]->(doc:Document)
            OPTIONAL MATCH (d)-[:DERIVED_FROM]->(tkt:Ticket)
            OPTIONAL MATCH (dc)-[:DERIVED_FROM]->(cdoc:Document)
            RETURN s.id, s.name, s.domain, s.company_origin, s.tech,
                   d.id, d.summary, d.date, d.effective_date, d.authority_level, d.status, d.source, d.company_origin,
                   dc.id, dc.summary, dc.date, dc.effective_date, dc.authority_level, dc.source, dc.company_origin, dc.status,
                   r_conf.status, r_conf.resolution_note,
                   collect(DISTINCT {id: doc.id, title: doc.title, url: doc.url}) as docs,
                   collect(DISTINCT {id: tkt.id, title: tkt.title, external_id: tkt.external_id}) as tkts,
                   collect(DISTINCT {id: cdoc.id, title: cdoc.title, url: cdoc.url}) as cdocs
        """
        res = graph.query(query, {"name": system_name})

        if not res.result_set:
            return ToolResult(
                tool_name="trace_decision_lineage",
                text_answer=f"System '{system_name}' was not found in the graph.",
                details={},
                subgraph=subgraph,
            )

        first = res.result_set[0]
        s_id, s_name, s_dom, s_co, s_tech = first[0], first[1], first[2], first[3], first[4]
        subgraph.add_node(s_id, s_name, "System", s_co, {"domain": s_dom, "tech": s_tech})

        text_lines = [f"### Decision Lineage & Conflict Trace for **{s_name}** ({s_co})\n"]

        # Aggregate per decision to eliminate Cartesian row explosion
        decisions: Dict[str, Dict[str, Any]] = {}
        for row in res.result_set:
            (
                _, _, _, _, _,
                d_id, d_summary, d_date, d_eff, d_auth, d_status, d_src, d_co,
                dc_id, dc_summary, dc_date, dc_eff, dc_auth, dc_src, dc_co, dc_status,
                rc_status, rc_note,
                docs, tkts, cdocs,
            ) = row

            if not d_id:
                continue

            if d_id not in decisions:
                decisions[d_id] = {
                    "id": d_id,
                    "summary": d_summary,
                    "date": d_date,
                    "effective_date": d_eff,
                    "authority": d_auth,
                    "status": d_status,
                    "source": d_src,
                    "company": d_co or s_co,
                    "docs": [d for d in docs if d.get("id")],
                    "tickets": [t for t in tkts if t.get("id")],
                    "conflicts": [],
                }

            if dc_id and not any(c["id"] == dc_id for c in decisions[d_id]["conflicts"]):
                decisions[d_id]["conflicts"].append({
                    "id": dc_id,
                    "summary": dc_summary,
                    "date": dc_date,
                    "effective_date": dc_eff,
                    "authority": dc_auth,
                    "source": dc_src,
                    "company": dc_co,
                    "status": dc_status,
                    "rc_status": rc_status,
                    "rc_note": rc_note,
                    "cdocs": [cd for cd in cdocs if cd.get("id")],
                })

        for d_id, d_info in decisions.items():
            subgraph.add_node(
                d_id,
                d_info["summary"][:30] + "...",
                "Decision",
                d_info["company"],
                {
                    "summary": d_info["summary"],
                    "date": d_info["date"],
                    "authority": d_info["authority"],
                    "status": d_info["status"],
                },
            )
            subgraph.add_edge(s_id, d_id, "GOVERNED_BY")
            status_label = f"`{d_info['status']}`" if d_info["status"] else "`ACTIVE`"
            text_lines.append(
                f"#### Governing Decision: *\"{d_info['summary']}\"*\n"
                f"- **Effective Date**: {d_info['effective_date'] or d_info['date']} | **Authority**: {d_info['authority']} | **Status**: {status_label}\n"
                f"- **Source Citation**: `{d_info['source']}`\n"
            )

            for doc in d_info["docs"]:
                subgraph.add_node(doc["id"], doc["title"], "Document", d_info["company"], {"url": doc["url"]})
                subgraph.add_edge(d_id, doc["id"], "DERIVED_FROM")
                text_lines.append(f"  - Derived from RFC: [{doc['title']}]({doc['url']})\n")

            for tkt in d_info["tickets"]:
                subgraph.add_node(tkt["id"], tkt["title"], "Ticket", d_info["company"], {"external_id": tkt.get("external_id")})
                subgraph.add_edge(d_id, tkt["id"], "DERIVED_FROM")
                text_lines.append(f"  - Associated Ticket: `{tkt.get('external_id') or tkt['id']}` ({tkt['title']})\n")

            for conf in d_info["conflicts"]:
                dc_id = conf["id"]
                subgraph.add_node(
                    dc_id,
                    conf["summary"][:30] + "...",
                    "Decision",
                    conf["company"],
                    {
                        "summary": conf["summary"],
                        "date": conf["date"],
                        "authority": conf["authority"],
                        "status": conf["status"],
                    },
                )
                subgraph.add_edge(d_id, dc_id, "CONFLICTS_WITH")
                if conf["rc_status"] == "RESOLVED" or d_info["status"] == "DEPRECATED" or conf["status"] == "DEPRECATED":
                    text_lines.append(
                        f"\n> [RESOLVED] **Resolved M&A Conflict with {conf['company']} Decision (Superceded):**\n"
                        f"> - Former: *\"{conf['summary']}\"* (`{conf['status'] or 'DEPRECATED'}`)\n"
                        f"> - Resolution: {conf['rc_note'] or 'Superceded by M&A Live Mutation Accord'}\n"
                    )
                else:
                    text_lines.append(
                        f"\n> [!] **Direct M&A Conflict with {conf['company']} Decision:**\n"
                        f"> - *\"{conf['summary']}\"*\n"
                        f"> - Authority: {conf['authority']} | Effective: {conf['effective_date'] or conf['date']}\n"
                        f"> - Source Citation: `{conf['source']}`\n"
                    )
                for cdoc in conf["cdocs"]:
                    subgraph.add_node(cdoc["id"], cdoc["title"], "Document", conf["company"], {"url": cdoc["url"]})
                    subgraph.add_edge(dc_id, cdoc["id"], "DERIVED_FROM")
                    text_lines.append(f"> - Counterpart RFC: [{cdoc['title']}]({cdoc['url']})\n")

        return ToolResult(
            tool_name="trace_decision_lineage",
            text_answer="\n".join(text_lines),
            details={"system": s_name, "company": s_co},
            subgraph=subgraph,
        )

    def get_warm_intro_path(self, person_a: str, person_b: str) -> ToolResult:
        """Finds the fastest warm-introduction or dependency chain between two engineers

        across company borders using bounded multi-hop path traversal.
        """
        graph = self._get_graph()
        subgraph = Subgraph()

        query = """
            MATCH (a:Person) WHERE toLower(a.name) CONTAINS toLower($p_a) OR toLower(a.id) CONTAINS toLower($p_a)
            WITH a LIMIT 1
            MATCH (b:Person) WHERE toLower(b.name) CONTAINS toLower($p_b) OR toLower(b.id) CONTAINS toLower($p_b)
            WITH a, b LIMIT 1
            MATCH p = (a)-[*1..4]-(b)
            WITH p, nodes(p) as nds, relationships(p) as rls, length(p) as h
            RETURN [n in nds | n.id] as node_ids,
                   [n in nds | coalesce(n.name, n.id)] as node_names,
                   [n in nds | labels(n)[0]] as node_labels,
                   [n in nds | coalesce(n.company_origin, 'External')] as node_companies,
                   [r in rls | [startNode(r).id, endNode(r).id, type(r)]] as rel_triplets,
                   h as hops
            ORDER BY h ASC
            LIMIT 1
        """
        res = graph.query(query, {"p_a": person_a, "p_b": person_b})

        if not res.result_set:
            return ToolResult(
                tool_name="get_warm_intro_path",
                text_answer=f"No connection path found between '{person_a}' and '{person_b}' within 4 hops.",
                details={},
                subgraph=subgraph,
            )

        row = res.result_set[0]
        node_ids, node_names, node_labels, node_companies, rel_triplets, hops = row

        # Add nodes to subgraph
        for i in range(len(node_ids)):
            subgraph.add_node(node_ids[i], node_names[i], node_labels[i], node_companies[i])

        chain_steps = []
        for i, triplet in enumerate(rel_triplets):
            r_src, r_dst, r_type = triplet[0], triplet[1], triplet[2]
            # Add true directed relationship in FalkorDB graph schema
            subgraph.add_edge(r_src, r_dst, r_type)

            curr_id = node_ids[i]
            curr_name = node_names[i]
            next_name = node_names[i+1]

            if r_src == curr_id:
                chain_steps.append(f"**{curr_name}** -`[:{r_type}]`-> **{next_name}**")
            else:
                chain_steps.append(f"**{curr_name}** <-`[:{r_type}]`- **{next_name}**")

        start_name = node_names[0]
        end_name = node_names[-1]
        pitch_context = f"({node_names[1]} and {node_names[-2]})" if len(node_names) > 2 else f"({node_names[1]})"

        text_answer = (
            f"### Warm Introduction Path: **{start_name}** -> **{end_name}** ({hops} Hops)\n\n"
            f"Fastest organizational bridge discovered across companies:\n\n"
            + "\n".join(f"{idx+1}. {step}" for idx, step in enumerate(chain_steps))
            + f"\n\n**Recommended Intro Pitch:**\n"
            f"> \"Hi {end_name}, I'm working with {start_name}. We noticed an architecture overlap between our services {pitch_context}, and would love to align on unified patterns.\""
        )

        return ToolResult(
            tool_name="get_warm_intro_path",
            text_answer=text_answer,
            details={"start": start_name, "end": end_name, "hops": hops, "chain": chain_steps},
            subgraph=subgraph,
        )


agent_tools = GraphAgentTools()
