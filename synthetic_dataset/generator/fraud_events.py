"""
fraud_events.py

V1.1 FIX for the most critical bug found in review: victim fraud amounts were
previously generated independently in evidence_txn.py (per chain) AND AGAIN,
completely disconnected, when computing the aggregator->cashout total. The FIR
generator also independently invented a THIRD, unrelated amount. Three different
numbers for what should have been one event.

This module generates each fraud amount exactly ONCE and produces a FraudEvent -
the authoritative record of how much money moved at every hop of one victim's
mule chain. Every other module (transactions, FIR narrative, case summary,
ground truth) reads from this object; none of them re-sample.

Money-conservation rule implemented here (see README's "V1.1 Changes" for the
full explanation):
  - hop 0 (victim -> first mule): full pass-through, no commission. The victim
    sends exactly what they were defrauded of; nothing is deducted at this hop.
  - hop k (k >= 1, mule_k -> mule_k+1 or -> aggregator): the SENDING mule keeps
    a commission (E.11's layer-conditioned rates) before forwarding the rest.
    hop 1's sender is the first mule -> "first_hop" commission bucket.
    hop 2+ -> "later_hop" commission bucket.
  - No hop can forward more than it received. This is enforced by construction
    (each hop_amount is a strict fraction of the previous), not checked after
    the fact.
"""

import random
from dataclasses import dataclass, field

from config import GenerationConfig
from evidence_txn import sample_victim_loss, sample_commission


@dataclass
class FraudEvent:
    """The single authoritative record for one victim's fraud amount and its
    entire downstream money trail, up to (and including) arrival at the
    ring's aggregator account."""
    victim_person_id: str
    chain_accounts: list          # [victim_acct, mule1_acct, ..., aggregator_acct]
    initial_amount: float         # what the victim was defrauded of - THE source of truth
    hop_amounts: list             # amount transferred at each hop, len = len(chain_accounts)-1
    hop_commissions: list         # commission fraction retained at each hop, same length
    final_amount_to_aggregator: float   # = hop_amounts[-1], what actually reaches the aggregator

    def to_ground_truth_dict(self) -> dict:
        return {
            "victim_person_id": self.victim_person_id,
            "chain_accounts": self.chain_accounts,
            "initial_amount": round(self.initial_amount, 2),
            "hop_amounts": [round(a, 2) for a in self.hop_amounts],
            "hop_commissions": [round(c, 4) for c in self.hop_commissions],
            "final_amount_to_aggregator": round(self.final_amount_to_aggregator, 2),
        }


def build_fraud_events(cfg: GenerationConfig, rng: random.Random, universe) -> list:
    """
    Called ONCE per case, immediately after topology construction and before
    any evidence (CDR/transactions/FIR) is generated. Every downstream module
    receives this list and must not call sample_victim_loss/sample_commission
    independently for the same event.
    """
    events = []
    for chain in universe.mule_chain_order:
        victim_person_id = chain["victim_person_id"]
        chain_accounts = chain["chain_accounts"]     # includes aggregator as last element

        initial_amount = sample_victim_loss(cfg, rng)
        hop_amounts = []
        hop_commissions = []
        received = initial_amount

        for i in range(len(chain_accounts) - 1):
            if i == 0:
                # victim -> first mule: full pass-through, victim takes no cut
                sent = received
                commission = 0.0
            else:
                layer = "first_hop" if i == 1 else "later_hop"
                commission = sample_commission(cfg, rng, layer)
                sent = received * (1 - commission)
            hop_amounts.append(sent)
            hop_commissions.append(commission)
            received = sent

        events.append(FraudEvent(
            victim_person_id=victim_person_id,
            chain_accounts=chain_accounts,
            initial_amount=initial_amount,
            hop_amounts=hop_amounts,
            hop_commissions=hop_commissions,
            final_amount_to_aggregator=hop_amounts[-1] if hop_amounts else 0.0,
        ))

    return events
