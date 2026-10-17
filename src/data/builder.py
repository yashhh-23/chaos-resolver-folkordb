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

PROJECT_ROOT = Path(__file__).resolve().parents[2]
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


def validate_dataset_uniqueness_and_endpoints(
    dataset: Dict[str, Any],
    include_external: bool = False,
    extra_nodes: Optional[List[Any]] = None,
    extra_relationships: Optional[List[Relationship]] = None,
) -> None:
    """Enforces node ID uniqueness and referential integrity of relationship endpoints (B12)."""
    seen_ids = set()
    all_node_ids = set()

    node_categories: List[Tuple[str, str]] = [
        ("people", "Person"),
        ("teams", "Team"),
        ("systems", "System"),
        ("documents", "Document"),
        ("tickets", "Ticket"),
        ("decisions", "Decision"),
        ("policies", "Policy"),
    ]

    for cat, _ in node_categories:
        for node in dataset.get(cat, []):
            nid = getattr(node, "id", None) or (node.get("id") if isinstance(node, dict) else None)
            if not nid:
                continue
            if nid in seen_ids:
                raise ValueError(f"Duplicate entity ID detected in dataset: '{nid}' in category '{cat}'")
            seen_ids.add(nid)
            all_node_ids.add(nid)

    if include_external:
        shared = get_shared_external_dependencies()
        for ext in shared.get("external_apis", []):
            nid = getattr(ext, "id", None) or (ext.get("id") if isinstance(ext, dict) else None)
            if nid:
                all_node_ids.add(nid)

    if extra_nodes:
        for en in extra_nodes:
            nid = getattr(en, "id", None) or (en.get("id") if isinstance(en, dict) else None)
            if nid:
                all_node_ids.add(nid)

    # Validate relationship endpoints
    relationships = list(dataset.get("relationships", []))
    if extra_relationships:
        relationships.extend(extra_relationships)

    for rel in relationships:
        if rel.source_id not in all_node_ids:
            raise ValueError(
                f"Referential integrity failure: Relationship '{rel.rel_type}' references "
                f"missing source endpoint ID '{rel.source_id}'"
            )
        if rel.target_id not in all_node_ids:
            raise ValueError(
                f"Referential integrity failure: Relationship '{rel.rel_type}' references "
                f"missing target endpoint ID '{rel.target_id}'"
            )


def _convert_dataset_to_cypher(
    dataset: Dict[str, Any],
    include_external: bool = False,
    company_prefix: Optional[str] = None,
    preserve_runtime_state: bool = True,
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
            queries.append(build_node_merge_cypher(label, props, preserve_runtime_state=preserve_runtime_state))

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
            queries.append(build_node_merge_cypher("ExternalAPI", ext_node.model_dump(), preserve_runtime_state=preserve_runtime_state))
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


def generate_graph_cypher_scripts(preserve_runtime_state: bool = True) -> Dict[str, List[str]]:
    """Generates the exact Cypher statements for all 3 graphs after validating ID uniqueness and endpoints."""
    finpay_data = get_finpay_dataset()
    vaultly_data = get_vaultly_dataset()
    shared = get_shared_external_dependencies()
    bridge_rels = get_ma_bridge_relationships()

    # Pre-generation dataset integrity verification (B12)
    validate_dataset_uniqueness_and_endpoints(finpay_data, include_external=True)
    validate_dataset_uniqueness_and_endpoints(vaultly_data, include_external=True)

    # Validate merged dataset integrity across both companies and bridge relationships
    merged_extra_nodes = [
        node.model_dump()
        for cat in ["people", "teams", "systems", "documents", "tickets", "decisions", "policies"]
        for node in vaultly_data.get(cat, [])
    ]
    validate_dataset_uniqueness_and_endpoints(
        finpay_data,
        include_external=True,
        extra_nodes=merged_extra_nodes,
        extra_relationships=list(vaultly_data.get("relationships", [])) + bridge_rels,
    )

    # 1. FinPay isolated graph (only FinPay nodes and calls)
    finpay_queries = list(INDEX_QUERIES)
    finpay_queries.extend(_convert_dataset_to_cypher(finpay_data, include_external=True, company_prefix="finpay", preserve_runtime_state=preserve_runtime_state))

    # 2. Vaultly isolated graph (only Vaultly nodes and calls)
    vaultly_queries = list(INDEX_QUERIES)
    vaultly_queries.extend(_convert_dataset_to_cypher(vaultly_data, include_external=True, company_prefix="vaultly", preserve_runtime_state=preserve_runtime_state))

    # 3. Merged brain graph (Both companies + cross-company bridge edges)
    merged_queries = list(INDEX_QUERIES)
    merged_queries.extend(_convert_dataset_to_cypher(finpay_data, include_external=False, preserve_runtime_state=preserve_runtime_state))
    merged_queries.extend(_convert_dataset_to_cypher(vaultly_data, include_external=False, preserve_runtime_state=preserve_runtime_state))

    # Add shared external dependencies
    for ext_node in shared["external_apis"]:
        merged_queries.append(build_node_merge_cypher("ExternalAPI", ext_node.model_dump(), preserve_runtime_state=preserve_runtime_state))
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
    target_path = Path(output_dir)
    out_path = target_path if target_path.is_absolute() else (PROJECT_ROOT / target_path)
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
