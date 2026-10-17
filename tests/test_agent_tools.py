"""Unit and integration tests for Phase 3: Deterministic Agent Tools, MCP & FastAPI."""

import pytest
from fastapi.testclient import TestClient
from src.tools.graph_tools import agent_tools, ToolResult
from src.tools.mcp_server import MCP_TOOL_DEFINITIONS, execute_tool
from src.api.main import app

client = TestClient(app)
client.headers = {"X-API-Key": "orgbridge-war-room-2026"}


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
    assert res.status == "success"
    assert "Diya Nair" in res.text_answer
    assert res.details["expert"] == "Diya Nair"
    assert res.details["topic_evidence_score"] > 0.0
    assert res.details["graph_influence"] >= 0.5
    assert res.details["evidence_count"] >= 1
    assert len(res.subgraph.nodes) > 0
    assert any(n.name == "Diya Nair" for n in res.subgraph.nodes)


def test_tool_find_counterpart_expert_insufficient_evidence():
    """Verifies that an unsupported topic returns insufficient_evidence rather than falsely crowning top PageRank (B13)."""
    res = agent_tools.find_counterpart_expert(topic="Quantum Cryptography Supercomputing", company="Vaultly")
    assert isinstance(res, ToolResult)
    assert res.tool_name == "find_counterpart_expert"
    assert res.status == "insufficient_evidence"
    assert res.details["evidence_found"] == 0
    assert "expert" not in res.details
    assert "Insufficient Evidence" in res.text_answer
    assert "Organizational Centrality Context" in res.text_answer
    assert "Topic rankings require concrete domain evidence" in res.text_answer


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
    assert res.details["algorithm"] in ["falkordb_native_algo_wcc", "python_adjacency_fallback"]
    assert "native_algorithm" in res.details


def test_tool_detect_organizational_silos_fallback(monkeypatch):
    """Verifies seamless fallback to Python adjacency BFS when FalkorDB CALL algo.wcc fails or is unsupported (B14)."""
    original_get_graph = agent_tools._get_graph

    class MockFailingGraph:
        def __init__(self, real_graph):
            self.real_graph = real_graph

        def query(self, cypher: str, params: dict = None):
            if "CALL algo.wcc()" in cypher:
                raise Exception("Procedure algo.wcc not available in mock test environment")
            return self.real_graph.query(cypher, params)

    real_graph = original_get_graph()
    monkeypatch.setattr(agent_tools, "_get_graph", lambda: MockFailingGraph(real_graph))

    res = agent_tools.detect_organizational_silos()
    assert isinstance(res, ToolResult)
    assert res.tool_name == "detect_organizational_silos"
    assert res.details["algorithm"] == "python_adjacency_fallback"
    assert res.details["native_algorithm"] is False
    assert res.details["total_components"] >= 1
    assert "Python Adjacency Traversal Fallback" in res.text_answer


def test_tool_detect_organizational_silos_b17_b18(monkeypatch):
    """Verifies B17 (separates external-only components from silos) and B18 (evidence-based recommendations)."""
    # 1. Real run on FalkorDB: verify no hardcoded string and proper structure
    res = agent_tools.detect_organizational_silos()
    assert res.tool_name == "detect_organizational_silos"
    assert "FinPay Platform Infrastructure & Shared Identity via warm-intro" not in res.text_answer
    assert "external_components_count" in res.details
    assert "isolated_silos_count" in res.details
    assert "integrated_networks_count" in res.details

    # If silos exist (e.g. Vaultly Mobile Experience), verify evidence-derived recommendation
    for silo in res.details.get("silos", []):
        assert "recommendation" in silo
        assert "FinPay Platform Infrastructure & Shared Identity" not in silo["recommendation"]
        assert silo["classification"] == "silo"
        assert len(silo["companies"]) == 1

    # 2. Mock graph with an external-only component and verify B17 classification
    original_get_graph = agent_tools._get_graph
    real_graph = original_get_graph()

    class MockExternalGraph:
        def query(self, cypher: str, params: dict = None):
            if "CALL algo.wcc()" in cypher:
                # Mock 3 components: 1 integrated, 1 silo, 1 external-only
                class MockNode:
                    def __init__(self, nid, name, label, company):
                        self.properties = {"id": nid, "name": name, "company_origin": company}
                        self.labels = [label]

                return type("MockResult", (), {
                    "result_set": [
                        # Component 0: Integrated (FinPay + Vaultly)
                        [MockNode("finpay:sys:core", "FinPay Core", "System", "FinPay"), 0],
                        [MockNode("vaultly:sys:core", "Vaultly Core", "System", "Vaultly"), 0],
                        # Component 1: Genuine Silo (Vaultly only)
                        [MockNode("vaultly:team:app", "Vaultly Mobile", "Team", "Vaultly"), 1],
                        # Component 2: External-only (AWS / Third Party)
                        [MockNode("ext:sys:aws_kms", "AWS KMS", "System", "External"), 2],
                        [MockNode("ext:sys:stripe", "Stripe API", "System", "External"), 2],
                    ]
                })()
            return real_graph.query(cypher, params)

    monkeypatch.setattr(agent_tools, "_get_graph", lambda: MockExternalGraph())
    ext_res = agent_tools.detect_organizational_silos()
    assert ext_res.details["isolated_silos_count"] == 1, "External-only component must NOT be counted as an isolated silo"
    assert ext_res.details["external_components_count"] == 1, "External-only component must be counted separately"
    assert len(ext_res.details["external_components"]) == 1
    assert ext_res.details["external_components"][0]["classification"] == "external_or_unclassified"
    assert "External & Third-Party Dependencies" in ext_res.text_answer


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


def test_security_and_authorization():
    """Verifies that unauthenticated callers are rejected (401) and write/admin roles are enforced (403)."""
    unauthed_client = TestClient(app)

    # 1. Unauthenticated mutation blocked with 401
    res = unauthed_client.post("/api/mutate/resolve-auth-conflict", json={"compromise_ttl_minutes": 30})
    assert res.status_code == 401

    # 2. Unauthenticated chat blocked with 401
    res = unauthed_client.post("/api/chat", json={"prompt": "Show me silos"})
    assert res.status_code == 401

    # 3. Unauthenticated reset blocked with 401
    res = unauthed_client.post("/api/mutate/reset-demo", json={})
    assert res.status_code == 401

    # 4. Authenticated write client can perform mutations
    authed_client = TestClient(app)
    authed_client.headers = {"X-API-Key": "orgbridge-war-room-2026"}
    res = authed_client.post("/api/mutate/resolve-auth-conflict", json={"compromise_ttl_minutes": 30})
    assert res.status_code == 200

    # 5. Write key without admin role cannot perform destructive reset (403 Forbidden)
    reset_forbidden = authed_client.post("/api/mutate/reset-demo", json={})
    assert reset_forbidden.status_code == 403

    # 6. Admin client with X-Admin-Key is authorized for reset-demo
    admin_client = TestClient(app)
    admin_client.headers = {"X-Admin-Key": "orgbridge-admin-war-room-2026"}
    reset_ok = admin_client.post("/api/mutate/reset-demo", json={})
    assert reset_ok.status_code == 200


def test_tenant_specific_mutations():
    """Verifies that mutations validate tenant graph parameter and operate on requested graph."""
    authed_client = TestClient(app)
    authed_client.headers = {"X-API-Key": "orgbridge-war-room-2026"}

    # Invalid tenant graph rejected with 400
    bad_res = authed_client.post("/api/mutate/resolve-auth-conflict", json={"graph": "invalid_graph_name"})
    assert bad_res.status_code == 400
    assert "Invalid graph tenant" in bad_res.json()["detail"]

    # Target specific valid graph tenant
    finpay_res = authed_client.post("/api/mutate/resolve-auth-conflict", json={"graph": "finpay_graph", "compromise_ttl_minutes": 25})
    assert finpay_res.status_code == 200
    assert finpay_res.json()["status"] == "success"


def test_deterministic_entity_resolution_hierarchy():
    """Verifies that entity resolution prioritizes exact ID, then exact name, and detects ambiguity (B7, B8)."""
    # 1. Exact ID match (case-insensitive)
    node, amb = agent_tools.resolve_entity("Person", "FINPAY:PERSON:AARAV_MEHTA")
    assert amb is None
    assert node is not None
    assert node["id"] == "finpay:person:aarav_mehta"

    # 2. Exact Name match (case-insensitive)
    node_name, amb_name = agent_tools.resolve_entity("Person", "aarav mehta")
    assert amb_name is None
    assert node_name is not None
    assert node_name["id"] == "finpay:person:aarav_mehta"

    # 3. Exact system ID
    sys_node, sys_amb = agent_tools.resolve_entity("System", "finpay:sys:gatekeeper_auth")
    assert sys_amb is None
    assert sys_node is not None
    assert sys_node["id"] == "finpay:sys:gatekeeper_auth"

    # 4. Nonexistent entity
    none_node, none_amb = agent_tools.resolve_entity("Person", "Nonexistent_Ghost_User_999")
    assert none_node is None
    assert none_amb == []


def test_warm_intro_path_ambiguity_and_shortest_path_semantics(monkeypatch):
    """Verifies that get_warm_intro_path reports shortest graph path semantics and handles ambiguity cleanly (B7)."""
    # Normal deterministic path
    res = agent_tools.get_warm_intro_path("finpay:person:aarav_mehta", "vaultly:person:diya_nair")
    assert res.status == "success"
    assert "Shortest topological graph path" in res.text_answer
    assert res.details.get("path_metric") == "shortest_topological_path"
    assert "resolved_a" in res.details
    assert "resolved_b" in res.details

    # Same person input
    same_res = agent_tools.get_warm_intro_path("Aarav Mehta", "finpay:person:aarav_mehta")
    assert same_res.status == "same_person"
    assert "No introduction path required" in same_res.text_answer

    # Nonexistent person input
    nf_res = agent_tools.get_warm_intro_path("Unknown Person 12345", "Diya Nair")
    assert nf_res.status == "not_found"
    assert "was not found in the graph" in nf_res.text_answer

    # Ambiguity detection when multiple people match
    def mock_resolve_ambiguous(self, label, identifier):
        if "Alex" in identifier:
            return None, [
                {"id": "finpay:person:alex_chen", "name": "Alex Chen", "company_origin": "FinPay", "role": "Staff Eng"},
                {"id": "vaultly:person:alex_kumar", "name": "Alex Kumar", "company_origin": "Vaultly", "role": "Sec Eng"},
            ]
        return agent_tools.resolve_entity(label, identifier)

    monkeypatch.setattr(agent_tools, "resolve_entity", mock_resolve_ambiguous.__get__(agent_tools))
    amb_res = agent_tools.get_warm_intro_path("Alex", "Diya Nair")
    assert amb_res.status == "ambiguous"
    assert "Ambiguous Person Query" in amb_res.text_answer
    assert amb_res.details["matched_count"] == 2


def test_trace_decision_lineage_deterministic_system_and_ambiguity(monkeypatch):
    """Verifies that trace_decision_lineage requires unique system before tracing lineage (B8)."""
    # Exact ID resolution
    res_id = agent_tools.trace_decision_lineage("finpay:sys:gatekeeper_auth")
    assert res_id.status == "success"
    assert "Decision Lineage" in res_id.text_answer
    assert res_id.details["system_id"] == "finpay:sys:gatekeeper_auth"

    # Nonexistent system
    res_nf = agent_tools.trace_decision_lineage("nonexistent_microservice_xyz")
    assert res_nf.status == "not_found"
    assert "was not found in the graph" in res_nf.text_answer

    # Ambiguous system
    def mock_resolve_sys_ambiguous(self, label, identifier):
        if identifier == "ambiguous_auth":
            return None, [
                {"id": "finpay:sys:gatekeeper_auth", "name": "Gatekeeper-Auth", "company_origin": "FinPay", "domain": "Auth"},
                {"id": "vaultly:sys:pulse_identity", "name": "Pulse-Identity", "company_origin": "Vaultly", "domain": "Auth"},
            ]
        return agent_tools.resolve_entity(label, identifier)

    monkeypatch.setattr(agent_tools, "resolve_entity", mock_resolve_sys_ambiguous.__get__(agent_tools))
    res_amb = agent_tools.trace_decision_lineage("ambiguous_auth")
    assert res_amb.status == "ambiguous"
    assert "Ambiguous System Query" in res_amb.text_answer
    assert res_amb.details["matched_count"] == 2



