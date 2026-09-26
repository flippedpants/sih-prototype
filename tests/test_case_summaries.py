import json

import httpx

from app import schema_config as schema
from app.case_summaries import (
    CASE_SUMMARY_SYSTEM_PROMPT,
    build_case_summary_context,
    case_summary_template,
    community_summary_template,
    generate_case_summary,
    generate_case_summary_llm,
    generate_community_summary,
    generate_community_summary_llm,
    precompute_case_summaries,
)


def test_build_case_summary_context_uses_only_persisted_facts(fake_driver):
    responses = [
        [{"case_id": "CASE-A", "node_count": 8, "edge_count": 10, "community_count": 2}],
        [
            {"node_id": "P1", "name": "Person One", "role": "BROKER", "betweenness_score": 0.8, "degree_centrality": 4.0},
            {"node_id": "P2", "name": None, "role": "MEMBER", "betweenness_score": 0.4, "degree_centrality": 2.0},
        ],
        [
            {"community_id": "7", "size": 3, "roles": ["BROKER", "MEMBER", "MEMBER"], "central_node_id": "P1", "central_node_name": "Person One"},
        ],
        [{"removed_node_count": 2, "resulting_component_count": 3}],
        [
            {"finding_type": "circular_flow", "flag_id": "F1", "node_ids": ["P1", "P2"], "total_amount": 1000.0, "cycle_length": 2, "from_node": None, "to_node": None, "transaction_count": None, "window_start": None, "window_end": None},
        ],
    ]
    fake_driver.handler = lambda _query, _parameters: responses.pop(0)

    context = build_case_summary_context("CASE-A", driver=fake_driver)

    assert context == {
        "case_id": "CASE-A",
        "node_count": 8,
        "edge_count": 10,
        "community_count": 2,
        "top_key_players": [
            {"name": "Person One", "id": "P1", "role": "broker", "betweenness_score": 0.8, "degree_centrality": 4.0},
            {"id": "P2", "role": "member", "betweenness_score": 0.4, "degree_centrality": 2.0},
        ],
        "communities": [{
            "community_id": "7",
            "size": 3,
            "role_composition": {"broker": 1, "member": 2},
            "most_central_node": {"id": "P1", "name": "Person One"},
        }],
        "fragmentation_summary": {"removed_node_count": 2, "resulting_component_count": 3},
        "notable_structural_findings": [{
            "type": "circular_flow", "flag_id": "F1", "node_ids": ["P1", "P2"],
            "total_amount": 1000.0, "cycle_length": 2,
        }],
    }


def test_summary_context_queries_are_parameterized_and_use_schema_constants(fake_driver):
    fake_driver.handler = lambda _query, _parameters: []

    try:
        build_case_summary_context("CASE-'unsafe", driver=fake_driver)
    except ValueError:
        pass

    query_text = "\n".join(query for query, _ in fake_driver.calls)
    assert "CASE-'unsafe" not in query_text
    assert all(parameters.get("case_id") == "CASE-'unsafe" for _, parameters in fake_driver.calls)
    assert schema.cypher_identifier(schema.PROP_BETWEENNESS) in query_text
    assert schema.cypher_identifier(schema.PROP_STRUCTURAL_ROLE) in query_text
    assert schema.cypher_identifier(schema.PROP_NUM_COMPONENTS_AFTER) in query_text
    assert schema.cypher_identifier(schema.PROP_FLAG_ID) in query_text


SUMMARY_CONTEXT = {
    "case_id": "CASE-A",
    "node_count": 8,
    "edge_count": 10,
    "community_count": 2,
    "top_key_players": [{
        "name": "Person One", "id": "P1", "role": "broker",
        "betweenness_score": 0.8, "degree_centrality": 4.0,
    }],
    "communities": [{
        "community_id": "7", "size": 3, "role_composition": {"broker": 1, "member": 2},
        "most_central_node": {"id": "P1", "name": "Person One"},
    }],
    "fragmentation_summary": {"removed_node_count": 2, "resulting_component_count": 3},
}


class StubResponse:
    def __init__(self, payload, status_code=200):
        self.payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError("failure", request=None, response=None)

    def json(self):
        return self.payload


def test_case_llm_receives_only_fixed_context_and_exact_prompt(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured.update({"url": url, **kwargs})
        return StubResponse({"choices": [{"message": {"content": "Verified summary."}}]})

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)

    result = generate_case_summary(SUMMARY_CONTEXT)

    assert result.text == "Verified summary."
    assert result.source == "llm"
    assert captured["url"] == "https://openrouter.ai/api/v1/chat/completions"
    from app import case_summaries

    assert captured["timeout"] == case_summaries.OPENROUTER_TIMEOUT_SECONDS
    assert captured["json"]["model"] == case_summaries.OPENROUTER_MODELS[0]
    assert captured["json"]["messages"][0]["content"] == CASE_SUMMARY_SYSTEM_PROMPT
    user_message = captured["json"]["messages"][1]["content"]
    assert user_message.startswith("Summarize the following case data:")
    assert json.loads(user_message.split("\n", 1)[1]) == SUMMARY_CONTEXT
    assert "tools" not in captured["json"]


def test_case_llm_falls_through_to_next_model_when_one_is_unavailable(monkeypatch):
    from app import case_summaries

    attempted = []

    def fake_post(url, **kwargs):
        model = kwargs["json"]["model"]
        attempted.append(model)
        if model == case_summaries.OPENROUTER_MODELS[0]:
            return StubResponse({}, status_code=429)
        return StubResponse({"choices": [{"message": {"content": "Second model summary."}}]})

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(httpx, "post", fake_post)
    monkeypatch.setattr(case_summaries.time, "sleep", lambda _seconds: None)

    result = generate_case_summary(SUMMARY_CONTEXT)

    assert result.text == "Second model summary."
    assert result.source == "llm"
    assert attempted == list(case_summaries.OPENROUTER_MODELS[:2])


def test_case_llm_failure_and_empty_response_use_template(monkeypatch):
    from app import case_summaries

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(case_summaries.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: (_ for _ in ()).throw(httpx.TimeoutException("slow")))
    expected = case_summary_template(SUMMARY_CONTEXT)

    assert generate_case_summary_llm(SUMMARY_CONTEXT) == expected
    assert generate_case_summary(SUMMARY_CONTEXT).source == "template"

    monkeypatch.setattr(httpx, "post", lambda *_args, **_kwargs: StubResponse({"choices": []}))
    assert generate_case_summary_llm(SUMMARY_CONTEXT) == expected


def test_community_llm_uses_short_prompt_and_template_fallback(monkeypatch):
    context = {"case_id": "CASE-A", **SUMMARY_CONTEXT["communities"][0]}
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    text = generate_community_summary_llm(context)
    result = generate_community_summary(context)

    assert text == community_summary_template(context)
    assert result.source == "template"
    assert 40 <= len(text.split()) <= 60


def test_prompts_set_distinct_length_targets():
    from app import case_summaries

    assert "80-120 words" in case_summaries.CASE_SUMMARY_SYSTEM_PROMPT
    assert "40-60 words" in case_summaries.COMMUNITY_SUMMARY_SYSTEM_PROMPT
    assert "80-120 words" not in case_summaries.COMMUNITY_SUMMARY_SYSTEM_PROMPT


def test_templates_omit_missing_values():
    context = {
        "case_id": "CASE-MISSING", "node_count": 1, "edge_count": 0, "community_count": 0,
        "top_key_players": [{"id": "P1", "role": "member"}],
        "communities": [],
        "fragmentation_summary": {"removed_node_count": 0},
    }

    assert "None" not in case_summary_template(context)


def test_precompute_persists_case_and_community_summaries(monkeypatch, fake_driver):
    from app import case_summaries

    monkeypatch.setattr(case_summaries, "build_case_summary_context", lambda case_id, driver=None: SUMMARY_CONTEXT)
    monkeypatch.setattr(
        case_summaries, "generate_case_summary",
        lambda _context: case_summaries.GeneratedSummary("Case summary text", "template"),
    )
    monkeypatch.setattr(
        case_summaries, "generate_community_summary",
        lambda _context: case_summaries.GeneratedSummary("Community summary text", "llm"),
    )
    fake_driver.handler = lambda query, _parameters: (
        [{"case_id": "CASE-A"}] if "AS case_id" in query else []
    )

    result = precompute_case_summaries(fake_driver, "CASE-A")

    assert result == {"case_id": "CASE-A", "case_source": "template", "community_count": 1}
    query_text = "\n".join(query for query, _ in fake_driver.calls)
    assert schema.cypher_identifier(schema.PROP_CASE_SUMMARY_TEXT) in query_text
    assert schema.cypher_identifier(schema.NODE_LABEL_COMMUNITY_SUMMARY) in query_text
    assert schema.cypher_identifier(schema.REL_HAS_COMMUNITY_SUMMARY) in query_text
    assert "Case summary text" not in query_text
    case_parameters = next(parameters for _, parameters in fake_driver.calls if "summary_text" in parameters)
    assert case_parameters["summary_text"] == "Case summary text"
    assert case_parameters["summary_source"] == "template"
    community_parameters = next(parameters for _, parameters in fake_driver.calls if "rows" in parameters)
    assert community_parameters["rows"][0]["summary_source"] == "llm"
    assert community_parameters["rows"][0]["summary_text"] == "Community summary text"
