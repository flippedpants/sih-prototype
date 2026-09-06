from app.generate_placeholder_data import generate_placeholder_data
from app.validate_case_scoping import validate_case_scoping

from .conftest import FakeDriver


def test_placeholder_generation_is_seeded_case_scoped_and_idempotent(fake_driver):
    summary = generate_placeholder_data(
        fake_driver, case_sizes={"CASE-A": 15, "CASE-B": 16}, seed=7
    )

    assert summary["cases"] == 2
    assert summary["entities"] == 31
    assert summary["relationships"] > 0
    query_text = "\n".join(query for query, _ in fake_driver.calls)
    assert "DETACH DELETE" in query_text
    assert "BELONGS_TO" in query_text
    relationship_rows = next(
        parameters["rows"]
        for query, parameters in fake_driver.calls
        if "UNWIND $rows AS row" in query and "relationship_type" in query
    )
    assert all(row["case_id"] in {"CASE-A", "CASE-B"} for row in relationship_rows)


def test_validation_reports_property_and_case_link_scoping():
    def handler(query, _parameters):
        if "scoping_mode" in query:
            return [
                {"case_id": "CASE-A", "scoping_mode": "property", "node_count": 4},
                {"case_id": "CASE-B", "scoping_mode": "case_link", "node_count": 3},
            ]
        if "missing_case_count" in query:
            return [{"missing_case_count": 0}]
        if "cross_case_count" in query:
            return [{"cross_case_count": 0}]
        if "unresolved_relationship_count" in query:
            return [{"unresolved_relationship_count": 0}]
        return []

    report = validate_case_scoping(FakeDriver(handler))

    assert report.valid is True
    assert {row.scoping_mode for row in report.cases} == {"property", "case_link"}


def test_validation_blocks_missing_and_cross_case_data():
    def handler(query, _parameters):
        if "missing_case_count" in query:
            return [{"missing_case_count": 2}]
        if "cross_case_count" in query:
            return [{"cross_case_count": 1}]
        if "unresolved_relationship_count" in query:
            return [{"unresolved_relationship_count": 3}]
        return []
