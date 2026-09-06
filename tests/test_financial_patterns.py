from datetime import datetime, timedelta, timezone

from app.detect_financial_patterns import (
    Transaction,
    detect_circular_flows,
    detect_structuring,
    persist_financial_flags,
)


def test_circular_flow_requires_increasing_timestamps_and_deduplicates_rotations():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transactions = [
        Transaction("t1", "a", "b", 10, start),
        Transaction("t2", "b", "c", 20, start + timedelta(hours=1)),
        Transaction("t3", "c", "a", 30, start + timedelta(hours=2)),
        Transaction("late", "b", "a", 5, start - timedelta(hours=1)),
    ]
    flags = detect_circular_flows(transactions)
    assert len(flags) == 1
    assert flags[0].node_ids == ("a", "b", "c")
    assert flags[0].total_amount == 60


def test_structuring_detects_three_subthreshold_transfers_in_window():
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    transactions = [
        Transaction(f"t{i}", "a", "b", 50_000, start + timedelta(days=i * 5))
        for i in range(3)
    ] + [Transaction("large", "a", "b", 250_000, start)]
    flags = detect_structuring(
        transactions,
        threshold=200_000,
        minimum_count=3,
        window_days=30,
    )
    assert len(flags) == 1
    assert flags[0].transaction_count == 3
    assert flags[0].total_amount == 150_000


def test_financial_flag_persistence_is_case_scoped_and_idempotent(fake_driver):
    persist_financial_flags(fake_driver, "CASE-A", [], [])
    query_text = "\n".join(query for query, _ in fake_driver.calls)
    assert "CircularFlowFlag" in query_text
    assert "StructuringFlag" in query_text
    assert "DETACH DELETE" in query_text
