"""
export.py

Writes the per-case directory structure (E.18) and generates EVIDENCE_FILE metadata
records (E.3) simulating what the "upload all files, auto-classify" workflow would
see for this case.
"""

import csv
import random
from datetime import timedelta
from pathlib import Path

from config import GenerationConfig


def _write_csv(path: Path, rows: list, fieldnames: list):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _sample_confidence(cfg: GenerationConfig, rng: random.Random):
    buckets = cfg.classification_confidence_buckets
    names = list(buckets.keys())
    weights = [buckets[n][2] for n in names]
    chosen = rng.choices(names, weights=weights, k=1)[0]
    lo, hi, _ = buckets[chosen]
    return chosen, round(rng.uniform(lo, hi), 3)


def build_evidence_file_records(id_factory, cfg: GenerationConfig, rng: random.Random,
                                 case_id: str, generated_files: list, anchor_date):
    """
    generated_files: list of (filename, detected_type, file_type) tuples for files
    actually produced in this case's export (FIR pdfs, CDR csv, etc.)
    """
    records = []
    for filename, detected_type, file_type in generated_files:
        bucket, confidence = _sample_confidence(cfg, rng)
        investigator_override = ""
        if bucket == "low":
            correct = rng.random() < cfg.investigator_override_correct_rate
            investigator_override = detected_type if correct else "UNKNOWN"
        upload_ts = anchor_date + timedelta(hours=rng.randint(0, 72))
        records.append({
            "evidence_file_id": id_factory.next("evidence_file"),
            "case_id": case_id,
            "filename": filename,
            "file_type": file_type,
            "detected_type": detected_type,
            "classification_confidence": confidence,
            "investigator_override": investigator_override,
            "upload_timestamp": upload_ts.isoformat(),
            "processing_status": "processed",
        })
    return records


def export_case(output_root: Path, universe, firs, calls, transactions,
                 derived_relationships, fraud_events, id_factory, cfg: GenerationConfig,
                 rng: random.Random, anchor_date):
    case_dir = output_root / f"CASE_{universe.case_id}"

    # -- FIR/ (rendered as .txt here in lieu of PDF rendering, which is a
    #    presentation-layer concern out of scope for the generator itself) --
    fir_files = []
    for fir in firs:
        fname = f"{fir.fir_id}.txt"
        (case_dir / "FIR").mkdir(parents=True, exist_ok=True)
        with open(case_dir / "FIR" / fname, "w") as f:
            f.write(f"FIR No: {fir.fir_id}\n")
            f.write(f"Police Station: {fir.police_station}\n")
            f.write(f"Date Filed: {fir.date_filed.date()}\n")
            f.write(f"Legal Sections: {'; '.join(fir.legal_sections)}\n")
            f.write(f"UTR Number: {fir.utr_number or 'NOT PROVIDED'}\n")
            f.write(f"Suspected Email: {fir.suspected_email or 'NOT PROVIDED'}\n\n")
            f.write(fir.narrative_text + "\n")
        fir_files.append((fname, "FIR", ".txt"))

    # separate NER annotation export (not something an investigator uploads,
    # but needed for evaluation) - kept alongside, not in EVIDENCE_META
    ner_dir = case_dir / "FIR" / "_ner_annotations"
    ner_dir.mkdir(parents=True, exist_ok=True)
    import json
    for fir in firs:
        with open(ner_dir / f"{fir.fir_id}_ner.json", "w") as f:
            json.dump(fir.ner_annotations, f, indent=2)

    # -- CDR/ --
    cdr_rows = [c.to_row() for c in calls]
    cdr_fname = "CDR_0001.csv"
    if cdr_rows:
        _write_csv(case_dir / "CDR" / cdr_fname, cdr_rows, list(cdr_rows[0].keys()))
    cdr_files = [(cdr_fname, "CDR", ".csv")] if cdr_rows else []

    # -- FINANCIAL/ --
    txn_rows = [t.to_row() for t in transactions]
    txn_fname = "transactions_0001.csv"
    if txn_rows:
        _write_csv(case_dir / "FINANCIAL" / txn_fname, txn_rows, list(txn_rows[0].keys()))
    txn_files = [(txn_fname, "FINANCIAL", ".csv")] if txn_rows else []

    # -- ENTITIES/ --
    ent_dir = case_dir / "ENTITIES"
    person_rows = [p.to_row() for p in universe.persons.values()]
    _write_csv(ent_dir / "persons.csv", person_rows, list(person_rows[0].keys()))
    org_rows = [o.to_row() for o in universe.organizations.values()]
    if org_rows:
        _write_csv(ent_dir / "organizations.csv", org_rows, list(org_rows[0].keys()))
    phone_rows = [ph.to_row() for ph in universe.phones.values()]
    _write_csv(ent_dir / "phones.csv", phone_rows, list(phone_rows[0].keys()))
    acct_rows = [a.to_row() for a in universe.accounts.values()]
    _write_csv(ent_dir / "accounts.csv", acct_rows, list(acct_rows[0].keys()))
    veh_rows = [v.to_row() for v in universe.vehicles.values()]
    if veh_rows:
        _write_csv(ent_dir / "vehicles.csv", veh_rows, list(veh_rows[0].keys()))
    loc_rows = [l.to_row() for l in universe.locations.values()]
    if loc_rows:
        _write_csv(ent_dir / "locations.csv", loc_rows, list(loc_rows[0].keys()))
    entity_files = [
        ("persons.csv", "ENTITY_LIST", ".csv"),
        ("accounts.csv", "ENTITY_LIST", ".csv"),
    ]
    if veh_rows:
        entity_files.append(("vehicles.csv", "VEHICLE_RECORD", ".csv"))

    # -- derived relationships (pass-2, what the pipeline actually sees) --
    rel_rows = [r.to_row() for r in derived_relationships]
    if rel_rows:
        _write_csv(case_dir / "ENTITIES" / "derived_relationships.csv",
                   rel_rows, list(rel_rows[0].keys()))

    # -- GROUND_TRUTH/ (never exposed to pipeline) --
    from ground_truth import write_ground_truth
    write_ground_truth(case_dir, universe, fraud_events)

    # -- CASE_SUMMARY.json (V1.1 addition): case-level aggregate for the
    #    "case metadata must match" consistency requirement - the total here
    #    must equal both the sum of FIR-stated amounts and the sum of each
    #    chain's first-hop transaction amount, since all three now read from
    #    the same fraud_events list.
    #    IMPORTANT: sum the SAME rounded values that fraud_events.json stores
    #    (round-per-event, then sum) rather than summing full-precision floats
    #    and rounding once - those two orders don't agree past a few paise,
    #    which validation.py's cross-check correctly flags as a mismatch.
    import json as _json
    total_fraud_amount = sum(round(fe.initial_amount, 2) for fe in fraud_events)
    case_summary = {
        "case_id": universe.case_id,
        "total_fraud_amount": round(total_fraud_amount, 2),
        "n_victims": len(fraud_events),
        "n_mule_chains": len(fraud_events),
        "aggregator_account_id": universe.aggregator_account_id,
        "cashout_account_id": universe.cashout_account_id,
    }
    with open(case_dir / "CASE_SUMMARY.json", "w") as f:
        _json.dump(case_summary, f, indent=2)

    # -- EVIDENCE_META/ (what the upload/classification step would see) --
    all_files = fir_files + cdr_files + txn_files + entity_files
    evidence_records = build_evidence_file_records(
        id_factory, cfg, rng, universe.case_id, all_files, anchor_date)
    if evidence_records:
        _write_csv(case_dir / "EVIDENCE_META" / "evidence_files.csv",
                   evidence_records, list(evidence_records[0].keys()))

    return case_dir
