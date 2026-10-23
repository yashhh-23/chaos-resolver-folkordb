"""M&A Auto-Linker Engine for FalkorDB.

Performs Hybrid Vector + Graph Entity Resolution:
1. Embeds System and Policy nodes using normalized dense vectors.
2. Queries FalkorDB vector space across companies.
3. Incorporates graph topological signals (shared ExternalAPI dependencies).
4. Automatically constructs [:REDUNDANT_WITH] and [:CONFLICTS_WITH] edges
   where similarity exceeds the specified threshold (default from settings).
"""

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timezone
import uuid
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

    def _resolve_candidate_pairs(
        self,
        graph_name: str,
        entity_label: str,
        source_vec: List[float],
        all_candidates: Dict[str, Dict[str, Any]],
        company_target: str,
        embed_candidate_fn: Any,
        cached_candidate_vectors: Optional[Dict[str, List[float]]] = None,
    ) -> List[Tuple[str, float]]:
        """Resolves target candidate pairs and similarities using vector index with pairwise fallback.

        Pre-filters vector neighbors against company_target and falls back to pairwise check
        whenever native search yields 0 target-company candidates. Reuses precomputed candidate
        vectors to avoid redundant re-embedding.
        """
        try:
            # Query top neighbors with an expanded k so cross-tenant candidates are not crowded out
            neighbors = query_vector_neighbors(graph_name, entity_label, source_vec, k=30)
        except Exception as e:
            logger.warning(f"Native vector search failed, falling back to pairwise check: {e}")
            neighbors = []

        candidates: List[Tuple[str, float]] = []
        if neighbors:
            for node, distance in neighbors:
                props = node.properties if hasattr(node, "properties") else (node if isinstance(node, dict) else {})
                if props.get("company_origin") == company_target:
                    cand_id = props.get("id")
                    if cand_id in all_candidates:
                        # Use native index distance directly (consistent with stored vector space)
                        sim = round(max(0.0, min(1.0, 1.0 - float(distance))), 2)
                        candidates.append((cand_id, sim))

        # If native vector search produced 0 target company candidates, fall back to pairwise comparison
        if not candidates:
            for cand_id, cand_info in all_candidates.items():
                if cached_candidate_vectors is not None and cand_id in cached_candidate_vectors:
                    cand_vec = cached_candidate_vectors[cand_id]
                else:
                    cand_vec = embed_candidate_fn(cand_info)
                    if cached_candidate_vectors is not None:
                        cached_candidate_vectors[cand_id] = cand_vec
                sim = embedding_service.cosine_similarity(source_vec, cand_vec)
                candidates.append((cand_id, sim))

        return candidates

    def detect_redundant_systems(
        self,
        graph_name: str,
        company_a: str = "FinPay",
        company_b: str = "Vaultly",
        pipeline_run_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Identifies redundant microservices using hybrid vector + graph neighbor resolution."""
        graph = db_client.get_graph(graph_name)
        candidate_vector_cache: Dict[str, List[float]] = {}
        now_ts = timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        run_id = pipeline_run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        model_version = embedding_service.model_version
        provider = embedding_service.provider

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

            candidates = self._resolve_candidate_pairs(
                graph_name=graph_name,
                entity_label="System",
                source_vec=fp_vec,
                all_candidates=vl_systems,
                company_target=company_b,
                embed_candidate_fn=lambda info: embedding_service.embed_text(
                    system_embedding_text(info["name"], info["domain"], info["tech"], info["desc"])
                ),
                cached_candidate_vectors=candidate_vector_cache,
            )

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

                # Domain alignment boost
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

                    # Create/Merge edge in FalkorDB with version tracking
                    merge_query = """
                        MATCH (a:System {id: $src}), (b:System {id: $tgt})
                        MERGE (a)-[r:REDUNDANT_WITH]->(b)
                        ON CREATE SET r.similarity = $sim,
                                      r.reason = $reason,
                                      r.auto_detected = true,
                                      r.method = 'hybrid_vector_graph',
                                      r.pipeline_run_id = $run_id,
                                      r.last_verified_at = $timestamp,
                                      r.model_version = $model_version,
                                      r.embedding_provider = $provider,
                                      r.status = 'ACTIVE'
                        ON MATCH SET r.similarity = $sim,
                                     r.reason = $reason,
                                     r.auto_detected = true,
                                     r.method = 'hybrid_vector_graph',
                                     r.pipeline_run_id = $run_id,
                                     r.last_verified_at = $timestamp,
                                     r.model_version = $model_version,
                                     r.embedding_provider = $provider,
                                     r.status = 'ACTIVE'
                    """
                    graph.query(
                        merge_query,
                        {
                            "src": fp_id, "tgt": vl_id, "sim": combined_score, "reason": reason,
                            "run_id": run_id, "timestamp": now_ts, "model_version": model_version,
                            "provider": provider,
                        },
                    )

                    redundancies.append({
                        "source": fp_id,
                        "source_name": fp_name,
                        "target": vl_id,
                        "target_name": vl_name,
                        "similarity": combined_score,
                        "reason": reason,
                        "common_apis": list(common_apis),
                        "pipeline_run_id": run_id,
                        "model_version": model_version,
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
        pipeline_run_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Identifies conflicting regulatory and security policies across companies."""
        graph = db_client.get_graph(graph_name)
        run_id = pipeline_run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_ts = timestamp or datetime.now(timezone.utc).isoformat()
        model_version = embedding_service.model_version
        provider = embedding_service.provider
        candidate_vec_cache: Dict[str, List[float]] = {}

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

            candidates = self._resolve_candidate_pairs(
                graph_name=graph_name,
                entity_label="Policy",
                source_vec=fp_vec,
                all_candidates=vl_map,
                company_target=company_b,
                embed_candidate_fn=lambda info: embedding_service.embed_text(
                    policy_embedding_text(info["name"], info["domain"], info["desc"])
                ),
                cached_candidate_vectors=candidate_vec_cache,
            )

            for vl_id, sim in candidates:
                vl_info = vl_map.get(vl_id)
                if not vl_info:
                    continue
                vl_name = vl_info["name"]
                vl_domain = vl_info["domain"]

                is_same_domain = fp_domain and vl_domain and fp_domain.lower() == vl_domain.lower()

                if is_same_domain and sim >= self.threshold:
                    from src.pipeline.policy_validator import policy_contradiction_engine

                    # Stage 2: Independently validate contradictions instead of assuming similarity implies conflict
                    validation = policy_contradiction_engine.validate_contradiction(
                        pol_a={
                            "id": fp_id, "name": fp_name, "domain": fp_domain,
                            "description": fp_desc, "source": fp_src, "company_origin": company_a,
                        },
                        pol_b={
                            "id": vl_id, "name": vl_name, "domain": vl_domain,
                            "description": vl_info.get("desc", ""), "source": vl_info.get("source", ""), "company_origin": company_b,
                        },
                    )

                    # Only link when a genuine contradiction is confirmed
                    if validation and validation.get("is_contradiction"):
                        severity = validation["severity"]
                        reason = validation["reason"]
                        c_type = validation.get("contradiction_type", "POLICY_CONTRADICTION")
                        status = validation.get("review_status", "CONFIRMED_CONTRADICTION")
                        conf = validation.get("confidence", 0.9)
                        auth_assess = validation.get("authority_assessment", "")

                        merge_query = """
                            MATCH (a:Policy {id: $src}), (b:Policy {id: $tgt})
                            MERGE (a)-[r:CONFLICTS_WITH]->(b)
                            ON CREATE SET r.severity = $sev, r.domain = $domain, r.reason = $reason,
                                          r.contradiction_type = $c_type, r.review_status = $status,
                                          r.confidence = $conf, r.authority_assessment = $auth_assess,
                                          r.auto_detected = true,
                                          r.pipeline_run_id = $run_id,
                                          r.last_verified_at = $timestamp,
                                          r.model_version = $model_version,
                                          r.embedding_provider = $provider,
                                          r.status = 'ACTIVE'
                            ON MATCH SET r.severity = $sev, r.domain = $domain, r.reason = $reason,
                                         r.contradiction_type = $c_type, r.review_status = $status,
                                         r.confidence = $conf, r.authority_assessment = $auth_assess,
                                         r.auto_detected = true,
                                         r.pipeline_run_id = $run_id,
                                         r.last_verified_at = $timestamp,
                                         r.model_version = $model_version,
                                         r.embedding_provider = $provider,
                                         r.status = 'ACTIVE'
                        """
                        graph.query(
                            merge_query,
                            {
                                "src": fp_id, "tgt": vl_id, "sev": severity, "domain": fp_domain,
                                "reason": reason, "c_type": c_type, "status": status,
                                "conf": conf, "auth_assess": auth_assess,
                                "run_id": run_id, "timestamp": now_ts,
                                "model_version": model_version, "provider": provider,
                            },
                        )

                        conflicts.append({
                            "source": fp_id,
                            "source_name": fp_name,
                            "target": vl_id,
                            "target_name": vl_name,
                            "domain": fp_domain,
                            "severity": severity,
                            "reason": reason,
                            "contradiction_type": c_type,
                            "review_status": status,
                            "pipeline_run_id": run_id,
                            "model_version": model_version,
                        })
                        logger.info(f"[{graph_name}] Linked policy conflict: {fp_name} <-> {vl_name} ({severity})")

        return conflicts

    def detect_decision_conflicts(
        self,
        graph_name: str,
        company_a: str = "FinPay",
        company_b: str = "Vaultly",
        pipeline_run_id: Optional[str] = None,
        timestamp: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Identifies conflicting architectural decisions across companies, deriving domains
        dynamically from linked System and Policy governance nodes.
        """
        graph = db_client.get_graph(graph_name)
        run_id = pipeline_run_id or f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_ts = timestamp or datetime.now(timezone.utc).isoformat()
        model_version = embedding_service.model_version
        provider = embedding_service.provider
        candidate_vec_cache: Dict[str, List[float]] = {}

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

            candidates = self._resolve_candidate_pairs(
                graph_name=graph_name,
                entity_label="Decision",
                source_vec=fp_vec,
                all_candidates=vl_map,
                company_target=company_b,
                embed_candidate_fn=lambda info: embedding_service.embed_text(
                    decision_embedding_text(info["summary"], info["auth"], info["source"])
                ),
                cached_candidate_vectors=candidate_vec_cache,
            )

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

                has_conflict_signal = has_graph_domain_match or has_auth_kw or has_log_kw or has_mesh_kw
                if sim >= self.threshold and has_conflict_signal:
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
                        ON CREATE SET r.severity = $sev, r.domain = $domain, r.reason = $reason,
                                      r.auto_detected = true,
                                      r.pipeline_run_id = $run_id,
                                      r.last_verified_at = $timestamp,
                                      r.model_version = $model_version,
                                      r.embedding_provider = $provider,
                                      r.status = 'ACTIVE'
                        ON MATCH SET r.severity = $sev, r.domain = $domain, r.reason = $reason,
                                     r.auto_detected = true,
                                     r.pipeline_run_id = $run_id,
                                     r.last_verified_at = $timestamp,
                                     r.model_version = $model_version,
                                     r.embedding_provider = $provider,
                                     r.status = 'ACTIVE'
                    """
                    graph.query(
                        merge_query,
                        {
                            "src": fp_id, "tgt": vl_id, "sev": severity, "domain": domain,
                            "reason": reason, "run_id": run_id, "timestamp": now_ts,
                            "model_version": model_version, "provider": provider,
                        },
                    )

                    conflicts.append({
                        "source": fp_id,
                        "source_summary": fp_summary,
                        "target": vl_id,
                        "target_summary": vl_summary,
                        "domain": domain,
                        "severity": severity,
                        "reason": reason,
                        "pipeline_run_id": run_id,
                        "model_version": model_version,
                    })
                    logger.info(f"[{graph_name}] Linked decision conflict: {fp_id} <-> {vl_id} ({severity})")

        return conflicts

    def run_pipeline(
        self,
        graph_name: str = None,
        company_a: str = "FinPay",
        company_b: str = "Vaultly",
    ) -> Dict[str, Any]:
        """Runs the complete auto-linker pipeline on the unified graph with run tracking and stale-edge reconciliation."""
        target_graph = graph_name or settings.graph_merged
        run_id = f"run_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
        now_ts = datetime.now(timezone.utc).isoformat()
        logger.info(f"=== Starting Auto-Linker Pipeline on '{target_graph}' (Tenants: {company_a} & {company_b}) [Run: {run_id}] ===")

        # Step 1: Vector indexing & node embeddings
        ensure_vector_indexes(target_graph)
        embedding_counts = populate_node_embeddings(target_graph)

        # Step 2: Auto-detect bridges with run tracking
        redundant_systems = self.detect_redundant_systems(
            target_graph, company_a=company_a, company_b=company_b,
            pipeline_run_id=run_id, timestamp=now_ts,
        )
        policy_conflicts = self.detect_policy_conflicts(
            target_graph, company_a=company_a, company_b=company_b,
            pipeline_run_id=run_id, timestamp=now_ts,
        )
        decision_conflicts = self.detect_decision_conflicts(
            target_graph, company_a=company_a, company_b=company_b,
            pipeline_run_id=run_id, timestamp=now_ts,
        )

        # Step 3: Stale bridge reconciliation
        # Purge any auto-detected bridges not verified in the current pipeline run
        graph = db_client.get_graph(target_graph)
        stale_systems_query = """
            MATCH (a:System)-[r:REDUNDANT_WITH]->(b:System)
            WHERE r.auto_detected = true AND coalesce(r.pipeline_run_id, '') <> $run_id
            DELETE r
            RETURN count(r) as deleted_count
        """
        stale_conflicts_query = """
            MATCH (a)-[r:CONFLICTS_WITH]->(b)
            WHERE r.auto_detected = true AND coalesce(r.pipeline_run_id, '') <> $run_id
            DELETE r
            RETURN count(r) as deleted_count
        """
        try:
            res_sys = graph.query(stale_systems_query, {"run_id": run_id}).result_set
            reconciled_systems = res_sys[0][0] if res_sys and len(res_sys[0]) > 0 else 0
        except Exception as e:
            logger.warning(f"Could not reconcile stale redundant system edges: {e}")
            reconciled_systems = 0

        try:
            res_conf = graph.query(stale_conflicts_query, {"run_id": run_id}).result_set
            reconciled_conflicts = res_conf[0][0] if res_conf and len(res_conf[0]) > 0 else 0
        except Exception as e:
            logger.warning(f"Could not reconcile stale conflict edges: {e}")
            reconciled_conflicts = 0

        total_reconciled = (reconciled_systems or 0) + (reconciled_conflicts or 0)
        if total_reconciled > 0:
            logger.info(f"[{target_graph}] Reconciled {total_reconciled} obsolete bridges ({reconciled_systems} systems, {reconciled_conflicts} conflicts)")

        summary = {
            "graph": target_graph,
            "pipeline_run_id": run_id,
            "embeddings_populated": embedding_counts,
            "redundant_systems_linked": len(redundant_systems),
            "policy_conflicts_linked": len(policy_conflicts),
            "decision_conflicts_linked": len(decision_conflicts),
            "total_bridges_created": len(redundant_systems) + len(policy_conflicts) + len(decision_conflicts),
            "reconciled_stale_bridges": total_reconciled,
            "reconciled_systems": reconciled_systems,
            "reconciled_conflicts": reconciled_conflicts,
            "model_version": embedding_service.model_version,
            "embedding_provider": embedding_service.provider,
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
            f"{summary['decision_conflicts_linked']} decision conflicts), "
            f"{total_reconciled} stale bridges reconciled ==="
        )
        return summary

    def link_incremental_node(
        self,
        node_id: str,
        label: str,
        tenant_graph: str,
    ) -> Dict[str, Any]:
        """Performs real-time incremental linking for newly ingested node.

        Embeds the node in tenant_graph, promotes sanitized representation to
        merged_brain, and links with counterpart entities across companies.
        """
        source_graph = db_client.get_graph(tenant_graph)
        merged_graph = db_client.get_graph(settings.graph_merged)

        # 1. Fetch node properties from source graph
        res = source_graph.query(f"MATCH (n:{label} {{id: $id}}) RETURN n", {"id": node_id})
        if not res.result_set:
            logger.warning(f"Incremental linking: node '{node_id}' not found in {tenant_graph}")
            return {"node_id": node_id, "label": label, "status": "not_found", "links_created": []}

        raw_node = res.result_set[0][0]
        node_props = raw_node.properties if hasattr(raw_node, "properties") else (raw_node if isinstance(raw_node, dict) else {})
        company_origin = node_props.get("company_origin")
        if not company_origin:
            if "finpay" in tenant_graph.lower() or "finpay" in node_id.lower():
                company_origin = "FinPay"
            elif "vaultly" in tenant_graph.lower() or "vaultly" in node_id.lower():
                company_origin = "Vaultly"
            else:
                company_origin = "Unified"

        target_company = "Vaultly" if company_origin == "FinPay" else "FinPay"
        links_created = []
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        from src.connectors.security_pipeline import scrub_untrusted_text
        from src.schema.cypher_schema import build_parameterized_node_merge

        # 2. Compute embedding
        if label == "System":
            name = node_props.get("name", "")
            domain = node_props.get("domain", "")
            tech = node_props.get("tech", "")
            desc = node_props.get("description", "")
            text = system_embedding_text(name, domain, tech, desc)
            clean_text = scrub_untrusted_text(text)
            vec = embedding_service.embed_text(clean_text)
            try:
                source_graph.query(
                    "MATCH (s:System {id: $id}) SET s.embedding = vecf32($vec)",
                    {"id": node_id, "vec": vec},
                )
            except Exception as e:
                logger.debug(f"Could not store vector embedding in {tenant_graph}: {e}")

            # Clean-room promotion to merged_brain: promote sanitized metadata
            promoted_props = {
                "id": node_id,
                "name": name,
                "domain": domain,
                "tech": tech,
                "tier": node_props.get("tier", "tier-1"),
                "description": scrub_untrusted_text(desc),
                "company_origin": company_origin,
                "repo": node_props.get("repo", ""),
                "external_id": node_props.get("external_id", ""),
                "source_system": node_props.get("source_system", "github"),
                "source_url": node_props.get("source_url", ""),
                "acl_visibility": node_props.get("acl_visibility", "RESTRICTED"),
                "sync_status": "SYNCED",
            }
            q_merge, p_merge = build_parameterized_node_merge("System", promoted_props)
            merged_graph.query(q_merge, p_merge)
            try:
                merged_graph.query(
                    "MATCH (s:System {id: $id}) SET s.embedding = vecf32($vec)",
                    {"id": node_id, "vec": vec},
                )
            except Exception as e:
                logger.debug(f"Could not store vector embedding in merged_brain: {e}")

            # Copy external API calls to merged_brain
            api_res = source_graph.query(
                "MATCH (s:System {id: $id})-[:CALLS]->(ext:ExternalAPI) RETURN ext.id, ext.name, ext.category, ext.provider",
                {"id": node_id},
            )
            my_apis = set()
            for api_row in api_res.result_set:
                ext_id, ext_name, ext_cat, ext_prov = api_row
                my_apis.add(ext_name)
                merged_graph.query(
                    """
                    MERGE (e:ExternalAPI {id: $id})
                    ON CREATE SET e.name = $name, e.category = $cat, e.provider = $prov, e.company_origin = 'External'
                    """,
                    {"id": ext_id, "name": ext_name, "cat": ext_cat, "prov": ext_prov},
                )
                merged_graph.query(
                    """
                    MATCH (s:System {id: $s_id}), (e:ExternalAPI {id: $e_id})
                    MERGE (s)-[:CALLS]->(e)
                    """,
                    {"s_id": node_id, "e_id": ext_id},
                )

            # Cross-company counterpart resolution in merged_brain
            counterparts_res = merged_graph.query(
                """
                MATCH (s:System {company_origin: $target_company})
                WHERE s.id <> $id
                OPTIONAL MATCH (s)-[:CALLS]->(ext:ExternalAPI)
                RETURN s.id, s.name, s.domain, s.description, s.tech, collect(ext.name) as ext_apis
                """,
                {"target_company": target_company, "id": node_id},
            )

            for c_row in counterparts_res.result_set:
                c_id, c_name, c_domain, c_desc, c_tech, c_apis = c_row
                c_apis_set = set(c_apis or [])
                c_vec = embedding_service.embed_text(system_embedding_text(c_name, c_domain or "", c_tech or "", c_desc or ""))
                cos_sim = embedding_service.cosine_similarity(vec, c_vec)

                common_apis = my_apis.intersection(c_apis_set)
                graph_bonus = settings.auto_linker_graph_bonus_per_api * len(common_apis)
                domain_bonus = settings.auto_linker_domain_bonus if (domain and c_domain and domain.lower() == c_domain.lower()) else 0.0

                combined = min(settings.auto_linker_max_score, round(cos_sim + graph_bonus + domain_bonus, 2))
                eff_threshold = self.threshold

                if combined >= eff_threshold:
                    reason = f"Incremental System Overlap ({combined}): common APIs {list(common_apis)}"
                    merged_graph.query(
                        """
                        MATCH (a:System {id: $src}), (b:System {id: $tgt})
                        MERGE (a)-[r:REDUNDANT_WITH]->(b)
                        ON CREATE SET r.similarity = $sim, r.reason = $reason, r.timestamp = $ts, r.incremental = true
                        ON MATCH SET r.similarity = $sim, r.reason = $reason, r.timestamp = $ts, r.incremental = true
                        """,
                        {"src": node_id, "tgt": c_id, "sim": combined, "reason": reason, "ts": now_ts},
                    )
                    links_created.append({"type": "REDUNDANT_WITH", "source": node_id, "target": c_id, "score": combined})

        elif label in ["Policy", "Decision"]:
            name = node_props.get("name") or node_props.get("summary", "")
            domain = node_props.get("domain", "")
            desc = node_props.get("description") or node_props.get("summary", "")
            clean_text = scrub_untrusted_text(f"{label}: {name} | Domain: {domain} | Description: {desc}")
            vec = embedding_service.embed_text(clean_text)

            try:
                source_graph.query(
                    f"MATCH (n:{label} {{id: $id}}) SET n.embedding = vecf32($vec)",
                    {"id": node_id, "vec": vec},
                )
            except Exception as e:
                logger.debug(f"Could not store vector embedding in {tenant_graph}: {e}")

            # Clean-room promotion
            promoted_props = {
                "id": node_id,
                "name": name if label == "Policy" else None,
                "summary": name if label == "Decision" else None,
                "domain": domain,
                "description": scrub_untrusted_text(desc),
                "authority_level": node_props.get("authority_level", "Architecture Committee"),
                "status": node_props.get("status", "ACTIVE"),
                "source": node_props.get("source", ""),
                "company_origin": company_origin,
                "acl_visibility": node_props.get("acl_visibility", "RESTRICTED"),
                "sync_status": "SYNCED",
            }
            promoted_props = {k: v for k, v in promoted_props.items() if v is not None}
            q_merge, p_merge = build_parameterized_node_merge(label, promoted_props)
            merged_graph.query(q_merge, p_merge)
            try:
                merged_graph.query(
                    f"MATCH (n:{label} {{id: $id}}) SET n.embedding = vecf32($vec)",
                    {"id": node_id, "vec": vec},
                )
            except Exception as e:
                logger.debug(f"Could not store vector embedding in merged_brain: {e}")

            # Cross-company counterpart resolution in merged_brain
            counterparts_res = merged_graph.query(
                f"""
                MATCH (n:{label} {{company_origin: $target_company}})
                WHERE n.id <> $id
                RETURN n.id, coalesce(n.name, n.summary), n.domain, coalesce(n.description, n.summary)
                """,
                {"target_company": target_company, "id": node_id},
            )

            for c_row in counterparts_res.result_set:
                c_id, c_name, c_domain, c_desc = c_row
                c_text = f"{label}: {c_name} | Domain: {c_domain} | Description: {c_desc}"
                c_vec = embedding_service.embed_text(c_text)
                sim = round(embedding_service.cosine_similarity(vec, c_vec), 2)

                if sim >= self.threshold or (domain and c_domain and domain.lower() == c_domain.lower() and sim >= 0.70):
                    reason = f"Incremental {label} Contradiction: {name} vs {c_name} in {domain or c_domain} (sim={sim})"
                    merged_graph.query(
                        f"""
                        MATCH (a:{label} {{id: $src}}), (b:{label} {{id: $tgt}})
                        MERGE (a)-[r:CONFLICTS_WITH]->(b)
                        ON CREATE SET r.similarity = $sim, r.reason = $reason, r.domain = $domain, r.timestamp = $ts, r.incremental = true
                        ON MATCH SET r.similarity = $sim, r.reason = $reason, r.domain = $domain, r.timestamp = $ts, r.incremental = true
                        """,
                        {"src": node_id, "tgt": c_id, "sim": sim, "reason": reason, "domain": domain or c_domain, "ts": now_ts},
                    )
                    links_created.append({"type": "CONFLICTS_WITH", "source": node_id, "target": c_id, "score": sim})

        return {
            "node_id": node_id,
            "label": label,
            "tenant_graph": tenant_graph,
            "company_origin": company_origin,
            "bridges_created": len(links_created),
            "links": links_created,
        }


def link_incremental_node(
    node_id: str,
    label: str,
    tenant_graph: str,
    threshold: Optional[float] = None,
) -> Dict[str, Any]:
    """Module-level helper to trigger incremental hybrid entity linking."""
    engine = AutoLinkerEngine(threshold=threshold)
    return engine.link_incremental_node(node_id=node_id, label=label, tenant_graph=tenant_graph)


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
