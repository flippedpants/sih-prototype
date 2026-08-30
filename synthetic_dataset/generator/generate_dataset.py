"""
generate_dataset.py

Orchestrator + CLI. Generates N complete synthetic cases, following the E.0
dependency order exactly:

  1. CASE  ->  2. topology  ->  3. entities (in topology.py)  ->  4. planted
  relationships  ->  5. CALLS  ->  6. TRANSACTIONS  ->  7. FIR + NER  ->
  8. EVIDENCE_FILE  ->  9. noise  ->  10. GROUND_TRUTH export

Usage:
    python3 generate_dataset.py --n-cases 5 --output-dir /path/to/output --seed 42
"""

import argparse
import random
from datetime import datetime
from pathlib import Path

from config import DEFAULT_CONFIG, INDIAN_STATES
from ids import IdFactory
from topology import build_case_topology
from entities import seed_faker
from fraud_events import build_fraud_events
from evidence_cdr import generate_calls
from evidence_txn import generate_transactions
from fir_generator import generate_fir_for_chain
from noise import apply_all_noise
from relationships import derive_relationships
from export import export_case
from validation import validate_dataset, print_report


def generate_one_case(id_factory, cfg, rng, year: int, case_seed: int):
    seed_faker(case_seed)   # V1.1 FIX: tie Faker's internal RNG to the same seed
    case_id = id_factory.next_case_id(year)
    case_type = rng.choices(
        list(cfg.case_type_weights.keys()),
        weights=list(cfg.case_type_weights.values()), k=1)[0]
    base_state = rng.choice(INDIAN_STATES)
    anchor_date = datetime(year, rng.randint(1, 12), rng.randint(1, 28))

    # steps 2-4: topology + entities + planted relationships
    universe = build_case_topology(id_factory, cfg, rng, case_id, case_type, base_state)

    # V1.1: build the single source of truth for every fraud amount in this
    # case, BEFORE any evidence is generated. Nothing downstream may resample.
    fraud_events = build_fraud_events(cfg, rng, universe)
    fraud_events_by_victim = {fe.victim_person_id: fe for fe in fraud_events}

    # step 5: CDR
    calls = generate_calls(id_factory, cfg, rng, universe, anchor_date)

    # step 6: transactions - now built entirely from fraud_events, not resampled
    transactions = generate_transactions(id_factory, cfg, rng, universe, fraud_events, anchor_date)

    # step 7: FIR + NER (one FIR per victim/mule-chain, per the "one victim files
    # one complaint" pattern - mules/organizer/manager deliberately not named)
    police_station_name = None
    for loc in universe.locations.values():
        if loc.location_type == "police_station":
            police_station_name = loc.name
            break

    firs = []
    agents = universe.role_index.get("AGENT", [])
    victims = universe.role_index.get("VICTIM", [])
    # map each victim to the agent who called them (best-effort via planted rels)
    victim_agent_map = {}
    for rel in universe.planted_relationships:
        if rel.role_pair == ("AGENT", "VICTIM"):
            victim_agent_map[rel.target_id] = rel.source_id

    for v_id in victims:
        agent_id = victim_agent_map.get(v_id, agents[0] if agents else None)
        fe = fraud_events_by_victim.get(v_id)
        if agent_id is None or fe is None:
            continue
        fir = generate_fir_for_chain(
            id_factory, cfg, rng, universe, case_type, v_id, agent_id,
            fe, anchor_date, police_station_name or "Cyber Cell")
        firs.append(fir)

    # step 9: noise (applied before export, after all evidence generated)
    apply_all_noise(id_factory, cfg, rng, universe)

    # pass-2 derived relationships (what the analysis pipeline actually sees)
    reference_date = datetime(year, 12, 31)
    derived = derive_relationships(id_factory, cfg, calls, transactions, firs, reference_date)

    return universe, firs, calls, transactions, derived, fraud_events, anchor_date


def generate_dataset(n_cases: int, output_dir: str, seed: int = None, year: int = 2026,
                      validate: bool = True):
    cfg = DEFAULT_CONFIG
    seed = seed if seed is not None else cfg.default_seed
    output_root = Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    summary = []
    id_factory = IdFactory()   # shared across the whole run: IDs are globally unique
    for i in range(n_cases):
        case_seed = seed + i
        rng = random.Random(case_seed)

        universe, firs, calls, transactions, derived, fraud_events, anchor_date = generate_one_case(
            id_factory, cfg, rng, year, case_seed)

        case_dir = export_case(output_root, universe, firs, calls, transactions,
                                derived, fraud_events, id_factory, cfg, rng, anchor_date)

        summary.append({
            "case_id": universe.case_id,
            "n_persons": len(universe.persons),
            "n_calls": len(calls),
            "n_transactions": len(transactions),
            "n_firs": len(firs),
            "n_mule_chains": len(universe.mule_chain_order),
            "path": str(case_dir),
        })
        print(f"[{i+1}/{n_cases}] Generated {universe.case_id}: "
              f"{len(universe.persons)} persons, {len(calls)} calls, "
              f"{len(transactions)} transactions, {len(firs)} FIRs")

    if validate:
        print("\nRunning validation suite...")
        report = validate_dataset(output_root)
        print_report(report)
        if report.errors():
            print(f"\n*** VALIDATION FAILED: {len(report.errors())} error(s) found. "
                  f"Dataset written but should NOT be treated as coherent. ***")
        else:
            print(f"\nValidation passed with 0 errors ({len(report.warnings())} warnings).")

    return summary


def main():
    parser = argparse.ArgumentParser(description="Generate synthetic Indian cyber-financial crime cases")
    parser.add_argument("--n-cases", type=int, default=5, help="Number of cases to generate")
    parser.add_argument("--output-dir", type=str, default="./output", help="Output directory")
    parser.add_argument("--seed", type=int, default=None, help="Base random seed")
    parser.add_argument("--year", type=int, default=2026, help="Synthetic anchor year")
    parser.add_argument("--validate", dest="validate", action="store_true", default=True,
                         help="Run the validation suite after generation (default: on)")
    parser.add_argument("--no-validate", dest="validate", action="store_false",
                         help="Skip validation (faster, not recommended)")
    args = parser.parse_args()

    summary = generate_dataset(args.n_cases, args.output_dir, args.seed, args.year, args.validate)
    print(f"\nDone. {len(summary)} cases written to {args.output_dir}")


if __name__ == "__main__":
    main()
