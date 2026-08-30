"""
relationships.py

Implements E.13's concretized weight formula and the two-pass ground-truth
architecture (E.0 step 13 / Part E revision Section 12):

  Pass 1 - planted relationships (topology.py output): carry hidden_ground_truth_label,
           used ONLY for ground-truth export and evaluation, never fed to the pipeline.
  Pass 2 - derived relationships: recomputed from the ACTUAL generated calls/transactions/
           FIR co-occurrences. This is what an analysis pipeline would actually see.

    weight = frequency_score x recency_decay x amount_score

    frequency_score  = log(1 + interaction_count)
    recency_decay    = exp(-lambda * days_since_last_interaction)
    amount_score     = log(1 + total_amount) / log(1 + reference_max_amount)   [0-1]
    CALLED-only edges: amount_score = 1 (neutral)
    MENTIONED_IN_FIR edges: fixed weight (no formula)
"""

import math
from collections import defaultdict
from datetime import datetime

from config import GenerationConfig


class DerivedRelationship:
    __slots__ = ("relationship_id", "source_id", "target_id", "relationship_type",
                 "weight", "first_seen", "last_seen", "source_doc")

    def to_row(self):
        return {
            "relationship_id": self.relationship_id,
            "source_id": self.source_id, "target_id": self.target_id,
            "relationship_type": self.relationship_type,
            "weight": round(self.weight, 4),
            "first_seen": self.first_seen.isoformat() if self.first_seen else "",
            "last_seen": self.last_seen.isoformat() if self.last_seen else "",
            "source_doc": self.source_doc or "",
        }


def derive_relationships(id_factory, cfg: GenerationConfig, calls: list,
                          transactions: list, firs: list, reference_date) -> list:
    """Recomputes RELATIONSHIP records from actual generated evidence (pass 2)."""

    call_groups = defaultdict(list)
    for c in calls:
        key = (c.caller_person_id, c.receiver_person_id)
        call_groups[key].append(c)

    txn_groups = defaultdict(list)
    for t in transactions:
        key = (t.sender_account_id, t.receiver_account_id)
        txn_groups[key].append(t)

    derived = []

    max_amount = max([sum(t.amount for t in group) for group in txn_groups.values()],
                      default=1.0)

    for (source, target), group in call_groups.items():
        n = len(group)
        last_ts = max(c.timestamp for c in group)
        first_ts = min(c.timestamp for c in group)
        days_since = max(0, (reference_date - last_ts).days)
        freq_score = math.log(1 + n)
        recency = math.exp(-cfg.recency_decay_lambda * days_since)
        weight = freq_score * recency * 1.0   # amount_score neutral for calls

        rel = DerivedRelationship()
        rel.relationship_id = id_factory.next("relationship")
        rel.source_id, rel.target_id = source, target
        rel.relationship_type = "CALLED"
        rel.weight = weight
        rel.first_seen, rel.last_seen = first_ts, last_ts
        rel.source_doc = "CDR"
        derived.append(rel)

    for (source, target), group in txn_groups.items():
        n = len(group)
        total_amount = sum(t.amount for t in group)
        last_ts = max(t.timestamp for t in group)
        first_ts = min(t.timestamp for t in group)
        days_since = max(0, (reference_date - last_ts).days)
        freq_score = math.log(1 + n)
        recency = math.exp(-cfg.recency_decay_lambda * days_since)
        amount_score = math.log(1 + total_amount) / math.log(1 + max_amount) if max_amount > 0 else 0
        weight = freq_score * recency * amount_score

        rel = DerivedRelationship()
        rel.relationship_id = id_factory.next("relationship")
        rel.source_id, rel.target_id = source, target
        rel.relationship_type = "TRANSACTED"
        rel.weight = weight
        rel.first_seen, rel.last_seen = first_ts, last_ts
        rel.source_doc = "TRANSACTIONS"
        derived.append(rel)

    for fir in firs:
        for ann in fir.ner_annotations:
            rel = DerivedRelationship()
            rel.relationship_id = id_factory.next("relationship")
            rel.source_id = fir.complainant_person_id
            rel.target_id = ann["entity_id"]
            rel.relationship_type = "MENTIONED_IN_FIR"
            rel.weight = cfg.mentioned_in_fir_weight
            rel.first_seen = rel.last_seen = fir.date_filed
            rel.source_doc = fir.fir_id
            derived.append(rel)

    return derived
