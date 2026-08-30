"""
entities.py

Generators for the base entity tables: PERSON, ORGANIZATION, PHONE, BANK_ACCOUNT,
VEHICLE, LOCATION. These produce skeleton records with hidden_role/hidden_community_id
set by the topology builder (topology.py) - not generated independently here, per
E.0 step 3.
"""

import random
from faker import Faker

from config import (
    GenerationConfig, INDIAN_STATES, STATE_DISTRICTS, VEHICLE_STATE_CODES,
)

fake = Faker("en_IN")


def seed_faker(seed: int):
    """
    V1.1 FIX: Faker keeps its own internal random state, entirely separate from
    Python's random module. Seeding random.Random(case_seed) (done everywhere
    else in this codebase) had NO effect on Faker's name/address generation -
    meaning every run with the same --seed still produced different names and
    addresses. This call must happen once per case, before any entity
    generation, using the same case_seed as the case's random.Random instance.
    """
    fake.seed_instance(seed)


def sample_age(cfg: GenerationConfig, is_offender: bool, rng: random.Random) -> int:
    """E.4 (revised): age band sampling, then uniform within the chosen band."""
    weights = cfg.age_band_weights_offender if is_offender else cfg.age_band_weights_civilian
    band = rng.choices(cfg.age_bands, weights=weights, k=1)[0]
    return rng.randint(band[0], band[1] - 1)


def sample_gender(cfg: GenerationConfig, is_offender: bool, rng: random.Random) -> str:
    """E.4 (revised): softened, explicitly-labeled placeholder split."""
    dist = cfg.gender_split_offender if is_offender else cfg.gender_split_civilian
    return rng.choices(list(dist.keys()), weights=list(dist.values()), k=1)[0]


def make_name(gender: str) -> str:
    if gender == "male":
        return fake.name_male()
    return fake.name_female()


def pick_state_district(rng: random.Random, preferred_state: str = None):
    state = preferred_state or rng.choice(INDIAN_STATES)
    district = rng.choice(STATE_DISTRICTS[state])
    return state, district


class PersonRecord:
    __slots__ = (
        "person_id", "canonical_name", "gender", "age", "occupation",
        "state", "district", "address", "aliases", "source_docs",
        "hidden_role", "hidden_community_id",
    )

    def __init__(self, person_id, canonical_name, gender, age, occupation,
                 state, district, address):
        self.person_id = person_id
        self.canonical_name = canonical_name
        self.gender = gender
        self.age = age
        self.occupation = occupation
        self.state = state
        self.district = district
        self.address = address
        self.aliases = []          # populated by noise.py
        self.source_docs = []      # populated during FIR/CDR/TXN generation
        self.hidden_role = None    # set by topology.py
        self.hidden_community_id = None

    def to_row(self):
        return {
            "person_id": self.person_id,
            "canonical_name": self.canonical_name,
            "aliases": ";".join(self.aliases),
            "gender": self.gender,
            "age": self.age,
            "occupation": self.occupation,
            "state": self.state,
            "district": self.district,
            "address": self.address,
            "source_docs": ";".join(self.source_docs),
        }


_OFFENDER_OCCUPATIONS = [
    "Unemployed", "Call Centre Executive", "Sales Executive", "Freelancer",
    "Data Entry Operator", "Shop Assistant",
]
_CIVILIAN_OCCUPATIONS = [
    "Software Engineer", "Teacher", "Government Employee", "Homemaker",
    "Shop Owner", "Farmer", "Retired", "Accountant", "Doctor", "Driver",
    "Bank Employee", "Student",
]


def generate_person(id_factory, cfg: GenerationConfig, rng: random.Random,
                     is_offender: bool, preferred_state: str = None) -> PersonRecord:
    gender = sample_gender(cfg, is_offender, rng)
    age = sample_age(cfg, is_offender, rng)
    name = make_name(gender)
    state, district = pick_state_district(rng, preferred_state)
    occupation = rng.choice(_OFFENDER_OCCUPATIONS if is_offender else _CIVILIAN_OCCUPATIONS)
    address = fake.address().replace("\n", ", ")
    pid = id_factory.next("person")
    return PersonRecord(pid, name, gender, age, occupation, state, district, address)


class OrganizationRecord:
    __slots__ = ("org_id", "name", "org_type", "state", "district",
                 "registered_address", "hidden_role")

    def __init__(self, org_id, name, org_type, state, district, registered_address):
        self.org_id = org_id
        self.name = name
        self.org_type = org_type
        self.state = state
        self.district = district
        self.registered_address = registered_address
        self.hidden_role = None

    def to_row(self):
        return {
            "org_id": self.org_id, "name": self.name, "org_type": self.org_type,
            "state": self.state, "district": self.district,
            "registered_address": self.registered_address,
        }


_ORG_NAME_COMPONENTS = ["Sundar", "Alpha", "Om", "Shree", "Global", "Metro",
                         "Prime", "Sunrise", "National", "United"]
_ORG_SUFFIXES = ["Enterprises", "Traders", "Ventures", "Solutions",
                  "Financial Services", "Infotech", "Holdings"]


def generate_organization(id_factory, rng: random.Random, case_type: str,
                           preferred_state: str = None) -> OrganizationRecord:
    if case_type == "call_centre_phishing":
        weights = {"call_centre": 0.6, "shell_company": 0.3, "front_business": 0.1}
    else:
        weights = {"shell_company": 0.5, "front_business": 0.4, "call_centre": 0.1}
    org_type = rng.choices(list(weights.keys()), weights=list(weights.values()), k=1)[0]
    name = f"{rng.choice(_ORG_NAME_COMPONENTS)} {rng.choice(_ORG_SUFFIXES)}"
    state, district = pick_state_district(rng, preferred_state)
    address = fake.address().replace("\n", ", ")
    return OrganizationRecord(id_factory.next("organization"), name, org_type,
                               state, district, address)


class PhoneRecord:
    __slots__ = ("phone_id", "number", "format_variants", "registered_person_id",
                 "sim_status", "carrier")

    def __init__(self, phone_id, number, registered_person_id, sim_status, carrier):
        self.phone_id = phone_id
        self.number = number
        self.format_variants = []   # populated by noise.py
        self.registered_person_id = registered_person_id
        self.sim_status = sim_status
        self.carrier = carrier

    def to_row(self):
        return {
            "phone_id": self.phone_id, "number": self.number,
            "format_variants": ";".join(self.format_variants),
            "registered_person_id": self.registered_person_id or "",
            "sim_status": self.sim_status, "carrier": self.carrier,
        }


_CARRIERS = ["Airtel", "Jio", "Vi", "BSNL"]


def generate_phone(id_factory, rng: random.Random, is_operational_burner: bool,
                    registered_person_id: str = None) -> PhoneRecord:
    first_digit = rng.choice("6789")
    rest = "".join(rng.choice("0123456789") for _ in range(9))
    number = f"+91{first_digit}{rest}"
    if is_operational_burner:
        sim_status = rng.choices(["suspected_fake", "prepaid_unregistered"],
                                  weights=[0.7, 0.3], k=1)[0]
        registered_person_id = None
    else:
        sim_status = "active"
    carrier = rng.choice(_CARRIERS)
    return PhoneRecord(id_factory.next("phone"), number, registered_person_id,
                        sim_status, carrier)


class BankAccountRecord:
    __slots__ = ("account_id", "synthetic_account_number", "bank_name",
                 "account_holder_person_id", "branch", "state", "account_type",
                 "hidden_mule_status")

    def __init__(self, account_id, account_number, bank_name, holder_id,
                 branch, state, account_type):
        self.account_id = account_id
        self.synthetic_account_number = account_number
        self.bank_name = bank_name
        self.account_holder_person_id = holder_id
        self.branch = branch
        self.state = state
        self.account_type = account_type
        self.hidden_mule_status = False

    def to_row(self):
        return {
            "account_id": self.account_id,
            "synthetic_account_number": self.synthetic_account_number,
            "bank_name": self.bank_name,
            "account_holder_person_id": self.account_holder_person_id or "",
            "branch": self.branch, "state": self.state,
            "account_type": self.account_type,
        }


_BANK_NAMES = ["Bank X", "National Trust Bank", "Union Commercial Bank",
               "Metro Cooperative Bank", "Bharat Savings Bank"]


def generate_bank_account(id_factory, rng: random.Random, is_mule: bool,
                           holder_person_id: str = None,
                           preferred_state: str = None) -> BankAccountRecord:
    account_number = "".join(rng.choice("0123456789") for _ in range(12))
    bank_name = rng.choice(_BANK_NAMES)
    state, district = pick_state_district(rng, preferred_state)
    branch = f"{district} Branch"
    account_type = rng.choices(["savings", "current"], weights=[0.8, 0.2], k=1)[0]
    holder = None if is_mule and rng.random() < 0.7 else holder_person_id
    rec = BankAccountRecord(id_factory.next("account"), account_number, bank_name,
                             holder, branch, state, account_type)
    rec.hidden_mule_status = is_mule
    return rec


class VehicleRecord:
    __slots__ = ("vehicle_id", "registration_number", "vehicle_type",
                 "owner_person_id", "state_of_registration")

    def __init__(self, vehicle_id, reg_number, vtype, owner_id, state):
        self.vehicle_id = vehicle_id
        self.registration_number = reg_number
        self.vehicle_type = vtype
        self.owner_person_id = owner_id
        self.state_of_registration = state

    def to_row(self):
        return {
            "vehicle_id": self.vehicle_id,
            "registration_number": self.registration_number,
            "vehicle_type": self.vehicle_type,
            "owner_person_id": self.owner_person_id,
            "state_of_registration": self.state_of_registration,
        }


def generate_vehicle(id_factory, rng: random.Random, owner_person: PersonRecord) -> VehicleRecord:
    state = owner_person.state
    if rng.random() < 0.05:
        state = rng.choice(list(VEHICLE_STATE_CODES.keys()))
    code = VEHICLE_STATE_CODES[state]
    district_num = rng.randint(1, 50)
    series = "".join(rng.choice("ABCDEFGHJKLMNPQRSTUVWXYZ") for _ in range(2))
    number = rng.randint(1000, 9999)
    reg = f"{code}{district_num:02d} {series} {number}"
    vtype = rng.choices(["two_wheeler", "hatchback", "sedan", "van"],
                         weights=[0.5, 0.25, 0.15, 0.1], k=1)[0]
    return VehicleRecord(id_factory.next("vehicle"), reg, vtype,
                          owner_person.person_id, state)


class LocationRecord:
    __slots__ = ("location_id", "name", "location_type", "state", "district", "city")

    def __init__(self, location_id, name, location_type, state, district, city):
        self.location_id = location_id
        self.name = name
        self.location_type = location_type
        self.state = state
        self.district = district
        self.city = city

    def to_row(self):
        return {
            "location_id": self.location_id, "name": self.name,
            "location_type": self.location_type, "state": self.state,
            "district": self.district, "city": self.city,
        }


def generate_location(id_factory, rng: random.Random, location_type: str,
                       state: str, district: str) -> LocationRecord:
    name_templates = {
        "police_station": f"{district} Cyber Cell Police Station",
        "cell_tower_site": f"Tower-{district}-{random.randint(1,99)}",
        "atm": f"{random.choice(_BANK_NAMES)} ATM, {district}",
        "cash_pickup_point": f"Cash Point, {district}",
        "residence": f"{district}",
        "business": f"{district} Commercial Complex",
    }
    name = name_templates.get(location_type, district)
    return LocationRecord(id_factory.next("location"), name, location_type,
                           state, district, district)
