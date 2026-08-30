"""
ground_truth.py

Exports the hidden ground-truth JSON files (E.14): roles.json, communities.json,
relationships.json. Written ONLY after all evidence tables are finalized, and never
included in anything the analysis pipeline or dashboard would read (E.0 step 14 /
E.17's privacy requirement, carried from the master context).
"""

import json

from topology import CaseUniverse


def build_roles_json(universe: CaseUniverse) -> dict:
    roles = {}
    for pid, person in universe.persons.items():
        if person.hidden_role:
            roles[pid] = {"hidden_role": person.hidden_role,
                          "ring_id": person.hidden_community_id}
    for aid, account in universe.accounts.items():
        if account.hidden_mule_status:
            roles[aid] = {"hidden_role": "MULE", "hidden_mule_status": True,
                          "ring_id": universe.ring_id}
    return roles


def build_communities_json(universe: CaseUniverse) -> dict:
    members = [pid for pid, p in universe.persons.items()
               if p.hidden_role not in (None, "INNOCENT_CONTACT")]
    innocent_members = [pid for pid, p in universe.persons.items()
                         if p.hidden_role == "INNOCENT_CONTACT"]
    return {
        universe.ring_id: {
            "members": members, "topology": "D1_hierarchical+D2_mule_chain",
            "is_innocent_cluster": False,
        },
        f"INNOCENT_CLUSTER_{universe.case_id}": {
            "members": innocent_members, "topology": "D3_control",
            "is_innocent_cluster": True,
        },
    }


def build_relationships_json(universe: CaseUniverse) -> dict:
    out = {}
    for i, rel in enumerate(universe.planted_relationships):
        rel_id = f"PLANTED-{universe.case_id}-{i:05d}"
        out[rel_id] = {
            "source": rel.source_id, "target": rel.target_id,
            "relationship_type": rel.relationship_type,
            "hidden_ground_truth_label": rel.hidden_ground_truth_label,
            "planted_by_topology": rel.planted_by_topology,
        }
    return out


def write_ground_truth(output_dir, universe: CaseUniverse, fraud_events: list = None):
    gt_dir = output_dir / "GROUND_TRUTH"
    gt_dir.mkdir(parents=True, exist_ok=True)
    with open(gt_dir / "roles.json", "w") as f:
        json.dump(build_roles_json(universe), f, indent=2)
    with open(gt_dir / "communities.json", "w") as f:
        json.dump(build_communities_json(universe), f, indent=2)
    with open(gt_dir / "relationships.json", "w") as f:
        json.dump(build_relationships_json(universe), f, indent=2)
    # V1.1 addition: the authoritative money-trail record for every fraud event
    # in this case, keyed by victim_person_id. This is what validation.py
    # cross-checks the observable FINANCIAL/transactions_0001.csv against - it
    # is not a role/community label, so it does not violate the hidden-ground-
    # truth separation rule (every amount in it is already fully observable in
    # the transactions file; this just gives validation the expected values to
    # check the observable data against).
    if fraud_events is not None:
        fe_dict = {fe.victim_person_id: fe.to_ground_truth_dict() for fe in fraud_events}
        with open(gt_dir / "fraud_events.json", "w") as f:
            json.dump(fe_dict, f, indent=2)
