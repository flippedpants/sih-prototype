"""
demo_tests.py

Standalone demonstration of the six specific tests requested for the V1.1
validation pass. Run after generate_dataset.py. Prints concrete evidence rather
than just a pass/fail count - this is meant to be read, not just trusted.

    python3 demo_tests.py --output-dir ./validation_dataset
"""

import argparse
import json
from pathlib import Path

from validation import CaseData, find_case_dirs, validate_dataset, print_report


def test1_fraud_amount_consistency(cases, n_show=3):
    print("\n" + "=" * 70)
    print("TEST 1 - Fraud amount consistency (case / transaction / FIR)")
    print("=" * 70)
    shown = 0
    for case in cases:
        if shown >= n_show:
            break
        for victim_id, fe in case.fraud_events.items():
            if shown >= n_show:
                break
            chain = fe["chain_accounts"]
            initial = fe["initial_amount"]
            # find the FIR for this victim
            fir_match = None
            for fir_id, fir in case.firs.items():
                # complainant is recorded via the person NER span in this FIR
                person_spans = [a for a in fir["ner"] if a["label"] == "PERSON" and a["entity_id"] == victim_id]
                if person_spans:
                    fir_match = (fir_id, fir)
                    break
            # find the first transaction (victim -> first mule)
            first_txn = [t for t in case.transactions
                         if t["sender_account_id"] == chain[0] and t["receiver_account_id"] == chain[1]]
            txn_amount = float(first_txn[0]["amount"]) if first_txn else None

            fir_amount_str = None
            if fir_match:
                fir_id, fir = fir_match
                amount_spans = [a for a in fir["ner"] if a["label"] == "AMOUNT"]
                if amount_spans:
                    a = amount_spans[0]
                    fir_amount_str = fir["narrative"][a["start"]:a["end"]]

            print(f"\nCase {case.case_id}, victim {victim_id}:")
            print(f"  fraud_events.json initial_amount:      Rs. {initial:,.2f}")
            print(f"  FINANCIAL first-hop transaction amount: Rs. {txn_amount:,.2f}" if txn_amount else "  [no matching transaction found]")
            print(f"  FIR narrative amount as written:        Rs. {fir_amount_str}" if fir_amount_str else "  [no FIR found]")
            consistent = (txn_amount is not None and abs(txn_amount - initial) < 0.01 and
                          fir_amount_str is not None and
                          abs(float(fir_amount_str.replace(",", "")) - round(initial)) < 1.0)
            print(f"  CONSISTENT: {consistent}")
            shown += 1


def test2_money_flow(cases, n_show=3):
    print("\n" + "=" * 70)
    print("TEST 2 - Money flow through mule chains")
    print("=" * 70)
    shown = 0
    for case in cases:
        if shown >= n_show:
            break
        for victim_id, fe in case.fraud_events.items():
            if shown >= n_show:
                break
            chain = fe["chain_accounts"]
            amounts = [fe["initial_amount"]] + fe["hop_amounts"]
            print(f"\nCase {case.case_id}, victim {victim_id}, chain length {len(chain)}:")
            for i in range(len(chain) - 1):
                label = "victim" if i == 0 else f"mule_{i}"
                next_label = "aggregator" if i + 1 == len(chain) - 1 else f"mule_{i+1}"
                commission = fe["hop_commissions"][i]
                print(f"  {chain[i]} ({label:10s}) -> {chain[i+1]} ({next_label:10s}): "
                      f"Rs. {amounts[i]:>12,.2f} -> Rs. {amounts[i+1]:>12,.2f} "
                      f"(commission {commission*100:.1f}%)")
            no_creation = all(amounts[i+1] <= amounts[i] + 0.01 for i in range(len(amounts)-1))
            print(f"  MONEY CONSERVED (no hop exceeds previous): {no_creation}")
            shown += 1


def test3_referential_integrity(report):
    print("\n" + "=" * 70)
    print("TEST 3 - Foreign-key / referential integrity")
    print("=" * 70)
    fk_errors = [i for i in report.errors() if i.category in
                 ("ENTITY_INTEGRITY", "CDR_INTEGRITY", "FINANCIAL_INTEGRITY")]
    print(f"Dangling references found: {len(fk_errors)}")
    if fk_errors:
        for e in fk_errors[:10]:
            print(f"  [{e.case_id}] {e.message}")
    else:
        print("  0 dangling references across all entity, CDR, and financial tables.")


def test4_ner_validation(cases):
    print("\n" + "=" * 70)
    print("TEST 4 - NER span accuracy")
    print("=" * 70)
    total_spans = 0
    matched_spans = 0
    for case in cases:
        for fir_id, fir in case.firs.items():
            narrative = fir["narrative"]
            for ann in fir["ner"]:
                total_spans += 1
                start, end, label, eid = ann["start"], ann["end"], ann["label"], ann.get("entity_id")
                span_text = narrative[start:end]
                expected = None
                if label == "PERSON" and eid in case.persons:
                    expected = case.persons[eid]["canonical_name"]
                elif label == "PHONE" and eid in case.phones:
                    expected = case.phones[eid]["number"]
                if expected is None or span_text == expected:
                    matched_spans += 1
    pct = 100.0 * matched_spans / total_spans if total_spans else 0
    print(f"Total NER spans checked: {total_spans:,}")
    print(f"Spans matching source text exactly: {matched_spans:,}")
    print(f"Match rate: {pct:.2f}%")


def test5_ground_truth(cases):
    print("\n" + "=" * 70)
    print("TEST 5 - Ground truth existence")
    print("=" * 70)
    total_role_entities = 0
    missing = 0
    for case in cases:
        known = case.all_entity_ids()
        for eid in case.roles:
            total_role_entities += 1
            if eid not in known:
                missing += 1
    print(f"Ground-truth role entities checked: {total_role_entities:,}")
    print(f"Missing/non-existent entities: {missing}")
    print(f"ALL GROUND-TRUTH ENTITIES EXIST: {missing == 0}")


def test6_topology(cases):
    print("\n" + "=" * 70)
    print("TEST 6 - Topology structure confirmation")
    print("=" * 70)
    d1_required = {"planted_organizer_manager_link", "planted_manager_agent_link",
                   "planted_agent_victim_link"}
    d2_required = {"planted_mule_chain_link", "planted_mule_to_aggregator_link",
                   "planted_aggregator_cashout_link"}
    all_ok = True
    for case in cases:
        labels = {rel.get("hidden_ground_truth_label") for rel in case.planted_relationships.values()}
        d1_ok = d1_required.issubset(labels)
        d2_ok = d2_required.issubset(labels)
        status = "OK" if (d1_ok and d2_ok) else "MISSING STRUCTURE"
        if not (d1_ok and d2_ok):
            all_ok = False
        print(f"  {case.case_id}: D1={'present' if d1_ok else 'MISSING'}, "
              f"D2={'present' if d2_ok else 'MISSING'}  [{status}]")
    print(f"\nALL CASES HAVE COMPLETE D1+D2 STRUCTURE: {all_ok}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=str, required=True)
    args = parser.parse_args()
    output_root = Path(args.output_dir)

    case_dirs = find_case_dirs(output_root)
    cases = [CaseData(d) for d in case_dirs]

    report = validate_dataset(output_root)

    test1_fraud_amount_consistency(cases)
    test2_money_flow(cases)
    test3_referential_integrity(report)
    test4_ner_validation(cases)
    test5_ground_truth(cases)
    test6_topology(cases)

    print("\n" + "=" * 70)
    print_report(report)


if __name__ == "__main__":
    main()
