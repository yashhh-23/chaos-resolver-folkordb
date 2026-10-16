"""Vector index manager and embedding population pipeline for FalkorDB nodes."""

from typing import List, Dict, Any, Tuple
from src.utils.logger import logger
from src.db.client import db_client
from src.embeddings.service import embedding_service

VECTOR_INDEX_COMMANDS = [
    "CREATE VECTOR INDEX FOR (s:System) ON (s.embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'}",
    "CREATE VECTOR INDEX FOR (p:Policy) ON (p.embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'}",
    "CREATE VECTOR INDEX FOR (d:Decision) ON (d.embedding) OPTIONS {dimension: 384, similarityFunction: 'cosine'}",
]


def ensure_vector_indexes(graph_name: str) -> List[str]:
    """Ensures vector indexes are created on System, Policy, and Decision nodes."""
    graph = db_client.get_graph(graph_name)
    results = []

    for cmd in VECTOR_INDEX_COMMANDS:
        try:
            graph.query(cmd)
            results.append(f"SUCCESS: {cmd}")
            logger.info(f"[{graph_name}] Created vector index: {cmd[:45]}...")
        except Exception as e:
            err = str(e).lower()
            if "already exists" in err or "equivalent" in err:
                results.append(f"EXISTS: {cmd[:45]}")
            else:
                logger.warning(f"[{graph_name}] Vector index warning: {e}")
                results.append(f"WARN: {e}")

    return results


def system_embedding_text(name: str, domain: str, tech: str, description: str) -> str:
    """Generates canonical text representation for System embedding."""
    return f"System: {name} | Domain: {domain} | Tech: {tech} | Description: {description}"


def policy_embedding_text(name: str, domain: str, description: str) -> str:
    """Generates canonical text representation for Policy embedding."""
    return f"Policy: {name} | Domain: {domain} | Description: {description}"


def decision_embedding_text(summary: str, authority: str = "", source: str = "") -> str:
    """Generates canonical text representation for Decision embedding."""
    return f"Decision: {summary} | Authority: {authority} | Source: {source}"


def populate_node_embeddings(graph_name: str) -> Dict[str, int]:
    """Computes and updates dense vector embeddings on all System, Policy, and Decision nodes."""
    graph = db_client.get_graph(graph_name)
    counts = {"systems": 0, "policies": 0, "decisions": 0}

    # 1. Systems
    sys_res = graph.query("MATCH (s:System) RETURN s.id, s.name, s.domain, s.description, s.tech")
    for row in sys_res.result_set:
        sys_id, name, domain, desc, tech = row[0], row[1], row[2], row[3], row[4]
        text_repr = system_embedding_text(name, domain, tech, desc)
        vec = embedding_service.embed_text(text_repr)
        graph.query(
            "MATCH (s:System {id: $id}) SET s.embedding = vecf32($vec)",
            {"id": sys_id, "vec": vec},
        )
        counts["systems"] += 1

    # 2. Policies
    pol_res = graph.query("MATCH (p:Policy) RETURN p.id, p.name, p.domain, p.description")
    for row in pol_res.result_set:
        pol_id, name, domain, desc = row[0], row[1], row[2], row[3]
        text_repr = policy_embedding_text(name, domain, desc)
        vec = embedding_service.embed_text(text_repr)
        graph.query(
            "MATCH (p:Policy {id: $id}) SET p.embedding = vecf32($vec)",
            {"id": pol_id, "vec": vec},
        )
        counts["policies"] += 1

    # 3. Decisions
    dec_res = graph.query("MATCH (d:Decision) RETURN d.id, d.summary, d.authority_level, d.source")
    for row in dec_res.result_set:
        dec_id, summary, auth, source = row[0], row[1], row[2], row[3]
        text_repr = decision_embedding_text(summary, auth, source)
        vec = embedding_service.embed_text(text_repr)
        graph.query(
            "MATCH (d:Decision {id: $id}) SET d.embedding = vecf32($vec)",
            {"id": dec_id, "vec": vec},
        )
        counts["decisions"] += 1

    logger.info(
        f"[{graph_name}] Embedded {counts['systems']} systems, "
        f"{counts['policies']} policies, and {counts['decisions']} decisions."
    )
    return counts


def query_vector_neighbors(
    graph_name: str,
    label: str,
    query_vector: List[float],
    k: int = 5,
) -> List[Tuple[Any, float]]:
    """Performs native FalkorDB vector similarity search using db.idx.vector.queryNodes."""
    graph = db_client.get_graph(graph_name)
    query = f"""
        CALL db.idx.vector.queryNodes('{label}', 'embedding', $k, vecf32($vec))
        YIELD node, score
        RETURN node, score
    """
    res = graph.query(query, {"k": k, "vec": query_vector})
    results = []
    for row in res.result_set:
        results.append((row[0], float(row[1])))
    return results
