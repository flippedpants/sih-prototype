"""Precompute greedy structural-fragmentation sequences with NetworkX."""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from typing import Any

import networkx as nx

from . import schema_config as schema
from .database import distinct_case_ids, managed_driver


@dataclass(frozen=True)
class CriticalityRank:
    rank: int
    node_id: str
    largest_component_before: int
    largest_component_after: int
    num_components_after: int


@dataclass(frozen=True)
class CriticalityResult:
    baseline_largest_component: int
    baseline_component_count: int
    ranks: tuple[CriticalityRank, ...]


def _component_metrics(graph: nx.Graph) -> tuple[int, int]:
    components = list(nx.connected_components(graph))
    return (max((len(component) for component in components), default=0), len(components))


def compute_criticality_from_graph(
    graph: nx.Graph,
    betweenness_scores: dict[Any, float],
    top_k: int = schema.CRITICALITY_DEFAULT_TOP_K,
    candidate_pool_size: int = schema.CRITICALITY_CANDIDATE_POOL_SIZE,
) -> CriticalityResult:
    """Greedily choose sequential removals that minimize the largest component."""
    if top_k < 0 or candidate_pool_size < 0:
        raise ValueError("top_k and candidate_pool_size cannot be negative")
    baseline_largest, baseline_components = _component_metrics(graph)
    working = graph.copy()
    candidates = sorted(
        working.nodes,
        key=lambda node: (-float(betweenness_scores.get(node, 0.0)), str(node)),
    )[:candidate_pool_size]
    ranks: list[CriticalityRank] = []
    # Each trial uses a copy; only the selected removal mutates the working graph.
    for rank in range(1, min(top_k, len(candidates)) + 1):
        before, _ = _component_metrics(working)
        trials: list[tuple[int, int, float, str, Any]] = []
        for candidate in candidates:
            if candidate not in working:
                continue
            trial = working.copy()
            trial.remove_node(candidate)
            largest_after, components_after = _component_metrics(trial)
            trials.append(
                (
                    largest_after,
                    -components_after,
                    -float(betweenness_scores.get(candidate, 0.0)),
                    str(candidate),
                    candidate,
                )
            )
        if not trials:
            break
        largest_after, neg_components, _neg_score, node_id_text, selected = min(trials)
        working.remove_node(selected)
        candidates.remove(selected)
        ranks.append(
            CriticalityRank(
                rank=rank,
                node_id=node_id_text,
                largest_component_before=before,
                largest_component_after=largest_after,
                num_components_after=-neg_components,
            )
        )
    return CriticalityResult(baseline_largest, baseline_components, tuple(ranks))


def load_case_graph(driver: Any, case_id: str) -> tuple[nx.Graph, dict[str, float]]:
    labels_node = schema.entity_label_predicate("node")
    labels_source = schema.entity_label_predicate("source")
    labels_target = schema.entity_label_predicate("target")
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    betweenness = schema.cypher_identifier(schema.PROP_BETWEENNESS)
    structural = schema.relationship_type_union(schema.STRUCTURAL_REL_TYPES)
    node_query = f"""
    MATCH (node) WHERE {labels_node}
    OPTIONAL MATCH (node)-[:{case_link}]->(case:{case_label})
    WITH node, coalesce(node.{case_prop}, case.{node_id}) AS resolved_case_id
    WHERE resolved_case_id = $case_id
    RETURN node.{node_id} AS node_id, coalesce(node.{betweenness}, 0.0) AS betweenness
    """
    edge_query = f"""
    MATCH (source)-[relationship:{structural}]->(target)
    WHERE {labels_source} AND {labels_target}
    OPTIONAL MATCH (source)-[:{case_link}]->(source_case:{case_label})
    OPTIONAL MATCH (target)-[:{case_link}]->(target_case:{case_label})
    WITH source, target, relationship,
         coalesce(source.{case_prop}, source_case.{node_id}) AS source_case_id,
         coalesce(target.{case_prop}, target_case.{node_id}) AS target_case_id
    WHERE source_case_id = $case_id AND target_case_id = $case_id
      AND coalesce(relationship.{case_prop}, source_case_id) = $case_id
    RETURN source.{node_id} AS source_id, target.{node_id} AS target_id
    """
    with driver.session() as session:
        node_rows = list(session.run(node_query, case_id=case_id))
        edge_rows = list(session.run(edge_query, case_id=case_id))
    graph = nx.Graph()
    graph.add_nodes_from(row["node_id"] for row in node_rows)
    graph.add_edges_from((row["source_id"], row["target_id"]) for row in edge_rows)
    scores = {row["node_id"]: float(row["betweenness"]) for row in node_rows}
    return graph, scores


def persist_criticality_results(
    driver: Any, case_id: str, result: CriticalityResult
) -> None:
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    result_label = schema.cypher_identifier(schema.NODE_LABEL_CRITICALITY_RESULT)
    result_link = schema.cypher_identifier(schema.REL_HAS_CRITICALITY_RESULT)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    rank_prop = schema.cypher_identifier(schema.PROP_RESULT_RANK)
    result_node = schema.cypher_identifier(schema.PROP_RESULT_NODE_ID)
    before = schema.cypher_identifier(schema.PROP_LARGEST_COMPONENT_BEFORE)
    after = schema.cypher_identifier(schema.PROP_LARGEST_COMPONENT_AFTER)
    components = schema.cypher_identifier(schema.PROP_NUM_COMPONENTS_AFTER)
    baseline_largest = schema.cypher_identifier(schema.PROP_BASELINE_LARGEST_COMPONENT)
    baseline_count = schema.cypher_identifier(schema.PROP_BASELINE_COMPONENT_COUNT)
    delete_query = f"""
    MATCH (case:{case_label} {{{node_id}: $case_id}})-[:{result_link}]->(old:{result_label})
    DETACH DELETE old
    """
    write_query = f"""
    MERGE (case:{case_label} {{{node_id}: $case_id}})
    SET case.{case_prop} = $case_id
    WITH case
    UNWIND $rows AS row
    CREATE (result:{result_label})
    SET result.{case_prop} = $case_id,
        result.{rank_prop} = row.rank,
        result.{result_node} = row.node_id,
        result.{before} = row.largest_component_before,
        result.{after} = row.largest_component_after,
        result.{components} = row.num_components_after,
        result.{baseline_largest} = $baseline_largest,
        result.{baseline_count} = $baseline_count
    CREATE (case)-[:{result_link}]->(result)
    """
    with driver.session() as session:
        session.run(delete_query, case_id=case_id).consume()
        session.run(
            write_query,
            case_id=case_id,
            rows=[asdict(row) for row in result.ranks],
            baseline_largest=result.baseline_largest_component,
            baseline_count=result.baseline_component_count,
        ).consume()


def compute_criticality(driver: Any, case_id: str, top_k: int) -> CriticalityResult:
    graph, scores = load_case_graph(driver, case_id)
    result = compute_criticality_from_graph(graph, scores, top_k=top_k)
    persist_criticality_results(driver, case_id, result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute structural fragmentation impact")
    parser.add_argument("case_id", nargs="?", help="One case; defaults to every discovered case")
    parser.add_argument("--top-k", type=int, default=schema.CRITICALITY_DEFAULT_TOP_K)
    args = parser.parse_args()
    with managed_driver() as driver:
        case_ids = [args.case_id] if args.case_id else distinct_case_ids(driver)
        for case_id in case_ids:
            result = compute_criticality(driver, case_id, args.top_k)
            print(f"Criticality stored for {case_id}: {[asdict(row) for row in result.ranks]}")


if __name__ == "__main__":
    main()
