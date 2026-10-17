"""Deterministic Agent Tools and Graph Algorithm Traversals for FalkorDB.

Implements the 6 core tools required by Track 03:
1. find_counterpart_expert(topic, company)
2. detect_policy_conflicts(domain)
3. find_redundant_systems()
4. trace_decision_lineage(system_name)
5. get_warm_intro_path(person_a, person_b)
6. detect_organizational_silos()

Every tool returns:
- A clear text answer with citations and evidence
- A structured Subgraph JSON (nodes and edges traversed) for UI visualization
"""

from typing import List, Dict, Any, Optional, Set, Tuple
from pydantic import BaseModel, Field
from src.config import settings
from src.db.client import db_client
from src.utils.logger import logger


def resolve_entity(
    graph,
    label: str,
    identifier: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
    """Deterministically resolves an entity identifier (namespaced ID or name) to a single node.

    Resolution hierarchy:
    1. Exact ID match (case-insensitive): `toLower(n.id) == ident_lower`
    2. Exact Name match (case-insensitive): `toLower(n.name) == ident_lower`
    3. Unique Partial match (substring in name or ID). If multiple match, returns ambiguity.

    Returns:
        (resolved_node, ambiguous_candidates)
        - (node, None): Successfully and uniquely resolved.
        - (None, candidates): Ambiguous match with >= 2 candidates.
        - (None, []): No matching entity found.
    """
    raw = (identifier or "").strip()
    if not raw:
        return None, []

    ident_lower = raw.lower()

    allowed_labels = {"Person", "System", "Team", "Policy", "Decision", "Document", "Ticket"}
    if label not in allowed_labels:
        raise ValueError(f"Unsupported entity label for resolution: {label}")

    query = f"""
        MATCH (n:{label})
        WHERE toLower(n.id) = toLower($ident)
           OR toLower(n.name) = toLower($ident)
           OR toLower(n.id) CONTAINS toLower($ident)
           OR toLower(n.name) CONTAINS toLower($ident)
        RETURN n.id as id,
               coalesce(n.name, n.id) as name,
               coalesce(n.company_origin, 'Unknown') as company_origin,
               coalesce(n.role, '') as role,
               coalesce(n.domain, '') as domain,
               coalesce(n.tech, '') as tech
    """
    try:
        res = graph.query(query, {"ident": raw})
        records = res.result_set or []
    except Exception as e:
        logger.error(f"Error resolving entity {label} with '{raw}': {e}")
        return None, []

    candidates = [
        {
            "id": r[0],
            "name": r[1],
            "company_origin": r[2],
            "role": r[3],
            "domain": r[4],
            "tech": r[5],
        }
        for r in records
    ]

    if not candidates:
        return None, []

    # Priority 1: Exact ID match (case-insensitive)
    exact_id = [c for c in candidates if c["id"].lower() == ident_lower]
    if len(exact_id) == 1:
        return exact_id[0], None
    elif len(exact_id) > 1:
        sorted_exact_id = sorted(exact_id, key=lambda x: (x.get("company_origin", ""), x.get("id", "")))
        return None, sorted_exact_id

    # Priority 2: Exact Name match (case-insensitive)
    exact_name = [c for c in candidates if c["name"].lower() == ident_lower]
    if len(exact_name) == 1:
        return exact_name[0], None
    elif len(exact_name) > 1:
        sorted_exact = sorted(exact_name, key=lambda x: (x.get("company_origin", ""), x.get("id", "")))
        return None, sorted_exact

    # Priority 3: Partial substring matches
    partial = [
        c for c in candidates
        if ident_lower in c["name"].lower() or ident_lower in c["id"].lower()
    ]
    if len(partial) == 1:
        return partial[0], None
    elif len(partial) > 1:
        sorted_partial = sorted(partial, key=lambda x: (x.get("name", ""), x.get("company_origin", ""), x.get("id", "")))
        return None, sorted_partial

    return None, []


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

    def resolve_entity(
        self,
        label: str,
        identifier: str,
    ) -> Tuple[Optional[Dict[str, Any]], Optional[List[Dict[str, Any]]]]:
        """Resolves an entity identifier to a unique node or returns ambiguous candidates."""
        return resolve_entity(self._get_graph(), label, identifier)

    def find_counterpart_expert(self, topic: str, company: str = "Vaultly") -> ToolResult:
        """Identifies the actual subject-matter experts in the specified company
        based on PR reviews, incident resolutions, authored RFCs, and PageRank (B13).
        Separates graph influence from topic relevance, provides concrete selection rationale,
        and returns 'insufficient_evidence' when no verified artifact evidence exists.
        """
        graph = self._get_graph()
        subgraph = Subgraph()
        topic_lower = topic.strip().lower()

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

            matching_evidence = []
            topic_score = 0.0

            # 1. Document authorship evidence
            matching_docs = []
            for d in docs:
                title = d.get("title", "")
                excerpt = d.get("excerpt", "")
                if topic_lower in title.lower() or topic_lower in excerpt.lower():
                    topic_score += 2.0
                    matching_evidence.append(f"Authored '{title}'")
                    matching_docs.append(d)

            # 2. Incident ticket resolution evidence
            matching_tickets = []
            for t in tickets:
                title = t.get("title", "")
                if topic_lower in title.lower():
                    topic_score += 2.0
                    sev = t.get("severity", "Incident")
                    matching_evidence.append(f"Resolved Incident '{title}' ({sev})")
                    matching_tickets.append(t)

            # 3. System ownership evidence
            matching_systems = []
            for s in systems:
                sys_name = s.get("name", "")
                sys_domain = s.get("domain", "")
                if topic_lower in sys_name.lower() or topic_lower in sys_domain.lower():
                    topic_score += 1.5
                    matching_evidence.append(f"Owns system '{sys_name}' in domain '{sys_domain}'")
                    matching_systems.append(s)

            # 4. Role alignment evidence
            if topic_lower in (role or "").lower():
                topic_score += 1.0
                matching_evidence.append(f"Role title directly aligns: '{role}'")

            candidates.append({
                "person_id": p_id,
                "name": name,
                "role": role,
                "email": email,
                "pagerank": round(pagerank or 0.5, 3),
                "topic_evidence_score": round(topic_score, 2),
                "evidence_count": len(matching_evidence),
                "evidence": matching_evidence,
                "matching_docs": matching_docs,
                "matching_tickets": matching_tickets,
                "matching_systems": matching_systems,
                "docs": docs,
                "tickets": tickets,
                "systems": systems,
            })

        if not candidates:
            return ToolResult(
                tool_name="find_counterpart_expert",
                status="not_found",
                text_answer=f"No engineers or personnel registered in company '{company}'.",
                details={"company": company, "topic": topic},
                subgraph=subgraph,
            )

        # Separate candidates with concrete evidence from those without evidence (B13)
        evidence_candidates = [c for c in candidates if c["evidence_count"] > 0]
        # Highest PageRank person in the company (for organizational context only)
        top_influencer = sorted(candidates, key=lambda c: c["pagerank"], reverse=True)[0]

        if not evidence_candidates:
            # Insufficient topic evidence: NEVER falsely claim top PageRank person is SME for this topic
            text_answer = (
                f"### Insufficient Evidence: No SME Found for '{topic}' in {company}\n\n"
                f"No verified subject-matter expertise evidence (authored documents/RFCs, resolved incident tickets, "
                f"or owned systems) was identified in **{company}**'s knowledge graph for the requested topic: `'{topic}'`.\n\n"
                f"- **Topic Match Confidence**: `0.0` (Insufficient evidence)\n"
                f"- **Artifacts Analyzed**: 0 matching RFCs, 0 incident tickets, 0 governed systems\n\n"
                f"> **Organizational Centrality Context**: The highest-ranked person in {company} by overall graph PageRank "
                f"is **{top_influencer['name']}** ({top_influencer['role']}, PageRank: `{top_influencer['pagerank']}`), "
                f"but they possess no documented artifact evidence for '{topic}'. Topic rankings require concrete domain evidence."
            )
            return ToolResult(
                tool_name="find_counterpart_expert",
                status="insufficient_evidence",
                text_answer=text_answer,
                details={
                    "topic": topic,
                    "company": company,
                    "evidence_found": 0,
                    "top_influencer": {
                        "name": top_influencer["name"],
                        "role": top_influencer["role"],
                        "pagerank": top_influencer["pagerank"],
                    },
                    "evaluated_candidates": len(candidates),
                },
                subgraph=subgraph,
            )

        # Sort candidates who have evidence primarily by topic evidence score, with PageRank as tiebreaker
        evidence_candidates.sort(
            key=lambda c: (c["topic_evidence_score"], c["pagerank"]),
            reverse=True,
        )
        top_expert = evidence_candidates[0]

        # Build Subgraph with verified evidence entities
        subgraph.add_node(
            top_expert["person_id"],
            top_expert["name"],
            "Person",
            company,
            {
                "role": top_expert["role"],
                "pagerank": top_expert["pagerank"],
                "topic_score": top_expert["topic_evidence_score"],
            },
        )
        for d in top_expert["matching_docs"]:
            subgraph.add_node(d["id"], d["title"], "Document", company)
            subgraph.add_edge(top_expert["person_id"], d["id"], "AUTHORED")
        for t in top_expert["matching_tickets"]:
            subgraph.add_node(t["id"], t["title"], "Ticket", company, {"severity": t.get("severity")})
            subgraph.add_edge(top_expert["person_id"], t["id"], "RESOLVED")
        for s in top_expert["matching_systems"]:
            subgraph.add_node(s["id"], s["name"], "System", company, {"domain": s.get("domain")})
            subgraph.add_edge(top_expert["person_id"], s["id"], "OWNS")

        evidence_str = "\n".join(f"  - {e}" for e in top_expert["evidence"])
        text_answer = (
            f"### Top SME Counterpart: **{top_expert['name']}** ({top_expert['role']} at {company})\n\n"
            f"- **Email**: `{top_expert['email']}`\n"
            f"- **Topic Relevance Score**: `{top_expert['topic_evidence_score']}` ({top_expert['evidence_count']} verified artifact match(es))\n"
            f"- **Structural Graph Influence (PageRank)**: `{top_expert['pagerank']}`\n"
            f"- **Demonstrated Proof of Expertise**:\n{evidence_str}\n\n"
            f"Recommended next step: Reach out directly on Slack or schedule an architectural alignment sync."
        )

        return ToolResult(
            tool_name="find_counterpart_expert",
            status="success",
            text_answer=text_answer,
            details={
                "topic": topic,
                "company": company,
                "expert": top_expert["name"],
                "topic_evidence_score": top_expert["topic_evidence_score"],
                "graph_influence": top_expert["pagerank"],
                "evidence_count": top_expert["evidence_count"],
                "evidence": top_expert["evidence"],
                "candidates": [
                    {
                        "name": c["name"],
                        "role": c["role"],
                        "topic_evidence_score": c["topic_evidence_score"],
                        "pagerank": c["pagerank"],
                        "evidence_count": c["evidence_count"],
                    }
                    for c in evidence_candidates[:3]
                ],
            },
            subgraph=subgraph,
        )

    def detect_policy_conflicts(self, domain: Optional[str] = None) -> ToolResult:
        """Connects conflicting compliance, security, and retention policies
        using a 3-stage pipeline: candidate generation, contradiction validation, and evidence reporting.
        """
        graph = self._get_graph()
        subgraph = Subgraph()

        from src.pipeline.policy_validator import policy_contradiction_engine

        # Execute 3-stage validation pipeline:
        # Stage 1: Candidate Generation (cross-tenant pairs + existing edges)
        # Stage 2: Contradiction Validation (numeric TTL/retention divergence, opposing mandates, authority hierarchy)
        # Stage 3: Conflict Reporting & Evidence Storage
        conflicts = policy_contradiction_engine.evaluate_graph_conflicts(graph, domain_filter=domain)

        if not conflicts:
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

        text_lines = [f"### M&A Policy & Compliance Conflicts Detected ({len(conflicts)} Found)\n"]

        for idx, item in enumerate(conflicts, 1):
            p1 = item["policy_a"]
            p2 = item["policy_b"]
            sev = item["severity"]
            reason = item["reason"]
            c_type = item.get("contradiction_type", "POLICY_CONTRADICTION")
            status = item.get("review_status", "CONFIRMED_CONTRADICTION")
            auth_assess = item.get("authority_assessment", "")

            # Add to subgraph
            subgraph.add_node(p1["id"], p1["name"], "Policy", p1["company"], {
                "domain": p1.get("domain"),
                "effective_date": p1.get("date"),
                "authority": p1.get("authority"),
            })
            subgraph.add_node(p2["id"], p2["name"], "Policy", p2["company"], {
                "domain": p2.get("domain"),
                "effective_date": p2.get("date"),
                "authority": p2.get("authority"),
            })
            subgraph.add_edge(p1["id"], p2["id"], "CONFLICTS_WITH", {
                "severity": sev,
                "reason": reason,
                "contradiction_type": c_type,
                "review_status": status,
            })

            d1 = item.get("source_doc_a") or {}
            d2 = item.get("source_doc_b") or {}

            for d in item.get("all_docs_a", []):
                subgraph.add_node(d["id"], d["title"], "Document", p1["company"], {"url": d.get("url")})
                subgraph.add_edge(p1["id"], d["id"], "DERIVED_FROM")
            for d in item.get("all_docs_b", []):
                subgraph.add_node(d["id"], d["title"], "Document", p2["company"], {"url": d.get("url")})
                subgraph.add_edge(p2["id"], d["id"], "DERIVED_FROM")

            d1_title = d1.get("title") or "FinPay Document"
            d1_url = d1.get("url") or "#"
            d2_title = d2.get("title") or "Vaultly Document"
            d2_url = d2.get("url") or "#"

            line_entry = [
                f"#### Conflict #{idx}: {p1['name']} vs. {p2['name']} `[{sev}]`",
                f"- **Domain**: `{item['domain']}`",
                f"- **Contradiction Type**: `{c_type}` (`{status}`)",
                f"- **{p1['company']} Rule** ({p1.get('date')}, {p1.get('authority')}): *\"{p1.get('desc')}\"*",
                f"  - Source Document: [{d1_title}]({d1_url})",
                f"- **{p2['company']} Rule** ({p2.get('date')}, {p2.get('authority')}): *\"{p2.get('desc')}\"*",
                f"  - Source Document: [{d2_title}]({d2_url})",
                f"- **Conflict Reason**: {reason}",
            ]
            if auth_assess:
                line_entry.append(f"- **Authority & Risk Assessment**: {auth_assess}")
            line_entry.append("")
            text_lines.append("\n".join(line_entry))

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

        resolved_sys, ambiguous = self.resolve_entity(label="System", identifier=system_name)
        if ambiguous:
            lines = [
                f"### Ambiguous System Query: '{system_name}'\n",
                "Multiple systems matched your input. Please disambiguate by providing an exact namespaced ID or exact name:\n",
            ]
            for idx, cand in enumerate(ambiguous, 1):
                lines.append(
                    f"{idx}. **{cand['name']}** (ID: `{cand['id']}`, Tenant: `{cand.get('company_origin', 'Unknown')}`, Domain: `{cand.get('domain', 'N/A')}`)"
                )
            return ToolResult(
                tool_name="trace_decision_lineage",
                status="ambiguous",
                text_answer="\n".join(lines),
                details={
                    "system_input": system_name,
                    "matched_count": len(ambiguous),
                    "candidates": ambiguous,
                },
                subgraph=subgraph,
            )

        if not resolved_sys:
            return ToolResult(
                tool_name="trace_decision_lineage",
                status="not_found",
                text_answer=f"System '{system_name}' was not found in the graph.",
                details={"system_input": system_name},
                subgraph=subgraph,
            )

        target_system_id = resolved_sys["id"]

        query = """
            MATCH (s:System {id: $sys_id})
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
        res = graph.query(query, {"sys_id": target_system_id})

        if not res.result_set:
            return ToolResult(
                tool_name="trace_decision_lineage",
                status="not_found",
                text_answer=f"System '{system_name}' ({target_system_id}) was not found in the graph.",
                details={"system_input": system_name, "system_id": target_system_id},
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
            details={"system": s_name, "company": s_co, "system_id": s_id},
            subgraph=subgraph,
        )

    def get_warm_intro_path(self, person_a: str, person_b: str) -> ToolResult:
        """Finds the shortest topological graph path between two engineers
        across company borders using native shortestPath traversal with bounded fallback.
        """
        graph = self._get_graph()
        subgraph = Subgraph()

        node_a, amb_a = self.resolve_entity(label="Person", identifier=person_a)
        if amb_a:
            lines = [
                f"### Ambiguous Person Query: '{person_a}'\n",
                "Multiple individuals matched your input. Please disambiguate by providing an exact namespaced ID or exact full name:\n",
            ]
            for idx, cand in enumerate(amb_a, 1):
                role_str = f", Role: `{cand['role']}`" if cand.get("role") else ""
                lines.append(f"{idx}. **{cand['name']}** (ID: `{cand['id']}`, Tenant: `{cand.get('company_origin', 'Unknown')}`{role_str})")
            return ToolResult(
                tool_name="get_warm_intro_path",
                status="ambiguous",
                text_answer="\n".join(lines),
                details={"input": person_a, "matched_count": len(amb_a), "candidates": amb_a},
                subgraph=subgraph,
            )
        if not node_a:
            return ToolResult(
                tool_name="get_warm_intro_path",
                status="not_found",
                text_answer=f"Person '{person_a}' was not found in the graph.",
                details={"input": person_a},
                subgraph=subgraph,
            )

        node_b, amb_b = self.resolve_entity(label="Person", identifier=person_b)
        if amb_b:
            lines = [
                f"### Ambiguous Person Query: '{person_b}'\n",
                "Multiple individuals matched your input. Please disambiguate by providing an exact namespaced ID or exact full name:\n",
            ]
            for idx, cand in enumerate(amb_b, 1):
                role_str = f", Role: `{cand['role']}`" if cand.get("role") else ""
                lines.append(f"{idx}. **{cand['name']}** (ID: `{cand['id']}`, Tenant: `{cand.get('company_origin', 'Unknown')}`{role_str})")
            return ToolResult(
                tool_name="get_warm_intro_path",
                status="ambiguous",
                text_answer="\n".join(lines),
                details={"input": person_b, "matched_count": len(amb_b), "candidates": amb_b},
                subgraph=subgraph,
            )
        if not node_b:
            return ToolResult(
                tool_name="get_warm_intro_path",
                status="not_found",
                text_answer=f"Person '{person_b}' was not found in the graph.",
                details={"input": person_b},
                subgraph=subgraph,
            )

        if node_a["id"] == node_b["id"]:
            subgraph.add_node(node_a["id"], node_a["name"], "Person", node_a.get("company_origin", "Unknown"))
            return ToolResult(
                tool_name="get_warm_intro_path",
                status="same_person",
                text_answer=f"Both arguments resolve to the same person: **{node_a['name']}** (ID: `{node_a['id']}`). No introduction path required.",
                details={"person": node_a},
                subgraph=subgraph,
            )

        res = None
        # 1. Attempt FalkorDB native shortestPath with deterministically resolved IDs
        try:
            native_q = f"""
                MATCH (a:Person {{id: $p_a_id}}), (b:Person {{id: $p_b_id}})
                WITH shortestPath((a)-[*..{settings.warm_intro_max_directed_hops}]-(b)) as p
                WHERE p IS NOT NULL
                WITH p, nodes(p) as nds, relationships(p) as rls, length(p) as h
                RETURN [n in nds | n.id] as node_ids,
                       [n in nds | coalesce(n.name, n.id)] as node_names,
                       [n in nds | labels(n)[0]] as node_labels,
                       [n in nds | coalesce(n.company_origin, 'External')] as node_companies,
                       [r in rls | [startNode(r).id, endNode(r).id, type(r)]] as rel_triplets,
                       h as hops
            """
            native_res = graph.query(native_q, {"p_a_id": node_a["id"], "p_b_id": node_b["id"]})
            if native_res and native_res.result_set:
                res = native_res
        except Exception as e:
            logger.warning(f"Native shortestPath query failed: {e}")
            res = None

        # 2. Seamless fallback to bounded bidirectional path match with deterministically resolved IDs
        if not res or not res.result_set:
            query = f"""
                MATCH (a:Person {{id: $p_a_id}}), (b:Person {{id: $p_b_id}})
                MATCH p = (a)-[*1..{settings.warm_intro_max_bidirectional_hops}]-(b)
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
            res = graph.query(query, {"p_a_id": node_a["id"], "p_b_id": node_b["id"]})

        if not res or not res.result_set:
            return ToolResult(
                tool_name="get_warm_intro_path",
                text_answer=f"No connection path found between '{node_a['name']}' ({node_a['id']}) and '{node_b['name']}' ({node_b['id']}) within {settings.warm_intro_max_bidirectional_hops} hops.",
                details={"resolved_a": node_a, "resolved_b": node_b},
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
            f"### Warm Introduction Path: **{start_name}** -> **{end_name}** ({hops} Hops - Shortest Graph Path)\n\n"
            f"Shortest topological graph path discovered across companies:\n\n"
            + "\n".join(f"{idx+1}. {step}" for idx, step in enumerate(chain_steps))
            + f"\n\n**Recommended Intro Pitch:**\n"
            f"> \"Hi {end_name}, I'm working with {start_name}. We noticed an architecture overlap between our services {pitch_context}, and would love to align on unified patterns.\""
        )

        return ToolResult(
            tool_name="get_warm_intro_path",
            text_answer=text_answer,
            details={
                "start": start_name,
                "end": end_name,
                "hops": hops,
                "chain": chain_steps,
                "path_metric": "shortest_topological_path",
                "resolved_a": node_a,
                "resolved_b": node_b,
            },
            subgraph=subgraph,
        )

    @staticmethod
    def _build_component_subgraph(
        components: List[Dict[str, Any]],
        nodes_data: Dict[str, Dict[str, Any]],
        subgraph: Subgraph,
        allowed_labels: Optional[Set[str]] = None,
        max_nodes: Optional[int] = None,
    ) -> None:
        """Serializes and adds component nodes to the visualization subgraph with optional label filtering and capacity limit."""
        for comp in components:
            for nid in comp.get("node_ids", []):
                if max_nodes is not None and len(subgraph.nodes) >= max_nodes:
                    return
                ninfo = nodes_data.get(nid, {})
                label = ninfo.get("label", "Node")
                if allowed_labels is not None and label not in allowed_labels:
                    continue
                subgraph.add_node(
                    node_id=nid,
                    name=ninfo.get("name", nid),
                    label=label,
                    company=ninfo.get("company", "Unknown"),
                    props=ninfo.get("props", {}),
                )

    def _find_silo_bridge_recommendation(self, graph, silo: Dict[str, Any]) -> str:
        """Derives evidence-based integration bridge recommendations from candidate bridge edges,
        shared dependencies, and reachable counterpart teams (B18).
        When no evidence supports a bridge, explicitly reports that no suitable bridge was found.
        """
        origin_company = silo.get("primary_company")
        if not origin_company or origin_company not in ("FinPay", "Vaultly"):
            return "No suitable bridge was found: Component origin is unclassified or external."

        target_company = "Vaultly" if origin_company == "FinPay" else "FinPay"
        node_ids = silo.get("node_ids", [])
        if not node_ids:
            return "No suitable bridge was found: Empty component node set."

        # 1. Check for real candidate or existing bridge edges to the target company
        try:
            bridge_query = """
                MATCH (a)-[r]-(b)
                WHERE (a.id IN $node_ids AND b.company_origin = $target)
                   OR (b.id IN $node_ids AND a.company_origin = $target)
                RETURN coalesce(a.name, a.title, a.id) as a_name,
                       type(r) as rel_type,
                       coalesce(b.name, b.title, b.id) as b_name
                LIMIT 1
            """
            b_res = graph.query(bridge_query, {"node_ids": node_ids, "target": target_company}).result_set
            if b_res and b_res[0]:
                a_n, r_t, b_n = b_res[0][0], b_res[0][1], b_res[0][2]
                return f"Candidate Bridge Identified: Establish formal architectural alignment on '{a_n}' <-> '{b_n}' ({r_t})."
        except Exception as e:
            logger.debug(f"Bridge edge query error: {e}")

        # 2. Check for shared functional dependencies / shared domain systems in target company
        try:
            domain_query = """
                MATCH (s_silo:System)
                WHERE s_silo.id IN $node_ids AND s_silo.domain IS NOT NULL
                MATCH (s_target:System {company_origin: $target})
                WHERE toLower(s_target.domain) = toLower(s_silo.domain)
                OPTIONAL MATCH (t_target:Team)-[:OWNS]->(s_target)
                RETURN s_silo.name, s_silo.domain, s_target.name, coalesce(t_target.name, 'Unassigned Team') as target_team
                LIMIT 1
            """
            d_res = graph.query(domain_query, {"node_ids": node_ids, "target": target_company}).result_set
            if d_res and d_res[0]:
                silo_sys, domain, target_sys, target_team = d_res[0][0], d_res[0][1], d_res[0][2], d_res[0][3]
                silo_teams = ", ".join(silo.get("teams", [])) or "Siloed Engineering"
                return (
                    f"Shared Domain Alignment: System '{silo_sys}' shares domain '{domain}' with {target_company}'s '{target_sys}'. "
                    f"Recommend initiating cross-company API contract alignment between `{silo_teams}` and counterpart team '{target_team}'."
                )
        except Exception as e:
            logger.debug(f"Domain counterpart query error: {e}")

        # 3. Check for shared third-party / external vendor dependencies
        try:
            vendor_query = """
                MATCH (a:System)-[:DEPENDS_ON]->(ext:System {company_origin: 'External'})
                WHERE a.id IN $node_ids
                MATCH (b:System {company_origin: $target})-[:DEPENDS_ON]->(ext)
                OPTIONAL MATCH (t_target:Team)-[:OWNS]->(b)
                RETURN a.name, ext.name, b.name, coalesce(t_target.name, 'Platform Engineering') as target_team
                LIMIT 1
            """
            v_res = graph.query(vendor_query, {"node_ids": node_ids, "target": target_company}).result_set
            if v_res and v_res[0]:
                silo_sys, ext_name, target_sys, target_team = v_res[0][0], v_res[0][1], v_res[0][2], v_res[0][3]
                return (
                    f"Shared External Dependency: Both '{silo_sys}' and {target_company}'s '{target_sys}' depend on shared external service '{ext_name}'. "
                    f"Recommend synchronizing vendor integration through '{target_team}'."
                )
        except Exception as e:
            logger.debug(f"Vendor dependency query error: {e}")

        # 4. Check for reachable counterpart teams by functional department / role alignment
        try:
            team_query = """
                MATCH (p_silo:Person) WHERE p_silo.id IN $node_ids AND p_silo.department IS NOT NULL
                MATCH (p_target:Person {company_origin: $target})
                WHERE toLower(p_silo.department) = toLower(p_target.department)
                OPTIONAL MATCH (p_target)-[:MEMBER_OF]->(t_target:Team)
                RETURN p_silo.name, p_target.name, coalesce(t_target.name, 'Architecture Guild') as target_team
                LIMIT 1
            """
            t_res = graph.query(team_query, {"node_ids": node_ids, "target": target_company}).result_set
            if t_res and t_res[0]:
                p_silo, p_target, target_team = t_res[0][0], t_res[0][1], t_res[0][2]
                return (
                    f"Reachable Counterpart Team: Introduce '{p_silo}' to '{p_target}' ({target_team} at {target_company}) "
                    f"via warm introduction path to coordinate architectural convergence."
                )
        except Exception as e:
            logger.debug(f"Counterpart team query error: {e}")

        # 5. When no evidence supports a bridge, state it explicitly (B18)
        silo_teams = ", ".join(silo.get("teams", [])) or "Isolated unit"
        return (
            f"No suitable bridge was found: No candidate bridge edges, shared functional dependencies, or "
            f"counterpart teams identified in {target_company} for `{silo_teams}`. "
            f"Requires manual organizational and architectural domain assignment."
        )

    def detect_organizational_silos(self) -> ToolResult:
        """Discovers isolated organizational islands and silos across FinPay and Vaultly
        using Weakly Connected Components (WCC) graph clustering (B14, B17, B18).
        Prioritizes FalkorDB native graph algorithm (CALL algo.wcc()) with seamless,
        documented fallback to Python graph traversal if unsupported.
        """
        graph = self._get_graph()
        subgraph = Subgraph()
        nodes_data: Dict[str, Dict[str, Any]] = {}
        components: List[List[str]] = []
        algorithm_used = "python_adjacency_fallback"

        # 1. Attempt FalkorDB native GraphBLAS algorithm: CALL algo.wcc()
        try:
            native_res = graph.query("CALL algo.wcc()")
            if native_res and native_res.result_set:
                from collections import defaultdict
                comp_map = defaultdict(list)
                for row in native_res.result_set:
                    node_obj, comp_id = row[0], row[1]
                    props = dict(getattr(node_obj, "properties", {}))
                    nid = props.get("id")
                    if not nid:
                        continue
                    disp_name = (
                        props.get("name")
                        or props.get("title")
                        or props.get("summary")
                        or nid
                    )
                    labels = getattr(node_obj, "labels", [])
                    label = labels[0] if labels else "Node"
                    company = props.get("company_origin", "External")

                    nodes_data[nid] = {
                        "name": disp_name,
                        "label": label,
                        "company": company,
                        "props": props,
                    }
                    comp_map[comp_id].append(nid)

                components = list(comp_map.values())
                algorithm_used = "falkordb_native_algo_wcc"
                logger.info(f"[{self.graph_name}] Successfully executed FalkorDB native graph algorithm: CALL algo.wcc() ({len(components)} components).")
        except Exception as e:
            logger.warning(f"[{self.graph_name}] FalkorDB native CALL algo.wcc() unavailable: {e}. Executing Python queue traversal fallback.")
            algorithm_used = "python_adjacency_fallback"

        # 2. Seamless documented fallback: queue-based BFS traversal if native unavailable
        if not nodes_data or algorithm_used == "python_adjacency_fallback":
            node_res = graph.query("""
                MATCH (n)
                RETURN n.id, coalesce(n.name, n.title, n.summary, n.id) as display_name,
                       labels(n)[0] as label, coalesce(n.company_origin, 'External') as company,
                       properties(n) as props
            """)
            nodes_data = {
                r[0]: {
                    "name": r[1],
                    "label": r[2],
                    "company": r[3],
                    "props": r[4] if isinstance(r[4], dict) else {},
                }
                for r in node_res.result_set
            }

            adj: Dict[str, set] = {nid: set() for nid in nodes_data}
            rel_res = graph.query("MATCH (a)-[r]->(b) RETURN a.id, b.id")
            for a_id, b_id in rel_res.result_set:
                if a_id in adj and b_id in adj:
                    adj[a_id].add(b_id)
                    adj[b_id].add(a_id)

            visited = set()
            components = []
            for nid in nodes_data:
                if nid not in visited:
                    comp = []
                    queue = [nid]
                    visited.add(nid)
                    for curr in queue:
                        comp.append(curr)
                        for neighbor in adj.get(curr, []):
                            if neighbor not in visited:
                                visited.add(neighbor)
                                queue.append(neighbor)
                    components.append(comp)

        # Sort components by size descending
        components.sort(key=lambda c: len(c), reverse=True)

        silo_components = []
        integrated_components = []
        external_components = []

        for comp_idx, comp_node_ids in enumerate(components):
            comp_nodes = [nodes_data[nid] for nid in comp_node_ids if nid in nodes_data]
            all_companies = {n["company"] for n in comp_nodes if n.get("company")}
            enterprise_companies = {c for c in all_companies if c not in ("External", "Shared", "ThirdParty", "Vendor", "Unknown")}
            teams = [n["name"] for n in comp_nodes if n["label"] == "Team"]
            systems = [n["name"] for n in comp_nodes if n["label"] == "System"]
            people = [n["name"] for n in comp_nodes if n["label"] == "Person"]

            comp_info = {
                "component_id": comp_idx + 1,
                "node_count": len(comp_node_ids),
                "companies": list(enterprise_companies),
                "all_companies": list(all_companies),
                "teams": teams,
                "systems": systems,
                "people": people,
                "node_ids": comp_node_ids,
            }

            if len(enterprise_companies) > 1:
                comp_info["classification"] = "integrated"
                integrated_components.append(comp_info)
            elif len(enterprise_companies) == 1:
                comp_info["classification"] = "silo"
                comp_info["primary_company"] = list(enterprise_companies)[0]
                comp_info["recommendation"] = self._find_silo_bridge_recommendation(graph, comp_info)
                silo_components.append(comp_info)
            else:
                # External-only or unclassified components are separated from internal organizational silos (B17)
                comp_info["classification"] = "external_or_unclassified"
                comp_info["primary_company"] = list(all_companies)[0] if all_companies else "External"
                comp_info["recommendation"] = "External / third-party component. No internal merger bridge required."
                external_components.append(comp_info)

        # Fetch relationship triplets for subgraph visualization
        rel_triplets = []
        try:
            rel_res = graph.query("MATCH (a)-[r]->(b) RETURN a.id, b.id, type(r)")
            for a_id, b_id, r_type in rel_res.result_set:
                rel_triplets.append((a_id, b_id, r_type))
        except Exception as e:
            logger.warning(f"Could not fetch relationships for subgraph: {e}")

        # 3. Build Subgraph visualization: include siloed nodes and key bridge entities
        self._build_component_subgraph(silo_components, nodes_data, subgraph)
        self._build_component_subgraph(
            integrated_components,
            nodes_data,
            subgraph,
            allowed_labels={"Team", "System"},
            max_nodes=settings.silos_subgraph_max_nodes,
        )

        subgraph_node_ids = {n.id for n in subgraph.nodes}
        for a_id, b_id, r_type in rel_triplets:
            if a_id in subgraph_node_ids and b_id in subgraph_node_ids:
                subgraph.add_edge(a_id, b_id, r_type)

        # 4. Format markdown response
        engine_label = (
            "FalkorDB Native GraphBLAS WCC (`CALL algo.wcc()`)"
            if algorithm_used == "falkordb_native_algo_wcc"
            else "Python Adjacency Traversal Fallback (BFS Components)"
        )
        lines = [
            f"### Organizational Silo & Network Topology Analysis (Weakly Connected Components)\n",
            f"- **Algorithm Engine**: {engine_label}",
            f"Discovered **{len(components)} connected components** across the enterprise knowledge graph (`{self.graph_name}`):\n",
            f"- **Integrated Core Networks**: {len(integrated_components)} component(s) bridging FinPay and Vaultly.",
            f"- **Isolated Organizational Silos**: {len(silo_components)} disconnected single-company island(s).",
        ]
        if external_components:
            lines.append(f"- **External & Third-Party Dependencies**: {len(external_components)} external/vendor cluster(s) (non-silos).\n")
        else:
            lines.append("")

        if silo_components:
            lines.append("#### Critical Siloed Business Units Detected:")
            for s in silo_components:
                co_label = s.get("primary_company", "Single-Company")
                teams_str = ", ".join(s["teams"]) if s["teams"] else "No formal team entity"
                people_str = ", ".join(s["people"]) if s["people"] else "None"
                sys_str = ", ".join(s["systems"]) if s["systems"] else "None (Edge/Client layer)"
                lines.append(
                    f"\n**[Silo Component #{s['component_id']} - {co_label}]** ({s['node_count']} nodes)\n"
                    f"- **Company Origin**: `{co_label}`\n"
                    f"- **Isolated Teams**: `{teams_str}`\n"
                    f"- **Key Personnel**: {people_str}\n"
                    f"- **Associated Systems**: {sys_str}\n"
                    f"- **Architectural Risk**: Team operates detached from the cross-company integration plane. High risk of redundant engineering efforts, API schema divergences, and unaligned governance.\n"
                    f"- **Recommended Integration Bridge**: {s['recommendation']}"
                )

        if external_components:
            lines.append("\n#### External & Third-Party Dependencies (Non-Silos):")
            for ext in external_components:
                comp_co = ", ".join(ext["all_companies"]) if ext["all_companies"] else "External"
                sys_str = ", ".join(ext["systems"]) if ext["systems"] else f"{ext['node_count']} external entities"
                lines.append(
                    f"- **Component #{ext['component_id']}** ({ext['node_count']} nodes, {comp_co}): "
                    f"Third-party external dependencies (`{sys_str}`). Not classified as internal organizational silo."
                )

        if integrated_components:
            lines.append("\n#### Cross-Border Integrated Networks:")
            for integ in integrated_components:
                teams_str = ", ".join(integ["teams"][:4]) if integ["teams"] else "Cross-functional"
                lines.append(
                    f"- **Component #{integ['component_id']}** ({integ['node_count']} nodes): Integrates {', '.join(integ['companies'])}. "
                    f"Active bridges established across teams `{teams_str}`."
                )

        lines.append(
            f"\n> *Algorithm: {engine_label} computed over '{self.graph_name}' to guarantee complete organizational network topology.*"
        )

        return ToolResult(
            tool_name="detect_organizational_silos",
            text_answer="\n".join(lines),
            details={
                "algorithm": algorithm_used,
                "native_algorithm": (algorithm_used == "falkordb_native_algo_wcc"),
                "total_components": len(components),
                "isolated_silos_count": len(silo_components),
                "integrated_networks_count": len(integrated_components),
                "external_components_count": len(external_components),
                "silos": silo_components,
                "integrated": integrated_components,
                "external_components": external_components,
            },
            subgraph=subgraph,
        )


agent_tools = GraphAgentTools()


def fetch_visualization_subgraph(
    graph_name: Optional[str] = None,
    node_limit: int = 100,
    rel_limit: int = 150,
) -> Subgraph:
    """Returns nodes and edges for visual rendering, stripping bulky embedding vectors to optimize payload size."""
    target_graph = graph_name or settings.graph_merged
    g = db_client.get_graph(target_graph)
    subgraph = Subgraph()

    # Query nodes
    node_query = f"""
        MATCH (n)
        RETURN n.id as id,
               coalesce(n.name, n.title, n.summary, n.id) as display_name,
               labels(n)[0] as label,
               coalesce(n.company_origin, 'External') as company,
               properties(n) as props
        LIMIT {node_limit}
    """
    node_res = g.query(node_query)
    for row in node_res.result_set:
        props = dict(row[4]) if isinstance(row[4], dict) else {}
        props.pop("embedding", None)
        subgraph.add_node(
            node_id=row[0],
            name=row[1],
            label=row[2],
            company=row[3],
            props=props,
        )

    # Query relationships (guaranteeing both source and target exist in node set)
    valid_node_ids = {n.id for n in subgraph.nodes}
    rel_query = f"""
        MATCH (a)-[r]->(b)
        RETURN a.id, b.id, type(r), properties(r)
        LIMIT {rel_limit}
    """
    rel_res = g.query(rel_query)
    for row in rel_res.result_set:
        if row[0] in valid_node_ids and row[1] in valid_node_ids:
            props = dict(row[3]) if isinstance(row[3], dict) else {}
            props.pop("embedding", None)
            subgraph.add_edge(
                source=row[0],
                target=row[1],
                rel_type=row[2],
                props=props,
            )

    return subgraph

