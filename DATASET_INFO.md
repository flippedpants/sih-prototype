# Synthetic Indian Crime Dataset — Phase 1 / V1

This document describes the Phase 1 synthetic-data generator integrated into this
repository at [`synthetic_dataset/generator/`](synthetic_dataset/generator/), and the
dataset it produces. It is documentation for the generator and its output only. For
the overall project (Phases 2-5: graph construction, network analysis, API,
dashboard), see [`criminal-network-analysis-project.md`](criminal-network-analysis-project.md),
which this file does not modify or restate.

## 1. Why synthetic data

The eventual analysis system (later phases) needs data to develop and test against,
but real FIRs, CDRs, and financial records are sensitive, restricted, and not
available for a hackathon-stage project. Phase 1 instead generates a **coherent,
self-consistent synthetic investigation dataset** — with a hidden ground-truth
criminal network planted inside it — so that later phases can be built and validated
against something that behaves like real investigation evidence, without touching
real personal data. Because the ground truth is known by construction, the analysis
system's output can be scored against it directly (precision/recall on network
recovery), which is not possible with real, unlabeled case data.

## 2. Phase 1

Phase 1 is the synthetic-data-generation phase of the project — it produces the
input evidence that later phases (entity resolution, graph construction, network
analysis, API, dashboard) will consume. Phase 1 does not do any graph analysis,
NER modeling, or entity resolution itself; it only generates data and validates
its own internal consistency.

Conceptual pipeline:

```
Synthetic criminal network
        ↓
Synthetic entities
        ↓
Underlying case events
        ↓
FIR + CDR + financial evidence
        ↓
Controlled noise + innocent contacts
        ↓
Hidden ground truth
        ↓
Validation
        ↓
Synthetic investigation dataset
```

## 3. V1 (this integration)

V1 is the current generator baseline, integrated from a previously developed and
validated implementation (v1.1). It implements two planted network structures per
case, **D1** and **D2**. Later structures (D3 as an implemented negative control,
D4, D5) and the analysis pipeline itself are out of scope for this integration —
see [Future work](#9-future-work).

### D1 — Hierarchical criminal network

```
Organizer
    ↓
Manager
   / \
Agent Agent
   ↓
Victims
```

A call-centre-phishing or fake-investment-app operation: an Organizer directs one
or two Managers, each Manager runs several Agents, and each Agent works a set of
victims. Calls (CDRs) are generated along these planted edges — organizer↔manager,
manager↔agent, agent↔victim — with distinct call-volume and duration patterns at
each layer.

### D2 — Mule / financial network

```
Victim
  ↓
Mule 1
  ↓
Mule 2 (0-3 further mule hops)
  ↓
Aggregator
  ↓
Cashout
```

Each victim's fraud payment moves through a chain of 2-4 intermediate mule
accounts before reaching a shared Aggregator account and finally a Cashout
account. Every hop is a real transaction between two real generated bank
accounts (see [Section 7](#7-fraud-event-source-of-truth)).

An **innocent-contact cluster** is also generated per case (in the spirit of a
D3 negative control): people connected to case entities through ordinary,
non-criminal contact, present so that the eventual analysis system has to
distinguish real network structure from incidental social/family noise.

## 4. Entities

Each case generates a self-contained universe of:

- **Persons** — offenders (organizer/manager/agent/mule/aggregator/cashout
  operator/recruiter/intermediary), victims, and innocent contacts
- **Organizations** — e.g. the shell company behind a fake investment app
- **Phones** — one or more per person, used for CDR generation
- **Bank accounts** — one or more per person, used for transaction generation
- **Vehicles** — generated for a subset of persons
- **Locations** — Indian states/districts drawn from a curated subset (see
  [Section 8](#8-synthetic-vs-source-backed-parameters))
- **Cases** — the top-level container (`CASE_<case_id>/`)
- **Evidence files** — simulated metadata for every file a case would produce
  if uploaded and auto-classified (filename, detected type, classification
  confidence, investigator override)

The same synthetic person, phone, and account IDs are reused consistently across
every evidence type for that case — a CDR referencing `PH-000003` and a
transaction referencing `ACC-000004` both resolve back to the same planted
person record.

## 5. Evidence

Each case directory (`CASE_<case_id>/`) contains:

- **`FIR/`** — one narrative FIR text file per victim/mule-chain, with legal
  section citations (BNS / IT Act), UTR number, and suspected email (both
  sometimes intentionally missing — see [Noise](#6-ner)), plus
  `_ner_annotations/` holding the entity spans for that FIR (see below)
- **`CDR/`** — call detail records generated only from planted CALLED edges
  (organizer-manager, manager-agent, agent-victim, recruiter-mule onboarding)
- **`FINANCIAL/`** — transaction records for every hop of every mule chain,
  driven entirely by the fraud-event source of truth
- **`ENTITIES/`** — `persons.csv`, `phones.csv`, `accounts.csv`,
  `organizations.csv`, `vehicles.csv`, `locations.csv`, and
  `derived_relationships.csv` (relationships recomputed from the actual
  generated evidence — the "pass 2" view, distinct from ground truth; see
  [Section 10](#10-ground-truth))
- **`EVIDENCE_META/evidence_files.csv`** — simulates what an "upload
  everything, auto-classify" ingestion step would record for each file
- **`CASE_SUMMARY.json`** — case-level totals (total fraud amount, victim/chain
  counts, aggregator and cashout account IDs) for quick cross-checking
- **`GROUND_TRUTH/`** — hidden evaluation data, kept separate from every file
  above (see [Section 10](#10-ground-truth))

## 6. NER

FIR narratives are template-generated, and the generator knows exactly where
each synthetic entity (person name, phone number) or fraud amount was inserted
into the text — so instead of running an NER model over the finished text, it
records the exact character span at generation time. Each `_ner_annotations/*.json`
file is a list of `{start, end, label, entity_id}` records, where `label` is
one of `PERSON`, `PHONE`, or `AMOUNT` (amounts have `entity_id: null` since a
rupee figure isn't a master-table entity). This gives ground-truth-accurate NER
labels for free, without training or running an actual model — useful later as
labeled data for a real NER model, but it is not itself an NER model.

## 7. Fraud event source of truth

Every mule chain's money flow is generated once, up front, per case
(`fraud_events.py`), before any FIR, CDR, or transaction file is written. Each
`FraudEvent` records a victim's initial loss and the exact amount remaining at
every subsequent hop (after each mule's commission is deducted). All downstream
evidence — the transaction rows, the FIR narrative's stated amount, the
ground-truth mule-chain record, and `CASE_SUMMARY.json`'s case-level total — read
from this same object. No amount is independently re-sampled anywhere else in the
pipeline, so a case cannot report three different numbers for what was meant to
be one fraud event.

Money conservation is enforced by construction: hop 0 (victim → first mule) is a
full pass-through; every later hop forwards a strict fraction of what it
received, after the sending mule's commission; no hop can ever forward more than
it received; and no money enters the system from anywhere other than a victim's
initial loss.

## 8. Synthetic vs. source-backed parameters

`synthetic_dataset/generator/config.py` tags every tunable generation parameter
with one of three status labels, and this distinction should be preserved
whenever the dataset's numbers are discussed:

- **FACT** — source-backed (e.g. the list of Indian states/NCRB-style
  geography categories)
- **ASSUMPTION** — informed by real reporting (e.g. victim-loss amounts are a
  log-normal distribution calibrated so its mean falls in the ₹66K-₹1.19L
  range reported in 2023-2025 I4C data; the offender gender split is softened
  from a real skew, not measured directly) but not a confirmed official
  statistic
- **RULE** — a deliberate synthetic-design choice with no claim to real-world
  accuracy (e.g. mule chain length of 2-4 hops, commission rate ranges, noise
  injection probabilities, case-type split)

None of the numbers this generator produces — victim counts, loss amounts,
demographic splits, commission rates, evidence density — should be cited as
official Indian crime statistics. They are calibrated synthetic modeling
choices, some of them informed by public reporting, none of them a substitute
for it.

## 9. Noise

Real investigation records are never perfectly clean, so the generator
deliberately injects controlled imperfections into the entity tables after all
evidence is generated:

- **Aliases** — some persons get 1-2 alternate name spellings (initials,
  spacing removed, honorific added)
- **Phone-format variants** — every phone number is also recorded in 2-3
  alternate formats (bare digits, hyphenated, spaced)
- **Duplicate records** — a small fraction of persons get a near-identical
  duplicate record with a minor name variation, deliberately *not* wired into
  the relationship/evidence graph, to stress-test entity resolution
- **Missing fields** — occupation and organization address are sometimes
  blanked; FIRs sometimes omit the UTR number or suspected email
- **Innocent contacts** — a population of persons connected only through
  ordinary, non-criminal contact (see D1/D2 section above)

This noise is intentional and should not be "cleaned up" to make the dataset
look nicer — the eventual analysis system needs to work with evidence this
messy, and needs to be able to tell a genuine criminal relationship apart from
ordinary noise.

## 10. Ground truth

`GROUND_TRUTH/` (per case) contains the information that only exists because
this is a synthetic dataset with a planted answer key:

- `roles.json` — each person's `hidden_role` (ORGANIZER, MANAGER, AGENT, MULE,
  AGGREGATOR, CASHOUT_OPERATOR, VICTIM, INNOCENT_CONTACT, ...) and ring ID
- `communities.json` — which planted ring/community each person belongs to
- `relationships.json` — the actual planted D1/D2 edges (who was really
  connected to whom, and how)
- `fraud_events.json` — the fraud-event source of truth described above

This is **evaluation information** — it exists to score the eventual analysis
system's output, not to be given to it. `persons.csv` and `accounts.csv` never
contain `hidden_role`, `hidden_community_id`, or `hidden_mule_status` columns;
this isolation is checked by validation, not just assumed.

### Observable vs. hidden

```
OBSERVABLE (given to the analysis pipeline)      HIDDEN (evaluation only)
  FIR                                               ROLES
  CDR                                                PLANTED RELATIONSHIPS
  TRANSACTIONS                                       TOPOLOGY
  ENTITIES                                           GROUND_TRUTH/ (all of it)
  EVIDENCE_META
```

The future analysis system must never be given anything under `GROUND_TRUTH/`.

## 11. Data generation

Run from `synthetic_dataset/generator/`:

```bash
pip install -r ../../requirements.txt   # or: pip install faker
python3 generate_dataset.py --n-cases 10 --output-dir ./my_dataset --seed 42
```

CLI options: `--n-cases` (how many cases to generate), `--output-dir` (where to
write them), `--seed` (base random seed — each case gets a derived per-case seed,
and both Python's `random` and Faker are seeded consistently, so a given
`--seed` reproduces byte-identical output), `--year` (synthetic anchor year),
and `--validate` / `--no-validate` (validation runs automatically after
generation by default).

Standalone validation on an existing output directory:

```bash
python3 validation.py --output-dir ./my_dataset
```

The six demonstration tests (fraud-amount consistency, money flow, referential
integrity, NER accuracy, ground truth existence, topology) with concrete
printed evidence:

```bash
python3 demo_tests.py --output-dir ./my_dataset
```

Generated output directories are not committed to this repository (see
`.gitignore`) — regenerate as needed. A small, committed example lives at
[`synthetic_dataset/samples/CASE_CYB-2026-001/`](synthetic_dataset/samples/CASE_CYB-2026-001/)
for reference.

## 12. Validation

`validation.py` reads back the actually-written output files (not in-memory
generator state) and checks:

- **ENTITY_INTEGRITY** — unique IDs; every phone→person, account→person,
  vehicle→person foreign key resolves
- **CDR_INTEGRITY** — caller/receiver phones exist, durations positive,
  timestamps parse
- **FINANCIAL_INTEGRITY** — sender/receiver accounts exist, amounts positive,
  and every transaction is cross-checked against `fraud_events.json`'s
  expected hop amount
- **FIR_INTEGRITY** — every NER-referenced entity ID actually exists
- **NER_INTEGRITY** — for every span, `narrative_text[start:end]` matches the
  referenced entity's canonical value character-for-character
- **GROUND_TRUTH_INTEGRITY** — every role/community/relationship entity
  exists; roles come from the valid role set
- **GROUND_TRUTH_ISOLATION** — confirms the observable entity tables do not
  leak `hidden_role`/`hidden_community_id`/`hidden_mule_status`
- **TOPOLOGY** — confirms every required D1 and D2 planted-edge type is
  present in ground truth for every case, and every planted D2 TRANSACTED
  edge has a matching real transaction record

A validation run reports `Errors:` and `Warnings:` counts explicitly and does
not fail silently. Re-running the generator and validation in this repository
(10 cases, seed 42) reproduced the reference numbers exactly: 3,989 persons,
8,913 CDR records, 3,703 transactions, 921 FIRs, 0 errors, 0 warnings across
all eight checks. Reproducibility was independently re-confirmed here with two
separate `--seed 99` runs producing byte-identical output (`diff -rq`).

## 13. Limitations

This is a **synthetic** dataset. It is not real Indian police data, not NCRB
data, not I4C data, and no real person, phone number, bank account, FIR, or
case in it corresponds to an actual investigation. Some generation parameters
are informed by public reporting (see [Section 8](#8-synthetic-vs-source-backed-parameters))
but the dataset as a whole should never be presented or cited as an official
statistic or real case record. FIRs are plain `.txt`, not rendered PDFs. The
NCRP/1930 complaint-form field list used is a reasonable placeholder, not
independently verified against the official portal. Generation and validation
have only been exercised at the scale tested here (~10 cases, ~4,000 persons)
— no performance or memory profiling has been done at larger scale.

## 14. Future work

Not implemented in V1, and explicitly out of scope for this integration:

- **D4** (bridge/intermediary connecting two separate rings) and **D5**
  (interstate spread of a single ring) — each V1 case is still one
  self-contained ring
- The full analysis pipeline described in
  [`criminal-network-analysis-project.md`](criminal-network-analysis-project.md):
  graph construction (NetworkX), centrality/community detection (Louvain),
  anomaly/mule detection, the FastAPI backend, and the visualization dashboard
- A production-grade NER model trained on this dataset's labels (the
  generator's spans are ground truth by construction, not model output)
- Advanced entity resolution beyond the noise-resolvability this dataset is
  designed to test
