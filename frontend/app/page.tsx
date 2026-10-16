"use client";

import React, { useState, useEffect } from "react";
import ChatPanel from "@/components/ChatPanel";
import GraphCanvas from "@/components/GraphCanvas";
import NodeInspectorModal from "@/components/NodeInspectorModal";
import { SubgraphData, GraphNode, fetchFullSubgraph, checkBackendHealth } from "@/lib/api";
import { FALLBACK_STATIC_GRAPH } from "@/lib/fallbackData";

export default function WarRoomDashboard() {
  const [graphData, setGraphData] = useState<SubgraphData>({ nodes: [], edges: [] });
  const [activeSubgraph, setActiveSubgraph] = useState<SubgraphData | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [isHealthy, setIsHealthy] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [availableGraphs, setAvailableGraphs] = useState<string[]>([
    "finpay_graph",
    "vaultly_graph",
    "merged_brain",
  ]);
  const [selectedGraph, setSelectedGraph] = useState<string>("merged_brain");

  // Load graph and health check on mount or when graph tenant selection changes
  useEffect(() => {
    async function loadGraphData() {
      setIsLoading(true);
      try {
        const health = await checkBackendHealth();
        setIsHealthy(!!health.falkordb_connected);
        if (health.active_graphs && Array.isArray(health.active_graphs) && health.active_graphs.length > 0) {
          setAvailableGraphs(health.active_graphs);
        }

        const data = await fetchFullSubgraph(selectedGraph);
        if (data && data.nodes && data.nodes.length > 0) {
          setGraphData(data);
        } else {
          setGraphData(FALLBACK_STATIC_GRAPH);
        }
      } catch (err) {
        console.info("Live backend connection pending, activating curated static preview:", err);
        setGraphData(FALLBACK_STATIC_GRAPH);
      } finally {
        setIsLoading(false);
      }
    }
    loadGraphData();
  }, [selectedGraph]);

  const handleSubgraphUpdate = (subgraph: SubgraphData | null) => {
    setActiveSubgraph(subgraph);
    // Auto-select first node if available to show inspector
    if (subgraph && subgraph.nodes.length > 0) {
      setSelectedNode(subgraph.nodes[0]);
    }
  };

  const handleFullGraphRefresh = (freshData?: SubgraphData) => {
    if (freshData && freshData.nodes && freshData.nodes.length > 0) {
      setGraphData(freshData);
    } else {
      fetchFullSubgraph(selectedGraph)
        .then((d) => {
          if (d && d.nodes) setGraphData(d);
        })
        .catch((err) => console.warn("Could not refresh full graph:", err));
    }
  };

  return (
    <main className="flex h-screen w-screen overflow-hidden bg-slate-950 font-sans">
      {/* Left Panel: Agent Chat & M&A Crisis Prompts */}
      <ChatPanel
        onSubgraphUpdate={handleSubgraphUpdate}
        onFullGraphRefresh={handleFullGraphRefresh}
        isBackendHealthy={isHealthy}
        graphData={graphData}
      />

      {/* Right Panel: Interactive FalkorDB Force-Graph Canvas */}
      <div className="relative flex-1 h-full bg-slate-950">
        {/* Floating Tenant Graph Selector Pill for Judges */}
        <div className="absolute top-4 left-4 z-20 flex items-center gap-1.5 p-1 bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-xl shadow-xl text-xs">
          <span className="px-2.5 py-1 text-slate-400 font-semibold uppercase tracking-wider text-[10px]">
            Graph Tenant:
          </span>
          {availableGraphs.map((g) => {
            const isSelected = g === selectedGraph;
            const label =
              g === "finpay_graph"
                ? "FinPay (Isolated)"
                : g === "vaultly_graph"
                ? "Vaultly (Isolated)"
                : "Merged Brain 🧠";
            return (
              <button
                key={g}
                onClick={() => {
                  setSelectedGraph(g);
                  setActiveSubgraph(null);
                  setSelectedNode(null);
                }}
                className={`px-3 py-1.5 rounded-lg font-medium transition-all ${
                  isSelected
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                    : "text-slate-300 hover:text-white hover:bg-slate-800/80"
                }`}
              >
                {label}
              </button>
            );
          })}
        </div>

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
