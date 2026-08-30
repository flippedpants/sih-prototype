"""
topology.py

Implements Part D's network topology templates. V1 scope (per Part A) builds the
combined D1 (hierarchical call-centre/investment-app operation) + D2 (mule-account
chain) topology for every case, plus an INNOCENT_CONTACT control cluster (the
negative-control piece of D3).

D4 (bridge/intermediary between two rings) and D5 (interstate spread) are NOT yet
implemented here - the data structures below are built so they can be added as
additional topology functions following the same pattern (see the TODO at the
bottom of this file). Flagging this honestly rather than claiming full D1-D5 coverage.

This is the ONLY place hidden_role / hidden_community_id / hidden_mule_status are
assigned - per E.0 step 3-4, everything downstream (CDR, transactions, FIR) is
generated FROM this planted structure, never independently.
"""

import random
from dataclasses import dataclass, field

from config import GenerationConfig
from entities import (
    generate_person, generate_organization, generate_phone,
    generate_bank_account, generate_vehicle, generate_location,
)


@dataclass
class PlantedRelationship:
    source_id: str
    target_id: str
    relationship_type: str          # CALLED | TRANSACTED
    hidden_ground_truth_label: str
    planted_by_topology: str
    # extra hints consumed by the evidence generators:
    role_pair: tuple = None
    chain_position: int = None


@dataclass
class CaseUniverse:
    """Everything generated for one case, before evidence (CDR/TXN/FIR) exists."""
    case_id: str
    ring_id: str
    persons: dict = field(default_factory=dict)          # person_id -> PersonRecord
    organizations: dict = field(default_factory=dict)
    phones: dict = field(default_factory=dict)
    accounts: dict = field(default_factory=dict)
    vehicles: dict = field(default_factory=dict)
    locations: dict = field(default_factory=dict)
    planted_relationships: list = field(default_factory=list)
    # convenience indexes:
    person_phone: dict = field(default_factory=dict)     # person_id -> phone_id
    person_account: dict = field(default_factory=dict)    # person_id -> account_id (primary)
    role_index: dict = field(default_factory=dict)        # role -> [person_id, ...]
    mule_chain_order: list = field(default_factory=list)  # list of {"victim_person_id", "chain_accounts"}
    # explicit references (fixes referential-integrity bug: these are always real
    # BANK_ACCOUNT ids that exist in universe.accounts, never fabricated strings)
    aggregator_account_id: str = None
    cashout_account_id: str = None


def _register_person(universe, person, role):
    person.hidden_role = role
    person.hidden_community_id = universe.ring_id
    universe.persons[person.person_id] = person
    universe.role_index.setdefault(role, []).append(person.person_id)
    return person


def build_case_topology(id_factory, cfg: GenerationConfig, rng: random.Random,
                         case_id: str, case_type: str, base_state: str) -> CaseUniverse:
    ring_id = f"RING_{case_id}"
    universe = CaseUniverse(case_id=case_id, ring_id=ring_id)

    # ---- police station location for this case's district -----------------
    from config import STATE_DISTRICTS
    district = rng.choice(STATE_DISTRICTS[base_state])
    station = generate_location(id_factory, rng, "police_station", base_state, district)
    universe.locations[station.location_id] = station

    # ======================================================================
    # D1 - HIERARCHICAL OPERATION: organizer -> manager(s) -> agents -> victims
    # ======================================================================
    organizer = _register_person(
        universe, generate_person(id_factory, cfg, rng, is_offender=True,
                                   preferred_state=base_state),
        "ORGANIZER")
    org_front = generate_organization(id_factory, rng, case_type, base_state)
    universe.organizations[org_front.org_id] = org_front

    n_managers = rng.randint(*cfg.n_managers)
    managers = []
    for _ in range(n_managers):
        m = _register_person(
            universe, generate_person(id_factory, cfg, rng, True, base_state),
            "MANAGER")
        managers.append(m)
        universe.planted_relationships.append(PlantedRelationship(
            organizer.person_id, m.person_id, "CALLED",
            "planted_organizer_manager_link", "D1", role_pair=("ORGANIZER", "MANAGER")))

    n_agents = rng.randint(*cfg.n_agents)
    agents = []
    for i in range(n_agents):
        a = _register_person(
            universe, generate_person(id_factory, cfg, rng, True, base_state),
            "AGENT")
        agents.append(a)
        mgr = managers[i % len(managers)]
        universe.planted_relationships.append(PlantedRelationship(
            mgr.person_id, a.person_id, "CALLED",
            "planted_manager_agent_link", "D1", role_pair=("MANAGER", "AGENT")))

    victims = []
    for a in agents:
        n_v = rng.randint(*cfg.n_victims_per_agent)
        for _ in range(n_v):
            v = _register_person(
                universe, generate_person(id_factory, cfg, rng, False),  # dispersed nationally
                "VICTIM")
            victims.append(v)
            universe.planted_relationships.append(PlantedRelationship(
                a.person_id, v.person_id, "CALLED",
                "planted_agent_victim_link", "D1", role_pair=("AGENT", "VICTIM")))

    # ======================================================================
    # D2 - MULE CHAIN(S): victim -> mule_A -> mule_B [-> mule_C] -> aggregator -> cashout
    # One chain per agent (feeding into a SHARED aggregator/cashout for the ring).
    # ======================================================================
    aggregator = _register_person(
        universe, generate_person(id_factory, cfg, rng, True, base_state), "AGGREGATOR")
    cashout = _register_person(
        universe, generate_person(id_factory, cfg, rng, True, base_state), "CASHOUT_OPERATOR")

    aggregator_account = generate_bank_account(
        id_factory, rng, is_mule=False, holder_person_id=aggregator.person_id,
        preferred_state=base_state)
    universe.accounts[aggregator_account.account_id] = aggregator_account
    universe.person_account[aggregator.person_id] = aggregator_account.account_id
    universe.aggregator_account_id = aggregator_account.account_id

    # FIX (V1.1): the cashout operator previously had no real BANK_ACCOUNT record,
    # so aggregator->cashout transactions referenced a fabricated "CASHOUT-{id}"
    # string that matched nothing in accounts.csv - a dangling foreign key.
    # Give the cashout operator a real account like every other role.
    cashout_account = generate_bank_account(
        id_factory, rng, is_mule=False, holder_person_id=cashout.person_id,
        preferred_state=base_state)
    universe.accounts[cashout_account.account_id] = cashout_account
    universe.person_account[cashout.person_id] = cashout_account.account_id
    universe.cashout_account_id = cashout_account.account_id

    cashout_vehicle = generate_vehicle(id_factory, rng, cashout)
    universe.vehicles[cashout_vehicle.vehicle_id] = cashout_vehicle
    cashout_location = generate_location(id_factory, rng, "cash_pickup_point",
                                          base_state, district)
    universe.locations[cashout_location.location_id] = cashout_location

    recruiter = _register_person(
        universe, generate_person(id_factory, cfg, rng, True, base_state), "RECRUITER")

    for v in victims:
        # victim's own account (funds leave from here)
        v_account = generate_bank_account(id_factory, rng, is_mule=False,
                                           holder_person_id=v.person_id,
                                           preferred_state=v.state)
        universe.accounts[v_account.account_id] = v_account
        universe.person_account[v.person_id] = v_account.account_id

        chain_len = rng.randint(*cfg.mule_chain_length)
        prev_account_id = v_account.account_id
        chain_accounts = [v_account.account_id]
        for pos in range(chain_len):
            mule = _register_person(
                universe, generate_person(id_factory, cfg, rng, True), "MULE")
            mule_account = generate_bank_account(
                id_factory, rng, is_mule=True, holder_person_id=mule.person_id,
                preferred_state=mule.state)   # dispersed - layering geography
            universe.accounts[mule_account.account_id] = mule_account
            universe.person_account[mule.person_id] = mule_account.account_id
            chain_accounts.append(mule_account.account_id)

            universe.planted_relationships.append(PlantedRelationship(
                prev_account_id, mule_account.account_id, "TRANSACTED",
                "planted_mule_chain_link", "D2",
                role_pair=("SOURCE", "MULE"), chain_position=pos))

            # recruiter -> mule: short onboarding burst, then silence
            universe.planted_relationships.append(PlantedRelationship(
                recruiter.person_id, mule.person_id, "CALLED",
                "planted_recruiter_mule_onboarding", "D2",
                role_pair=("RECRUITER", "MULE")))

            prev_account_id = mule_account.account_id

        # FIX (V1.1): the last mule -> aggregator hop is now included as a real
        # element of chain_accounts (not a separate, disconnected relationship),
        # so evidence generation naturally covers every hop including this one -
        # previously no CDR/transaction ever represented this final hop at all.
        chain_accounts.append(aggregator_account.account_id)
        universe.planted_relationships.append(PlantedRelationship(
            prev_account_id, aggregator_account.account_id, "TRANSACTED",
            "planted_mule_to_aggregator_link", "D2", role_pair=("MULE", "AGGREGATOR")))

        universe.mule_chain_order.append({
            "victim_person_id": v.person_id,
            "chain_accounts": chain_accounts,
        })

    # aggregator -> cashout planted relationship (evidence generated per-case,
    # batched, in evidence_txn.py - using the real cashout_account_id above)
    universe.planted_relationships.append(PlantedRelationship(
        aggregator_account.account_id, cashout_account.account_id, "TRANSACTED",
        "planted_aggregator_cashout_link", "D2", role_pair=("AGGREGATOR", "CASHOUT_OPERATOR")))

    # ======================================================================
    # Innocent-contact control cluster (D3 spirit) - ordinary social/business
    # contacts of the organizer/manager, deliberately NOT part of the ring
    # ======================================================================
    n_innocent = rng.randint(*cfg.n_innocent_contacts_per_case)
    for _ in range(n_innocent):
        ic = _register_person(
            universe, generate_person(id_factory, cfg, rng, False), "INNOCENT_CONTACT")
        # ordinary edge to organizer or a manager - low weight, non-criminal context
        anchor = rng.choice([organizer] + managers)
        universe.planted_relationships.append(PlantedRelationship(
            anchor.person_id, ic.person_id, "CALLED",
            "innocent_family_or_business_contact", "D3_control",
            role_pair=("INNOCENT_ANCHOR", "INNOCENT_CONTACT")))

    # ---- give every operational/criminal role a phone ----------------------
    for role in ["ORGANIZER", "MANAGER", "AGENT", "RECRUITER", "MULE"]:
        for pid in universe.role_index.get(role, []):
            burner = role != "ORGANIZER" or rng.random() < 0.5
            phone = generate_phone(id_factory, rng, is_operational_burner=burner,
                                    registered_person_id=pid if not burner else None)
            universe.phones[phone.phone_id] = phone
            universe.person_phone[pid] = phone.phone_id
    for role in ["VICTIM", "INNOCENT_CONTACT"]:
        for pid in universe.role_index.get(role, []):
            phone = generate_phone(id_factory, rng, is_operational_burner=False,
                                    registered_person_id=pid)
            universe.phones[phone.phone_id] = phone
            universe.person_phone[pid] = phone.phone_id

    return universe


# TODO (not implemented in this V1 pass, per the honesty note at the top of this file):
#   - D4: build_bridge_between(universe_a, universe_b, rng) -> shared INTERMEDIARY
#     connecting two independently-generated CaseUniverse rings.
#   - D5: interstate variant - same as build_case_topology but forcing
#     organizer/agent/mule/aggregator into deliberately different states, plus
#     a second FIR filed in a different state referencing an overlapping phone
#     or account number, to test cross-jurisdiction entity resolution.
