"""Single source of truth for the placeholder Neo4j schema.

PLACEHOLDER SCHEMA: replace values in this module when the real dataset arrives.
All graph-analysis modules import labels, relationship types, and property names
from here. They must never duplicate those schema identifiers inline.

If the real graph splits entities across labels, update ``ENTITY_NODE_LABELS``.
Every query builder creates a label-union predicate from that tuple; search for
``entity_label_predicate`` when adapting unusual multi-label semantics.
"""
from __future__ import annotations

import re

# Node labels
NODE_LABEL_ENTITY = "Person"
ENTITY_NODE_LABELS = (NODE_LABEL_ENTITY,)
NODE_LABEL_CASE = "Case"
NODE_LABEL_CRITICALITY_RESULT = "CriticalityRank"
NODE_LABEL_CIRCULAR_FLOW_FLAG = "CircularFlowFlag"
NODE_LABEL_STRUCTURING_FLAG = "StructuringFlag"

# Entity and relationship properties
PROP_NODE_ID = "id"
PROP_NODE_NAME = "name"
PROP_CASE_ID = "case_id"
PROP_RELATIONSHIP_ID = "id"

# Relationship types
REL_CALL = "CALLED"
REL_TRANSACTION = "TRANSFERRED_TO"
REL_ASSOCIATION = "ASSOCIATED_WITH"
REL_CASE_LINK = "BELONGS_TO"
STRUCTURAL_REL_TYPES = (REL_CALL, REL_TRANSACTION, REL_ASSOCIATION)
REL_WEIGHT_PROPERTY = "weight"

# Financial relationship properties
TXN_PROP_AMOUNT = "amount"
TXN_PROP_TIMESTAMP = "timestamp"

# Algorithm output contract
PROP_BETWEENNESS = "betweenness_score"
PROP_DEGREE = "degree_score"
PROP_COMMUNITY_ID = "community_id"
PROP_COMMUNITY_SIZE = "community_size"
PROP_STRUCTURAL_ROLE = "structural_role"
REL_SIMILAR_TO = "SIMILAR_TO"
REL_SIMILAR_TO_SCORE_PROP = "score"

# Derived-result schema
REL_HAS_CRITICALITY_RESULT = "HAS_CRITICALITY_RESULT"
PROP_RESULT_RANK = "rank"
PROP_RESULT_NODE_ID = "node_id"
PROP_LARGEST_COMPONENT_BEFORE = "largest_component_before"
PROP_LARGEST_COMPONENT_AFTER = "largest_component_after"
PROP_NUM_COMPONENTS_AFTER = "num_components_after"
PROP_BASELINE_LARGEST_COMPONENT = "baseline_largest_component"
PROP_BASELINE_COMPONENT_COUNT = "baseline_component_count"

PROP_FLAG_ID = "flag_id"
PROP_FLAG_NODE_IDS = "node_ids"
PROP_FLAG_TOTAL_AMOUNT = "total_amount"
PROP_FLAG_CYCLE_LENGTH = "cycle_length"
PROP_FLAG_FROM_NODE = "from_node"
PROP_FLAG_TO_NODE = "to_node"
PROP_FLAG_TRANSACTION_COUNT = "transaction_count"
PROP_FLAG_WINDOW_START = "window_start"
PROP_FLAG_WINDOW_END = "window_end"

# Structural role thresholds
HUB_BETWEENNESS_PERCENTILE = 85
HUB_DEGREE_PERCENTILE = 85
BROKER_BETWEENNESS_PERCENTILE = 85
BROKER_DEGREE_PERCENTILE_MAX = 50

# Fragmentation simulation
CRITICALITY_CANDIDATE_POOL_SIZE = 20
CRITICALITY_DEFAULT_TOP_K = 5

# Financial-pattern rules (placeholders pending dataset calibration)
STRUCTURING_THRESHOLD_AMOUNT = 200_000
STRUCTURING_WINDOW_DAYS = 30
STRUCTURING_MIN_TRANSACTION_COUNT = 3
CIRCULAR_FLOW_MIN_LENGTH = 3
CIRCULAR_FLOW_MAX_LENGTH = 5

_IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PROJECTION_COMPONENT_PATTERN = re.compile(r"[^A-Za-z0-9_]")


def cypher_identifier(value: str) -> str:
    """Quote a trusted config identifier after rejecting unsafe characters."""
    if not _IDENTIFIER_PATTERN.fullmatch(value):
        raise ValueError(f"unsafe schema identifier: {value!r}")
    return f"`{value}`"


def entity_label_predicate(variable: str) -> str:
    """Return a Cypher predicate matching any configured entity label."""
    if not _IDENTIFIER_PATTERN.fullmatch(variable):
        raise ValueError(f"unsafe Cypher variable: {variable!r}")
    return "(" + " OR ".join(
        f"{variable}:{cypher_identifier(label)}" for label in ENTITY_NODE_LABELS
    ) + ")"


def relationship_type_union(types: tuple[str, ...] | list[str]) -> str:
    """Return a safe relationship-type union for a Cypher pattern."""
    return "|".join(cypher_identifier(value) for value in types)


def projection_name(case_id: str, directed: bool = False) -> str:
    suffix = "directed" if directed else "undirected"
    safe_case_id = _PROJECTION_COMPONENT_PATTERN.sub("_", case_id)
    if not safe_case_id:
        raise ValueError("case_id must contain at least one alphanumeric character")
    return f"case_{safe_case_id}_{suffix}"
