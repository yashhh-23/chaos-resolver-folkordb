/**
 * API client to communicate with OrgBridge FastAPI backend.
 */

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  (process.env.NODE_ENV === "development"
    ? "http://localhost:8000"
    : "https://orgbridge-ai-backend.onrender.com");

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
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) throw new Error(`Failed to load graph: ${res.statusText}`);
  return await res.json();
}

export async function callTool(endpoint: string, payload?: Record<string, any>): Promise<ToolResponse> {
  const res = await fetch(`${API_BASE}/api/tools/${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) throw new Error(`Tool call failed: ${res.statusText}`);
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

  const res = await fetch(`${API_BASE}${endpoint}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined,
  });
  if (!res.ok) throw new Error(`Mutation failed: ${res.statusText}`);
  return await res.json();
}

