from app import schema_config as schema


def test_placeholder_schema_contract_is_centralized():
    assert schema.ENTITY_NODE_LABELS == ("Person",)
    assert schema.STRUCTURAL_REL_TYPES == ("CALLED", "TRANSFERRED_TO", "ASSOCIATED_WITH")
    assert schema.PROP_BETWEENNESS == "betweenness_score"
    assert schema.PROP_STRUCTURAL_ROLE == "structural_role"
    assert schema.STRUCTURING_THRESHOLD_AMOUNT == 200_000


def test_projection_names_are_safe_and_deterministic():
    assert schema.projection_name("CASE-01") == "case_CASE_01_undirected"
    assert schema.projection_name("CASE-01", directed=True) == "case_CASE_01_directed"
    assert schema.cypher_identifier("valid_name") == "`valid_name`"
