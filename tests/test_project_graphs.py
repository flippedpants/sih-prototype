from app import schema_config as schema
from app.project_graphs import project_case_graph

from .conftest import FakeDriver


def test_undirected_projection_is_recreated_and_scoped_to_one_case():
    driver = FakeDriver(
        lambda query, _params: [{"exists": True}] if "gds.graph.exists" in query else []
    )
    result = project_case_graph(driver, "CASE-A")

    assert result.name == schema.projection_name("CASE-A")
    assert any("gds.graph.drop" in query for query, _ in driver.calls)
    projection = next(
        parameters
        for query, parameters in driver.calls
        if "gds.graph.project.cypher" in query
    )
    assert projection["case_id"] == "CASE-A"
    assert "UNION ALL" in projection["relationship_query"]
    assert all(rel_type in projection["relationship_query"] for rel_type in schema.STRUCTURAL_REL_TYPES)


def test_directed_projection_contains_transactions_only(fake_driver):
    project_case_graph(fake_driver, "CASE-A", directed=True)
    projection = next(
        parameters for query, parameters in fake_driver.calls if "gds.graph.project.cypher" in query
    )
