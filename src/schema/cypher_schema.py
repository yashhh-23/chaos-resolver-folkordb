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
    "SUPERSEDES",
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
    Replaces unbound or excessive variable-length paths [*], [*..N], [r*], [:REL*]
    with bounded [*1..max_hops], and appends a LIMIT clause if not present.
    """
    cleaned = query.strip()

    # Match variable-length patterns: [*], [*..10], [r*], [:OWNS*], [r:OWNS*..10], etc.
    var_len_pattern = r'\[\s*([a-zA-Z0-9_]*)\s*(?::([a-zA-Z0-9_|]+))?\s*\*\s*(\d*(?:\.\.\d*)?)?\s*\]'

    def _bound_var_hops(match: re.Match) -> str:
        var = match.group(1) or ""
        rel = match.group(2)
        range_str = match.group(3) or ""
        prefix = f"{var}:{rel}" if rel else var

        if not range_str:
            return f"[{prefix}*1..{max_hops}]"
        elif range_str.startswith(".."):
            up = int(range_str[2:])
            return f"[{prefix}*1..{min(up, max_hops)}]"
        elif range_str.endswith(".."):
            low = min(int(range_str[:-2]), max_hops)
            return f"[{prefix}*{low}..{max_hops}]"
        elif ".." in range_str:
            parts = range_str.split("..")
            low = min(int(parts[0]), max_hops)
            up = min(int(parts[1]), max_hops)
            return f"[{prefix}*{low}..{up}]"
        else:
            val = int(range_str)
            return f"[{prefix}*{min(val, max_hops)}]"

    cleaned = re.sub(var_len_pattern, _bound_var_hops, cleaned)

    # Ensure query has LIMIT if it's a MATCH / RETURN query and doesn't already have one
    if "RETURN" in cleaned.upper() and "LIMIT" not in cleaned.upper():
        cleaned = f"{cleaned} LIMIT {default_limit}"

    return cleaned


def escape_cypher_value(val: Any) -> str:
    """Escapes backslashes and single quotes in string values for safe Cypher query interpolation."""
    s = val if isinstance(val, str) else str(val)
    return s.replace("\\", "\\\\").replace("'", "\\'")


def format_cypher_value(val: Any) -> str:
    """Formats a Python scalar/list value into a Cypher literal string representation."""
    if isinstance(val, bool):
        return str(val).lower()
    elif isinstance(val, (int, float)):
        return str(val)
    elif isinstance(val, list):
        escaped_list = [
            f"'{escape_cypher_value(item)}'" if isinstance(item, str) else str(item)
            for item in val
        ]
        return f"[{', '.join(escaped_list)}]"
    elif val is None:
        return "null"
    return f"'{escape_cypher_value(val)}'"


def format_cypher_properties(properties: Dict[str, Any], prefix: str = "") -> str:
    """Formats and escapes a properties dictionary into Cypher property syntax.

    If prefix is empty (default), returns Cypher object syntax '{k: v, ...}'.
    If prefix is provided (e.g. 'r.'), returns comma-separated assignments: 'r.k = v, ...'.
    """
    if not properties:
        return "" if prefix else "{}"

    if prefix:
        assignments = [
            f"{prefix}{k} = {format_cypher_value(v)}"
            for k, v in properties.items()
            if v is not None
        ]
        return ", ".join(assignments)

    props = [
        f"{k}: {format_cypher_value(v)}"
        for k, v in properties.items()
        if v is not None
    ]
    return "{" + ", ".join(props) + "}"


def build_node_merge_cypher(label: str, properties: Dict[str, Any]) -> str:
    """Builds a MERGE Cypher statement for a node using its unique ID."""
    if label not in ALLOWED_LABELS:
        raise ValueError(f"Label '{label}' is not in allowed schema labels: {ALLOWED_LABELS}")

    props_repr = format_cypher_properties(properties)
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
        assignments = format_cypher_properties(properties, prefix="r.")
        if assignments:
            prop_assigns = f" ON CREATE SET {assignments} ON MATCH SET {assignments}"

    return (
        f"MATCH (a {{id: '{src_escaped}'}}), (b {{id: '{tgt_escaped}'}}) "
        f"MERGE (a)-[r:{rel_type}]->(b){prop_assigns}"
    )
