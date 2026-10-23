"use client";

import React, { useState, useEffect } from "react";
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
  Copy,
  Check,
  Trash2,
} from "lucide-react";
import { SubgraphData, ToolResponse, callTool, mutateGraph, chatWithAgent } from "@/lib/api";



import Markdown from "markdown-to-jsx";

export interface Message {
  id: string;
  sender: "user" | "agent";
  text: string;
  toolName?: string;
  subgraph?: SubgraphData;
  timestamp: string;
}

const TOOL_DISPLAY_NAMES: Record<string, string> = {
  live_mutation: "Real-Time Alignment",
  find_counterpart_expert: "Expert Discovery",
  detect_policy_conflicts: "Policy Conflict Audit",
  find_redundant_systems: "Redundancy Analysis",
  trace_decision_lineage: "Decision Lineage",
  get_warm_intro_path: "Warm Introduction",
  detect_organizational_silos: "Silo Isolation",
  schema_constrained_cypher: "Graph Intelligence",
  llm_agent: "AI Reasoning",
  error: "System Notice",
};

function formatToolBadge(name?: string): string {
  if (!name) return "";
  return TOOL_DISPLAY_NAMES[name] || name.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

interface ParsedBlock {
  type: "text" | "details";
  summary?: string;
  content: string;
  children?: ParsedBlock[];
}

/**
 * Robustly parses balanced <details>...</details> blocks supporting arbitrary nesting.
 * Raw HTML inside markdown is disabled so hostile tags can never be injected.
 */
function parseDetailsBlocks(text: string): ParsedBlock[] {
  const result: ParsedBlock[] = [];
  let remaining = text;
  const openTagRegex = /<details(?:\s+class="([^"]*)")?>/i;

  while (remaining.length > 0) {
    const match = openTagRegex.exec(remaining);
    if (!match) {
      if (remaining) result.push({ type: "text", content: remaining });
      break;
    }

    const startIndex = match.index;
    if (startIndex > 0) {
      result.push({ type: "text", content: remaining.slice(0, startIndex) });
    }

    let depth = 1;
    let cursor = startIndex + match[0].length;
    let endIndex = -1;

    while (cursor < remaining.length) {
      const remainingSlice = remaining.slice(cursor);
      const nextOpen = remainingSlice.search(/<details(?:\s+[^>]*)?>/i);
      const nextClose = remainingSlice.search(/<\/details>/i);

      if (nextClose === -1) {
        break;
      }

      if (nextOpen !== -1 && nextOpen < nextClose) {
        depth++;
        cursor += nextOpen + 9;
      } else {
        depth--;
        if (depth === 0) {
          endIndex = cursor + nextClose + 10;
          break;
        }
        cursor += nextClose + 10;
      }
    }

    if (endIndex === -1) {
      result.push({ type: "text", content: remaining.slice(startIndex) });
      break;
    }

    const detailsBlock = remaining.slice(startIndex, endIndex);
    const summaryMatch = /<summary>([\s\S]*?)<\/summary>/i.exec(detailsBlock);
    const summary = summaryMatch ? summaryMatch[1].trim() : "Thinking & Query Execution";

    let innerContent = "";
    if (summaryMatch) {
      const summaryEnd = summaryMatch.index + summaryMatch[0].length;
      innerContent = detailsBlock.slice(summaryEnd, detailsBlock.lastIndexOf("</details>"));
    } else {
      innerContent = detailsBlock.slice(match[0].length, detailsBlock.lastIndexOf("</details>"));
    }

    result.push({
      type: "details",
      summary: summary,
      content: innerContent.trim(),
      children: parseDetailsBlocks(innerContent.trim()),
    });

    remaining = remaining.slice(endIndex);
  }

  return result;
}

const safeMarkdownOverrides = {
  a: {
    component: ({ href, children, ...props }: any) => {
      // Safe link handling: only allow http://, https://, /, or mailto:
      const isSafe = /^(?:https?:\/\/|\/|mailto:)[^\s"'>]+$/i.test(href || "");
      if (!isSafe) {
        return <span className="text-slate-300 font-mono text-[11px]">{children}</span>;
      }
      return (
        <a
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-cyan-400 underline underline-offset-2 hover:text-cyan-300 font-medium"
          {...props}
        >
          {children}
        </a>
      );
    },
  },
  code: {
    component: ({ children, ...props }: any) => {
      return (
        <code
          className="bg-slate-950 text-cyan-300 px-1 py-0.5 rounded font-mono text-[11px] border border-slate-800"
          {...props}
        >
          {children}
        </code>
      );
    },
  },
  strong: {
    component: ({ children, ...props }: any) => {
      const str = (Array.isArray(children) ? children.join("") : typeof children === "string" ? children : "").trim();
      const match = str.match(/^\[?(CRITICAL|HIGH|MEDIUM|LOW)\]?(\s+SEVERITY)?$/i);
      if (match) {
        const upper = match[1].toUpperCase();
        let color = "bg-red-950/80 text-red-300 border-red-700/80";
        if (upper === "HIGH") color = "bg-amber-950/80 text-amber-300 border-amber-600/80";
        if (upper === "MEDIUM") color = "bg-yellow-950/80 text-yellow-300 border-yellow-600/80";
        if (upper === "LOW") color = "bg-blue-950/80 text-blue-300 border-blue-600/80";
        return (
          <span className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border ${color} ml-1.5 shadow-sm align-middle`}>
            {upper} SEVERITY
          </span>
        );
      }
      return (
        <strong className="font-bold text-white" {...props}>
          {children}
        </strong>
      );
    },
  },
  table: {
    component: ({ children, ...props }: any) => (
      <div className="overflow-x-auto my-2 rounded border border-slate-800/80 bg-slate-950/70 shadow-sm">
        <table className="w-full text-left text-[11px] font-mono border-collapse" {...props}>
          {children}
        </table>
      </div>
    ),
  },
  thead: {
    component: ({ children, ...props }: any) => (
      <thead className="border-b border-slate-800 bg-slate-900/90 text-cyan-300" {...props}>
        {children}
      </thead>
    ),
  },
  tbody: {
    component: ({ children, ...props }: any) => (
      <tbody className="divide-y divide-slate-800/60 text-slate-300" {...props}>
        {children}
      </tbody>
    ),
  },
  tr: {
    component: ({ children, ...props }: any) => (
      <tr className="hover:bg-slate-900/40 transition-colors" {...props}>
        {children}
      </tr>
    ),
  },
  th: {
    component: ({ children, ...props }: any) => (
      <th className="px-3 py-1.5 font-semibold text-[10px] tracking-wider uppercase text-slate-300" {...props}>
        {children}
      </th>
    ),
  },
  td: {
    component: ({ children, ...props }: any) => (
      <td className="px-3 py-1.5 text-slate-200" {...props}>
        {children}
      </td>
    ),
  },
  blockquote: {
    component: ({ children, ...props }: any) => (
      <blockquote className="border-l-2 border-cyan-500/80 pl-2.5 my-1.5 text-slate-300 italic text-[11px] bg-slate-900/40 py-1 rounded-r" {...props}>
        {children}
      </blockquote>
    ),
  },
  h1: {
    component: ({ children, ...props }: any) => (
      <h1 className="font-bold text-cyan-400 text-base mt-2 mb-1" {...props}>
        {children}
      </h1>
    ),
  },
  h2: {
    component: ({ children, ...props }: any) => (
      <h2 className="font-bold text-cyan-400 text-sm mt-2 mb-1" {...props}>
        {children}
      </h2>
    ),
  },
  h3: {
    component: ({ children, ...props }: any) => (
      <h3 className="font-bold text-cyan-400 text-sm mt-2 mb-1" {...props}>
        {children}
      </h3>
    ),
  },
  h4: {
    component: ({ children, ...props }: any) => (
      <h4 className="font-semibold text-slate-100 text-xs mt-1.5 mb-0.5" {...props}>
        {children}
      </h4>
    ),
  },
  ul: {
    component: ({ children, ...props }: any) => (
      <ul className="list-disc list-inside space-y-1 my-1 pl-1 text-slate-200" {...props}>
        {children}
      </ul>
    ),
  },
  ol: {
    component: ({ children, ...props }: any) => (
      <ol className="list-decimal list-inside space-y-1 my-1 pl-1 text-slate-200" {...props}>
        {children}
      </ol>
    ),
  },
  hr: {
    component: ({ ...props }: any) => (
      <hr className="border-slate-700/70 my-2" {...props} />
    ),
  },
  p: {
    component: ({ children, ...props }: any) => (
      <p className="leading-relaxed my-1" {...props}>
        {children}
      </p>
    ),
  },
};

function SafeMarkdownNodeList({ blocks }: { blocks: ParsedBlock[] }) {
  return (
    <>
      {blocks.map((block, idx) => {
        if (block.type === "text") {
          return (
            <Markdown
              key={idx}
              options={{
                disableParsingRawHTML: true,
                overrides: safeMarkdownOverrides,
              }}
            >
              {block.content}
            </Markdown>
          );
        } else {
          return (
            <details
              key={idx}
              className="group my-2.5 border border-slate-800/80 bg-slate-950/60 hover:bg-slate-950/80 rounded-lg overflow-hidden transition-all duration-200 shadow-sm"
            >
              <summary className="flex items-center justify-between cursor-pointer select-none px-3 py-2 text-[11px] font-medium text-slate-400 hover:text-cyan-300 bg-slate-900/40 hover:bg-slate-900/70 border-b border-transparent group-open:border-slate-800/70 transition-all">
                <span className="flex items-center gap-1.5 font-mono">
                  <Sparkles className="w-3.5 h-3.5 text-cyan-400 shrink-0" />
                  <span>{block.summary || "Thinking & Query Execution"}</span>
                </span>
                <span className="text-[10px] text-slate-500 font-mono group-open:rotate-180 transition-transform duration-200">
                  ▼
                </span>
              </summary>
              <div className="p-3 text-[11px] space-y-2 text-slate-300 font-normal">
                {block.children && block.children.length > 0 ? (
                  <SafeMarkdownNodeList blocks={block.children} />
                ) : (
                  <Markdown
                    options={{
                      disableParsingRawHTML: true,
                      overrides: safeMarkdownOverrides,
                    }}
                  >
                    {block.content}
                  </Markdown>
                )}
              </div>
            </details>
          );
        }
      })}
    </>
  );
}

function SafeMarkdownRenderer({ text }: { text: string }) {
  if (!text) return null;
  // Pre-process stand-alone severity badges like [CRITICAL] or `[HIGH]` into **[CRITICAL]** for rich rendering
  const formatted = text.replace(/`?\[(CRITICAL|HIGH|MEDIUM|LOW)\]`?(?!\()/gi, "**[$1]**");
  const blocks = parseDetailsBlocks(formatted);
  return <SafeMarkdownNodeList blocks={blocks} />;
}

interface ChatPanelProps {
  selectedGraph?: string;
  onSubgraphUpdate: (subgraph: SubgraphData | null) => void;
  onFullGraphRefresh?: (freshData?: SubgraphData) => Promise<void> | void;
  onBackendHealthy?: () => void;
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
  {
    label: "Organizational Silos",
    icon: Layers,
    prompt: "Discover isolated organizational islands and single-tenant silos across FinPay and Vaultly using Weakly Connected Components (WCC).",
    endpoint: "detect-silos",
    payload: {},
  },
];


const MAX_MESSAGES = 40;
const SESSION_STORAGE_KEY = "orgbridge_chat_session_history";

export default function ChatPanel({
  selectedGraph = "merged_brain",
  onSubgraphUpdate,
  onFullGraphRefresh,
  onBackendHealthy,
  isBackendHealthy,
}: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      sender: "agent",
      text: "### Welcome to OrgBridge AI (The M&A Chaos Resolver)\n\nI am connected to your live **FalkorDB Multi-Tenant Brain** (`finpay_graph`, `vaultly_graph`, and `merged_brain`).\n\nClick any of the **M&A Crisis Prompts** below or ask any question to resolve organizational silos, uncover hidden dependencies, and detect conflicting architectural decisions.",
      timestamp: "Just now",
    },
  ]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  // Load chat session from sessionStorage on mount (F6)
  useEffect(() => {
    try {
      const stored = sessionStorage.getItem(SESSION_STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        if (Array.isArray(parsed) && parsed.length > 0) {
          setMessages(parsed);
        }
      }
    } catch (err) {
      console.warn("Could not load stored session history:", err);
    }
  }, []);

  // Persist compact chat session transcript on update (F6)
  useEffect(() => {
    if (messages.length > 0) {
      try {
        const compact = messages.slice(-MAX_MESSAGES).map((m) => ({
          id: m.id,
          sender: m.sender,
          text: m.text,
          toolName: m.toolName,
          timestamp: m.timestamp,
          subgraph: m.subgraph
            ? {
                nodes: m.subgraph.nodes?.slice(0, 30),
                edges: m.subgraph.edges?.slice(0, 50),
              }
            : undefined,
        }));
        sessionStorage.setItem(SESSION_STORAGE_KEY, JSON.stringify(compact));
      } catch (err) {
        console.warn("Could not persist session history:", err);
      }
    }
  }, [messages]);

  // Memory management: limit retained chat history to prevent memory/DOM bloat (F6)
  const appendMessage = (newMsg: Message) => {
    setMessages((prev) => {
      const updated = [...prev, newMsg];
      if (updated.length > MAX_MESSAGES) {
        return [updated[0], ...updated.slice(-(MAX_MESSAGES - 1))];
      }
      return updated;
    });
  };

  const handleExportTranscript = () => {
    const transcript = messages
      .map(
        (m) =>
          `[${m.timestamp}] ${m.sender === "user" ? "USER" : `AGENT (${m.toolName || "Chat"})`}:\n${m.text}\n`
      )
      .join("\n---\n\n");
    navigator.clipboard.writeText(transcript);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleClearSession = () => {
    try {
      sessionStorage.removeItem(SESSION_STORAGE_KEY);
    } catch {}
    setMessages([
      {
        id: "welcome",
        sender: "agent",
        text: "### Welcome to OrgBridge AI (The M&A Chaos Resolver)\n\nI am connected to your live **FalkorDB Multi-Tenant Brain** (`finpay_graph`, `vaultly_graph`, and `merged_brain`).\n\nClick any of the **M&A Crisis Prompts** below or ask any question to resolve organizational silos, uncover hidden dependencies, and detect conflicting architectural decisions.",
        timestamp: "Just now",
      },
    ]);
    onSubgraphUpdate(null);
  };

  const handleRunCrisisPrompt = async (crisis: typeof CRISIS_PROMPTS[0]) => {
    if (isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: crisis.prompt,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    appendMessage(userMsg);
    setIsLoading(true);

    try {
      const res: ToolResponse = await callTool(crisis.endpoint, { ...crisis.payload, graph: selectedGraph });
      onBackendHealthy?.();
      const agentMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        text: res.text_answer,
        toolName: res.tool_name,
        subgraph: res.subgraph,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      appendMessage(agentMsg);
      if (res.subgraph) {
        onSubgraphUpdate(res.subgraph);
      }
    } catch (err: any) {
      appendMessage({
        id: (Date.now() + 1).toString(),
        sender: "agent",
        toolName: "error",
        text: `**Query Error**: ${err.message || err}`,
        timestamp: "Error",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleLiveMutation = async (
    action: "resolve-auth" | "resolve-retention" | "merge-teams" | "reset-demo",
    promptText: string,
    payload?: Record<string, any>
  ) => {
    if (isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: promptText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    appendMessage(userMsg);
    setIsLoading(true);

    try {
      // Build sensible domain defaults if not supplied
      let mutationPayload = payload;
      if (!mutationPayload) {
        if (action === "resolve-auth") {
          mutationPayload = { compromise_ttl_minutes: 30, confirm_compliance_override: false };
        } else if (action === "resolve-retention") {
          mutationPayload = { retention_days: 90, confirm_compliance_override: false };
        } else if (action === "merge-teams") {
          mutationPayload = {
            team_a_id: "finpay:team:secarch",
            team_b_id: "vaultly:team:identity_growth",
            unified_name: "Unified M&A Security & Identity Team",
          };
        }
      }

      const res = await mutateGraph(action, selectedGraph, mutationPayload);
      onBackendHealthy?.();

      const actionTitleMap: Record<string, string> = {
        "resolve-auth": "Authentication Policy Standardization",
        "resolve_auth_conflict": "Authentication Policy Standardization",
        "resolve-retention": "Data Retention Harmonization",
        "resolve_retention_conflict": "Data Retention Harmonization",
        "merge-teams": "Cross-Company Team Consolidation",
        "merge_teams": "Cross-Company Team Consolidation",
        "reset-demo": "Baseline Knowledge Restoration",
        "reset_demo": "Baseline Knowledge Restoration",
      };

      const friendlyDecision = actionTitleMap[res.action || action] || "Enterprise Knowledge Alignment";

      let outboxText = "";
      if (res.outbox?.writebacks) {
        const gh = res.outbox.writebacks.github;
        const jira = res.outbox.writebacks.jira;
        const slack = res.outbox.writebacks.slack;
        outboxText = `\n\n#### 🔗 External Systems Write-Back\n` +
          `- **GitHub PR**: [${gh?.title || "Deprecation Pull Request"}](${gh?.html_url || "#"}) (Status: \`${gh?.sync_status || "SYNCED"}\`)\n` +
          `- **Jira Epic**: [${jira?.summary || "Migration Epic"}](${jira?.key ? `https://finpay-jira.atlassian.net/browse/${jira.key}` : "#"}) (Status: \`${jira?.sync_status || "SYNCED"}\`)\n` +
          `- **Slack**: Block Kit Approval Card sent to \`${slack?.channel || "#mna-architecture-bridge"}\` (Status: \`${slack?.sync_status || "SYNCED"}\`)`;
      }

      const agentMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        text: `### Real-Time Policy Alignment Implemented\n\n` +
              `**Decision**: ${friendlyDecision}\n\n` +
              `**Impact**: ${res.resolution_summary || res.message}${outboxText}\n\n` +
              `> *Enterprise knowledge updated in real-time. Verified as of ${res.timestamp || "now"}.*`,
        toolName: "live_mutation",
        subgraph: res.subgraph,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      appendMessage(agentMsg);

      // Re-fetch or update the full graph from FalkorDB so main canvas reflects mutations
      if (action === "reset-demo") {
        if (selectedGraph === "merged_brain" && res.subgraph) {
          if (onFullGraphRefresh) {
            await onFullGraphRefresh(res.subgraph);
          }
        } else if (onFullGraphRefresh) {
          await onFullGraphRefresh();
        }
        onSubgraphUpdate(null);
      } else {
        if (onFullGraphRefresh) {
          await onFullGraphRefresh();
        }
        if (res.subgraph) {
          onSubgraphUpdate(res.subgraph);
        }
      }
    } catch (err: any) {
      appendMessage({
        id: (Date.now() + 1).toString(),
        sender: "agent",
        toolName: "error",
        text: `**Mutation Error**: ${err.message || err}`,
        timestamp: "Error",
      });
    } finally {
      setIsLoading(false);
    }
  };

  const handleCustomSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!input.trim() || isLoading) return;

    const userText = input.trim();
    setInput("");

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    appendMessage(userMsg);
    setIsLoading(true);

    try {
      const res: ToolResponse = await chatWithAgent(userText, selectedGraph);
      onBackendHealthy?.();

      appendMessage({
        id: (Date.now() + 1).toString(),
        sender: "agent",
        text: res.text_answer,
        toolName: res.tool_name,
        subgraph: res.subgraph,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      });
      if (res.subgraph && res.subgraph.nodes?.length > 0) {
        onSubgraphUpdate(res.subgraph);
      }
    } catch (err: any) {
      appendMessage({
        id: (Date.now() + 1).toString(),
        sender: "agent",
        toolName: "error",
        text: `**Query Error**: ${err.message || err}`,
        timestamp: "Error",
      });
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-slate-900 border-r border-slate-800 w-full">
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
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            The M&A Chaos Resolver — FalkorDB Brain
          </p>
        </div>

        {/* Header Actions: Transcript Export, Session Reset, & Database Status */}
        <div className="flex items-center gap-1.5">
          <div className="hidden sm:flex items-center gap-1.5 text-[10px] bg-slate-950/80 px-2 py-1 rounded-full border border-slate-800 text-slate-400">
            <span className="flex items-center gap-1" title="GitHub App Connected"><span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />GitHub</span>
            <span className="text-slate-700">|</span>
            <span className="flex items-center gap-1" title="Jira 3LO Connected"><span className="w-1.5 h-1.5 rounded-full bg-sky-400" />Jira</span>
            <span className="text-slate-700">|</span>
            <span className="flex items-center gap-1" title="Slack Events API Connected"><span className="w-1.5 h-1.5 rounded-full bg-indigo-400" />Slack</span>
          </div>

          <button
            onClick={handleExportTranscript}
            className="p-1.5 rounded-lg bg-slate-950/80 hover:bg-slate-800 text-slate-400 hover:text-cyan-300 border border-slate-800 transition shadow-sm"
            title="Copy Session Transcript to Clipboard (F6)"
          >
            {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          <button
            onClick={handleClearSession}
            className="p-1.5 rounded-lg bg-slate-950/80 hover:bg-slate-800 text-slate-400 hover:text-amber-400 border border-slate-800 transition shadow-sm"
            title="Reset Chat Session & Clear Stored History (F6)"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>

          <div className="flex items-center gap-1.5 text-xs bg-slate-950/80 px-2.5 py-1 rounded-full border border-slate-800 shadow-sm">
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

      {/* Executive Alignment Actions */}
      <div className="p-3 bg-slate-950/70 border-b border-slate-800/80">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            Executive Alignment Actions
          </p>
          <span className="text-[10px] text-slate-400">Real-Time Knowledge Updates</span>
        </div>
        <div className="grid grid-cols-2 gap-1.5">
          <button
            onClick={() =>
              handleLiveMutation(
                "resolve-auth",
                "Resolve the authentication policy conflict: standardize on a unified 30-minute session with biometric refresh."
              )
            }
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 border border-emerald-700/60 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
            <span className="truncate">Standardize Auth Policy</span>
          </button>
          <button
            onClick={() =>
              handleLiveMutation(
                "resolve-retention",
                "Resolve the data retention conflict: enact a unified 90-day tiered cold storage policy across both companies."
              )
            }
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-emerald-950/40 hover:bg-emerald-900/50 text-emerald-300 border border-emerald-700/60 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <CheckCircle2 className="w-3 h-3 text-emerald-400 shrink-0" />
            <span className="truncate">Harmonize Log Retention</span>
          </button>
          <button
            onClick={() =>
              handleLiveMutation(
                "merge-teams",
                "Consolidate Security Architecture (FinPay) and Identity Growth (Vaultly) into a unified engineering org."
              )
            }
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-indigo-950/40 hover:bg-indigo-900/50 text-indigo-300 border border-indigo-700/60 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <GitMerge className="w-3 h-3 text-indigo-400 shrink-0" />
            <span className="truncate">Consolidate Security Teams</span>
          </button>
          <button
            onClick={() =>
              handleLiveMutation(
                "reset-demo",
                "Restore the knowledge graph to its initial pre-merger baseline."
              )
            }
            disabled={isLoading}
            className="flex items-center gap-1.5 text-[11px] bg-slate-800/80 hover:bg-slate-700/80 text-slate-300 border border-slate-700 px-2 py-1.5 rounded-md transition disabled:opacity-50 text-left"
          >
            <RotateCcw className="w-3 h-3 text-amber-400 shrink-0" />
            <span className="truncate">Restore Baseline Graph</span>
          </button>
        </div>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.map((m) => {
          const isErrorMsg =
            m.toolName === "error" ||
            m.text.startsWith("**Mutation Error**:") ||
            m.text.startsWith("**Query Error**:") ||
            m.text.includes("Mutation Error") ||
            m.text.includes("Query Error");

          return (
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
                    <Bot className={`w-3.5 h-3.5 ${isErrorMsg ? "text-red-400" : "text-cyan-400"}`} />
                    <span className={`font-semibold ${isErrorMsg ? "text-red-300" : "text-slate-300"}`}>
                      OrgBridge Agent
                    </span>
                    {m.toolName && (
                      <span
                        className={`text-[10px] px-2 py-0.5 rounded-full border font-medium tracking-wide ${
                          isErrorMsg
                            ? "bg-red-950/80 text-red-300 border-red-700/70"
                            : "bg-cyan-950/70 text-cyan-300 border-cyan-700/60"
                        }`}
                      >
                        {formatToolBadge(m.toolName)}
                      </span>
                    )}
                  </>
                )}
              </div>

              <div
                className={`p-3.5 rounded-xl max-w-[92%] text-xs leading-relaxed shadow-lg ${
                  m.sender === "user"
                    ? "bg-blue-600 text-white rounded-tr-none font-medium"
                    : isErrorMsg
                    ? "bg-red-950/40 border border-red-700/70 text-red-200 rounded-tl-none shadow-red-950/20"
                    : "bg-slate-800/90 border border-slate-700/70 text-slate-200 rounded-tl-none"
                }`}
              >
                {m.sender === "user" ? (
                  <div className="whitespace-pre-wrap break-words">{m.text}</div>
                ) : isErrorMsg ? (
                  <div className="flex items-start gap-2.5">
                    <div className="p-1 rounded-md bg-red-900/50 text-red-400 border border-red-700/60 shrink-0 mt-0.5">
                      <ShieldAlert className="w-4 h-4 text-red-400" />
                    </div>
                    <div className="space-y-1 break-words text-red-200 flex-1 leading-relaxed">
                      <SafeMarkdownRenderer text={m.text.replace(/^⚠️\s*/, "")} />
                    </div>
                  </div>
                ) : (
                  <div className="space-y-1.5 break-words">
                    <SafeMarkdownRenderer text={m.text} />
                  </div>
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
          );
        })}

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
