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
    assert "subgraph" in res
    assert len(res["subgraph"]["nodes"]) > 0
    assert len(res["subgraph"]["edges"]) > 0
    assert "pipeline_summary" in res

    # Verify 384-float embedding vectors are stripped from subgraph payload
    for node in res["subgraph"]["nodes"]:
        assert "embedding" not in node["properties"], f"Node {node['id']} should not contain embedding payload"

