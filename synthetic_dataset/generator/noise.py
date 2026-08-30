"""
noise.py

Concrete noise-injection functions per E.15: aliases, phone formatting variants,
duplicate records, missing fields. Applied as a post-processing pass over the
finished entity tables (E.0 step 9) - after all evidence generation, before export.
"""

import random

from config import GenerationConfig
from topology import CaseUniverse


def _alias_variants(name: str, rng: random.Random) -> list:
    parts = name.split()
    variants = []
    if len(parts) >= 2:
        # initials: "Raj Kumar" -> "R. Kumar"
        variants.append(f"{parts[0][0]}. {' '.join(parts[1:])}")
        # spacing removal: "Raj Kumar" -> "RajKumar"
        variants.append("".join(parts))
        # honorific add
        variants.append(f"Shri {name}")
    return variants


def inject_person_aliases(cfg: GenerationConfig, rng: random.Random,
                           universe: CaseUniverse):
    for person in universe.persons.values():
        if rng.random() < cfg.p_alias:
            pool = _alias_variants(person.canonical_name, rng)
            if pool:
                k = min(len(pool), rng.randint(1, 2))
                person.aliases = rng.sample(pool, k)


def _phone_format_variants(number: str) -> list:
    # number format: +91XXXXXXXXXX
    digits = number.replace("+91", "")
    return [
        digits,                                    # 9876543210
        f"+91-{digits}",                            # +91-9876543210
        f"+91 {digits[:5]} {digits[5:]}",           # +91 98765 43210
    ]


def inject_phone_format_variants(universe: CaseUniverse):
    for phone in universe.phones.values():
        phone.format_variants = _phone_format_variants(phone.number)


def inject_duplicate_persons(id_factory, cfg: GenerationConfig, rng: random.Random,
                              universe: CaseUniverse):
    """
    With probability p_dup per person, insert a near-identical duplicate record
    (simulating imperfect record-keeping across source documents). Duplicates are
    NOT wired into the relationship/evidence graph - they exist purely to stress-test
    entity resolution during evaluation.
    """
    from entities import PersonRecord
    duplicates = []
    for person in list(universe.persons.values()):
        if rng.random() < cfg.p_dup:
            dup_name = person.canonical_name
            # near-identical, not identical: minor typo or spacing change
            if rng.random() < 0.5 and " " in dup_name:
                dup_name = dup_name.replace(" ", "", 1)
            dup = PersonRecord(
                id_factory.next("person"), dup_name, person.gender, person.age,
                person.occupation, person.state, person.district, person.address)
            dup.hidden_role = person.hidden_role
            dup.hidden_community_id = person.hidden_community_id
            duplicates.append(dup)
    for d in duplicates:
        universe.persons[d.person_id] = d


def inject_missing_fields(cfg: GenerationConfig, rng: random.Random,
                           universe: CaseUniverse):
    for person in universe.persons.values():
        if rng.random() < cfg.p_missing:
            person.occupation = None
    for org in universe.organizations.values():
        if rng.random() < cfg.p_missing:
            org.registered_address = None


def apply_all_noise(id_factory, cfg: GenerationConfig, rng: random.Random,
                     universe: CaseUniverse):
    inject_person_aliases(cfg, rng, universe)
    inject_phone_format_variants(universe)
    inject_duplicate_persons(id_factory, cfg, rng, universe)
    inject_missing_fields(cfg, rng, universe)
