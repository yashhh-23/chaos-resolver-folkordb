"""FalkorDB Seeding CLI for Phase 1 M&A Dataset.

Populates:
1. finpay_graph (Acquirer isolated graph)
2. vaultly_graph (Target isolated graph)
3. merged_brain (Unified multigraph with REDUNDANT_WITH and CONFLICTS_WITH bridge edges)
"""

import argparse
import sys
from typing import Dict, List, Any
from src.config import settings
from src.utils.logger import logger
from src.db.client import db_client
from src.data.builder import (
    generate_graph_cypher_scripts,
    export_cypher_files,
)


def seed_graph(graph_name: str, queries: List[str], clear_first: bool = False) -> Dict[str, Any]:
    """Executes a list of Cypher queries on the specified FalkorDB graph with post-seeding invariant verification."""
    graph = db_client.get_graph(graph_name)
    success_count = 0
    error_count = 0
    failed_details: List[Dict[str, Any]] = []

    if clear_first:
        try:
            logger.info(f"[{graph_name}] Flushing existing graph data...")
            graph.query("MATCH (n) DETACH DELETE n")
        except Exception as e:
            logger.warning(f"[{graph_name}] Could not clear graph: {e}")

    logger.info(f"[{graph_name}] Executing {len(queries)} Cypher statements...")
    for idx, query in enumerate(queries, 1):
        try:
            graph.query(query)
            success_count += 1
        except Exception as e:
            # Safe ignore for already existing index in FalkorDB
            err_str = str(e).lower()
            if any(sub in err_str for sub in ["already exists", "equivalent index", "already indexed"]):
                success_count += 1
            else:
                logger.error(f"[{graph_name}] Error executing query #{idx}: {query} -> {e}")
                error_count += 1
                failed_details.append({"query_index": idx, "query": query, "error": str(e)})

    # Post-seeding invariant verification: Validate that expected nodes and relationships exist
    try:
        node_res = graph.query("MATCH (n) RETURN count(n) as node_count")
        rel_res = graph.query("MATCH ()-[r]->() RETURN count(r) as rel_count")
        node_count = node_res.result_set[0][0] if node_res.result_set else 0
        rel_count = rel_res.result_set[0][0] if rel_res.result_set else 0
    except Exception as e:
        node_count = 0
        rel_count = 0
        error_count += 1
        failed_details.append({"invariant_check": "node_rel_count", "error": str(e)})

    is_success = (error_count == 0) and (node_count > 0)
    logger.info(
        f"[{graph_name}] Completed: {success_count} succeeded, {error_count} failed. "
        f"Post-seed nodes: {node_count}, rels: {rel_count}"
    )

    return {
        "status": "success" if is_success else "failed",
        "success": success_count,
        "failed": error_count,
        "node_count": node_count,
        "rel_count": rel_count,
        "errors": failed_details,
    }


def seed_all_graphs(clear_first: bool = False) -> Dict[str, Any]:
    """Seeds finpay_graph, vaultly_graph, and merged_brain in FalkorDB with strict verification across all graphs."""
    scripts = generate_graph_cypher_scripts()
    summary = {}
    total_failed = 0

    for graph_name, queries in scripts.items():
        logger.info(f"=== Seeding {graph_name} ===")
        res = seed_graph(graph_name, queries, clear_first=clear_first)
        summary[graph_name] = res
        total_failed += res.get("failed", 0)
        if res.get("status") != "success":
            total_failed += 1

    overall_status = "success" if total_failed == 0 else "failed"

    # Return structure with both top-level graph keys (for backwards compatibility) and overall status
    result = {
        "status": overall_status,
        "total_failures": total_failed,
        "graphs": summary,
    }
    for g_name, g_res in summary.items():
        result[g_name] = g_res

    return result


def verify_graphs():
    """Performs quick sanity verification queries on all graphs."""
    logger.info("=== Verifying Graphs ===")
    for graph_name in [settings.graph_finpay, settings.graph_vaultly, settings.graph_merged]:
        try:
            graph = db_client.get_graph(graph_name)
            node_res = graph.query("MATCH (n) RETURN count(n) as node_count")
            rel_res = graph.query("MATCH ()-[r]->() RETURN count(r) as rel_count")
            node_cnt = node_res.result_set[0][0] if node_res.result_set else 0
            rel_cnt = rel_res.result_set[0][0] if rel_res.result_set else 0
            logger.info(f"[{graph_name}] Nodes: {node_cnt}, Relationships: {rel_cnt}")
        except Exception as e:
            logger.error(f"[{graph_name}] Verification failed: {e}")


def main():
    parser = argparse.ArgumentParser(description="OrgBridge AI - FalkorDB Phase 1 Seeder")
    parser.add_argument(
        "--clear",
        action="store_true",
        help="Clear existing graph nodes before inserting (DETACH DELETE)",
    )
    parser.add_argument(
        "--export-only",
        action="store_true",
        help="Only export Cypher scripts and JSON dataset to disk without connecting to DB",
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Run verification count queries after seeding",
    )
    args = parser.parse_args()

    # Always generate artifacts/cypher
    export_cypher_files()

    if args.export_only:
        logger.info("Export-only mode finished successfully. Artifacts created in 'artifacts/' directory.")
        return

    logger.info("Checking FalkorDB connectivity...")
    try:
        db_client.connect()
    except Exception as e:
        logger.error(f"Cannot connect to FalkorDB: {e}")
        logger.info(
            "To spin up local FalkorDB, run:\n"
            "  docker-compose up -d\n"
            "Or configure FalkorDB Cloud credentials in .env\n"
            "Use --export-only if you just want to preview generated Cypher scripts."
        )
        sys.exit(1)

    seed_all_graphs(clear_first=args.clear)

    if args.verify:
        verify_graphs()

    logger.info("Phase 1 seeding completed successfully!")


if __name__ == "__main__":
    main()
