"""Run and persist the core GDS algorithms for one or every case."""
from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from typing import Any

from . import schema_config as schema
from .database import distinct_case_ids, managed_driver
from .project_graphs import project_case_graph


@dataclass(frozen=True)
class CoreAlgorithmSummary:
    case_id: str
    projection_name: str
    metrics: dict[str, int] = field(default_factory=dict)


def _metric(row: dict[str, Any] | None, key: str) -> int:
    return int((row or {}).get(key, 0))


def _write_community_sizes(driver: Any, case_id: str) -> int:
    labels = schema.entity_label_predicate("node")
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    community = schema.cypher_identifier(schema.PROP_COMMUNITY_ID)
    community_size = schema.cypher_identifier(schema.PROP_COMMUNITY_SIZE)
    query = f"""
    MATCH (node) WHERE {labels}
    OPTIONAL MATCH (node)-[:{case_link}]->(case:{case_label})
    WITH node, coalesce(node.{case_prop}, case.{node_id}) AS resolved_case_id
    WHERE resolved_case_id = $case_id AND node.{community} IS NOT NULL
    WITH node.{community} AS community_id, collect(DISTINCT node) AS members
    WITH members, size(members) AS member_count
    FOREACH (member IN members | SET member.{community_size} = member_count)
    RETURN sum(member_count) AS nodes_updated
    """
    with driver.session() as session:
        row = session.run(query, case_id=case_id).single()
    return _metric(row, "nodes_updated")


def _delete_case_similarities(driver: Any, case_id: str) -> None:
    similar_type = schema.cypher_identifier(schema.REL_SIMILAR_TO)
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    query = f"""
    MATCH (source)-[similar:{similar_type}]->(target)
    WHERE source.{case_prop} = $case_id AND target.{case_prop} = $case_id
    DELETE similar
    """
    with driver.session() as session:
        session.run(query, case_id=case_id).consume()


def run_core_algorithms(driver: Any, case_id: str) -> CoreAlgorithmSummary:
    """Reproject a case and persist centrality, community, and similarity data."""
    projection = project_case_graph(driver, case_id, directed=False)
    graph_name = schema.projection_name(case_id)
    metrics: dict[str, int] = {}
    with driver.session() as session:
        row = session.run(
            """
            CALL gds.betweenness.write($graph_name, {writeProperty: $write_property})
            YIELD nodePropertiesWritten
            RETURN nodePropertiesWritten
            """,
            graph_name=graph_name,
            write_property=schema.PROP_BETWEENNESS,
        ).single()
        metrics["betweenness_nodes"] = _metric(row, "nodePropertiesWritten")

        degree_config: dict[str, Any] = {"writeProperty": schema.PROP_DEGREE}
        if schema.REL_WEIGHT_PROPERTY:
            degree_config["relationshipWeightProperty"] = "weight"
        row = session.run(
            """
            CALL gds.degree.write($graph_name, $config)
            YIELD nodePropertiesWritten
            RETURN nodePropertiesWritten
            """,
            graph_name=graph_name,
            config=degree_config,
            write_property=schema.PROP_DEGREE,
        ).single()
        metrics["degree_nodes"] = _metric(row, "nodePropertiesWritten")

        louvain_config: dict[str, Any] = {"writeProperty": schema.PROP_COMMUNITY_ID}
        if schema.REL_WEIGHT_PROPERTY:
            louvain_config["relationshipWeightProperty"] = "weight"
        row = session.run(
            """
            CALL gds.louvain.write($graph_name, $config)
            YIELD nodePropertiesWritten
            RETURN nodePropertiesWritten
            """,
            graph_name=graph_name,
            config=louvain_config,
            write_property=schema.PROP_COMMUNITY_ID,
        ).single()
        metrics["community_nodes"] = _metric(row, "nodePropertiesWritten")

    metrics["community_sizes"] = _write_community_sizes(driver, case_id)
    # Similarity is a suggestion layer and never participates in structural projections.
    _delete_case_similarities(driver, case_id)
    similarity_config: dict[str, Any] = {
        "writeRelationshipType": schema.REL_SIMILAR_TO,
        "writeProperty": schema.REL_SIMILAR_TO_SCORE_PROP,
    }
    if schema.REL_WEIGHT_PROPERTY:
        similarity_config["relationshipWeightProperty"] = "weight"
    with driver.session() as session:
        row = session.run(
            """
            CALL gds.nodeSimilarity.write($graph_name, $config)
            YIELD relationshipsWritten
            RETURN relationshipsWritten
            """,
            graph_name=graph_name,
            config=similarity_config,
            relationship_type=schema.REL_SIMILAR_TO,
            write_property=schema.REL_SIMILAR_TO_SCORE_PROP,
        ).single()
    metrics["similarity_relationships"] = _metric(row, "relationshipsWritten")
    return CoreAlgorithmSummary(
        case_id=case_id,
        projection_name=getattr(projection, "name", graph_name),
        metrics=metrics,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run persistent Zone 1 GDS algorithms")
    parser.add_argument("case_id", nargs="?", help="One case; defaults to every discovered case")
    args = parser.parse_args()
    with managed_driver() as driver:
        case_ids = [args.case_id] if args.case_id else distinct_case_ids(driver)
        for case_id in case_ids:
            summary = run_core_algorithms(driver, case_id)
            print(f"Core algorithms complete for {case_id}: {summary.metrics}")


if __name__ == "__main__":
    main()
