"""
Configuration and tunable parameters for the mule-account fraud
network synthetic data generator.

Every range/value here is either:
  - SOURCED: anchored to a real reported figure (noted inline)
  - ASSUMPTION: illustrative, chosen for internal consistency, not claimed
    as ground truth
"""

# ---------------------------------------------------------------------------
# Ring size tiers
# SOURCED: Jamtara (~350 mule accounts) and Nuh (~1,000 mule accounts) are
# real district-level totals, not single-ring sizes. We scale them down to
# plausible single-ring counts while preserving the relative size gap.
# ---------------------------------------------------------------------------
RING_SIZE_TIERS = {
    "small_jamtara_scale": (15, 40),
    "large_nuh_scale": (60, 150),
}

# ---------------------------------------------------------------------------
# Scam subtypes and their typical extraction amount ranges (INR)
# ASSUMPTION: bands are illustrative, loosely bounded by RBI/I4C aggregate
# figures, not case-level ground truth.
# ---------------------------------------------------------------------------
SCAM_SUBTYPES = {
    "digital_arrest": {"amount_range": (50_000, 2_500_000)},
    "investment_app": {"amount_range": (20_000, 5_000_000)},
    "task_based": {"amount_range": (500, 50_000)},
    "loan_app": {"amount_range": (2_000, 100_000)},
}

# ---------------------------------------------------------------------------
# Motif timing windows (hours between hops)
# SOURCED: fast_pass_through window is grounded in the documented AML
# red-flag rule (funds net near-zero within 48 hours). Others are
# ASSUMPTION, kept internally consistent with that anchor.
# ---------------------------------------------------------------------------
MOTIF_TIMING_HOURS = {
    "fast_pass_through": (0.5, 6),
    "fan_out_fan_in": (2, 48),
    "dormant_then_burst": (1, 12),       # burst phase only
    "recruited_crypto_exit": (6, 72),
}

# SOURCED: dormant-then-spike pattern is a documented Indian Banks'
# Association mule indicator.
DORMANCY_DAYS_RANGE = (30, 90)

# ---------------------------------------------------------------------------
# Mule type distribution (rough priors — tune freely)
# ---------------------------------------------------------------------------
MULE_TYPE_WEIGHTS = {
    "complicit": 0.35,
    "deceived": 0.45,
    "synthetic_kyc": 0.20,
}

RECRUITMENT_CHANNELS = ["whatsapp", "telegram", "instagram_bot", "facebook_bot", "in_person"]

# SOURCED: states/districts flagged as high-risk by I4C reporting
INDIAN_STATES_HIGH_RISK = [
    "Haryana", "Jharkhand", "Uttar Pradesh", "Rajasthan", "Bihar",
    "Karnataka", "Maharashtra", "Delhi", "Madhya Pradesh", "Tamil Nadu",
]

OCCUPATIONS = ["student", "homemaker", "gig_worker", "salaried", "unemployed", "retired", "business_owner"]

BANK_TIERS = ["public_sector", "private", "cooperative", "payment_bank"]

# Default seed for reproducible runs. Actual seeding happens once, in
# assemble.py's main(), via `--seed` (this is just the documented default) -
# nothing in this module seeds `random` itself, since doing so as an
# import-time side effect would silently override whatever seed a caller
# asked for.
RANDOM_SEED = 42
