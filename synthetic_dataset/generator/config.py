"""
config.py

Every tunable generation parameter from Part E, Section E.16 (final consolidated
parameter table), in one place. Nothing in the rest of the codebase should hardcode
a magic number that belongs here.

Each parameter is commented with its Status tag from the specification:
  FACT        - source-backed
  ASSUMPTION  - source-informed but not a confirmed national statistic
  RULE        - a deliberate synthetic-design choice, no claim to real-world accuracy

See: indian_criminal_network_dataset_specification_part_E_v2_FINAL.md
"""

from dataclasses import dataclass, field


# ---------------------------------------------------------------------------
# Geography (Part A.3 / NCRB taxonomy - FACT for the list itself)
# ---------------------------------------------------------------------------

INDIAN_STATES = [
    "Maharashtra", "Uttar Pradesh", "Karnataka", "Tamil Nadu", "Telangana",
    "Delhi", "Gujarat", "Rajasthan", "West Bengal", "Haryana",
    "Madhya Pradesh", "Bihar", "Punjab", "Odisha", "Kerala",
    "Jharkhand", "Assam", "Uttarakhand",
]

# A few representative districts per state, enough for synthetic variety.
# (RULE - a small curated subset, not the full NCRB district list, sufficient
# for a hackathon-scale synthetic dataset.)
STATE_DISTRICTS = {
    "Maharashtra": ["Mumbai", "Pune", "Thane", "Nagpur", "Nashik"],
    "Uttar Pradesh": ["Lucknow", "Noida", "Ghaziabad", "Kanpur", "Varanasi"],
    "Karnataka": ["Bengaluru Urban", "Mysuru", "Mangaluru", "Belagavi"],
    "Tamil Nadu": ["Chennai", "Coimbatore", "Madurai", "Salem"],
    "Telangana": ["Hyderabad", "Rangareddy", "Warangal"],
    "Delhi": ["New Delhi", "South Delhi", "North Delhi", "West Delhi"],
    "Gujarat": ["Ahmedabad", "Surat", "Vadodara", "Rajkot"],
    "Rajasthan": ["Jaipur", "Jodhpur", "Udaipur"],
    "West Bengal": ["Kolkata", "Howrah", "Siliguri"],
    "Haryana": ["Gurugram", "Faridabad", "Panipat"],
    "Madhya Pradesh": ["Bhopal", "Indore", "Gwalior"],
    "Bihar": ["Patna", "Gaya", "Bhagalpur"],
    "Punjab": ["Ludhiana", "Amritsar", "Jalandhar"],
    "Odisha": ["Bhubaneswar", "Cuttack", "Rourkela"],
    "Kerala": ["Ernakulam", "Thiruvananthapuram", "Kozhikode"],
    "Jharkhand": ["Ranchi", "Jamtara", "Dhanbad"],
    "Assam": ["Guwahati", "Dibrugarh"],
    "Uttarakhand": ["Dehradun", "Haldwani", "Nainital"],
}

VEHICLE_STATE_CODES = {
    "Maharashtra": "MH", "Uttar Pradesh": "UP", "Karnataka": "KA",
    "Tamil Nadu": "TN", "Telangana": "TG", "Delhi": "DL", "Gujarat": "GJ",
    "Rajasthan": "RJ", "West Bengal": "WB", "Haryana": "HR",
    "Madhya Pradesh": "MP", "Bihar": "BR", "Punjab": "PB", "Odisha": "OD",
    "Kerala": "KL", "Jharkhand": "JH", "Assam": "AS", "Uttarakhand": "UK",
}


# ---------------------------------------------------------------------------
# Roles (Part C)
# ---------------------------------------------------------------------------

CRIMINAL_ROLES = [
    "ORGANIZER", "MANAGER", "AGENT", "RECRUITER", "MULE",
    "INTERMEDIARY", "AGGREGATOR", "CASHOUT_OPERATOR",
]
NON_CRIMINAL_ROLES = ["VICTIM", "INNOCENT_CONTACT"]
ALL_ROLES = CRIMINAL_ROLES + NON_CRIMINAL_ROLES


@dataclass
class GenerationConfig:
    # -- Case-level (E.2) ---------------------------------------------------
    case_type_weights: dict = field(default_factory=lambda: {
        "call_centre_phishing": 0.5,          # RULE - unconfirmed split (Part A.1)
        "fake_investment_app": 0.5,           # RULE
    })
    case_status_weights: dict = field(default_factory=lambda: {
        "open": 0.40, "under_investigation": 0.45, "closed": 0.15,  # RULE
    })

    # -- EVIDENCE_FILE (E.3) -------------------------------------------------
    classification_confidence_buckets: dict = field(default_factory=lambda: {
        "high": (0.90, 0.99, 0.85),   # (min, max, probability)  RULE - UX placeholder
        "medium": (0.60, 0.89, 0.12),
        "low": (0.30, 0.59, 0.03),
    })
    investigator_override_correct_rate = 0.95   # RULE

    # -- PERSON age bands (E.4, revised) -------------------------------------
    # SOURCE-INFORMED ASSUMPTION - see verification note in Part E v2.
    age_bands = [(18, 30), (30, 45), (45, 60), (60, 75)]
    age_band_weights_offender = [0.45, 0.40, 0.12, 0.03]
    age_band_weights_civilian = [0.20, 0.30, 0.30, 0.20]  # victim / innocent_contact

    # -- PERSON gender (E.4, revised) ----------------------------------------
    gender_split_offender = {"male": 0.90, "female": 0.10}   # SOURCE-INFORMED ASSUMPTION (softened)
    gender_split_civilian = {"male": 0.50, "female": 0.50}   # SYNTHETIC DESIGN CHOICE

    # -- Topology D1 (hierarchical) sizing (Part D) --------------------------
    n_managers = (1, 2)          # RULE, inclusive range
    n_agents = (3, 6)            # RULE
    n_victims_per_agent = (10, 30)  # RULE

    # -- CDR / call patterns (E.10) -------------------------------------------
    agent_victim_call_burst = (1, 3)              # calls, RULE
    agent_victim_call_window_minutes = 10          # RULE
    agent_victim_call_duration_sec = (30, 600)      # RULE
    manager_agent_call_interval_days_lambda = 1.0   # Poisson lambda, RULE
    manager_agent_call_duration_sec = (60, 300)     # RULE
    organizer_manager_call_interval_days = (3, 7)   # RULE
    organizer_manager_call_duration_sec = (120, 900) # RULE
    recruiter_mule_onboarding_calls = (1, 3)         # RULE, then silence

    # -- Topology D2 (mule chain) sizing --------------------------------------
    mule_chain_length = (2, 4)                # RULE, loosely anchored to real "5-10 accounts" reporting
    mule_hop_minutes = (2, 45)                # SOURCE-INFORMED (real "minutes apart" pattern)

    # -- Victim loss amount (E.11, revised) -----------------------------------
    # SOURCE-INFORMED ASSUMPTION + SYNTHETIC DESIGN CHOICE.
    # Log-normal calibrated so mean falls in the verified ₹66K-₹1.19L/complaint
    # range found in 2023-2025 I4C data. Using ₹90,000 as the default anchor mean.
    victim_loss_lognormal_mean_inr = 90_000
    victim_loss_lognormal_sigma = 1.1          # controls tail heaviness
    victim_loss_high_value_floor_inr = 5_000_000   # 50 lakh+ tail threshold
    victim_loss_high_value_probability = 0.03       # RULE
    victim_loss_crore_probability = 0.015           # 1-2% of cases, RULE

    # -- Mule commission (E.11, revised) ---------------------------------------
    # SOURCE-INFORMED (anchored to a real verified 4% case) + SYNTHETIC DESIGN CHOICE
    commission_first_hop = (0.01, 0.05, 0.03)     # (min, max, default)
    commission_later_hop = (0.01, 0.05, 0.02)
    commission_aggregator = (0.01, 0.03, 0.02)
    commission_high_tail = (0.05, 0.10)
    commission_high_tail_probability = 0.10        # RULE

    # -- RELATIONSHIP weight formula (E.13) -------------------------------------
    recency_decay_lambda = 0.05     # per day, RULE
    mentioned_in_fir_weight = 0.1   # RULE

    # -- Noise injection (E.15) ---------------------------------------------
    p_alias = 0.30           # RULE
    p_dup = 0.03              # RULE
    p_missing = 0.05          # RULE
    p_phone_variant = 1.0     # applied to every mentioned phone, RULE

    # -- FIR / evidence field missingness (E.12, revised) ------------------
    p_utr_missing = 0.15       # MODELING ASSUMPTION
    p_email_missing = 0.60     # MODELING ASSUMPTION - many scams have no email
    p_vehicle_generated = 0.12  # only for a subset of persons, RULE

    # -- Innocent-contact population (Part C / D3) ---------------------------
    n_innocent_contacts_per_case = (5, 15)   # RULE

    # -- Reproducibility ------------------------------------------------------
    default_seed = 42


DEFAULT_CONFIG = GenerationConfig()
