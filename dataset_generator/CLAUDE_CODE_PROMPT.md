# Prompt for Claude Code — Phase B + C: mule-network synthetic dataset generator

Copy everything below this line into Claude Code as your task prompt. Before running it, put these three files in your project folder — Claude Code should read them first, not recreate them:

- `mule-network-dataset-schema-spec.md` (the full schema — authoritative reference for every field name and structure)
- `config.py` (already written and tested — all tunable parameters)
- `entities.py` (already written and tested — Person/Account/Phone/Recruiter/CryptoExit factory functions)

---

## Task prompt (copy from here)

I'm building a synthetic dataset generator for a criminal-network-analysis hackathon project (India-focused mule-account/cyber-fraud layering networks). No real case-level dataset exists publicly, so this generator produces realistic synthetic fraud rings anchored to real reported patterns (RBI/I4C typologies, AML industry research) rather than arbitrary randomness.

**Read `mule-network-dataset-schema-spec.md` first** — it is the authoritative spec. Every field name, entity type, and edge type you use must match it exactly. `config.py` and `entities.py` already exist and are tested — read them, use their functions, do not rewrite them unless you find an actual bug (explain it if so).

### What to build

**1. `motifs.py`** — four functions, one per motif defined in schema Section 4. Each function signature should be `generate_<motif_name>(case_id: str, scam_subtype: str, size_tier: str) -> dict`, returning:
```python
{
  "nodes": [...],       # list of entity dicts from entities.py factories
  "edges": [...],       # list of relationship dicts per schema Section 3
  "case_metadata": {...} # per schema Section 6
}
```

- `generate_fast_pass_through` — linear chain: victim → mule → mule → exit, no fan-out. Use `MOTIF_TIMING_HOURS["fast_pass_through"]` from config for hop timing.
- `generate_fan_out_fan_in` — victim → layer-1 mule → 2-4 layer-2 mules → converge on one hub. Layer-1→layer-2 timing should be faster than layer-2→hub, both within `MOTIF_TIMING_HOURS["fan_out_fan_in"]`.
- `generate_dormant_then_burst` — an account with `account_age_days` and no transaction history for `DORMANCY_DAYS_RANGE` days, then a sudden fan-out burst within `MOTIF_TIMING_HOURS["dormant_then_burst"]`.
- `generate_recruited_crypto_exit` — include a `RECRUITER_PLATFORM` node with a `RECRUITED_VIA` edge into the entry-layer mule, then fan-out/fan-in structure terminating at a `CRYPTO_OFFRAMP` node (`is_exit_node=True` on the linked account).

**Every motif must:**
- Use `entities.py` factory functions for all nodes (never construct entity dicts by hand)
- Sample `mule_type` per `MULE_TYPE_WEIGHTS` from config for every mule person, and pass it into `make_person()` so the ground-truth deviation-score logic applies correctly
- Sample ring size from `RING_SIZE_TIERS[size_tier]` and scam amount from `SCAM_SUBTYPES[scam_subtype]["amount_range"]`
- Give every `TRANSACTION` edge a `computed_weight` using the formula in schema Section 3.1: `log(frequency) * exp(-lambda * days_since) * log(amount)` — pick a reasonable `lambda` constant and document it as an ASSUMPTION comment, consistent with the style in `config.py`
- Set `TRANSACTION.channel` to a plausible value (`upi`, `neft_imps`, `atm_withdrawal`, `crypto_convert` — use `crypto_convert` for the final hop into a `CRYPTO_OFFRAMP` node)

**2. `noise.py`** — background "legitimate" traffic so the fraud rings aren't sitting in isolation:
- A Barabási–Albert-generated set of ordinary Person+Account nodes with regular, unremarkable transaction patterns (no suspicious timing, no layering)
- A function that injects a small, configurable number of cross-cluster `SHARED_ADDRESS` / `SHARED_DEVICE` edges connecting some noise nodes to ring nodes — this is the deliberate false-positive risk described in schema Section 3.4, needed so community detection has something realistic to filter against
- Keep noise volume configurable (e.g. `generate_noise(num_nodes: int, num_cross_links: int)`)

**3. `assemble.py`** — the Phase C driver, run as a script:
- Loop generating `N` cases (make `N` a CLI arg or constant at the top, default something like 40), each time randomly picking a motif, `scam_subtype`, and `size_tier`
- Call the matching `motifs.py` function, merge its nodes/edges into one combined dataset
- Generate and merge the noise graph from `noise.py`
- Serialize the result to `output/`:
  - `output/graph_nodes.json`
  - `output/graph_edges.json`
  - `output/case_metadata.json`
- At the end, print a summary report to stdout: total node count, total edge count, case count broken down by motif and by scam_subtype, and size-tier distribution

### Testing / acceptance criteria

- `python assemble.py` must run end-to-end with no errors and produce all three output files
- Add a small number of sanity-check assertions inside `assemble.py` after generation (not a separate test framework — keep it simple): every mule-role account has a non-null `mule_layer` or `is_exit_node=True`; every `case_metadata` entry's declared `node_count` matches the actual nodes generated for that `case_id`; no duplicate entity IDs across the whole combined dataset
- Print a short PASS/FAIL line for each sanity check

### Constraints

- Standard library + `networkx` only (`pip install networkx` if not present) — no other new dependencies without asking
- Keep every field name identical to the schema spec — this dataset gets consumed by an analysis pipeline later that expects exact field names
- Don't implement Phase D (FIR text generation) or Phase F (analysis engine) — out of scope for this task
- Add a short docstring to every function explaining what motif/behavior it implements

## End of prompt
