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
                try:
                    available = {m.id for m in self.groq_client.models.list().data}
                    candidates = [
                        self.model,
                        "qwen/qwen3.8-27b",
                        "openai/gpt-oss-120b",
                        "openai/gpt-oss-20b",
                        "llama-3.3-70b-versatile",
                        "llama-3.1-70b-versatile",
                        "llama3-70b-8192",
                    ]
                    for candidate in candidates:
                        if candidate in available:
                            self.model = candidate
                            break
                except Exception as model_err:
                    logger.debug("Could not query Groq models list: %s", model_err)

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
                            "description": "Read-only Cypher query. Example: 'MATCH (p:Person) WHERE toLower(p.name) CONTAINS \"aarav\" OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team) RETURN p.name, p.role, t.name LIMIT 10'. Always return informative properties like p.name, p.role, p.department, and t.name to clearly answer the user's question.",
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

    def _execute_cypher(
        self,
        query: str,
        explanation: str,
        graph_name: str,
        user_prompt: str = "",
    ) -> ToolResult:
        """Executes a schema-constrained, sanitized Cypher query and formats the result."""
        # Enforce read-only constraint
        upper = query.upper()
        for forbidden in ["DROP", "DELETE", "DETACH", "CREATE", "SET", "MERGE", "REMOVE"]:
            if re.search(rf"\b{forbidden}\b", upper):
                return ToolResult(
                    tool_name="schema_constrained_cypher",
                    status="error",
                    text_answer=f"**Security Violation**: Destructive or mutating Cypher statement `{forbidden}` is prohibited in text-to-Cypher.",
                    subgraph=Subgraph(),
                )

        sanitized = sanitize_cypher_query(query, max_hops=4, default_limit=25)
        graph = db_client.get_graph(graph_name)
        subgraph = Subgraph()

        try:
            res = graph.query(sanitized)
            rows = res.result_set
            headers = [h[1] if isinstance(h, (tuple, list)) and len(h) > 1 else str(h) for h in res.header] if hasattr(res, "header") and res.header else []

            # 1. Synthesize concise executive user-friendly answer
            friendly_answer = ""
            if rows:
                if self.is_available() and user_prompt:
                    try:
                        client = self.groq_client or self.openai_client
                        dict_rows = [
                            {str(headers[i] if i < len(headers) else f"col_{i}"): val for i, val in enumerate(row)}
                            for row in rows[:10]
                        ]
                        synth_prompt = (
                            f"User Question: '{user_prompt}'\n"
                            f"Database Records: {json.dumps(dict_rows, default=str)}\n\n"
                            f"Provide a direct, natural, executive 1-sentence answer to the user's question based on these records. "
                            f"Do NOT mention 'database', 'Cypher', 'query', 'returned', or 'rows'. "
                            f"Directly state the answer (e.g. \"Aarav Mehta's role is Staff Security Engineer in the FinPay Security Architecture team.\")."
                        )
                        synth_res = client.chat.completions.create(
                            model=self.model,
                            messages=[
                                {
                                    "role": "system",
                                    "content": "You are OrgBridge AI, an executive assistant synthesizing concise, natural answers from verified enterprise graph data.",
                                },
                                {"role": "user", "content": synth_prompt},
                            ],
                            temperature=0.1,
                            max_tokens=150,
                        )
                        friendly_answer = (synth_res.choices[0].message.content or "").strip()
                    except Exception as synth_err:
                        logger.debug("Failed to synthesize friendly Cypher answer with LLM: %s", synth_err)

                if not friendly_answer:
                    first_row = rows[0]
                    if headers and len(first_row) == len(headers):
                        row_map = {str(h): first_row[idx] for idx, h in enumerate(headers)}
                        name = row_map.get("p.name") or row_map.get("name")
                        role = row_map.get("p.role") or row_map.get("role") or row_map.get("t.name")
                        if name and role:
                            friendly_answer = f"{name}'s role is {role}."
                        else:
                            friendly_answer = f"Found {len(rows)} record(s) matching your request."
                    else:
                        friendly_answer = f"Found {len(rows)} record(s) matching your request."
            else:
                friendly_answer = f"No matching records found in the organization graph for '{user_prompt or explanation}'."

            # 2. Format technical details under collapsible Thinking dropdown
            thinking_lines = [
                "<details class=\"thinking-dropdown\">",
                "<summary>Thinking & Query Execution</summary>\n",
                f"**Cypher**: `{sanitized}`\n",
                f"**Purpose**: *{explanation}*\n",
                f"**Returned**: {len(rows)} record(s)\n",
            ]

            if rows:
                if headers:
                    header_line = "| " + " | ".join(str(h) for h in headers) + " |"
                    sep_line = "| " + " | ".join("---" for _ in headers) + " |"
                    thinking_lines.extend([header_line, sep_line])
                    for row in rows[:15]:
                        thinking_lines.append("| " + " | ".join(str(val) for val in row) + " |")
                else:
                    for row in rows[:15]:
                        thinking_lines.append(f"- {row}")
            else:
                thinking_lines.append("*Query returned 0 matching records in the graph.*")

            thinking_lines.append("</details>")

            full_text = f"{friendly_answer}\n\n" + "\n".join(thinking_lines)

            return ToolResult(
                tool_name="schema_constrained_cypher",
                text_answer=full_text,
                details={"query": sanitized, "row_count": len(rows), "summary": friendly_answer},
                subgraph=subgraph,
            )
        except Exception as e:
            logger.error(f"Error executing schema-constrained Cypher query: {e}")
            return ToolResult(
                tool_name="schema_constrained_cypher",
                status="error",
                text_answer=f"**Cypher Execution Error**: {e}\nQuery attempted: `{sanitized}`",
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
            f"You are OrgBridge AI (The M&A Chaos Resolver), an autonomous corporate brain running on Groq LPU inference and powered by FalkorDB.\n"
            f"If asked about your architecture or whether Groq is used, confirm that you run on Groq for ultra-fast LPU inference and function calling, while all enterprise knowledge graphs and vector embeddings are stored and queried in FalkorDB.\n\n"
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
                        user_prompt=user_prompt,
                    )
                else:
                    return execute_tool(fn_name, fn_args, graph_name=target_graph)

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
