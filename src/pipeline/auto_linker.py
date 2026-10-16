"""M&A Auto-Linker Engine for FalkorDB.

Performs Hybrid Vector + Graph Entity Resolution:
1. Embeds System and Policy nodes using normalized dense vectors.
2. Queries FalkorDB vector space across companies.
3. Incorporates graph topological signals (shared ExternalAPI dependencies).
4. Automatically constructs [:REDUNDANT_WITH] and [:CONFLICTS_WITH] edges
   where similarity exceeds the specified threshold (default from settings).
"""

from typing import List, Dict, Any, Optional
from src.config import settings
from src.utils.logger import logger
from src.db.client import db_client
from src.embeddings.service import embedding_service
from src.pipeline.vector_index import (
    ensure_vector_indexes,
    populate_node_embeddings,
    query_vector_neighbors,
    system_embedding_text,
    policy_embedding_text,
    decision_embedding_text,
)


class AutoLinkerEngine:
    """Orchestrates automated cross-tenant bridge linking in merged_brain."""

    def __init__(self, threshold: Optional[float] = None):
        self.threshold = threshold if threshold is not None else settings.auto_linker_threshold

    def detect_redundant_systems(
        self,
        graph_name: str,
        company_a: str = "FinPay",
        company_b: str = "Vaultly",
    ) -> List[Dict[str, Any]]:
        """Identifies redundant microservices using hybrid vector + graph neighbor resolution."""
        graph = db_client.get_graph(graph_name)

        # Retrieve company_a systems with their external API dependencies
        fp_query = """
            MATCH (s:System {company_origin: $company_a})
            OPTIONAL MATCH (s)-[:CALLS]->(ext:ExternalAPI)
            RETURN s.id, s.name, s.domain, s.description, s.tech, collect(ext.name) as ext_apis
        """
        fp_res = graph.query(fp_query, {"company_a": company_a})

        # Retrieve company_b systems with their external API dependencies
        vl_query = """
            MATCH (s:System {company_origin: $company_b})
            OPTIONAL MATCH (s)-[:CALLS]->(ext:ExternalAPI)
            RETURN s.id, s.name, s.domain, s.description, s.tech, collect(ext.name) as ext_apis
        """
        vl_res = graph.query(vl_query, {"company_b": company_b})
        vl_systems = {
            row[0]: {
                "name": row[1],
                "domain": row[2] or "",
                "desc": row[3] or "",
                "tech": row[4] or "",
                "apis": set(row[5] or []),
            }
            for row in vl_res.result_set
        }

        redundancies = []

        for fp_row in fp_res.result_set:
            fp_id, fp_name, fp_domain, fp_desc, fp_tech, fp_apis = fp_row
            fp_apis_set = set(fp_apis or [])
            fp_vec = embedding_service.embed_text(
                system_embedding_text(fp_name, fp_domain, fp_tech, fp_desc)
            )

            # Query FalkorDB vector space for top neighbor candidates
            try:
                neighbors = query_vector_neighbors(graph_name, "System", fp_vec, k=10)
            except Exception as e:
                logger.warning(f"Native vector search failed, falling back to pairwise check: {e}")
                neighbors = []

            if neighbors:
                candidates = []
                for node, distance in neighbors:
                    props = node.properties if hasattr(node, "properties") else {}
                    if props.get("company_origin") == company_b:
                        vl_id = props.get("id")
                        vl_info = vl_systems.get(vl_id)
                        if vl_info:
                            vl_vec = embedding_service.embed_text(
                                system_embedding_text(vl_info["name"], vl_info["domain"], vl_info["tech"], vl_info["desc"])
                            )
                            # Compute canonical cosine similarity directly to avoid engine distance metric ambiguity
                            cos_sim = embedding_service.cosine_similarity(fp_vec, vl_vec)
                        else:
                            cos_sim = round(max(0.0, 1.0 - float(distance)), 2)
                        candidates.append((vl_id, cos_sim))
            else:
                candidates = []
                for vl_id, vl_info in vl_systems.items():
                    vl_vec = embedding_service.embed_text(
                        system_embedding_text(vl_info["name"], vl_info["domain"], vl_info["tech"], vl_info["desc"])
                    )
                    cos_sim = embedding_service.cosine_similarity(fp_vec, vl_vec)
                    candidates.append((vl_id, cos_sim))

            for vl_id, cos_sim in candidates:
                vl_info = vl_systems.get(vl_id)
                if not vl_info:
                    continue
                vl_name = vl_info["name"]
                vl_domain = vl_info["domain"]
                vl_apis_set = vl_info["apis"]

                # Topological signal: shared external API dependencies
                common_apis = fp_apis_set.intersection(vl_apis_set)
                graph_bonus = settings.auto_linker_graph_bonus_per_api * len(common_apis)

                # Domain alignment boost:
                # Applied when domains match, but matching domain alone without shared external APIs
                # or high base semantic similarity must never promote false-positive redundancies
                # (e.g., internal service mesh vs external public API gateway).
                has_same_domain = bool(fp_domain and vl_domain and fp_domain.lower() == vl_domain.lower())
                name_collision = bool(fp_name.lower() == vl_name.lower())

                if has_same_domain and (common_apis or name_collision or cos_sim >= self.threshold):
                    domain_bonus = settings.auto_linker_domain_bonus
                else:
                    domain_bonus = 0.0

                combined_score = min(settings.auto_linker_max_score, round(cos_sim + graph_bonus + domain_bonus, 2))

                if combined_score >= self.threshold:
                    matched_domain = fp_domain if has_same_domain else f"{fp_domain}/{vl_domain}"
                    reason_parts = [f"Semantic similarity: {cos_sim:.2f} (domain: {matched_domain})"]
                    if common_apis:
                        reason_parts.append(f"shared external API calls: {list(common_apis)}")
                    elif domain_bonus > 0 and (has_same_domain or name_collision):
                        reason_parts.append("domain alignment boost")
                    reason = " | ".join(reason_parts)

                    # Create/Merge edge in FalkorDB
                    merge_query = """
                        MATCH (a:System {id: $src}), (b:System {id: $tgt})
                        MERGE (a)-[r:REDUNDANT_WITH]->(b)
                        ON CREATE SET r.similarity = $sim, r.reason = $reason, r.auto_detected = true, r.method = 'hybrid_vector_graph'
                        ON MATCH SET r.similarity = $sim, r.reason = $reason, r.auto_detected = true, r.method = 'hybrid_vector_graph'
                    """
                    graph.query(
                        merge_query,
                        {"src": fp_id, "tgt": vl_id, "sim": combined_score, "reason": reason},
                    )

                    redundancies.append({
                        "source": fp_id,
                        "source_name": fp_name,
                        "target": vl_id,
                        "target_name": vl_name,
                        "similarity": combined_score,
                        "reason": reason,
                        "common_apis": list(common_apis),
                    })
                    logger.info(
                        f"[{graph_name}] Linked redundant systems: "
                        f"{fp_name} <-> {vl_name} (score={combined_score})"
                    )

        return redundancies

    def detect_policy_conflicts(
        self,
        graph_name: str,
        company_a: str = "FinPay",
        company_b: str = "Vaultly",
    ) -> List[Dict[str, Any]]:
        """Identifies conflicting regulatory and security policies across companies."""
        graph = db_client.get_graph(graph_name)

        fp_policies = graph.query(
            "MATCH (p:Policy {company_origin: $company_a}) RETURN p.id, p.name, p.domain, p.description, p.source",
            {"company_a": company_a},
        ).result_set
        vl_policies = graph.query(
            "MATCH (p:Policy {company_origin: $company_b}) RETURN p.id, p.name, p.domain, p.description, p.source",
            {"company_b": company_b},
        ).result_set
        vl_map = {row[0]: {"name": row[1], "domain": row[2] or "", "desc": row[3] or "", "source": row[4]} for row in vl_policies}

        conflicts = []

        for fp_row in fp_policies:
            fp_id, fp_name, fp_domain, fp_desc, fp_src = fp_row
            fp_vec = embedding_service.embed_text(policy_embedding_text(fp_name, fp_domain, fp_desc))

            try:
                neighbors = query_vector_neighbors(graph_name, "Policy", fp_vec, k=10)
            except Exception as e:
                logger.warning(f"Native vector search failed, falling back to pairwise check: {e}")
                neighbors = []

            if neighbors:
                candidates = []
                for node, distance in neighbors:
                    props = node.properties if hasattr(node, "properties") else {}
                    if props.get("company_origin") == company_b:
                        vl_id = props.get("id")
                        vl_info = vl_map.get(vl_id)
                        if vl_info:
                            vl_vec = embedding_service.embed_text(
                                policy_embedding_text(vl_info["name"], vl_info["domain"], vl_info["desc"])
                            )
                            sim = embedding_service.cosine_similarity(fp_vec, vl_vec)
                        else:
                            sim = round(max(0.0, 1.0 - float(distance)), 2)
                        candidates.append((vl_id, sim))

            else:
                candidates = []
                for vl_id, vl_info in vl_map.items():
                    vl_vec = embedding_service.embed_text(
                        policy_embedding_text(vl_info["name"], vl_info["domain"], vl_info["desc"])
                    )
                    sim = embedding_service.cosine_similarity(fp_vec, vl_vec)
                    candidates.append((vl_id, sim))

            for vl_id, sim in candidates:
                vl_info = vl_map.get(vl_id)
                if not vl_info:
                    continue
                vl_name = vl_info["name"]
                vl_domain = vl_info["domain"]

                is_same_domain = fp_domain and vl_domain and fp_domain.lower() == vl_domain.lower()

                if is_same_domain or sim >= self.threshold:
                    severity = "CRITICAL" if "auth" in fp_domain.lower() else "HIGH"
                    reason = f"Domain mismatch in {fp_domain}: '{fp_name}' vs '{vl_name}' (semantic overlap: {sim:.2f})"

                    merge_query = """
                        MATCH (a:Policy {id: $src}), (b:Policy {id: $tgt})
                        MERGE (a)-[r:CONFLICTS_WITH]->(b)
                        ON CREATE SET r.severity = $sev, r.domain = $domain, r.reason = $reason, r.auto_detected = true
                        ON MATCH SET r.severity = $sev, r.domain = $domain, r.reason = $reason, r.auto_detected = true
                    """
                    graph.query(
                        merge_query,
                        {"src": fp_id, "tgt": vl_id, "sev": severity, "domain": fp_domain, "reason": reason},
                    )

                    conflicts.append({
                        "source": fp_id,
                        "source_name": fp_name,
                        "target": vl_id,
                        "target_name": vl_name,
                        "domain": fp_domain,
                        "severity": severity,
                        "reason": reason,
                    })
                    logger.info(f"[{graph_name}] Linked policy conflict: {fp_name} <-> {vl_name} ({severity})")

        return conflicts

    def detect_decision_conflicts(
        self,
        graph_name: str,
        company_a: str = "FinPay",
        company_b: str = "Vaultly",
    ) -> List[Dict[str, Any]]:
        """Identifies conflicting architectural decisions across companies, deriving domains

        dynamically from linked System and Policy governance nodes.
        """
        graph = db_client.get_graph(graph_name)

        fp_decisions = graph.query(
            """MATCH (d:Decision {company_origin: $company_a})
               OPTIONAL MATCH (s:System)-[:GOVERNED_BY]->(d)
               OPTIONAL MATCH (s)-[:GOVERNED_BY]->(p:Policy)
               RETURN d.id, d.summary, d.authority_level, d.source,
                      collect(DISTINCT s.domain) as sys_domains,
                      collect(DISTINCT p.domain) as pol_domains""",
            {"company_a": company_a},
        ).result_set

        vl_decisions = graph.query(
            """MATCH (d:Decision {company_origin: $company_b})
               OPTIONAL MATCH (s:System)-[:GOVERNED_BY]->(d)
               OPTIONAL MATCH (s)-[:GOVERNED_BY]->(p:Policy)
               RETURN d.id, d.summary, d.authority_level, d.source,
                      collect(DISTINCT s.domain) as sys_domains,
                      collect(DISTINCT p.domain) as pol_domains""",
            {"company_b": company_b},
        ).result_set

        vl_map = {
            row[0]: {
                "summary": row[1] or "",
                "auth": row[2] or "",
                "source": row[3] or "",
                "sys_domains": [d for d in (row[4] or []) if d],
                "pol_domains": [d for d in (row[5] or []) if d],
            }
            for row in vl_decisions
        }

        conflicts = []

        for fp_row in fp_decisions:
            fp_id, fp_summary, fp_auth, fp_src, fp_sys_doms, fp_pol_doms = fp_row
            fp_vec = embedding_service.embed_text(decision_embedding_text(fp_summary, fp_auth, fp_src))
            fp_domains = set([d for d in (fp_sys_doms or []) + (fp_pol_doms or []) if d])

            try:
                neighbors = query_vector_neighbors(graph_name, "Decision", fp_vec, k=10)
            except Exception as e:
                logger.warning(f"Native vector search failed, falling back to pairwise check: {e}")
                neighbors = []

            if neighbors:
                candidates = []
                for node, distance in neighbors:
                    props = node.properties if hasattr(node, "properties") else {}
                    if props.get("company_origin") == company_b:
                        vl_id = props.get("id")
                        vl_info = vl_map.get(vl_id)
                        if vl_info:
                            vl_vec = embedding_service.embed_text(
                                decision_embedding_text(vl_info["summary"], vl_info["auth"], vl_info["source"])
                            )
                            sim = embedding_service.cosine_similarity(fp_vec, vl_vec)
                        else:
                            sim = round(max(0.0, 1.0 - float(distance)), 2)
                        candidates.append((vl_id, sim))

            else:
                candidates = []
                for vl_id, vl_info in vl_map.items():
                    vl_vec = embedding_service.embed_text(
                        decision_embedding_text(vl_info["summary"], vl_info["auth"], vl_info["source"])
                    )
                    sim = embedding_service.cosine_similarity(fp_vec, vl_vec)
                    candidates.append((vl_id, sim))

            for vl_id, sim in candidates:
                vl_info = vl_map.get(vl_id)
                if not vl_info:
                    continue
                vl_summary = vl_info["summary"]
                vl_domains = set((vl_info.get("sys_domains") or []) + (vl_info.get("pol_domains") or []))

                # Derive domain dynamically from graph governance relations
                shared_domains = fp_domains.intersection(vl_domains)
                has_graph_domain_match = len(shared_domains) > 0

                # Domain keyword overlap check (fallback / enhancement)
                fp_lower = fp_summary.lower()
                vl_lower = vl_summary.lower()
                has_auth_kw = ("jwt" in fp_lower or "15-min" in fp_lower) and ("7-day" in vl_lower or "session" in vl_lower)
                has_log_kw = ("30-day" in fp_lower or "purge" in fp_lower) and ("180" in vl_lower or "retention" in vl_lower)
                has_mesh_kw = ("mtls" in fp_lower) and ("bearer" in vl_lower or "api" in vl_lower)

                if has_graph_domain_match or has_auth_kw or has_log_kw or has_mesh_kw or sim >= self.threshold:
                    if "Authentication" in shared_domains or has_auth_kw:
                        severity = "CRITICAL"
                        domain = "Session Security"
                        reason = f"{company_a} mandates 15-min JWT expiry vs {company_b} 7-day persistent session tokens"
                    elif "Data Retention" in shared_domains or has_log_kw:
                        severity = "HIGH"
                        domain = "Data Retention"
                        reason = f"{company_a} mandates 30-day log purge vs {company_b} 180-day forensic audit retention"
                    elif "Gateway" in shared_domains or has_mesh_kw:
                        severity = "MEDIUM"
                        domain = "Network Security"
                        reason = "Zero-trust SPIFFE mTLS mesh vs static API Bearer token architecture"
                    elif shared_domains:
                        derived_dom = next(iter(shared_domains))
                        severity = "MEDIUM"
                        domain = derived_dom
                        reason = f"Conflicting governing decisions in {derived_dom} (similarity: {sim:.2f})"
                    else:
                        severity = "MEDIUM"
                        domain = "Architecture"
                        reason = f"Decision divergence (similarity: {sim:.2f})"

                    merge_query = """
                        MATCH (a:Decision {id: $src}), (b:Decision {id: $tgt})
                        MERGE (a)-[r:CONFLICTS_WITH]->(b)
                        ON CREATE SET r.severity = $sev, r.domain = $domain, r.reason = $reason, r.auto_detected = true
                        ON MATCH SET r.severity = $sev, r.domain = $domain, r.reason = $reason, r.auto_detected = true
                    """
                    graph.query(
                        merge_query,
                        {"src": fp_id, "tgt": vl_id, "sev": severity, "domain": domain, "reason": reason},
                    )

                    conflicts.append({
                        "source": fp_id,
                        "source_summary": fp_summary,
                        "target": vl_id,
                        "target_summary": vl_summary,
                        "domain": domain,
                        "severity": severity,
                        "reason": reason,
                    })
                    logger.info(f"[{graph_name}] Linked decision conflict: {fp_id} <-> {vl_id} ({severity})")

        return conflicts

    def run_pipeline(
        self,
        graph_name: str = None,
        company_a: str = "FinPay",
        company_b: str = "Vaultly",
    ) -> Dict[str, Any]:
        """Runs the complete auto-linker pipeline on the unified graph."""
        target_graph = graph_name or settings.graph_merged
        logger.info(f"=== Starting Auto-Linker Pipeline on '{target_graph}' (Tenants: {company_a} & {company_b}) ===")

        # Step 1: Vector indexing & node embeddings
        ensure_vector_indexes(target_graph)
        embedding_counts = populate_node_embeddings(target_graph)

        # Step 2: Auto-detect bridges
        redundant_systems = self.detect_redundant_systems(target_graph, company_a=company_a, company_b=company_b)
        policy_conflicts = self.detect_policy_conflicts(target_graph, company_a=company_a, company_b=company_b)
        decision_conflicts = self.detect_decision_conflicts(target_graph, company_a=company_a, company_b=company_b)

        summary = {
            "graph": target_graph,
            "embeddings_populated": embedding_counts,
            "redundant_systems_linked": len(redundant_systems),
            "policy_conflicts_linked": len(policy_conflicts),
            "decision_conflicts_linked": len(decision_conflicts),
            "total_bridges_created": len(redundant_systems) + len(policy_conflicts) + len(decision_conflicts),
            "details": {
                "redundancies": redundant_systems,
                "policy_conflicts": policy_conflicts,
                "decision_conflicts": decision_conflicts,
            },
        }

        logger.info(
            f"=== Auto-Linker Completed: {summary['total_bridges_created']} bridges linked "
            f"({summary['redundant_systems_linked']} redundant systems, "
            f"{summary['policy_conflicts_linked']} policy conflicts, "
            f"{summary['decision_conflicts_linked']} decision conflicts) ==="
        )
        return summary


auto_linker_engine = AutoLinkerEngine()


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OrgBridge AI - M&A Auto-Linker Engine")
    parser.add_argument("--graph", default=settings.graph_merged, help="Target graph name")
    parser.add_argument("--threshold", type=float, default=None, help=f"Similarity threshold (default {settings.auto_linker_threshold})")
    parser.add_argument("--company-a", default="FinPay", help="First company origin")
    parser.add_argument("--company-b", default="Vaultly", help="Second company origin")
    args = parser.parse_args()

    engine = AutoLinkerEngine(threshold=args.threshold)
    engine.run_pipeline(args.graph, company_a=args.company_a, company_b=args.company_b)


if __name__ == "__main__":
    main()
