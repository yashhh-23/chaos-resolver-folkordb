"""Live Graph Mutation Engine for OrgBridge AI.

Satisfies Track 03's requirement: 'Keeping knowledge current as things change'.
Executes transactional Cypher MERGE, SET, and DELETE operations in FalkorDB to:
1. Resolve policy & decision conflicts live (compromise or deprecation).
2. Merge cross-company teams into unified organizational units.
3. Keep real-time knowledge current as M&A integration progresses.
"""

from typing import Dict, Any, Optional
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
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subgraph = Subgraph()

        # Step 1: Update conflicting policies and decisions to DEPRECATED
        deprecate_query = """
            MATCH (p1:Policy {id: 'finpay:pol:session_security'})-[r:CONFLICTS_WITH]->(p2:Policy {id: 'vaultly:pol:session_continuity'})
            SET p1.status = 'DEPRECATED',
                p2.status = 'DEPRECATED',
                r.status = 'RESOLVED',
                r.resolved_at = $timestamp,
                r.resolution_note = 'Superceded by Unified M&A Hybrid Session Standard'
        """
        graph.query(deprecate_query, {"timestamp": now_str})

        deprecate_dec_query = """
            MATCH (d1:Decision {id: 'finpay:dec:jwt_15m'})-[rd:CONFLICTS_WITH]->(d2:Decision {id: 'vaultly:dec:session_7d'})
            SET d1.status = 'DEPRECATED',
                d2.status = 'DEPRECATED',
                rd.status = 'RESOLVED',
                rd.resolved_at = $timestamp,
                rd.resolution_note = 'Superceded by Unified 30-min JWT Decision'
        """
        graph.query(deprecate_dec_query, {"timestamp": now_str})

        # Step 2: Create Unified M&A Policy and Decision
        create_unified_query = """
            MERGE (pol:Policy {id: 'unified:pol:hybrid_session_auth'})
            ON CREATE SET
                pol.name = 'Unified M&A Adaptive Session Policy',
                pol.domain = 'Authentication',
                pol.company_origin = 'Unified',
                pol.status = 'ACTIVE',
                pol.effective_date = '2026-10-17',
                pol.authority_level = 'Joint M&A Executive Committee',
                pol.description = 'Adaptive 30-min active session with hardware biometric refresh token (PCI-DSS compliant + frictionless mobile UX)',
                pol.source = 'M&A Resolution Order #2026-01'

            MERGE (dec:Decision {id: 'unified:dec:adaptive_jwt_30m'})
            ON CREATE SET
                dec.summary = 'Adopt 30-minute JWT token lifetime with biometric refresh on mobile',
                dec.date = '2026-10-17',
                dec.effective_date = '2026-10-17',
                dec.authority_level = 'Joint M&A Architecture Committee',
                dec.status = 'ACTIVE',
                dec.company_origin = 'Unified',
                dec.source = 'Executive Order EO-2026-04'

            MERGE (pol)-[:SUPERSEDES]->(dec)
        """
        graph.query(create_unified_query)

        # Step 3: Re-link Gatekeeper-Auth and Pulse-Identity to the new Unified Policy and Decision
        relink_query = """
            MATCH (pol:Policy {id: 'unified:pol:hybrid_session_auth'})
            MATCH (dec:Decision {id: 'unified:dec:adaptive_jwt_30m'})
            MATCH (s1:System {id: 'finpay:sys:gatekeeper_auth'})
            MATCH (s2:System {id: 'vaultly:sys:pulse_identity'})
            MERGE (s1)-[:GOVERNED_BY]->(pol)
            MERGE (s2)-[:GOVERNED_BY]->(pol)
            MERGE (s1)-[:GOVERNED_BY]->(dec)
            MERGE (s2)-[:GOVERNED_BY]->(dec)
        """
        graph.query(relink_query)

        # Build Subgraph of resolved state
        subgraph.add_node("unified:pol:hybrid_session_auth", "Unified M&A Adaptive Session Policy", "Policy", "Unified", {"status": "ACTIVE"})
        subgraph.add_node("unified:dec:adaptive_jwt_30m", "Adopt 30-min JWT Decision", "Decision", "Unified", {"status": "ACTIVE"})
        subgraph.add_node("finpay:sys:gatekeeper_auth", "Gatekeeper-Auth", "System", "FinPay")
        subgraph.add_node("vaultly:sys:pulse_identity", "Pulse-Identity", "System", "Vaultly")
        subgraph.add_edge("finpay:sys:gatekeeper_auth", "unified:pol:hybrid_session_auth", "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:pulse_identity", "unified:pol:hybrid_session_auth", "GOVERNED_BY")
        subgraph.add_edge("finpay:sys:gatekeeper_auth", "unified:dec:adaptive_jwt_30m", "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:pulse_identity", "unified:dec:adaptive_jwt_30m", "GOVERNED_BY")
        subgraph.add_edge("unified:pol:hybrid_session_auth", "unified:dec:adaptive_jwt_30m", "SUPERSEDES")

        logger.info(f"[{self.graph_name}] Live Mutation: Resolved Auth Token Conflict in FalkorDB.")

        return {
            "action": "resolve_auth_conflict",
            "status": "success",
            "timestamp": now_str,
            "unified_policy_id": "unified:pol:hybrid_session_auth",
            "resolved_conflict": "FinPay 15-min JWT vs Vaultly 7-day Session",
            "resolution_summary": (
                "Created 'Unified M&A Adaptive Session Policy' (30-min JWT with biometric refresh). "
                "Marked legacy conflicting policies as DEPRECATED. "
                "Re-governed Gatekeeper-Auth and Pulse-Identity to the unified standard."
            ),
            "subgraph": subgraph.model_dump(),
        }

    def resolve_retention_conflict(self, retention_days: int = 90) -> Dict[str, Any]:
        """Resolves the data retention conflict between FinPay (30 days) and Vaultly (180 days)

        by creating a partitioned 90-day audit standard.
        """
        graph = self._get_graph()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subgraph = Subgraph()

        deprecate_query = """
            MATCH (p1:Policy {id: 'finpay:pol:retention_compliance'})-[r:CONFLICTS_WITH]->(p2:Policy {id: 'vaultly:pol:forensic_audit_retention'})
            SET p1.status = 'DEPRECATED',
                p2.status = 'DEPRECATED',
                r.status = 'RESOLVED',
                r.resolved_at = $timestamp,
                r.resolution_note = 'Superceded by Tiered 90-Day Audit Archival Standard'
        """
        graph.query(deprecate_query, {"timestamp": now_str})

        deprecate_dec_query = """
            MATCH (d1:Decision {id: 'finpay:dec:log_purge_30d'})-[rd:CONFLICTS_WITH]->(d2:Decision {id: 'vaultly:dec:log_retention_180d'})
            SET d1.status = 'DEPRECATED',
                d2.status = 'DEPRECATED',
                rd.status = 'RESOLVED',
                rd.resolved_at = $timestamp,
                rd.resolution_note = 'Superceded by Tiered 90-Day Audit Standard'
        """
        graph.query(deprecate_dec_query, {"timestamp": now_str})

        create_unified_query = """
            MERGE (pol:Policy {id: 'unified:pol:tiered_retention_90d'})
            ON CREATE SET
                pol.name = 'Unified M&A Tiered Log & Audit Retention Policy',
                pol.domain = 'Data Retention',
                pol.company_origin = 'Unified',
                pol.status = 'ACTIVE',
                pol.effective_date = '2026-10-17',
                pol.authority_level = 'Joint Legal & CISO Council',
                pol.description = '90-day cold encrypted storage for financial audit trails with automated 30-day purge for non-audit debug telemetry',
                pol.source = 'Joint Compliance Accord 2026'

            MERGE (dec:Decision {id: 'unified:dec:tiered_retention_90d'})
            ON CREATE SET
                dec.summary = 'Adopt 90-day tiered retention with cold storage for audit logs',
                dec.date = '2026-10-17',
                dec.effective_date = '2026-10-17',
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
        graph.query(create_unified_query)

        subgraph.add_node("unified:pol:tiered_retention_90d", "Tiered Log & Audit Policy", "Policy", "Unified", {"status": "ACTIVE"})
        subgraph.add_node("unified:dec:tiered_retention_90d", "Tiered 90-Day Retention Decision", "Decision", "Unified", {"status": "ACTIVE"})
        subgraph.add_node("finpay:sys:finpay_mesh_gateway", "FinPay-Mesh-Gateway", "System", "FinPay")
        subgraph.add_node("vaultly:sys:vaultly_public_api", "Vaultly-Public-API", "System", "Vaultly")
        subgraph.add_edge("finpay:sys:finpay_mesh_gateway", "unified:pol:tiered_retention_90d", "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:vaultly_public_api", "unified:pol:tiered_retention_90d", "GOVERNED_BY")
        subgraph.add_edge("finpay:sys:finpay_mesh_gateway", "unified:dec:tiered_retention_90d", "GOVERNED_BY")
        subgraph.add_edge("vaultly:sys:vaultly_public_api", "unified:dec:tiered_retention_90d", "GOVERNED_BY")
        subgraph.add_edge("unified:pol:tiered_retention_90d", "unified:dec:tiered_retention_90d", "SUPERSEDES")

        logger.info(f"[{self.graph_name}] Live Mutation: Resolved Data Retention Conflict in FalkorDB.")

        return {
            "action": "resolve_retention_conflict",
            "status": "success",
            "timestamp": now_str,
            "unified_policy_id": "unified:pol:tiered_retention_90d",
            "resolved_conflict": "FinPay 30-day purge vs Vaultly 180-day forensic audit",
            "resolution_summary": (
                "Created 'Unified M&A Tiered Log & Audit Retention Policy' (90-day encrypted cold storage). "
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
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
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
                "timestamp": now_str,
            },
        )

        subgraph.add_node(unified_id, unified_name, "Team", "Unified")
        subgraph.add_node("finpay:person:aarav_mehta", "Aarav Mehta", "Person", "FinPay")
        subgraph.add_node("vaultly:person:diya_nair", "Diya Nair", "Person", "Vaultly")
        subgraph.add_edge("finpay:person:aarav_mehta", unified_id, "MEMBER_OF")
        subgraph.add_edge("vaultly:person:diya_nair", unified_id, "MEMBER_OF")

        logger.info(f"[{self.graph_name}] Live Mutation: Merged teams {team_a_id} and {team_b_id} into {unified_id}.")

        return {
            "action": "merge_teams",
            "status": "success",
            "timestamp": now_str,
            "unified_team_id": unified_id,
            "unified_team_name": unified_name,
            "resolution_summary": (
                f"Merged '{team_a_id}' and '{team_b_id}' into '{unified_name}'. "
                "Engineers Aarav Mehta and Diya Nair are now co-members of the joint organization."
            ),
            "subgraph": subgraph.model_dump(),
        }


live_mutations = LiveMutationEngine()
