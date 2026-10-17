"use client";

import React, { useState, useEffect } from "react";
import { Brain } from "lucide-react";
import ChatPanel from "@/components/ChatPanel";
import GraphCanvas from "@/components/GraphCanvas";
import NodeInspectorModal from "@/components/NodeInspectorModal";
import { SubgraphData, GraphNode, fetchFullSubgraph, checkBackendHealth } from "@/lib/api";
import { getFallbackGraph } from "@/lib/fallbackData";

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
  const [isFallbackMode, setIsFallbackMode] = useState<boolean>(false);

  // Draggable splitter & graph maximize state
  const [chatWidth, setChatWidth] = useState<number>(480);
  const [isResizing, setIsResizing] = useState<boolean>(false);
  const [isMaximized, setIsMaximized] = useState<boolean>(false);

  // Mouse drag handlers for resizing chat panel vs graph canvas
  useEffect(() => {
    if (!isResizing) return;

    const handleMouseMove = (e: MouseEvent) => {
      const minWidth = 280;
      const maxWidth = Math.max(minWidth, Math.floor(window.innerWidth * 0.75));
      const newWidth = Math.min(Math.max(e.clientX, minWidth), maxWidth);
      setChatWidth(newWidth);
    };

    const handleMouseUp = () => {
      setIsResizing(false);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };

    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";

    window.addEventListener("mousemove", handleMouseMove);
    window.addEventListener("mouseup", handleMouseUp);

    return () => {
      window.removeEventListener("mousemove", handleMouseMove);
      window.removeEventListener("mouseup", handleMouseUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
  }, [isResizing]);

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
          setIsFallbackMode(false);
        } else {
          setGraphData(getFallbackGraph(selectedGraph));
          setIsFallbackMode(true);
        }
      } catch (err) {
        console.info("Live backend connection pending, activating curated offline demo preview:", err);
        setGraphData(getFallbackGraph(selectedGraph));
        setIsFallbackMode(true);
      } finally {
        setIsLoading(false);
      }
    }
    loadGraphData();
  }, [selectedGraph]);

  // Periodic background health check & live graph recovery when backend is waking up from cold start
  useEffect(() => {
    if (isHealthy) return;

    const interval = setInterval(async () => {
      try {
        const health = await checkBackendHealth();
        if (health.falkordb_connected) {
          setIsHealthy(true);
          if (health.active_graphs && Array.isArray(health.active_graphs) && health.active_graphs.length > 0) {
            setAvailableGraphs(health.active_graphs);
          }
          // Seamlessly swap static fallback preview with live FalkorDB multigraph
          const data = await fetchFullSubgraph(selectedGraph);
          if (data && data.nodes && data.nodes.length > 0) {
            setGraphData(data);
            setIsFallbackMode(false);
          }
        }
      } catch {
        // Backend still spinning up on cold start...
      }
    }, 4000);

    return () => clearInterval(interval);
  }, [isHealthy, selectedGraph]);

  const handleSubgraphUpdate = (subgraph: SubgraphData | null) => {
    setActiveSubgraph(subgraph);
    // Auto-select first node if available to show inspector
    if (subgraph && subgraph.nodes.length > 0) {
      setSelectedNode(subgraph.nodes[0]);
    }
  };

  const handleFullGraphRefresh = async (freshData?: SubgraphData): Promise<void> => {
    if (freshData && freshData.nodes && freshData.nodes.length > 0 && selectedGraph === "merged_brain") {
      setGraphData(freshData);
      setIsHealthy(true);
    } else {
      try {
        const d = await fetchFullSubgraph(selectedGraph);
        if (d && d.nodes && d.nodes.length > 0) {
          setGraphData(d);
          setIsHealthy(true);
        } else {
          setGraphData(getFallbackGraph(selectedGraph));
        }
      } catch (err) {
        console.warn("Could not refresh full graph, activating tenant fallback:", err);
        setGraphData(getFallbackGraph(selectedGraph));
      }
    }
  };

  return (
    <main className="flex h-screen w-screen overflow-hidden bg-slate-950 font-sans">
      {/* Left Panel: Agent Chat & M&A Crisis Prompts */}
      <div
        style={{
          width: isMaximized ? 0 : `${chatWidth}px`,
          minWidth: isMaximized ? 0 : undefined,
        }}
        className={`h-full flex-shrink-0 transition-[width] ${
          isResizing ? "duration-0" : "duration-200"
        } ${isMaximized ? "overflow-hidden opacity-0 pointer-events-none" : "opacity-100"}`}
      >
        <ChatPanel
          selectedGraph={selectedGraph}
          onSubgraphUpdate={handleSubgraphUpdate}
          onFullGraphRefresh={handleFullGraphRefresh}
          onBackendHealthy={() => setIsHealthy(true)}
          isBackendHealthy={isHealthy}
        />
      </div>

      {/* Draggable Divider Handle between Chatbot and Graph */}
      {!isMaximized && (
        <div
          onMouseDown={(e) => {
            e.preventDefault();
            setIsResizing(true);
          }}
          className={`relative w-1.5 hover:w-2 transition-all cursor-col-resize z-30 flex items-center justify-center select-none group bg-slate-900 border-x border-slate-800 hover:bg-indigo-600 active:bg-indigo-500 ${
            isResizing ? "bg-indigo-600 w-2 shadow-[0_0_12px_#6366f1]" : ""
          }`}
          title="Drag left/right to resize Chat Panel and Graph Canvas"
        >
          {/* Subtle grab handle indicator */}
          <div className="w-0.5 h-8 rounded-full bg-slate-600 group-hover:bg-white transition-colors" />
        </div>
      )}

      {/* Right Panel: Interactive FalkorDB Force-Graph Canvas */}
      <div className="relative flex-1 h-full min-w-0 bg-slate-950">
        {/* Floating Tenant Graph Selector Pill & Live/Preview Status for Judges */}
        <div className="absolute top-4 left-4 z-20 flex items-center gap-2 p-1 bg-slate-900/90 backdrop-blur-md border border-slate-700/80 rounded-xl shadow-xl text-xs max-w-[calc(100%-2rem)] overflow-x-auto">
          <span className="px-2.5 py-1 text-slate-400 font-semibold uppercase tracking-wider text-[10px] whitespace-nowrap">
            Graph Tenant:
          </span>
          {availableGraphs.map((g) => {
            const isSelected = g === selectedGraph;
            const isMerged = g === "merged_brain";
            const label =
              g === "finpay_graph"
                ? "FinPay (Isolated)"
                : g === "vaultly_graph"
                ? "Vaultly (Isolated)"
                : "Merged Brain";
            return (
              <button
                key={g}
                onClick={() => {
                  setSelectedGraph(g);
                  setActiveSubgraph(null);
                  setSelectedNode(null);
                }}
                className={`inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-medium whitespace-nowrap transition-all ${
                  isSelected
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-500/20"
                    : "text-slate-300 hover:text-white hover:bg-slate-800/80"
                }`}
              >
                {isMerged && <Brain className="w-3.5 h-3.5 text-cyan-300" />}
                <span>{label}</span>
              </button>
            );
          })}

          <div className="h-4 w-[1px] bg-slate-700/80 mx-0.5 hidden sm:block" />

          {/* Explicit Connection / Preview Mode Status Badge (F1) */}
          {isFallbackMode ? (
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-amber-500/10 border border-amber-500/30 text-amber-400 font-medium text-[11px] whitespace-nowrap"
              title="Displaying curated offline demo preview with cross-company bridges while backend instance initializes"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-amber-400 animate-ping" />
              <span>Offline Demo Preview (Connecting to FalkorDB...)</span>
            </span>
          ) : (
            <span
              className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400 font-medium text-[11px] whitespace-nowrap"
              title="Connected to live FalkorDB GraphBLAS instance"
            >
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span>Live FalkorDB Multi-Tenant</span>
            </span>
          )}
        </div>

        <GraphCanvas
          data={graphData}
          activeSubgraph={activeSubgraph}
          onNodeClick={(node) => setSelectedNode(node)}
          isLoading={isLoading}
          isMaximized={isMaximized}
          onToggleMaximize={() => setIsMaximized((prev) => !prev)}
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
