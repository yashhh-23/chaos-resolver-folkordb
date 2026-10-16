"""Unit tests for Phase 1 Schema Design and Synthetic M&A Dataset."""

import pytest
from src.schema.models import (
    CompanyOrigin,
    StatusEnum,
    TicketSeverity,
    Person,
    System,
    Policy,
    Decision,
)
from src.schema.cypher_schema import (
    ALLOWED_LABELS,
    ALLOWED_RELATIONSHIPS,
    INDEX_QUERIES,
    sanitize_cypher_query,
    build_node_merge_cypher,
    build_relationship_merge_cypher,
)
from src.data.synthetic_data import (
    get_finpay_dataset,
    get_vaultly_dataset,
    get_shared_external_dependencies,
    get_ma_bridge_relationships,
)
from src.data.builder import generate_graph_cypher_scripts


def test_allowed_labels_and_relationships():
    assert "Person" in ALLOWED_LABELS
    assert "System" in ALLOWED_LABELS
    assert "Policy" in ALLOWED_LABELS
    assert "Decision" in ALLOWED_LABELS
    assert "REDUNDANT_WITH" in ALLOWED_RELATIONSHIPS
    assert "CONFLICTS_WITH" in ALLOWED_RELATIONSHIPS
    assert "SUPERSEDES" in ALLOWED_RELATIONSHIPS
    assert CompanyOrigin.UNIFIED.value == "Unified"


def test_cypher_query_sanitizer():
    # Test bounding of unbounded hop queries
    unbounded = "MATCH (a:Person)-[*]-(b:System) RETURN a, b"
    bounded = sanitize_cypher_query(unbounded, max_hops=4)
    assert "[*1..4]" in bounded
    assert "LIMIT 25" in bounded

    # Test bounding of [*..10], [r*], [:OWNS*], [r:OWNS*..10]
    assert "[*1..4]" in sanitize_cypher_query("MATCH (a)-[*..10]->(b) RETURN a")
    assert "[r*1..4]" in sanitize_cypher_query("MATCH (a)-[r*]->(b) RETURN a")
    assert "[:OWNS*1..4]" in sanitize_cypher_query("MATCH (a)-[:OWNS*]->(b) RETURN a")
    assert "[r:OWNS*1..4]" in sanitize_cypher_query("MATCH (a)-[r:OWNS*..12]->(b) RETURN a")

    # Test preserving queries that already have a limit
    already_limited = "MATCH (n:Person) RETURN n LIMIT 10"
    sanitized = sanitize_cypher_query(already_limited)
    assert sanitized.endswith("LIMIT 10")


def test_build_node_merge_cypher():
    p = Person(
        id="finpay:person:test_user",
        name="Test User",
        role="Engineer",
        department="Core",
        email="test@finpay.com",
        company_origin=CompanyOrigin.FINPAY,
        pagerank=0.5,
    )
    cypher = build_node_merge_cypher("Person", p.model_dump())
    assert "MERGE (n:Person {id: 'finpay:person:test_user'})" in cypher
    assert "test@finpay.com" in cypher
    assert "FinPay" in cypher

    # Test backslash and single quote escaping
    escaped_cypher = build_node_merge_cypher("Person", {"id": "test\\id", "name": "O'Connor\\"})
    assert "test\\\\id" in escaped_cypher
    assert "O\\'Connor\\\\" in escaped_cypher


def test_build_relationship_merge_cypher():
    cypher = build_relationship_merge_cypher(
        source_id="finpay:sys:gatekeeper_auth",
        target_id="vaultly:sys:pulse_identity",
        rel_type="REDUNDANT_WITH",
        properties={"similarity": 0.93, "reason": "OAuth parity"},
    )
    assert "REDUNDANT_WITH" in cypher
    assert "finpay:sys:gatekeeper_auth" in cypher
    assert "vaultly:sys:pulse_identity" in cypher
    assert "0.93" in cypher

    # Test backslash and single quote escaping in relationship
    rel_escaped = build_relationship_merge_cypher(
        source_id="finpay:sys:a\\1",
        target_id="vaultly:sys:b'2",
        rel_type="CALLS",
        properties={"path": "C:\\logs\\test'"},
    )
    assert "finpay:sys:a\\\\1" in rel_escaped
    assert "vaultly:sys:b\\'2" in rel_escaped
    assert "C:\\\\logs\\\\test\\'" in rel_escaped


def test_entity_collision_prevention():
    """Validates Edge Case #1: Same employee / service name across companies must have distinct IDs."""
    finpay = get_finpay_dataset()
    vaultly = get_vaultly_dataset()

    fp_rahuls = [p for p in finpay["people"] if p.name == "Rahul Sharma"]
    vl_rahuls = [p for p in vaultly["people"] if p.name == "Rahul Sharma"]

    assert len(fp_rahuls) == 1
    assert len(vl_rahuls) == 1
    assert fp_rahuls[0].id != vl_rahuls[0].id
    assert fp_rahuls[0].company_origin == CompanyOrigin.FINPAY
    assert vl_rahuls[0].company_origin == CompanyOrigin.VAULTLY

    fp_core = [s for s in finpay["systems"] if s.name == "core-api"]
    vl_core = [s for s in vaultly["systems"] if s.name == "core-api"]

    assert len(fp_core) == 1
    assert len(vl_core) == 1
    assert fp_core[0].id != vl_core[0].id
    assert fp_core[0].company_origin == CompanyOrigin.FINPAY
    assert vl_core[0].company_origin == CompanyOrigin.VAULTLY


def test_policy_and_decision_lineage():
    """Validates Edge Case #3: Policy Contradictions & Temporal Precedence."""
    finpay = get_finpay_dataset()
    vaultly = get_vaultly_dataset()

    for d in finpay["decisions"] + vaultly["decisions"]:
        assert d.effective_date != ""
        assert d.authority_level != ""
        assert d.status in [StatusEnum.ACTIVE, StatusEnum.DEPRECATED, StatusEnum.UNDER_REVIEW]
        assert d.source != ""

    for pol in finpay["policies"] + vaultly["policies"]:
        assert pol.effective_date != ""
        assert pol.authority_level != ""
        assert pol.status in [StatusEnum.ACTIVE, StatusEnum.DEPRECATED, StatusEnum.UNDER_REVIEW]


def test_relationship_referential_integrity():
    """Ensures every internal edge points to an existing node ID within the dataset."""
    for company_name, get_dataset_fn in [("FinPay", get_finpay_dataset), ("Vaultly", get_vaultly_dataset)]:
        data = get_dataset_fn()
        valid_ids = set()
        for key in ["people", "teams", "systems", "documents", "tickets", "decisions", "policies"]:
            for item in data[key]:
                valid_ids.add(item.id)

        for rel in data["relationships"]:
            assert rel.source_id in valid_ids, f"[{company_name}] Missing source_id: {rel.source_id}"
            assert rel.target_id in valid_ids, f"[{company_name}] Missing target_id: {rel.target_id}"


def test_bridge_relationships():
    """Validates cross-company bridges connect FinPay entities to Vaultly entities."""
    bridges = get_ma_bridge_relationships()
    assert len(bridges) > 0

    redundant_edges = [b for b in bridges if b.rel_type == "REDUNDANT_WITH"]
    conflict_edges = [b for b in bridges if b.rel_type == "CONFLICTS_WITH"]

    assert len(redundant_edges) >= 3
    assert len(conflict_edges) >= 4

    for bridge in bridges:
        assert (
            (bridge.source_id.startswith("finpay:") and bridge.target_id.startswith("vaultly:"))
            or (bridge.source_id.startswith("vaultly:") and bridge.target_id.startswith("finpay:"))
        )


def test_cypher_scripts_generation():
    scripts = generate_graph_cypher_scripts()
    assert "finpay_graph" in scripts
    assert "vaultly_graph" in scripts
    assert "merged_brain" in scripts

    assert len(scripts["finpay_graph"]) > 50
    assert len(scripts["vaultly_graph"]) > 50
    assert len(scripts["merged_brain"]) > 100
