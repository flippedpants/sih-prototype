"""Classify case-scoped structural roles from precomputed centrality scores."""
from __future__ import annotations

import argparse
from collections import Counter
from typing import Any

import numpy as np

from . import schema_config as schema
from .database import distinct_case_ids, managed_driver

ROLE_HUB = "HUB"
ROLE_BROKER = "BROKER"
ROLE_PERIPHERAL = "PERIPHERAL"
ROLE_MEMBER = "MEMBER"


def _threshold(values: list[float], percentile: float) -> float:
    return float(np.percentile(np.asarray(values, dtype=float), percentile))


def classify_structural_roles(driver: Any, case_id: str) -> dict[str, int]:
    """Compute percentile thresholds within one case and persist classifications."""
    labels = schema.entity_label_predicate("node")
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    betweenness = schema.cypher_identifier(schema.PROP_BETWEENNESS)
    degree = schema.cypher_identifier(schema.PROP_DEGREE)
    role_prop = schema.cypher_identifier(schema.PROP_STRUCTURAL_ROLE)
    read_query = f"""
    MATCH (node) WHERE {labels}
    OPTIONAL MATCH (node)-[:{case_link}]->(case:{case_label})
    WITH node, coalesce(node.{case_prop}, case.{node_id}) AS resolved_case_id
    WHERE resolved_case_id = $case_id
    RETURN node.{node_id} AS node_id,
           coalesce(node.{betweenness}, 0.0) AS betweenness,
           coalesce(node.{degree}, 0.0) AS degree
    ORDER BY node_id
    """
    with driver.session() as session:
        rows = [dict(row) for row in session.run(read_query, case_id=case_id)]
    if not rows:
        return {}

    betweenness_values = [float(row["betweenness"]) for row in rows]
    degree_values = [float(row["degree"]) for row in rows]
    hub_betweenness = _threshold(
        betweenness_values, schema.HUB_BETWEENNESS_PERCENTILE
    )
    hub_degree = _threshold(degree_values, schema.HUB_DEGREE_PERCENTILE)
    broker_betweenness = _threshold(
        betweenness_values, schema.BROKER_BETWEENNESS_PERCENTILE
    )
    broker_degree_max = _threshold(
        degree_values, schema.BROKER_DEGREE_PERCENTILE_MAX
    )
    median_betweenness = _threshold(betweenness_values, 50)
    median_degree = _threshold(degree_values, 50)

    updates: list[dict[str, str]] = []
    for row in rows:
        node_betweenness = float(row["betweenness"])
        node_degree = float(row["degree"])
        if node_betweenness >= hub_betweenness and node_degree >= hub_degree:
            role = ROLE_HUB
        elif (
            node_betweenness >= broker_betweenness
            and node_degree <= broker_degree_max
        ):
            role = ROLE_BROKER
        elif node_betweenness < median_betweenness and node_degree < median_degree:
            role = ROLE_PERIPHERAL
        else:
            role = ROLE_MEMBER
        updates.append({"node_id": row["node_id"], "role": role})

    write_query = f"""
    UNWIND $rows AS row
    MATCH (node) WHERE {labels} AND node.{node_id} = row.node_id
    OPTIONAL MATCH (node)-[:{case_link}]->(case:{case_label})
    WITH node, row, coalesce(node.{case_prop}, case.{node_id}) AS resolved_case_id
    WHERE resolved_case_id = $case_id
    SET node.{role_prop} = row.role
    """
    with driver.session() as session:
        session.run(write_query, case_id=case_id, rows=updates).consume()
    return dict(Counter(row["role"] for row in updates))


def main() -> None:
    parser = argparse.ArgumentParser(description="Classify precomputed structural roles")
    parser.add_argument("case_id", nargs="?", help="One case; defaults to every discovered case")
    args = parser.parse_args()
    with managed_driver() as driver:
        case_ids = [args.case_id] if args.case_id else distinct_case_ids(driver)
        for case_id in case_ids:
            counts = classify_structural_roles(driver, case_id)
            print(f"Structural roles written for {case_id}: {counts}")


if __name__ == "__main__":
    main()
