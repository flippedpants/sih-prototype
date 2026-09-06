from app import schema_config as schema
from app.run_core_algorithms import run_core_algorithms


def test_core_algorithms_write_contract_properties(fake_driver, monkeypatch):
    monkeypatch.setattr(
        "app.run_core_algorithms.project_case_graph", lambda *_args, **_kwargs: None
    )
    summary = run_core_algorithms(fake_driver, "CASE-A")

    query_text = "\n".join(query for query, _ in fake_driver.calls)
    assert "gds.betweenness.write" in query_text
    assert "gds.degree.write" in query_text
    assert "gds.louvain.write" in query_text
    assert "gds.nodeSimilarity.write" in query_text
    all_parameters = [parameters for _, parameters in fake_driver.calls]
    assert any(
        parameters.get("write_property") == schema.PROP_BETWEENNESS
        for parameters in all_parameters
    )
    assert any(
        parameters.get("write_property") == schema.PROP_COMMUNITY_ID
        for parameters in all_parameters
    )
    assert any(
        parameters.get("relationship_type") == schema.REL_SIMILAR_TO
        for parameters in all_parameters
    )
    assert summary.case_id == "CASE-A"

def test_similarity_relationships_are_removed_before_recomputation(fake_driver, monkeypatch):
    monkeypatch.setattr("app.run_core_algorithms.project_case_graph", lambda *_a, **_k: None)
    run_core_algorithms(fake_driver, "CASE-A")
    assert any("DELETE similar" in query for query, _ in fake_driver.calls)

