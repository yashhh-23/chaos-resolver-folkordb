"""Model Context Protocol (MCP) and LLM Tool Definitions for OrgBridge AI.

Exposes the 5 deterministic FalkorDB tools in standard JSON-Schema format
for autonomous LLM agents (Groq Llama-3.3-70B / OpenAI / Anthropic).
"""

from typing import Dict, Any, List
from src.tools.graph_tools import agent_tools, ToolResult

MCP_TOOL_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "name": "find_counterpart_expert",
        "description": "Finds the actual subject-matter expert in an acquired or acquiring company based on PR reviews, resolved incidents, and authored RFCs (using PageRank).",
        "parameters": {
            "type": "object",
            "properties": {
                "topic": {
                    "type": "string",
                    "description": "Domain, technology, or topic of expertise (e.g. 'Authentication', 'Ledger', 'PCI', 'KYC')",
                },
                "company": {
                    "type": "string",
                    "enum": ["Vaultly", "FinPay"],
                    "default": "Vaultly",
                    "description": "Target company to search within",
                },
            },
            "required": ["topic"],
        },
    },
    {
        "name": "detect_policy_conflicts",
        "description": "Identifies conflicting regulatory, security, and data retention policies between FinPay and Vaultly, tracing them to source documents.",
        "parameters": {
            "type": "object",
            "properties": {
                "domain": {
                    "type": "string",
                    "description": "Optional domain filter (e.g. 'Authentication', 'Data Retention', 'Network Security')",
                },
            },
        },
    },
    {
        "name": "find_redundant_systems",
        "description": "Exposes redundant systems across FinPay and Vaultly identified by hybrid vector similarity and shared external API dependencies.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
    {
        "name": "trace_decision_lineage",
        "description": "Traces governing architectural decisions for a microservice, opposing company decisions, and source citations (Slack threads, RFCs, Jira tickets).",
        "parameters": {
            "type": "object",
            "properties": {
                "system_name": {
                    "type": "string",
                    "description": "Name or ID of the system (e.g. 'Gatekeeper-Auth', 'Pulse-Identity', 'FinPay-Core-Ledger')",
                },
            },
            "required": ["system_name"],
        },
    },
    {
        "name": "get_warm_intro_path",
        "description": "Finds the fastest warm introduction or dependency path between two engineers across company borders using shortest graph traversal.",
        "parameters": {
            "type": "object",
            "properties": {
                "person_a": {
                    "type": "string",
                    "description": "Name or ID of the originating person (e.g. 'Aarav Mehta')",
                },
                "person_b": {
                    "type": "string",
                    "description": "Name or ID of the counterpart person (e.g. 'Diya Nair')",
                },
            },
            "required": ["person_a", "person_b"],
        },
    },
    {
        "name": "detect_organizational_silos",
        "description": "Discovers isolated organizational islands and single-tenant silos across FinPay and Vaultly using Weakly Connected Components (WCC) graph clustering.",
        "parameters": {
            "type": "object",
            "properties": {},
        },
    },
]


def execute_tool(tool_name: str, arguments: Dict[str, Any]) -> ToolResult:
    """Dispatches tool execution dynamically based on tool name."""
    if tool_name == "find_counterpart_expert":
        return agent_tools.find_counterpart_expert(
            topic=arguments.get("topic", ""),
            company=arguments.get("company", "Vaultly"),
        )
    elif tool_name == "detect_policy_conflicts":
        return agent_tools.detect_policy_conflicts(
            domain=arguments.get("domain"),
        )
    elif tool_name == "find_redundant_systems":
        return agent_tools.find_redundant_systems()
    elif tool_name == "trace_decision_lineage":
        return agent_tools.trace_decision_lineage(
            system_name=arguments.get("system_name", ""),
        )
    elif tool_name == "get_warm_intro_path":
        return agent_tools.get_warm_intro_path(
            person_a=arguments.get("person_a", ""),
            person_b=arguments.get("person_b", ""),
        )
    elif tool_name == "detect_organizational_silos":
        return agent_tools.detect_organizational_silos()
    else:
        raise ValueError(f"Unknown MCP tool: {tool_name}")

