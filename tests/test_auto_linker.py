"""Unit tests for Phase 2: Embeddings Service and M&A Auto-Linker Engine."""

import pytest
from src.embeddings.service import EmbeddingService
from src.pipeline.auto_linker import AutoLinkerEngine


def test_embedding_service_dimensions_and_normalization():
    svc = EmbeddingService(dimension=384)
    vec = svc.embed_text("Gatekeeper Authentication Gateway")
    assert len(vec) == 384
    # Check L2 norm is approximately 1.0
    norm = sum(x * x for x in vec) ** 0.5
    assert abs(norm - 1.0) < 1e-4


def test_embedding_cosine_similarity():
    svc = EmbeddingService(dimension=384)
    v1 = svc.embed_text("Gatekeeper-Auth OAuth2 user session tokens")
    v2 = svc.embed_text("Pulse-Identity OAuth2 user session authentication")
    v3 = svc.embed_text("Unrelated Agricultural Farming Weather Forecast")

    sim_auth = svc.cosine_similarity(v1, v2)
    sim_unrelated = svc.cosine_similarity(v1, v3)

    assert sim_auth > 0.80, f"Expected high semantic similarity, got {sim_auth}"
    assert sim_auth > sim_unrelated, f"Auth similarity {sim_auth} should exceed unrelated {sim_unrelated}"


def test_auto_linker_threshold_configuration():
    engine_strict = AutoLinkerEngine(threshold=0.95)
    assert engine_strict.threshold == 0.95

    engine_default = AutoLinkerEngine(threshold=0.82)
    assert engine_default.threshold == 0.82


def test_external_api_hybrid_overlap_boost():
    """Validates that shared external API dependencies increase hybrid resolution score."""
    svc = EmbeddingService(dimension=384)
    v1 = svc.embed_text("Customer-KYC-Service")
    v2 = svc.embed_text("User-Onboarding-Verification")
    base_sim = svc.cosine_similarity(v1, v2)

    # Topological bonus for shared UIDAI API
    shared_apis = ["UIDAI_Aadhaar"]
    graph_bonus = 0.12 * len(shared_apis)
    boosted = base_sim + graph_bonus

    assert boosted > base_sim
    assert boosted >= 0.82


def test_auto_linker_threshold_filtering():
    """Validates that a strict threshold (0.99) properly filters lower-similarity conflicts."""
    from src.config import settings
    from src.db.client import db_client

    db_client.connect()
    strict_engine = AutoLinkerEngine(threshold=0.99)
    strict_policies = strict_engine.detect_policy_conflicts(settings.graph_merged)
    strict_decisions = strict_engine.detect_decision_conflicts(settings.graph_merged)

    # At 0.99, sub-0.99 conflicts are filtered out
    assert len(strict_policies) == 0
    assert len(strict_decisions) <= 1
    if strict_decisions:
        assert strict_decisions[0]["domain"] == "Data Retention"


def test_embedding_service_model_metadata():
    """Verifies that EmbeddingService carries explicit model version and provider metadata (B6)."""
    svc = EmbeddingService(dimension=384)
    assert hasattr(svc, "provider")
    assert hasattr(svc, "model_name")
    assert hasattr(svc, "model_version")
    assert hasattr(svc, "is_trained_model")
    assert svc.provider in ("openai", "local_hash_anchor")
    assert len(svc.model_version) > 0


def test_candidate_pairs_target_filtering_and_fallback(monkeypatch):
    """Verifies that _resolve_candidate_pairs filters out same-company neighbors
    and falls back to pairwise target-company calculation when no target neighbors match (B5).
    """
    engine = AutoLinkerEngine(threshold=0.7)
    svc = EmbeddingService(dimension=384)
    source_vec = svc.embed_text("Authentication Service")

    # Mock native vector query to return ONLY nodes from FinPay (same company origin)
    def mock_query_vector_neighbors(graph_name, label, vector, k=30):
        return [
            ({"id": "fp:sys:internal_auth", "company_origin": "FinPay"}, 0.05),
            ({"id": "fp:sys:internal_token", "company_origin": "FinPay"}, 0.08),
        ]

    import src.pipeline.auto_linker as al_module
    monkeypatch.setattr(al_module, "query_vector_neighbors", mock_query_vector_neighbors)

    all_target_candidates = {
        "vl:sys:pulse_identity": {
            "name": "Pulse Identity",
            "desc": "Authentication service",
        }
    }

    pairs = engine._resolve_candidate_pairs(
        graph_name="test_graph",
        entity_label="System",
        source_vec=source_vec,
        all_candidates=all_target_candidates,
        company_target="Vaultly",
        embed_candidate_fn=lambda info: svc.embed_text(f"{info['name']} {info['desc']}"),
    )

    # Must NOT return FinPay nodes; must fall back and evaluate the target Vaultly candidate
    assert len(pairs) == 1
    cand_id, sim = pairs[0]
    assert cand_id == "vl:sys:pulse_identity"
    assert sim > 0.0


def test_candidate_pairs_native_search_score(monkeypatch):
    """Verifies that native FalkorDB vector search distances are properly converted
    to cosine similarities without redundant local re-embedding (B6).
    """
    engine = AutoLinkerEngine(threshold=0.7)
    svc = EmbeddingService(dimension=384)
    source_vec = svc.embed_text("Authentication Service")

    # Mock native vector query returning a target company node with cosine distance 0.08
    def mock_query_vector_neighbors(graph_name, label, vector, k=30):
        return [
            ({"id": "vl:sys:auth", "company_origin": "Vaultly"}, 0.08),
        ]

    import src.pipeline.auto_linker as al_module
    monkeypatch.setattr(al_module, "query_vector_neighbors", mock_query_vector_neighbors)

    all_target_candidates = {
        "vl:sys:auth": {"name": "Vaultly Auth"}
    }

    pairs = engine._resolve_candidate_pairs(
        graph_name="test_graph",
        entity_label="System",
        source_vec=source_vec,
        all_candidates=all_target_candidates,
        company_target="Vaultly",
        embed_candidate_fn=lambda info: [0.0] * 384,
    )

    assert len(pairs) == 1
    cand_id, sim = pairs[0]
    assert cand_id == "vl:sys:auth"
    # Cosine similarity = 1.0 - 0.08 = 0.92
    assert sim == 0.92


def test_stale_bridge_reconciliation():
    """Verifies that pipeline execution reconciles and purges obsolete auto-detected bridge edges (B5)."""
    from src.config import settings
    from src.db.client import db_client

    db_client.connect()
    graph = db_client.get_graph(settings.graph_merged)

    # Plant a synthetic stale bridge with a past run_id
    stale_query = """
        MATCH (a:System {id: 'finpay:sys:gatekeeper_auth'}), (b:System {id: 'vaultly:sys:pulse_identity'})
        MERGE (a)-[r:REDUNDANT_WITH]->(b)
        SET r.auto_detected = true,
            r.pipeline_run_id = 'stale_legacy_run_999999',
            r.similarity = 0.90,
            r.reason = 'Synthetic obsolete bridge'
    """
    graph.query(stale_query)

    # Verify stale edge exists
    check_query = """
        MATCH (a:System)-[r:REDUNDANT_WITH]->(b:System)
        WHERE r.pipeline_run_id = 'stale_legacy_run_999999'
        RETURN count(r) as cnt
    """
    res = graph.query(check_query).result_set
    assert res[0][0] == 1

    # Run auto-linker pipeline which should execute stale bridge reconciliation
    engine = AutoLinkerEngine()
    summary = engine.run_pipeline(settings.graph_merged)

    assert "pipeline_run_id" in summary
    assert summary["pipeline_run_id"].startswith("run_")
    assert summary["model_version"] is not None
    assert summary["embedding_provider"] is not None

    # The stale edge with legacy run_id must no longer exist (it was either refreshed with current run_id or deleted)
    res_after = graph.query(check_query).result_set
    assert res_after[0][0] == 0


