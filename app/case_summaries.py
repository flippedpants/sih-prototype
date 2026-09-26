"""Build bounded Zone 2 inputs exclusively from persisted Zone 1 facts."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
import time
from contextlib import nullcontext
from typing import Any

import httpx

from . import schema_config as schema
from .database import distinct_case_ids, managed_driver


def _case_scope(variable: str) -> str:
    if not variable.isidentifier():
        raise ValueError("unsafe Cypher variable")
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    return (
        f"({variable}.{case_prop} = $case_id OR EXISTS {{ MATCH ({variable})-[:{case_link}]->"
        f"(:{case_label} {{{node_id}: $case_id}}) }})"
    )


def _plain(row: Any) -> dict[str, Any] | None:
    if row is None:
        return None
    return row.data() if hasattr(row, "data") else dict(row)


def _json_value(value: Any) -> Any:
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_value(item) for key, item in value.items()}
    return value


def _drop_empty_values(values: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _json_value(value)
        for key, value in values.items()
        if value is not None and value != []
    }


def build_case_summary_context(case_id: str, *, driver: Any | None = None) -> dict[str, Any]:
    """Return a fixed, JSON-safe payload of facts already persisted by Zone 1."""
    labels = schema.entity_label_predicate("node")
    source_labels = schema.entity_label_predicate("source")
    target_labels = schema.entity_label_predicate("target")
    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    case_link = schema.cypher_identifier(schema.REL_CASE_LINK)
    criticality_label = schema.cypher_identifier(schema.NODE_LABEL_CRITICALITY_RESULT)
    criticality_link = schema.cypher_identifier(schema.REL_HAS_CRITICALITY_RESULT)
    circular_label = schema.cypher_identifier(schema.NODE_LABEL_CIRCULAR_FLOW_FLAG)
    structuring_label = schema.cypher_identifier(schema.NODE_LABEL_STRUCTURING_FLAG)
    structural = schema.relationship_type_union(schema.STRUCTURAL_REL_TYPES)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    node_name = schema.cypher_identifier(schema.PROP_NODE_NAME)
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    betweenness = schema.cypher_identifier(schema.PROP_BETWEENNESS)
    degree = schema.cypher_identifier(schema.PROP_DEGREE)
    community = schema.cypher_identifier(schema.PROP_COMMUNITY_ID)
    role = schema.cypher_identifier(schema.PROP_STRUCTURAL_ROLE)
    rank = schema.cypher_identifier(schema.PROP_RESULT_RANK)
    components = schema.cypher_identifier(schema.PROP_NUM_COMPONENTS_AFTER)
    flag_id = schema.cypher_identifier(schema.PROP_FLAG_ID)
    flag_nodes = schema.cypher_identifier(schema.PROP_FLAG_NODE_IDS)
    flag_total = schema.cypher_identifier(schema.PROP_FLAG_TOTAL_AMOUNT)
    flag_cycle = schema.cypher_identifier(schema.PROP_FLAG_CYCLE_LENGTH)
    flag_from = schema.cypher_identifier(schema.PROP_FLAG_FROM_NODE)
    flag_to = schema.cypher_identifier(schema.PROP_FLAG_TO_NODE)
    flag_count = schema.cypher_identifier(schema.PROP_FLAG_TRANSACTION_COUNT)
    flag_start = schema.cypher_identifier(schema.PROP_FLAG_WINDOW_START)
    flag_end = schema.cypher_identifier(schema.PROP_FLAG_WINDOW_END)

    counts_query = f"""
    MATCH (case:{case_label} {{{node_id}: $case_id}})
    CALL (case) {{
      OPTIONAL MATCH (node) WHERE {labels} AND {_case_scope("node")}
      RETURN count(DISTINCT node) AS node_count,
             count(DISTINCT node.{community}) AS community_count
    }}
    CALL (case) {{
      OPTIONAL MATCH (source)-[relationship:{structural}]->(target)
      WHERE {source_labels} AND {target_labels}
        AND {_case_scope("source")} AND {_case_scope("target")}
      RETURN count(DISTINCT relationship) AS edge_count
    }}
    RETURN case.{node_id} AS case_id, node_count, edge_count, community_count
    """
    players_query = f"""
    MATCH (node) WHERE {labels} AND {_case_scope("node")}
    RETURN node.{node_id} AS node_id, node.{node_name} AS name,
           node.{role} AS role, node.{betweenness} AS betweenness_score,
           node.{degree} AS degree_centrality
    ORDER BY node.{betweenness} DESC, node.{node_id}
    LIMIT 5
    """
    communities_query = f"""
    MATCH (node) WHERE {labels} AND {_case_scope("node")}
      AND node.{community} IS NOT NULL
    WITH node.{community} AS raw_community_id, node
    ORDER BY raw_community_id, node.{betweenness} DESC, node.{node_id}
    WITH raw_community_id, collect(node) AS members
    RETURN toString(raw_community_id) AS community_id, size(members) AS size,
           [member IN members | member.{role}] AS roles,
           head(members).{node_id} AS central_node_id,
           head(members).{node_name} AS central_node_name
    ORDER BY size DESC, community_id
    """
    fragmentation_query = f"""
    MATCH (case:{case_label} {{{node_id}: $case_id}})-[:{criticality_link}]->
          (result:{criticality_label})
    WITH result ORDER BY result.{rank} DESC
    WITH collect(result) AS results
    RETURN size(results) AS removed_node_count,
           head(results).{components} AS resulting_component_count
    """
    findings_query = f"""
    MATCH (flag) WHERE (flag:{circular_label} OR flag:{structuring_label})
      AND flag.{case_prop} = $case_id
    RETURN CASE WHEN flag:{circular_label} THEN 'circular_flow' ELSE 'structuring' END AS finding_type,
           flag.{flag_id} AS flag_id, flag.{flag_nodes} AS node_ids,
           flag.{flag_total} AS total_amount, flag.{flag_cycle} AS cycle_length,
           flag.{flag_from} AS from_node, flag.{flag_to} AS to_node,
           flag.{flag_count} AS transaction_count, flag.{flag_start} AS window_start,
           flag.{flag_end} AS window_end
    ORDER BY finding_type, flag_id
    """

    driver_context = nullcontext(driver) if driver is not None else managed_driver()
    with driver_context as active_driver, active_driver.session() as session:
        counts = _plain(session.run(counts_query, case_id=case_id).single())
        players = [_plain(row) for row in session.run(players_query, case_id=case_id)]
        communities = [_plain(row) for row in session.run(communities_query, case_id=case_id)]
        fragmentation = _plain(session.run(fragmentation_query, case_id=case_id).single())
        findings = [_plain(row) for row in session.run(findings_query, case_id=case_id)]

    if counts is None:
        raise ValueError(f"case not found: {case_id}")

    top_key_players = []
    for player in players:
        if player is None:
            continue
        item = {
            "name": player.get("name"),
            "id": player.get("node_id"),
            "role": (player.get("role") or "member").lower(),
            "betweenness_score": player.get("betweenness_score"),
            "degree_centrality": player.get("degree_centrality"),
        }
        top_key_players.append(_drop_empty_values(item))

    community_facts = []
    for item in communities:
        if item is None:
            continue
        role_counts = Counter((value or "member").lower() for value in item.get("roles", []))
        central = _drop_empty_values({
            "id": item.get("central_node_id"),
            "name": item.get("central_node_name"),
        })
        community_facts.append({
            "community_id": item["community_id"],
            "size": int(item["size"]),
            "role_composition": dict(sorted(role_counts.items())),
            "most_central_node": central,
        })

    context: dict[str, Any] = {
        "case_id": counts["case_id"],
        "node_count": int(counts["node_count"]),
        "edge_count": int(counts["edge_count"]),
        "community_count": int(counts["community_count"]),
        "top_key_players": top_key_players,
        "communities": community_facts,
    }
    if fragmentation:
        context["fragmentation_summary"] = _drop_empty_values(fragmentation)
    structural_findings = [
        _drop_empty_values({"type": item.pop("finding_type"), **item})
        for row in findings
        if row is not None
        for item in [dict(row)]
    ]
    if structural_findings:
        context["notable_structural_findings"] = structural_findings
    return context


def build_community_summary_context(
    case_context: dict[str, Any], community_id: str
) -> dict[str, Any]:
    """Select one aggregate community fact without exposing member-level graph data."""
    community = next(
        (item for item in case_context.get("communities", []) if item["community_id"] == community_id),
        None,
    )
    if community is None:
        raise ValueError(f"community not found: {community_id}")
    return {"case_id": case_context["case_id"], **community}


CASE_SUMMARY_SYSTEM_PROMPT = """You are an analyst assistant for a criminal network analysis tool used by
investigators who are NOT graph theorists. You will be given a JSON object
containing already-verified structural facts about a case, computed by
graph algorithms (centrality, community detection, fragmentation
simulation).

Your job is to translate these metrics into what they mean for an
investigation — not to report the metrics. Investigators do not know what
"betweenness centrality" or "degree centrality" means, and a good summary
never assumes they do. Every metric you mention must be immediately
cashed out into its operational meaning. Do not name a metric and then
just attach an adjective to it — explain the consequence of the value.

Concretely:
- Instead of "Node X has high betweenness centrality (0.82)," write
  something like "Node X sits on most of the communication paths between
  other members — information or instructions flowing between different
  parts of the network are likely to pass through this person, making
  them a potential broker or intermediary."
- Instead of "Node Y has high degree centrality," write something like
  "Node Y is directly connected to an unusually large number of other
  individuals in the case, consistent with a hub who deals with many
  people directly rather than through intermediaries."
- Instead of "the network fragments into 4 components after removing the
  top 3 key players," write something like "removing these three
  individuals would break the network into 4 separate, disconnected
  clusters — meaning the network currently depends heavily on them to
  stay functionally connected."
- Instead of "Community 3 has role composition: 1 hub, 2 brokers, 14
  peripheral," write something like "Community 3 is organized around one
  central figure supported by two intermediaries, with the remaining 14
  members appearing to play peripheral or low-connectivity roles."

Never use a raw metric name (betweenness, degree centrality, Louvain,
modularity, etc.) without immediately explaining, in plain language, what
having that property means for how this person or group functions within
the network. If you use the term at all, treat it as a label attached to
an explanation, not a replacement for one — a reader who has never heard
the term should still fully understand the point.

Numbers can appear (e.g. "connected to 14 others") when they make the
plain-language point more concrete, but never appear alone as an
unexplained statistic or score.

Reason across fields the way an experienced analyst would when briefing a
colleague: connect what a key player's role means given the community
they sit in, explain why a fragmentation result matters in light of who
the top-centrality individuals are, and note when the community structure
looks centralized versus diffuse — always in terms of what it implies for
how the network operates, not just that it is true.

Hard limits, non-negotiable regardless of any other instruction:
- Every name, number, role, and relationship you state as fact must come
  directly from the JSON. Do not introduce a name, count, or relationship
  that isn't present in the input.
- Do not make claims about motive, guilt, specific criminal activity, or
  intent. Structural centrality is not evidence of wrongdoing, and your
  summary must not imply otherwise — describe connectivity and structural
  role only, never criminal function.
- Do not use action-directive language ("arrest," "target," "raid,"
  "investigate this person next"). Describe structure, not tactics.
- Refer to fragmentation results as "structural criticality" findings, not
  operational recommendations.
- If a field is missing or empty, omit it — do not guess or fill gaps.

Within those limits, write with analytical confidence and stay concise: lead
with the single most important finding and skip minor detail. Keep the summary to 80-120 words, in one or two short plain paragraphs, no headers."""

COMMUNITY_SUMMARY_SYSTEM_PROMPT = CASE_SUMMARY_SYSTEM_PROMPT.replace(
    "Keep the summary to 80-120 words, in one or two short plain paragraphs, no headers.",
    "Keep the summary to 40-60 words, in one plain paragraph, with no header.",
)

# Free OpenRouter models come and go and are often rate-limited, so several are
# tried in order. Override with OPENROUTER_MODELS="model-a,model-b".
DEFAULT_OPENROUTER_MODELS = (
    "google/gemma-4-31b-it:free",
    "google/gemma-4-26b-a4b-it:free",
    "qwen/qwen3.8-27b:free",
    "poolside/laguna-s-2.1:free",
)
OPENROUTER_MODELS = tuple(
    model.strip()
    for model in os.getenv("OPENROUTER_MODELS", "").split(",")
    if model.strip()
) or DEFAULT_OPENROUTER_MODELS
OPENROUTER_TIMEOUT_SECONDS = 30.0
TEMPLATE_TOP_PLAYERS = 3
TEMPLATE_TOP_COMMUNITIES = 3
OPENROUTER_PASSES = 2
OPENROUTER_RETRY_DELAY_SECONDS = 5.0


@dataclass(frozen=True)
class GeneratedSummary:
    text: str
    source: str


def _display_node(node: dict[str, Any]) -> str:
    node_id = str(node.get("id", ""))
    name = node.get("name")
    return f"{name} ({node_id})" if name else node_id


def _role_counts_text(role_composition: dict[str, Any]) -> str:
    return ", ".join(
        f"{count} {role}{'' if count == 1 else 's'}"
        for role, count in sorted(role_composition.items())
    )


def case_summary_template(context: dict[str, Any]) -> str:
    """Deterministically restate only fields supplied in the fixed case context."""
    paragraphs = [
        f"Case {context['case_id']} contains {context.get('node_count', 0)} nodes and "
        f"{context.get('edge_count', 0)} edges across {context.get('community_count', 0)} "
        "precomputed communities."
    ]
    players = context.get("top_key_players", [])[:TEMPLATE_TOP_PLAYERS]
    if players:
        descriptions = [
            f"{_display_node(player)} ({player.get('role', 'member')})" for player in players
        ]
        paragraphs.append("Highest betweenness: " + ", ".join(descriptions) + ".")
    communities = context.get("communities", [])[:TEMPLATE_TOP_COMMUNITIES]
    if communities:
        descriptions = []
        for community in communities:
            detail = f"community {community['community_id']} ({community['size']} nodes"
            central = community.get("most_central_node")
            if central:
                detail += f", most central {_display_node(central)}"
            descriptions.append(detail + ")")
        paragraphs.append("Largest communities: " + "; ".join(descriptions) + ".")
    fragmentation = context.get("fragmentation_summary")
    if fragmentation:
        details = []
        if fragmentation.get("removed_node_count") is not None:
            details.append(f"removing {fragmentation['removed_node_count']} top-ranked nodes")
        if fragmentation.get("resulting_component_count") is not None:
            details.append(f"leaves {fragmentation['resulting_component_count']} components")
        if details:
            paragraphs.append("Structural criticality: " + " ".join(details) + ".")
    findings = context.get("notable_structural_findings", [])
    if findings:
        descriptions = [
            f"{item.get('type')} flag {item.get('flag_id')}"
            for item in findings
        ]
        paragraphs.append("The stored structural flags are " + ", ".join(descriptions) + ".")
    return "\n\n".join(paragraphs)


def community_summary_template(context: dict[str, Any]) -> str:
    """Return a 40-60 word deterministic description of one persisted community."""
    central = context.get("most_central_node") or {}
    central_text = _display_node(central) or "No named node"
    roles = _role_counts_text(context.get("role_composition", {})) or "no stored role counts"
    return (
        f"Community {context['community_id']} in case {context['case_id']} contains "
        f"{context.get('size', 0)} nodes. Its persisted structural-role composition is {roles}. "
        f"{central_text} has the highest stored betweenness centrality within this community. "
        "This summary describes verified structural measurements only and does not infer motive, "
        "intent, or activity."
    )


def _extract_response_text(payload: Any) -> str:
    if not isinstance(payload, dict):
        raise ValueError("malformed LLM response")
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("empty LLM response")
    first_choice = choices[0]
    if not isinstance(first_choice, dict):
        raise ValueError("malformed LLM response")
    message = first_choice.get("message")
    if not isinstance(message, dict):
        raise ValueError("malformed LLM response")
    content = message.get("content")
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty LLM response")
    return content.strip()


def _request_summary(context: dict[str, Any], system_prompt: str, max_output_tokens: int) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]
    base_url = os.getenv("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
    user_content = "Summarize the following case data:\n" + json.dumps(
        context, sort_keys=True, separators=(",", ":")
    )
    last_error: Exception | None = None
    for attempt in range(OPENROUTER_PASSES):
        if attempt:
            time.sleep(OPENROUTER_RETRY_DELAY_SECONDS)
        for model in OPENROUTER_MODELS:
            try:
                response = httpx.post(
                    f"{base_url}/chat/completions",
                    headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                    json={
                        "model": model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_content},
                        ],
                        "max_tokens": max_output_tokens,
                    },
                    timeout=OPENROUTER_TIMEOUT_SECONDS,
                )
                response.raise_for_status()
                return _extract_response_text(response.json())
            except Exception as error:
                last_error = error
    raise last_error if last_error else RuntimeError("no OpenRouter models configured")


def generate_case_summary(context: dict[str, Any]) -> GeneratedSummary:
    try:
        return GeneratedSummary(_request_summary(context, CASE_SUMMARY_SYSTEM_PROMPT, 1200), "llm")
    except Exception:
        return GeneratedSummary(case_summary_template(context), "template")


def generate_case_summary_llm(context: dict[str, Any]) -> str:
    return generate_case_summary(context).text


def generate_community_summary(context: dict[str, Any]) -> GeneratedSummary:
    try:
        return GeneratedSummary(_request_summary(context, COMMUNITY_SUMMARY_SYSTEM_PROMPT, 150), "llm")
    except Exception:
        return GeneratedSummary(community_summary_template(context), "template")


def generate_community_summary_llm(context: dict[str, Any]) -> str:
    return generate_community_summary(context).text


def precompute_case_summaries(driver: Any, case_id: str) -> dict[str, Any]:
    """Generate once from fixed contexts and replace persisted summary records."""
    context = build_case_summary_context(case_id, driver=driver)
    case_summary = generate_case_summary(context)
    community_rows = []
    generated_at = datetime.now(UTC).isoformat()
    for community in context.get("communities", []):
        community_context = build_community_summary_context(context, community["community_id"])
        summary = generate_community_summary(community_context)
        community_rows.append({
            "community_id": community["community_id"],
            "summary_text": summary.text,
            "summary_source": summary.source,
            "generated_at": generated_at,
        })

    case_label = schema.cypher_identifier(schema.NODE_LABEL_CASE)
    community_label = schema.cypher_identifier(schema.NODE_LABEL_COMMUNITY_SUMMARY)
    community_link = schema.cypher_identifier(schema.REL_HAS_COMMUNITY_SUMMARY)
    node_id = schema.cypher_identifier(schema.PROP_NODE_ID)
    case_prop = schema.cypher_identifier(schema.PROP_CASE_ID)
    community_id = schema.cypher_identifier(schema.PROP_COMMUNITY_ID)
    summary_text = schema.cypher_identifier(schema.PROP_CASE_SUMMARY_TEXT)
    generated = schema.cypher_identifier(schema.PROP_CASE_SUMMARY_GENERATED_AT)
    source = schema.cypher_identifier(schema.PROP_CASE_SUMMARY_SOURCE)
    case_query = f"""
    MATCH (case:{case_label} {{{node_id}: $case_id}})
    SET case.{summary_text} = $summary_text,
        case.{generated} = $generated_at,
        case.{source} = $summary_source
    RETURN case.{node_id} AS case_id
    """
    delete_query = f"""
    MATCH (case:{case_label} {{{node_id}: $case_id}})-[:{community_link}]->
          (old:{community_label})
    DETACH DELETE old
    """
    community_query = f"""
    MATCH (case:{case_label} {{{node_id}: $case_id}})
    UNWIND $rows AS row
    CREATE (summary:{community_label})
    SET summary.{case_prop} = $case_id,
        summary.{community_id} = row.community_id,
        summary.{summary_text} = row.summary_text,
        summary.{generated} = row.generated_at,
        summary.{source} = row.summary_source
    CREATE (case)-[:{community_link}]->(summary)
    """
    with driver.session() as session:
        stored_case = _plain(session.run(
            case_query,
            case_id=case_id,
            summary_text=case_summary.text,
            summary_source=case_summary.source,
            generated_at=generated_at,
        ).single())
        if stored_case is None:
            raise ValueError(f"case not found: {case_id}")
        session.run(delete_query, case_id=case_id).consume()
        session.run(community_query, case_id=case_id, rows=community_rows).consume()
    return {
        "case_id": case_id,
        "case_source": case_summary.source,
        "community_count": len(community_rows),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Precompute bounded Zone 2 summaries")
    parser.add_argument("case_id", nargs="?", help="One case; defaults to every discovered case")
    args = parser.parse_args()
    with managed_driver() as driver:
        case_ids = [args.case_id] if args.case_id else distinct_case_ids(driver)
        for case_id in case_ids:
            result = precompute_case_summaries(driver, case_id)
            print(
                f"Summaries stored for {case_id}: {result['community_count']} communities, "
                f"case source {result['case_source']}"
            )


if __name__ == "__main__":
    main()
