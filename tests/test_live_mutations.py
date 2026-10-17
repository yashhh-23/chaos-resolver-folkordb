"""Integration and unit tests for Phase 5: Live Graph Mutations (Track 03 Hardening)."""

import pytest
from src.config import settings
from src.db.client import db_client
from src.pipeline.mutations import LiveMutationEngine


@pytest.fixture(scope="module")
def mutation_engine():
    db_client.connect()
    return LiveMutationEngine(graph_name=settings.graph_merged)


@pytest.fixture(scope="module", autouse=True)
def teardown_demo_reset(mutation_engine):
    """Ensures that after all tests in this module run, FalkorDB is cleanly restored to baseline."""
    yield
    mutation_engine.reset_demo(include_subgraph=False)


def test_resolve_auth_conflict(mutation_engine):
    """Verifies that resolving auth token conflict executes MERGE/SET and returns valid subgraph."""
    res = mutation_engine.resolve_auth_conflict(compromise_ttl_minutes=30)
    assert res["status"] == "success"
    assert res["action"] == "resolve_auth_conflict"
    assert "unified_policy_id" in res
    assert res["unified_policy_id"] == "unified:pol:hybrid_session_auth"
    assert "post_verification" in res
    assert res["post_verification"]["verified"] is True
    assert "subgraph" in res
    assert len(res["subgraph"]["nodes"]) >= 3
    assert len(res["subgraph"]["edges"]) >= 2

    # Query FalkorDB to verify the policy exists
    graph = db_client.get_graph(settings.graph_merged)
    q = "MATCH (p:Policy {id: 'unified:pol:hybrid_session_auth'}) RETURN p.status as status, p.domain as domain"
    records = graph.query(q).result_set
    assert len(records) > 0
    assert records[0][0] == "ACTIVE"
    assert records[0][1] == "Authentication"

    # Test ON MATCH SET idempotency and property update
    res2 = mutation_engine.resolve_auth_conflict(compromise_ttl_minutes=45)
    assert res2["status"] == "success"
    q2 = "MATCH (p:Policy {id: 'unified:pol:hybrid_session_auth'}) RETURN p.description"
    rec2 = graph.query(q2).result_set
    assert len(rec2) > 0
    assert "45-min" in rec2[0][0]


def test_resolve_retention_conflict(mutation_engine):
    """Verifies that resolving retention conflict creates unified tiered policy."""
    res = mutation_engine.resolve_retention_conflict(retention_days=90)
    assert res["status"] == "success"
    assert res["action"] == "resolve_retention_conflict"
    assert res["unified_policy_id"] == "unified:pol:tiered_retention_90d"
    assert "post_verification" in res
    assert res["post_verification"]["verified"] is True
    assert "subgraph" in res
    assert len(res["subgraph"]["nodes"]) >= 3

    # Query FalkorDB to verify the policy exists
    graph = db_client.get_graph(settings.graph_merged)
    q = "MATCH (p:Policy {id: 'unified:pol:tiered_retention_90d'}) RETURN p.status as status"
    records = graph.query(q).result_set
    assert len(records) > 0
    assert records[0][0] == "ACTIVE"

    # Test ON MATCH SET updates
    res2 = mutation_engine.resolve_retention_conflict(retention_days=90)
    assert res2["status"] == "success"


def test_merge_teams(mutation_engine):
    """Verifies that merging teams unifies FinPay and Vaultly engineers and deprecates old teams."""
    res = mutation_engine.merge_teams(unified_name="Unified M&A Security & Identity Team")
    assert res["status"] == "success"
    assert res["action"] == "merge_teams"
    assert res["unified_team_id"] == "unified:team:identity_secarch"
    assert "subgraph" in res
    assert len(res["subgraph"]["nodes"]) >= 3

    graph = db_client.get_graph(settings.graph_merged)

    # Verify engineers belong to the unified team in FalkorDB
    q = """
        MATCH (p:Person)-[:MEMBER_OF]->(t:Team {id: 'unified:team:identity_secarch'})
        RETURN count(p) as member_count
    """
    records = graph.query(q).result_set
    assert len(records) > 0
    assert records[0][0] >= 2

    # Verify old teams are marked MERGED
    q_old_status = """
        MATCH (t:Team)
        WHERE t.id IN ['finpay:team:secarch', 'vaultly:team:identity_growth']
        RETURN t.status, count(t)
    """
    old_res = graph.query(q_old_status).result_set
    assert len(old_res) > 0
    assert old_res[0][0] == "MERGED"

    # Verify old teams have 0 remaining MEMBER_OF edges
    q_old_members = """
        MATCH (p:Person)-[:MEMBER_OF]->(t:Team)
        WHERE t.id IN ['finpay:team:secarch', 'vaultly:team:identity_growth']
        RETURN count(p)
    """
    assert graph.query(q_old_members).result_set[0][0] == 0

    # Test ON MATCH SET update
    res_rename = mutation_engine.merge_teams(unified_name="Renamed Unified Identity Team")
    assert res_rename["status"] == "success"
    q_name = "MATCH (ut:Team {id: 'unified:team:identity_secarch'}) RETURN ut.name"
    assert graph.query(q_name).result_set[0][0] == "Renamed Unified Identity Team"


def test_reset_demo(mutation_engine):
    """Verifies that reset_demo restores multigraphs and returns fresh subgraph without embedding bloat."""
    res = mutation_engine.reset_demo(include_subgraph=True)
    assert res["status"] == "success"
    assert res["action"] == "reset_demo"
    assert "stages" in res
    assert res["stages"]["seeding"]["status"] == "success"
    assert res["stages"]["verification"]["node_count"] > 0
    assert "subgraph" in res
    assert len(res["subgraph"]["nodes"]) > 0
    assert len(res["subgraph"]["edges"]) > 0
    assert "pipeline_summary" in res

    # Verify 384-float embedding vectors are stripped from subgraph payload
    for node in res["subgraph"]["nodes"]:
        assert "embedding" not in node["properties"], f"Node {node['id']} should not contain embedding payload"


def test_merge_teams_input_validation_and_preconditions(mutation_engine):
    """Verifies B3: Precondition validation, history preservation, and dynamic IDs in team merges."""
    # 1. Missing team should raise ValueError
    with pytest.raises(ValueError, match="do not exist"):
        mutation_engine.merge_teams(
            team_a_id="finpay:team:non_existent",
            team_b_id="vaultly:team:identity_growth",
        )

    # 2. Merging a team into itself should raise ValueError
    with pytest.raises(ValueError, match="Cannot merge team.*into itself"):
        mutation_engine.merge_teams(
            team_a_id="finpay:team:secarch",
            team_b_id="finpay:team:secarch",
        )

    # 3. Dynamic team ID generation for custom teams
    res_custom = mutation_engine.merge_teams(
        team_a_id="finpay:team:payments_core",
        team_b_id="vaultly:team:ledger_eng",
        unified_name="Unified Core Payments & Ledger Team",
    )
    assert res_custom["status"] == "success"
    assert res_custom["unified_team_id"] == "unified:team:ledger_eng_payments_core"
    assert "payments_core" in res_custom["source_teams"][0] or "payments_core" in res_custom["source_teams"][1]

    # Verify history preservation on the deprecated team node
    graph = db_client.get_graph(settings.graph_merged)
    q_hist = """
        MATCH (t:Team {id: 'finpay:team:payments_core'})
        RETURN t.status, t.merged_into, t.historical_members
    """
    hist_rec = graph.query(q_hist).result_set
    assert len(hist_rec) > 0
    assert hist_rec[0][0] == "MERGED"
    assert hist_rec[0][1] == "unified:team:ledger_eng_payments_core"
    assert isinstance(hist_rec[0][2], list)

    # 4. Attempting to merge an already-merged team into a different team must fail preconditions
    with pytest.raises(ValueError, match="already merged into"):
        mutation_engine.merge_teams(
            team_a_id="finpay:team:payments_core",
            team_b_id="vaultly:team:app_experience",
        )


def test_policy_contradiction_validation_engine():
    """Verifies B4: 3-stage policy contradiction validation with quantitative proof & authority weighting."""
    from src.pipeline.policy_validator import policy_contradiction_engine
    from src.tools.graph_tools import GraphAgentTools

    # Test 1: Concrete TTL contradiction (15m vs 7d)
    auth_a = {
        "id": "test:pol:auth_a",
        "name": "Strict Session Policy",
        "domain": "Authentication",
        "description": "Ephemeral tokens capped at 900 seconds. PCI-DSS Requirement 8.2.",
        "authority_level": "CISO",
        "company_origin": "FinPay",
    }
    auth_b = {
        "id": "test:pol:auth_b",
        "name": "Frictionless Session Policy",
        "domain": "Authentication",
        "description": "Mobile refresh tokens persist up to 7 days with biometric re-auth.",
        "authority_level": "Head of Product",
        "company_origin": "Vaultly",
    }
    val_auth = policy_contradiction_engine.validate_contradiction(auth_a, auth_b)
    assert val_auth is not None
    assert val_auth["is_contradiction"] is True
    assert val_auth["contradiction_type"] == "TOKEN_LIFECYCLE_TTL_CONTRADICTION"
    assert val_auth["review_status"] == "CONFIRMED_CONTRADICTION"
    assert val_auth["severity"] == "CRITICAL"
    assert "672x" in val_auth["concrete_proof"]
    assert val_auth["confidence"] >= 0.95

    # Test 2: Concrete Retention contradiction (30d purge vs 180d forensic audit)
    ret_a = {
        "id": "test:pol:ret_a",
        "name": "Data Minimization",
        "domain": "Data Retention",
        "description": "Purge all access logs and telemetry after 30 days.",
        "authority_level": "VP Compliance",
        "company_origin": "FinPay",
    }
    ret_b = {
        "id": "test:pol:ret_b",
        "name": "Forensic Audit Retention",
        "domain": "Data Retention",
        "description": "Audit trails and transactional logs must be retained for at least 180 days for banking audits.",
        "authority_level": "Head of Security",
        "company_origin": "Vaultly",
    }
    val_ret = policy_contradiction_engine.validate_contradiction(ret_a, ret_b)
    assert val_ret is not None
    assert val_ret["is_contradiction"] is True
    assert val_ret["contradiction_type"] == "DATA_RETENTION_HORIZON_INCOMPATIBILITY"
    assert val_ret["review_status"] == "CONFIRMED_CONTRADICTION"
    assert val_ret["severity"] in ["CRITICAL", "HIGH"]

    # Test 3: Compatible non-contradictory policies sharing the same domain
    comp_a = {
        "id": "test:pol:comp_a",
        "name": "MFA Standard",
        "domain": "Authentication",
        "description": "Enforce WebAuthn FIDO2 biometric authentication on all privileged access.",
        "authority_level": "Security Lead",
        "company_origin": "FinPay",
    }
    comp_b = {
        "id": "test:pol:comp_b",
        "name": "Hardware Token Policy",
        "domain": "Authentication",
        "description": "Require WebAuthn hardware security keys for internal identity access.",
        "authority_level": "Head of Security",
        "company_origin": "Vaultly",
    }
    val_comp = policy_contradiction_engine.validate_contradiction(comp_a, comp_b)
    # Since both enforce WebAuthn without opposing TTLs or opposing directives, they are compatible!
    assert val_comp is None

    # Test 4: Tool output contains contradiction types and authority assessments
    tools = GraphAgentTools(graph_name=settings.graph_merged)
    res = tools.detect_policy_conflicts()
    if res.details["conflicts"]:
        first = res.details["conflicts"][0]
        assert "contradiction_type" in first
        assert "review_status" in first
        assert "authority_assessment" in first
        assert "Contradiction Type" in res.text_answer


def test_mutation_post_verification_and_invariants(mutation_engine):
    """Verifies B10: Post-mutation invariant checks prove node/relationship states before reporting success."""
    # Test auth conflict resolution post-verification fields
    res_auth = mutation_engine.resolve_auth_conflict(compromise_ttl_minutes=25)
    assert res_auth["status"] == "success"
    assert res_auth["post_verification"]["verified"] is True
    assert res_auth["post_verification"]["policy_status"] == "ACTIVE"
    assert res_auth["post_verification"]["decision_status"] == "ACTIVE"

    # Test retention conflict resolution post-verification fields
    res_ret = mutation_engine.resolve_retention_conflict(retention_days=60)
    assert res_ret["status"] == "success"
    assert res_ret["post_verification"]["verified"] is True
    assert res_ret["post_verification"]["policy_status"] == "ACTIVE"
    assert res_ret["post_verification"]["decision_status"] == "ACTIVE"


def test_reset_demo_multi_stage_verification_and_failure(mutation_engine, monkeypatch):
    """Verifies B10: Multi-stage tracking in reset_demo and failure propagation when seeding fails."""
    # 1. Normal run has multi-stage reporting
    res = mutation_engine.reset_demo(include_subgraph=False)
    assert res["status"] == "success"
    assert "stages" in res
    assert "seeding" in res["stages"]
    assert "auto_linker" in res["stages"]
    assert "verification" in res["stages"]
    assert res["stages"]["seeding"]["status"] == "success"
    assert res["stages"]["verification"]["node_count"] > 0

    # 2. Simulated seeding failure raises RuntimeError
    from src.data import seed
    def mock_failed_seed_all(*args, **kwargs):
        return {
            "status": "failed",
            "total_failures": 3,
            "failed_details": [{"statement": "CREATE (...) ", "error": "Redis connection dropped"}],
        }

    monkeypatch.setattr(seed, "seed_all_graphs", mock_failed_seed_all)
    with pytest.raises(RuntimeError, match="Reset failed during graph seeding stage: 3 statement"):
        mutation_engine.reset_demo(include_subgraph=False)


def test_reseed_preserves_live_mutation_state_and_destructive_reset(mutation_engine):
    """Verifies B11: Ordinary reseeding (clear_first=False) preserves runtime mutated status & embeddings,

    while destructive reset restores clean baseline.
    """
    from src.data.seed import seed_graph

    # 1. Resolve auth conflict, mutating finpay:pol:session_security to DEPRECATED
    res = mutation_engine.resolve_auth_conflict(compromise_ttl_minutes=30)
    assert res["status"] == "success"

    # Also attach a dummy embedding property to verify it is preserved
    graph = db_client.get_graph(settings.graph_merged)
    graph.query("MATCH (p:Policy {id: 'finpay:pol:session_security'}) SET p.runtime_embedding = [0.123, 0.456]")

    # Verify pre-condition
    check_pre = graph.query("MATCH (p:Policy {id: 'finpay:pol:session_security'}) RETURN p.status, p.runtime_embedding").result_set
    assert len(check_pre) > 0
    assert check_pre[0][0] == "DEPRECATED"
    assert len(check_pre[0][1]) == 2

    # 2. Run ordinary reseeding without clearing (clear_first=False, preserve_runtime_state=True)
    seed_res = seed_graph(settings.graph_merged, clear_first=False, preserve_runtime_state=True)
    assert seed_res["status"] == "success"

    # Verify that status is STILL DEPRECATED and runtime_embedding was NOT blown away
    check_post = graph.query("MATCH (p:Policy {id: 'finpay:pol:session_security'}) RETURN p.status, p.runtime_embedding").result_set
    assert len(check_post) > 0
    assert check_post[0][0] == "DEPRECATED", "Ordinary re-seed must not overwrite live-mutated status"
    assert len(check_post[0][1]) == 2, "Ordinary re-seed must preserve runtime-added node properties"

    # 3. Now run authorized destructive reset (clear_first=True, preserve_runtime_state=False)
    reset_res = mutation_engine.reset_demo(include_subgraph=False)
    assert reset_res["status"] == "success"

    # Verify that clean baseline is restored
    check_baseline = graph.query("MATCH (p:Policy {id: 'finpay:pol:session_security'}) RETURN p.status, p.runtime_embedding").result_set
    assert len(check_baseline) > 0
    assert check_baseline[0][0] == "ACTIVE"
    assert check_baseline[0][1] is None or check_baseline[0][1] == ""



