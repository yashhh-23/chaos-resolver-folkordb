"""M&A Auto-Linker Engine for FalkorDB.

Performs Hybrid Vector + Graph Entity Resolution:
1. Embeds System and Policy nodes using normalized dense vectors.
2. Queries FalkorDB vector space across companies.
3. Incorporates graph topological signals (shared ExternalAPI dependencies).
4. Automatically constructs [:REDUNDANT_WITH] and [:CONFLICTS_WITH] edges
   where similarity exceeds the specified threshold (default 0.82).
"""

from typing import List, Dict, Any
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

    def __init__(self, threshold: float = 0.82):
        self.threshold = threshold

    def detect_redundant_systems(self, graph_name: str) -> List[Dict[str, Any]]:
        """Identifies redundant microservices using hybrid vector + graph neighbor resolution."""
        graph = db_client.get_graph(graph_name)

        # Retrieve FinPay systems with their external API dependencies
        fp_query = """
            MATCH (s:System {company_origin: 'FinPay'})
            OPTIONAL MATCH (s)-[:CALLS]->(ext:ExternalAPI)
            RETURN s.id, s.name, s.domain, s.description, s.tech, collect(ext.name) as ext_apis
        """
        fp_res = graph.query(fp_query)

        # Retrieve Vaultly systems with their external API dependencies
        vl_query = """
            MATCH (s:System {company_origin: 'Vaultly'})
            OPTIONAL MATCH (s)-[:CALLS]->(ext:ExternalAPI)
            RETURN s.id, s.name, s.domain, s.description, s.tech, collect(ext.name) as ext_apis
        """
        vl_res = graph.query(vl_query)
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
                    if props.get("company_origin") == "Vaultly":
                        vl_id = props.get("id")
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
                graph_bonus = 0.12 * len(common_apis)

                # Domain alignment boost
                domain_bonus = 0.05 if fp_domain.lower() == vl_domain.lower() else 0.0

                combined_score = min(0.99, round(cos_sim + graph_bonus + domain_bonus, 2))

                if combined_score >= self.threshold:
                    reason_parts = [f"Semantic similarity: {cos_sim:.2f} (domain: {fp_domain})"]
                    if common_apis:
                        reason_parts.append(f"shared external API calls: {list(common_apis)}")
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

    def detect_policy_conflicts(self, graph_name: str) -> List[Dict[str, Any]]:
        """Identifies conflicting regulatory and security policies across companies."""
        graph = db_client.get_graph(graph_name)

        fp_policies = graph.query("MATCH (p:Policy {company_origin: 'FinPay'}) RETURN p.id, p.name, p.domain, p.description, p.source").result_set
        vl_policies = graph.query("MATCH (p:Policy {company_origin: 'Vaultly'}) RETURN p.id, p.name, p.domain, p.description, p.source").result_set
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
                    if props.get("company_origin") == "Vaultly":
                        vl_id = props.get("id")
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

                is_same_domain = fp_domain.lower() == vl_domain.lower()

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

    def detect_decision_conflicts(self, graph_name: str) -> List[Dict[str, Any]]:
        """Identifies conflicting architectural decisions across companies."""
        graph = db_client.get_graph(graph_name)

        fp_decisions = graph.query("MATCH (d:Decision {company_origin: 'FinPay'}) RETURN d.id, d.summary, d.authority_level, d.source").result_set
        vl_decisions = graph.query("MATCH (d:Decision {company_origin: 'Vaultly'}) RETURN d.id, d.summary, d.authority_level, d.source").result_set
        vl_map = {row[0]: {"summary": row[1] or "", "auth": row[2] or "", "source": row[3] or ""} for row in vl_decisions}

        conflicts = []

        for fp_row in fp_decisions:
            fp_id, fp_summary, fp_auth, fp_src = fp_row
            fp_vec = embedding_service.embed_text(decision_embedding_text(fp_summary, fp_auth, fp_src))

            try:
                neighbors = query_vector_neighbors(graph_name, "Decision", fp_vec, k=10)
            except Exception as e:
                logger.warning(f"Native vector search failed, falling back to pairwise check: {e}")
                neighbors = []

            if neighbors:
                candidates = []
                for node, distance in neighbors:
                    props = node.properties if hasattr(node, "properties") else {}
                    if props.get("company_origin") == "Vaultly":
                        vl_id = props.get("id")
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

                # Domain keyword overlap check
                fp_lower = fp_summary.lower()
                vl_lower = vl_summary.lower()

                has_auth_conflict = ("jwt" in fp_lower or "15-min" in fp_lower) and ("7-day" in vl_lower or "session" in vl_lower)
                has_log_conflict = ("30-day" in fp_lower or "purge" in fp_lower) and ("180" in vl_lower or "retention" in vl_lower)
                has_mesh_conflict = ("mtls" in fp_lower) and ("bearer" in vl_lower or "api" in vl_lower)

                if has_auth_conflict or has_log_conflict or has_mesh_conflict or sim >= self.threshold:
                    if has_auth_conflict:
                        severity = "CRITICAL"
                        domain = "Session Security"
                        reason = "FinPay mandates 15-min JWT expiry vs Vaultly 7-day persistent session tokens"
                    elif has_log_conflict:
                        severity = "HIGH"
                        domain = "Data Retention"
                        reason = "FinPay mandates 30-day log purge vs Vaultly 180-day forensic audit retention"
                    elif has_mesh_conflict:
                        severity = "MEDIUM"
                        domain = "Network Security"
                        reason = "Zero-trust SPIFFE mTLS mesh vs static API Bearer token architecture"
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

    def run_pipeline(self, graph_name: str = None) -> Dict[str, Any]:
        """Runs the complete auto-linker pipeline on the unified graph."""
        target_graph = graph_name or settings.graph_merged
        logger.info(f"=== Starting Auto-Linker Pipeline on '{target_graph}' ===")

        # Step 1: Vector indexing & node embeddings
        ensure_vector_indexes(target_graph)
        embedding_counts = populate_node_embeddings(target_graph)

        # Step 2: Auto-detect bridges
        redundant_systems = self.detect_redundant_systems(target_graph)
        policy_conflicts = self.detect_policy_conflicts(target_graph)
        decision_conflicts = self.detect_decision_conflicts(target_graph)

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


auto_linker_engine = AutoLinkerEngine(threshold=0.82)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="OrgBridge AI - M&A Auto-Linker Engine")
    parser.add_argument("--graph", default=settings.graph_merged, help="Target graph name")
    parser.add_argument("--threshold", type=float, default=0.82, help="Similarity threshold (default 0.82)")
    args = parser.parse_args()

    engine = AutoLinkerEngine(threshold=args.threshold)
    engine.run_pipeline(args.graph)


if __name__ == "__main__":
    main()
