"""Cypher schema definitions, indexing rules, and query constraints for FalkorDB."""

from typing import List, Dict, Any
import re

# Strict label and relationship contracts for the M&A Brain
ALLOWED_LABELS = [
    "Person",
    "Team",
    "System",
    "Document",
    "Ticket",
    "Decision",
    "Policy",
    "ExternalAPI",
]

ALLOWED_RELATIONSHIPS = [
    "OWNS",
    "MEMBER_OF",
    "AUTHORED",
    "RESOLVED",
    "AFFECTS",
    "GOVERNED_BY",
    "DEPENDS_ON",
    "CALLS",
    "DERIVED_FROM",
    "REDUNDANT_WITH",
    "CONFLICTS_WITH",
]

INDEX_QUERIES: List[str] = [
    "CREATE INDEX FOR (p:Person) ON (p.id)",
    "CREATE INDEX FOR (p:Person) ON (p.company_origin)",
    "CREATE INDEX FOR (s:System) ON (s.id)",
    "CREATE INDEX FOR (s:System) ON (s.company_origin)",
    "CREATE INDEX FOR (t:Team) ON (t.id)",
    "CREATE INDEX FOR (doc:Document) ON (doc.id)",
    "CREATE INDEX FOR (tk:Ticket) ON (tk.id)",
    "CREATE INDEX FOR (d:Decision) ON (d.id)",
    "CREATE INDEX FOR (pol:Policy) ON (pol.id)",
]


def sanitize_cypher_query(query: str, max_hops: int = 4, default_limit: int = 25) -> str:
    """Enforces hop-depth protection and LIMIT clauses on Cypher queries.

    Guards against LLM Cypher Hallucination & Infinite Traversal Loops (Edge Case #4).
    Replaces unbound variable-length paths [*] or [*..N] with bounded [*1..max_hops],
    and appends a LIMIT clause if not present.
    """
    cleaned = query.strip()

    # Replace unbounded [*] with bounded [*1..max_hops]
    cleaned = re.sub(r'\[\*\]', f'[*1..{max_hops}]', cleaned)

    # Ensure query has LIMIT if it's a MATCH / RETURN query and doesn't already have one
    if "RETURN" in cleaned.upper() and "LIMIT" not in cleaned.upper():
        cleaned = f"{cleaned} LIMIT {default_limit}"

    return cleaned


def escape_cypher_value(val: Any) -> str:
    """Escapes backslashes and single quotes in string values for safe Cypher query interpolation."""
    s = val if isinstance(val, str) else str(val)
    return s.replace("\\", "\\\\").replace("'", "\\'")


def build_node_merge_cypher(label: str, properties: Dict[str, Any]) -> str:
    """Builds a MERGE Cypher statement for a node using its unique ID."""
    if label not in ALLOWED_LABELS:
        raise ValueError(f"Label '{label}' is not in allowed schema labels: {ALLOWED_LABELS}")

    props_strings = []
    for k, v in properties.items():
        if isinstance(v, str):
            escaped = escape_cypher_value(v)
            props_strings.append(f"{k}: '{escaped}'")
        elif isinstance(v, (int, float)):
            props_strings.append(f"{k}: {v}")
        elif isinstance(v, bool):
            props_strings.append(f"{k}: {str(v).lower()}")
        elif v is None:
            continue
        else:
            escaped = escape_cypher_value(v)
            props_strings.append(f"{k}: '{escaped}'")

    props_repr = "{" + ", ".join(props_strings) + "}"
    node_id = escape_cypher_value(properties.get("id", ""))
    return f"MERGE (n:{label} {{id: '{node_id}'}}) ON CREATE SET n = {props_repr} ON MATCH SET n = {props_repr}"


def build_relationship_merge_cypher(
    source_id: str,
    target_id: str,
    rel_type: str,
    properties: Dict[str, Any] = None,
) -> str:
    """Builds a MERGE Cypher statement for a relationship between two nodes."""
    if rel_type not in ALLOWED_RELATIONSHIPS:
        raise ValueError(f"Relationship '{rel_type}' not in allowed relationships: {ALLOWED_RELATIONSHIPS}")

    src_escaped = escape_cypher_value(source_id)
    tgt_escaped = escape_cypher_value(target_id)

    prop_assigns = ""
    if properties:
        items = []
        for k, v in properties.items():
            if isinstance(v, str):
                escaped = escape_cypher_value(v)
                items.append(f"r.{k} = '{escaped}'")
            elif isinstance(v, (int, float)):
                items.append(f"r.{k} = {v}")
            elif isinstance(v, bool):
                items.append(f"r.{k} = {str(v).lower()}")
            else:
                escaped = escape_cypher_value(v)
                items.append(f"r.{k} = '{escaped}'")
        if items:
            prop_assigns = " ON CREATE SET " + ", ".join(items) + " ON MATCH SET " + ", ".join(items)

    return (
        f"MATCH (a {{id: '{src_escaped}'}}), (b {{id: '{tgt_escaped}'}}) "
        f"MERGE (a)-[r:{rel_type}]->(b){prop_assigns}"
    )
