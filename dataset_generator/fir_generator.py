"""
Builds one FIR/complaint document (schema spec Section 7) for a given case,
using only values that trace back to that case's actual generated entities
and transactions - never an invented name, amount, or account.

Depends on Phase C's output/graph_nodes.json, graph_edges.json, and
case_metadata.json (see build_case_indices), and on the templates in
text_templates.py.
"""

import re

from text_templates import (
    AUTHORITY_DISPLAY,
    DIGITAL_ARREST_AUTHORITIES,
    DIGITAL_ARREST_TEMPLATES,
    SIMPLE_SUBTYPE_TEMPLATES,
    SLOT_LABELS,
)

_SLOT_RE = re.compile(r"\{(\w+)\}")


def format_inr(amount):
    """Formats a rupee amount using Indian digit grouping, e.g.
    1234567.5 -> '12,34,567.50', matching how such amounts are actually
    written out in an FIR narrative."""
    amount = round(float(amount), 2)
    rupees = int(amount)
    paise = round((amount - rupees) * 100)
    digits = str(rupees)
    if len(digits) <= 3:
        grouped = digits
    else:
        last3 = digits[-3:]
        rest = digits[:-3]
        groups = []
        while len(rest) > 2:
            groups.insert(0, rest[-2:])
            rest = rest[:-2]
        if rest:
            groups.insert(0, rest)
        grouped = ",".join(groups) + "," + last3
    return f"{grouped}.{paise:02d}"


def _usable(template, values):
    """True if every {slot} placeholder in template has a value available in
    `values` - filters out templates needing data this case doesn't have
    (e.g. a `{phone}` template, when no PHONE entities exist at all in the
    current Phase C dataset)."""
    return all(slot in values for slot in _SLOT_RE.findall(template))


def render_template(template, values):
    """Renders one `{slot}`-style template against `values`, building the
    output string and recording each inserted value's exact character span
    as it is appended - never searching for it afterwards, which would give
    the wrong span for any value that happens to repeat elsewhere in the
    text. Returns (text, spans) where spans is a list of
    {"text", "label", "start", "end"} dicts with offsets relative to the
    start of this rendered text."""
    pieces = []
    spans = []
    cursor = 0
    pos = 0
    for match in _SLOT_RE.finditer(template):
        literal = template[pos:match.start()]
        pieces.append(literal)
        cursor += len(literal)

        slot = match.group(1)
        value = str(values[slot])
        start = cursor
        pieces.append(value)
        cursor += len(value)
        spans.append({"text": value, "label": SLOT_LABELS[slot], "start": start, "end": cursor})

        pos = match.end()
    pieces.append(template[pos:])
    return "".join(pieces), spans


def build_case_indices(nodes, edges, case_metadata):
    """Slices the merged Phase C nodes/edges lists back into a per-case view.

    Neither `nodes` nor `edges` carry an explicit case_id field, but
    assemble.py's generation loop appends each case's nodes and edges as one
    contiguous block, in the same order as case_metadata, before the noise
    graph is appended at the very end. That means positional slicing by each
    case_metadata entry's `node_count` recovers exact case membership with no
    change to the generator - verified against `total_amount_inr` (summing
    each case's own TRANSACTION edges reproduces that field exactly).

    Returns {case_id: {"meta", "victims", "account_by_person",
    "transactions"}}.
    """
    index = {}
    cursor = 0
    for meta in case_metadata:
        n = meta["node_count"]
        case_nodes = nodes[cursor:cursor + n]
        cursor += n

        node_ids = {node["id"] for node in case_nodes}
        case_edges = [e for e in edges if e["source_id"] in node_ids and e["target_id"] in node_ids]

        victims = [n for n in case_nodes if n["type"] == "PERSON" and n["ground_truth"]["role"] == "victim"]
        account_by_person = {n["linked_person_id"]: n for n in case_nodes if n["type"] == "ACCOUNT"}
        phone_by_person = {n["linked_person_id"]: n for n in case_nodes if n["type"] == "PHONE"}
        transactions = [e for e in case_edges if e["type"] == "TRANSACTION"]

        index[meta["case_id"]] = {
            "meta": meta,
            "victims": victims,
            "account_by_person": account_by_person,
            "phone_by_person": phone_by_person,
            "transactions": transactions,
        }
    return index


def _victim_first_outflow(case_entry, victim):
    """Returns (amount, target_account_id) for the earliest TRANSACTION edge
    out of this victim's own account - the real amount and real first-hop
    account this victim's money actually moved to. Returns None if the
    victim has no linked account or no recorded outgoing transaction (should
    not happen for a generated fraud ring, but this is checked rather than
    assumed, since a caller must not invent a value in that case)."""
    account = case_entry["account_by_person"].get(victim["id"])
    if account is None:
        return None
    outflows = [e for e in case_entry["transactions"] if e["source_id"] == account["id"]]
    if not outflows:
        return None
    first = min(outflows, key=lambda e: e["timestamp"])
    return first["amount"], first["target_id"]


def generate_fir(case_id, case_index, doc_seq, rng):
    """Builds one FIR document dict for `case_id`. `doc_seq` (1-based) cycles
    through the case's available victims when there is more than one,
    and `rng` (a random.Random) drives which template variant and which
    impersonated authority (digital_arrest only) get chosen.

    Returns None if the case has no victim, or its victim(s) have no
    recorded outgoing transaction to build a real amount/account_ref from -
    in either case there is no real data to build a document from, so none
    is fabricated.
    """
    entry = case_index[case_id]
    victims = entry["victims"]
    if not victims:
        return None

    victim = victims[(doc_seq - 1) % len(victims)]
    outflow = _victim_first_outflow(entry, victim)
    if outflow is None:
        return None
    amount, account_ref = outflow

    values = {
        "victim_name": victim["canonical_name"],
        "amount": format_inr(amount),
        "account_ref": account_ref,
        "location": victim["visible"]["state"],
    }
    victim_phone = entry["phone_by_person"].get(victim["id"])
    if victim_phone is not None:
        values["phone"] = victim_phone["visible"]["phone_number"]

    subtype = entry["meta"]["scam_subtype"]
    if subtype == "digital_arrest":
        authority = rng.choice(DIGITAL_ARREST_AUTHORITIES)
        values["impersonated_authority"] = AUTHORITY_DISPLAY[authority]
        stage_order = ["impersonation", "intimidation", "confinement", "extortion"]
        stage_templates = DIGITAL_ARREST_TEMPLATES
    else:
        stage_order = ["lure", "deposit", "lockout"]
        stage_templates = SIMPLE_SUBTYPE_TEMPLATES[subtype]

    narrative_stages = {}
    labeled_entities = []
    text_pieces = []
    cursor = 0
    for i, stage in enumerate(stage_order):
        candidates = [t for t in stage_templates[stage] if _usable(t, values)]
        template = rng.choice(candidates)
        stage_text, stage_spans = render_template(template, values)

        if i > 0:
            text_pieces.append(" ")
            cursor += 1

        for span in stage_spans:
            labeled_entities.append({
                "text": span["text"],
                "label": span["label"],
                "start": span["start"] + cursor,
                "end": span["end"] + cursor,
            })

        text_pieces.append(stage_text)
        cursor += len(stage_text)
        narrative_stages[stage] = stage_text

    return {
        "doc_id": f"FIR-{case_id}-{doc_seq:02d}",
        "case_id": case_id,
        "scam_subtype": subtype,
        "narrative_stages": narrative_stages,
        "labeled_entities": labeled_entities,
        # Full concatenated narrative (stages joined with a single space, in
        # stage_order) - not part of the Section 7 example, but required for
        # labeled_entities' start/end offsets to mean anything: schema
        # Section 7 shows narrative_stages as separate per-stage strings,
        # and the corpus's self-check explicitly validates spans against
        # "the concatenated document text", so that concatenation has to be
        # stored, not just implied.
        "text": "".join(text_pieces),
    }
