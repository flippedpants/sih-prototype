"""Create idempotent, case-scoped Neo4j GDS Cypher projections."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from typing import Any

from . import schema_config as schema
from .database import distinct_case_ids, managed_driver
from .validate_case_scoping import validate_case_scoping


@dataclass(frozen=True)
class ProjectionResult:
    name: str
    case_id: str
    directed: bool
    node_count: int
    relationship_count: int


def _node_query() -> str:
    labels = schema.entity_label_predicate("node")
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    case_id = schema.cypher_identifier(schema.PROP_CASE_ID)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    return f"""
    MATCH (node) WHERE {labels}
    OPTIONAL MATCH (node)-[:{case_link}]->(case:{case_label})
    WITH node, coalesce(node.{case_id}, case.{node_id}) AS resolved_case_id
    WHERE resolved_case_id = $case_id
    RETURN id(node) AS id
    """


def _relationship_query(directed: bool) -> str:
    labels_source = schema.entity_label_predicate("source")
    labels_target = schema.entity_label_predicate("target")
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    case_id = schema.cypher_identifier(schema.PROP_CASE_ID)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    selected_types = (schema.REL_TRANSACTION,) if directed else schema.STRUCTURAL_REL_TYPES
    relationship_types = schema.relationship_type_union(selected_types)
    weight_expression = (
        f"coalesce(relationship.{schema.cypher_identifier(schema.REL_WEIGHT_PROPERTY)}, 1.0)"
        if schema.REL_WEIGHT_PROPERTY
        else "1.0"
    )
    # Cypher projection is intentional while labels remain provisional. If the
    # real schema splits entities, entity_label_predicate supplies the union.
    base = f"""
    MATCH (source)-[relationship:{relationship_types}]->(target)
    WHERE {labels_source} AND {labels_target}
    OPTIONAL MATCH (source)-[:{case_link}]->(source_case:{case_label})
    OPTIONAL MATCH (target)-[:{case_link}]->(target_case:{case_label})
    WITH source, target, relationship,
         coalesce(source.{case_id}, source_case.{node_id}) AS source_case_id,
         coalesce(target.{case_id}, target_case.{node_id}) AS target_case_id
    WHERE source_case_id = $case_id AND target_case_id = $case_id
      AND coalesce(relationship.{case_id}, source_case_id) = $case_id
    RETURN id(source) AS source, id(target) AS target,
           {weight_expression} AS weight
    """
    if directed:
        return base
    reverse = base.replace(
        "RETURN id(source) AS source, id(target) AS target,",
        "RETURN id(target) AS source, id(source) AS target,",
    )
    return base + "\nUNION ALL\n" + reverse


def project_case_graph(
    driver: Any,
    case_id: str,
    directed: bool = False,
    *,
    validate: bool = True,
) -> ProjectionResult:
    """Drop and recreate one named projection after validating global scoping."""
    if validate:
        report = validate_case_scoping(driver)
        if not report.valid:
            raise ValueError("case scoping validation failed; projection was not created")
    name = schema.projection_name(case_id, directed)
    with driver.session() as session:
        existence = session.run(
            "CALL gds.graph.exists($name) YIELD exists RETURN exists", name=name
        ).single()
        if existence and existence["exists"]:
            session.run("CALL gds.graph.drop($name, false)", name=name).consume()
        row = session.run(
            """
            CALL gds.graph.project.cypher(
                $name,
                $node_query,
                $relationship_query,
                {parameters: {case_id: $case_id}}
            )
            YIELD graphName, nodeCount, relationshipCount
            RETURN graphName, nodeCount, relationshipCount
            """,
            name=name,
            node_query=_node_query(),
            relationship_query=_relationship_query(directed),
            case_id=case_id,
        ).single() or {}
    return ProjectionResult(
        name=name,
        case_id=case_id,
        directed=directed,
        node_count=int(row.get("nodeCount", 0)),
        relationship_count=int(row.get("relationshipCount", 0)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Recreate case-scoped GDS projections")
    parser.add_argument("case_id", nargs="?", help="One case; defaults to every discovered case")
    parser.add_argument("--directed", action="store_true", help="Project transaction direction")
    args = parser.parse_args()
    with managed_driver() as driver:
        case_ids = [args.case_id] if args.case_id else distinct_case_ids(driver)
        for case_id in case_ids:
            result = project_case_graph(driver, case_id, args.directed)
            print(
                f"Projected {result.name}: {result.node_count} nodes, "
                f"{result.relationship_count} relationships"
            )


if __name__ == "__main__":
    main()
