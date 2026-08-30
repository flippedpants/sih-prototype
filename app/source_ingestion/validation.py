"""Structural and per-row validation for config-driven source ingestion."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Mapping

from .models import SourceMapping


class StructuralValidationError(ValueError):
    """A file cannot be parsed because its structure does not match its mapping."""


def required_columns(mapping: SourceMapping) -> set[str]:
    columns: set[str] = set()
    for block in mapping.entity_blocks():
        columns.add(block.id_column)
        columns.update(block.attribute_columns)
        if block.canonical_name_column:
            columns.add(block.canonical_name_column)
        if block.aliases_column:
            columns.add(block.aliases_column)
    for block in mapping.relationship_blocks():
        columns.update({block.source_column, block.target_column, *block.weight_columns})
        if block.timestamp_column:
            columns.add(block.timestamp_column)
    return columns


def validate_structure(headers: list[str], rows: list[Mapping[str, object]], mapping: SourceMapping) -> None:
    missing = sorted(required_columns(mapping) - set(headers))
    if missing:
        raise StructuralValidationError(f"missing required columns: {', '.join(missing)}")
    if len(headers) != len(set(headers)):
        raise StructuralValidationError("duplicate column headers are not supported")
    if not mapping.allow_extra_columns:
        unexpected = sorted(set(headers) - required_columns(mapping))
        if unexpected:
            raise StructuralValidationError(f"unexpected columns: {', '.join(unexpected)}")
    null_columns = sorted(column for column in required_columns(mapping) if not any(_value(row.get(column)) for row in rows))
    if null_columns:
        raise StructuralValidationError(f"required columns contain no values: {', '.join(null_columns)}")


def require_value(row: Mapping[str, object], column: str) -> str:
    value = _value(row.get(column))
    if value is None:
        raise ValueError(f"{column} cannot be empty")
    return value


def parse_timestamp(row: Mapping[str, object], column: str | None) -> datetime | None:
    if not column:
        return None
    value = require_value(row, column)
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError(f"{column} must be an ISO-8601 date/time") from error


def parse_weight(row: Mapping[str, object], columns: list[str]) -> float:
    if not columns:
        return 1.0
    try:
        return sum(float(require_value(row, column)) for column in columns)
    except ValueError as error:
        raise ValueError("weight columns must be numeric") from error


def _value(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
