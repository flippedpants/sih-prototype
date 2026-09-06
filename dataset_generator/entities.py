"""
Entity factory functions: Person, Account, Phone, Recruiter platform,
Crypto exit node. Matches schema spec Section 2.

Every entity gets a globally unique ID via the counters below, since
Phase C combines many independently-generated cases into one graph and
IDs must not collide across cases.
"""

import itertools
import random

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


def _random_name():
    return f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"


def make_person(role, mule_type=None, recruitment_channel=None):
    """role: victim | mule | mastermind | recruiter_operator | legitimate"""
    pid = f"P-{next(_person_counter):05d}"
    is_complicit = mule_type == "complicit"
    return {
        "id": pid,
        "type": "PERSON",
        "canonical_name": _random_name(),
        "aliases": [],
        "visible": {
            "stated_occupation": random.choice(OCCUPATIONS),
            "state": random.choice(INDIAN_STATES_HIGH_RISK),
            "district_risk_tier": random.choice(["high", "medium", "low"]),
        },
        "ground_truth": {
            "role": role,
            "mule_type": mule_type,
            "recruitment_channel": recruitment_channel,
            # complicit mules show a bigger deviation between profile and
            # transaction behaviour than deceived/synthetic ones (schema Sec. 5)
            "economic_profile_deviation_score": round(random.uniform(0.4, 0.95), 2)
            if is_complicit else round(random.uniform(0.0, 0.3), 2),
        },
        "source_docs": [],
    }


def make_account(person_id, mule_layer=None, is_exit_node=False, opened_via_bc=False,
                  kyc_status="verified", account_age_days=None):
    aid = f"A-{next(_account_counter):05d}"
    if account_age_days is None:
        # mule accounts skew new; legitimate accounts skew old
        account_age_days = random.randint(5, 30) if mule_layer else random.randint(180, 2000)
    return {
        "id": aid,
        "type": "ACCOUNT",
        "linked_person_id": person_id,
        "visible": {
            "account_age_days": account_age_days,
            "kyc_status": kyc_status,
            "bank_tier": random.choice(BANK_TIERS),
            "opened_via_bc": opened_via_bc,
        },
        "ground_truth": {
            "mule_layer": mule_layer,
            "is_exit_node": is_exit_node,
        },
    }


def make_phone(person_id):
    return {
        "id": f"PH-{next(_phone_counter):05d}",
        "type": "PHONE",
        "linked_person_id": person_id,
        "visible": {"sim_registered_days": random.randint(1, 3000)},
    }


def make_recruiter_platform(channel=None):
    return {
        "id": f"ORG-{next(_org_counter):05d}",
        "type": "RECRUITER_PLATFORM",
        "visible": {
            "channel": channel or random.choice(RECRUITMENT_CHANNELS),
            "pretext": random.choice(["job_offer", "task_reward", "investment_lead"]),
        },
    }


def make_crypto_exit():
    return {
        "id": f"EXIT-{next(_exit_counter):05d}",
        "type": "CRYPTO_OFFRAMP",
        "visible": {"platform_type": random.choice(["p2p_exchange", "wallet_service"])},
    }
