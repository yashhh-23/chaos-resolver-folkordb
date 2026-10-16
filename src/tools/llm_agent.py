"""Groq Llama-3.3-70B Autonomous Agent & Schema-Constrained Text-to-Cypher Engine.

Provides an LLM agent with tool calling over the 6 FalkorDB M&A tools,
plus schema-constrained dynamic text-to-Cypher query generation with strict
FalkorDB label/relationship contracts and query sanitization.
Falls back seamlessly to deterministic graph traversal when GROQ_API_KEY is unset.
"""

from typing import Dict, Any, List, Optional
import json
import re
from src.config import settings
from src.db.client import db_client
from src.utils.logger import logger
from src.schema.cypher_schema import sanitize_cypher_query, ALLOWED_LABELS, ALLOWED_RELATIONSHIPS
from src.tools.graph_tools import agent_tools, GraphAgentTools, ToolResult, Subgraph
from src.tools.mcp_server import MCP_TOOL_DEFINITIONS, execute_tool

try:
    from groq import Groq
except ImportError:
    Groq = None

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None


def get_live_graph_schema(graph_name: str) -> Dict[str, List[str]]:
    """Inspects live labels and relationship types directly from FalkorDB."""
    graph = db_client.get_graph(graph_name)
    labels = list(ALLOWED_LABELS)
    rel_types = list(ALLOWED_RELATIONSHIPS)

    try:
        lbl_res = graph.query("CALL db.labels()")
        if lbl_res and lbl_res.result_set:
            labels = [r[0] for r in lbl_res.result_set if r[0]]
    except Exception:
        pass

    try:
        rel_res = graph.query("CALL db.relationshipTypes()")
        if rel_res and rel_res.result_set:
            rel_types = [r[0] for r in rel_res.result_set if r[0]]
    except Exception:
        pass

    return {"labels": labels, "relationship_types": rel_types}


class LLMAgent:
    """Autonomous agent powered by Groq Llama-3.3-70B (with OpenAI and offline deterministic fallbacks)."""

    def __init__(self, model: Optional[str] = None):
        self.model = model or settings.llm_model or "llama-3.3-70b-versatile"
        self.groq_client = None
        self.openai_client = None

        if settings.groq_api_key and Groq is not None:
            try:
                self.groq_client = Groq(api_key=settings.groq_api_key)
                logger.info(f"Initialized Groq LLMAgent with model {self.model}")
            except Exception as e:
                logger.warning(f"Failed to initialize Groq client: {e}")

        if not self.groq_client and settings.openai_api_key and OpenAI is not None:
            try:
                self.openai_client = OpenAI(api_key=settings.openai_api_key)
                self.model = "gpt-4o"
                logger.info("Initialized OpenAI fallback LLMAgent with model gpt-4o")
            except Exception as e:
                logger.warning(f"Failed to initialize OpenAI client: {e}")

    def is_available(self) -> bool:
        """Returns True if a live LLM client (Groq or OpenAI) is configured."""
        return self.groq_client is not None or self.openai_client is not None

    def _get_tools_spec(self) -> List[Dict[str, Any]]:
        """Converts MCP tool definitions to standard OpenAI/Groq function calling format."""
        specs = []
        for tool in MCP_TOOL_DEFINITIONS:
            specs.append({
                "type": "function",
                "function": {
                    "name": tool["name"],
                    "description": tool["description"],
                    "parameters": tool.get("parameters", {"type": "object", "properties": {}}),
                },
            })

        # Add 7th tool: Schema-constrained ad-hoc Cypher execution
        specs.append({
            "type": "function",
            "function": {
                "name": "run_schema_constrained_cypher",
                "description": "Executes a sanitized, read-only Cypher query against FalkorDB for ad-hoc analytical questions. Query must only use verified schema labels and relationships.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Read-only Cypher query (e.g. 'MATCH (p:Person)-[:OWNS]->(s:System) RETURN p.name, s.name LIMIT 10')",
                        },
                        "explanation": {
                            "type": "string",
                            "description": "Brief explanation of what the query calculates or discovers.",
                        },
                    },
                    "required": ["query"],
                },
            },
        })
        return specs

    def _execute_cypher(self, query: str, explanation: str, graph_name: str) -> ToolResult:
        """Executes a schema-constrained, sanitized Cypher query and formats the result."""
        # Enforce read-only constraint
        upper = query.upper()
        for forbidden in ["DROP", "DELETE", "DETACH", "CREATE", "SET", "MERGE", "REMOVE"]:
            if re.search(rf"\b{forbidden}\b", upper):
                return ToolResult(
                    tool_name="schema_constrained_cypher",
                    status="error",
                    text_answer=f"⚠️ **Security Violation**: Destructive or mutating Cypher statement `{forbidden}` is prohibited in text-to-Cypher.",
                    subgraph=Subgraph(),
                )

        sanitized = sanitize_cypher_query(query, max_hops=4, default_limit=25)
        graph = db_client.get_graph(graph_name)
        subgraph = Subgraph()

        try:
            res = graph.query(sanitized)
            rows = res.result_set
            headers = [h[1] if isinstance(h, tuple) else str(h) for h in res.header] if hasattr(res, "header") and res.header else []

            # Format tabular answer
            lines = [
                f"### 🔍 Dynamic FalkorDB Query Result\n",
                f"**Cypher**: `{sanitized}`\n",
                f"**Purpose**: *{explanation}*\n",
                f"**Returned**: {len(rows)} record(s)\n",
            ]

            if rows:
                if headers:
                    header_line = "| " + " | ".join(str(h) for h in headers) + " |"
                    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
                    lines.extend([header_line, sep_line])
                    for row in rows[:15]:
                        lines.append("| " + " | ".join(str(val) for val in row) + " |")
                else:
                    for row in rows[:15]:
                        lines.append(f"- {row}")
            else:
                lines.append("*Query returned 0 matching records in the graph.*")

            return ToolResult(
                tool_name="schema_constrained_cypher",
                text_answer="\n".join(lines),
                details={"query": sanitized, "row_count": len(rows)},
                subgraph=subgraph,
            )
        except Exception as e:
            logger.error(f"Error executing schema-constrained Cypher query: {e}")
            return ToolResult(
                tool_name="schema_constrained_cypher",
                status="error",
                text_answer=f"⚠️ **Cypher Execution Error**: {e}\nQuery attempted: `{sanitized}`",
                subgraph=subgraph,
            )

    def _fallback_deterministic_dispatch(self, user_prompt: str, graph_name: str) -> ToolResult:
        """Offline deterministic intent router when no LLM API key is present."""
        lower = user_prompt.lower()
        tools = GraphAgentTools(graph_name=graph_name)

        # 1. Silos (WCC)
        if any(k in lower for k in ["silo", "island", "isolated", "wcc", "component", "unconnected", "topology"]):
            return tools.detect_organizational_silos()

        # 2. Warm Intro Path
        if any(k in lower for k in ["intro", "connect", "path", "reach", "introduce", "warm"]):
            # Extract names if present
            between_match = re.search(r'(?:between|from)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:and|to)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)', user_prompt, re.I)
            if between_match:
                p_a, p_b = between_match.group(1).strip(), between_match.group(2).strip()
            else:
                p_a, p_b = "Aarav Mehta", "Diya Nair"
            return tools.get_warm_intro_path(person_a=p_a, person_b=p_b)

        # 3. Decision Lineage
        if any(k in lower for k in ["lineage", "why", "decision", "rfc", "origin", "history", "govern"]):
            sys_match = re.search(r'(?:for|system|of)\s+([A-Za-z0-9_-]+)', user_prompt, re.I)
            sys_name = sys_match.group(1).strip() if sys_match else "Gatekeeper-Auth"
            return tools.trace_decision_lineage(system_name=sys_name)

        # 4. Expert Counterpart
        if any(k in lower for k in ["expert", "who", "sme", "counterpart", "specialist", "lead", "engineer"]):
            company = "Vaultly"
            if "finpay" in lower:
                company = "FinPay"
            topic = "Authentication"
            if "retention" in lower or "audit" in lower:
                topic = "Data Retention"
            elif "ledger" in lower or "balance" in lower:
                topic = "Ledger"
            elif "kyc" in lower:
                topic = "KYC"
            return tools.find_counterpart_expert(topic=topic, company=company)

        # 5. Policy Conflicts
        if any(k in lower for k in ["conflict", "policy", "retention", "compliance", "clash", "contradiction"]):
            domain = None
            if "auth" in lower:
                domain = "Authentication"
            elif "retention" in lower:
                domain = "Data Retention"
            return tools.detect_policy_conflicts(domain=domain)

        # 6. Redundant Systems (default)
        return tools.find_redundant_systems()

    def chat(self, user_prompt: str, graph_name: Optional[str] = None) -> ToolResult:
        """Processes a natural language prompt via Groq Llama-3.3-70B or deterministic fallback."""
        target_graph = graph_name or settings.graph_merged

        if not self.is_available():
            logger.info("GROQ_API_KEY unset; delegating to deterministic graph tools.")
            return self._fallback_deterministic_dispatch(user_prompt, target_graph)

        # Retrieve dynamic live schema
        schema = get_live_graph_schema(target_graph)
        system_prompt = (
            f"You are OrgBridge AI (The M&A Chaos Resolver), an autonomous corporate brain powered by FalkorDB.\n"
            f"Live FalkorDB Graph Schema for tenant '{target_graph}':\n"
            f"- Allowed Labels: {', '.join(schema['labels'])}\n"
            f"- Allowed Relationships: {', '.join(schema['relationship_types'])}\n\n"
            f"Tools Available:\n"
            f"1. find_counterpart_expert: Finds SMEs across companies via PageRank and incident lineage.\n"
            f"2. detect_policy_conflicts: Detects regulatory/security policy contradictions.\n"
            f"3. find_redundant_systems: Discovers duplicate microservices via hybrid embeddings & API calls.\n"
            f"4. trace_decision_lineage: Traces architecture decisions, opposing decisions, and RFC sources.\n"
            f"5. get_warm_intro_path: Discovers shortest organizational bridges between engineers.\n"
            f"6. detect_organizational_silos: Computes Weakly Connected Components (WCC) to isolate disconnected islands.\n"
            f"7. run_schema_constrained_cypher: Executes ad-hoc read-only Cypher using only verified labels.\n\n"
            f"Always prioritize tool calls to answer questions with verifiable graph data."
        )

        tools = self._get_tools_spec()
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            client = self.groq_client or self.openai_client
            response = client.chat.completions.create(
                model=self.model,
                messages=messages,
                tools=tools,
                tool_choice="auto",
                temperature=0.1,
            )

            msg = response.choices[0].message

            # Handle function calling
            if msg.tool_calls:
                tool_call = msg.tool_calls[0]
                fn_name = tool_call.function.name
                fn_args = json.loads(tool_call.function.arguments or "{}")

                logger.info(f"LLM Agent called tool '{fn_name}' with args {fn_args}")

                if fn_name == "run_schema_constrained_cypher":
                    return self._execute_cypher(
                        query=fn_args.get("query", ""),
                        explanation=fn_args.get("explanation", "Dynamic schema-constrained query"),
                        graph_name=target_graph,
                    )
                else:
                    return execute_tool(fn_name, fn_args)

            # Direct response
            return ToolResult(
                tool_name="llm_agent",
                text_answer=msg.content or "No response generated.",
                details={"model": self.model},
                subgraph=Subgraph(),
            )

        except Exception as e:
            logger.error(f"Error during LLM agent invocation: {e}. Falling back to deterministic dispatcher.")
            return self._fallback_deterministic_dispatch(user_prompt, target_graph)


llm_agent = LLMAgent()
