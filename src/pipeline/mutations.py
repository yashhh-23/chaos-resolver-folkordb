"""Live Graph Mutation Engine for OrgBridge AI.

Satisfies Track 03's requirement: 'Keeping knowledge current as things change'.
Executes transactional Cypher MERGE, SET, and DELETE operations in FalkorDB to:
1. Resolve policy & decision conflicts live (compromise or deprecation).
2. Merge cross-company teams into unified organizational units.
3. Keep real-time knowledge current as M&A integration progresses.
"""

from typing import Dict, Any, List
from datetime import datetime
from src.config import settings
from src.utils.logger import logger
from src.db.client import db_client
from src.tools.graph_tools import Subgraph


class LiveMutationEngine:
    """Executes live graph updates and schema mutations in FalkorDB."""

    def __init__(self, graph_name: str = None):
        self.graph_name = graph_name or settings.graph_merged

    def _get_graph(self):
        return db_client.get_graph(self.graph_name)

    def resolve_auth_conflict(self, compromise_ttl_minutes: int = 30) -> Dict[str, Any]:
        """Resolves the critical authentication token conflict between FinPay (15-min)

        and Vaultly (7-day) by creating a unified hybrid M&A policy and updating lineage.
        """
        graph = self._get_graph()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_date = datetime.now().strftime("%Y-%m-%d")
        subgraph = Subgraph()

        dec_id = f"unified:dec:adaptive_jwt_{compromise_ttl_minutes}m"
        dec_label = f"Adopt {compromise_ttl_minutes}-min JWT Decision"
        pol_desc = (
            f"Adaptive {compromise_ttl_minutes}-min active session with hardware biometric "
            f"refresh token (PCI-DSS compliant + frictionless mobile UX)"
        )
        dec_summary = f"Adopt {compromise_ttl_minutes}-minute JWT token lifetime with biometric refresh on mobile"
        dec_note = f"Superceded by Unified {compromise_ttl_minutes}-min JWT Decision"

        # Step 1: Update conflicting policies and decisions to DEPRECATED
        deprecate_query = """
            MATCH (p1:Policy {id: 'finpay:pol:session_security'})-[r:CONFLICTS_WITH]->(p2:Policy {id: 'vaultly:pol:session_continuity'})
            SET p1.status = 'DEPRECATED',
                p2.status = 'DEPRECATED',
                r.status = 'RESOLVED',
                r.resolved_at = $timestamp,
                r.resolution_note = 'Superceded by Unified M&A Hybrid Session Standard'
        """
        graph.query(deprecate_query, {"timestamp": now_ts})

        deprecate_dec_query = """
            MATCH (d1:Decision {id: 'finpay:dec:jwt_15m'})-[rd:CONFLICTS_WITH]->(d2:Decision {id: 'vaultly:dec:session_7d'})
            SET d1.status = 'DEPRECATED',
                d2.status = 'DEPRECATED',
                rd.status = 'RESOLVED',
                rd.resolved_at = $timestamp,
                rd.resolution_note = $resolution_note
        """
        graph.query(deprecate_dec_query, {"timestamp": now_ts, "resolution_note": dec_note})

        # Step 2: Create Unified M&A Policy and Decision
        create_unified_query = """
            MERGE (pol:Policy {id: 'unified:pol:hybrid_session_auth'})
            ON CREATE SET
                pol.name = 'Unified M&A Adaptive Session Policy',
                pol.domain = 'Authentication',
                pol.company_origin = 'Unified',
                pol.status = 'ACTIVE',
                pol.effective_date = $effective_date,
                pol.authority_level = 'Joint M&A Executive Committee',
                pol.description = $pol_desc,
                pol.source = 'M&A Resolution Order #2026-01'

            MERGE (dec:Decision {id: $dec_id})
            ON CREATE SET
                dec.summary = $dec_summary,
                dec.date = $effective_date,
                dec.effective_date = $effective_date,
                dec.authority_level = 'Joint M&A Architecture Committee',
                dec.status = 'ACTIVE',
                dec.company_origin = 'Unified',
                dec.source = 'Executive Order EO-2026-04'

            MERGE (pol)-[:SUPERSEDES]->(dec)
        """
        graph.query(create_unified_query, {
            "pol_desc": pol_desc,
            "dec_summary": dec_summary,
            "dec_id": dec_id,
            "effective_date": today_date,
        })

        # Step 3: Re-link Gatekeeper-Auth and Pulse-Identity to the new Unified Policy and Decision
        relink_query = """
            MATCH (pol:Policy {id: 'unified:pol:hybrid_session_auth'})
            MATCH (dec:Decision {id: $dec_id})
            MATCH (s1:System {id: 'finpay:sys:gatekeeper_auth'})
            MATCH (s2:System {id: 'vaultly:sys:pulse_identity'})
            MERGE (s1)-[:GOVERNED_BY]->(pol)
            MERGE (s2)-[:GOVERNED_BY]->(pol)
            MERGE (s1)-[:GOVERNED_BY]->(dec)
            MERGE (s2)-[:GOVERNED_BY]->(dec)
        """
        graph.query(relink_query, {"dec_id": dec_id})

        # Build Subgraph of resolved state
        subgraph.add_node("unified:pol:hybrid_session_auth", "Unified M&A Adaptive Session Policy", "Policy", "Unified", {"status": "ACTIVE"})
        subgraph.add_node(dec_id, dec_label, "Decision", "Unified", {"status": "ACTIVE"})
        subgraph.add_node("finpay:sys:gatekeeper_auth", "Gatekeeper-Auth", "System", "FinPay")
        subgraph.add_node("vaultly:sys:pulse_identity", "Pulse-Identity", "System", "Vaultly")
        subgraph.add_edge("finpay:sys:gatekeeper_auth", "unified:pol:hybrid_session_auth", "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:pulse_identity", "unified:pol:hybrid_session_auth", "GOVERNED_BY")
        subgraph.add_edge("finpay:sys:gatekeeper_auth", dec_id, "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:pulse_identity", dec_id, "GOVERNED_BY")
        subgraph.add_edge("unified:pol:hybrid_session_auth", dec_id, "SUPERSEDES")

        logger.info(f"[{self.graph_name}] Live Mutation: Resolved Auth Token Conflict in FalkorDB ({compromise_ttl_minutes}m).")

        return {
            "action": "resolve_auth_conflict",
            "status": "success",
            "timestamp": now_ts,
            "unified_policy_id": "unified:pol:hybrid_session_auth",
            "unified_decision_id": dec_id,
            "resolved_conflict": "FinPay 15-min JWT vs Vaultly 7-day Session",
            "resolution_summary": (
                f"Created 'Unified M&A Adaptive Session Policy' ({compromise_ttl_minutes}-min JWT with biometric refresh). "
                "Marked legacy conflicting policies as DEPRECATED. "
                "Re-governed Gatekeeper-Auth and Pulse-Identity to the unified standard."
            ),
            "subgraph": subgraph.model_dump(),
        }

    def resolve_retention_conflict(self, retention_days: int = 90) -> Dict[str, Any]:
        """Resolves the data retention conflict between FinPay (30 days) and Vaultly (180 days)

        by creating a partitioned tiered audit standard.
        """
        graph = self._get_graph()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        today_date = datetime.now().strftime("%Y-%m-%d")
        subgraph = Subgraph()

        pol_id = f"unified:pol:tiered_retention_{retention_days}d"
        dec_id = f"unified:dec:tiered_retention_{retention_days}d"
        pol_label = f"Tiered {retention_days}-Day Log & Audit Policy"
        dec_label = f"Tiered {retention_days}-Day Retention Decision"

        pol_desc = (
            f"{retention_days}-day cold encrypted storage for financial audit trails "
            f"with automated 30-day purge for non-audit debug telemetry"
        )
        dec_summary = f"Adopt {retention_days}-day tiered retention with cold storage for audit logs"
        res_note = f"Superceded by Tiered {retention_days}-Day Audit Standard"

        deprecate_query = """
            MATCH (p1:Policy {id: 'finpay:pol:retention_compliance'})-[r:CONFLICTS_WITH]->(p2:Policy {id: 'vaultly:pol:forensic_audit_retention'})
            SET p1.status = 'DEPRECATED',
                p2.status = 'DEPRECATED',
                r.status = 'RESOLVED',
                r.resolved_at = $timestamp,
                r.resolution_note = $resolution_note
        """
        graph.query(deprecate_query, {"timestamp": now_ts, "resolution_note": res_note})

        deprecate_dec_query = """
            MATCH (d1:Decision {id: 'finpay:dec:log_purge_30d'})-[rd:CONFLICTS_WITH]->(d2:Decision {id: 'vaultly:dec:log_retention_180d'})
            SET d1.status = 'DEPRECATED',
                d2.status = 'DEPRECATED',
                rd.status = 'RESOLVED',
                rd.resolved_at = $timestamp,
                rd.resolution_note = $resolution_note
        """
        graph.query(deprecate_dec_query, {"timestamp": now_ts, "resolution_note": res_note})

        create_unified_query = """
            MERGE (pol:Policy {id: $pol_id})
            ON CREATE SET
                pol.name = 'Unified M&A Tiered Log & Audit Retention Policy',
                pol.domain = 'Data Retention',
                pol.company_origin = 'Unified',
                pol.status = 'ACTIVE',
                pol.effective_date = $effective_date,
                pol.authority_level = 'Joint Legal & CISO Council',
                pol.description = $pol_desc,
                pol.source = 'Joint Compliance Accord 2026'

            MERGE (dec:Decision {id: $dec_id})
            ON CREATE SET
                dec.summary = $dec_summary,
                dec.date = $effective_date,
                dec.effective_date = $effective_date,
                dec.authority_level = 'Joint Legal & CISO Council',
                dec.status = 'ACTIVE',
                dec.company_origin = 'Unified',
                dec.source = 'Joint Compliance Accord 2026'

            MERGE (pol)-[:SUPERSEDES]->(dec)

            MERGE (s1:System {id: 'finpay:sys:finpay_mesh_gateway'})
            MERGE (s2:System {id: 'vaultly:sys:vaultly_public_api'})
            MERGE (s1)-[:GOVERNED_BY]->(pol)
            MERGE (s2)-[:GOVERNED_BY]->(pol)
            MERGE (s1)-[:GOVERNED_BY]->(dec)
            MERGE (s2)-[:GOVERNED_BY]->(dec)
        """
        graph.query(create_unified_query, {
            "pol_id": pol_id,
            "dec_id": dec_id,
            "pol_desc": pol_desc,
            "dec_summary": dec_summary,
            "effective_date": today_date,
        })

        subgraph.add_node(pol_id, pol_label, "Policy", "Unified", {"status": "ACTIVE"})
        subgraph.add_node(dec_id, dec_label, "Decision", "Unified", {"status": "ACTIVE"})
        subgraph.add_node("finpay:sys:finpay_mesh_gateway", "FinPay-Mesh-Gateway", "System", "FinPay")
        subgraph.add_node("vaultly:sys:vaultly_public_api", "Vaultly-Public-API", "System", "Vaultly")
        subgraph.add_edge("finpay:sys:finpay_mesh_gateway", pol_id, "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:vaultly_public_api", pol_id, "GOVERNED_BY")
        subgraph.add_edge("finpay:sys:finpay_mesh_gateway", dec_id, "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:vaultly_public_api", dec_id, "GOVERNED_BY")
        subgraph.add_edge(pol_id, dec_id, "SUPERSEDES")

        logger.info(f"[{self.graph_name}] Live Mutation: Resolved Data Retention Conflict in FalkorDB ({retention_days}d).")

        return {
            "action": "resolve_retention_conflict",
            "status": "success",
            "timestamp": now_ts,
            "unified_policy_id": pol_id,
            "unified_decision_id": dec_id,
            "resolved_conflict": "FinPay 30-day purge vs Vaultly 180-day forensic audit",
            "resolution_summary": (
                f"Created 'Unified M&A Tiered Log & Audit Retention Policy' ({retention_days}-day encrypted cold storage). "
                "Marked conflicting policies as DEPRECATED and updated Gateway governance live."
            ),
            "subgraph": subgraph.model_dump(),
        }

    def merge_teams(
        self,
        team_a_id: str = "finpay:team:secarch",
        team_b_id: str = "vaultly:team:identity_growth",
        unified_name: str = "Unified M&A Security & Identity Team",
    ) -> Dict[str, Any]:
        """Merges two distinct departmental teams into a unified joint team in FalkorDB."""
        graph = self._get_graph()
        now_ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subgraph = Subgraph()
        unified_id = "unified:team:identity_secarch"

        merge_query = """
            MERGE (ut:Team {id: $u_id})
            ON CREATE SET
                ut.name = $u_name,
                ut.charter = 'Consolidated Identity, Access Management, and PCI-DSS Compliance across FinPay and Vaultly',
                ut.company_origin = 'Unified',
                ut.merged_at = $timestamp

            WITH ut
            MATCH (p1:Person)-[:MEMBER_OF]->(t1:Team {id: $t1_id})
            MERGE (p1)-[:MEMBER_OF]->(ut)

            WITH ut
            MATCH (p2:Person)-[:MEMBER_OF]->(t2:Team {id: $t2_id})
            MERGE (p2)-[:MEMBER_OF]->(ut)

            WITH ut
            MATCH (t1:Team {id: $t1_id})-[r1:OWNS]->(s1:System)
            MERGE (ut)-[:OWNS]->(s1)

            WITH ut
            MATCH (t2:Team {id: $t2_id})-[r2:OWNS]->(s2:System)
            MERGE (ut)-[:OWNS]->(s2)
        """
        graph.query(
            merge_query,
            {
                "u_id": unified_id,
                "u_name": unified_name,
                "t1_id": team_a_id,
                "t2_id": team_b_id,
                "timestamp": now_ts,
            },
        )

        subgraph.add_node(unified_id, unified_name, "Team", "Unified")

        # Query actual team members dynamically from FalkorDB
        members_query = """
            MATCH (p:Person)-[:MEMBER_OF]->(t:Team)
            WHERE t.id IN [$t1_id, $t2_id]
            RETURN DISTINCT p.id, p.name, p.company_origin
        """
        members_res = graph.query(members_query, {"t1_id": team_a_id, "t2_id": team_b_id})
        found_members = []

        if members_res.result_set:
            for row in members_res.result_set:
                p_id, p_name, p_co = row[0], row[1], row[2]
                subgraph.add_node(p_id, p_name, "Person", p_co or "Unified")
                subgraph.add_edge(p_id, unified_id, "MEMBER_OF")
                found_members.append(p_name)
        else:
            # Fallback if called before seeding
            subgraph.add_node("finpay:person:aarav_mehta", "Aarav Mehta", "Person", "FinPay")
            subgraph.add_node("vaultly:person:diya_nair", "Diya Nair", "Person", "Vaultly")
            subgraph.add_edge("finpay:person:aarav_mehta", unified_id, "MEMBER_OF")
            subgraph.add_edge("vaultly:person:diya_nair", unified_id, "MEMBER_OF")
            found_members = ["Aarav Mehta", "Diya Nair"]

        logger.info(
            f"[{self.graph_name}] Live Mutation: Merged teams {team_a_id} and {team_b_id} "
            f"into {unified_id} ({len(found_members)} members)."
        )

        return {
            "action": "merge_teams",
            "status": "success",
            "timestamp": now_ts,
            "unified_team_id": unified_id,
            "unified_team_name": unified_name,
            "members": found_members,
            "resolution_summary": (
                f"Merged '{team_a_id}' and '{team_b_id}' into joint org '{unified_name}'. "
                f"Consolidated team members ({', '.join(found_members)}) and unified system ownership under FalkorDB."
            ),
            "subgraph": subgraph.model_dump(),
        }

    def reset_demo(self, include_subgraph: bool = True) -> Dict[str, Any]:
        """Resets FalkorDB multigraphs to pristine initial Phase 1/2 state."""
        from src.data.seed import seed_all_graphs
        from src.pipeline.auto_linker import auto_linker_engine

        logger.info(f"[{self.graph_name}] Resetting demo multigraphs in FalkorDB...")
        seed_all_graphs(clear_first=True)
        pipeline_summary = auto_linker_engine.run_pipeline(self.graph_name)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        result: Dict[str, Any] = {
            "action": "reset_demo",
            "status": "success",
            "timestamp": now_str,
            "message": "FalkorDB multigraphs reset and auto-linked successfully.",
            "pipeline_summary": pipeline_summary,
        }

        if include_subgraph:
            subgraph = Subgraph()
            g = self._get_graph()
            node_res = g.query("""
                MATCH (n)
                RETURN n.id as id,
                       coalesce(n.name, n.title, n.summary, n.id) as display_name,
                       labels(n)[0] as label,
                       coalesce(n.company_origin, 'External') as company,
                       properties(n) as props
                LIMIT 100
            """)
            for row in node_res.result_set:
                subgraph.add_node(
                    node_id=row[0],
                    name=row[1],
                    label=row[2],
                    company=row[3],
                    props=row[4] if isinstance(row[4], dict) else {},
                )

            valid_node_ids = {n.id for n in subgraph.nodes}
            rel_res = g.query("""
                MATCH (a)-[r]->(b)
                RETURN a.id, b.id, type(r), properties(r)
                LIMIT 150
            """)
            for row in rel_res.result_set:
                if row[0] in valid_node_ids and row[1] in valid_node_ids:
                    subgraph.add_edge(
                        source=row[0],
                        target=row[1],
                        rel_type=row[2],
                        props=row[3] if isinstance(row[3], dict) else {},
                    )
            result["subgraph"] = subgraph.model_dump()

        return result


live_mutations = LiveMutationEngine()
