"""Convert flexible, user-supplied CSV mappings into normalized graph records."""
from __future__ import annotations

import csv
import io
from typing import Any

from .models import CsvFileMapping, CsvIngestionMapping, EntityInput, SourceRecordInput, SourceRelationInput


def parse_csv_uploads(uploaded_files: list[tuple[str, bytes]], mapping_data: dict[str, Any]) -> list[SourceRecordInput]:
    """Parse all files using declared column mappings, without fixed dataset fields."""
    mapping = CsvIngestionMapping.model_validate(mapping_data)
    configurations = {item.file_name: item for item in mapping.files}
    names = [name for name, _ in uploaded_files]
    if len(names) != len(set(names)):
        raise ValueError("uploaded CSV file names must be unique")

    records: list[SourceRecordInput] = []
    for file_name, content in uploaded_files:
        config = configurations.get(file_name)
        if config is None:
            raise ValueError(f"no mapping was supplied for uploaded file '{file_name}'")
        try:
            reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
        except UnicodeDecodeError as error:
            raise ValueError(f"CSV file '{file_name}' must be UTF-8 encoded") from error
        _validate_headers(file_name, reader.fieldnames, config)
        for row_number, row in enumerate(reader, start=2):
            records.append(_record_from_row(file_name, row_number, row, config))
    if not records:
        raise ValueError("uploaded CSV files contain no data rows")
    return records


def _validate_headers(file_name: str, headers: list[str] | None, config: CsvFileMapping) -> None:
    present = set(headers or [])
    required = {config.record_id_column}
    for entity in config.entities:
        required.add(entity.id_column)
        if entity.display_name_column:
            required.add(entity.display_name_column)
        required.update(entity.identifiers.values())
        required.update(entity.attributes.values())
    for relation in config.relations:
        required.update({relation.source_id_column, relation.target_id_column})
        if relation.weight_column:
            required.add(relation.weight_column)
        required.update(relation.attributes.values())
    if config.evidence.confidence_column:
        required.add(config.evidence.confidence_column)
    if config.evidence.occurred_at_column:
        required.add(config.evidence.occurred_at_column)
    required.update(config.evidence.attributes.values())
    missing = sorted(required - present)
    if missing:
        raise ValueError(f"CSV file '{file_name}' is missing mapped columns: {', '.join(missing)}")


def _record_from_row(file_name: str, row_number: int, row: dict[str, str | None], config: CsvFileMapping) -> SourceRecordInput:
    raw_record_id = _required(row, config.record_id_column, file_name, row_number)
    entities = [
        EntityInput(
            id=_required(row, item.id_column, file_name, row_number),
            entity_type=item.entity_type,
            display_name=_optional(row, item.display_name_column),
            identifiers=_mapped_values(row, item.identifiers),
            attributes=_mapped_values(row, item.attributes),
        )
        for item in config.entities
    ]
    relations = [
        SourceRelationInput(
            relation_type=item.relation_type,
            source_ref=_required(row, item.source_id_column, file_name, row_number),
            target_ref=_required(row, item.target_id_column, file_name, row_number),
            weight=_number(row, item.weight_column, 1.0, file_name, row_number),
            attributes=_mapped_values(row, item.attributes),
        )
        for item in config.relations
    ]
    evidence: dict[str, Any] = {
        "source_kind": config.evidence.source_kind,
        "confidence": _number(row, config.evidence.confidence_column, 1.0, file_name, row_number),
        "attributes": _mapped_values(row, config.evidence.attributes),
    }
    occurred_at = _optional(row, config.evidence.occurred_at_column)
    if occurred_at:
        evidence["occurred_at"] = occurred_at
    return SourceRecordInput(record_id=f"{file_name}:{raw_record_id}", entities=entities, relations=relations, evidence=evidence)


def _mapped_values(row: dict[str, str | None], fields: dict[str, str]) -> dict[str, str]:
    return {field: value for field, column in fields.items() if (value := _optional(row, column)) is not None}


def _optional(row: dict[str, str | None], column: str | None) -> str | None:
    if not column:
        return None
    value = row.get(column)
    return value.strip() if value and value.strip() else None


def _required(row: dict[str, str | None], column: str, file_name: str, row_number: int) -> str:
    value = _optional(row, column)
    if value is None:
        raise ValueError(f"CSV file '{file_name}', row {row_number}: column '{column}' cannot be empty")
    return value


def _number(row: dict[str, str | None], column: str | None, default: float, file_name: str, row_number: int) -> float:
    value = _optional(row, column)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as error:
        raise ValueError(f"CSV file '{file_name}', row {row_number}: column '{column}' must be numeric") from error
