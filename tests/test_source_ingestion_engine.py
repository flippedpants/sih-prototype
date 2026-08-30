import pytest

from app.source_ingestion.engine import SourceIngestionEngine
from app.source_ingestion.validation import StructuralValidationError


CDR_MAPPING = {
    "source_type": "cdr",
    "row_maps_to": "edge",
    "entities": [
        {"column_aliases": ["caller", "calling_number"], "entity_type": "PHONE", "role": "source"},
        {"column_aliases": ["callee", "called_number"], "entity_type": "PHONE", "role": "target"},
    ],
    "relationship": {
        "type": "CALLED",
        "source_column_aliases": ["caller", "calling_number"],
        "target_column_aliases": ["callee", "called_number"],
        "weight_columns": {"duration": {"aliases": ["duration_seconds"], "required": False}},
        "timestamp_column": {"aliases": ["call_time"], "required": False},
    },
}


def test_clean_cdr_file_creates_typed_entities_relationship_and_provenance():
    result = SourceIngestionEngine().ingest_bytes(
        "calls.csv",
        b"caller,callee,duration_seconds,call_time\n+911111,+922222,42,2026-08-01T12:30:00Z\n",
        CDR_MAPPING,
    )

    assert result.validation_errors == []
    assert [entity.id for entity in result.entities] == ["PHONE:+911111", "PHONE:+922222"]
    assert result.relationships[0].type == "CALLED"
    assert result.relationships[0].weight == 42.0
    assert result.relationships[0].timestamp.isoformat() == "2026-08-01T12:30:00+00:00"
    assert result.relationships[0].source_doc == "cdr:calls.csv:2"


def test_missing_required_columns_fails_before_row_processing():
    with pytest.raises(StructuralValidationError, match="callee"):
        SourceIngestionEngine().ingest_bytes(
            "calls.csv", b"caller,duration_seconds,call_time\n+911111,42,2026-08-01T12:30:00Z\n", CDR_MAPPING
        )


def test_unparseable_dates_are_collected_as_row_validation_errors():
    result = SourceIngestionEngine().ingest_bytes(
        "calls.csv",
        b"caller,callee,duration_seconds,call_time\n+911111,+922222,42,not-a-date\n",
        CDR_MAPPING,
    )

    assert result.entities == []
    assert result.relationships == []
    assert result.validation_errors[0].row_number == 2
    assert "call_time" in result.validation_errors[0].reason


def test_mixed_fir_shape_supports_multiple_entity_and_relationship_blocks():
    mapping = {
        "source_type": "fir_intake",
        "row_maps_to": "mixed",
        "entities": [
            {"entity_type": "PERSON", "id_column": "person_id", "canonical_name_column": "person_name", "aliases_column": "aliases"},
            {"entity_type": "LOCATION", "id_column": "location_id", "attribute_columns": ["district"]},
        ],
        "relationships": [
            {"type": "NAMED_IN_FIR", "source_column": "person_id", "target_column": "location_id", "weight_columns": [], "timestamp_column": "fir_date"}
        ],
    }
    result = SourceIngestionEngine().ingest_bytes(
        "fir.csv",
        b"person_id,person_name,aliases,location_id,district,fir_date\np-1,Arun Kumar,Arun|A. Kumar,loc-7,Delhi,2026-07-01\n",
        mapping,
    )

    assert {(entity.type, entity.id) for entity in result.entities} == {("PERSON", "PERSON:p-1"), ("LOCATION", "LOCATION:loc-7")}
    assert result.entities[0].aliases == ["Arun", "A. Kumar"]
    assert result.relationships[0].source_id == "PERSON:p-1"
    assert result.relationships[0].target_id == "LOCATION:loc-7"


def test_resolves_explicit_alternate_column_aliases():
    result = SourceIngestionEngine().ingest_bytes("calls.csv", b"calling_number,called_number\n1,2\n", CDR_MAPPING)
    assert [entity.id for entity in result.entities] == ["PHONE:1", "PHONE:2"]


def test_missing_required_alias_reports_the_logical_field():
    with pytest.raises(StructuralValidationError, match=r"relationship\[0\]\.target"):
        SourceIngestionEngine().ingest_bytes("calls.csv", b"caller\n1\n", CDR_MAPPING)


def test_reports_all_missing_required_aliases_together():
    with pytest.raises(StructuralValidationError) as error:
        SourceIngestionEngine().ingest_bytes("calls.csv", b"other\nx\n", CDR_MAPPING)
    assert "relationship[0].source" in str(error.value)
    assert "relationship[0].target" in str(error.value)


def test_ignores_extra_columns_and_normalizes_header_case_and_whitespace():
    result = SourceIngestionEngine().ingest_bytes("calls.csv", b" Caller , CALLEE ,unexpected\n1,2,x\n", CDR_MAPPING)
    assert result.relationships[0].source_id == "PHONE:1"
