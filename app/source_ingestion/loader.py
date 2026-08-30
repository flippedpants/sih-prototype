"""Load mapping definitions from JSON files or request payloads."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import SourceMapping

MAPPING_DIRECTORY = Path(__file__).resolve().parent.parent / "source_mappings"


def load_mapping(source_type: str) -> SourceMapping:
    path = MAPPING_DIRECTORY / f"{source_type}.json"
    if not path.is_file():
        raise KeyError(f"unknown source_type: {source_type}")
    mapping = SourceMapping.model_validate_json(path.read_text())
    if mapping.source_type != source_type:
        raise ValueError(f"mapping source_type '{mapping.source_type}' does not match '{source_type}'")
    return mapping


def parse_mapping(payload: dict[str, Any]) -> SourceMapping:
    return SourceMapping.model_validate(payload)
