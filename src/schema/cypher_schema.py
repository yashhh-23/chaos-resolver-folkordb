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


# Strict, parameterized read-only query templates for supported recurring questions (B9)
CYPHER_TEMPLATES: Dict[str, Dict[str, Any]] = {
    "systems_by_domain": {
        "description": "Finds systems within a specific technical domain",
        "template": "MATCH (s:System) WHERE toLower(s.domain) = toLower($domain) RETURN s.id, s.name, s.domain, s.company_origin, s.tech LIMIT $limit",
        "required_params": ["domain"],
    },
    "policies_by_domain": {
        "description": "Finds active policies in a compliance domain",
        "template": "MATCH (p:Policy) WHERE toLower(p.domain) = toLower($domain) RETURN p.id, p.name, p.domain, p.status, p.description, p.company_origin LIMIT $limit",
        "required_params": ["domain"],
    },
    "person_by_role": {
        "description": "Finds personnel matching role keywords",
        "template": "MATCH (p:Person) WHERE toLower(p.role) CONTAINS toLower($role) RETURN p.id, p.name, p.role, p.department, p.company_origin LIMIT $limit",
        "required_params": ["role"],
    },
    "team_members": {
        "description": "Retrieves members of a specific team",
        "template": "MATCH (p:Person)-[:MEMBER_OF]->(t:Team) WHERE toLower(t.name) CONTAINS toLower($team) RETURN p.id, p.name, p.role, t.name, p.company_origin LIMIT $limit",
        "required_params": ["team"],
    },
    "system_by_name": {
        "description": "Finds a system by exact or partial name",
        "template": "MATCH (s:System) WHERE toLower(s.name) = toLower($name) OR toLower(s.id) = toLower($name) RETURN s.id, s.name, s.domain, s.company_origin, s.tech LIMIT $limit",
        "required_params": ["name"],
    },
}

WHITELISTED_READ_PROCEDURES = {
    "db.idx.vector.querynodes",
    "algo.wcc",
    "db.labels",
    "db.relationshiptypes",
}

PROHIBITED_MUTATION_KEYWORDS = [
    "CREATE",
    "MERGE",
    "DELETE",
    "DETACH",
    "SET",
    "REMOVE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "RENAME",
    "LOAD",
    "FOREACH",
    "GRANT",
    "DENY",
    "REVOKE",
]

ALLOWED_START_CLAUSES = ("MATCH", "OPTIONAL MATCH", "WITH", "UNWIND")


def validate_readonly_cypher(
    query: str,
    max_hops: int = 4,
    max_limit: int = 50,
    default_limit: int = 25,
) -> Dict[str, Any]:
    """Strictly validates and bounds Cypher queries to enforce a read-only security boundary (B9).

    Validations:
    1. Rejection of mutating, destructive, administrative, and external data-loading keywords outside string literals.
    2. Enforcing that queries begin with read-only entry clauses (MATCH, OPTIONAL MATCH, WITH, UNWIND).
    3. Mandatory presence of a valid RETURN clause.
    4. Capping procedure execution (CALL) strictly to whitelisted read-only procedures.
    5. Automatic bounding of variable-length graph traversals to max_hops.
    6. Strict ceiling on LIMIT clauses capped at max_limit.

    Returns:
        Dict with keys: valid (bool), sanitized_query (str), error_code (str or None), message (str or None).
    """
    cleaned = (query or "").strip()
    if not cleaned:
        return {
            "valid": False,
            "sanitized_query": "",
            "error_code": "EMPTY_QUERY",
            "message": "Query cannot be empty.",
        }

    # Strip quoted strings to inspect Cypher keywords without false positives on data literals
    stripped = re.sub(r"'([^'\\]|\\.)*'", "''", cleaned)
    stripped = re.sub(r'"([^"\\]|\\.)*"', '""', stripped)
    stripped_upper = stripped.upper()

    # 1. Prohibited mutating and DDL/DCL keywords check
    for kw in PROHIBITED_MUTATION_KEYWORDS:
        if re.search(rf"\b{kw}\b", stripped_upper):
            return {
                "valid": False,
                "sanitized_query": "",
                "error_code": "MUTATING_OPERATION_PROHIBITED",
                "message": f"Destructive or mutating Cypher clause '{kw}' is prohibited in read-only queries.",
            }

    # 2. Check procedure execution: only whitelisted procedures allowed
    call_matches = re.finditer(r"\bCALL\s+([a-zA-Z0-9_.]+)", stripped, re.IGNORECASE)
    for m in call_matches:
        proc_name = m.group(1).lower()
        if proc_name not in WHITELISTED_READ_PROCEDURES:
            return {
                "valid": False,
                "sanitized_query": "",
                "error_code": "DISALLOWED_PROCEDURE",
                "message": f"Execution of procedure '{proc_name}' via CALL is prohibited in read-only queries.",
            }

    # 3. Check starting clause: must start with read-only entry clause
    first_token_match = re.match(r"^\s*([a-zA-Z]+(?:\s+[a-zA-Z]+)?)", stripped)
    if not first_token_match:
        return {
            "valid": False,
            "sanitized_query": "",
            "error_code": "MALFORMED_QUERY",
            "message": "Query contains no recognizable Cypher statement.",
        }
    first_token = first_token_match.group(1).upper()
    if not any(first_token.startswith(c) for c in ALLOWED_START_CLAUSES):
        return {
            "valid": False,
            "sanitized_query": "",
            "error_code": "INVALID_ENTRY_CLAUSE",
            "message": f"Read-only queries must begin with one of: {', '.join(ALLOWED_START_CLAUSES)}. Found '{first_token}'.",
        }

    # 4. Mandatory RETURN clause
    if not re.search(r"\bRETURN\b", stripped_upper):
        return {
            "valid": False,
            "sanitized_query": "",
            "error_code": "MISSING_RETURN_CLAUSE",
            "message": "Read-only Cypher query must include a RETURN clause.",
        }

    # 5. Bound variable-length traversal paths
    sanitized = sanitize_cypher_query(cleaned, max_hops=max_hops, default_limit=default_limit)

    # 6. Enforce LIMIT ceiling (cannot exceed max_limit)
    limit_match = re.search(r"\bLIMIT\s+(\d+)\b", sanitized, re.IGNORECASE)
    if limit_match:
        limit_val = int(limit_match.group(1))
        if limit_val > max_limit:
            sanitized = re.sub(r"\bLIMIT\s+\d+\b", f"LIMIT {max_limit}", sanitized, flags=re.IGNORECASE)
    else:
        sanitized = f"{sanitized} LIMIT {default_limit}"

    return {
        "valid": True,
        "sanitized_query": sanitized,
        "error_code": None,
        "message": None,
    }


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
