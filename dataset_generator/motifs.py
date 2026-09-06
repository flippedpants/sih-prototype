"""
Motif generators: one function per ring topology defined in the schema
spec, Section 4. Each function returns {"nodes": [...], "edges": [...],
"case_metadata": {...}} for exactly one case, built entirely from
entities.py factory functions.
"""

import math
import random
from datetime import datetime, timedelta

from config import (
    DORMANCY_DAYS_RANGE,
    MOTIF_TIMING_HOURS,
    MULE_TYPE_WEIGHTS,
    RECRUITMENT_CHANNELS,
    RING_SIZE_TIERS,
    SCAM_SUBTYPES,
)
from entities import make_account, make_crypto_exit, make_person, make_recruiter_platform

# ASSUMPTION: decay constant for computed_weight's exp(-lambda * days_since)
# term. Chosen so the recency factor roughly halves every ~14 days
# (ln(2)/14 ~= 0.0495), keeping recent transactions dominant without
# zeroing out month-old ones entirely.
WEIGHT_LAMBDA = 0.05

# ASSUMPTION: reference "now" that every "days_since" in computed_weight is
# measured against - i.e. the dataset's generation time.
REFERENCE_DATE = datetime(2026, 9, 4)


def sample_mule_type():
    """Weighted sample of mule_type per config.MULE_TYPE_WEIGHTS."""
    types, weights = zip(*MULE_TYPE_WEIGHTS.items())
    return random.choices(types, weights=weights, k=1)[0]


def _sample_frequency():
    # ASSUMPTION: schema's computed_weight formula uses "frequency" (repeat
    # transfers represented by that edge). A literal single hop has
    # frequency=1, which zeroes log(frequency) for every edge. We model each
    # edge as 1-4 batched transfers - itself a documented mule behavior
    # (several small transfers rather than one lump sum) - so the formula
    # stays meaningful instead of degenerating to zero everywhere.
    return random.randint(1, 4)


def compute_weight(amount, timestamp, frequency=None):
    """log(frequency) * exp(-lambda * days_since) * log(amount), per schema Sec. 3.1."""
    if frequency is None:
        frequency = _sample_frequency()
    days_since = max((REFERENCE_DATE - timestamp).days, 0)
    return math.log(frequency) * math.exp(-WEIGHT_LAMBDA * days_since) * math.log(amount)


def make_transaction_edge(source_id, target_id, amount, timestamp, channel):
    """Builds one TRANSACTION edge dict per schema Sec. 3.1."""
    return {
        "source_id": source_id,
        "target_id": target_id,
        "type": "TRANSACTION",
        "amount": round(amount, 2),
        "timestamp": timestamp.isoformat(),
        "channel": channel,
        "computed_weight": round(compute_weight(amount, timestamp), 6),
    }


def _make_mule_person_and_account(mule_layer, force_mule_type=None, recruitment_channel=None):
    """Person+Account pair for a mule, with mule_type-specific behavioral
    signature per schema Sec. 5 (kyc_status, opened_via_bc, account_age_days,
    recruitment_channel)."""
    mule_type = force_mule_type or sample_mule_type()
    channel = recruitment_channel
    if mule_type == "deceived" and channel is None:
        channel = random.choice(RECRUITMENT_CHANNELS)
    person = make_person(role="mule", mule_type=mule_type, recruitment_channel=channel)

    if mule_type == "synthetic_kyc":
        # near-zero prior history, often opened via a compromised BC channel
        account = make_account(
            person["id"], mule_layer=mule_layer, kyc_status="fake_or_stolen",
            opened_via_bc=random.random() < 0.6, account_age_days=random.randint(0, 10),
        )
    elif mule_type == "deceived":
        # fewer/larger transactions, first-time-banking-user profile
        account = make_account(
            person["id"], mule_layer=mule_layer, kyc_status="verified",
            account_age_days=random.randint(30, 400),
        )
    else:  # complicit
        account = make_account(
            person["id"], mule_layer=mule_layer, kyc_status=random.choice(["verified", "minimal"]),
        )
    return person, account


def _case_metadata(case_id, scam_subtype, motif, size_tier, nodes, edges, created_at):
    total_amount = sum(e["amount"] for e in edges if e["type"] == "TRANSACTION")
    return {
        "case_id": case_id,
        "scam_subtype": scam_subtype,
        "motif": motif,
        "ring_size_tier": size_tier,
        "created_at": created_at.isoformat(),
        "last_updated": created_at.isoformat(),
        "node_count": len(nodes),
        "total_amount_inr": round(total_amount, 2),
    }


def generate_fast_pass_through(case_id: str, scam_subtype: str, size_tier: str) -> dict:
    """
    Linear chain victim -> mule -> mule -> exit, no fan-out. The full chain
    completes inside MOTIF_TIMING_HOURS['fast_pass_through'], matching the
    documented near-zero-net-within-48-hours mule signature.

    ASSUMPTION: this motif is structurally a fixed 3-hop chain by
    definition ("no fan-out"), so size_tier is recorded in case_metadata
    but does not change the chain length.
    """
    nodes, edges = [], []
    created_at = REFERENCE_DATE - timedelta(days=random.randint(1, 300))
    amount = random.uniform(*SCAM_SUBTYPES[scam_subtype]["amount_range"])

    victim_person = make_person(role="victim")
    victim_account = make_account(victim_person["id"])
    nodes += [victim_person, victim_account]

    mule1_person, mule1_account = _make_mule_person_and_account(mule_layer="layer_1")
    mule2_person, mule2_account = _make_mule_person_and_account(mule_layer="layer_2")
    nodes += [mule1_person, mule1_account, mule2_person, mule2_account]

    exit_person = make_person(role="mastermind")
    exit_account = make_account(exit_person["id"], is_exit_node=True, account_age_days=random.randint(1, 15))
    nodes += [exit_person, exit_account]

    lo, hi = MOTIF_TIMING_HOURS["fast_pass_through"]
    third = hi / 3
    t1 = created_at
    t2 = t1 + timedelta(hours=random.uniform(lo / 3, max(lo / 3 + 0.1, third)))
    t3 = t2 + timedelta(hours=random.uniform(lo / 3, max(lo / 3 + 0.1, third)))

    edges.append(make_transaction_edge(victim_account["id"], mule1_account["id"], amount, t1,
                                        random.choice(["upi", "neft_imps"])))
    edges.append(make_transaction_edge(mule1_account["id"], mule2_account["id"], amount * random.uniform(0.85, 0.98),
                                        t2, random.choice(["upi", "neft_imps"])))
    edges.append(make_transaction_edge(mule2_account["id"], exit_account["id"], amount * random.uniform(0.8, 0.95),
                                        t3, random.choice(["upi", "neft_imps", "atm_withdrawal"])))

    case_metadata = _case_metadata(case_id, scam_subtype, "fast_pass_through", size_tier, nodes, edges, created_at)
    return {"nodes": nodes, "edges": edges, "case_metadata": case_metadata}


def generate_fan_out_fan_in(case_id: str, scam_subtype: str, size_tier: str) -> dict:
    """
    Victim -> layer-1 mule -> 2-4 layer-2 mules -> converge on one hub
    account. Layer-1->layer-2 hops are faster than layer-2->hub hops, both
    bounded by MOTIF_TIMING_HOURS['fan_out_fan_in'] - matches I4C's Layer
    1/Layer 2 terminology and layering's purpose of defeating single-account
    thresholds.

    ASSUMPTION: the schema describes a single victim/layer-1/hub unit. To
    reach the ring_size_tier's node-count range we repeat that unit as
    multiple parallel layer-1 branches (each still fanning into its own
    2-4 layer-2 mules) that all converge on one shared hub account, rather
    than inventing a different topology for "large" rings.
    """
    nodes, edges = [], []
    created_at = REFERENCE_DATE - timedelta(days=random.randint(1, 300))
    lo, hi = MOTIF_TIMING_HOURS["fan_out_fan_in"]

    target_size = random.randint(*RING_SIZE_TIERS[size_tier])
    per_branch_nodes = 2 * (1 + 1 + 3)  # victim + layer1 + ~3 layer2, 2 entities each
    num_branches = max(1, round(target_size / per_branch_nodes))

    hub_person = make_person(role="mastermind")
    hub_account = make_account(hub_person["id"], is_exit_node=True, account_age_days=random.randint(1, 20))
    nodes += [hub_person, hub_account]

    for _ in range(num_branches):
        amount = random.uniform(*SCAM_SUBTYPES[scam_subtype]["amount_range"])
        victim_person = make_person(role="victim")
        victim_account = make_account(victim_person["id"])
        nodes += [victim_person, victim_account]

        l1_person, l1_account = _make_mule_person_and_account(mule_layer="layer_1")
        nodes += [l1_person, l1_account]

        t_in = created_at + timedelta(hours=random.uniform(0, 24))
        edges.append(make_transaction_edge(victim_account["id"], l1_account["id"], amount, t_in,
                                            random.choice(["upi", "neft_imps"])))

        n_layer2 = random.randint(2, 4)
        layer2_accounts = []
        for _ in range(n_layer2):
            p, a = _make_mule_person_and_account(mule_layer="layer_2")
            nodes += [p, a]
            layer2_accounts.append(a)
            t_mid = t_in + timedelta(hours=random.uniform(lo, max(lo + 0.1, hi / 3)))
            share = amount / n_layer2 * random.uniform(0.8, 1.0)
            edges.append(make_transaction_edge(l1_account["id"], a["id"], share, t_mid,
                                                random.choice(["upi", "neft_imps"])))

        for a in layer2_accounts:
            t_out = t_in + timedelta(hours=random.uniform(hi / 2, hi))
            share = amount / n_layer2 * random.uniform(0.75, 0.95)
            edges.append(make_transaction_edge(a["id"], hub_account["id"], share, t_out,
                                                random.choice(["upi", "neft_imps", "atm_withdrawal"])))

    case_metadata = _case_metadata(case_id, scam_subtype, "fan_out_fan_in", size_tier, nodes, edges, created_at)
    return {"nodes": nodes, "edges": edges, "case_metadata": case_metadata}


def generate_dormant_then_burst(case_id: str, scam_subtype: str, size_tier: str) -> dict:
    """
    A previously dormant account (no transactions for DORMANCY_DAYS_RANGE
    days) suddenly receives a lump sum from a victim and fans it out to
    several recipient accounts within MOTIF_TIMING_HOURS['dormant_then_burst']
    hours. Matches the Indian Banks' Association mule indicator: sudden
    activity spike plus high counterparty count after a quiet account
    history.
    """
    nodes, edges = [], []
    dormancy_days = random.randint(*DORMANCY_DAYS_RANGE)
    burst_start = REFERENCE_DATE - timedelta(days=random.randint(1, 200))
    created_at = burst_start - timedelta(days=dormancy_days)
    amount = random.uniform(*SCAM_SUBTYPES[scam_subtype]["amount_range"])

    victim_person = make_person(role="victim")
    victim_account = make_account(victim_person["id"])
    nodes += [victim_person, victim_account]

    dormant_person, dormant_account = _make_mule_person_and_account(mule_layer="layer_1")
    # account existed through the dormancy window before the burst
    dormant_account["visible"]["account_age_days"] = dormancy_days + random.randint(10, 60)
    nodes += [dormant_person, dormant_account]

    edges.append(make_transaction_edge(victim_account["id"], dormant_account["id"], amount, burst_start,
                                        random.choice(["upi", "neft_imps"])))

    lo, hi = MOTIF_TIMING_HOURS["dormant_then_burst"]
    target_size = random.randint(*RING_SIZE_TIERS[size_tier])
    n_recipients = max(3, min(target_size // 3, 20))

    for _ in range(n_recipients):
        p, a = _make_mule_person_and_account(mule_layer="layer_2")
        nodes += [p, a]
        t = burst_start + timedelta(hours=random.uniform(lo, hi))
        share = amount / n_recipients * random.uniform(0.8, 1.0)
        edges.append(make_transaction_edge(dormant_account["id"], a["id"], share, t,
                                            random.choice(["upi", "neft_imps", "atm_withdrawal"])))

    case_metadata = _case_metadata(case_id, scam_subtype, "dormant_then_burst", size_tier, nodes, edges, created_at)
    return {"nodes": nodes, "edges": edges, "case_metadata": case_metadata}


def generate_recruited_crypto_exit(case_id: str, scam_subtype: str, size_tier: str) -> dict:
    """
    RECRUITER_PLATFORM -[RECRUITED_VIA]-> entry-layer mule, then a
    fan-out/fan-in structure that terminates at a crypto off-ramp: the
    final hop moves funds from a mule account (is_exit_node=True) into a
    CRYPTO_OFFRAMP node via a crypto_convert transaction. Matches documented
    bot-driven recruitment pipelines feeding transnational crypto cash-out;
    recruitment precedes the first transaction by days-to-weeks.
    """
    nodes, edges = [], []
    created_at = REFERENCE_DATE - timedelta(days=random.randint(1, 300))
    lo, hi = MOTIF_TIMING_HOURS["recruited_crypto_exit"]

    platform = make_recruiter_platform(channel=random.choice(
        ["telegram_bot", "instagram_bot", "facebook_bot", "whatsapp"]))
    platform["visible"]["pretext"] = "job_offer"
    nodes.append(platform)

    # deceived mules recruited via a job-offer pretext almost always carry a
    # RECRUITED_VIA edge (schema Sec. 5) - force that mule_type for the entry mule
    entry_person, entry_account = _make_mule_person_and_account(
        mule_layer="layer_1", force_mule_type="deceived")
    nodes += [entry_person, entry_account]

    recruited_at = created_at - timedelta(days=random.randint(3, 21))
    edges.append({
        "source_id": platform["id"],
        "target_id": entry_person["id"],
        "type": "RECRUITED_VIA",
        "timestamp": recruited_at.isoformat(),
    })

    victim_person = make_person(role="victim")
    victim_account = make_account(victim_person["id"])
    nodes += [victim_person, victim_account]

    amount = random.uniform(*SCAM_SUBTYPES[scam_subtype]["amount_range"])
    t_in = created_at
    edges.append(make_transaction_edge(victim_account["id"], entry_account["id"], amount, t_in,
                                        random.choice(["upi", "neft_imps"])))

    target_size = random.randint(*RING_SIZE_TIERS[size_tier])
    n_layer2 = max(2, min(target_size // 3, 6))
    layer2_accounts = []
    for _ in range(n_layer2):
        p, a = _make_mule_person_and_account(mule_layer="layer_2")
        nodes += [p, a]
        layer2_accounts.append(a)
        t_mid = t_in + timedelta(hours=random.uniform(lo, max(lo + 0.1, hi / 2)))
        share = amount / n_layer2 * random.uniform(0.8, 1.0)
        edges.append(make_transaction_edge(entry_account["id"], a["id"], share, t_mid,
                                            random.choice(["upi", "neft_imps"])))

    exit_person, exit_account = _make_mule_person_and_account(mule_layer="layer_3plus")
    exit_account["ground_truth"]["is_exit_node"] = True
    nodes += [exit_person, exit_account]

    crypto_node = make_crypto_exit()
    nodes.append(crypto_node)

    for a in layer2_accounts:
        t_out = t_in + timedelta(hours=random.uniform(hi / 2, hi))
        share = amount / n_layer2 * random.uniform(0.75, 0.95)
        edges.append(make_transaction_edge(a["id"], exit_account["id"], share, t_out,
                                            random.choice(["upi", "neft_imps"])))

    t_final = t_in + timedelta(hours=hi + random.uniform(1, 6))
    edges.append(make_transaction_edge(exit_account["id"], crypto_node["id"],
                                        amount * random.uniform(0.7, 0.95), t_final, "crypto_convert"))

    case_metadata = _case_metadata(case_id, scam_subtype, "recruited_crypto_exit", size_tier, nodes, edges, created_at)
    return {"nodes": nodes, "edges": edges, "case_metadata": case_metadata}
