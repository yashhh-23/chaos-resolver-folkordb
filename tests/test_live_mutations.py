"""Integration and unit tests for Phase 5: Live Graph Mutations (Track 03 Hardening)."""

import pytest
from src.config import settings
from src.db.client import db_client
from src.pipeline.mutations import LiveMutationEngine


@pytest.fixture(scope="module")
def mutation_engine():
    db_client.connect()
    return LiveMutationEngine(graph_name=settings.graph_merged)


def test_resolve_auth_conflict(mutation_engine):
    """Verifies that resolving auth token conflict executes MERGE/SET and returns valid subgraph."""
    res = mutation_engine.resolve_auth_conflict()
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


def test_resolve_retention_conflict(mutation_engine):
    """Verifies that resolving retention conflict creates unified tiered policy."""
    res = mutation_engine.resolve_retention_conflict()
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


def test_merge_teams(mutation_engine):
    """Verifies that merging teams unifies FinPay and Vaultly engineers."""
    res = mutation_engine.merge_teams()
    assert res["status"] == "success"
    assert res["action"] == "merge_teams"
    assert res["unified_team_id"] == "unified:team:identity_secarch"
    assert "subgraph" in res
    assert len(res["subgraph"]["nodes"]) >= 3

    # Verify engineers belong to the unified team in FalkorDB
    graph = db_client.get_graph(settings.graph_merged)
    q = """
        MATCH (p:Person)-[:MEMBER_OF]->(t:Team {id: 'unified:team:identity_secarch'})
        RETURN count(p) as member_count
    """
    records = graph.query(q).result_set
    assert len(records) > 0
    assert records[0][0] >= 2


def test_reset_demo(mutation_engine):
    """Verifies that reset_demo restores multigraphs and returns fresh subgraph."""
    res = mutation_engine.reset_demo(include_subgraph=True)
    assert res["status"] == "success"
    assert res["action"] == "reset_demo"
    assert "subgraph" in res
    assert len(res["subgraph"]["nodes"]) > 0
    assert len(res["subgraph"]["edges"]) > 0
    assert "pipeline_summary" in res
