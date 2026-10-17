"use client";

import React, { useRef, useEffect, useState, useMemo } from "react";
import dynamic from "next/dynamic";
import { GraphNode, SubgraphData } from "@/lib/api";
import { getEndpointId } from "@/lib/utils";
import { ZoomIn, ZoomOut, Maximize2, Minimize2, RotateCcw, Layers, RefreshCw } from "lucide-react";

// Dynamically import ForceGraph2D with ssr disabled and explicit ref forwarding via custom props
const ForceGraph2D = dynamic(
  () =>
    import("react-force-graph-2d").then((mod) => {
      const Component = mod.default;
      return function ForceGraphClient({
        forwardedRef,
        onGraphReady,
        ...props
      }: any) {
        return (
          <Component
            ref={(inst: any) => {
              if (forwardedRef) {
                if (typeof forwardedRef === "function") {
                  forwardedRef(inst);
                } else {
                  forwardedRef.current = inst;
                }
              }
              if (onGraphReady) {
                onGraphReady(inst);
              }
            }}
            {...props}
          />
        );
      };
    }),
  {
    ssr: false,
    loading: () => (
      <div className="h-full w-full flex items-center justify-center bg-slate-950 text-slate-400">
        <RefreshCw className="w-6 h-6 animate-spin mr-2" />
        Loading FalkorDB Live Canvas...
      </div>
    ),
  }
);

interface GraphCanvasProps {
  data: SubgraphData;
  activeSubgraph?: SubgraphData | null;
  onNodeClick?: (node: GraphNode) => void;
  isLoading?: boolean;
  isMaximized?: boolean;
  onToggleMaximize?: () => void;
}

export default function GraphCanvas({
  data,
  activeSubgraph,
  onNodeClick,
  isLoading,
  isMaximized = false,
  onToggleMaximize,
}: GraphCanvasProps) {
  const fgRef = useRef<any>(null);
  const [graphReady, setGraphReady] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const [showOnlyActive, setShowOnlyActive] = useState(false);

  // Helper to obtain the active ForceGraphMethods instance reliably
  const getGraph = () => {
    if (fgRef.current && typeof fgRef.current.zoom === "function") {
      return fgRef.current;
    }
    if (typeof window !== "undefined" && (window as any).__warRoomForceGraph) {
      return (window as any).__warRoomForceGraph;
    }
    return fgRef.current;
  };

  // Measure container dimensions with ResizeObserver for instant splitter dragging responsiveness
  useEffect(() => {
    function updateDimensions() {
      if (containerRef.current) {
        const { clientWidth, clientHeight } = containerRef.current;
        if (clientWidth > 0 && clientHeight > 0) {
          setDimensions({
            width: clientWidth,
            height: clientHeight,
          });
        }
      }
    }
    updateDimensions();

    let resizeObserver: ResizeObserver | null = null;
    if (typeof ResizeObserver !== "undefined" && containerRef.current) {
      resizeObserver = new ResizeObserver(() => {
        updateDimensions();
      });
      resizeObserver.observe(containerRef.current);
    }

    window.addEventListener("resize", updateDimensions);
    return () => {
      window.removeEventListener("resize", updateDimensions);
      resizeObserver?.disconnect();
    };
  }, []);

  // Compute active node and edge sets
  const activeNodeIds = useMemo(() => {
    if (!activeSubgraph?.nodes) return new Set<string>();
    return new Set(activeSubgraph.nodes.map((n) => n.id));
  }, [activeSubgraph]);

  const activeEdgeKeys = useMemo(() => {
    if (!activeSubgraph?.edges) return new Set<string>();
    const keys = new Set<string>();
    for (const e of activeSubgraph.edges) {
      const sId = getEndpointId(e.source);
      const tId = getEndpointId(e.target);
      keys.add(`${sId}->${tId}`);
      keys.add(`${tId}->${sId}`);
    }
    return keys;
  }, [activeSubgraph]);

  // Filter and sanitize graph data so disconnected links never cause D3 simulation crash
  const displayData = useMemo(() => {
    const sourceData =
      showOnlyActive && activeSubgraph && activeSubgraph.nodes && activeSubgraph.nodes.length > 0
        ? activeSubgraph
        : data;

    const rawNodes = sourceData?.nodes || [];
    const rawEdges = sourceData?.edges || [];

    const nodes = rawNodes.map((n) => ({ ...n }));
    const validNodeIds = new Set(nodes.map((n) => n.id));

    const links = rawEdges
      .filter((e) => {
        const sId = getEndpointId(e.source);
        const tId = getEndpointId(e.target);
        return validNodeIds.has(sId) && validNodeIds.has(tId);
      })
      .map((e) => ({ ...e }));

    return { nodes, links };
  }, [data, activeSubgraph, showOnlyActive]);

  // Center on active nodes or graph when data updates
  useEffect(() => {
    const fg = getGraph();
    if (fg) {
      setTimeout(() => {
        fg?.zoomToFit?.(400, 40);
      }, 500);
    }
  }, [displayData, graphReady]);

  // Re-center on canvas when maximized or minimized layout changes
  useEffect(() => {
    const fg = getGraph();
    if (fg) {
      setTimeout(() => {
        fg?.zoomToFit?.(400, 40);
      }, 300);
    }
  }, [isMaximized, graphReady]);

  const handleZoomIn = () => {
    const fg = getGraph();
    if (!fg) {
      console.warn("Force graph instance not yet ready");
      return;
    }
    try {
      const current = typeof fg.zoom === "function" ? fg.zoom() : 1;
      const validZoom = typeof current === "number" && !isNaN(current) && current > 0 ? current : 1;
      fg.zoom(validZoom * 1.35, 300);
    } catch (e) {
      console.warn("Zoom In error:", e);
    }
  };

  const handleZoomOut = () => {
    const fg = getGraph();
    if (!fg) {
      console.warn("Force graph instance not yet ready");
      return;
    }
    try {
      const current = typeof fg.zoom === "function" ? fg.zoom() : 1;
      const validZoom = typeof current === "number" && !isNaN(current) && current > 0 ? current : 1;
      fg.zoom(Math.max(validZoom * 0.7, 0.05), 300);
    } catch (e) {
      console.warn("Zoom Out error:", e);
    }
  };

  const handleFitView = () => {
    const fg = getGraph();
    if (!fg) {
      console.warn("Force graph instance not yet ready");
      return;
    }
    try {
      fg.zoomToFit?.(400, 40);
    } catch (e) {
      console.warn("Fit view error:", e);
      try {
        fg.centerAt?.(0, 0, 300);
        fg.zoom?.(1, 300);
      } catch {}
    }
  };

  // Color functions
  const getNodeColor = (node: GraphNode) => {
    const isHighlighted = activeNodeIds.size === 0 || activeNodeIds.has(node.id);
    if (!isHighlighted) {
      return "#33415555"; // dimmed
    }
    if (node.company_origin === "FinPay") return "#3b82f6"; // Blue
    if (node.company_origin === "Vaultly") return "#f97316"; // Orange
    if (node.company_origin === "Unified") return "#10b981"; // Emerald for post-M&A unified entities
    return "#a855f7"; // Purple for external / shared
  };

  const getEdgeColor = (link: any) => {
    const sId = getEndpointId(link.source);
    const tId = getEndpointId(link.target);
    const isHighlighted = activeEdgeKeys.size === 0 || activeEdgeKeys.has(`${sId}->${tId}`);

    if (link.rel_type === "CONFLICTS_WITH") return isHighlighted ? "#ef4444" : "#ef444433";
    if (link.rel_type === "REDUNDANT_WITH") return isHighlighted ? "#22c55e" : "#22c55e33";
    return isHighlighted ? "#64748b" : "#33415533";
  };

  return (
    <div ref={containerRef} className="relative h-full w-full bg-slate-950 overflow-hidden">
      {isLoading && (
        <div className="absolute inset-0 z-20 flex items-center justify-center bg-slate-950/70 backdrop-blur-sm text-slate-300">
          <RefreshCw className="w-5 h-5 animate-spin mr-2 text-cyan-400" />
          <span className="text-sm font-medium">Syncing FalkorDB Graph...</span>
        </div>
      )}

      {/* Empty State Prompt */}
      {!isLoading && displayData.nodes.length === 0 && (
        <div className="absolute inset-0 z-10 flex flex-col items-center justify-center p-6 text-center bg-slate-950/80 backdrop-blur-sm pointer-events-none">
          <div className="p-3 bg-slate-900 border border-slate-800 rounded-full mb-3 text-cyan-400">
            <Layers className="w-8 h-8" />
          </div>
          <h3 className="text-base font-semibold text-slate-200 mb-1">Connecting to FalkorDB...</h3>
          <p className="text-sm text-slate-400 max-w-sm">
            Please verify the backend connection is established and the knowledge graph is populated.
          </p>
        </div>
      )}

      {/* Top Overlay Legend & Status */}
      <div className="absolute top-16 left-4 z-10 flex flex-wrap gap-2 items-center text-xs bg-slate-900/80 backdrop-blur-md px-3 py-2 rounded-lg border border-slate-800 text-slate-300 shadow-xl">
        <div className="flex items-center gap-1.5">
          <span className="w-2.5 h-2.5 rounded-full bg-blue-500 shadow-[0_0_8px_#3b82f6]"></span>
          <span className="font-semibold text-blue-400">FinPay (Acquirer)</span>
        </div>
        <div className="flex items-center gap-1.5 ml-2">
          <span className="w-2.5 h-2.5 rounded-full bg-orange-500 shadow-[0_0_8px_#f97316]"></span>
          <span className="font-semibold text-orange-400">Vaultly (Target)</span>
        </div>
        <div className="flex items-center gap-1.5 ml-2">
          <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_8px_#10b981]"></span>
          <span className="font-semibold text-emerald-400">Unified (Post-M&A)</span>
        </div>
        <div className="flex items-center gap-1.5 ml-2">
          <span className="w-2.5 h-2.5 rounded-full bg-purple-500"></span>
          <span>Shared / External</span>
        </div>
        <div className="h-3 w-px bg-slate-700 mx-1" />
        <div className="flex items-center gap-1">
          <span className="w-2 h-0.5 bg-red-500"></span>
          <span className="text-red-400 font-medium">CONFLICTS_WITH</span>
        </div>
        <div className="flex items-center gap-1 ml-1">
          <span className="w-2 h-0.5 bg-green-500"></span>
          <span className="text-green-400 font-medium">REDUNDANT_WITH</span>
        </div>
      </div>

      {/* Floating Canvas Controls */}
      <div className="absolute top-4 right-4 z-20 flex flex-col gap-1.5 bg-slate-900/80 backdrop-blur-md p-1.5 rounded-lg border border-slate-800 shadow-xl">
        <button
          onClick={handleZoomIn}
          className="p-1.5 hover:bg-slate-800 text-slate-300 hover:text-white rounded transition"
          title="Zoom In"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={handleZoomOut}
          className="p-1.5 hover:bg-slate-800 text-slate-300 hover:text-white rounded transition"
          title="Zoom Out"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <button
          onClick={handleFitView}
          className="p-1.5 hover:bg-slate-800 text-slate-300 hover:text-white rounded transition"
          title="Fit View"
        >
          <RotateCcw className="w-4 h-4" />
        </button>
        {onToggleMaximize && (
          <button
            onClick={onToggleMaximize}
            className="p-1.5 hover:bg-slate-800 text-slate-300 hover:text-white rounded transition"
            title={isMaximized ? "Restore Split View" : "Maximize Graph Fullscreen"}
          >
            {isMaximized ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>
        )}
        {activeSubgraph && activeSubgraph.nodes.length > 0 && (
          <button
            onClick={() => setShowOnlyActive(!showOnlyActive)}
            className={`p-1.5 rounded transition ${
              showOnlyActive ? "bg-cyan-600 text-white" : "hover:bg-slate-800 text-slate-300 hover:text-white"
            }`}
            title="Toggle Tool Subgraph Isolation"
          >
            <Layers className="w-4 h-4" />
          </button>
        )}
      </div>

      {/* Live Graph Canvas */}
      <ForceGraph2D
        ref={fgRef}
        forwardedRef={fgRef}
        onGraphReady={(inst: any) => {
          fgRef.current = inst;
          if (typeof window !== "undefined") {
            (window as any).__warRoomForceGraph = inst;
          }
          setGraphReady(true);
        }}
        width={dimensions.width}
        height={dimensions.height}
        graphData={displayData}
        backgroundColor="#090d16"
        nodeLabel={(n: any) => `${n.name || n.id} (${n.label || 'Entity'})\nCompany: ${n.company_origin}`}
        nodeColor={getNodeColor as any}
        nodeRelSize={6}
        nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
          const isHighlighted = activeNodeIds.size === 0 || activeNodeIds.has(node.id);
          const color = getNodeColor(node);
          const radius = (node.label === "System" ? 7 : node.label === "Person" ? 6 : 5);

          // Outer Glow if active
          if (activeNodeIds.has(node.id)) {
            ctx.beginPath();
            ctx.arc(node.x, node.y, radius + 3, 0, 2 * Math.PI, false);
            ctx.fillStyle = color + "44";
            ctx.fill();
            ctx.strokeStyle = color;
            ctx.lineWidth = 1.5;
            ctx.stroke();
          }

          // Node Body
          ctx.beginPath();
          ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
          ctx.fillStyle = color;
          ctx.fill();

          // Label text
          if (globalScale > 0.8 || activeNodeIds.has(node.id)) {
            const label = node.name || node.id;
            const fontSize = Math.max(10 / globalScale, 3);
            ctx.font = `${fontSize}px Sans-Serif`;
            ctx.textAlign = "center";
            ctx.textBaseline = "top";
            ctx.fillStyle = isHighlighted ? "#f1f5f9" : "#64748b";
            ctx.fillText(label, node.x, node.y + radius + 2);
          }
        }}
        linkColor={getEdgeColor}
        linkWidth={(link: any) => {
          const sId = getEndpointId(link.source);
          const tId = getEndpointId(link.target);
          return activeEdgeKeys.has(`${sId}->${tId}`) ? 3 : 1.2;
        }}
        linkDirectionalArrowLength={4}
        linkDirectionalArrowRelPos={0.9}
        linkDirectionalParticles={(link: any) => {
          const sId = getEndpointId(link.source);
          const tId = getEndpointId(link.target);
          return activeEdgeKeys.has(`${sId}->${tId}`) ? 3 : 0;
        }}
        linkDirectionalParticleSpeed={0.008}
        linkDirectionalParticleWidth={2.5}
        onNodeClick={(node: any) => onNodeClick && onNodeClick(node)}
        cooldownTicks={100}
      />
    </div>
  );
}
