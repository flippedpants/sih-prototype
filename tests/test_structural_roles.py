from app.classify_structural_roles import classify_structural_roles

from .conftest import FakeDriver


def test_roles_use_per_case_percentiles_and_are_written_in_one_batch():
    scores = [
        {"node_id": "hub", "betweenness": 100.0, "degree": 100.0},
        {"node_id": "broker", "betweenness": 90.0, "degree": 1.0},
        {"node_id": "peripheral", "betweenness": 0.0, "degree": 0.0},
        {"node_id": "member", "betweenness": 10.0, "degree": 20.0},
        {"node_id": "member-2", "betweenness": 20.0, "degree": 30.0},
        {"node_id": "member-3", "betweenness": 30.0, "degree": 40.0},
        {"node_id": "member-4", "betweenness": 40.0, "degree": 50.0},
    ]
    driver = FakeDriver(
        lambda query, _params: scores if "betweenness" in query and "RETURN" in query else []
    )

    counts = classify_structural_roles(driver, "CASE-A")

    written = next(
        parameters["rows"]
        for query, parameters in driver.calls
        if "UNWIND $rows" in query
    )
    roles = {row["node_id"]: row["role"] for row in written}
    assert roles["hub"] == "HUB"
    assert roles["broker"] == "BROKER"
    assert roles["peripheral"] == "PERIPHERAL"
