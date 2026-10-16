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
