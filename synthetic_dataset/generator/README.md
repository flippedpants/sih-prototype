# Indian Cyber-Financial Crime Synthetic Dataset Generator

Implements the "Indian Criminal Network Synthetic Dataset Specification" (Parts A-E, v2 final).

## Quick start

```bash
pip install faker
python3 generate_dataset.py --n-cases 10 --output-dir ./my_dataset --seed 42
```

Validation runs automatically after generation by default. Skip it with `--no-validate`
if you want faster iteration during development (not recommended for anything you'll
actually use downstream).

Run validation standalone on an existing dataset:
```bash
python3 validation.py --output-dir ./my_dataset
```

Run the six specific demonstration tests (fraud-amount consistency, money flow,
referential integrity, NER accuracy, ground truth, topology) with readable evidence:
```bash
python3 demo_tests.py --output-dir ./my_dataset
```

---

## V1.1 Changes

This pass fixed real bugs found on review of the V1 package - not cosmetic changes.
Each is described with what was actually broken, not just what changed.

### 1. Fraud amount now has a single source of truth (`fraud_events.py`, new)

**Bug found:** `evidence_txn.py` called `sample_victim_loss()` once when building a
victim's mule chain, then called it AGAIN with fresh randomness when computing the
aggregator->cashout total - producing a completely unrelated number. `fir_generator.py`
called `rng.randint(10000, 500000)` independently, a THIRD unrelated amount. A case
could report three different numbers for what was supposed to be one fraud event.

**Fix:** `fraud_events.py` is new. `build_fraud_events()` runs once per case,
immediately after the topology is built and before any evidence generation, and
produces one `FraudEvent` per victim/chain containing the initial amount and the
exact amount at every hop. Transactions, FIR narratives, ground truth, and the new
case-level summary all read from this same object. Nothing downstream calls
`sample_victim_loss()` or `sample_commission()` a second time for the same event.

### 2. Financial flow is now built from real upstream transactions, not resampled

**Bug found:** the aggregator->cashout batch total was computed as
`sum(sample_victim_loss(...) for _ in range(n_chains)) * 0.85` - brand new random
numbers with no relationship to what actually moved through the mule chains.
Separately, the mule chain's *last* hop (final mule -> aggregator) had a planted
relationship but **no transaction was ever generated for it at all** - the last leg
of the money trail was simply missing from the evidence.

**Fix:** the aggregator's cashout total is now `sum(fe.final_amount_to_aggregator for
fe in fraud_events)`, i.e. the actual amount that arrived via the real per-chain
transactions, minus one explicit aggregator-layer commission. Every hop in a chain -
including the final mule-to-aggregator hop - is now included in `chain_accounts` and
gets a real transaction row.

### 3. Money-conservation rule (documented and enforced by construction)

- Hop 0 (victim -> first mule): full pass-through, victim takes no cut.
- Hop *k* (*k* >= 1): the sending mule keeps a commission (first-hop / later-hop /
  aggregator buckets, per Part E's revised rates) before forwarding the rest.
- No hop can forward more than it received - enforced structurally in
  `fraud_events.py` (each `hop_amount` is computed as a strict fraction of the
  previous), not checked after the fact.
- No external funding source is modeled in V1.1; all money entering the system
  originates from a victim's `initial_amount`.

### 4. Referential integrity - the dangling cashout reference is fixed

**Bug found:** the cashout operator had no real `BANK_ACCOUNT` record. The
aggregator->cashout transaction's `receiver_account_id` was a fabricated string,
`f"CASHOUT-{person_id}"`, that never matched anything in `accounts.csv` - a dangling
foreign key that validation now would have caught immediately (and does, if
re-introduced - see `validate_financial_integrity`).

**Fix:** `topology.py` now generates a real `BANK_ACCOUNT` for the cashout operator,
exactly like every other role. `universe.cashout_account_id` and
`universe.aggregator_account_id` are explicit, unambiguous fields on `CaseUniverse`
rather than being re-derived by searching relationship lists.

### 5. `validation.py` (new) - runs automatically after every generation run

Reads back the actual written files (not in-memory generator state - the two can
diverge in ways an in-memory check would never catch) and validates:

- **Entity integrity** - unique IDs, every foreign key (phone->person,
  account->person, vehicle->person) resolves.
- **CDR integrity** - caller/receiver phones exist, durations positive, timestamps parse.
- **Financial integrity** - sender/receiver accounts exist, amounts positive, AND
  every transaction is cross-checked against `fraud_events.json`'s expected hop
  amount (this is what would have caught bugs #1/#2 immediately, had it existed
  before this pass).
- **FIR integrity** - every NER-referenced entity ID exists.
- **NER integrity** - for every span, `narrative_text[start:end]` is checked
  character-for-character against the referenced entity's canonical value.
- **Ground truth integrity** - every role/community/relationship entity exists;
  roles are from the valid set.
- **Ground truth isolation** - confirms `persons.csv`/`accounts.csv` do NOT contain
  `hidden_role`/`hidden_community_id`/`hidden_mule_status` columns (this was already
  correctly excluded in V1's `to_row()` methods; validation now proves it rather than
  assuming it).
- **Topology** - confirms every required D1 and D2 planted-edge type is actually
  present in ground truth for every case, and that every planted D2 TRANSACTED edge
  has a matching real transaction record.

A validation run with any `ERROR`-severity issue is printed clearly and the CLI
reports it prominently - it does not fail silently.

### 6. FIR narrative consistency

**Bug found (secondary):** the FIR cited the bank of the ring's far-downstream
*aggregator* account - something a real complainant would have no way to know,
since victims only ever interact with the first hop they were told to pay.

**Fix:** the FIR now cites `chain_accounts[1]`'s bank (the actual first-hop account
the victim was told to transfer to). The amount named in the FIR is now
`fraud_event.initial_amount`, tracked as an NER span with label `AMOUNT` (entity_id
is `None` since amounts aren't a master-table entity type - validated by presence
and cross-checked in `demo_tests.py`'s Test 1, not by entity-ID lookup).

### 7. A second, unrelated reproducibility bug was found and fixed

**Bug found during testing (not requested, but caught by actually running the
reproducibility test rather than assuming it would pass):** `Faker` maintains its
own internal random state, completely separate from Python's `random` module. Every
other part of the generator seeds a `random.Random(case_seed)` instance correctly,
but `entities.py`'s Faker calls (`fake.name()`, `fake.address()`, etc.) were never
tied to that seed at all - meaning `--seed 42` run twice produced **different**
names, addresses, and FIR text every time, despite every other part of the case
being identical.

**Fix:** `entities.py` now exposes `seed_faker(seed)`, called once per case in
`generate_dataset.py` with the same `case_seed` used for that case's
`random.Random` instance. Verified: two independent runs with `--seed 99` now
produce **byte-identical** output directories (confirmed with `diff -rq`).

### 8. CASE_SUMMARY.json (new) and a rounding-consistency fix within it

New per-case file with `total_fraud_amount`, `aggregator_account_id`, and
`cashout_account_id` - gives validation (and a human) one place to check the
case-level total against. During testing, the first version of this file computed
its total by summing full-precision floats and rounding once, while
`fraud_events.json` rounds each event to 2 decimals before storing it - these two
orders of operations don't agree past a few paise, and validation correctly flagged
it as a mismatch on the first 10-case test run. Fixed by summing the *same* rounded
per-event values in both places.

---

## Test results (10-case run, seed 42)

```
Cases:                 10
Persons:               3,989
Organizations:         10
Phones:                3,853
Accounts:              3,690
CDR records:           8,913
Transactions:          3,703
FIRs:                  921

ENTITY_INTEGRITY       PASS
CDR_INTEGRITY          PASS
FINANCIAL_INTEGRITY    PASS
FIR_INTEGRITY          PASS
NER_INTEGRITY          PASS
GROUND_TRUTH_INTEGRITY PASS
GROUND_TRUTH_ISOLATION PASS
TOPOLOGY               PASS

Errors: 0
Warnings: 0
```

`demo_tests.py` additionally confirmed, with concrete printed evidence (not just a
pass count):
- **Test 1 (fraud amount consistency):** case/transaction/FIR amounts match exactly
  for every case sampled.
- **Test 2 (money flow):** every sampled mule chain shows strictly decreasing
  amounts hop-to-hop, ending at the aggregator, matching `fraud_events.json` exactly.
- **Test 3 (referential integrity):** 0 dangling references.
- **Test 4 (NER):** 2,763 / 2,763 spans matched their source text exactly (100.00%).
- **Test 5 (ground truth):** 6,738 / 6,738 ground-truth role entities exist.
- **Test 6 (topology):** all 10 cases have complete D1 + D2 structure.
- **Reproducibility:** two independent `--seed 99` runs produced byte-identical output.

---

## What's implemented (V1.1, per Part A scope)

- Topology D1 (hierarchical call-centre/investment-app operation) + D2 (mule-account
  chain), combined, per case.
- Innocent-contact control cluster (D3's negative-control spirit).
- Full entity set: PERSON, ORGANIZATION, PHONE, BANK_ACCOUNT, VEHICLE, LOCATION.
- CDR generation from planted CALLED edges only.
- Transaction generation entirely driven by `fraud_events.py`'s single source of
  truth, with the revised heavy-tailed victim-loss distribution and
  layer-conditioned mule commission (Part E v2).
- FIR narrative generation with automatically-computed NER spans, including AMOUNT
  as a tracked span.
- BNS/IT Act legal-section assignment.
- Noise injection: aliases, phone formatting variants, duplicate records, missing
  fields - confirmed to remain resolvable to their canonical entity, not just
  present.
- Two-pass relationship architecture: planted ground truth (hidden, isolated - now
  validated, not just designed that way) vs. derived relationships recomputed from
  actual generated evidence.
- EVIDENCE_FILE metadata simulating the upload/auto-classify workflow.
- **New in V1.1:** `validation.py`, `fraud_events.py`, `demo_tests.py`,
  `CASE_SUMMARY.json`, confirmed seeded reproducibility.

## What's NOT yet implemented (honest scope note - unchanged from V1, by design)

- **D4 (bridge/intermediary between two rings)** and **D5 (interstate spread)** -
  intentionally deferred to V1.2, per this pass's explicit scope boundary. Each case
  is still one self-contained ring.
- FIR files are `.txt`, not rendered `.pdf`.
- The exact NCRP/1930 complaint-form field list (E.12) remains a reasonable
  placeholder, not independently re-verified against the official portal.
- **Not yet claimed as production-ready.** This pass proves internal coherence at
  small scale (10 cases, ~4,000 persons). It has not been tested at the scale
  implied by "large-scale generation" in the original roadmap, and no performance/
  memory profiling has been done. The `AMOUNT` NER label was added without updating
  Part E's original NER label list in the specification documents themselves - the
  generator and validator agree with each other, but the specification document
  should be updated to match before this is treated as fully spec-locked.
- `demo_tests.py`'s Test 1 amount-consistency check has a soft float-vs-rounded-string
  comparison (`abs(... ) < 1.0`) rather than exact equality, since the FIR narrative
  intentionally displays a rounded whole-rupee string while the underlying value
  carries paise - this is correct behavior, not a bug, but worth knowing if you
  extend the test.

## File map

| File | Spec section | V1.1 status |
|---|---|---|
| config.py | E.16 (all tunable parameters) | unchanged |
| ids.py | E.1 | unchanged |
| entities.py | E.4-E.9 | **fixed** (Faker seeding) |
| topology.py | Part D (D1, D2, D3-control) | **fixed** (real cashout account, full chain incl. aggregator) |
| fraud_events.py | E.11 (revised) | **new** - the core V1.1 fix |
| evidence_cdr.py | E.10 | unchanged |
| evidence_txn.py | E.11 (revised) | **fixed** (consumes fraud_events, no resampling) |
| fir_generator.py | E.12 (revised) | **fixed** (consumes fraud_events, correct bank reference, AMOUNT span) |
| noise.py | E.15 | unchanged (resolvability confirmed by validation) |
| relationships.py | E.13 | unchanged |
| ground_truth.py | E.14 | **fixed** (exports fraud_events.json) |
| export.py | E.3, E.18 | **fixed** (CASE_SUMMARY.json, rounding consistency) |
| validation.py | new (V1.1 requirement) | **new** |
| demo_tests.py | new (V1.1 requirement) | **new** |
| generate_dataset.py | E.0 (orchestrator) | **fixed** (wires fraud_events, Faker seeding, --validate flag) |
