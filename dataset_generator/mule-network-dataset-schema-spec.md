# Mule Account Fraud Network — Synthetic Dataset Schema Specification

**Project:** AI-Powered Criminal Network Analysis System — narrowed domain
**Domain:** Money-mule / cyber-fraud layering networks (India)
**Status:** Phase A — schema finalization (precedes generator code)

---

## 1. Purpose and design principles

This document is the contract between the **synthetic data generator** (Phase B) and the **analysis engine** (already specified in the base architecture doc). Every field defined here exists because it is either:

- required by the analysis pipeline (centrality, community detection, path analysis, anomaly detection), or
- required to reproduce a structural pattern confirmed by a real source (RBI, I4C, AML industry research), or
- required by a dashboard feature already agreed on (case selector, key-player panel, path explainer, community view, fragmentation view)

No field exists "because it might be useful." Section 10 maps every non-obvious field back to the source that justified it.

**Ground truth vs. inferred fields** — every entity and relationship carries a `ground_truth` block (hidden from the analysis pipeline at inference time) and a `visible` block (what the pipeline can see). This split lets you score precision/recall on centrality, community detection, and anomaly detection against a known-correct answer key.

---

## 2. Entity schema

### 2.1 Person

```json
{
  "id": "P-0001",
  "type": "PERSON",
  "canonical_name": "string",
  "aliases": ["string"],
  "visible": {
    "stated_occupation": "student | homemaker | gig_worker | salaried | unemployed | retired | business_owner",
    "state": "string (Indian state, for geographic clustering)",
    "district_risk_tier": "high | medium | low"
  },
  "ground_truth": {
    "role": "victim | mule | mastermind | recruiter_operator | legitimate",
    "mule_type": "complicit | deceived | synthetic_kyc | null",
    "recruitment_channel": "whatsapp | telegram | instagram_bot | facebook_bot | in_person | null",
    "economic_profile_deviation_score": "float 0-1"
  },
  "source_docs": ["doc_id"]
}
```

`mule_type` is a three-way categorical, not binary "mule / not mule" — this directly reflects the complicit / deceived / synthetic-KYC split used in Indian AML practice, and each type needs a different behavioral signature in the generator (Section 4).

### 2.2 Account

```json
{
  "id": "A-0001",
  "type": "ACCOUNT",
  "linked_person_id": "P-000X",
  "visible": {
    "account_age_days": "int",
    "kyc_status": "verified | minimal | fake_or_stolen",
    "bank_tier": "public_sector | private | cooperative | payment_bank",
    "opened_via_bc": "boolean"
  },
  "ground_truth": {
    "mule_layer": "layer_1 | layer_2 | layer_3plus | null",
    "is_exit_node": "boolean"
  }
}
```

`opened_via_bc` (Business Correspondent channel) exists specifically to let you generate the synthetic-KYC motif, since BC-channel compromise is a documented distinct vulnerability, not a generic "fake account" flag.

### 2.3 Phone

```json
{
  "id": "PH-0001",
  "type": "PHONE",
  "linked_person_id": "P-000X",
  "visible": { "sim_registered_days": "int" }
}
```

### 2.4 Platform / recruiter node

```json
{
  "id": "ORG-0001",
  "type": "RECRUITER_PLATFORM",
  "visible": {
    "channel": "telegram_bot | instagram_bot | facebook_bot | whatsapp",
    "pretext": "job_offer | task_reward | investment_lead"
  }
}
```

Represents the documented bot-driven recruitment layer, not a person — this node feeds `RECRUITED_VIA` edges into mule nodes (Section 3.3) and is deliberately kept separate from the transaction subgraph.

### 2.5 Crypto exit node (optional, per motif)

```json
{
  "id": "EXIT-0001",
  "type": "CRYPTO_OFFRAMP",
  "visible": { "platform_type": "p2p_exchange | wallet_service" }
}
```

---

## 3. Relationship schema

### 3.1 Transaction (the core edge)

```json
{
  "source_id": "A-000X",
  "target_id": "A-000Y",
  "type": "TRANSACTION",
  "amount": "float (INR)",
  "timestamp": "ISO datetime",
  "channel": "upi | neft_imps | atm_withdrawal | crypto_convert",
  "computed_weight": "log(frequency) x exp(-lambda x days_since) x log(amount)"
}
```

### 3.2 Call / Communication

```json
{
  "source_id": "P-000X",
  "target_id": "P-000Y",
  "type": "CALL",
  "frequency": "int",
  "last_contact": "ISO datetime"
}
```

### 3.3 Recruited_via

```json
{
  "source_id": "ORG-000X",
  "target_id": "P-000Y",
  "type": "RECRUITED_VIA",
  "timestamp": "ISO datetime"
}
```

This is a distinct edge type from `TRANSACTION` on purpose — recruitment and money-flow are two separate documented crimes (recruitment fraud vs. layering), and keeping them as separate edge types lets the dashboard show a recruitment sub-graph without polluting the transaction-path explainer.

### 3.4 Shared_address / Shared_device (noise + genuine-link source)

```json
{
  "source_id": "P-000X",
  "target_id": "P-000Y",
  "type": "SHARED_ADDRESS | SHARED_DEVICE",
  "confidence": "float 0-1"
}
```

Deliberately generated both **inside** rings (genuine signal) and **across** unrelated rings/legitimate clusters (noise), to give community detection something realistic to filter against — this is what Section 6 of the base architecture doc means by "filtered against relationship-type density to reduce false positives from innocent social/family clusters."

---

## 4. Motif library (ring topologies)

Each motif is a reusable generator function, not a one-off template. Every generated case instantiates exactly one motif, parameterized by ring size and scam subtype.

| Motif | Structure | Timing signature | Source basis |
|---|---|---|---|
| **Fast pass-through** | Victim → mule → mule → exit (linear chain, no fan-out) | Full chain completes in 2-6 hours | Matches the documented near-zero-net-within-48-hours mule signature |
| **Fan-out / fan-in (layering)** | Victim → layer-1 mule → 2-4 layer-2 mules → converge on one hub/exit | Layer-1 to layer-2 within hours; layer-2 to exit within 1-2 days | Matches I4C's Layer 1 / Layer 2 terminology and the documented purpose of layering (defeat single-account thresholds) |
| **Dormant-then-burst** | Account sits inactive 30-90 days, then receives and disburses a large sum within hours | Long dormancy, sudden spike | Matches Indian Banks' Association's documented mule indicators: sudden spikes in account activity, high counterparty count |
| **Recruited fan-out with crypto offramp** | Recruiter platform → mule (recruitment edge) → transaction fan-out → crypto exit node | Recruitment precedes first transaction by days-to-weeks | Matches documented bot-driven recruitment pipelines and crypto-offramp usage by transnational syndicates |

**Ring sizing** — generate two size tiers per motif: a **small ring** (~15-40 accounts, modeled loosely on Jamtara's ~350-account/district-level density scaled down to single-ring size) and a **large ring** (~150-300 accounts, modeled on Nuh's ~1,000-account district scale, scaled to a single coordinated ring rather than a whole district). Document this scaling assumption explicitly in your pitch — you are not claiming these are literal ring sizes, only that they're anchored to real reported orders of magnitude rather than picked arbitrarily.

---

## 5. Ground-truth mule-type behavioral signatures

This is the section that actually drives realism — each `mule_type` needs a distinct, generatable pattern, not just a label:

| mule_type | Behavioral signature to generate |
|---|---|
| `complicit` | Transaction volume strongly disconnected from `stated_occupation` (e.g., student account moving lakhs); consistent, regular timing (suggests instruction-following); active receipt of multiple unrelated inbound sources |
| `deceived` | Fewer, larger transactions; account holder profile skews toward first-time banking users; a `RECRUITED_VIA` edge from a job-offer-pretext platform node almost always present |
| `synthetic_kyc` | `kyc_status = fake_or_stolen` or `opened_via_bc = true`; near-zero prior account history; often the **first** hop in a chain (closest to the mastermind), not the victim-facing hop |

---

## 6. Case / ring metadata

```json
{
  "case_id": "C-0001",
  "scam_subtype": "digital_arrest | investment_app | task_based | loan_app",
  "motif": "fast_pass_through | fan_out_fan_in | dormant_then_burst | recruited_crypto_exit",
  "ring_size_tier": "small_jamtara_scale | large_nuh_scale",
  "created_at": "ISO datetime",
  "last_updated": "ISO datetime",
  "node_count": "int",
  "total_amount_inr": "float"
}
```

Powers the case selector/dashboard feature directly — no additional derivation needed.

---

## 7. FIR / complaint text generation schema

Structured around I4C's own documented four-stage digital-arrest pattern, so NER training text mirrors real complaint structure rather than invented prose:

```json
{
  "doc_id": "FIR-0001",
  "case_id": "C-0001",
  "scam_subtype": "digital_arrest",
  "narrative_stages": {
    "impersonation": "string (which authority was impersonated: police | cbi | rbi | customs | narcotics | ed)",
    "intimidation": "string (fabricated accusation used)",
    "confinement": "string (video call / isolation tactic, if applicable)",
    "extortion": "string (amount demanded, payment framing: security_deposit | escrow | fine)"
  },
  "labeled_entities": [
    {"text": "string", "label": "PERSON | ACCOUNT | PHONE | AMOUNT | LOCATION | ORG", "start": "int", "end": "int"}
  ]
}
```

Non-digital-arrest subtypes (`investment_app`, `task_based`, `loan_app`) use a simpler two-to-three-stage structure (lure → escalating deposit → lockout) rather than forcing the four-stage frame where it doesn't apply.

---

## 8. Analysis output extensions

Two additions beyond the original architecture doc, needed to support the community-view and fragmentation-view dashboard features:

### 8.1 Community density summary (feature 6 support)

```json
{
  "community_id": "int",
  "internal_edge_density": "float",
  "external_edge_count": "int",
  "structure_label": "closed_cluster | bridging_cluster"
}
```

`structure_label` is assigned by a fixed rule (e.g., `internal_edge_density` above a threshold and `external_edge_count` below a threshold → `closed_cluster`), not by a model — consistent with the "no LLM in the analysis path" principle.

### 8.2 Structural fragmentation output (feature 7 support)

```json
{
  "removal_step": "int",
  "node_id": "string",
  "removal_rank_metric": "betweenness | degree",
  "largest_component_before": "int",
  "largest_component_after": "int",
  "component_count_after": "int"
}
```

Computed by iterative removal of top-k ranked nodes with `networkx.connected_components` recomputed after each step — a direct implementation of the key-player/network-robustness problem, no new data required beyond the existing graph.

---

## 9. Source-to-design traceability

| Design decision | Justified by |
|---|---|
| Three-way `mule_type` (complicit/deceived/synthetic_kyc) | AML industry analysis of Indian mule typologies |
| `mule_layer` field using Layer 1/2/3+ terminology | I4C Suspect Registry's own Layer 1 mule account terminology |
| Dormant-then-burst motif | Indian Banks' Association documented mule indicators (sudden activity spikes, high counterparty count) |
| Fast pass-through timing (near-zero net within 48h) | AML red-flag rule translating mule typology into a transaction-monitoring rule |
| Recruiter platform node + `RECRUITED_VIA` edge | I4C's documented bot-driven recruitment networks on Telegram/Instagram/Facebook |
| Four-stage FIR narrative structure | I4C's official 6 March 2025 advisory on digital arrest scam modus operandi |
| `opened_via_bc` field | CBI's 2025 finding on BC-channel-linked mule account vulnerabilities |
| Small/large ring size tiers | Reported Jamtara (~350 accounts) and Nuh (~1,000 accounts) district-level mule account counts |
| Crypto exit node | Documented use of P2P crypto platforms as the terminal layer by transnational syndicates |

---

## 10. What Phase B builds on top of this

Phase B (motif-generator code) implements Section 4's four motif functions as parameterized Python generators, Section 5's behavioral signatures as attribute-sampling logic per `mule_type`, and Section 7's FIR templates as a separate text-generation module feeding your NER training set. Phase C assembles many case instances plus Barabási–Albert background noise into one combined graph per the original architecture's Phase 2.
