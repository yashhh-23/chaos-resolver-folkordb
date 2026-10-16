"use client";

import React, { useState } from "react";
import {
  Send,
  Sparkles,
  Bot,
  User,
  ShieldAlert,
  GitMerge,
  Users,
  Compass,
  FileText,
  Activity,
  Layers,
  Zap,
  RotateCcw,
  CheckCircle2,
} from "lucide-react";
import { SubgraphData, ToolResponse, callTool, mutateGraph, fetchFullSubgraph } from "@/lib/api";


export interface Message {
  id: string;
  sender: "user" | "agent";
  text: string;
  toolName?: string;
  subgraph?: SubgraphData;
  timestamp: string;
}

interface ChatPanelProps {
  onSubgraphUpdate: (subgraph: SubgraphData | null) => void;
  isBackendHealthy: boolean;
}

const CRISIS_PROMPTS = [
  {
    label: "Auth SME Discovery",
    icon: Users,
    prompt: "Who is the true subject-matter expert on Authentication at Vaultly based on authored RFCs & PageRank?",
    endpoint: "find-counterpart-expert",
    payload: { topic: "Authentication", company: "Vaultly" },
  },
  {
    label: "Policy Collisions",
    icon: ShieldAlert,
    prompt: "Detect critical compliance and data retention policy conflicts between FinPay and Vaultly.",
    endpoint: "detect-policy-conflicts",
    payload: { domain: "Data Retention" },
  },
  {
    label: "Redundant Systems",
    icon: GitMerge,
    prompt: "Find all redundant microservice clusters across companies and identify shared external APIs.",
    endpoint: "find-redundant-systems",
    payload: {},
  },
  {
    label: "Decision Lineage",
    icon: FileText,
    prompt: "Trace the architectural decisions and RFC origin for Gatekeeper-Auth, and highlight target conflicts.",
    endpoint: "trace-decision-lineage",
    payload: { system_name: "Gatekeeper-Auth" },
  },
  {
    label: "Warm Intro Path",
    icon: Compass,
    prompt: "Find the shortest warm introduction path connecting Aarav Mehta (FinPay) to Diya Nair (Vaultly).",
    endpoint: "warm-intro-path",
    payload: { person_a: "Aarav Mehta", person_b: "Diya Nair" },
  },
];

export default function ChatPanel({
  onSubgraphUpdate,
  isBackendHealthy,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "agent",
      text: "### 🧠 Welcome to OrgBridge AI (The M&A Chaos Resolver)\n\nI am connected to your live **FalkorDB Multi-Tenant Brain** (`finpay_graph`, `vaultly_graph`, and `merged_brain`).\n\nClick any of the **M&A Crisis Prompts** below or ask any question to resolve organizational silos, uncover hidden dependencies, and detect conflicting architectural decisions.",
      timestamp: "Just now",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const handleRunCrisisPrompt = async (crisis: typeof CRISIS_PROMPTS[0]) => {
    if (isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: crisis.prompt,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res: ToolResponse = await callTool(crisis.endpoint, crisis.payload);
      const agentMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        text: res.text_answer,
        toolName: res.tool_name,
        subgraph: res.subgraph,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, agentMsg]);
      if (res.subgraph) {
        onSubgraphUpdate(res.subgraph);
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          text: `⚠️ **Error querying graph**: ${err.message || err}`,
          timestamp: "Error",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLiveMutation = async (action: "resolve-auth" | "resolve-retention" | "merge-teams" | "reset-demo", actionLabel: string) => {
    if (isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: `[Execute Live Mutation]: ${actionLabel}`,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res = await mutateGraph(action);
      const agentMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        text: `### ⚡ Live Graph Mutation Executed (Track 03)\n\n` +
              `**Action**: \`${res.action || action}\`\n\n` +
              `**Result**: ${res.resolution_summary || res.message}\n\n` +
              `> *FalkorDB multigraph state updated live via Cypher MERGE/SET. Knowledge is current as of ${res.timestamp || "now"}.*`,
        toolName: "live_mutation",
        subgraph: res.subgraph,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, agentMsg]);
      if (res.subgraph) {
        onSubgraphUpdate(res.subgraph);
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          text: `⚠️ **Mutation Error**: ${err.message || err}`,
          timestamp: "Error",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleCustomSubmit = async (e: React.FormEvent) => {

    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userText = input.trim();
    setInput("");

    // Infer endpoint based on query keywords
    let endpoint = "find-redundant-systems";
    let payload: any = {};
    const lower = userText.toLowerCase();

    if (lower.includes("expert") || lower.includes("who") || lower.includes("sme")) {

      endpoint = "find-counterpart-expert";
      payload = { topic: lower.includes("auth") ? "Authentication" : "Core", company: "Vaultly" };
    } else if (lower.includes("conflict") || lower.includes("policy") || lower.includes("retention")) {
      endpoint = "detect-policy-conflicts";
      payload = { domain: lower.includes("auth") ? "Authentication" : undefined };
    } else if (lower.includes("lineage") || lower.includes("why") || lower.includes("decision")) {
      endpoint = "trace-decision-lineage";
      payload = { system_name: "Gatekeeper-Auth" };
    } else if (lower.includes("intro") || lower.includes("connect") || lower.includes("path")) {
      endpoint = "warm-intro-path";
      payload = { person_a: "Aarav Mehta", person_b: "Diya Nair" };
    }

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res: ToolResponse = await callTool(endpoint, payload);
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          text: res.text_answer,
          toolName: res.tool_name,
          subgraph: res.subgraph,
          timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
        },
      ]);
      if (res.subgraph) {
        onSubgraphUpdate(res.subgraph);
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          text: `⚠️ **Query Error**: ${err.message}`,
          timestamp: "Error",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border-r border-slate-800 w-full lg:w-[480px] xl:w-[540px]">
      {/* Header */}
      <div className="p-4 border-b border-slate-800 flex items-center justify-between bg-slate-900/60 backdrop-blur-md">
        <div>
          <div className="flex items-center gap-2">
            <span className="p-1.5 rounded-lg bg-indigo-600/30 text-indigo-400 border border-indigo-500/30">
              <Sparkles className="w-4 h-4" />
            </span>
            <h1 className="font-bold text-base text-slate-100 tracking-tight">
              OrgBridge AI
            </h1>
            <span className="text-[10px] font-semibold bg-indigo-500/20 text-indigo-300 px-1.5 py-0.5 rounded border border-indigo-500/30">
              Track 03
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            The M&A Chaos Resolver — FalkorDB Brain
          </p>
        </div>

        {/* Database connectivity pill */}
        <div className="flex items-center gap-2">
          <div className="flex items-center gap-1.5 text-xs bg-slate-950/80 px-2.5 py-1 rounded-full border border-slate-800">
            <span
              className={`w-2 h-2 rounded-full ${
                isBackendHealthy ? "bg-emerald-500 animate-pulse" : "bg-amber-500"
              }`}
            />
            <span className="text-[11px] font-medium text-slate-300">
              {isBackendHealthy ? "FalkorDB Live" : "Connecting..."}
            </span>
          </div>
        </div>
      </div>

      {/* M&A Crisis Prompts Carousel / Grid */}
      <div className="p-3 bg-slate-950/50 border-b border-slate-800/80">
        <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center gap-1">
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          Judge Evaluation Prompts (One-Click)
        </p>
        <div className="flex flex-wrap gap-1.5">
          {CRISIS_PROMPTS.map((crisis, idx) => {
            const Icon = crisis.icon;
            return (
              <button
                key={idx}
                onClick={() => handleRunCrisisPrompt(crisis)}
                disabled={isLoading}
                className="flex items-center gap-1 text-[11px] bg-slate-800/90 hover:bg-slate-700 hover:border-slate-600 text-slate-200 border border-slate-700/80 px-2.5 py-1 rounded-md transition disabled:opacity-50"
              >
                <Icon className="w-3 h-3 text-cyan-400" />
                <span>{crisis.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Live Graph Mutation Controls (Track 03 Hardening) */}
      <div className="p-3 bg-slate-950/70 border-b border-slate-800/80">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            Live Brain Mutations (Track 03)
          </p>
          <span className="text-[10px] text-slate-500 font-mono">Dynamic Cypher MERGE/SET</span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() => handleLiveMutation("resolve-auth", "Unify 30-min JWT with Biometric Refresh")}
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 border border-emerald-700/60 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
            <span className="truncate">Resolve Auth Conflict</span>
          </button>
          <button
            onClick={() => handleLiveMutation("resolve-retention", "Adopt 90-Day Tiered Audit Storage")}
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 border border-emerald-700/60 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
            <span className="truncate">Resolve Retention</span>
          </button>
          <button
            onClick={() => handleLiveMutation("merge-teams", "Merge SecArch and Identity Growth into Unified Org")}
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-indigo-950/40 hover:bg-indigo-900/50 text-indigo-300 border border-indigo-700/60 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <GitMerge className="w-3 h-3 text-indigo-400 shrink-0" />
            <span className="truncate">Merge Sec & Auth</span>
          </button>
          <button
            onClick={() => handleLiveMutation("reset-demo", "Restore FalkorDB multigraph to initial state")}
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 border border-slate-700 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <RotateCcw className="w-3 h-3 text-amber-400 shrink-0" />
            <span className="truncate">Reset Demo Graph</span>
          </button>
        </div>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m) => (
          <div
            key={m.id}
            className={`flex flex-col ${
              m.sender === "user" ? "items-end" : "items-start"
            }`}
          >
            <div className="flex items-center gap-1.5 mb-1 text-[11px] text-slate-400">
              {m.sender === "user" ? (
                <>
                  <span>You</span>
                  <User className="w-3.5 h-3.5 text-slate-400" />
                </>
              ) : (
                <>
                  <Bot className="w-3.5 h-3.5 text-cyan-400" />
                  <span className="font-semibold text-slate-300">OrgBridge Agent</span>
                  {m.toolName && (
                    <span className="bg-slate-800 text-[10px] text-cyan-300 px-1.5 py-0.2 rounded border border-cyan-800">
                      {m.toolName}
                    </span>
                  )}
                </>
              )}
            </div>

            <div
              className={`p-3.5 rounded-xl max-w-[92%] text-xs leading-relaxed shadow-lg ${
                m.sender === "user"
                  ? "bg-blue-600 text-white rounded-tr-none"
                  : "bg-slate-800/90 border border-slate-700/70 text-slate-200 rounded-tl-none prose prose-invert prose-xs max-w-none"
              }`}
            >
              <div
                className="whitespace-pre-wrap break-words space-y-2"
                dangerouslySetInnerHTML={{
                  __html: m.text
                    .replace(/\n\n/g, "<br/><br/>")
                    .replace(/\n/g, "<br/>")
                    .replace(/### (.*?)(<br\/>|$)/g, '<h3 class="font-bold text-cyan-400 text-sm">$1</h3>')
                    .replace(/#### (.*?)(<br\/>|$)/g, '<h4 class="font-semibold text-slate-100 text-xs mt-1">$1</h4>')
                    .replace(/\*\*(.*?)\*\*/g, '<strong class="font-bold text-white">$1</strong>')
                    .replace(/\*(.*?)\*/g, '<em class="text-slate-300">$1</em>')
                    .replace(/`([^`]+)`/g, '<code class="bg-slate-900 text-cyan-300 px-1 py-0.5 rounded font-mono text-[11px]">$1</code>')
                    .replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" rel="noreferrer" class="text-blue-400 underline hover:text-blue-300">$1</a>'),
                }}
              />

              {m.subgraph && m.subgraph.nodes.length > 0 && (
                <div className="mt-3 pt-2 border-t border-slate-700/60 flex items-center justify-between text-[11px]">
                  <span className="text-slate-400">
                    Traversed: {m.subgraph.nodes.length} nodes, {m.subgraph.edges.length} edges
                  </span>
                  <button
                    onClick={() => onSubgraphUpdate(m.subgraph || null)}
                    className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 font-medium transition"
                  >
                    <Layers className="w-3 h-3" />
                    Inspect on Canvas
                  </button>
                </div>
              )}
            </div>
            <span className="text-[10px] text-slate-500 mt-1">{m.timestamp}</span>
          </div>
        ))}

        {isLoading && (
          <div className="flex items-center gap-2 p-3 bg-slate-800/60 rounded-xl border border-slate-700/50 text-slate-400 text-xs w-fit animate-pulse">
            <Bot className="w-4 h-4 text-cyan-400 animate-spin" />
            <span>Traversing FalkorDB multigraph & executing Cypher algorithms...</span>
          </div>
        )}
      </div>

      {/* Input Form */}
      <form
        onSubmit={handleCustomSubmit}
        className="p-3 border-t border-slate-800 bg-slate-900/80 backdrop-blur-md flex items-center gap-2"
      >
        <input
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask a question or test an M&A scenario..."
          disabled={isLoading}
          className="flex-1 bg-slate-950 border border-slate-800 focus:border-cyan-500 focus:outline-none rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 transition"
        />
        <button
          type="submit"
          disabled={isLoading || !input.trim()}
          className="bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white p-2 rounded-lg transition"
          title="Send query"
        >
          <Send className="w-4 h-4" />
        </button>
      </form>
    </div>
  );
}
