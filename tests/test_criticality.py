import networkx as nx

from app.compute_criticality import (
    compute_criticality_from_graph,
    persist_criticality_results,
)


def test_greedy_criticality_uses_sequential_graph_mutation():
    graph = nx.path_graph(["a", "b", "c", "d", "e"])
    scores = {"a": 0, "b": 3, "c": 10, "d": 3, "e": 0}

    result = compute_criticality_from_graph(
        graph, scores, top_k=2, candidate_pool_size=5
    )

    assert result.baseline_largest_component == 5
    assert result.ranks[0].node_id == "c"
    assert result.ranks[0].largest_component_after == 2
    assert result.ranks[1].largest_component_before == 2


def test_criticality_persistence_replaces_only_the_case_results(fake_driver):
    graph = nx.star_graph(["leaf-a", "leaf-b", "leaf-c"])
    result = compute_criticality_from_graph(
        graph, {"0": 10, "leaf-a": 1, "leaf-b": 1, "leaf-c": 1}, top_k=1
    )
    persist_criticality_results(fake_driver, "CASE-A", result)
    query_text = "\n".join(query for query, _ in fake_driver.calls)
    assert "HAS_CRITICALITY_RESULT" in query_text
    assert "DETACH DELETE" in query_text
    assert any(parameters.get("case_id") == "CASE-A" for _, parameters in fake_driver.calls)
