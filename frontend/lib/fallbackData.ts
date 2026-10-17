import { SubgraphData } from "./api";
import { getEndpointId } from "./utils";

/**
 * Curated offline fallback graph representing the core FinPay & Vaultly M&A dilemma.
 * Activated when live backend is unreachable so War Room never shows an empty canvas.
 */
export const FALLBACK_STATIC_GRAPH: SubgraphData = {
  nodes: [
    {
      id: "finpay:sys:gatekeeper_auth",
      name: "Gatekeeper-Auth",
      label: "System",
      company_origin: "FinPay",
      properties: { tech: "Go/Redis", domain: "Authentication", tier: "tier-1" },
    },
    {
      id: "vaultly:sys:pulse_identity",
      name: "Pulse-Identity",
      label: "System",
      company_origin: "Vaultly",
      properties: { tech: "Node/PostgreSQL", domain: "Authentication", tier: "tier-1" },
    },
    {
      id: "finpay:person:aarav_mehta",
      name: "Aarav Mehta",
      label: "Person",
      company_origin: "FinPay",
      properties: { role: "Staff Security Engineer", email: "aarav.mehta@finpay.com", pagerank: 0.89 },
    },
    {
      id: "vaultly:person:diya_nair",
      name: "Diya Nair",
      label: "Person",
      company_origin: "Vaultly",
      properties: { role: "Senior Backend Developer", email: "diya.nair@vaultly.io", pagerank: 0.92 },
    },
    {
      id: "ext:api:aws_kms",
      name: "AWS_KMS",
      label: "ExternalAPI",
      company_origin: "External",
      properties: { provider: "Amazon Web Services", category: "Key Management" },
    },
    {
      id: "ext:api:uidai_aadhaar",
      name: "UIDAI_Aadhaar",
      label: "ExternalAPI",
      company_origin: "External",
      properties: { provider: "Unique Identification Authority of India", category: "Identity & Verification" },
    },
    {
      id: "ext:api:stripe",
      name: "Stripe_Gateway",
      label: "ExternalAPI",
      company_origin: "External",
      properties: { provider: "Stripe, Inc.", category: "Payment Processing" },
    },
    {
      id: "finpay:pol:session_security",
      name: "FinPay Session Security Policy",
      label: "Policy",
      company_origin: "FinPay",
      properties: { domain: "Authentication", status: "ACTIVE" },
    },
    {
      id: "vaultly:pol:session_continuity",
      name: "Vaultly Frictionless Session Policy",
      label: "Policy",
      company_origin: "Vaultly",
      properties: { domain: "Authentication", status: "ACTIVE" },
    },
    {
      id: "finpay:sys:finpay_core_ledger",
      name: "FinPay-Core-Ledger",
      label: "System",
      company_origin: "FinPay",
      properties: { tech: "Java/PostgreSQL", domain: "Ledger", tier: "tier-1" },
    },
    {
      id: "vaultly:sys:vault_engine",
      name: "Vault-Engine",
      label: "System",
      company_origin: "Vaultly",
      properties: { tech: "Rust/RocksDB", domain: "Ledger", tier: "tier-1" },
    },
    {
      id: "finpay:sys:customer_kyc",
      name: "Customer-KYC-Service",
      label: "System",
      company_origin: "FinPay",
      properties: { tech: "Python/FastAPI", domain: "KYC", tier: "tier-2" },
    },
    {
      id: "vaultly:sys:user_onboarding",
      name: "User-Onboarding-Verification",
      label: "System",
      company_origin: "Vaultly",
      properties: { tech: "TypeScript/NestJS", domain: "KYC", tier: "tier-2" },
    },
  ],
  edges: [
    {
      source: "finpay:sys:gatekeeper_auth",
      target: "vaultly:sys:pulse_identity",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity: 0.99 },
    },
    {
      source: "finpay:pol:session_security",
      target: "vaultly:pol:session_continuity",
      rel_type: "CONFLICTS_WITH",
      properties: { severity: "CRITICAL", domain: "Authentication" },
    },
    {
      source: "finpay:sys:gatekeeper_auth",
      target: "ext:api:aws_kms",
      rel_type: "CALLS",
    },
    {
      source: "vaultly:sys:pulse_identity",
      target: "ext:api:aws_kms",
      rel_type: "CALLS",
    },
    {
      source: "finpay:sys:customer_kyc",
      target: "ext:api:uidai_aadhaar",
      rel_type: "CALLS",
    },
    {
      source: "vaultly:sys:user_onboarding",
      target: "ext:api:uidai_aadhaar",
      rel_type: "CALLS",
    },
    {
      source: "finpay:person:aarav_mehta",
      target: "finpay:sys:gatekeeper_auth",
      rel_type: "OWNS",
    },
    {
      source: "finpay:person:aarav_mehta",
      target: "finpay:sys:customer_kyc",
      rel_type: "OWNS",
    },
    {
      source: "vaultly:person:diya_nair",
      target: "vaultly:sys:pulse_identity",
      rel_type: "OWNS",
    },
    {
      source: "vaultly:person:diya_nair",
      target: "vaultly:sys:user_onboarding",
      rel_type: "OWNS",
    },
    {
      source: "finpay:sys:finpay_core_ledger",
      target: "vaultly:sys:vault_engine",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity: 0.99 },
    },
    {
      source: "finpay:sys:customer_kyc",
      target: "vaultly:sys:user_onboarding",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity: 0.99 },
    },
    {
      source: "finpay:sys:finpay_core_ledger",
      target: "ext:api:stripe",
      rel_type: "CALLS",
    },
    {
      source: "vaultly:sys:vault_engine",
      target: "ext:api:stripe",
      rel_type: "CALLS",
    },
  ],
};

/**
 * Returns isolated tenant subgraphs or unified merged graph for offline mode.
 */
export function getFallbackGraph(selectedGraph: string = "merged_brain"): SubgraphData {
  if (selectedGraph === "finpay_graph") {
    const finpayNodes = FALLBACK_STATIC_GRAPH.nodes.filter((n) => n.company_origin === "FinPay");
    const finpayNodeIds = new Set(finpayNodes.map((n) => n.id));

    const validEdges = FALLBACK_STATIC_GRAPH.edges.filter((e) => {
      const src = getEndpointId(e.source);
      const tgt = getEndpointId(e.target);
      return (
        (finpayNodeIds.has(src) || finpayNodeIds.has(tgt)) &&
        !src.startsWith("vaultly:") &&
        !tgt.startsWith("vaultly:")
      );
    });

    const connectedNodeIds = new Set<string>();
    validEdges.forEach((e) => {
      connectedNodeIds.add(getEndpointId(e.source));
      connectedNodeIds.add(getEndpointId(e.target));
    });

    const nodes = FALLBACK_STATIC_GRAPH.nodes.filter(
      (n) => n.company_origin === "FinPay" || (n.company_origin === "External" && connectedNodeIds.has(n.id))
    );

    return { nodes, edges: validEdges };
  }

  if (selectedGraph === "vaultly_graph") {
    const vaultlyNodes = FALLBACK_STATIC_GRAPH.nodes.filter((n) => n.company_origin === "Vaultly");
    const vaultlyNodeIds = new Set(vaultlyNodes.map((n) => n.id));

    const validEdges = FALLBACK_STATIC_GRAPH.edges.filter((e) => {
      const src = getEndpointId(e.source);
      const tgt = getEndpointId(e.target);
      return (
        (vaultlyNodeIds.has(src) || vaultlyNodeIds.has(tgt)) &&
        !src.startsWith("finpay:") &&
        !tgt.startsWith("finpay:")
      );
    });

    const connectedNodeIds = new Set<string>();
    validEdges.forEach((e) => {
      connectedNodeIds.add(getEndpointId(e.source));
      connectedNodeIds.add(getEndpointId(e.target));
    });

    const nodes = FALLBACK_STATIC_GRAPH.nodes.filter(
      (n) => n.company_origin === "Vaultly" || (n.company_origin === "External" && connectedNodeIds.has(n.id))
    );

    return { nodes, edges: validEdges };
  }

  return FALLBACK_STATIC_GRAPH;
}
