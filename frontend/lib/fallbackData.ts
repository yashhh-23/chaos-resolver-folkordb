import { SubgraphData } from "./api";

/**
 * Empty fallback state used when the backend is initializing or unreachable.
 * Prevents hardcoding duplicate synthetic data in the frontend that drifts from backend FalkorDB datasets.
 */
export const EMPTY_FALLBACK_GRAPH: SubgraphData = {
  nodes: [],
  edges: [],
};

export function getFallbackGraph(_selectedGraph: string = "merged_brain"): SubgraphData {
  return EMPTY_FALLBACK_GRAPH;
}
