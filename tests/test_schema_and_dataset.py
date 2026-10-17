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
    validate_readonly_cypher,
    CYPHER_TEMPLATES,
    build_node_merge_cypher,
    build_relationship_merge_cypher,
)
from src.data.synthetic_data import (
    get_finpay_dataset,
    get_vaultly_dataset,
    get_shared_external_dependencies,
    get_ma_bridge_relationships,
)
from src.data.builder import (
    generate_graph_cypher_scripts,
    validate_dataset_uniqueness_and_endpoints,
)


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


def test_validate_readonly_cypher_security_boundary():
    """Verifies that validate_readonly_cypher strictly rejects mutations, enforces read clauses, and bounds queries (B9)."""
    # 1. Prohibited mutating operations
    for bad_kw in ["CREATE (n:Person)", "MERGE (s:System)", "DELETE p", "DETACH DELETE n", "SET p.role = 'Admin'", "REMOVE p.tag"]:
        res = validate_readonly_cypher(f"MATCH (p:Person) {bad_kw} RETURN p")
        assert res["valid"] is False
        assert res["error_code"] == "MUTATING_OPERATION_PROHIBITED"

    # 2. Administrative procedures rejected
    bad_call = validate_readonly_cypher("CALL dbms.security.createUser('hacker', 'pass') RETURN 1")
    assert bad_call["valid"] is False
    assert bad_call["error_code"] in ("DISALLOWED_PROCEDURE", "INVALID_ENTRY_CLAUSE")

    # 3. Disallowed entry clause
    bad_start = validate_readonly_cypher("DROP INDEX ON :Person(id) RETURN 1")
    assert bad_start["valid"] is False

    # 4. Missing RETURN clause
    missing_ret = validate_readonly_cypher("MATCH (p:Person) WHERE p.name = 'Aarav'")
    assert missing_ret["valid"] is False
    assert missing_ret["error_code"] == "MISSING_RETURN_CLAUSE"

    # 5. Mutating keyword allowed inside data string literals without false positive
    safe_data = validate_readonly_cypher("MATCH (p:Policy) WHERE p.name = 'CREATE_NEW_ACCORD' RETURN p.name")
    assert safe_data["valid"] is True
    assert "LIMIT 25" in safe_data["sanitized_query"]

    # 6. LIMIT ceiling enforcement (max_limit = 50)
    huge_limit = validate_readonly_cypher("MATCH (p:Person) RETURN p.name LIMIT 9999", max_limit=50)
    assert huge_limit["valid"] is True
    assert "LIMIT 50" in huge_limit["sanitized_query"]


def test_parameterized_cypher_templates():
    """Verifies predefined query templates catalog and execution structure (B9)."""
    assert "systems_by_domain" in CYPHER_TEMPLATES
    assert "policies_by_domain" in CYPHER_TEMPLATES
    assert "person_by_role" in CYPHER_TEMPLATES
    assert "team_members" in CYPHER_TEMPLATES
    assert "system_by_name" in CYPHER_TEMPLATES

    tmpl = CYPHER_TEMPLATES["systems_by_domain"]
    assert "$domain" in tmpl["template"]
    assert "$limit" in tmpl["template"]
    assert "RETURN" in tmpl["template"]


def test_node_merge_preserves_runtime_state_and_destructive_baseline():
    """Verifies B11: Selective property updates preserve runtime status & fields, while destructive mode restores baseline."""
    pol_props = {
        "id": "finpay:pol:session_security",
        "name": "Strict Ephemeral Session Standard",
        "status": "ACTIVE",
        "domain": "Authentication",
    }

    # 1. Ordinary ingestion (preserve_runtime_state=True)
    ordinary_cypher = build_node_merge_cypher("Policy", pol_props, preserve_runtime_state=True)
    assert "ON MATCH SET" in ordinary_cypher
    assert "n +=" in ordinary_cypher
    # Ensure mutated statuses like DEPRECATED are protected from being overwritten to ACTIVE
    assert "CASE WHEN n.status IN ['DEPRECATED', 'MERGED', 'RESOLVED'] THEN n.status ELSE 'ACTIVE' END" in ordinary_cypher

    # Node without status uses n += for all props
    person_props = {"id": "finpay:person:aarav", "name": "Aarav Mehta"}
    person_cypher = build_node_merge_cypher("Person", person_props, preserve_runtime_state=True)
    assert "ON MATCH SET n +=" in person_cypher
    assert "CASE WHEN" not in person_cypher

    # 2. Destructive baseline restoration (preserve_runtime_state=False)
    destructive_cypher = build_node_merge_cypher("Policy", pol_props, preserve_runtime_state=False)
    assert "ON MATCH SET n = {" in destructive_cypher
    assert "CASE WHEN" not in destructive_cypher


def test_relationship_builder_label_constraints_and_endpoint_verification():
    """Verifies B12: Relationship builder constrains endpoint labels and verifies created_count."""
    # 1. Inferred endpoint labels from IDs
    cypher = build_relationship_merge_cypher(
        source_id="finpay:sys:gatekeeper_auth",
        target_id="vaultly:sys:pulse_identity",
        rel_type="REDUNDANT_WITH",
    )
    assert "MATCH (a:System {id: 'finpay:sys:gatekeeper_auth'}), (b:System {id: 'vaultly:sys:pulse_identity'})" in cypher
    assert "RETURN count(r) as created_count" in cypher

    # 2. Inferred endpoint labels for Person to Team
    member_cypher = build_relationship_merge_cypher(
        source_id="finpay:person:aarav_mehta",
        target_id="finpay:team:secarch",
        rel_type="MEMBER_OF",
    )
    assert "MATCH (a:Person {id: 'finpay:person:aarav_mehta'}), (b:Team {id: 'finpay:team:secarch'})" in member_cypher
    assert "RETURN count(r) as created_count" in member_cypher

    # 3. Explicit label override
    override_cypher = build_relationship_merge_cypher(
        source_id="custom:id:1",
        target_id="custom:id:2",
        rel_type="SUPERSEDES",
        source_label="Policy",
        target_label="Decision",
    )
    assert "MATCH (a:Policy {id: 'custom:id:1'}), (b:Decision {id: 'custom:id:2'})" in override_cypher


def test_dataset_uniqueness_and_endpoint_validation():
    """Verifies B12: Dataset validation catches duplicate entity IDs and missing relationship endpoints."""
    from src.schema.models import Relationship

    # 1. Duplicate entity ID detection
    dataset_with_dup = {
        "people": [
            Person(id="finpay:person:dup_1", name="User A", role="Eng", department="Core", email="a@finpay.com", company_origin=CompanyOrigin.FINPAY),
            Person(id="finpay:person:dup_1", name="User B", role="Eng", department="Core", email="b@finpay.com", company_origin=CompanyOrigin.FINPAY),
        ],
        "relationships": [],
    }
    with pytest.raises(ValueError, match="Duplicate entity ID detected"):
        validate_dataset_uniqueness_and_endpoints(dataset_with_dup)

    # 2. Missing relationship endpoint detection
    dataset_with_missing_endpoint = {
        "people": [
            Person(id="finpay:person:valid_user", name="User A", role="Eng", department="Core", email="a@finpay.com", company_origin=CompanyOrigin.FINPAY),
        ],
        "relationships": [
            Relationship(source_id="finpay:person:valid_user", target_id="finpay:team:non_existent", rel_type="MEMBER_OF"),
        ],
    }
    with pytest.raises(ValueError, match="Referential integrity failure.*missing target endpoint"):
        validate_dataset_uniqueness_and_endpoints(dataset_with_missing_endpoint)


