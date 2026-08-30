"""
evidence_txn.py

Generates the TRANSACTIONS table from planted TRANSACTED relationships (E.11,
revised in Part E v2). Implements:
  - victim_loss_amount: log-normal, anchored to verified 2023-2025 I4C per-complaint
    averages (~66K-1.19L INR), with an explicit high-value tail (50L+, occasional crore).
  - mule commission: layer-conditioned (first hop / later hop / aggregator), anchored
    to one verified real case (Bengaluru CCB, 4% per lakh), not a flat universal rate.
  - hop timing: 2-45 minutes apart, matching the real reported rapid-layering pattern.
"""

import math
import random
from datetime import timedelta

from config import GenerationConfig
from topology import CaseUniverse


class TransactionRecord:
    __slots__ = ("transaction_id", "sender_account_id", "receiver_account_id",
                 "amount", "timestamp", "transaction_type", "source_evidence_file_id")

    def to_row(self):
        return {
            "transaction_id": self.transaction_id,
            "sender_account_id": self.sender_account_id,
            "receiver_account_id": self.receiver_account_id,
            "amount": round(self.amount, 2),
            "timestamp": self.timestamp.isoformat(),
            "transaction_type": self.transaction_type,
            "source_evidence_file_id": self.source_evidence_file_id or "",
        }


def sample_victim_loss(cfg: GenerationConfig, rng: random.Random) -> float:
    """E.11 revised: heavy-tailed, anchored to verified I4C 2023-2025 figures."""
    if rng.random() < cfg.victim_loss_crore_probability:
        return rng.uniform(1_00_00_000, 5_00_00_000)  # occasional crore-level outlier
    if rng.random() < cfg.victim_loss_high_value_probability:
        return rng.uniform(cfg.victim_loss_high_value_floor_inr,
                            cfg.victim_loss_high_value_floor_inr * 3)
    mu = math.log(cfg.victim_loss_lognormal_mean_inr) - (cfg.victim_loss_lognormal_sigma ** 2) / 2
    amount = rng.lognormvariate(mu, cfg.victim_loss_lognormal_sigma)
    return max(1000.0, amount)


def sample_commission(cfg: GenerationConfig, rng: random.Random, layer: str) -> float:
    if rng.random() < cfg.commission_high_tail_probability:
        lo, hi = cfg.commission_high_tail
        return rng.uniform(lo, hi)
    if layer == "first_hop":
        lo, hi, _default = cfg.commission_first_hop
    elif layer == "aggregator":
        lo, hi, _default = cfg.commission_aggregator
    else:
        lo, hi, _default = cfg.commission_later_hop
    return rng.uniform(lo, hi)


def generate_transactions(id_factory, cfg: GenerationConfig, rng: random.Random,
                           universe: CaseUniverse, fraud_events: list, anchor_date) -> list:
    """
    V1.1 FIX: every transaction amount now comes from the pre-computed FraudEvent
    (fraud_events.py) instead of being resampled here. Every hop in a chain,
    including the final mule->aggregator hop, now produces a real transaction
    row - previously that last hop had a planted relationship but no evidence
    row at all.
    """
    txns = []

    for fe in fraud_events:
        chain_accounts = fe.chain_accounts
        t = anchor_date + timedelta(days=rng.randint(0, 30), hours=rng.randint(9, 21))

        for i in range(len(chain_accounts) - 1):
            txn = TransactionRecord()
            txn.transaction_id = id_factory.next("transaction")
            txn.sender_account_id = chain_accounts[i]
            txn.receiver_account_id = chain_accounts[i + 1]
            txn.amount = fe.hop_amounts[i]          # from the single source of truth
            txn.timestamp = t
            txn.transaction_type = rng.choices(
                ["UPI", "IMPS", "NEFT"], weights=[0.6, 0.3, 0.1], k=1)[0]
            txn.source_evidence_file_id = None
            txns.append(txn)

            gap_minutes = rng.randint(*cfg.mule_hop_minutes)
            t = t + timedelta(minutes=gap_minutes)

    txns.extend(generate_aggregator_cashout_transactions(
        id_factory, cfg, rng, universe, fraud_events, anchor_date))

    return txns


def generate_aggregator_cashout_transactions(id_factory, cfg: GenerationConfig,
                                              rng: random.Random, universe: CaseUniverse,
                                              fraud_events: list, anchor_date) -> list:
    """
    V1.1 FIX: the cashout total is now derived from the ACTUAL sum of money that
    arrived at the aggregator (fe.final_amount_to_aggregator across all fraud
    events for this case), not a freshly resampled, unrelated random total. The
    receiver is now a real BANK_ACCOUNT id (universe.cashout_account_id), not a
    fabricated "CASHOUT-{id}" string with no matching entity record.

    Money conservation: total cashed out = total received at aggregator, minus
    one explicit aggregator-layer commission (E.11's "aggregator" bucket) taken
    once for the whole batch. Batch amounts always sum to exactly this total -
    no batch can create money beyond what was actually received.
    """
    txns = []
    if not fraud_events or universe.aggregator_account_id is None or universe.cashout_account_id is None:
        return txns

    total_received = sum(fe.final_amount_to_aggregator for fe in fraud_events)
    if total_received <= 0:
        return txns

    agg_commission = sample_commission(cfg, rng, "aggregator")
    total_available = total_received * (1 - agg_commission)

    n_batches = rng.randint(2, 5)
    t = anchor_date + timedelta(days=rng.randint(5, 45))
    remaining = total_available
    for b in range(n_batches):
        batches_left = n_batches - b
        batch_amount = remaining / batches_left if batches_left > 0 else remaining
        if batch_amount <= 0:
            break
        txn = TransactionRecord()
        txn.transaction_id = id_factory.next("transaction")
        txn.sender_account_id = universe.aggregator_account_id
        txn.receiver_account_id = universe.cashout_account_id   # real account, always exists
        txn.amount = batch_amount
        txn.timestamp = t
        txn.transaction_type = rng.choices(
            ["NEFT", "cash_deposit"], weights=[0.7, 0.3], k=1)[0]
        txn.source_evidence_file_id = None
        txns.append(txn)
        remaining -= batch_amount
        t = t + timedelta(days=rng.randint(1, 10))

    return txns
