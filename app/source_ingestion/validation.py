"""Structural and per-row validation for config-driven source ingestion."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Mapping

from .models import SourceMapping


class StructuralValidationError(ValueError):
    """A file cannot be parsed because its structure does not match its mapping."""


class MappingError(StructuralValidationError):
    pass


def normalize_header(value: str) -> str:
    return value.strip().lower()


def resolve_column(df_columns: list[str], aliases: list[str], field_name: str, required: bool = True) -> str | None:
    normalized = {normalize_header(column): column for column in df_columns}
    for alias in aliases:
        if normalize_header(alias) in normalized:
            return normalized[normalize_header(alias)]
    if required:
        raise MappingError(f"{field_name}: tried aliases {aliases}; file headers: {df_columns}")
    return None


def resolve_mapping_columns(headers: list[str], mapping: SourceMapping, file_name: str) -> SourceMapping:
    """Resolve only configured aliases; never infer column meaning."""
    resolved = mapping.model_copy(deep=True)
    failures: list[str] = []
    def pick(aliases, name, required=True):
        try: return resolve_column(headers, aliases, name, required)
        except MappingError as error: failures.append(str(error)); return None
    raw_blocks = resolved.entities if resolved.row_maps_to != "entity" else [resolved]
    for index, block in enumerate(raw_blocks):
        if resolved.row_maps_to == "edge":
            aliases = block.column_aliases or ([block.column] if block.column else [])
            block.column = pick(aliases, f"entity[{index}].id") or ""
            continue
        aliases = block.id_column_aliases or ([block.id_column] if block.id_column else [])
        block.id_column = pick(aliases, f"entity[{index}].id") or ""
        block.canonical_name_column = pick(block.canonical_name_aliases or ([block.canonical_name_column] if block.canonical_name_column else []), f"entity[{index}].canonical_name", bool(block.canonical_name_aliases or block.canonical_name_column))
        block.aliases_column = pick(block.aliases_column_aliases or ([block.aliases_column] if block.aliases_column else []), f"entity[{index}].aliases", False)
        block.attribute_columns = [column for name, aliases in block.attribute_column_aliases.items() if (column := pick(aliases, f"entity[{index}].attribute.{name}", False))]
    for index, block in enumerate(resolved.relationship_blocks()):
        block.source_column = pick(block.source_column_aliases or ([block.source_column] if block.source_column else []), f"relationship[{index}].source") or ""
        block.target_column = pick(block.target_column_aliases or ([block.target_column] if block.target_column else []), f"relationship[{index}].target") or ""
        weights = block.weight_columns if isinstance(block.weight_columns, dict) else {name: [name] for name in block.weight_columns}
        block.weight_columns = [column for name, spec in weights.items() if (column := pick(spec.get("aliases", []) if isinstance(spec, dict) else spec, f"relationship[{index}].weight.{name}", bool(spec.get("required", False)) if isinstance(spec, dict) else True))]
        spec = block.timestamp_column
        block.timestamp_column = pick(spec.get("aliases", []) if isinstance(spec, dict) else ([spec] if isinstance(spec, str) else []), f"relationship[{index}].timestamp", bool(spec.get("required", False)) if isinstance(spec, dict) else bool(spec))
    if failures:
        message = f"column resolution failed for source_type={mapping.source_type}, file={file_name}: " + " | ".join(failures)
        logging.getLogger(__name__).error(message)
        raise MappingError(message)
    return resolved


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
