"""
Entity factory functions: Person, Account, Phone, Recruiter platform,
Crypto exit node. Matches schema spec Section 2.

Every entity gets a globally unique ID via the counters below, since
Phase C combines many independently-generated cases into one graph and
IDs must not collide across cases.

Every factory takes an explicit `rng: random.Random` parameter and draws
only from it - no bare `random.*` calls - so a caller's choice of rng
(e.g. entity_attribute_rng for case entities, noise_rng for background
entities) fully determines and isolates this function's randomness.
"""

import itertools

from config import OCCUPATIONS, BANK_TIERS, INDIAN_STATES_HIGH_RISK, RECRUITMENT_CHANNELS

_person_counter = itertools.count(1)
_account_counter = itertools.count(1)
_phone_counter = itertools.count(1)
_org_counter = itertools.count(1)
_exit_counter = itertools.count(1)

FIRST_NAMES = [
    "Amit", "Priya", "Ravi", "Sunita", "Vijay", "Anjali", "Rahul", "Pooja",
    "Suresh", "Kavita", "Manoj", "Deepa", "Arjun", "Neha", "Sanjay", "Rekha",
]
LAST_NAMES = [
    "Sharma", "Verma", "Patel", "Reddy", "Singh", "Kumar", "Gupta", "Nair",
    "Iyer", "Das", "Mehta", "Joshi", "Rao", "Chauhan", "Yadav", "Pillai",
]


def _random_name(rng):
    return f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"


def make_person(rng, role, mule_type=None, recruitment_channel=None):
    """role: victim | mule | mastermind | recruiter_operator | legitimate"""
    pid = f"P-{next(_person_counter):05d}"
    is_complicit = mule_type == "complicit"
    return {
        "id": pid,
        "type": "PERSON",
        "canonical_name": _random_name(rng),
        "aliases": [],
        "visible": {
            "stated_occupation": rng.choice(OCCUPATIONS),
            "state": rng.choice(INDIAN_STATES_HIGH_RISK),
            "district_risk_tier": rng.choice(["high", "medium", "low"]),
        },
        "ground_truth": {
            "role": role,
            "mule_type": mule_type,
            "recruitment_channel": recruitment_channel,
            # complicit mules show a bigger deviation between profile and
            # transaction behaviour than deceived/synthetic ones (schema Sec. 5)
            "economic_profile_deviation_score": round(rng.uniform(0.4, 0.95), 2)
            if is_complicit else round(rng.uniform(0.0, 0.3), 2),
        },
        "source_docs": [],
    }


def make_account(rng, person_id, mule_layer=None, is_exit_node=False, opened_via_bc=False,
                  kyc_status="verified", account_age_days=None):
    aid = f"A-{next(_account_counter):05d}"
    if account_age_days is None:
        # mule accounts skew new; legitimate accounts skew old
        account_age_days = rng.randint(5, 30) if mule_layer else rng.randint(180, 2000)
    return {
        "id": aid,
        "type": "ACCOUNT",
        "linked_person_id": person_id,
        "visible": {
            "account_age_days": account_age_days,
            "kyc_status": kyc_status,
            "bank_tier": rng.choice(BANK_TIERS),
            "opened_via_bc": opened_via_bc,
        },
        "ground_truth": {
            "mule_layer": mule_layer,
            "is_exit_node": is_exit_node,
        },
    }


def make_phone(rng, person_id):
    # Plain 10-digit Indian mobile format, no +91 prefix or separators:
    # first digit in {6,7,8,9} (the valid leading digits), the rest
    # uniform. Not enforced globally unique - with 4*10**9 possible values
    # against a dataset of a few hundred phones, collision odds are
    # negligible, and the spec only calls for plausible-unique, not
    # guaranteed-unique.
    phone_number = rng.choice("6789") + "".join(str(rng.randint(0, 9)) for _ in range(9))
    return {
        "id": f"PH-{next(_phone_counter):05d}",
        "type": "PHONE",
        "linked_person_id": person_id,
        # phone_number lives under "visible" (not top-level, alongside id)
        # because it is exactly the kind of fact an investigation would
        # actually observe (it's what appears in the FIR text) - consistent
        # with every other entity's visible/ground_truth split in this file.
        "visible": {"sim_registered_days": rng.randint(1, 3000), "phone_number": phone_number},
    }


def make_recruiter_platform(rng, channel=None):
    return {
        "id": f"ORG-{next(_org_counter):05d}",
        "type": "RECRUITER_PLATFORM",
        "visible": {
            "channel": channel or rng.choice(RECRUITMENT_CHANNELS),
            "pretext": rng.choice(["job_offer", "task_reward", "investment_lead"]),
        },
    }


def make_crypto_exit(rng):
    return {
        "id": f"EXIT-{next(_exit_counter):05d}",
        "type": "CRYPTO_OFFRAMP",
        "visible": {"platform_type": rng.choice(["p2p_exchange", "wallet_service"])},
    }
