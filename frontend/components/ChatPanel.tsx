"use client";

import React, { useState, useMemo } from "react";
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
import { SubgraphData, ToolResponse, callTool, mutateGraph } from "@/lib/api";


export interface Message {
  id: string;
  sender: "user" | "agent";
  text: string;
  toolName?: string;
  subgraph?: SubgraphData;
  timestamp: string;
}

const KNOWN_SYSTEMS_FALLBACK = [
  "Gatekeeper-Auth",
  "Pulse-Identity",
  "FinPay-Core-Ledger",
  "Vault-Engine",
  "FinPay-Mesh-Gateway",
  "Vaultly-Public-API",
  "Customer-KYC-Service",
  "User-Onboarding-Verification",
  "core-api",
];

const KNOWN_PEOPLE_FALLBACK = [
  "Aarav Mehta",
  "Diya Nair",
  "Rohan Gupta",
  "Priya Sharma",
  "Neha Verma",
  "Arjun Das",
  "Kabir Patel",
  "Tanya Sen",
  "Rahul Sharma",
];

const KNOWN_DOMAINS_FALLBACK = [
  "Authentication",
  "Data Retention",
  "Ledger",
  "Gateway",
  "KYC",
  "Core Services",
];

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function formatInline(str: string): string {
  return str
    // Inline code: `code`
    .replace(
      /`([^`]+)`/g,
      '<code class="bg-slate-950 text-cyan-300 px-1 py-0.5 rounded font-mono text-[11px] border border-slate-800">$1</code>'
    )
    // Bold: **bold**
    .replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-white">$1</strong>')
    // Italic: *italic*
    .replace(/\*([^*]+)\*/g, '<em class="text-slate-300">$1</em>')
    // Links: [text](url)
    .replace(
      /\[(.*?)\]\(((?:https?:\/\/|\/|mailto:)[^\s"'>]+)\)/g,
      '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-cyan-400 underline underline-offset-2 hover:text-cyan-300 font-medium">$1</a>'
    );
}

function renderSafeMarkdown(text: string): string {
  if (!text) return "";

  // 1. Escape all raw HTML to neutralize XSS
  const escaped = escapeHtml(text);

  // 2. Process block elements line by line
  const lines = escaped.split(/\r?\n/);
  const output: string[] = [];
  let inUl = false;
  let inOl = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Unordered list item (- or *)
    const ulMatch = line.match(/^(\s*)[-*]\s+(.*)$/);
    if (ulMatch) {
      if (inOl) {
        output.push("</ol>");
        inOl = false;
      }
      if (!inUl) {
        output.push('<ul class="list-disc list-inside space-y-1 my-1 pl-1 text-slate-200">');
        inUl = true;
      }
      output.push(`<li>${formatInline(ulMatch[2])}</li>`);
      continue;
    } else if (inUl) {
      output.push("</ul>");
      inUl = false;
    }

    // Ordered list item (1. 2.)
    const olMatch = line.match(/^(\s*)\d+\.\s+(.*)$/);
    if (olMatch) {
      if (inUl) {
        output.push("</ul>");
        inUl = false;
      }
      if (!inOl) {
        output.push('<ol class="list-decimal list-inside space-y-1 my-1 pl-1 text-slate-200">');
        inOl = true;
      }
      output.push(`<li>${formatInline(olMatch[2])}</li>`);
      continue;
    } else if (inOl) {
      output.push("</ol>");
      inOl = false;
    }

    // Headings
    if (line.startsWith("### ")) {
      output.push(`<h3 class="font-bold text-cyan-400 text-sm mt-2 mb-1">${formatInline(line.slice(4))}</h3>`);
      continue;
    }
    if (line.startsWith("#### ")) {
      output.push(`<h4 class="font-semibold text-slate-100 text-xs mt-1.5 mb-0.5">${formatInline(line.slice(5))}</h4>`);
      continue;
    }

    // Blockquotes (> becomes &gt;)
    if (line.startsWith("&gt; ") || line.startsWith("&gt;")) {
      const bqContent = line.replace(/^&gt;\s?/, "");
      output.push(
        `<blockquote class="border-l-2 border-cyan-500/80 pl-2.5 my-1.5 text-slate-300 italic text-[11px] bg-slate-900/40 py-1 rounded-r">${formatInline(
          bqContent
        )}</blockquote>`
      );
      continue;
    }

    // Horizontal rules
    if (/^---|\*\*\*|___$/.test(line.trim())) {
      output.push('<hr class="border-slate-700/70 my-2" />');
      continue;
    }

    // Paragraph gaps
    if (!line.trim()) {
      output.push('<div class="h-1.5"></div>');
      continue;
    }

    // Regular line
    output.push(`<p class="leading-relaxed">${formatInline(line)}</p>`);
  }

  if (inUl) output.push("</ul>");
  if (inOl) output.push("</ol>");

  return output.join("");
}

interface ChatPanelProps {
  onSubgraphUpdate: (subgraph: SubgraphData | null) => void;
  onFullGraphRefresh?: (freshData?: SubgraphData) => void;
  isBackendHealthy: boolean;
  graphData?: SubgraphData;
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
  onFullGraphRefresh,
  isBackendHealthy,
  graphData,
}: ChatPanelProps) {
  // Dynamically derive systems, people, domains, and companies from the live graph
  const dynamicSystems = useMemo(() => {
    const fromGraph = (graphData?.nodes || [])
      .filter((n) => n.label === "System" && n.name)
      .map((n) => n.name);
    return Array.from(new Set(fromGraph.length > 0 ? fromGraph : KNOWN_SYSTEMS_FALLBACK));
  }, [graphData]);

  const dynamicPeople = useMemo(() => {
    const fromGraph = (graphData?.nodes || [])
      .filter((n) => n.label === "Person" && n.name)
      .map((n) => n.name);
    return Array.from(new Set(fromGraph.length > 0 ? fromGraph : KNOWN_PEOPLE_FALLBACK));
  }, [graphData]);

  const dynamicDomains = useMemo(() => {
    const fromGraph = (graphData?.nodes || [])
      .map((n) => n.properties?.domain)
      .filter(Boolean) as string[];
    return Array.from(new Set(fromGraph.length > 0 ? fromGraph : KNOWN_DOMAINS_FALLBACK));
  }, [graphData]);

  const dynamicCompanies = useMemo(() => {
    const fromGraph = (graphData?.nodes || [])
      .map((n) => n.company_origin)
      .filter((c) => c && c !== "External") as string[];
    const set = new Set(fromGraph.length > 0 ? fromGraph : ["FinPay", "Vaultly", "Unified"]);
    set.add("Unified");
    return Array.from(set);
  }, [graphData]);
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

      // Re-fetch the full updated graph from FalkorDB so main canvas reflects mutations
      if (onFullGraphRefresh) {
        onFullGraphRefresh();
      }

      // Handle active subgraph isolation / highlight
      if (action === "reset-demo") {
        onSubgraphUpdate(null);
      } else if (res.subgraph) {
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

    // Dynamically infer endpoint and extract entities
    let endpoint = "find-redundant-systems";
    let payload: any = {};
    const lower = userText.toLowerCase();

    // 1. Warm Intro Path
    if (
      lower.includes("intro") ||
      lower.includes("connect") ||
      lower.includes("path") ||
      lower.includes("reach") ||
      lower.includes("introduce") ||
      lower.includes("warm")
    ) {
      endpoint = "warm-intro-path";
      // Find known people dynamically mentioned in query
      const matchedPeople = dynamicPeople.filter((p) => lower.includes(p.toLowerCase()));
      let personA = matchedPeople[0];
      let personB = matchedPeople[1];

      // Try regex extraction for "between X and Y" or "from X to Y"
      if (!personA || !personB) {
        const betweenMatch = userText.match(
          /(?:between|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:and|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)/i
        );
        if (betweenMatch) {
          personA = personA || betweenMatch[1].trim();
          personB = personB || betweenMatch[2].trim();
        }
      }

      payload = {
        person_a: personA || dynamicPeople[0] || "Aarav Mehta",
        person_b: personB || dynamicPeople[1] || "Diya Nair",
      };
    }
    // 2. Decision Lineage
    else if (
      lower.includes("lineage") ||
      lower.includes("why") ||
      lower.includes("decision") ||
      lower.includes("rfc") ||
      lower.includes("origin") ||
      lower.includes("history")
    ) {
      endpoint = "trace-decision-lineage";
      const matchedSys = dynamicSystems.find((s) => lower.includes(s.toLowerCase()));
      let systemName = matchedSys;

      if (!systemName) {
        const quoted = userText.match(/['"]([^'"]+)['"]/);
        const sysWord = userText.match(/(?:for|system|of)\s+([A-Za-z0-9_-]+)/i);
        systemName = (quoted && quoted[1]) || (sysWord && sysWord[1]) || dynamicSystems[0] || "Gatekeeper-Auth";
      }

      payload = { system_name: systemName };
    }
    // 3. Counterpart SME Discovery
    else if (
      lower.includes("expert") ||
      lower.includes("who") ||
      lower.includes("sme") ||
      lower.includes("counterpart") ||
      lower.includes("specialist") ||
      lower.includes("lead")
    ) {
      endpoint = "find-counterpart-expert";
      // Dynamic company extraction supporting Unified entity after live mutations
      let company = "Vaultly";
      if (lower.includes("unified")) company = "Unified";
      else if (lower.includes("finpay")) company = "FinPay";
      else if (lower.includes("vaultly")) company = "Vaultly";
      else {
        const matchedCo = dynamicCompanies.find((c) => lower.includes(c.toLowerCase()));
        if (matchedCo) company = matchedCo;
      }

      let topic = dynamicDomains[0] || "Authentication";
      if (lower.includes("auth")) topic = "Authentication";
      else if (lower.includes("retention") || lower.includes("audit")) topic = "Data Retention";
      else if (lower.includes("ledger") || lower.includes("balance")) topic = "Ledger";
      else if (lower.includes("gateway") || lower.includes("mesh")) topic = "Gateway";
      else if (lower.includes("kyc") || lower.includes("onboard")) topic = "KYC";
      else if (lower.includes("core")) topic = "Core Services";
      else {
        const matchedDomain = dynamicDomains.find((d) => lower.includes(d.toLowerCase()));
        if (matchedDomain) topic = matchedDomain;
      }

      payload = { topic, company };
    }
    // 4. Policy Conflicts
    else if (
      lower.includes("conflict") ||
      lower.includes("policy") ||
      lower.includes("retention") ||
      lower.includes("compliance") ||
      lower.includes("clash") ||
      lower.includes("contradiction")
    ) {
      endpoint = "detect-policy-conflicts";
      let domain: string | undefined = undefined;
      if (lower.includes("auth")) domain = "Authentication";
      else if (lower.includes("retention") || lower.includes("audit")) domain = "Data Retention";
      else if (lower.includes("ledger")) domain = "Ledger";
      else if (lower.includes("gateway") || lower.includes("mesh")) domain = "Gateway";
      else if (lower.includes("kyc")) domain = "KYC";
      else if (lower.includes("core")) domain = "Core Services";
      else {
        const matchedDomain = dynamicDomains.find((d) => lower.includes(d.toLowerCase()));
        if (matchedDomain) domain = matchedDomain;
      }

      payload = { domain };
    }
    // 5. Redundant Systems (default)
    else {
      endpoint = "find-redundant-systems";
      payload = {};
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
                    <span className="bg-slate-800 text-[10px] text-cyan-300 px-1.5 py-0.5 rounded border border-cyan-800 font-mono">
                      {m.toolName}
                    </span>
                  )}
                </>
              )}
            </div>

            <div
              className={`p-3.5 rounded-xl max-w-[92%] text-xs leading-relaxed shadow-lg ${
                m.sender === "user"
                  ? "bg-blue-600 text-white rounded-tr-none font-medium"
                  : "bg-slate-800/90 border border-slate-700/70 text-slate-200 rounded-tl-none"
              }`}
            >
              {m.sender === "user" ? (
                <div className="whitespace-pre-wrap break-words">{m.text}</div>
              ) : (
                <div
                  className="space-y-1.5 break-words"
                  dangerouslySetInnerHTML={{
                    __html: renderSafeMarkdown(m.text),
                  }}
                />
              )}

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
