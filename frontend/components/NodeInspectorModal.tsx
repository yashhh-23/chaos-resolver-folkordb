"use client";

import React from "react";
import { X, ExternalLink, ShieldCheck, Cpu, User, FileText, CheckCircle2 } from "lucide-react";
import { GraphNode } from "@/lib/api";

interface NodeInspectorModalProps {
  node: GraphNode | null;
  onClose: () => void;
}

export default function NodeInspectorModal({ node, onClose }: NodeInspectorModalProps) {
  if (!node) return null;

  const isFinPay = node.company_origin === "FinPay";
  const isVaultly = node.company_origin === "Vaultly";

  const getIcon = () => {
    switch (node.label) {
      case "Person":
        return <User className="w-5 h-5 text-blue-400" />;
      case "System":
        return <Cpu className="w-5 h-5 text-emerald-400" />;
      case "Policy":
      case "Decision":
        return <ShieldCheck className="w-5 h-5 text-amber-400" />;
      default:
        return <FileText className="w-5 h-5 text-purple-400" />;
    }
  };

  const props = node.properties || {};

  return (
    <div className="absolute bottom-4 right-4 z-20 w-80 md:w-96 bg-slate-900/95 backdrop-blur-md border border-slate-700/80 rounded-xl p-4 shadow-2xl text-xs text-slate-200 transition-all duration-200 transform translate-y-0 opacity-100 ease-out">
      <div className="flex items-start justify-between border-b border-slate-800 pb-3 mb-3">
        <div className="flex items-center gap-2">
          <div className="p-2 rounded-lg bg-slate-800 border border-slate-700">
            {getIcon()}
          </div>
          <div>
            <h3 className="font-bold text-sm text-white">{node.name}</h3>
            <div className="flex items-center gap-1.5 mt-0.5">
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 bg-slate-800 rounded text-slate-400 border border-slate-700">
                {node.label}
              </span>
              <span
                className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                  isFinPay
                    ? "bg-blue-600/30 text-blue-300 border border-blue-500/30"
                    : isVaultly
                    ? "bg-orange-600/30 text-orange-300 border border-orange-500/30"
                    : "bg-purple-600/30 text-purple-300 border border-purple-500/30"
                }`}
              >
                {node.company_origin}
              </span>
            </div>
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-slate-400 hover:text-slate-100 p-1 hover:bg-slate-800 rounded transition"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="space-y-2 max-h-60 overflow-y-auto pr-1">
        <div className="grid grid-cols-3 gap-1 py-1 border-b border-slate-800/60">
          <span className="text-slate-400 font-medium">Node ID</span>
          <span className="col-span-2 font-mono text-[11px] text-slate-300 break-all">{node.id}</span>
        </div>

        {Object.entries(props).map(([k, v]) => {
          if (k === "embedding" || v === null || v === undefined) return null;
          return (
            <div key={k} className="grid grid-cols-3 gap-1 py-1 border-b border-slate-800/40">
              <span className="text-slate-400 font-medium capitalize">{k.replace(/_/g, " ")}</span>
              <span className="col-span-2 text-slate-200 break-words font-sans">
                {typeof v === "object" ? JSON.stringify(v) : String(v)}
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
