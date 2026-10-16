"""Unit and integration tests for Phase 3: Deterministic Agent Tools, MCP & FastAPI."""

import pytest
from fastapi.testclient import TestClient
from src.tools.graph_tools import agent_tools, ToolResult
from src.tools.mcp_server import MCP_TOOL_DEFINITIONS, execute_tool
from src.api.main import app

client = TestClient(app)


def test_mcp_tool_definitions_schema():
    assert len(MCP_TOOL_DEFINITIONS) == 6
    tool_names = [t["name"] for t in MCP_TOOL_DEFINITIONS]
    assert "find_counterpart_expert" in tool_names
    assert "detect_policy_conflicts" in tool_names
    assert "find_redundant_systems" in tool_names
    assert "trace_decision_lineage" in tool_names
    assert "get_warm_intro_path" in tool_names
    assert "detect_organizational_silos" in tool_names



def test_tool_find_counterpart_expert():
    res = agent_tools.find_counterpart_expert(topic="Authentication", company="Vaultly")
    assert isinstance(res, ToolResult)
    assert res.tool_name == "find_counterpart_expert"
    assert "Diya Nair" in res.text_answer
    assert len(res.subgraph.nodes) > 0
    assert any(n.name == "Diya Nair" for n in res.subgraph.nodes)


def test_tool_detect_policy_conflicts():
    res = agent_tools.detect_policy_conflicts(domain="Data Retention")
    assert isinstance(res, ToolResult)
    # Validates active conflict detection if unmutated, or compliant summary if mutations already ran
    if len(res.details["conflicts"]) > 0:
        assert "180" in res.text_answer or "Retention" in res.text_answer
        assert len(res.subgraph.edges) > 0
    else:
        assert "0 Active Conflicts" in res.text_answer
        assert "previously resolved" in res.text_answer


def test_tool_find_redundant_systems():
    res = agent_tools.find_redundant_systems()
    assert isinstance(res, ToolResult)
    assert len(res.details["redundant_systems"]) >= 3
    # Check that Gatekeeper-Auth and Pulse-Identity are detected
    names = [r["system_a"]["name"] + " <-> " + r["system_b"]["name"] for r in res.details["redundant_systems"]]
    assert any("Gatekeeper-Auth" in n for n in names)
    assert len(res.subgraph.nodes) >= 4


def test_tool_trace_decision_lineage():
    res = agent_tools.trace_decision_lineage("Gatekeeper-Auth")
    assert isinstance(res, ToolResult)
    assert "Decision Lineage" in res.text_answer
    assert "15-min JWT expiry" in res.text_answer
    assert len(res.subgraph.nodes) > 0

    # Test reverse direction conflict surfacing on Vaultly counterpart
    res_pulse = agent_tools.trace_decision_lineage("Pulse-Identity")
    assert isinstance(res_pulse, ToolResult)
    assert "Pulse-Identity" in res_pulse.text_answer
    assert "Conflict" in res_pulse.text_answer or "Conflict" in str(res_pulse.subgraph.edges)
    assert len(res_pulse.subgraph.nodes) > 0

    # Ensure no duplicate governing decision headings for the same decision
    lines = res_pulse.text_answer.split("\n")
    gov_lines = [l for l in lines if l.startswith("#### Governing Decision:")]
    assert len(gov_lines) == len(set(gov_lines))


def test_tool_get_warm_intro_path():
    res = agent_tools.get_warm_intro_path(person_a="Aarav Mehta", person_b="Diya Nair")
    assert isinstance(res, ToolResult)
    assert "Warm Introduction Path" in res.text_answer
    assert res.details.get("hops", 0) <= 5
    assert len(res.subgraph.nodes) >= 2


def test_tool_detect_organizational_silos():
    res = agent_tools.detect_organizational_silos()
    assert isinstance(res, ToolResult)
    assert res.tool_name == "detect_organizational_silos"
    assert "Weakly Connected Components" in res.text_answer
    assert res.details.get("total_components", 0) >= 1
    assert len(res.subgraph.nodes) > 0


def test_mcp_execute_dispatcher():
    res = execute_tool("find_redundant_systems", {})
    assert res.tool_name == "find_redundant_systems"
    silo_res = execute_tool("detect_organizational_silos", {})
    assert silo_res.tool_name == "detect_organizational_silos"


def test_fastapi_endpoints():
    # Health check
    h_res = client.get("/api/health")
    assert h_res.status_code == 200
    assert h_res.json()["falkordb_connected"] is True

    # Redundant systems
    red_res = client.post("/api/tools/find-redundant-systems")
    assert red_res.status_code == 200
    assert red_res.json()["tool_name"] == "find_redundant_systems"

    # Organizational silos (WCC)
    silo_res = client.post("/api/tools/detect-silos")
    assert silo_res.status_code == 200
    assert silo_res.json()["tool_name"] == "detect_organizational_silos"

    # Chat endpoint (Groq / Offline router)
    chat_res = client.post("/api/chat", json={"prompt": "Who is the expert on Authentication?"})
    assert chat_res.status_code == 200
    assert chat_res.json()["tool_name"] == "find_counterpart_expert"

    # Subgraph for visual rendering
    sub_res = client.get("/api/graph/subgraph")
    assert sub_res.status_code == 200
    data = sub_res.json()
    assert "nodes" in data
    assert "edges" in data
    assert len(data["nodes"]) > 0


def test_llm_agent_chat_and_cypher():
    from src.tools.llm_agent import llm_agent

    # Test deterministic fallback chat
    res = llm_agent.chat("Detect disconnected organizational silos")
    assert res.tool_name == "detect_organizational_silos"
    assert "Weakly Connected Components" in res.text_answer

    # Test schema-constrained safe Cypher execution
    cypher_res = llm_agent._execute_cypher(
        "MATCH (p:Person) RETURN p.name, p.role",
        "List all engineers",
        "merged_brain",
    )
    assert cypher_res.status == "success"
    assert cypher_res.details["row_count"] >= 1

    # Test security rejection on mutating Cypher
    blocked_res = llm_agent._execute_cypher(
        "MATCH (p:Person) DELETE p",
        "Delete nodes",
        "merged_brain",
    )
    assert blocked_res.status == "error"
    assert "Security Violation" in blocked_res.text_answer


