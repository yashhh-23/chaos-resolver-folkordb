/**
 * API client to communicate with OrgBridge FastAPI backend.
 */

import { API_BASE } from "./config";

export interface GraphNode {
  id: string;
  name: string;
  label: string;
  company_origin: string;
  properties?: Record<string, any>;
  x?: number;
  y?: number;
  vx?: number;
  vy?: number;
}

export interface GraphEdge {
  source: string | GraphNode;
  target: string | GraphNode;
  rel_type: string;
  properties?: Record<string, any>;
}

export interface SubgraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface ToolResponse {
  tool_name: string;
  status: string;
  text_answer: string;
  details: Record<string, any>;
  subgraph: SubgraphData;
}

async function fetchWithRetry(url: string, options: RequestInit, retries = 2, delayMs = 1000): Promise<Response> {
  let lastError: any;
  for (let i = 0; i <= retries; i++) {
    try {
      const res = await fetch(url, options);
      return res;
    } catch (err) {
      lastError = err;
      if (i < retries) {
        await new Promise((r) => setTimeout(r, delayMs * (i + 1)));
      }
    }
  }
  throw lastError || new Error("Network request failed after retries");
}

async function extractErrorMessage(res: Response, fallbackPrefix: string): Promise<string> {
  try {
    const errBody = await res.json().catch(() => ({}));
    if (typeof errBody.detail === "string") return errBody.detail;
    if (Array.isArray(errBody.detail)) {
      return errBody.detail.map((d: any) => d.msg || JSON.stringify(d)).join(", ");
    }
    if (errBody.message) return String(errBody.message);
  } catch {
    // ignore parse error
  }
  return res.statusText ? `${fallbackPrefix}: ${res.statusText}` : `${fallbackPrefix} (HTTP ${res.status})`;
}

export async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/api/health`, { cache: "no-store" });
    if (!res.ok) return { healthy: false };
    return await res.json();
  } catch (e) {
    return { healthy: false, error: String(e) };
  }
}

export async function fetchFullSubgraph(graphName?: string): Promise<SubgraphData> {
  const url = graphName ? `${API_BASE}/api/graph/subgraph?graph=${graphName}` : `${API_BASE}/api/graph/subgraph`;
  const res = await fetchWithRetry(url, { cache: "no-store" });
  if (!res.ok) {
    const errMsg = await extractErrorMessage(res, "Failed to load graph");
    throw new Error(errMsg);
  }
  return await res.json();
}

export async function callTool(endpoint: string, payload?: Record<string, any>): Promise<ToolResponse> {
  const res = await fetchWithRetry(`${API_BASE}/api/tools/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    const errMsg = await extractErrorMessage(res, "Tool call failed");
    throw new Error(errMsg);
  }
  return await res.json();
}

export async function mutateGraph(
  action: "resolve-auth" | "resolve-retention" | "merge-teams" | "reset-demo",
  payload?: Record<string, any>
): Promise<any> {
  let endpoint = "";
  if (action === "resolve-auth") endpoint = "/api/mutate/resolve-auth-conflict";
  else if (action === "resolve-retention") endpoint = "/api/mutate/resolve-retention-conflict";
  else if (action === "merge-teams") endpoint = "/api/mutate/merge-teams";
  else if (action === "reset-demo") endpoint = "/api/mutate/reset-demo";

  const res = await fetchWithRetry(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) {
    const errMsg = await extractErrorMessage(res, "Mutation failed");
    throw new Error(errMsg);
  }
  return await res.json();
}

export async function chatWithAgent(prompt: string, graph?: string): Promise<ToolResponse> {
  const res = await fetchWithRetry(`${API_BASE}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ prompt, graph }),
  });
  if (!res.ok) {
    const errMsg = await extractErrorMessage(res, "Agent chat failed");
    throw new Error(errMsg);
  }
  return await res.json();
}


