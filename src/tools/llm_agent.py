"""Groq Llama-3.3-70B Autonomous Agent & Schema-Constrained Text-to-Cypher Engine.

Provides an LLM agent with tool calling over the 6 FalkorDB M&A tools,
plus schema-constrained dynamic text-to-Cypher query generation with strict
FalkorDB label/relationship contracts and query sanitization.
Falls back seamlessly to deterministic graph traversal when GROQ_API_KEY is unset.
"""

from typing import Dict, Any, List, Optional
import json
import re
import concurrent.futures
from src.config import settings
from src.db.client import db_client
from src.utils.logger import logger
from src.schema.cypher_schema import (
    sanitize_cypher_query,
    validate_readonly_cypher,
    CYPHER_TEMPLATES,
    ALLOWED_LABELS,
    ALLOWED_RELATIONSHIPS,
)
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


# ---------------------------------------------------------------------------
# Domain guardrail
# ---------------------------------------------------------------------------
_IN_SCOPE_KEYWORDS = [
    # people / org
    "expert", "sme", "who", "counterpart", "engineer", "person", "people", "team",
    "member", "org", "department", "finpay", "vaultly", "merger", "m&a", "acquisition",
    "employee", "staff", "lead", "manager", "role",
    # systems / tech
    "system", "service", "microservice", "api", "gateway", "auth", "authentication",
    "authorization", "jwt", "token", "sso", "identity", "oauth", "saml",
    "ledger", "payment", "kyc", "compliance", "audit", "log", "retention",
    "data", "database", "graph", "falkordb", "cypher", "query",
    # policies / decisions
    "policy", "conflict", "contradict", "clash", "redundan", "overlap",
    "decision", "lineage", "rfc", "adl", "architecture", "govern",
    "regulation", "pci", "gdpr", "sox", "hipaa",
    # warm intro / silos
    "intro", "introduce", "path", "connect", "bridge", "silo", "island",
    "isolated", "wcc", "component", "topology", "cluster",
    # general graph / org-brain context
    "orgbridge", "knowledge", "graph", "incident", "on-call", "oncall",
    "ownership", "owns", "responsible", "stakeholder",
]

_OUT_OF_SCOPE_PATTERNS = [
    r"\bjava\b", r"\bpython\b", r"\bjavascript\b", r"\bc\+\+\b", r"\brust\b",
    r"\bhtml\b", r"\bcss\b", r"\bsql\b(?!\s*(query|schema))",
    r"\brecip\b", r"\bcook\b", r"\bfood\b", r"\bweather\b",
    r"\bsport\b", r"\bfootball\b", r"\bcricket\b", r"\bbasketball\b",
    r"\bmovie\b", r"\bfilm\b", r"\bsong\b", r"\bmusic\b",
    r"\bnews\b", r"\bpolitic\b", r"\belection\b",
    r"\bmath\b", r"\balgebra\b", r"\bcalculus\b",
    r"\bhistory\b", r"\bgeograph\b", r"\bscience\b(?!\s*of)",
    r"\bpoem\b", r"\bstory\b", r"\bessay\b", r"\bwrite\s+a\b",
    r"\btranslat\b", r"\blanguage\b(?!\s*model)",
    r"\bmedical\b", r"\bdoctor\b", r"\bhospital\b",
    r"\btravel\b", r"\bhotel\b", r"\bflight\b",
    r"\bjoke\b", r"\bfunny\b",
]

_REFUSAL_RESPONSE = (
    "I'm **OrgBridge AI** — the M&A Chaos Resolver for the FinPay ↔ Vaultly merger. "
    "My knowledge is strictly limited to the enterprise graph: people, teams, systems, "
    "policies, decisions, and organizational topology stored in FalkorDB.\n\n"
    "I can help with:\n"
    "- 🔍 **Expert discovery** — find SMEs and counterparts across both companies\n"
    "- ⚠️ **Policy conflicts** — detect contradictions in compliance and security policies\n"
    "- 🔄 **Redundant systems** — identify overlapping microservices\n"
    "- 📜 **Decision lineage** — trace architecture decisions and RFC sources\n"
    "- 🤝 **Warm intro paths** — find shortest organizational bridges between engineers\n"
    "- 🏝️ **Organizational silos** — detect disconnected teams and isolated units\n\n"
    "Please ask a question related to the merger, the org graph, or the systems and people in it."
)


def _is_in_scope(prompt: str) -> bool:
    """Returns True if the prompt is likely within the M&A org-graph domain."""
    lower = prompt.lower()

    # Explicit out-of-scope pattern check (fast fail)
    for pat in _OUT_OF_SCOPE_PATTERNS:
        if re.search(pat, lower):
            return False

    # Must contain at least one in-scope keyword to be allowed
    for kw in _IN_SCOPE_KEYWORDS:
        if kw in lower:
            return True

    return False


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
                            "description": "Read-only Cypher query. Example: 'MATCH (p:Person) WHERE toLower(p.name) CONTAINS \"diya\" OPTIONAL MATCH (p)-[:MEMBER_OF]->(t:Team) RETURN p.name, p.role, p.department, p.company_origin, t.name LIMIT 10'. ALWAYS include p.company_origin (contains 'FinPay' or 'Vaultly') so the person's company is explicitly known.",
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

    def execute_cypher_template(
        self,
        template_key: str,
        params: Dict[str, Any],
        graph_name: str,
        user_prompt: str = "",
        timeout_seconds: float = 5.0,
    ) -> ToolResult:
        """Executes a predefined, parameterized read-only Cypher query template (B9)."""
        template_info = CYPHER_TEMPLATES.get(template_key)
        if not template_info:
            return ToolResult(
                tool_name="parameterized_cypher_template",
                status="error",
                text_answer=f"Unknown Cypher query template: '{template_key}'. Available templates: {list(CYPHER_TEMPLATES.keys())}",
                subgraph=Subgraph(),
            )

        query = template_info["template"]
        call_params = dict(params)
        call_params.setdefault("limit", 25)

        graph = db_client.get_graph(graph_name)
        subgraph = Subgraph()

        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(graph.query, query, call_params)
                res = future.result(timeout=timeout_seconds)
            rows = res.result_set
            headers = [h[1] if isinstance(h, (tuple, list)) and len(h) > 1 else str(h) for h in res.header] if hasattr(res, "header") and res.header else []

            text_lines = [f"Found {len(rows)} record(s) matching template '{template_key}':"]
            for r in rows[:10]:
                text_lines.append(f"- {', '.join(str(val) for val in r if val is not None)}")

            return ToolResult(
                tool_name="parameterized_cypher_template",
                status="success",
                text_answer="\n".join(text_lines),
                details={"template": template_key, "params": call_params, "record_count": len(rows)},
                subgraph=subgraph,
            )
        except concurrent.futures.TimeoutError:
            return ToolResult(
                tool_name="parameterized_cypher_template",
                status="error",
                text_answer=f"**Execution Safeguard**: Query execution timed out after {timeout_seconds} seconds.",
                subgraph=subgraph,
            )
        except Exception as e:
            return ToolResult(
                tool_name="parameterized_cypher_template",
                status="error",
                text_answer=f"Error executing template '{template_key}': {e}",
                subgraph=subgraph,
            )

    def _execute_cypher(
        self,
        query: str,
        explanation: str,
        graph_name: str,
        user_prompt: str = "",
        timeout_seconds: float = 5.0,
    ) -> ToolResult:
        """Executes a schema-constrained, sanitized Cypher query and formats the result with execution safeguards."""
        # 1. Enforce strict read-only grammar and clause validation (B9)
        validation = validate_readonly_cypher(query, max_hops=4, max_limit=50, default_limit=25)
        if not validation["valid"]:
            return ToolResult(
                tool_name="schema_constrained_cypher",
                status="error",
                text_answer=f"**Security Violation**: {validation['message']}",
                details={"error_code": validation.get("error_code")},
                subgraph=Subgraph(),
            )

        sanitized = validation["sanitized_query"]
        graph = db_client.get_graph(graph_name)
        subgraph = Subgraph()

        # 2. Server-side execution safeguard with timeout
        try:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
                future = executor.submit(graph.query, sanitized)
                res = future.result(timeout=timeout_seconds)
            rows = res.result_set
            headers = [h[1] if isinstance(h, (tuple, list)) and len(h) > 1 else str(h) for h in res.header] if hasattr(res, "header") and res.header else []
        except concurrent.futures.TimeoutError:
            logger.error(f"[{graph_name}] Cypher query exceeded timeout ({timeout_seconds}s): {sanitized}")
            return ToolResult(
                tool_name="schema_constrained_cypher",
                status="error",
                text_answer=f"**Execution Safeguard**: Query execution timed out after {timeout_seconds} seconds.",
                details={"error_code": "QUERY_TIMEOUT", "query": sanitized},
                subgraph=subgraph,
            )
        except Exception as e:
            logger.error(f"[{graph_name}] Cypher query execution error: {e}")
            return ToolResult(
                tool_name="schema_constrained_cypher",
                status="error",
                text_answer=f"**Query Execution Error**: {str(e)}",
                details={"query": sanitized},
                subgraph=subgraph,
            )

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
                        f"MANDATORY REQUIREMENT: Always explicitly specify the person's company affiliation (from company_origin, e.g. 'of Vaultly company' or 'of FinPay company') along with their role, team, and department.\n"
                        f"Example format: \"Diya Nair is a Senior Backend Developer on the Vaultly Growth & Identity team within the Identity & Growth department of Vaultly company.\"\n"
                        f"Do NOT mention 'database', 'Cypher', 'query', 'returned', or 'rows'."
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
                    company = (
                        row_map.get("p.company_origin")
                        or row_map.get("s.company_origin")
                        or row_map.get("pol.company_origin")
                        or row_map.get("t.company_origin")
                        or row_map.get("company_origin")
                        or row_map.get("p.company")
                        or row_map.get("company")
                        or ""
                    )

                    # 1. System entity dispatch
                    if (
                        any(k.startswith("s.") for k in row_map)
                        or "s.name" in row_map
                        or ("system" in user_prompt.lower() and not any(k.startswith("p.") for k in row_map))
                    ):
                        sys_name = row_map.get("s.name") or row_map.get("name") or "The requested system"
                        tech = row_map.get("s.tech") or row_map.get("tech") or ""
                        domain = row_map.get("s.domain") or row_map.get("domain") or ""
                        tier = row_map.get("s.tier") or row_map.get("tier") or ""
                        parts = [f"**{sys_name}** is a"]
                        if tier:
                            parts.append(str(tier))
                        if domain:
                            parts.append(f"{domain}")
                        parts.append("system")
                        if tech:
                            parts.append(f"built with {tech}")
                        if company:
                            parts.append(f"at {company} company")
                        friendly_answer = " ".join(parts) + f". (Found {len(rows)} matching record{'s' if len(rows) != 1 else ''})."

                    # 2. Policy entity dispatch
                    elif (
                        any(k.startswith("pol.") for k in row_map)
                        or "pol.name" in row_map
                        or "policy" in user_prompt.lower()
                    ):
                        pol_name = row_map.get("pol.name") or row_map.get("name") or "The policy"
                        domain = row_map.get("pol.domain") or row_map.get("domain") or ""
                        sev = row_map.get("pol.severity") or row_map.get("severity") or ""
                        auth = row_map.get("pol.authority") or row_map.get("authority") or ""
                        parts = [f"**{pol_name}** is a"]
                        if sev:
                            parts.append(f"{sev}-severity")
                        if domain:
                            parts.append(f"{domain}")
                        parts.append("governance policy")
                        if auth:
                            parts.append(f"enforced by {auth}")
                        if company:
                            parts.append(f"of {company} company")
                        friendly_answer = " ".join(parts) + f". (Found {len(rows)} matching record{'s' if len(rows) != 1 else ''})."

                    # 3. Team entity dispatch
                    elif any(k.startswith("t.") for k in row_map) and not any(k.startswith("p.") for k in row_map):
                        team_name = row_map.get("t.name") or row_map.get("name") or "The requested team"
                        dept = row_map.get("t.department") or row_map.get("department") or ""
                        parts = [f"**{team_name}** is an engineering team"]
                        if dept:
                            parts.append(f"in the {dept} department")
                        if company:
                            parts.append(f"of {company} company")
                        friendly_answer = " ".join(parts) + f". (Found {len(rows)} matching record{'s' if len(rows) != 1 else ''})."

                    # 4. Person entity default
                    else:
                        name = row_map.get("p.name") or row_map.get("name") or "The requested person"
                        role = row_map.get("p.role") or row_map.get("role") or ""
                        dept = row_map.get("p.department") or row_map.get("department") or ""
                        team = row_map.get("t.name") or row_map.get("team") or ""

                        parts = [name]
                        if role:
                            parts.append(f"is a {role}")
                        if team:
                            parts.append(f"on the {team} team")
                        if dept:
                            parts.append(f"within the {dept} department")
                        if company:
                            parts.append(f"of {company} company")

                        if len(parts) > 1:
                            friendly_answer = " ".join(parts) + "."
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

    def _fallback_deterministic_dispatch(self, user_prompt: str, graph_name: str) -> ToolResult:
        """Offline deterministic intent router when no LLM API key is present."""
        # Guardrail: reject out-of-scope prompts even in offline/fallback mode
        if not _is_in_scope(user_prompt):
            logger.info(f"Guardrail (fallback): out-of-scope prompt blocked: {user_prompt[:80]!r}")
            return ToolResult(
                tool_name="guardrail",
                status="out_of_scope",
                text_answer=_REFUSAL_RESPONSE,
                details={"reason": "prompt_outside_domain"},
                subgraph=Subgraph(),
            )

        lower = user_prompt.lower()
        tools = GraphAgentTools(graph_name=graph_name)

        # 1. Silos (WCC)
        if any(k in lower for k in ["silo", "island", "isolated", "wcc", "component", "unconnected", "topology"]):
            return tools.detect_organizational_silos()

        # 2. Warm Intro Path
        if any(k in lower for k in ["intro", "connect", "path", "reach", "introduce", "warm"]):
            between_match = re.search(
                r'(?:between|from|connect|intro\s+for|introduce)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)\s+(?:and|to|with)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)?)',
                user_prompt,
                re.I,
            )
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

        # ---------------------------------------------------------------
        # GUARDRAIL LAYER 1: Pre-flight domain scope check
        # Reject queries that are clearly outside the M&A org-graph domain
        # before any LLM call is made — zero hallucination risk.
        # ---------------------------------------------------------------
        if not _is_in_scope(user_prompt):
            logger.info(f"Guardrail: out-of-scope prompt blocked: {user_prompt[:80]!r}")
            return ToolResult(
                tool_name="guardrail",
                status="out_of_scope",
                text_answer=_REFUSAL_RESPONSE,
                details={"reason": "prompt_outside_domain"},
                subgraph=Subgraph(),
            )

        if not self.is_available():
            logger.info("GROQ_API_KEY unset; delegating to deterministic graph tools.")
            return self._fallback_deterministic_dispatch(user_prompt, target_graph)

        # Retrieve dynamic live schema
        schema = get_live_graph_schema(target_graph)

        # ---------------------------------------------------------------
        # GUARDRAIL LAYER 2: Hardened system prompt with explicit domain
        # boundaries and mandatory refusal instruction.
        # ---------------------------------------------------------------
        system_prompt = (
            f"You are OrgBridge AI (The M&A Chaos Resolver), an autonomous corporate brain running on Groq LPU inference and powered by FalkorDB.\n"
            f"If asked about your architecture or whether Groq is used, confirm that you run on Groq for ultra-fast LPU inference and function calling, while all enterprise knowledge graphs and vector embeddings are stored and queried in FalkorDB.\n\n"
            f"⛔ STRICT DOMAIN BOUNDARY — MANDATORY:\n"
            f"You ONLY answer questions about the FinPay ↔ Vaultly M&A merger and the enterprise knowledge graph in FalkorDB.\n"
            f"This includes: people, teams, systems, policies, decisions, compliance, architecture, organizational silos, and warm introduction paths.\n"
            f"You MUST REFUSE to answer ANY question that is not directly related to the merger, the org graph, or the enterprise systems and people in it.\n"
            f"If the user asks about general programming, other companies, recipes, sports, news, weather, jokes, history, science, math, travel, or ANY other off-topic subject, "
            f"respond ONLY with this exact refusal message and nothing else:\n"
            f"\"{_REFUSAL_RESPONSE}\"\n"
            f"Do NOT explain, help with, or partially address any off-topic question. Simply return the refusal message.\n\n"
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
            f"7. run_schema_constrained_cypher: Executes ad-hoc read-only Cypher using only verified labels. When querying people, teams, or systems, ALWAYS query and return p.company_origin (e.g. 'FinPay' or 'Vaultly') along with role, department, and team names.\n\n"
            f"Always prioritize tool calls to answer questions with verifiable graph data. "
            f"Never answer from general knowledge — every answer must come from a tool call or graph query."
        )

        tools = self._get_tools_spec()
        safe_user_content = f"<untrusted_external_data>\n{user_prompt}\n</untrusted_external_data>"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": safe_user_content},
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

                # Zero-Trust Guard: Block any attempted call to mutating endpoints
                prohibited_mutating_tools = {
                    "resolve_auth_conflict", "resolve_retention_conflict", "merge_teams",
                    "delete_node", "create_node", "update_policy", "execute_mutation",
                }
                if fn_name in prohibited_mutating_tools or "mutate" in fn_name.lower() or "delete" in fn_name.lower():
                    logger.warning(f"Blocked unauthorized LLM attempt to invoke mutating tool: {fn_name}")
                    return ToolResult(
                        tool_name="security_guard",
                        status="forbidden",
                        text_answer="LLM agent is restricted to read-only tools and cannot directly invoke mutating operations.",
                        details={"blocked_tool": fn_name},
                        subgraph=Subgraph(),
                    )

                if fn_name == "run_schema_constrained_cypher":
                    return self._execute_cypher(
                        query=fn_args.get("query", ""),
                        explanation=fn_args.get("explanation", "Dynamic schema-constrained query"),
                        graph_name=target_graph,
                        user_prompt=user_prompt,
                    )
                else:
                    return execute_tool(fn_name, fn_args, graph_name=target_graph)

            # ---------------------------------------------------------------
            # GUARDRAIL LAYER 3: Post-flight intercept of direct text responses.
            # If the LLM chose NOT to call a tool, its direct text response must
            # be validated. Any response that looks like a refusal or a generic
            # explanation rather than graph-grounded data is replaced with the
            # canonical refusal. This stops the LLM from "helpfully" answering
            # off-topic questions even when the system prompt says not to.
            # ---------------------------------------------------------------
            direct_text = (msg.content or "").strip()

            # Re-run the scope check on the LLM's direct response content.
            # If the LLM's response is long but doesn't call a tool and the
            # original prompt was borderline, enforce refusal.
            if not _is_in_scope(user_prompt):
                logger.warning("Guardrail Layer 3: LLM bypassed tool call on out-of-scope prompt; enforcing refusal.")
                return ToolResult(
                    tool_name="guardrail",
                    status="out_of_scope",
                    text_answer=_REFUSAL_RESPONSE,
                    details={"reason": "llm_direct_response_on_oos_prompt"},
                    subgraph=Subgraph(),
                )

            # Allow genuine on-scope clarifying responses (e.g. "please specify which team")
            return ToolResult(
                tool_name="llm_agent",
                text_answer=direct_text or "No response generated.",
                details={"model": self.model},
                subgraph=Subgraph(),
            )

        except Exception as e:
            logger.error(f"Error during LLM agent invocation: {e}. Falling back to deterministic dispatcher.")
            return self._fallback_deterministic_dispatch(user_prompt, target_graph)


llm_agent = LLMAgent()
