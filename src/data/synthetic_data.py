"""Synthetic M&A Dataset Generator for FinPay (Acquirer) and Vaultly (Startup).

Models realistic real-world M&A dilemmas:
- Overlapping services (Auth, KYC, Core Ledger)
- Contradicting security, retention, and token policies
- Cross-referenced Jira, Slack, and RFC citations
- Namespaced provenance to prevent entity collisions
"""

from typing import List, Dict, Any
from src.schema.models import (
    CompanyOrigin,
    StatusEnum,
    TicketSeverity,
    Person,
    Team,
    System,
    Document,
    Ticket,
    Decision,
    Policy,
    ExternalAPI,
    Relationship,
)


def get_finpay_dataset() -> Dict[str, Any]:
    """Returns all entities and internal relationships for FinPay (Company A)."""
    people = [
        Person(
            id="finpay:person:aarav_mehta",
            name="Aarav Mehta",
            role="Staff Security Engineer",
            department="Security Architecture",
            email="aarav.mehta@finpay.com",
            company_origin=CompanyOrigin.FINPAY,
            pagerank=0.89,
        ),
        Person(
            id="finpay:person:priya_sharma",
            name="Priya Sharma",
            role="Principal Payments Engineer",
            department="Core Payments",
            email="priya.sharma@finpay.com",
            company_origin=CompanyOrigin.FINPAY,
            pagerank=0.94,
        ),
        Person(
            id="finpay:person:rohan_gupta",
            name="Rohan Gupta",
            role="DevOps & Platform Lead",
            department="Cloud Platform",
            email="rohan.gupta@finpay.com",
            company_origin=CompanyOrigin.FINPAY,
            pagerank=0.82,
        ),
        Person(
            id="finpay:person:neha_verma",
            name="Neha Verma",
            role="VP Compliance & Governance",
            department="Legal & Compliance",
            email="neha.verma@finpay.com",
            company_origin=CompanyOrigin.FINPAY,
            pagerank=0.78,
        ),
        # Entity collision test node
        Person(
            id="finpay:person:rahul_s",
            name="Rahul Sharma",
            role="Frontend Staff Engineer",
            department="Consumer Web",
            email="rahul.s@finpay.com",
            company_origin=CompanyOrigin.FINPAY,
            pagerank=0.65,
        ),
    ]

    teams = [
        Team(
            id="finpay:team:secarch",
            name="FinPay Security Architecture",
            charter="Enforce PCI-DSS, zero-trust infrastructure, and cryptographic standards",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Team(
            id="finpay:team:payments_core",
            name="FinPay Core Payments",
            charter="High-throughput double-entry transactional accounting and clearing",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Team(
            id="finpay:team:platform_infra",
            name="FinPay Platform Infrastructure",
            charter="Kubernetes service mesh, telemetry pipelines, and access gateways",
            company_origin=CompanyOrigin.FINPAY,
        ),
    ]

    systems = [
        System(
            id="finpay:sys:gatekeeper_auth",
            name="Gatekeeper-Auth",
            tech="Go/Redis",
            domain="Authentication",
            description="Centralized OAuth2 and session token issuance service with strict 15-min expiry",
            tier="tier-1",
            repo="github.com/finpay/gatekeeper-auth",
            company_origin=CompanyOrigin.FINPAY,
        ),
        System(
            id="finpay:sys:finpay_core_ledger",
            name="FinPay-Core-Ledger",
            tech="Java/PostgreSQL",
            domain="Ledger",
            description="Double-entry ledger handling banking settlement, balance reconciliation, and Stripe gateway",
            tier="tier-1",
            repo="github.com/finpay/ledger-core",
            company_origin=CompanyOrigin.FINPAY,
        ),
        System(
            id="finpay:sys:customer_kyc",
            name="Customer-KYC-Service",
            tech="Python/FastAPI",
            domain="KYC",
            description="Customer identity verification pipeline calling UIDAI Aadhaar verification gateway",
            tier="tier-2",
            repo="github.com/finpay/customer-kyc",
            company_origin=CompanyOrigin.FINPAY,
        ),
        System(
            id="finpay:sys:finpay_mesh_gateway",
            name="FinPay-Mesh-Gateway",
            tech="Envoy/Istio",
            domain="Gateway",
            description="Zero-trust ingress and service mesh gateway enforcing SPIFFE mTLS authentication",
            tier="tier-1",
            repo="github.com/finpay/mesh-gateway",
            company_origin=CompanyOrigin.FINPAY,
        ),
        # Entity collision test service
        System(
            id="finpay:sys:core_api",
            name="core-api",
            tech="Go/gRPC",
            domain="Core Services",
            description="FinPay enterprise core routing microservice",
            tier="tier-1",
            repo="github.com/finpay/core-api",
            company_origin=CompanyOrigin.FINPAY,
        ),
    ]

    documents = [
        Document(
            id="finpay:doc:rfc_sec_089",
            title="RFC-089: PCI-DSS Ephemeral Session Expiry Standard",
            doc_type="RFC",
            url="https://wiki.finpay.internal/rfc/089",
            excerpt="Mandates all consumer session tokens expire strictly after 15 minutes of inactivity to satisfy PCI-DSS audit clause 8.2.",
            author_id="finpay:person:aarav_mehta",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Document(
            id="finpay:doc:postmortem_2025_09",
            title="Postmortem: Long-lived Token Leakage in Partner Gateway",
            doc_type="Postmortem",
            url="https://wiki.finpay.internal/incidents/2025-09",
            excerpt="Unchecked token longevity caused session replay vulnerability. Incident resolved by enforcing 15-minute max TTL.",
            author_id="finpay:person:aarav_mehta",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Document(
            id="finpay:doc:gov_log_retention",
            title="FinPay Security Standard: 30-Day Log Minimization",
            doc_type="Policy Doc",
            url="https://wiki.finpay.internal/policies/sec-pol-12",
            excerpt="All access logs, debug traces, and telemetry files must be permanently purged after 30 days to reduce data exposure surface.",
            author_id="finpay:person:neha_verma",
            company_origin=CompanyOrigin.FINPAY,
        ),
    ]

    tickets = [
        Ticket(
            id="finpay:tkt:fin_1042",
            title="Enforce strict 15-minute JWT expiration across Gatekeeper-Auth",
            ticket_type="Incident Mitigation",
            severity=TicketSeverity.HIGH,
            status="CLOSED",
            resolved_by_id="finpay:person:aarav_mehta",
            affects_system_id="finpay:sys:gatekeeper_auth",
            external_id="FIN-1042",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Ticket(
            id="finpay:tkt:fin_2198",
            title="Automate 30-day lifecycle expiration rule on telemetry S3 buckets",
            ticket_type="Task",
            severity=TicketSeverity.MEDIUM,
            status="CLOSED",
            resolved_by_id="finpay:person:rohan_gupta",
            affects_system_id="finpay:sys:finpay_mesh_gateway",
            external_id="FIN-2198",
            company_origin=CompanyOrigin.FINPAY,
        ),
    ]

    decisions = [
        Decision(
            id="finpay:dec:jwt_15m",
            summary="Use 15-min JWT expiry for PCI compliance across all web and mobile clients",
            date="2025-11-10",
            effective_date="2025-12-01",
            authority_level="CISO / Architecture Committee",
            status=StatusEnum.ACTIVE,
            source="Slack #sec-arch",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Decision(
            id="finpay:dec:log_purge_30d",
            summary="Strict 30-day purge of all raw application, audit, and access logs",
            date="2025-08-15",
            effective_date="2025-09-01",
            authority_level="VP Compliance",
            status=StatusEnum.ACTIVE,
            source="Notion SEC-POL-12",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Decision(
            id="finpay:dec:mtls_enforcement",
            summary="Mandate Istio mTLS with SPIFFE IDs for all internal inter-service calls",
            date="2025-06-20",
            effective_date="2025-07-01",
            authority_level="Architecture Committee",
            status=StatusEnum.ACTIVE,
            source="Jira FIN-902",
            company_origin=CompanyOrigin.FINPAY,
        ),
    ]

    policies = [
        Policy(
            id="finpay:pol:session_security",
            name="FinPay Session Security Policy",
            domain="Authentication",
            description="Ephemeral token lifecycles strictly capped at 900 seconds. PCI-DSS Requirement 8.2.",
            effective_date="2025-12-01",
            authority_level="CISO",
            status=StatusEnum.ACTIVE,
            source="FinPay Security Standard v4.1",
            company_origin=CompanyOrigin.FINPAY,
        ),
        Policy(
            id="finpay:pol:retention_compliance",
            name="FinPay Data Minimization & Log Retention",
            domain="Data Retention",
            description="Delete all access logs, debug traces, and telemetry after 30 days to mitigate data leak exposure.",
            effective_date="2025-09-01",
            authority_level="VP Compliance",
            status=StatusEnum.ACTIVE,
            source="Legal & Compliance Charter",
            company_origin=CompanyOrigin.FINPAY,
        ),
    ]

    relationships = [
        # Team memberships
        Relationship(source_id="finpay:person:aarav_mehta", target_id="finpay:team:secarch", rel_type="MEMBER_OF"),
        Relationship(source_id="finpay:person:priya_sharma", target_id="finpay:team:payments_core", rel_type="MEMBER_OF"),
        Relationship(source_id="finpay:person:rohan_gupta", target_id="finpay:team:platform_infra", rel_type="MEMBER_OF"),
        Relationship(source_id="finpay:person:rahul_s", target_id="finpay:team:platform_infra", rel_type="MEMBER_OF"),
        # System ownership
        Relationship(source_id="finpay:person:aarav_mehta", target_id="finpay:sys:gatekeeper_auth", rel_type="OWNS"),
        Relationship(source_id="finpay:team:secarch", target_id="finpay:sys:gatekeeper_auth", rel_type="OWNS"),
        Relationship(source_id="finpay:person:priya_sharma", target_id="finpay:sys:finpay_core_ledger", rel_type="OWNS"),
        Relationship(source_id="finpay:team:payments_core", target_id="finpay:sys:finpay_core_ledger", rel_type="OWNS"),
        Relationship(source_id="finpay:person:rohan_gupta", target_id="finpay:sys:finpay_mesh_gateway", rel_type="OWNS"),
        Relationship(source_id="finpay:person:aarav_mehta", target_id="finpay:sys:customer_kyc", rel_type="OWNS"),
        Relationship(source_id="finpay:person:rahul_s", target_id="finpay:sys:core_api", rel_type="OWNS"),
        # Authorship & resolution
        Relationship(source_id="finpay:person:aarav_mehta", target_id="finpay:doc:rfc_sec_089", rel_type="AUTHORED"),
        Relationship(source_id="finpay:person:aarav_mehta", target_id="finpay:doc:postmortem_2025_09", rel_type="AUTHORED"),
        Relationship(source_id="finpay:person:neha_verma", target_id="finpay:doc:gov_log_retention", rel_type="AUTHORED"),
        Relationship(source_id="finpay:person:aarav_mehta", target_id="finpay:tkt:fin_1042", rel_type="RESOLVED"),
        Relationship(source_id="finpay:person:rohan_gupta", target_id="finpay:tkt:fin_2198", rel_type="RESOLVED"),
        Relationship(source_id="finpay:tkt:fin_1042", target_id="finpay:sys:gatekeeper_auth", rel_type="AFFECTS"),
        Relationship(source_id="finpay:tkt:fin_2198", target_id="finpay:sys:finpay_mesh_gateway", rel_type="AFFECTS"),
        # System governance & dependencies
        Relationship(source_id="finpay:sys:gatekeeper_auth", target_id="finpay:dec:jwt_15m", rel_type="GOVERNED_BY"),
        Relationship(source_id="finpay:sys:gatekeeper_auth", target_id="finpay:pol:session_security", rel_type="GOVERNED_BY"),
        Relationship(source_id="finpay:sys:finpay_mesh_gateway", target_id="finpay:dec:log_purge_30d", rel_type="GOVERNED_BY"),
        Relationship(source_id="finpay:sys:finpay_mesh_gateway", target_id="finpay:pol:retention_compliance", rel_type="GOVERNED_BY"),
        Relationship(source_id="finpay:sys:finpay_mesh_gateway", target_id="finpay:dec:mtls_enforcement", rel_type="GOVERNED_BY"),
        Relationship(source_id="finpay:sys:finpay_core_ledger", target_id="finpay:sys:gatekeeper_auth", rel_type="DEPENDS_ON"),
        # Decision/Policy lineage
        Relationship(source_id="finpay:dec:jwt_15m", target_id="finpay:doc:rfc_sec_089", rel_type="DERIVED_FROM"),
        Relationship(source_id="finpay:dec:jwt_15m", target_id="finpay:tkt:fin_1042", rel_type="DERIVED_FROM"),
        Relationship(source_id="finpay:pol:session_security", target_id="finpay:doc:rfc_sec_089", rel_type="DERIVED_FROM"),
        Relationship(source_id="finpay:pol:retention_compliance", target_id="finpay:doc:gov_log_retention", rel_type="DERIVED_FROM"),
    ]

    return {
        "people": people,
        "teams": teams,
        "systems": systems,
        "documents": documents,
        "tickets": tickets,
        "decisions": decisions,
        "policies": policies,
        "relationships": relationships,
    }


def get_vaultly_dataset() -> Dict[str, Any]:
    """Returns all entities and internal relationships for Vaultly (Company B)."""
    people = [
        Person(
            id="vaultly:person:diya_nair",
            name="Diya Nair",
            role="Senior Backend Developer",
            department="Identity & Growth",
            email="diya.nair@vaultly.io",
            company_origin=CompanyOrigin.VAULTLY,
            pagerank=0.92,
        ),
        Person(
            id="vaultly:person:kabir_patel",
            name="Kabir Patel",
            role="Lead Systems Architect",
            department="Core Ledger",
            email="kabir.patel@vaultly.io",
            company_origin=CompanyOrigin.VAULTLY,
            pagerank=0.91,
        ),
        Person(
            id="vaultly:person:tanya_sen",
            name="Tanya Sen",
            role="Head of Information Security",
            department="SecOps & Compliance",
            email="tanya.sen@vaultly.io",
            company_origin=CompanyOrigin.VAULTLY,
            pagerank=0.85,
        ),
        Person(
            id="vaultly:person:arjun_das",
            name="Arjun Das",
            role="Lead Mobile Architect",
            department="Mobile App",
            email="arjun.das@vaultly.io",
            company_origin=CompanyOrigin.VAULTLY,
            pagerank=0.76,
        ),
        # Entity collision test node
        Person(
            id="vaultly:person:rahul_s",
            name="Rahul Sharma",
            role="Data Platform Engineer",
            department="Data Infrastructure",
            email="rahul.s@vaultly.io",
            company_origin=CompanyOrigin.VAULTLY,
            pagerank=0.68,
        ),
    ]

    teams = [
        Team(
            id="vaultly:team:identity_growth",
            name="Vaultly Growth & Identity",
            charter="Maximize user onboarding velocity and frictionless consumer login",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Team(
            id="vaultly:team:ledger_eng",
            name="Vaultly High-Frequency Ledger",
            charter="Ultra-low latency micro-deposits, wallet transfers, and instant payouts",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Team(
            id="vaultly:team:app_experience",
            name="Vaultly Mobile Experience",
            charter="Native iOS and Android consumer banking application experience",
            company_origin=CompanyOrigin.VAULTLY,
        ),
    ]

    systems = [
        System(
            id="vaultly:sys:pulse_identity",
            name="Pulse-Identity",
            tech="Node/PostgreSQL",
            domain="Authentication",
            description="Customer authentication service issuing 7-day persistent session refresh tokens for mobile retention",
            tier="tier-1",
            repo="github.com/vaultly-org/pulse-identity",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        System(
            id="vaultly:sys:vault_engine",
            name="Vault-Engine",
            tech="Rust/RocksDB",
            domain="Ledger",
            description="Embedded key-value settlement engine handling sub-millisecond wallet transactions and Stripe webhooks",
            tier="tier-1",
            repo="github.com/vaultly-org/vault-engine",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        System(
            id="vaultly:sys:user_onboarding",
            name="User-Onboarding-Verification",
            tech="TypeScript/NestJS",
            domain="KYC",
            description="Instant onboarding flow performing biometric selfie and UIDAI Aadhaar verification",
            tier="tier-2",
            repo="github.com/vaultly-org/onboarding-svc",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        System(
            id="vaultly:sys:vaultly_public_api",
            name="Vaultly-Public-API",
            tech="Express/Redis",
            domain="Gateway",
            description="Edge API gateway terminating consumer requests with static Bearer tokens",
            tier="tier-1",
            repo="github.com/vaultly-org/public-gateway",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        # Entity collision test service
        System(
            id="vaultly:sys:core_api",
            name="core-api",
            tech="Node/Express",
            domain="Core Services",
            description="Vaultly internal microservice orchestrator",
            tier="tier-1",
            repo="github.com/vaultly-org/core-api",
            company_origin=CompanyOrigin.VAULTLY,
        ),
    ]

    documents = [
        Document(
            id="vaultly:doc:rfc_ux_042",
            title="RFC-042: Frictionless 7-Day Mobile Session Persistence",
            doc_type="RFC",
            url="https://notion.vaultly.internal/rfc-42",
            excerpt="Permits 7-day persistent refresh tokens on verified mobile devices to eliminate aggressive re-authentication churn.",
            author_id="vaultly:person:diya_nair",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Document(
            id="vaultly:doc:compliance_audit_2026",
            title="Neobank Forensic Audit Standard: 180-Day Retention Addendum",
            doc_type="Audit Guidelines",
            url="https://notion.vaultly.internal/audit-2026",
            excerpt="Mandates all transactional audit logs, authentication timestamps, and ledger writes be retained for minimum 180 days.",
            author_id="vaultly:person:tanya_sen",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Document(
            id="vaultly:doc:arch_vault_engine",
            title="Vault-Engine Low-Latency Settlement Specification",
            doc_type="Architecture",
            url="https://notion.vaultly.internal/vault-arch",
            excerpt="Rust-based ledger architecture achieving 50k TPS with write-ahead logging and external Stripe payout synchronization.",
            author_id="vaultly:person:kabir_patel",
            company_origin=CompanyOrigin.VAULTLY,
        ),
    ]

    tickets = [
        Ticket(
            id="vaultly:tkt:vault_310",
            title="Extend mobile refresh token validity to 7 days for UX improvement",
            ticket_type="Feature Enhancement",
            severity=TicketSeverity.HIGH,
            status="CLOSED",
            resolved_by_id="vaultly:person:diya_nair",
            affects_system_id="vaultly:sys:pulse_identity",
            external_id="VAULT-310",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Ticket(
            id="vaultly:tkt:vault_884",
            title="Configure cold storage archival to preserve 180 days of audit trails",
            ticket_type="Compliance Task",
            severity=TicketSeverity.CRITICAL,
            status="CLOSED",
            resolved_by_id="vaultly:person:tanya_sen",
            affects_system_id="vaultly:sys:vaultly_public_api",
            external_id="VAULT-884",
            company_origin=CompanyOrigin.VAULTLY,
        ),
    ]

    decisions = [
        Decision(
            id="vaultly:dec:session_7d",
            summary="Allow 7-day persistent session tokens for frictionless mobile UX",
            date="2026-02-14",
            effective_date="2026-03-01",
            authority_level="Head of Product & Security",
            status=StatusEnum.ACTIVE,
            source="Notion RFC-42",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Decision(
            id="vaultly:dec:log_retention_180d",
            summary="Keep forensic audit logs for 180 days per Neobank partnership agreement",
            date="2026-01-10",
            effective_date="2026-01-20",
            authority_level="Head of Security",
            status=StatusEnum.ACTIVE,
            source="Slack #compliance-war-room",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Decision(
            id="vaultly:dec:api_key_bearer",
            summary="Use API Bearer tokens with shared secret header over HTTPS",
            date="2025-10-05",
            effective_date="2025-10-15",
            authority_level="Lead Architect",
            status=StatusEnum.ACTIVE,
            source="Jira VAULT-104",
            company_origin=CompanyOrigin.VAULTLY,
        ),
    ]

    policies = [
        Policy(
            id="vaultly:pol:session_continuity",
            name="Vaultly Frictionless Session Policy",
            domain="Authentication",
            description="Allow mobile device refresh tokens to persist up to 7 days with biometric re-auth.",
            effective_date="2026-03-01",
            authority_level="Head of Product & Security",
            status=StatusEnum.ACTIVE,
            source="Vaultly UX Policy Manual",
            company_origin=CompanyOrigin.VAULTLY,
        ),
        Policy(
            id="vaultly:pol:forensic_audit_retention",
            name="Vaultly Forensic Audit Retention Policy",
            domain="Data Retention",
            description="Audit trails, transactional signatures, and access logs must be retained for at least 180 days for banking audits.",
            effective_date="2026-01-20",
            authority_level="Head of Security",
            status=StatusEnum.ACTIVE,
            source="Neobank Partner Addendum",
            company_origin=CompanyOrigin.VAULTLY,
        ),
    ]

    relationships = [
        # Team memberships
        Relationship(source_id="vaultly:person:diya_nair", target_id="vaultly:team:identity_growth", rel_type="MEMBER_OF"),
        Relationship(source_id="vaultly:person:kabir_patel", target_id="vaultly:team:ledger_eng", rel_type="MEMBER_OF"),
        Relationship(source_id="vaultly:person:tanya_sen", target_id="vaultly:team:identity_growth", rel_type="MEMBER_OF"),
        Relationship(source_id="vaultly:person:arjun_das", target_id="vaultly:team:app_experience", rel_type="MEMBER_OF"),
        Relationship(source_id="vaultly:person:rahul_s", target_id="vaultly:team:ledger_eng", rel_type="MEMBER_OF"),
        # System ownership
        Relationship(source_id="vaultly:person:diya_nair", target_id="vaultly:sys:pulse_identity", rel_type="OWNS"),
        Relationship(source_id="vaultly:team:identity_growth", target_id="vaultly:sys:pulse_identity", rel_type="OWNS"),
        Relationship(source_id="vaultly:person:kabir_patel", target_id="vaultly:sys:vault_engine", rel_type="OWNS"),
        Relationship(source_id="vaultly:team:ledger_eng", target_id="vaultly:sys:vault_engine", rel_type="OWNS"),
        Relationship(source_id="vaultly:person:diya_nair", target_id="vaultly:sys:user_onboarding", rel_type="OWNS"),
        Relationship(source_id="vaultly:person:tanya_sen", target_id="vaultly:sys:vaultly_public_api", rel_type="OWNS"),
        Relationship(source_id="vaultly:person:rahul_s", target_id="vaultly:sys:core_api", rel_type="OWNS"),
        # Authorship & resolution
        Relationship(source_id="vaultly:person:diya_nair", target_id="vaultly:doc:rfc_ux_042", rel_type="AUTHORED"),
        Relationship(source_id="vaultly:person:tanya_sen", target_id="vaultly:doc:compliance_audit_2026", rel_type="AUTHORED"),
        Relationship(source_id="vaultly:person:kabir_patel", target_id="vaultly:doc:arch_vault_engine", rel_type="AUTHORED"),
        Relationship(source_id="vaultly:person:diya_nair", target_id="vaultly:tkt:vault_310", rel_type="RESOLVED"),
        Relationship(source_id="vaultly:person:tanya_sen", target_id="vaultly:tkt:vault_884", rel_type="RESOLVED"),
        Relationship(source_id="vaultly:tkt:vault_310", target_id="vaultly:sys:pulse_identity", rel_type="AFFECTS"),
        Relationship(source_id="vaultly:tkt:vault_884", target_id="vaultly:sys:vaultly_public_api", rel_type="AFFECTS"),
        # System governance & dependencies
        Relationship(source_id="vaultly:sys:pulse_identity", target_id="vaultly:dec:session_7d", rel_type="GOVERNED_BY"),
        Relationship(source_id="vaultly:sys:pulse_identity", target_id="vaultly:pol:session_continuity", rel_type="GOVERNED_BY"),
        Relationship(source_id="vaultly:sys:vaultly_public_api", target_id="vaultly:dec:log_retention_180d", rel_type="GOVERNED_BY"),
        Relationship(source_id="vaultly:sys:vaultly_public_api", target_id="vaultly:pol:forensic_audit_retention", rel_type="GOVERNED_BY"),
        Relationship(source_id="vaultly:sys:vaultly_public_api", target_id="vaultly:dec:api_key_bearer", rel_type="GOVERNED_BY"),
        Relationship(source_id="vaultly:sys:vault_engine", target_id="vaultly:sys:pulse_identity", rel_type="DEPENDS_ON"),
        # Decision/Policy lineage
        Relationship(source_id="vaultly:dec:session_7d", target_id="vaultly:doc:rfc_ux_042", rel_type="DERIVED_FROM"),
        Relationship(source_id="vaultly:dec:session_7d", target_id="vaultly:tkt:vault_310", rel_type="DERIVED_FROM"),
        Relationship(source_id="vaultly:pol:session_continuity", target_id="vaultly:doc:rfc_ux_042", rel_type="DERIVED_FROM"),
        Relationship(source_id="vaultly:pol:forensic_audit_retention", target_id="vaultly:doc:compliance_audit_2026", rel_type="DERIVED_FROM"),
    ]

    return {
        "people": people,
        "teams": teams,
        "systems": systems,
        "documents": documents,
        "tickets": tickets,
        "decisions": decisions,
        "policies": policies,
        "relationships": relationships,
    }


def get_shared_external_dependencies() -> Dict[str, Any]:
    """Returns shared external nodes and calls from both companies to demonstrate hybrid graph resolution."""
    external_apis = [
        ExternalAPI(
            id="ext:api:uidai_aadhaar",
            name="UIDAI_Aadhaar",
            category="Identity & Verification",
            provider="Unique Identification Authority of India",
        ),
        ExternalAPI(
            id="ext:api:stripe",
            name="Stripe_Gateway",
            category="Payment Processing",
            provider="Stripe, Inc.",
        ),
        ExternalAPI(
            id="ext:api:aws_kms",
            name="AWS_KMS",
            category="Key Management",
            provider="Amazon Web Services",
        ),
    ]

    external_calls = [
        # Shared KYC dependency
        Relationship(source_id="finpay:sys:customer_kyc", target_id="ext:api:uidai_aadhaar", rel_type="CALLS"),
        Relationship(source_id="vaultly:sys:user_onboarding", target_id="ext:api:uidai_aadhaar", rel_type="CALLS"),
        # Shared payment dependency
        Relationship(source_id="finpay:sys:finpay_core_ledger", target_id="ext:api:stripe", rel_type="CALLS"),
        Relationship(source_id="vaultly:sys:vault_engine", target_id="ext:api:stripe", rel_type="CALLS"),
        # Shared key management
        Relationship(source_id="finpay:sys:gatekeeper_auth", target_id="ext:api:aws_kms", rel_type="CALLS"),
        Relationship(source_id="vaultly:sys:pulse_identity", target_id="ext:api:aws_kms", rel_type="CALLS"),
    ]

    return {
        "external_apis": external_apis,
        "relationships": external_calls,
    }


def get_ma_bridge_relationships() -> List[Relationship]:
    """Returns cross-company bridge edges for the unified 'merged_brain' graph.

    Explicitly models canonical M&A links aligned with the AutoLinker engine:
    - [:REDUNDANT_WITH] for overlapping microservices
    - [:CONFLICTS_WITH] for contradicting decisions & policies
    """
    return [
        # Redundant Systems (Hybrid Vector + Graph Resolution)
        Relationship(
            source_id="finpay:sys:gatekeeper_auth",
            target_id="vaultly:sys:pulse_identity",
            rel_type="REDUNDANT_WITH",
            properties={
                "similarity": 0.99,
                "reason": "Semantic similarity: 0.87 (domain: Authentication) | shared external API calls: ['AWS_KMS']",
                "auto_detected": True,
                "method": "hybrid_vector_graph",
            },
        ),
        Relationship(
            source_id="finpay:sys:finpay_core_ledger",
            target_id="vaultly:sys:vault_engine",
            rel_type="REDUNDANT_WITH",
            properties={
                "similarity": 0.99,
                "reason": "Semantic similarity: 0.87 (domain: Ledger) | shared external API calls: ['Stripe_Gateway']",
                "auto_detected": True,
                "method": "hybrid_vector_graph",
            },
        ),
        Relationship(
            source_id="finpay:sys:customer_kyc",
            target_id="vaultly:sys:user_onboarding",
            rel_type="REDUNDANT_WITH",
            properties={
                "similarity": 0.99,
                "reason": "Semantic similarity: 0.87 (domain: KYC) | shared external API calls: ['UIDAI_Aadhaar']",
                "auto_detected": True,
                "method": "hybrid_vector_graph",
            },
        ),
        Relationship(
            source_id="finpay:sys:core_api",
            target_id="vaultly:sys:core_api",
            rel_type="REDUNDANT_WITH",
            properties={
                "similarity": 0.87,
                "reason": "Semantic similarity: 0.82 (domain: Core Services) | domain alignment boost",
                "auto_detected": True,
                "method": "hybrid_vector_graph",
            },
        ),

        # Conflicting Decisions
        Relationship(
            source_id="finpay:dec:jwt_15m",
            target_id="vaultly:dec:session_7d",
            rel_type="CONFLICTS_WITH",
            properties={
                "severity": "CRITICAL",
                "domain": "Session Security",
                "reason": "FinPay mandates 15-min JWT expiry vs Vaultly 7-day persistent session tokens",
                "auto_detected": True,
            },
        ),
        Relationship(
            source_id="finpay:dec:log_purge_30d",
            target_id="vaultly:dec:log_retention_180d",
            rel_type="CONFLICTS_WITH",
            properties={
                "severity": "HIGH",
                "domain": "Data Retention",
                "reason": "FinPay mandates 30-day log purge vs Vaultly 180-day forensic audit retention",
                "auto_detected": True,
            },
        ),
        Relationship(
            source_id="finpay:dec:mtls_enforcement",
            target_id="vaultly:dec:api_key_bearer",
            rel_type="CONFLICTS_WITH",
            properties={
                "severity": "MEDIUM",
                "domain": "Network Security",
                "reason": "Zero-trust SPIFFE mTLS mesh vs static API Bearer token architecture",
                "auto_detected": True,
            },
        ),
        # Conflicting Policies
        Relationship(
            source_id="finpay:pol:session_security",
            target_id="vaultly:pol:session_continuity",
            rel_type="CONFLICTS_WITH",
            properties={
                "severity": "CRITICAL",
                "domain": "Authentication",
                "reason": "Domain mismatch in Authentication: 'FinPay Session Security Policy' vs 'Vaultly Frictionless Session Policy' (semantic overlap: 0.87)",
                "auto_detected": True,
            },
        ),
        Relationship(
            source_id="finpay:pol:retention_compliance",
            target_id="vaultly:pol:forensic_audit_retention",
            rel_type="CONFLICTS_WITH",
            properties={
                "severity": "HIGH",
                "domain": "Data Retention",
                "reason": "Domain mismatch in Data Retention: 'FinPay Data Minimization & Log Retention' vs 'Vaultly Forensic Audit Retention Policy' (semantic overlap: 0.87)",
                "auto_detected": True,
            },
        ),
    ]
