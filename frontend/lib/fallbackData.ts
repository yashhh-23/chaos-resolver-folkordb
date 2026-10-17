import { SubgraphData } from "./api";

/**
 * Curated offline demo fallback graphs representing the M&A War Room state.
 * Displayed when the backend is waking up from a cold start, ensuring judges
 * immediately see a rich, interactive preview with cross-company bridges and conflicts.
 */

const FALLBACK_MERGED_BRAIN: SubgraphData = {
  nodes: [
    // FinPay Systems
    {
      id: "finpay:sys:gatekeeper_auth",
      name: "Gatekeeper-Auth",
      label: "System",
      company_origin: "FinPay",
      properties: { domain: "Authentication", tier: "Tier-1", status: "Production", rps: 45000 },
    },
    {
      id: "finpay:sys:finpay_core_ledger",
      name: "FinPay-Core-Ledger",
      label: "System",
      company_origin: "FinPay",
      properties: { domain: "Core Banking", tier: "Tier-1", status: "Production", rps: 82000 },
    },
    {
      id: "finpay:sys:customer_kyc",
      name: "Customer-KYC-Service",
      label: "System",
      company_origin: "FinPay",
      properties: { domain: "Compliance", tier: "Tier-2", status: "Production" },
    },
    {
      id: "finpay:sys:finpay_mesh_gateway",
      name: "FinPay-Mesh-Gateway",
      label: "System",
      company_origin: "FinPay",
      properties: { domain: "Gateway", tier: "Tier-1", status: "Production" },
    },

    // Vaultly Systems
    {
      id: "vaultly:sys:pulse_identity",
      name: "Pulse-Identity",
      label: "System",
      company_origin: "Vaultly",
      properties: { domain: "Authentication", tier: "Tier-1", status: "Production", rps: 38000 },
    },
    {
      id: "vaultly:sys:vault_engine",
      name: "Vault-Engine",
      label: "System",
      company_origin: "Vaultly",
      properties: { domain: "Core Banking", tier: "Tier-1", status: "Production", rps: 76000 },
    },
    {
      id: "vaultly:sys:user_onboarding",
      name: "User-Onboarding-Verification",
      label: "System",
      company_origin: "Vaultly",
      properties: { domain: "Compliance", tier: "Tier-2", status: "Production" },
    },
    {
      id: "vaultly:sys:vaultly_public_api",
      name: "Vaultly-Public-API",
      label: "System",
      company_origin: "Vaultly",
      properties: { domain: "Gateway", tier: "Tier-1", status: "Production" },
    },

    // FinPay Teams & Personnel
    {
      id: "finpay:team:secarch",
      name: "FinPay Security Architecture",
      label: "Team",
      company_origin: "FinPay",
      properties: { charter: "Enterprise security architecture and IAM governance" },
    },
    {
      id: "finpay:person:aarav_mehta",
      name: "Aarav Mehta",
      label: "Person",
      company_origin: "FinPay",
      properties: { role: "Staff Security Engineer", pagerank: 0.88, department: "Security Architecture" },
    },
    {
      id: "finpay:team:payments_core",
      name: "FinPay Core Payments",
      label: "Team",
      company_origin: "FinPay",
      properties: { charter: "High-throughput ledger settlement and payment processing" },
    },
    {
      id: "finpay:person:priya_sharma",
      name: "Priya Sharma",
      label: "Person",
      company_origin: "FinPay",
      properties: { role: "Principal Payments Engineer", pagerank: 0.94, department: "Core Payments" },
    },

    // Vaultly Teams & Personnel
    {
      id: "vaultly:team:identity_growth",
      name: "Vaultly Growth & Identity",
      label: "Team",
      company_origin: "Vaultly",
      properties: { charter: "Mobile identity, consumer auth, and growth experimentation" },
    },
    {
      id: "vaultly:person:diya_nair",
      name: "Diya Nair",
      label: "Person",
      company_origin: "Vaultly",
      properties: { role: "Lead Identity Architect", pagerank: 0.85, department: "Identity" },
    },
    {
      id: "vaultly:team:ledger_eng",
      name: "Vaultly High-Frequency Ledger",
      label: "Team",
      company_origin: "Vaultly",
      properties: { charter: "Real-time ledger accounting engine and audit journal" },
    },
    {
      id: "vaultly:person:kabir_patel",
      name: "Kabir Patel",
      label: "Person",
      company_origin: "Vaultly",
      properties: { role: "Principal Systems Architect", pagerank: 0.91, department: "Core Engineering" },
    },
    {
      id: "vaultly:team:app_experience",
      name: "Vaultly Mobile Experience",
      label: "Team",
      company_origin: "Vaultly",
      properties: { charter: "Native iOS and Android consumer banking application experience" },
    },
    {
      id: "vaultly:person:arjun_das",
      name: "Arjun Das",
      label: "Person",
      company_origin: "Vaultly",
      properties: { role: "Lead Mobile Architect", pagerank: 0.76, department: "Mobile App" },
    },

    // Policies
    {
      id: "finpay:pol:session_security",
      name: "FinPay Session Security Policy",
      label: "Policy",
      company_origin: "FinPay",
      properties: { domain: "Authentication", status: "ACTIVE", max_token_ttl_min: 15 },
    },
    {
      id: "vaultly:pol:session_continuity",
      name: "Vaultly Frictionless Session Policy",
      label: "Policy",
      company_origin: "Vaultly",
      properties: { domain: "Authentication", status: "ACTIVE", max_token_ttl_min: 10080 },
    },
    {
      id: "finpay:pol:retention_compliance",
      name: "FinPay Data Minimization & Log Retention",
      label: "Policy",
      company_origin: "FinPay",
      properties: { domain: "Data Retention", status: "ACTIVE", retention_days: 30 },
    },
    {
      id: "vaultly:pol:forensic_audit_retention",
      name: "Vaultly Forensic Audit Retention Policy",
      label: "Policy",
      company_origin: "Vaultly",
      properties: { domain: "Data Retention", status: "ACTIVE", retention_days: 180 },
    },

    // Decisions
    {
      id: "finpay:dec:jwt_15m",
      name: "15-min JWT Lifetime",
      label: "Decision",
      company_origin: "FinPay",
      properties: { summary: "Enforce strict 15-minute token expiry for PCI-DSS compliance" },
    },
    {
      id: "vaultly:dec:session_7d",
      name: "7-Day Rolling Sessions",
      label: "Decision",
      company_origin: "Vaultly",
      properties: { summary: "7-day rolling biometric refresh to minimize user re-login churn" },
    },
    {
      id: "finpay:dec:log_purge_30d",
      name: "30-day Debug Log Purge",
      label: "Decision",
      company_origin: "FinPay",
      properties: { summary: "Hard purge of all debug logs after 30 days for data minimization" },
    },
    {
      id: "vaultly:dec:log_retention_180d",
      name: "180-day Forensic Log Retention",
      label: "Decision",
      company_origin: "Vaultly",
      properties: { summary: "Retain raw audit traces for 180 days for financial compliance" },
    },
  ],
  edges: [
    // Cross-Company Bridge: Redundant Systems
    {
      source: "finpay:sys:gatekeeper_auth",
      target: "vaultly:sys:pulse_identity",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity_score: 0.99, domain: "Authentication" },
    },
    {
      source: "finpay:sys:finpay_core_ledger",
      target: "vaultly:sys:vault_engine",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity_score: 0.99, domain: "Core Banking" },
    },
    {
      source: "finpay:sys:customer_kyc",
      target: "vaultly:sys:user_onboarding",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity_score: 0.99, domain: "Compliance" },
    },

    // Cross-Company Bridge: Architectural Policy Conflicts
    {
      source: "finpay:pol:session_security",
      target: "vaultly:pol:session_continuity",
      rel_type: "CONFLICTS_WITH",
      properties: { severity: "CRITICAL", domain: "Authentication" },
    },
    {
      source: "finpay:pol:retention_compliance",
      target: "vaultly:pol:forensic_audit_retention",
      rel_type: "CONFLICTS_WITH",
      properties: { severity: "HIGH", domain: "Data Retention" },
    },
    {
      source: "finpay:dec:jwt_15m",
      target: "vaultly:dec:session_7d",
      rel_type: "CONFLICTS_WITH",
      properties: { severity: "CRITICAL", type: "TTL_CONTRADICTION" },
    },
    {
      source: "finpay:dec:log_purge_30d",
      target: "vaultly:dec:log_retention_180d",
      rel_type: "CONFLICTS_WITH",
      properties: { severity: "HIGH", type: "RETENTION_CONTRADICTION" },
    },

    // Governance & Ownership
    { source: "finpay:sys:gatekeeper_auth", target: "finpay:pol:session_security", rel_type: "GOVERNED_BY" },
    { source: "vaultly:sys:pulse_identity", target: "vaultly:pol:session_continuity", rel_type: "GOVERNED_BY" },
    { source: "finpay:team:secarch", target: "finpay:sys:gatekeeper_auth", rel_type: "OWNS" },
    { source: "vaultly:team:identity_growth", target: "vaultly:sys:pulse_identity", rel_type: "OWNS" },
    { source: "finpay:team:payments_core", target: "finpay:sys:finpay_core_ledger", rel_type: "OWNS" },
    { source: "vaultly:team:ledger_eng", target: "vaultly:sys:vault_engine", rel_type: "OWNS" },

    // Team Memberships
    { source: "finpay:person:aarav_mehta", target: "finpay:team:secarch", rel_type: "MEMBER_OF" },
    { source: "finpay:person:priya_sharma", target: "finpay:team:payments_core", rel_type: "MEMBER_OF" },
    { source: "vaultly:person:diya_nair", target: "vaultly:team:identity_growth", rel_type: "MEMBER_OF" },
    { source: "vaultly:person:kabir_patel", target: "vaultly:team:ledger_eng", rel_type: "MEMBER_OF" },
    { source: "vaultly:person:arjun_das", target: "vaultly:team:app_experience", rel_type: "MEMBER_OF" },
  ],
};

export function getFallbackGraph(selectedGraph: string = "merged_brain"): SubgraphData {
  if (selectedGraph === "finpay_graph") {
    const finpayNodes = FALLBACK_MERGED_BRAIN.nodes.filter((n) => n.company_origin === "FinPay");
    const nodeIds = new Set(finpayNodes.map((n) => n.id));
    const finpayEdges = FALLBACK_MERGED_BRAIN.edges.filter(
      (e) => nodeIds.has(typeof e.source === "string" ? e.source : e.source.id) &&
             nodeIds.has(typeof e.target === "string" ? e.target : e.target.id)
    );
    return { nodes: finpayNodes, edges: finpayEdges };
  }

  if (selectedGraph === "vaultly_graph") {
    const vaultlyNodes = FALLBACK_MERGED_BRAIN.nodes.filter((n) => n.company_origin === "Vaultly");
    const nodeIds = new Set(vaultlyNodes.map((n) => n.id));
    const vaultlyEdges = FALLBACK_MERGED_BRAIN.edges.filter(
      (e) => nodeIds.has(typeof e.source === "string" ? e.source : e.source.id) &&
             nodeIds.has(typeof e.target === "string" ? e.target : e.target.id)
    );
    return { nodes: vaultlyNodes, edges: vaultlyEdges };
  }

  return FALLBACK_MERGED_BRAIN;
}
