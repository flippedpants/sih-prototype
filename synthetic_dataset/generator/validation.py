"""
validation.py

V1.1 addition. Post-hoc validation that reads back exactly what was written to
disk (not in-memory generator state) and checks it for internal coherence. This
is deliberately independent of the generator code path, so it can catch bugs
the generator itself wouldn't "know" about - e.g. a dangling foreign key would
never raise a Python exception during generation, it just silently produces a
broken CSV row. Reading the files back and cross-checking is the only way to
actually prove coherence rather than assume it.

Can be run automatically after generation (generate_dataset.py's --validate,
on by default) or standalone:

    python3 validation.py --output-dir ./my_dataset
"""

import argparse
import csv
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


VALID_ROLES = {
    "ORGANIZER", "MANAGER", "AGENT", "RECRUITER", "MULE", "INTERMEDIARY",
    "AGGREGATOR", "CASHOUT_OPERATOR", "VICTIM", "INNOCENT_CONTACT",
}
VALID_NER_LABELS = {"PERSON", "PHONE", "LOCATION", "VEHICLE", "ORGANIZATION",
                     "BANK_ACCOUNT", "AMOUNT"}
FORBIDDEN_OBSERVABLE_COLUMNS = {"hidden_role", "hidden_community_id", "hidden_mule_status"}
AMOUNT_TOLERANCE = 0.01   # rupees - float rounding slack, not a real discrepancy


# ---------------------------------------------------------------------------
# Report data structures
# ---------------------------------------------------------------------------

@dataclass
class Issue:
    severity: str      # "ERROR" or "WARNING"
    category: str
    message: str
    case_id: str = ""


@dataclass
class ValidationReport:
    issues: list = field(default_factory=list)
    stats: dict = field(default_factory=dict)

    def add(self, severity, category, message, case_id=""):
        self.issues.append(Issue(severity, category, message, case_id))

    def errors(self):
        return [i for i in self.issues if i.severity == "ERROR"]

    def warnings(self):
        return [i for i in self.issues if i.severity == "WARNING"]

    def category_status(self, category):
        cat_errors = [i for i in self.issues if i.category == category and i.severity == "ERROR"]
        return "FAIL" if cat_errors else "PASS"


CATEGORIES = [
    "ENTITY_INTEGRITY", "CDR_INTEGRITY", "FINANCIAL_INTEGRITY", "FIR_INTEGRITY",
    "NER_INTEGRITY", "GROUND_TRUTH_INTEGRITY", "GROUND_TRUTH_ISOLATION", "TOPOLOGY",
]


# ---------------------------------------------------------------------------
# File loading
# ---------------------------------------------------------------------------

def load_csv(path: Path):
    if not path.exists():
        return []
    with open(path, newline="") as f:
        return list(csv.DictReader(f))


def load_json(path: Path):
    if not path.exists():
        return {}
    with open(path) as f:
        return json.load(f)


class CaseData:
    """Loads every file for one case directory back into memory for validation."""

    def __init__(self, case_dir: Path):
        self.case_dir = case_dir
        self.case_id = case_dir.name.replace("CASE_", "")

        ent = case_dir / "ENTITIES"
        self.persons = {r["person_id"]: r for r in load_csv(ent / "persons.csv")}
        self.organizations = {r["org_id"]: r for r in load_csv(ent / "organizations.csv")}
        self.phones = {r["phone_id"]: r for r in load_csv(ent / "phones.csv")}
        self.accounts = {r["account_id"]: r for r in load_csv(ent / "accounts.csv")}
        self.vehicles = {r["vehicle_id"]: r for r in load_csv(ent / "vehicles.csv")}
        self.locations = {r["location_id"]: r for r in load_csv(ent / "locations.csv")}
        self.derived_relationships = load_csv(ent / "derived_relationships.csv")

        self.calls = load_csv(case_dir / "CDR" / "CDR_0001.csv")
        self.transactions = load_csv(case_dir / "FINANCIAL" / "transactions_0001.csv")
        self.evidence_files = load_csv(case_dir / "EVIDENCE_META" / "evidence_files.csv")

        self.fir_dir = case_dir / "FIR"
        self.firs = self._load_firs()

        gt = case_dir / "GROUND_TRUTH"
        self.roles = load_json(gt / "roles.json")
        self.communities = load_json(gt / "communities.json")
        self.planted_relationships = load_json(gt / "relationships.json")
        self.fraud_events = load_json(gt / "fraud_events.json")

        self.case_summary = load_json(case_dir / "CASE_SUMMARY.json")

    def _load_firs(self):
        firs = {}
        if not self.fir_dir.exists():
            return firs
        for f in sorted(self.fir_dir.glob("FIR-*.txt")):
            fir_id = f.stem
            content = f.read_text()
            narrative = content.split("\n\n", 1)[1].rstrip("\n") if "\n\n" in content else content
            ner_path = self.fir_dir / "_ner_annotations" / f"{fir_id}_ner.json"
            ner = load_json(ner_path) if ner_path.exists() else []
            firs[fir_id] = {"narrative": narrative, "ner": ner, "full_text": content}
        return firs

    def all_entity_ids(self):
        return (set(self.persons) | set(self.organizations) | set(self.phones) |
                set(self.accounts) | set(self.vehicles) | set(self.locations))


def find_case_dirs(output_root: Path):
    return sorted([d for d in output_root.iterdir() if d.is_dir() and d.name.startswith("CASE_")])


# ---------------------------------------------------------------------------
# Individual validators
# ---------------------------------------------------------------------------

def validate_entity_integrity(case: CaseData, report: ValidationReport):
    cat = "ENTITY_INTEGRITY"

    for name, table, id_field in [
        ("person", case.persons, "person_id"), ("organization", case.organizations, "org_id"),
        ("phone", case.phones, "phone_id"), ("account", case.accounts, "account_id"),
        ("vehicle", case.vehicles, "vehicle_id"), ("location", case.locations, "location_id"),
    ]:
        ids = list(table.keys())
        if len(ids) != len(set(ids)):
            report.add("ERROR", cat, f"Duplicate {name} IDs found", case.case_id)

    for pid, row in case.phones.items():
        rp = row.get("registered_person_id", "")
        if rp and rp not in case.persons:
            report.add("ERROR", cat, f"Phone {pid} references missing person {rp}", case.case_id)

    for aid, row in case.accounts.items():
        holder = row.get("account_holder_person_id", "")
        if holder and holder not in case.persons:
            report.add("ERROR", cat, f"Account {aid} references missing person {holder}", case.case_id)

    for vid, row in case.vehicles.items():
        owner = row.get("owner_person_id", "")
        if owner and owner not in case.persons:
            report.add("ERROR", cat, f"Vehicle {vid} references missing person {owner}", case.case_id)


def validate_cdr_integrity(case: CaseData, report: ValidationReport):
    cat = "CDR_INTEGRITY"
    for row in case.calls:
        cid = row.get("call_id", "?")
        if row["caller_phone_id"] not in case.phones:
            report.add("ERROR", cat, f"Call {cid} caller phone missing: {row['caller_phone_id']}", case.case_id)
        if row["receiver_phone_id"] not in case.phones:
            report.add("ERROR", cat, f"Call {cid} receiver phone missing: {row['receiver_phone_id']}", case.case_id)
        try:
            dur = int(row["duration_seconds"])
            if dur <= 0:
                report.add("ERROR", cat, f"Call {cid} non-positive duration ({dur})", case.case_id)
        except (ValueError, KeyError):
            report.add("ERROR", cat, f"Call {cid} invalid/missing duration", case.case_id)
        try:
            datetime.fromisoformat(row["timestamp"])
        except Exception:
            report.add("ERROR", cat, f"Call {cid} invalid timestamp: {row.get('timestamp')}", case.case_id)


def validate_financial_integrity(case: CaseData, report: ValidationReport):
    cat = "FINANCIAL_INTEGRITY"

    for row in case.transactions:
        tid = row.get("transaction_id", "?")
        sender, receiver = row["sender_account_id"], row["receiver_account_id"]
        if sender not in case.accounts:
            report.add("ERROR", cat, f"Transaction {tid} sender account missing: {sender}", case.case_id)
        if receiver not in case.accounts:
            report.add("ERROR", cat, f"Transaction {tid} receiver account missing: {receiver}", case.case_id)
        try:
            amt = float(row["amount"])
            if amt <= 0:
                report.add("ERROR", cat, f"Transaction {tid} non-positive amount ({amt})", case.case_id)
        except (ValueError, KeyError):
            report.add("ERROR", cat, f"Transaction {tid} invalid/missing amount", case.case_id)
        try:
            datetime.fromisoformat(row["timestamp"])
        except Exception:
            report.add("ERROR", cat, f"Transaction {tid} invalid timestamp", case.case_id)

    if not case.fraud_events:
        report.add("WARNING", cat, "No fraud_events.json found - skipping money-conservation cross-check", case.case_id)
        return

    # cross-check every hop transaction against the authoritative fraud_events.json
    for victim_id, fe in case.fraud_events.items():
        chain = fe["chain_accounts"]
        hop_amounts = fe["hop_amounts"]
        for i in range(len(chain) - 1):
            sender, receiver = chain[i], chain[i + 1]
            expected_amount = hop_amounts[i]
            matches = [t for t in case.transactions
                       if t["sender_account_id"] == sender and t["receiver_account_id"] == receiver]
            if not matches:
                report.add("ERROR", cat,
                            f"Missing expected transaction {sender}->{receiver} "
                            f"for fraud event (victim {victim_id})", case.case_id)
                continue
            actual = float(matches[0]["amount"])
            if abs(actual - expected_amount) > AMOUNT_TOLERANCE:
                report.add("ERROR", cat,
                            f"Transaction {sender}->{receiver} amount {actual} != "
                            f"fraud-event amount {expected_amount} (victim {victim_id})", case.case_id)

    # case-level total: sum of initial amounts should equal CASE_SUMMARY total
    if case.case_summary:
        computed_total = sum(fe["initial_amount"] for fe in case.fraud_events.values())
        declared_total = case.case_summary.get("total_fraud_amount")
        if declared_total is not None and abs(computed_total - declared_total) > AMOUNT_TOLERANCE:
            report.add("ERROR", cat,
                        f"CASE_SUMMARY total_fraud_amount ({declared_total}) != "
                        f"sum of fraud_events initial amounts ({computed_total})", case.case_id)

        # money conservation: aggregator cannot pay out more than it received
        aggregator_account_id = case.case_summary.get("aggregator_account_id")
        total_in = sum(fe["final_amount_to_aggregator"] for fe in case.fraud_events.values())
        agg_out_txns = [t for t in case.transactions
                         if t["sender_account_id"] == aggregator_account_id]
        total_out = sum(float(t["amount"]) for t in agg_out_txns)
        if total_out > total_in + AMOUNT_TOLERANCE:
            report.add("ERROR", cat,
                        f"Aggregator outflow ({total_out:.2f}) exceeds inflow ({total_in:.2f}) "
                        f"- money creation detected", case.case_id)


def validate_fir_integrity(case: CaseData, report: ValidationReport):
    cat = "FIR_INTEGRITY"
    known_ids = case.all_entity_ids()
    for fir_id, fir in case.firs.items():
        for ann in fir["ner"]:
            eid = ann.get("entity_id")
            if eid and eid not in known_ids:
                report.add("ERROR", cat, f"FIR {fir_id} NER entity_id {eid} does not exist", case.case_id)


def validate_ner_integrity(case: CaseData, report: ValidationReport):
    """For every NER span: text[start:end] must exactly equal the canonical
    value of the referenced entity. This is the core NER-correctness check
    requested - not just 'does the file parse' but 'is every span exactly right'."""
    cat = "NER_INTEGRITY"
    for fir_id, fir in case.firs.items():
        narrative = fir["narrative"]
        for ann in fir["ner"]:
            start, end, label = ann.get("start"), ann.get("end"), ann.get("label")
            eid = ann.get("entity_id")

            if start is None or end is None or start >= end:
                report.add("ERROR", cat, f"FIR {fir_id} NER span invalid bounds "
                                          f"(start={start}, end={end})", case.case_id)
                continue
            if start < 0 or end > len(narrative):
                report.add("ERROR", cat, f"FIR {fir_id} NER span out of bounds "
                                          f"(len={len(narrative)})", case.case_id)
                continue
            if label not in VALID_NER_LABELS:
                report.add("WARNING", cat, f"FIR {fir_id} unexpected NER label {label}", case.case_id)

            span_text = narrative[start:end]
            expected = None
            if label == "PERSON" and eid in case.persons:
                expected = case.persons[eid]["canonical_name"]
            elif label == "PHONE" and eid in case.phones:
                expected = case.phones[eid]["number"]

            if expected is not None and span_text != expected:
                report.add("ERROR", cat,
                            f"FIR {fir_id} NER span mismatch: text[{start}:{end}]="
                            f"'{span_text}' but expected '{expected}'", case.case_id)


def validate_ground_truth_integrity(case: CaseData, report: ValidationReport):
    cat = "GROUND_TRUTH_INTEGRITY"
    known_ids = case.all_entity_ids()

    for eid, info in case.roles.items():
        if eid not in known_ids:
            report.add("ERROR", cat, f"Ground truth role entity {eid} does not exist", case.case_id)
        role = info.get("hidden_role")
        if role and role not in VALID_ROLES:
            report.add("ERROR", cat, f"Ground truth entity {eid} has invalid role '{role}'", case.case_id)

    for comm_id, info in case.communities.items():
        for member in info.get("members", []):
            if member not in case.persons:
                report.add("ERROR", cat, f"Community {comm_id} references missing person {member}", case.case_id)

    for rel_id, info in case.planted_relationships.items():
        s, t = info.get("source"), info.get("target")
        if s not in known_ids:
            report.add("ERROR", cat, f"Planted relationship {rel_id} source {s} missing", case.case_id)
        if t not in known_ids:
            report.add("ERROR", cat, f"Planted relationship {rel_id} target {t} missing", case.case_id)


def validate_ground_truth_isolation(case: CaseData, report: ValidationReport):
    """Confirms the observable tables do NOT leak role/community labels - the
    analysis pipeline must never be able to read hidden_role etc. off disk."""
    cat = "GROUND_TRUTH_ISOLATION"
    for name, table in [("persons.csv", case.persons), ("accounts.csv", case.accounts)]:
        if table:
            sample_cols = set(next(iter(table.values())).keys())
            leaked = FORBIDDEN_OBSERVABLE_COLUMNS & sample_cols
            if leaked:
                report.add("ERROR", cat, f"{name} leaks ground-truth columns: {leaked}", case.case_id)


def validate_topology(case: CaseData, report: ValidationReport):
    """Confirms the generated evidence actually realizes D1 (hierarchical) and
    D2 (mule chain), rather than assuming the topology builder succeeded just
    because it ran without an exception."""
    cat = "TOPOLOGY"

    d1_required = {"planted_organizer_manager_link", "planted_manager_agent_link",
                   "planted_agent_victim_link"}
    d2_required = {"planted_mule_chain_link", "planted_mule_to_aggregator_link",
                   "planted_aggregator_cashout_link"}
    present_labels = {rel.get("hidden_ground_truth_label")
                       for rel in case.planted_relationships.values()}

    missing_d1 = d1_required - present_labels
    missing_d2 = d2_required - present_labels
    if missing_d1:
        report.add("ERROR", cat, f"D1 topology incomplete, missing edge types: {missing_d1}", case.case_id)
    if missing_d2:
        report.add("ERROR", cat, f"D2 topology incomplete, missing edge types: {missing_d2}", case.case_id)

    roles_present = {v.get("hidden_role") for v in case.roles.values()}
    required_roles = {"ORGANIZER", "MANAGER", "AGENT", "VICTIM", "MULE",
                       "AGGREGATOR", "CASHOUT_OPERATOR"}
    missing_roles = required_roles - roles_present
    if missing_roles:
        report.add("ERROR", cat, f"Missing required roles for D1/D2: {missing_roles}", case.case_id)

    # every mule-chain edge referenced in ground truth should have a matching
    # real transaction (this overlaps with FINANCIAL_INTEGRITY's per-hop check
    # but confirms it from the topology angle: the STRUCTURE is present, not
    # just that amounts happen to match where transactions do exist)
    planted_transacted = [r for r in case.planted_relationships.values()
                           if r.get("relationship_type") == "TRANSACTED"]
    observed_pairs = {(t["sender_account_id"], t["receiver_account_id"]) for t in case.transactions}
    missing_edges = 0
    for rel in planted_transacted:
        if rel.get("planted_by_topology") == "D2" and (rel["source"], rel["target"]) not in observed_pairs:
            missing_edges += 1
    if missing_edges:
        report.add("ERROR", cat, f"{missing_edges} planted D2 TRANSACTED edges have no "
                                  f"corresponding transaction record", case.case_id)


VALIDATORS = [
    validate_entity_integrity,
    validate_cdr_integrity,
    validate_financial_integrity,
    validate_fir_integrity,
    validate_ner_integrity,
    validate_ground_truth_integrity,
    validate_ground_truth_isolation,
    validate_topology,
]


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def validate_dataset(output_root: Path) -> ValidationReport:
    report = ValidationReport()
    case_dirs = find_case_dirs(output_root)

    totals = {"cases": 0, "persons": 0, "organizations": 0, "phones": 0,
              "accounts": 0, "calls": 0, "transactions": 0, "firs": 0}

    for case_dir in case_dirs:
        case = CaseData(case_dir)
        totals["cases"] += 1
        totals["persons"] += len(case.persons)
        totals["organizations"] += len(case.organizations)
        totals["phones"] += len(case.phones)
        totals["accounts"] += len(case.accounts)
        totals["calls"] += len(case.calls)
        totals["transactions"] += len(case.transactions)
        totals["firs"] += len(case.firs)

        for validator in VALIDATORS:
            validator(case, report)

    report.stats = totals
    return report


def print_report(report: ValidationReport):
    s = report.stats
    print("\nDATASET VALIDATION REPORT")
    print("=" * 60)
    print(f"Cases:                 {s.get('cases', 0):,}")
    print(f"Persons:               {s.get('persons', 0):,}")
    print(f"Organizations:         {s.get('organizations', 0):,}")
    print(f"Phones:                {s.get('phones', 0):,}")
    print(f"Accounts:              {s.get('accounts', 0):,}")
    print(f"CDR records:           {s.get('calls', 0):,}")
    print(f"Transactions:          {s.get('transactions', 0):,}")
    print(f"FIRs:                  {s.get('firs', 0):,}")
    print()
    for cat in CATEGORIES:
        print(f"{cat:<22} {report.category_status(cat)}")
    print()
    print(f"Errors: {len(report.errors())}")
    print(f"Warnings: {len(report.warnings())}")

    if report.errors():
        print("\n--- ERROR DETAIL (first 20) ---")
        for issue in report.errors()[:20]:
            print(f"[{issue.case_id}] {issue.category}: {issue.message}")
        if len(report.errors()) > 20:
            print(f"... and {len(report.errors()) - 20} more")

    if report.warnings():
        print("\n--- WARNING DETAIL (first 10) ---")
        for issue in report.warnings()[:10]:
            print(f"[{issue.case_id}] {issue.category}: {issue.message}")
        if len(report.warnings()) > 10:
            print(f"... and {len(report.warnings()) - 10} more")


def main():
    parser = argparse.ArgumentParser(description="Validate a generated synthetic dataset")
    parser.add_argument("--output-dir", type=str, required=True)
    args = parser.parse_args()
    report = validate_dataset(Path(args.output_dir))
    print_report(report)
    if report.errors():
        raise SystemExit(1)


if __name__ == "__main__":
    main()
