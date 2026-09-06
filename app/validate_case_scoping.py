"""Validate that every entity and structural relationship resolves to one case."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from . import schema_config as schema
from .database import managed_driver


@dataclass(frozen=True)
class CaseCount:
    case_id: str
    scoping_mode: str
    node_count: int


@dataclass(frozen=True)
class CaseScopingReport:
    cases: tuple[CaseCount, ...]
    missing_entity_count: int
    cross_case_relationship_count: int
    unresolved_relationship_count: int

    @property
    def valid(self) -> bool:
        return not (
            self.missing_entity_count
            or self.cross_case_relationship_count
            or self.unresolved_relationship_count
        )


def _identifiers() -> dict[str, str]:
    return {
        "case_label": schema.cypher_identifier(schema.NODE_LABEL_CASE),
        "case_link": schema.cypher_identifier(schema.REL_CASE_LINK),
        "case_id": schema.cypher_identifier(schema.PROP_CASE_ID),
        "node_id": schema.cypher_identifier(schema.PROP_NODE_ID),
        "structural": schema.relationship_type_union(schema.STRUCTURAL_REL_TYPES),
    }


def validate_case_scoping(driver: Any) -> CaseScopingReport:
    """Inspect both supported scoping patterns without mutating graph data."""
    identifiers = _identifiers()
    entity = schema.entity_label_predicate("entity")
    source = schema.entity_label_predicate("source")
    target = schema.entity_label_predicate("target")
    case_label = identifiers["case_label"]
    case_link = identifiers["case_link"]
    case_id = identifiers["case_id"]
    node_id = identifiers["node_id"]
    structural = identifiers["structural"]

    summary_query = f"""
    MATCH (entity) WHERE {entity}
    OPTIONAL MATCH (entity)-[:{case_link}]->(case:{case_label})
    WITH coalesce(entity.{case_id}, case.{node_id}) AS case_id,
         CASE WHEN entity.{case_id} IS NOT NULL THEN 'property' ELSE 'case_link' END AS scoping_mode,
         entity
    WHERE case_id IS NOT NULL
    RETURN case_id, scoping_mode, count(DISTINCT entity) AS node_count
    ORDER BY case_id, scoping_mode
    """
    missing_query = f"""
    MATCH (entity) WHERE {entity}
    OPTIONAL MATCH (entity)-[:{case_link}]->(case:{case_label})
    WITH entity, coalesce(entity.{case_id}, case.{node_id}) AS resolved_case_id
    WHERE resolved_case_id IS NULL
    RETURN count(DISTINCT entity) AS missing_case_count
    """
    relationship_prefix = f"""
    MATCH (source)-[relationship:{structural}]->(target)
    WHERE {source} AND {target}
    OPTIONAL MATCH (source)-[:{case_link}]->(source_case:{case_label})
    OPTIONAL MATCH (target)-[:{case_link}]->(target_case:{case_label})
    WITH relationship,
         coalesce(source.{case_id}, source_case.{node_id}) AS source_case_id,
         coalesce(target.{case_id}, target_case.{node_id}) AS target_case_id
    """
    cross_case_query = relationship_prefix + """
    WHERE source_case_id IS NOT NULL AND target_case_id IS NOT NULL
      AND source_case_id <> target_case_id
    RETURN count(DISTINCT relationship) AS cross_case_count
    """
    unresolved_query = relationship_prefix + f"""
    WHERE (relationship.{case_id} IS NULL AND (
             source_case_id IS NULL OR target_case_id IS NULL OR source_case_id <> target_case_id
          ))
       OR (relationship.{case_id} IS NOT NULL AND (
             (source_case_id IS NOT NULL AND relationship.{case_id} <> source_case_id)
             OR (target_case_id IS NOT NULL AND relationship.{case_id} <> target_case_id)
          ))
    RETURN count(DISTINCT relationship) AS unresolved_relationship_count
    """

    with driver.session() as session:
        case_rows = list(session.run(summary_query))
        missing = session.run(missing_query).single() or {"missing_case_count": 0}
        cross_case = session.run(cross_case_query).single() or {"cross_case_count": 0}
        unresolved = session.run(unresolved_query).single() or {
            "unresolved_relationship_count": 0
        }
    return CaseScopingReport(
        cases=tuple(
            CaseCount(
                case_id=row["case_id"],
                scoping_mode=row["scoping_mode"],
                node_count=row["node_count"],
            )
            for row in case_rows
        ),
        missing_entity_count=missing["missing_case_count"],
        cross_case_relationship_count=cross_case["cross_case_count"],
        unresolved_relationship_count=unresolved["unresolved_relationship_count"],
    )


def _print_report(report: CaseScopingReport) -> None:
    print("CASE ID | SCOPING MODE | ENTITY COUNT")
    print("-" * 45)
    for row in report.cases:
        print(f"{row.case_id} | {row.scoping_mode} | {row.node_count}")
    print(f"Missing entity case identifiers: {report.missing_entity_count}")
    print(f"Cross-case structural relationships: {report.cross_case_relationship_count}")
    print(f"Unresolved structural relationships: {report.unresolved_relationship_count}")
    if not report.valid:
        print("BLOCKING WARNING: case scoping is invalid; algorithms must not run.")


def main() -> None:
    with managed_driver() as driver:
        report = validate_case_scoping(driver)
    _print_report(report)
    if not report.valid:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
