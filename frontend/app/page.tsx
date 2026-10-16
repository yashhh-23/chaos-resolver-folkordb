"use client";

import React, { useState, useEffect } from "react";
import ChatPanel from "@/components/ChatPanel";
import GraphCanvas from "@/components/GraphCanvas";
import NodeInspectorModal from "@/components/NodeInspectorModal";
import { SubgraphData, GraphNode, fetchFullSubgraph, checkBackendHealth } from "@/lib/api";

export default function WarRoomDashboard() {
  const [graphData, setGraphData] = useState<SubgraphData>({ nodes: [], edges: [] });
  const [activeSubgraph, setActiveSubgraph] = useState<SubgraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [isHealthy, setIsHealthy] = useState(false);
  const [isLoading, setIsLoading] = useState(true);

  // Load initial graph and health check
  useEffect(() => {
    async function init() {
      setIsLoading(true);
      try {
        const health = await checkBackendHealth();
        setIsHealthy(!!health.falkordb_connected);

        const data = await fetchFullSubgraph("merged_brain");
        setGraphData(data);
      } catch (err) {
        console.warn("Could not fetch live graph, using fallback static preview", err);
      } finally {
        setIsLoading(false);
      }
    }
    init();
  }, []);

  const handleSubgraphUpdate = (subgraph: SubgraphData | null) => {
    setActiveSubgraph(subgraph);
    // Auto-select first node if available to show inspector
    if (subgraph && subgraph.nodes.length > 0) {
      setSelectedNode(subgraph.nodes[0]);
    }
  };

  return (
    <main className="flex h-screen w-screen overflow-hidden bg-slate-950 font-sans">
      {/* Left Panel: Agent Chat & M&A Crisis Prompts */}
      <ChatPanel
        onSubgraphUpdate={handleSubgraphUpdate}
        isBackendHealthy={isHealthy}
      />

      {/* Right Panel: Interactive FalkorDB Force-Graph Canvas */}
      <div className="relative flex-1 h-full bg-slate-950">
        <GraphCanvas
          data={graphData}
          activeSubgraph={activeSubgraph}
          onNodeClick={(node) => setSelectedNode(node)}
          isLoading={isLoading}
        />

        {/* Selected Node Properties Drawer */}
        <NodeInspectorModal
          node={selectedNode}
          onClose={() => setSelectedNode(null)}
        />
      </div>
    </main>
  );
}
