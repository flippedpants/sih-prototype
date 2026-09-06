"""DISPOSABLE placeholder graph generator; remove when real data is loaded.

It creates two small case-scoped preferential-attachment graphs solely so the
Zone 1 computations can be developed before the real synthetic dataset arrives.
It is deliberately separate from any future production ingestion path.
"""
from __future__ import annotations

import argparse
import random
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any

from . import schema_config as schema
from .database import managed_driver

DEFAULT_CASE_SIZES = {"TOY-CASE-01": 20, "TOY-CASE-02": 20}


def _preferential_edges(case_id: str, size: int, rng: random.Random) -> list[dict[str, Any]]:
    node_ids = [f"{case_id}:P{index:03d}" for index in range(size)]
    degree: Counter[str] = Counter()
    pairs: list[tuple[str, str]] = []
    for index in range(1, size):
        source = node_ids[index]
        population = node_ids[:index]
        target_count = min(2, index)
        selected: set[str] = set()
        while len(selected) < target_count:
            weights = [degree[node_id] + 1 for node_id in population]
            selected.add(rng.choices(population, weights=weights, k=1)[0])
        for target in selected:
            pairs.append((source, target))
            degree[source] += 1
            degree[target] += 1

    relationship_types = schema.STRUCTURAL_REL_TYPES
    started = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows: list[dict[str, Any]] = []
    for index, (source, target) in enumerate(pairs):
        relationship_type = relationship_types[index % len(relationship_types)]
        amount = float(rng.randint(1_000, 150_000))
        rows.append({
            "id": f"{case_id}:R{index:04d}",
            "case_id": case_id,
            "source": source,
            "target": target,
            "relationship_type": relationship_type,
            "weight": round(rng.uniform(1, 20), 3),
            "amount": amount if relationship_type == schema.REL_TRANSACTION else None,
            "timestamp": (started + timedelta(hours=index)).isoformat(),
        })

    # Seed one ordered 3-cycle and one structuring pattern per toy case so the
    # deterministic financial detectors always have known positive examples.
    cycle = node_ids[:3]
    for offset, (source, target) in enumerate(zip(cycle, cycle[1:] + cycle[:1])):
        rows.append({
            "id": f"{case_id}:CYCLE:{offset}",
            "case_id": case_id,
            "source": source,
            "target": target,
            "relationship_type": schema.REL_TRANSACTION,
            "weight": 1.0,
            "amount": float(20_000 + offset * 1_000),
            "timestamp": (started + timedelta(days=1, hours=offset)).isoformat(),
        })
    for offset in range(schema.STRUCTURING_MIN_TRANSACTION_COUNT):
        rows.append({
            "id": f"{case_id}:STRUCTURE:{offset}",
            "case_id": case_id,
            "source": node_ids[3],
            "target": node_ids[4],
            "relationship_type": schema.REL_TRANSACTION,
            "weight": 1.0,
            "amount": 50_000.0,
            "timestamp": (started + timedelta(days=offset * 5)).isoformat(),
        })
    return rows


def generate_placeholder_data(
    driver: Any,
    case_sizes: dict[str, int] | None = None,
    seed: int = 2025,
) -> dict[str, int]:
    """Replace only the named toy cases and return generated row counts."""
    case_sizes = case_sizes or DEFAULT_CASE_SIZES
    if any(size < 5 for size in case_sizes.values()):
        raise ValueError("placeholder cases require at least five entities")
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    entity_label = schema.cypher_identifier(schema.NODE_LABEL_ENTITY)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    node_name = schema.cypher_identifier(schema.PROP_NODE_NAME)
    case_id_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    rel_id = schema.cypher_identifier(schema.PROP_RELATIONSHIP_ID)
    weight = schema.cypher_identifier(schema.REL_WEIGHT_PROPERTY or "weight")
    amount = schema.cypher_identifier(schema.TXN_PROP_AMOUNT)
    timestamp = schema.cypher_identifier(schema.TXN_PROP_TIMESTAMP)
    nodes = [
        {"id": f"{case_id}:P{index:03d}", "name": f"Placeholder Person {index + 1}", "case_id": case_id}
        for case_id, size in case_sizes.items() for index in range(size)
    ]
    rng = random.Random(seed)
    relationships = [
        row for case_id, size in case_sizes.items()
        for row in _preferential_edges(case_id, size, rng)
    ]
    with driver.session() as session:
        for case_id in case_sizes:
            session.run(
                f"MATCH (entity) WHERE {schema.entity_label_predicate('entity')} AND entity.{case_id_prop} = $case_id DETACH DELETE entity",
                case_id=case_id,
            ).consume()
            session.run(
                f"MATCH (case:{case_label} {{{node_id}: $case_id}}) DETACH DELETE case",
                case_id=case_id,
            ).consume()
        session.run(
            f"""
            UNWIND $rows AS row
            MERGE (case:{case_label} {{{node_id}: row.case_id}})
            SET case.{case_id_prop} = row.case_id
            MERGE (entity:{entity_label} {{{node_id}: row.id}})
            SET entity.{node_name} = row.name, entity.{case_id_prop} = row.case_id
            MERGE (entity)-[:{case_link}]->(case)
            """,
            rows=nodes,
        ).consume()
        for relationship_type in schema.STRUCTURAL_REL_TYPES:
            rows = [row for row in relationships if row["relationship_type"] == relationship_type]
            rel_type = schema.cypher_identifier(relationship_type)
            session.run(
                f"""
                // relationship_type is selected from schema_config, never user input
                UNWIND $rows AS row
                MATCH (source:{entity_label} {{{node_id}: row.source}})
                MATCH (target:{entity_label} {{{node_id}: row.target}})
                MERGE (source)-[relationship:{rel_type} {{{rel_id}: row.id}}]->(target)
                SET relationship.{case_id_prop} = row.case_id,
                    relationship.{weight} = row.weight,
                    relationship.{amount} = row.amount,
                    relationship.{timestamp} = row.timestamp
                """,
                rows=rows,
            ).consume()
    return {"cases": len(case_sizes), "entities": len(nodes), "relationships": len(relationships)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate disposable Zone 1 placeholder data")
    parser.add_argument("--seed", type=int, default=2025)
    args = parser.parse_args()
    with managed_driver() as driver:
        summary = generate_placeholder_data(driver, seed=args.seed)
    print("Placeholder data generated:", summary)

