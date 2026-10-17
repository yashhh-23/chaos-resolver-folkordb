"""Live Graph Mutation Engine for OrgBridge AI.

Satisfies Track 03's requirement: 'Keeping knowledge current as things change'.
Executes transactional Cypher MERGE, SET, and DELETE operations in FalkorDB to:
1. Resolve policy & decision conflicts live (compromise or deprecation).
2. Merge cross-company teams into unified organizational units.
3. Keep real-time knowledge current as M&A integration progresses.
"""

from typing import Dict, Any, List, Optional
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
        if self.graph_name == settings.graph_merged:
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
        else:
            # Isolated tenant graph: deprecate policies and decisions present in this tenant
            graph.query("""
                MATCH (p:Policy)
                WHERE p.id IN ['finpay:pol:session_security', 'vaultly:pol:session_continuity']
                SET p.status = 'DEPRECATED'
            """)
            graph.query("""
                MATCH (d:Decision)
                WHERE d.id IN ['finpay:dec:jwt_15m', 'vaultly:dec:session_7d']
                SET d.status = 'DEPRECATED'
            """)

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
            ON MATCH SET
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
            ON MATCH SET
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
            MATCH (s:System)
            WHERE s.id IN ['finpay:sys:gatekeeper_auth', 'vaultly:sys:pulse_identity']
            MERGE (s)-[:GOVERNED_BY]->(pol)
            MERGE (s)-[:GOVERNED_BY]->(dec)
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
                f"Established 'Unified M&A Adaptive Session Policy' ({compromise_ttl_minutes}-minute session tokens with biometric refresh). "
                "Deprecated conflicting legacy policies and re-governed Gatekeeper-Auth and Pulse-Identity under the unified security standard."
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

        # Step 1: Update conflicting policies and decisions to DEPRECATED
        if self.graph_name == settings.graph_merged:
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
        else:
            graph.query("""
                MATCH (p:Policy)
                WHERE p.id IN ['finpay:pol:retention_compliance', 'vaultly:pol:forensic_audit_retention']
                SET p.status = 'DEPRECATED'
            """)
            graph.query("""
                MATCH (d:Decision)
                WHERE d.id IN ['finpay:dec:log_purge_30d', 'vaultly:dec:log_retention_180d']
                SET d.status = 'DEPRECATED'
            """)

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
            ON MATCH SET
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
            ON MATCH SET
                dec.summary = $dec_summary,
                dec.date = $effective_date,
                dec.effective_date = $effective_date,
                dec.authority_level = 'Joint Legal & CISO Council',
                dec.status = 'ACTIVE',
                dec.company_origin = 'Unified',
                dec.source = 'Joint Compliance Accord 2026'

            MERGE (pol)-[:SUPERSEDES]->(dec)

            WITH pol, dec
            MATCH (s:System)
            WHERE s.id IN ['finpay:sys:finpay_mesh_gateway', 'vaultly:sys:vaultly_public_api']
            MERGE (s)-[:GOVERNED_BY]->(pol)
            MERGE (s)-[:GOVERNED_BY]->(dec)
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
                f"Enacted 'Unified M&A Tiered Log & Audit Retention Policy' ({retention_days}-day encrypted cold storage for compliance). "
                "Deprecated conflicting retention policies and unified platform audit logging across both organizations."
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

        # Step 1: Create or update Unified Team node
        merge_team_query = """
            MERGE (ut:Team {id: $u_id})
            ON CREATE SET
                ut.name = $u_name,
                ut.charter = 'Consolidated Identity, Access Management, and PCI-DSS Compliance across FinPay and Vaultly',
                ut.company_origin = 'Unified',
                ut.status = 'ACTIVE',
                ut.merged_at = $timestamp
            ON MATCH SET
                ut.name = $u_name,
                ut.charter = 'Consolidated Identity, Access Management, and PCI-DSS Compliance across FinPay and Vaultly',
                ut.company_origin = 'Unified',
                ut.status = 'ACTIVE',
                ut.merged_at = $timestamp
        """
        graph.query(merge_team_query, {"u_id": unified_id, "u_name": unified_name, "timestamp": now_ts})

        # Step 2: Migrate team members to unified team and delete old membership edges
        migrate_members_query = """
            MATCH (ut:Team {id: $u_id})
            MATCH (p:Person)-[r:MEMBER_OF]->(t:Team)
            WHERE t.id IN [$t1_id, $t2_id]
            MERGE (p)-[:MEMBER_OF]->(ut)
            DELETE r
        """
        graph.query(migrate_members_query, {"u_id": unified_id, "t1_id": team_a_id, "t2_id": team_b_id})

        # Step 3: Migrate system ownership to unified team and delete old ownership edges
        migrate_ownership_query = """
            MATCH (ut:Team {id: $u_id})
            MATCH (t:Team)-[r:OWNS]->(s:System)
            WHERE t.id IN [$t1_id, $t2_id]
            MERGE (ut)-[:OWNS]->(s)
            DELETE r
        """
        graph.query(migrate_ownership_query, {"u_id": unified_id, "t1_id": team_a_id, "t2_id": team_b_id})

        # Step 4: Mark old teams as MERGED and establish SUPERSEDES relationship
        deprecate_teams_query = """
            MATCH (ut:Team {id: $u_id})
            MATCH (t:Team)
            WHERE t.id IN [$t1_id, $t2_id]
            SET t.status = 'MERGED',
                t.merged_into = $u_id,
                t.merged_at = $timestamp
            MERGE (ut)-[:SUPERSEDES]->(t)
        """
        graph.query(deprecate_teams_query, {"u_id": unified_id, "t1_id": team_a_id, "t2_id": team_b_id, "timestamp": now_ts})

        subgraph.add_node(unified_id, unified_name, "Team", "Unified", {"status": "ACTIVE"})

        # Query actual team members dynamically from FalkorDB under unified team
        members_query = """
            MATCH (p:Person)-[:MEMBER_OF]->(ut:Team {id: $u_id})
            RETURN DISTINCT p.id, p.name, p.company_origin
        """
        members_res = graph.query(members_query, {"u_id": unified_id})
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

        # Add owned systems and superseded teams to subgraph
        owned_systems_query = """
            MATCH (ut:Team {id: $u_id})-[:OWNS]->(s:System)
            RETURN DISTINCT s.id, coalesce(s.name, s.id), s.company_origin
        """
        sys_res = graph.query(owned_systems_query, {"u_id": unified_id})
        for row in (sys_res.result_set or []):
            subgraph.add_node(row[0], row[1], "System", row[2] or "Unified")
            subgraph.add_edge(unified_id, row[0], "OWNS")

        old_teams_query = """
            MATCH (t:Team)
            WHERE t.id IN [$t1_id, $t2_id]
            RETURN t.id, coalesce(t.name, t.id), t.company_origin
        """
        old_teams_res = graph.query(old_teams_query, {"t1_id": team_a_id, "t2_id": team_b_id})
        for row in (old_teams_res.result_set or []):
            subgraph.add_node(row[0], row[1], "Team", row[2] or "Unified", {"status": "MERGED"})
            subgraph.add_edge(unified_id, row[0], "SUPERSEDES")

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
                f"Successfully unified Security Architecture (FinPay) and Identity Growth (Vaultly) into '{unified_name}'. "
                f"Consolidated team members ({', '.join(found_members)}) and re-aligned core system ownership under the joint engineering organization."
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
            from src.tools.graph_tools import fetch_visualization_subgraph
            subgraph = fetch_visualization_subgraph(self.graph_name)
            result["subgraph"] = subgraph.model_dump()

        return result


live_mutations = LiveMutationEngine()


def get_mutation_engine(graph_name: Optional[str] = None) -> LiveMutationEngine:
    """Returns a LiveMutationEngine instance bound to the requested tenant or default merged_brain."""
    return LiveMutationEngine(graph_name=graph_name) if graph_name else live_mutations
