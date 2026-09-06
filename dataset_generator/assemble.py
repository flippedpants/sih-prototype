"""
Phase C driver: generates N synthetic mule-network fraud cases (one motif
each), adds a Barabasi-Albert background-noise graph with cross-cluster
links into the rings, merges everything into one combined dataset, writes
it to output/, runs sanity-check assertions, and prints a summary report.
"""

import argparse
import json
import os
import random
import sys
from collections import Counter

from config import RANDOM_SEED, RING_SIZE_TIERS, SCAM_SUBTYPES
from motifs import (
    generate_dormant_then_burst,
    generate_fan_out_fan_in,
    generate_fast_pass_through,
    generate_recruited_crypto_exit,
)
from noise import generate_noise
from rng_streams import derive_seed

MOTIF_GENERATORS = {
    "fast_pass_through": generate_fast_pass_through,
    "fan_out_fan_in": generate_fan_out_fan_in,
    "dormant_then_burst": generate_dormant_then_burst,
    "recruited_crypto_exit": generate_recruited_crypto_exit,
}

# ASSUMPTION: default case count for a hackathon-scale demo dataset;
# override with `python assemble.py <N>`.
DEFAULT_NUM_CASES = 40

# Default seed for reproducible runs; override with `--seed`.
DEFAULT_SEED = RANDOM_SEED

# ASSUMPTION: noise graph sized relative to case count so it provides
# realistic background density without dominating generation time.
NOISE_NODES_PER_CASE = 3
NOISE_CROSS_LINKS_PER_CASE = 1

OUTPUT_DIR = "output"


def generate_dataset(num_cases: int, case_selection_rng, entity_attribute_rng, noise_rng):
    """Generates num_cases motif-driven cases plus one noise graph, merged
    into combined node/edge lists. Returns (nodes, edges, case_metadata,
    motif_counts, subtype_counts, tier_counts, case_node_counts_match).

    case_selection_rng picks each case's motif/scam_subtype/size_tier and is
    also the case_rng threaded into that motif's own structural decisions;
    entity_attribute_rng is threaded through to entities.py's factory calls;
    noise_rng drives generate_noise() entirely. The three streams never mix,
    so a change confined to one of them cannot shift what any of the others
    produce."""
    all_nodes = []
    all_edges = []
    all_case_metadata = []
    motif_counts = Counter()
    subtype_counts = Counter()
    tier_counts = Counter()
    ring_person_ids = []
    case_node_counts_match = True

    motif_names = list(MOTIF_GENERATORS.keys())
    scam_subtypes = list(SCAM_SUBTYPES.keys())
    size_tiers = list(RING_SIZE_TIERS.keys())

    for i in range(1, num_cases + 1):
        case_id = f"C-{i:04d}"
        motif = case_selection_rng.choice(motif_names)
        scam_subtype = case_selection_rng.choice(scam_subtypes)
        size_tier = case_selection_rng.choice(size_tiers)

        result = MOTIF_GENERATORS[motif](case_id, scam_subtype, size_tier,
                                          case_selection_rng, entity_attribute_rng)

        if len(result["nodes"]) != result["case_metadata"]["node_count"]:
            case_node_counts_match = False

        all_nodes.extend(result["nodes"])
        all_edges.extend(result["edges"])
        all_case_metadata.append(result["case_metadata"])
        ring_person_ids.extend(n["id"] for n in result["nodes"] if n["type"] == "PERSON")

        motif_counts[motif] += 1
        subtype_counts[scam_subtype] += 1
        tier_counts[size_tier] += 1

    noise_result = generate_noise(
        num_nodes=num_cases * NOISE_NODES_PER_CASE,
        num_cross_links=num_cases * NOISE_CROSS_LINKS_PER_CASE,
        noise_rng=noise_rng,
        ring_person_ids=ring_person_ids,
    )
    all_nodes.extend(noise_result["nodes"])
    all_edges.extend(noise_result["edges"])

    return (all_nodes, all_edges, all_case_metadata, motif_counts, subtype_counts,
            tier_counts, case_node_counts_match)


def run_sanity_checks(nodes, case_node_counts_match):
    """Returns a list of (description, passed) tuples for the required
    sanity checks."""
    checks = []

    person_role_by_id = {n["id"]: n["ground_truth"]["role"] for n in nodes if n["type"] == "PERSON"}

    mule_layer_ok = True
    for n in nodes:
        if n["type"] != "ACCOUNT":
            continue
        if person_role_by_id.get(n["linked_person_id"]) != "mule":
            continue
        gt = n["ground_truth"]
        if gt["mule_layer"] is None and gt["is_exit_node"] is not True:
            mule_layer_ok = False
            break
    checks.append(("Every mule-role account has mule_layer set or is_exit_node=True", mule_layer_ok))

    checks.append(("Every case_metadata.node_count matches its generated node list", case_node_counts_match))

    ids = [n["id"] for n in nodes]
    checks.append(("No duplicate entity IDs across the combined dataset", len(ids) == len(set(ids))))

    return checks


def write_output(nodes, edges, case_metadata):
    """Writes the combined nodes, edges, and case metadata to OUTPUT_DIR as
    graph_nodes.json, graph_edges.json, and case_metadata.json, overwriting
    any existing files there."""
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    with open(os.path.join(OUTPUT_DIR, "graph_nodes.json"), "w", encoding="utf-8") as f:
        json.dump(nodes, f, indent=2)
    with open(os.path.join(OUTPUT_DIR, "graph_edges.json"), "w", encoding="utf-8") as f:
        json.dump(edges, f, indent=2)
    with open(os.path.join(OUTPUT_DIR, "case_metadata.json"), "w", encoding="utf-8") as f:
        json.dump(case_metadata, f, indent=2)


def print_summary(nodes, edges, case_metadata, motif_counts, subtype_counts, tier_counts, seed):
    """Prints the dataset summary report, including the seed that produced it
    so any run's output can be traced back to a reproducible command."""
    print("=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)
    print(f"Seed: {seed}")
    print(f"Total nodes: {len(nodes)}")
    print(f"Total edges: {len(edges)}")
    print(f"Total cases: {len(case_metadata)}")
    print("\nCases by motif:")
    for motif, count in motif_counts.items():
        print(f"  {motif}: {count}")
    print("\nCases by scam_subtype:")
    for subtype, count in subtype_counts.items():
        print(f"  {subtype}: {count}")
    print("\nCases by size tier:")
    for tier, count in tier_counts.items():
        print(f"  {tier}: {count}")


def parse_args():
    """Parses CLI args: a positional case count (keeps the pre-existing
    `python assemble.py <N>` usage working) plus `--seed` for reproducible
    runs."""
    parser = argparse.ArgumentParser(
        description="Generate a synthetic mule-network fraud dataset (Phase C).")
    parser.add_argument("num_cases", type=int, nargs="?", default=DEFAULT_NUM_CASES,
                         help=f"Number of motif-driven cases to generate (default: {DEFAULT_NUM_CASES})")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED,
                         help=f"Random seed for reproducible generation (default: {DEFAULT_SEED})")
    return parser.parse_args()


def main():
    """CLI entry point: derives the three graph-generation rng streams from
    `--seed`, generates the dataset, writes it to OUTPUT_DIR, prints the
    summary report, and runs sanity checks (exiting with status 1 if any
    check fails)."""
    args = parse_args()

    # Each concern gets its own independent random.Random(), derived from
    # the one user-facing --seed. No global `random.seed()` call and no
    # bare `random.*` calls exist anywhere downstream of this - every
    # function takes an explicit rng parameter - so a change confined to
    # one stream (e.g. entities.py's make_phone) can never shift what
    # another stream (e.g. case_selection's motif picks) produces.
    case_selection_rng = random.Random(derive_seed(args.seed, "case_selection"))
    entity_attribute_rng = random.Random(derive_seed(args.seed, "entity_attribute"))
    noise_rng = random.Random(derive_seed(args.seed, "noise"))

    (nodes, edges, case_metadata, motif_counts, subtype_counts, tier_counts,
     case_node_counts_match) = generate_dataset(
        args.num_cases, case_selection_rng, entity_attribute_rng, noise_rng)

    write_output(nodes, edges, case_metadata)
    print_summary(nodes, edges, case_metadata, motif_counts, subtype_counts, tier_counts, args.seed)

    print("\n" + "=" * 60)
    print("SANITY CHECKS")
    print("=" * 60)
    checks = run_sanity_checks(nodes, case_node_counts_match)
    all_passed = True
    for description, passed in checks:
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_passed = False
        print(f"[{status}] {description}")

    if not all_passed:
        sys.exit(1)


if __name__ == "__main__":
    main()
