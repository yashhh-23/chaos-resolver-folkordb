import { GraphNode } from "./api";

/**
 * Normalizes a D3 force-graph endpoint (which can be a string ID, an object with an `id`, or null/undefined)
 * into a string ID.
 */
export function getEndpointId(endpoint: string | GraphNode | any): string {
  if (typeof endpoint === "object" && endpoint !== null) {
    return (endpoint as { id?: string }).id || String(endpoint);
  }
  return String(endpoint || "");
}
