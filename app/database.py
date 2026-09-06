"""Neo4j connection and shared command-line helpers."""
from __future__ import annotations

import argparse
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

from neo4j import GraphDatabase


def create_driver() -> Any:
    """Create a driver from environment variables and verify connectivity."""
    driver = GraphDatabase.driver(
        os.getenv("NEO4J_URI", "bolt://localhost:7687"),
        auth=(
            os.getenv("NEO4J_USER", "neo4j"),
            os.getenv("NEO4J_PASSWORD", "change-me-now"),
        ),
    )
    driver.verify_connectivity()
    return driver


@contextmanager
def managed_driver() -> Iterator[Any]:
    driver = create_driver()
    try:
        yield driver
    finally:
        driver.close()


def case_id_parser(description: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("case_id", help="Case identifier to process")
    return parser


def distinct_case_ids(driver: Any) -> list[str]:
    """Return sorted case identifiers found on entity properties or case links."""
    from . import schema_config as schema

    labels = schema.entity_label_predicate("entity")
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    case_id = schema.cypher_identifier(schema.PROP_CASE_ID)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    query = f"""
    MATCH (entity) WHERE {labels}
    OPTIONAL MATCH (entity)-[:{case_link}]->(case:{case_label})
    WITH coalesce(entity.{case_id}, case.{node_id}) AS resolved_case_id
    WHERE resolved_case_id IS NOT NULL
    RETURN DISTINCT resolved_case_id AS case_id ORDER BY case_id
    """
    with driver.session() as session:
        return [row["case_id"] for row in session.run(query)]
