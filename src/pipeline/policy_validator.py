"""Policy Contradiction Validation Engine.

Separates policy conflict resolution into three rigorous stages:
1. Candidate Generation: Discovers cross-company policy candidate pairs via domain matching,
   vector semantic search, and existing graph relationships without prematurely declaring conflict.
2. Contradiction Validation: Independently validates whether policies actually contradict each other
   through quantitative constraint divergence (e.g. 15-min vs 7-day TTL, 30-day vs 180-day retention),
   opposing compliance directives (purge vs retain, strict vs frictionless), and authority mismatch.
3. Conflict Reporting & Evidence Storage: Stores and formats comprehensive audit evidence including
   compared statements, effective dates, authority hierarchy, review status, and confidence scores.
"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import re

from src.utils.logger import logger
from src.embeddings.service import embedding_service


# Authority Level Weighting for Structured Severity Assessment
AUTHORITY_WEIGHTS = {
    "board": 4,
    "ciso": 4,
    "vp compliance": 4,
    "general counsel": 4,
    "audit committee": 4,
    "joint legal & ciso council": 4,
    "architecture committee": 3,
    "head of security": 3,
    "director of risk": 3,
    "head of product & security": 3,
    "lead architect": 2,
    "head of product": 2,
    "engineering vp": 2,
    "department guideline": 1,
    "team standard": 1,
}

REGULATORY_KEYWORDS = [
    "pci-dss", "pci", "soc2", "gdpr", "dpdp", "hipaa", "audit", "banking",
    "statutory", "regulator", "compliance charter", "mandate"
]


class PolicyContradictionEngine:
    """Three-stage engine for detecting and validating policy contradictions."""

    def __init__(self, semantic_threshold: float = 0.70):
        self.semantic_threshold = semantic_threshold

    @staticmethod
    def get_authority_weight(authority_level: Optional[str]) -> int:
        """Computes authority rank from 1 (team guideline) to 4 (board/CISO/compliance)."""
        if not authority_level:
            return 1
        auth_lower = authority_level.lower()
        for title, weight in AUTHORITY_WEIGHTS.items():
            if title in auth_lower:
                return weight
        return 2

    @staticmethod
    def extract_time_metrics(text: str) -> Dict[str, Any]:
        """Extracts seconds/minutes/days durations and intent keywords from policy descriptions."""
        text_lower = text.lower()
        metrics: Dict[str, Any] = {
            "ttl_seconds": None,
            "retention_days": None,
            "intents": set(),
        }

        # Seconds / minutes / hours for session/token TTL
        sec_match = re.search(r'(\d+)\s*(?:seconds?|secs?)\b', text_lower)
        min_match = re.search(r'(\d+)\s*(?:minutes?|mins?)\b', text_lower)
        hr_match = re.search(r'(\d+)\s*(?:hours?|hrs?)\b', text_lower)
        day_match = re.search(r'(\d+)\s*(?:days?)\b', text_lower)

        if sec_match:
            metrics["ttl_seconds"] = int(sec_match.group(1))
        elif min_match:
            metrics["ttl_seconds"] = int(min_match.group(1)) * 60
        elif hr_match:
            metrics["ttl_seconds"] = int(hr_match.group(1)) * 3600
        elif day_match and any(w in text_lower for w in ["token", "session", "jwt", "refresh", "auth"]):
            metrics["ttl_seconds"] = int(day_match.group(1)) * 86400

        # Retention days
        if "retention" in text_lower or "purge" in text_lower or "log" in text_lower or "audit" in text_lower:
            if day_match:
                metrics["retention_days"] = int(day_match.group(1))
            mo_match = re.search(r'(\d+)\s*(?:months?)\b', text_lower)
            if mo_match:
                metrics["retention_days"] = int(mo_match.group(1)) * 30

        # Keyword intents
        if any(w in text_lower for w in ["purge", "delete", "destroy", "minimization", "erase", "expir"]):
            metrics["intents"].add("PURGE")
        if any(w in text_lower for w in ["retain", "forensic", "preserve", "store", "keep", "audit trail"]):
            metrics["intents"].add("RETAIN")
        if any(w in text_lower for w in ["ephemeral", "capped", "strict", "short-lived", "rigid"]):
            metrics["intents"].add("STRICT_EXPIRY")
        if any(w in text_lower for w in ["persist", "frictionless", "continuity", "re-auth", "long-lived"]):
            metrics["intents"].add("PERSISTENT_SESSION")
        if any(w in text_lower for w in ["mtls", "spiffe", "zero-trust", "certificate"]):
            metrics["intents"].add("ZERO_TRUST")
        if any(w in text_lower for w in ["bearer", "api key", "shared secret", "static"]):
            metrics["intents"].add("SHARED_SECRET")

        return metrics

    def validate_contradiction(
        self,
        pol_a: Dict[str, Any],
        pol_b: Dict[str, Any],
        existing_severity: Optional[str] = None,
        existing_reason: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Stage 2: Independently evaluates whether two candidate policies contradict each other.

        Returns None if policies are compatible or non-contradictory.
        Returns a rich validation evidence dictionary if contradiction is verified.
        """
        desc_a = pol_a.get("description", "") or pol_a.get("desc", "")
        desc_b = pol_b.get("description", "") or pol_b.get("desc", "")
        dom_a = (pol_a.get("domain", "") or "").strip()
        dom_b = (pol_b.get("domain", "") or "").strip()
        name_a = pol_a.get("name", "")
        name_b = pol_b.get("name", "")

        metrics_a = self.extract_time_metrics(f"{name_a} {desc_a}")
        metrics_b = self.extract_time_metrics(f"{name_b} {desc_b}")

        is_contradiction = False
        contradiction_type = "GENERAL_POLICY_DIVERGENCE"
        review_status = "REQUIRES_LEGAL_REVIEW"
        confidence = 0.75
        concrete_proof = ""

        # Test 1: TTL / Session Lifespan Discrepancy
        ttl_a = metrics_a.get("ttl_seconds")
        ttl_b = metrics_b.get("ttl_seconds")
        if ttl_a and ttl_b and ttl_a != ttl_b:
            ratio = max(ttl_a, ttl_b) / max(1, min(ttl_a, ttl_b))
            if ratio >= 2.0 or "STRICT_EXPIRY" in metrics_a["intents"] or "PERSISTENT_SESSION" in metrics_b["intents"]:
                is_contradiction = True
                contradiction_type = "TOKEN_LIFECYCLE_TTL_CONTRADICTION"
                review_status = "CONFIRMED_CONTRADICTION"
                confidence = 0.98
                ttl_a_str = f"{ttl_a // 60}m" if ttl_a >= 60 else f"{ttl_a}s"
                ttl_b_str = f"{ttl_b // 86400}d" if ttl_b >= 86400 else f"{ttl_b // 60}m"
                concrete_proof = (
                    f"Direct session lifetime conflict: {pol_a.get('company_origin', 'FinPay')} mandates {ttl_a_str} "
                    f"({ttl_a}s) token lifecycle, while {pol_b.get('company_origin', 'Vaultly')} permits {ttl_b_str} "
                    f"({ttl_b}s) persistent session lifespan ({ratio:.0f}x divergence)."
                )

        # Test 2: Data Retention Horizon Incompatibility (e.g. 30-day purge vs 180-day forensic audit)
        ret_a = metrics_a.get("retention_days")
        ret_b = metrics_b.get("retention_days")
        if ret_a and ret_b and ret_a != ret_b:
            has_purge = "PURGE" in metrics_a["intents"] or "PURGE" in metrics_b["intents"]
            has_retain = "RETAIN" in metrics_a["intents"] or "RETAIN" in metrics_b["intents"]
            if has_purge or has_retain or abs(ret_a - ret_b) >= 30:
                is_contradiction = True
                contradiction_type = "DATA_RETENTION_HORIZON_INCOMPATIBILITY"
                review_status = "CONFIRMED_CONTRADICTION"
                confidence = 0.99
                concrete_proof = (
                    f"Regulatory retention horizon clash: {pol_a.get('company_origin', 'FinPay')} enforces {ret_a}-day "
                    f"permanent log destruction, which directly violates {pol_b.get('company_origin', 'Vaultly')}'s "
                    f"mandatory {ret_b}-day forensic audit retention requirement."
                )

        # Test 3: Opposing Regulatory or Architectural Directives
        if not is_contradiction:
            if ("PURGE" in metrics_a["intents"] and "RETAIN" in metrics_b["intents"]) or \
               ("RETAIN" in metrics_a["intents"] and "PURGE" in metrics_b["intents"]):
                is_contradiction = True
                contradiction_type = "COMPLIANCE_DIRECTIVE_OPPOSITION"
                review_status = "CONFIRMED_CONTRADICTION"
                confidence = 0.95
                concrete_proof = "Opposing legal mandates: One policy requires mandatory data purge while the counterpart requires mandatory audit retention."

            elif ("STRICT_EXPIRY" in metrics_a["intents"] and "PERSISTENT_SESSION" in metrics_b["intents"]) or \
                 ("PERSISTENT_SESSION" in metrics_a["intents"] and "STRICT_EXPIRY" in metrics_b["intents"]):
                is_contradiction = True
                contradiction_type = "SECURITY_POSTURE_MISMATCH"
                review_status = "HIGH_CONFIDENCE_CONTRADICTION"
                confidence = 0.92
                concrete_proof = "Opposing authentication standards: Strict ephemeral session cap vs frictionless multi-day persistence."

            elif ("ZERO_TRUST" in metrics_a["intents"] and "SHARED_SECRET" in metrics_b["intents"]) or \
                 ("SHARED_SECRET" in metrics_a["intents"] and "ZERO_TRUST" in metrics_b["intents"]):
                is_contradiction = True
                contradiction_type = "AUTHENTICATION_ARCHITECTURE_CONFLICT"
                review_status = "HIGH_CONFIDENCE_CONTRADICTION"
                confidence = 0.90
                concrete_proof = "Incompatible network security paradigms: SPIFFE zero-trust mTLS vs static API Bearer tokens."

        # If existing graph already flagged CONFLICTS_WITH and reason provides specific details
        if not is_contradiction and existing_reason:
            is_contradiction = True
            contradiction_type = "PRE_IDENTIFIED_CONFLICT"
            review_status = "REQUIRES_LEGAL_REVIEW"
            confidence = 0.85
            concrete_proof = existing_reason

        # If still not contradicted, verify if they are merely discussing the same domain compatibly
        if not is_contradiction:
            # Compatible policies sharing domain or topic
            return None

        # Stage 2B: Structured Severity Assessment
        auth_weight_a = self.get_authority_weight(pol_a.get("authority_level"))
        auth_weight_b = self.get_authority_weight(pol_b.get("authority_level"))
        max_auth_weight = max(auth_weight_a, auth_weight_b)

        has_regulatory_impact = any(
            k in desc_a.lower() or k in desc_b.lower() or
            k in pol_a.get("source", "").lower() or k in pol_b.get("source", "").lower()
            for k in REGULATORY_KEYWORDS
        )

        if max_auth_weight >= 4 and has_regulatory_impact:
            severity = "CRITICAL"
            authority_assessment = (
                f"Critical risk: Enacted by executive authority ({pol_a.get('authority_level', 'CISO')} / "
                f"{pol_b.get('authority_level', 'Executive')}) with statutory and compliance exposure (e.g. PCI-DSS, Banking Audit)."
            )
        elif max_auth_weight >= 3 or has_regulatory_impact:
            severity = "HIGH"
            authority_assessment = (
                f"High risk: Significant security architecture or regulatory retention disparity involving "
                f"{pol_a.get('authority_level', 'Security')} and {pol_b.get('authority_level', 'Architecture')}."
            )
        elif max_auth_weight >= 2:
            severity = "MEDIUM"
            authority_assessment = "Medium risk: Architectural friction across engineering and product team policies."
        else:
            severity = "LOW"
            authority_assessment = "Low risk: Minor operational guideline variance."

        if existing_severity and existing_severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
            # Never downgrade pre-vetted critical compliance conflicts
            if existing_severity == "CRITICAL":
                severity = "CRITICAL"

        reason = concrete_proof or existing_reason or (
            f"Policy contradiction between '{pol_a.get('name')}' and '{pol_b.get('name')}' in domain {dom_a or dom_b}."
        )

        return {
            "is_contradiction": True,
            "contradiction_type": contradiction_type,
            "review_status": review_status,
            "severity": severity,
            "confidence": confidence,
            "reason": reason,
            "concrete_proof": concrete_proof or reason,
            "authority_assessment": authority_assessment,
            "authority_weights": {"policy_a": auth_weight_a, "policy_b": auth_weight_b},
        }

    def evaluate_graph_conflicts(
        self,
        graph,
        domain_filter: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Executes the full 3-stage contradiction pipeline on a FalkorDB graph instance.

        Stage 1: Candidate Generation (Existing edges + unlinked cross-tenant policy pairs)
        Stage 2: Contradiction Validation (Quantitative divergence + opposing directives + structured severity)
        Stage 3: Evidence Storage and Conflict Formatting
        """
        # --- Stage 1: Candidate Generation ---
        # 1A. Fetch all active policies
        pol_query = """
            MATCH (p:Policy)
            WHERE coalesce(p.status, 'ACTIVE') <> 'DEPRECATED'
            OPTIONAL MATCH (p)-[:DERIVED_FROM]->(doc:Document)
            RETURN p.id, p.name, p.domain, p.description, p.effective_date, p.authority_level, p.source, p.company_origin,
                   collect(DISTINCT {id: doc.id, title: doc.title, url: doc.url, excerpt: doc.excerpt}) as docs
        """
        pol_res = graph.query(pol_query)
        policies: Dict[str, Dict[str, Any]] = {}
        for row in (pol_res.result_set or []):
            docs = [d for d in row[8] if d.get("id")]
            policies[row[0]] = {
                "id": row[0],
                "name": row[1],
                "domain": row[2] or "",
                "description": row[3] or "",
                "effective_date": row[4] or "",
                "authority_level": row[5] or "",
                "source": row[6] or "",
                "company_origin": row[7] or "",
                "docs": docs,
            }

        # 1B. Fetch existing CONFLICTS_WITH edges in the graph
        existing_edges_query = """
            MATCH (p1:Policy)-[r:CONFLICTS_WITH]-(p2:Policy)
            WHERE p1.id < p2.id
              AND coalesce(r.status, 'ACTIVE') <> 'RESOLVED'
              AND coalesce(p1.status, 'ACTIVE') <> 'DEPRECATED'
              AND coalesce(p2.status, 'ACTIVE') <> 'DEPRECATED'
            RETURN p1.id, p2.id, r.severity, r.reason, r.domain
        """
        edge_res = graph.query(existing_edges_query)
        existing_edges: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for row in (edge_res.result_set or []):
            pair = tuple(sorted([row[0], row[1]]))
            existing_edges[pair] = {
                "severity": row[2],
                "reason": row[3],
                "domain": row[4],
            }

        # Form candidate pairs
        candidate_pairs: Dict[Tuple[str, str], Dict[str, Any]] = {}

        # Add pre-existing edges as candidates
        for pair, meta in existing_edges.items():
            if pair[0] in policies and pair[1] in policies:
                candidate_pairs[pair] = meta

        # Discover unlinked candidate pairs (same domain or semantic overlap across companies)
        pol_list = list(policies.values())
        for i in range(len(pol_list)):
            for j in range(i + 1, len(pol_list)):
                p1 = pol_list[i]
                p2 = pol_list[j]
                pair = tuple(sorted([p1["id"], p2["id"]]))
                if pair in candidate_pairs:
                    continue

                # Cross-company or distinct entities
                if p1["company_origin"] == p2["company_origin"] and p1["company_origin"] not in ("Unified", ""):
                    continue

                dom_match = (
                    p1["domain"] and p2["domain"] and
                    p1["domain"].strip().lower() == p2["domain"].strip().lower()
                )

                if dom_match:
                    candidate_pairs[pair] = {"severity": None, "reason": None, "domain": p1["domain"]}
                else:
                    # Semantic search candidate generation
                    v1 = embedding_service.embed_text(f"{p1['name']} {p1['domain']} {p1['description']}")
                    v2 = embedding_service.embed_text(f"{p2['name']} {p2['domain']} {p2['description']}")
                    sim = embedding_service.cosine_similarity(v1, v2)
                    if sim >= self.semantic_threshold:
                        candidate_pairs[pair] = {"severity": None, "reason": None, "domain": p1["domain"] or p2["domain"]}

        # Apply domain filter if requested
        if domain_filter:
            df_lower = domain_filter.strip().lower()
            filtered_pairs = {}
            for pair, meta in candidate_pairs.items():
                p1 = policies[pair[0]]
                p2 = policies[pair[1]]
                if df_lower in p1["domain"].lower() or df_lower in p2["domain"].lower():
                    filtered_pairs[pair] = meta
            candidate_pairs = filtered_pairs

        # --- Stage 2 & 3: Contradiction Validation & Conflict Reporting ---
        validated_conflicts: List[Dict[str, Any]] = []

        for pair, edge_meta in candidate_pairs.items():
            p1 = policies[pair[0]]
            p2 = policies[pair[1]]

            validation = self.validate_contradiction(
                pol_a=p1,
                pol_b=p2,
                existing_severity=edge_meta.get("severity"),
                existing_reason=edge_meta.get("reason"),
            )

            # If validation determined they are compatible, filter out
            if not validation or not validation.get("is_contradiction"):
                continue

            # Store / Synchronize rich edge evidence back to FalkorDB
            now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            try:
                sync_query = """
                    MATCH (a:Policy {id: $src}), (b:Policy {id: $tgt})
                    MERGE (a)-[r:CONFLICTS_WITH]->(b)
                    SET r.severity = $sev,
                        r.domain = $domain,
                        r.reason = $reason,
                        r.contradiction_type = $c_type,
                        r.review_status = $status,
                        r.confidence = $conf,
                        r.authority_assessment = $auth_assess,
                        r.validated_at = $timestamp
                """
                graph.query(sync_query, {
                    "src": p1["id"],
                    "tgt": p2["id"],
                    "sev": validation["severity"],
                    "domain": p1["domain"] or p2["domain"],
                    "reason": validation["reason"],
                    "c_type": validation["contradiction_type"],
                    "status": validation["review_status"],
                    "conf": validation["confidence"],
                    "auth_assess": validation["authority_assessment"],
                    "timestamp": now_ts,
                })
            except Exception as e:
                logger.debug(f"Could not sync edge properties to graph: {e}")

            d1 = p1["docs"][0] if p1["docs"] else {}
            d2 = p2["docs"][0] if p2["docs"] else {}

            conflict_record = {
                "policy_a": {
                    "id": p1["id"],
                    "name": p1["name"],
                    "company": p1["company_origin"],
                    "date": p1["effective_date"],
                    "authority": p1["authority_level"],
                    "desc": p1["description"],
                    "domain": p1["domain"],
                },
                "policy_b": {
                    "id": p2["id"],
                    "name": p2["name"],
                    "company": p2["company_origin"],
                    "date": p2["effective_date"],
                    "authority": p2["authority_level"],
                    "desc": p2["description"],
                    "domain": p2["domain"],
                },
                "domain": p1["domain"] or p2["domain"],
                "severity": validation["severity"],
                "reason": validation["reason"],
                "contradiction_type": validation["contradiction_type"],
                "review_status": validation["review_status"],
                "confidence": validation["confidence"],
                "authority_assessment": validation["authority_assessment"],
                "source_doc_a": d1,
                "source_doc_b": d2,
                "all_docs_a": p1["docs"],
                "all_docs_b": p2["docs"],
            }
            validated_conflicts.append(conflict_record)

        return validated_conflicts


# Global singleton instance
policy_contradiction_engine = PolicyContradictionEngine()
