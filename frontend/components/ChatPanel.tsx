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
import { SubgraphData, ToolResponse, callTool, mutateGraph, chatWithAgent } from "@/lib/api";



export interface Message {
  id: string;
  sender: "user" | "agent";
  text: string;
  toolName?: string;
  subgraph?: SubgraphData;
  timestamp: string;
}

function escapeHtml(str: string): string {
  return str
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

const EMOJI_TO_SVG: Record<string, string> = {
  "🧠": `<svg class="inline-block w-4 h-4 text-cyan-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/><path d="M17.599 6.5a3 3 0 0 0 .399-1.375"/><path d="M6.003 5.125A3 3 0 0 0 6.401 6.5"/><path d="M3.477 10.896a4 4 0 0 1 .585-.396"/><path d="M19.938 10.5a4 4 0 0 1 .585.396"/><path d="M6 18a4 4 0 0 1-1.967-.516"/><path d="M19.967 17.484A4 4 0 0 1 18 18"/></svg>`,
  "⚡": `<svg class="inline-block w-3.5 h-3.5 text-amber-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/></svg>`,
  "⚠️": `<svg class="inline-block w-3.5 h-3.5 text-amber-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z"/><line x1="12" y1="9" x2="12" y2="13"/><line x1="12" y1="17" x2="12.01" y2="17"/></svg>`,
  "🔍": `<svg class="inline-block w-3.5 h-3.5 text-cyan-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>`,
  "🔗": `<svg class="inline-block w-3.5 h-3.5 text-indigo-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>`,
  "🏝️": `<svg class="inline-block w-3.5 h-3.5 text-cyan-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
  "🏝": `<svg class="inline-block w-3.5 h-3.5 text-cyan-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`,
};

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

function formatSeverityBadge(sev: string): string {
  const upper = sev.toUpperCase();
  let color = "bg-red-950/80 text-red-300 border-red-700/80";
  if (upper === "HIGH") color = "bg-amber-950/80 text-amber-300 border-amber-600/80";
  if (upper === "MEDIUM") color = "bg-yellow-950/80 text-yellow-300 border-yellow-600/80";
  if (upper === "LOW") color = "bg-blue-950/80 text-blue-300 border-blue-600/80";
  return `<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-bold tracking-wider uppercase border ${color} ml-1.5 shadow-sm align-middle">${upper} SEVERITY</span>`;
}

function formatInline(str: string): string {
  // Convert `[HIGH]`, `[CRITICAL]`, [HIGH], [CRITICAL] into styled enterprise badges (unless part of a markdown link [TEXT](url))
  let processed = str.replace(/`?\[(CRITICAL|HIGH|MEDIUM|LOW)\]`?(?!\()/gi, (_, sev) => formatSeverityBadge(sev));

  const codeSpans: string[] = [];
  // 1. Extract inline code spans and replace with placeholder to protect internal asterisks/brackets
  processed = processed.replace(/`([^`]+)`/g, (_, code) => {
    const idx = codeSpans.length;
    codeSpans.push(
      `<code class="bg-slate-950 text-cyan-300 px-1 py-0.5 rounded font-mono text-[11px] border border-slate-800">${code}</code>`
    );
    return `___INLINE_CODE_${idx}___`;
  });

  // 2. Bold: **bold**
  processed = processed.replace(/\*\*([^*]+)\*\*/g, '<strong class="font-bold text-white">$1</strong>');

  // 3. Italic: *italic*
  processed = processed.replace(/\*([^*]+)\*/g, '<em class="text-slate-300">$1</em>');

  // 4. Links: [text](url)
  processed = processed.replace(
    /\[(.*?)\]\(((?:https?:\/\/|\/|mailto:)[^\s"'>]+)\)/g,
    '<a href="$2" target="_blank" rel="noopener noreferrer" class="text-cyan-400 underline underline-offset-2 hover:text-cyan-300 font-medium">$1</a>'
  );

  // 5. Replace any emojis with proper inline SVGs
  for (const [emoji, svg] of Object.entries(EMOJI_TO_SVG)) {
    if (processed.includes(emoji)) {
      processed = processed.split(emoji).join(svg);
    }
  }

  // 6. Restore protected code spans
  return processed.replace(/___INLINE_CODE_(\d+)___/g, (_, idx) => codeSpans[Number(idx)] || "");
}

function renderSafeMarkdown(text: string): string {
  if (!text) return "";

  // 1. Extract <details>...</details> blocks to render interactive collapsible dropdowns
  const detailsBlocks: string[] = [];
  const textWithoutDetails = text.replace(
    /<details(?:\s+class="([^"]*)")?>\s*(?:<summary>(.*?)<\/summary>)?([\s\S]*?)<\/details>/gi,
    (_, _cls, summary, content) => {
      const idx = detailsBlocks.length;
      const cleanSummary = (summary || "Thinking & Query Execution").trim();
      const renderedContent = renderSafeMarkdown(content.trim());
      const detailsHtml = `
<details class="group my-2.5 border border-slate-800/80 bg-slate-950/60 hover:bg-slate-950/80 rounded-lg overflow-hidden transition-all duration-200 shadow-sm">
  <summary class="flex items-center justify-between cursor-pointer select-none px-3 py-2 text-[11px] font-medium text-slate-400 hover:text-cyan-300 bg-slate-900/40 hover:bg-slate-900/70 border-b border-transparent group-open:border-slate-800/70 transition-all">
    <span class="flex items-center gap-1.5 font-mono">
      <svg class="w-3.5 h-3.5 text-cyan-400 shrink-0" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5a3 3 0 1 0-5.997.125 4 4 0 0 0-2.526 5.77 4 4 0 0 0 .556 6.588A4 4 0 1 0 12 18Z"/><path d="M12 5a3 3 0 1 1 5.997.125 4 4 0 0 1 2.526 5.77 4 4 0 0 1-.556 6.588A4 4 0 1 1 12 18Z"/><path d="M15 13a4.5 4.5 0 0 1-3-4 4.5 4.5 0 0 1-3 4"/></svg>
      <span>${formatInline(escapeHtml(cleanSummary))}</span>
    </span>
    <span class="text-[10px] text-slate-500 font-mono group-open:rotate-180 transition-transform duration-200">▼</span>
  </summary>
  <div class="p-3 text-[11px] space-y-2 text-slate-300 font-normal">
    ${renderedContent}
  </div>
</details>`.trim();
      detailsBlocks.push(detailsHtml);
      return `\n\n___DETAILS_BLOCK_${idx}___\n\n`;
    }
  );

  // 2. Escape all raw HTML to neutralize XSS
  const escaped = escapeHtml(textWithoutDetails);

  // 3. Process block elements line by line
  const lines = escaped.split(/\r?\n/);
  const output: string[] = [];
  let inUl = false;
  let inOl = false;

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];

    // Details block placeholder
    const detailsMatch = line.trim().match(/^___DETAILS_BLOCK_(\d+)___$/);
    if (detailsMatch) {
      if (inUl) {
        output.push("</ul>");
        inUl = false;
      }
      if (inOl) {
        output.push("</ol>");
        inOl = false;
      }
      const idx = Number(detailsMatch[1]);
      output.push(detailsBlocks[idx] || "");
      continue;
    }

    // Markdown Table parsing (consecutive lines starting & ending with |)
    if (line.trim().startsWith("|") && line.trim().endsWith("|")) {
      const tableLines: string[] = [line.trim()];
      while (
        i + 1 < lines.length &&
        lines[i + 1].trim().startsWith("|") &&
        lines[i + 1].trim().endsWith("|")
      ) {
        i++;
        tableLines.push(lines[i].trim());
      }
      if (tableLines.length >= 2 && /^\|\s*[-:]+/.test(tableLines[1])) {
        if (inUl) {
          output.push("</ul>");
          inUl = false;
        }
        if (inOl) {
          output.push("</ol>");
          inOl = false;
        }

        const headerCells = tableLines[0]
          .split("|")
          .slice(1, -1)
          .map((c) => c.trim());
        const bodyRows = tableLines.slice(2).map((rowStr) =>
          rowStr
            .split("|")
            .slice(1, -1)
            .map((c) => c.trim())
        );

        let tableHtml =
          '<div class="overflow-x-auto my-2 rounded border border-slate-800/80 bg-slate-950/70 shadow-sm">';
        tableHtml += '<table class="w-full text-left text-[11px] font-mono border-collapse">';
        tableHtml += '<thead><tr class="border-b border-slate-800 bg-slate-900/90 text-cyan-300">';
        headerCells.forEach((cell) => {
          tableHtml += `<th class="px-3 py-1.5 font-semibold text-[10px] tracking-wider uppercase text-slate-300">${formatInline(
            cell
          )}</th>`;
        });
        tableHtml += "</tr></thead>";
        tableHtml += '<tbody class="divide-y divide-slate-800/60 text-slate-300">';
        bodyRows.forEach((row) => {
          tableHtml += '<tr class="hover:bg-slate-900/40 transition-colors">';
          row.forEach((cell) => {
            tableHtml += `<td class="px-3 py-1.5 text-slate-200">${formatInline(cell)}</td>`;
          });
          tableHtml += "</tr>";
        });
        tableHtml += "</tbody></table></div>";
        output.push(tableHtml);
        continue;
      }
    }

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
      const headingText = line.slice(4).trim();
      let iconSvg = "";
      if (headingText.includes("Welcome to OrgBridge AI") || headingText.includes("Brain")) {
        iconSvg = EMOJI_TO_SVG["🧠"];
      } else if (
        headingText.includes("Live Graph Mutation") ||
        headingText.includes("Policy Alignment") ||
        headingText.includes("Real-Time") ||
        headingText.includes("Alignment Implemented")
      ) {
        iconSvg = EMOJI_TO_SVG["⚡"];
      } else if (headingText.includes("Organizational Silo")) {
        iconSvg = `<svg class="inline-block w-4 h-4 text-cyan-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="12 2 2 7 12 12 22 7 12 2"/><polyline points="2 17 12 22 22 17"/><polyline points="2 12 12 17 22 12"/></svg>`;
      } else if (headingText.includes("Policy & Compliance Conflicts")) {
        iconSvg = `<svg class="inline-block w-4 h-4 text-red-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`;
      } else if (headingText.includes("Redundant Microservices")) {
        iconSvg = `<svg class="inline-block w-4 h-4 text-green-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="18" cy="18" r="3"/><circle cx="6" cy="6" r="3"/><path d="M6 21V9a9 9 0 0 0 9 9"/></svg>`;
      } else if (headingText.includes("Decision Lineage")) {
        iconSvg = `<svg class="inline-block w-4 h-4 text-amber-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z"/><polyline points="14 2 14 8 20 8"/></svg>`;
      } else if (headingText.includes("Warm Introduction Path")) {
        iconSvg = `<svg class="inline-block w-4 h-4 text-cyan-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76"/></svg>`;
      } else if (headingText.includes("Top SME Counterpart")) {
        iconSvg = `<svg class="inline-block w-4 h-4 text-blue-400 align-text-bottom mr-1" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/></svg>`;
      } else if (headingText.includes("Dynamic FalkorDB Query Result")) {
        iconSvg = EMOJI_TO_SVG["🔍"];
      }

      output.push(
        `<h3 class="flex items-start gap-2 font-bold text-cyan-400 text-sm mt-2 mb-1">` +
          (iconSvg ? `<span class="shrink-0 mt-0.5 flex items-center">${iconSvg}</span>` : "") +
          `<span class="flex-1 leading-snug">${formatInline(headingText)}</span>` +
        `</h3>`
      );
      continue;
    }
    if (line.startsWith("#### ")) {
      const headingText = line.slice(5).trim();
      let subIcon = "";
      if (
        headingText.toLowerCase().includes("critical") ||
        headingText.toLowerCase().includes("conflict") ||
        headingText.toLowerCase().includes("error") ||
        headingText.toLowerCase().includes("warning")
      ) {
        subIcon = EMOJI_TO_SVG["⚠️"];
      } else if (
        headingText.toLowerCase().includes("cross-border") ||
        headingText.toLowerCase().includes("integrated")
      ) {
        subIcon = EMOJI_TO_SVG["🔗"];
      }
      output.push(
        `<h4 class="flex items-start gap-1.5 font-semibold text-slate-100 text-xs mt-1.5 mb-0.5">` +
          (subIcon ? `<span class="shrink-0 mt-0.5 flex items-center">${subIcon}</span>` : "") +
          `<span class="flex-1 leading-snug">${formatInline(headingText)}</span>` +
        `</h4>`
      );
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
  let finalHtml = output.join("");
  finalHtml = finalHtml.replace(/<p[^>]*>___DETAILS_BLOCK_(\d+)___<\/p>/g, (_, idx) => detailsBlocks[Number(idx)] || "");
  finalHtml = finalHtml.replace(/___DETAILS_BLOCK_(\d+)___/g, (_, idx) => detailsBlocks[Number(idx)] || "");
  return finalHtml;
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
          toolName: "error",
          text: `**Query Error**: ${err.message || err}`,
          timestamp: "Error",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const handleLiveMutation = async (
    action: "resolve-auth" | "resolve-retention" | "merge-teams" | "reset-demo",
    promptText: string
  ) => {
    if (isLoading) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: promptText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res = await mutateGraph(action);
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

      const agentMsg: Message = {
        id: (Date.now() + 1).toString(),
        sender: "agent",
        text: `### Real-Time Policy Alignment Implemented\n\n` +
              `**Decision**: ${friendlyDecision}\n\n` +
              `**Impact**: ${res.resolution_summary || res.message}\n\n` +
              `> *Enterprise knowledge updated in real-time. Verified as of ${res.timestamp || "now"}.*`,
        toolName: "live_mutation",
        subgraph: res.subgraph,
        timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
      };
      setMessages((prev) => [...prev, agentMsg]);

      // Re-fetch or update the full graph from FalkorDB so main canvas reflects mutations
      if (action === "reset-demo") {
        // If viewing merged_brain, pass res.subgraph directly; if isolated tenant, re-fetch that tenant's baseline
        if (selectedGraph === "merged_brain" && res.subgraph) {
          if (onFullGraphRefresh) {
            await onFullGraphRefresh(res.subgraph);
          }
        } else if (onFullGraphRefresh) {
          await onFullGraphRefresh();
        }
        onSubgraphUpdate(null);
      } else {
        // Await full graph refresh first so graphData contains the newly created unified:* nodes
        // before onSubgraphUpdate triggers active subgraph isolation and inspector selection.
        if (onFullGraphRefresh) {
          await onFullGraphRefresh();
        }
        if (res.subgraph) {
          onSubgraphUpdate(res.subgraph);
        }
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          toolName: "error",
          text: `**Mutation Error**: ${err.message || err}`,
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

    const userMsg: Message = {
      id: Date.now().toString(),
      sender: "user",
      text: userText,
      timestamp: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };

    setMessages((prev) => [...prev, userMsg]);
    setIsLoading(true);

    try {
      const res: ToolResponse = await chatWithAgent(userText, selectedGraph);
      onBackendHealthy?.();

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
      if (res.subgraph && res.subgraph.nodes?.length > 0) {
        onSubgraphUpdate(res.subgraph);
      }
    } catch (err: any) {
      setMessages((prev) => [
        ...prev,
        {
          id: (Date.now() + 1).toString(),
          sender: "agent",
          toolName: "error",
          text: `**Query Error**: ${err.message || err}`,
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

      {/* Executive Alignment Actions (Track 03 Hardening) */}
      <div className="p-3 bg-slate-950/70 border-b border-slate-800/80">
        <div className="flex items-center justify-between mb-2">
          <p className="text-[11px] font-semibold uppercase tracking-wider text-amber-400 flex items-center gap-1">
            <Zap className="w-3.5 h-3.5 text-amber-400" />
            Executive Alignment Actions (Track 03)
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
                    <div
                      className="space-y-1 break-words text-red-200 flex-1 leading-relaxed"
                      dangerouslySetInnerHTML={{
                        __html: renderSafeMarkdown(m.text.replace(/^⚠️\s*/, "")),
                      }}
                    />
                  </div>
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
