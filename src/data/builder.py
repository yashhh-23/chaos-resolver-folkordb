"""Graph Builder orchestrator for multi-tenant M&A data ingestion.

Provides:
- Ingestion into finpay_graph, vaultly_graph, and merged_brain
- Export of runnable Cypher scripts (.cypher) and JSON payloads
- Schema index application across graphs
"""

from typing import Dict, Any, List, Tuple, Optional
from pathlib import Path

from src.config import settings
from src.utils.logger import logger
from src.schema.models import Relationship
from src.schema.cypher_schema import (
    INDEX_QUERIES,
    build_node_merge_cypher,
    build_relationship_merge_cypher,
)
from src.data.synthetic_data import (
    get_finpay_dataset,
    get_vaultly_dataset,
    get_shared_external_dependencies,
    get_ma_bridge_relationships,
)


def _convert_dataset_to_cypher(
    dataset: Dict[str, Any],
    include_external: bool = False,
    company_prefix: Optional[str] = None,
) -> List[str]:
    """Converts a company dataset dictionary into an ordered list of MERGE Cypher queries."""
    queries: List[str] = []

    # 1. Nodes
    node_categories: List[Tuple[str, str]] = [
        ("people", "Person"),
        ("teams", "Team"),
        ("systems", "System"),
        ("documents", "Document"),
        ("tickets", "Ticket"),
        ("decisions", "Decision"),
        ("policies", "Policy"),
    ]

    for category_key, label in node_categories:
        nodes = dataset.get(category_key, [])
        for node in nodes:
            props = node.model_dump()
            queries.append(build_node_merge_cypher(label, props))

    # 2. Relationships
    relationships: List[Relationship] = dataset.get("relationships", [])
    for rel in relationships:
        queries.append(
            build_relationship_merge_cypher(
                source_id=rel.source_id,
                target_id=rel.target_id,
                rel_type=rel.rel_type,
                properties=rel.properties,
            )
        )

    # 3. External nodes & dependencies if requested
    if include_external:
        shared = get_shared_external_dependencies()
        for ext_node in shared["external_apis"]:
            queries.append(build_node_merge_cypher("ExternalAPI", ext_node.model_dump()))
        for ext_rel in shared["relationships"]:
            if company_prefix is None or ext_rel.source_id.startswith(f"{company_prefix}:"):
                queries.append(
                    build_relationship_merge_cypher(
                        source_id=ext_rel.source_id,
                        target_id=ext_rel.target_id,
                        rel_type=ext_rel.rel_type,
                        properties=ext_rel.properties,
                    )
                )

    return queries


def generate_graph_cypher_scripts() -> Dict[str, List[str]]:
    """Generates the exact Cypher statements for all 3 graphs."""
    finpay_data = get_finpay_dataset()
    vaultly_data = get_vaultly_dataset()

    # 1. FinPay isolated graph (only FinPay nodes and calls)
    finpay_queries = list(INDEX_QUERIES)
    finpay_queries.extend(_convert_dataset_to_cypher(finpay_data, include_external=True, company_prefix="finpay"))

    # 2. Vaultly isolated graph (only Vaultly nodes and calls)
    vaultly_queries = list(INDEX_QUERIES)
    vaultly_queries.extend(_convert_dataset_to_cypher(vaultly_data, include_external=True, company_prefix="vaultly"))

    # 3. Merged brain graph (Both companies + cross-company bridge edges)
    merged_queries = list(INDEX_QUERIES)
    merged_queries.extend(_convert_dataset_to_cypher(finpay_data, include_external=False))
    merged_queries.extend(_convert_dataset_to_cypher(vaultly_data, include_external=False))

    # Add shared external dependencies
    shared = get_shared_external_dependencies()
    for ext_node in shared["external_apis"]:
        merged_queries.append(build_node_merge_cypher("ExternalAPI", ext_node.model_dump()))
    for ext_rel in shared["relationships"]:
        merged_queries.append(
            build_relationship_merge_cypher(
                source_id=ext_rel.source_id,
                target_id=ext_rel.target_id,
                rel_type=ext_rel.rel_type,
                properties=ext_rel.properties,
            )
        )

    # Add cross-company bridge edges
    bridge_rels = get_ma_bridge_relationships()
    for bridge_rel in bridge_rels:
        merged_queries.append(
            build_relationship_merge_cypher(
                source_id=bridge_rel.source_id,
                target_id=bridge_rel.target_id,
                rel_type=bridge_rel.rel_type,
                properties=bridge_rel.properties,
            )
        )

    return {
        settings.graph_finpay: finpay_queries,
        settings.graph_vaultly: vaultly_queries,
        settings.graph_merged: merged_queries,
    }


def export_cypher_files(output_dir: str = "artifacts/cypher") -> List[str]:
    """Exports generated Cypher queries to disk as runnable .cypher scripts."""
    scripts = generate_graph_cypher_scripts()
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    created_files = []

    for graph_name, queries in scripts.items():
        file_path = out_path / f"{graph_name}.cypher"
        content = f"// FalkorDB Ingestion Script for: {graph_name}\n"
        content += "// Generated by OrgBridge AI (M&A Chaos Resolver)\n\n"
        content += ";\n".join(queries) + ";\n"
        file_path.write_text(content, encoding="utf-8")
        created_files.append(str(file_path))
        logger.info(f"Exported Cypher script: {file_path} ({len(queries)} statements)")

    return created_files

