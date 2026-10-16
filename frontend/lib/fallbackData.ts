import { SubgraphData } from "./api";

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
      properties: { tech: "Node.js / Express", domain: "Authentication", tier: "Tier-1" },
    },
    {
      id: "vaultly:sys:pulse_identity",
      name: "Pulse-Identity",
      label: "System",
      company_origin: "Vaultly",
      properties: { tech: "Go / Gin", domain: "Authentication", tier: "Tier-1" },
    },
    {
      id: "finpay:person:aarav_mehta",
      name: "Aarav Mehta",
      label: "Person",
      company_origin: "FinPay",
      properties: { role: "Principal Security Architect", email: "aarav.mehta@finpay.com", pagerank: 0.88 },
    },
    {
      id: "vaultly:person:diya_nair",
      name: "Diya Nair",
      label: "Person",
      company_origin: "Vaultly",
      properties: { role: "Senior Backend Developer", email: "diya.nair@vaultly.io", pagerank: 0.92 },
    },
    {
      id: "ext:uidai_aadhaar",
      name: "UIDAI Aadhaar API",
      label: "ExternalAPI",
      company_origin: "External",
      properties: { provider: "UIDAI", category: "Identity" },
    },
    {
      id: "ext:stripe",
      name: "Stripe Connect API",
      label: "ExternalAPI",
      company_origin: "External",
      properties: { provider: "Stripe", category: "Payments" },
    },
    {
      id: "finpay:pol:session_security",
      name: "Session Security Standard",
      label: "Policy",
      company_origin: "FinPay",
      properties: { domain: "Authentication", status: "ACTIVE" },
    },
    {
      id: "vaultly:pol:session_continuity",
      name: "Mobile Session Continuity Policy",
      label: "Policy",
      company_origin: "Vaultly",
      properties: { domain: "Authentication", status: "ACTIVE" },
    },
    {
      id: "finpay:sys:finpay_core_ledger",
      name: "FinPay-Core-Ledger",
      label: "System",
      company_origin: "FinPay",
      properties: { tech: "Java / Spring Boot", domain: "Ledger", tier: "Tier-1" },
    },
    {
      id: "vaultly:sys:vault_engine",
      name: "Vault-Engine",
      label: "System",
      company_origin: "Vaultly",
      properties: { tech: "Rust / Actix", domain: "Ledger", tier: "Tier-1" },
    },
  ],
  edges: [
    {
      source: "finpay:sys:gatekeeper_auth",
      target: "vaultly:sys:pulse_identity",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity: 0.89 },
    },
    {
      source: "finpay:pol:session_security",
      target: "vaultly:pol:session_continuity",
      rel_type: "CONFLICTS_WITH",
      properties: { severity: "CRITICAL", domain: "Authentication" },
    },
    {
      source: "finpay:sys:gatekeeper_auth",
      target: "ext:uidai_aadhaar",
      rel_type: "CALLS",
    },
    {
      source: "vaultly:sys:pulse_identity",
      target: "ext:uidai_aadhaar",
      rel_type: "CALLS",
    },
    {
      source: "finpay:person:aarav_mehta",
      target: "finpay:sys:gatekeeper_auth",
      rel_type: "OWNS",
    },
    {
      source: "vaultly:person:diya_nair",
      target: "vaultly:sys:pulse_identity",
      rel_type: "OWNS",
    },
    {
      source: "finpay:sys:finpay_core_ledger",
      target: "vaultly:sys:vault_engine",
      rel_type: "REDUNDANT_WITH",
      properties: { similarity: 0.99 },
    },
  ],
};
