"""
fir_generator.py

Generates FIR narratives from templates, with NER spans computed automatically at
insertion time (E.12) - because we know exactly where each entity gets inserted,
no separate annotation pass is needed. This is the "free labeled data" mechanism
from the master context's NER strategy.

Legal-section assignment follows scenario -> modus operandi -> facts -> provision,
using the verified BNS/IT-Act sections from Part E v2 (E.12 revised).
"""

import random
from datetime import timedelta

from config import GenerationConfig
from topology import CaseUniverse


CALL_CENTRE_TEMPLATES = [
    (
        "On {date}, the complainant {victim_name}, resident of {victim_address}, "
        "received a call from mobile number {agent_phone} in which the caller "
        "falsely represented himself as a bank official and induced the complainant "
        "to share confidential banking details. Acting on this deception, an amount "
        "of Rs. {amount} was fraudulently transferred out of the complainant's "
        "account. The complainant was directed to transfer funds to an account "
        "held with {bank_name}. The complainant realized the fraud only after "
        "noticing unauthorized debit alerts on {date2} and immediately reported "
        "the matter to the {police_station}."
    ),
    (
        "The complainant {victim_name} states that on {date}, an unknown person "
        "using mobile number {agent_phone} contacted the complainant claiming to "
        "be from the customer support division of a telecom/banking service and "
        "requested an OTP for 'verification purposes'. The complainant, believing "
        "the call to be genuine, shared the OTP, following which Rs. {amount} was "
        "debited from the complainant's account without authorization. The amount "
        "was traced to have been credited to an account with {bank_name}. The "
        "matter is reported to {police_station} for investigation."
    ),
]

FAKE_INVESTMENT_TEMPLATES = [
    (
        "The complainant {victim_name}, residing at {victim_address}, states that "
        "on {date} he/she was contacted through a social media platform by a "
        "person offering high returns on investment through an online trading "
        "application. Believing the representations to be genuine, the complainant "
        "invested a total sum of Rs. {amount}, transferring the amount to an "
        "account held with {bank_name}. The application subsequently stopped "
        "functioning and all contact with the caller (mobile number {agent_phone}) "
        "was lost. The complainant approached {police_station} on {date2} upon "
        "realizing the fraud."
    ),
    (
        "It is submitted by the complainant {victim_name} that between {date} and "
        "{date2}, the complainant was induced by unknown persons to deposit funds "
        "in a fraudulent investment scheme operated through a mobile application. "
        "The complainant transferred an aggregate sum of Rs. {amount} to an account "
        "maintained with {bank_name}, acting on assurances received via mobile "
        "number {agent_phone}. The complainant lodges this complaint at "
        "{police_station} after being unable to withdraw the invested amount."
    ),
]


def _legal_sections_for(case_type: str, rng: random.Random) -> list:
    """E.12 revised: scenario -> modus operandi -> facts -> provision."""
    sections = ["BNS Section 318 (cheating)"]
    if rng.random() < 0.6:
        sections.append("IT Act Section 66D (cheating by personation using computer resource)")
    if case_type == "fake_investment_app" and rng.random() < 0.5:
        sections.append("BNS Section 336(3) (forgery for the purpose of cheating)")
    if rng.random() < 0.3:
        sections.append("BNS Section 61 (criminal conspiracy)")
    if rng.random() < 0.15:
        sections.append("IT Act Section 66C (identity theft)")
    return sections


class FIRRecord:
    def __init__(self):
        self.fir_id = None
        self.case_id = None
        self.date_filed = None
        self.police_station = None
        self.complainant_person_id = None
        self.legal_sections = []
        self.narrative_text = ""
        self.ner_annotations = []   # list of dicts: start, end, label, entity_id
        self.utr_number = None
        self.suspected_email = None

    def to_row(self):
        return {
            "fir_id": self.fir_id, "case_id": self.case_id,
            "date_filed": self.date_filed.isoformat(),
            "police_station": self.police_station,
            "complainant_person_id": self.complainant_person_id,
            "legal_sections": "; ".join(self.legal_sections),
            "narrative_text": self.narrative_text,
            "utr_number": self.utr_number or "",
            "suspected_email": self.suspected_email or "",
        }


def _insert_and_track(template: str, slots: dict, entity_labels: dict):
    """
    Fills `template` with `slots`, tracking the character span of every slot
    that has a corresponding entry in `entity_labels` (slot_name -> (label, entity_id)).
    Returns (final_text, annotations).
    """
    text = template
    annotations = []
    # Process slots in the order they appear in the template to keep offsets correct;
    # do this by repeatedly finding the next {slot} occurrence and substituting.
    import re
    pattern = re.compile(r"\{(\w+)\}")

    result_parts = []
    last_end = 0
    cursor_out = 0
    for m in pattern.finditer(template):
        slot_name = m.group(1)
        result_parts.append(template[last_end:m.start()])
        cursor_out += len(template[last_end:m.start()])
        value = str(slots.get(slot_name, ""))
        start_offset = cursor_out
        result_parts.append(value)
        cursor_out += len(value)
        if slot_name in entity_labels:
            label, entity_id = entity_labels[slot_name]
            annotations.append({
                "start": start_offset, "end": cursor_out,
                "label": label, "entity_id": entity_id,
            })
        last_end = m.end()
    result_parts.append(template[last_end:])
    text = "".join(result_parts)
    return text, annotations


def generate_fir_for_chain(id_factory, cfg: GenerationConfig, rng: random.Random,
                            universe: CaseUniverse, case_type: str,
                            victim_person_id: str, agent_person_id: str,
                            fraud_event, anchor_date,
                            police_station_name: str) -> FIRRecord:
    """
    V1.1 FIX: `fraud_event` (a fraud_events.FraudEvent) is now REQUIRED and is the
    only source of the amount named in the FIR - this used to be sampled
    independently here, producing a number unrelated to the actual transaction
    trail. The amount is also now tracked as an NER span (label AMOUNT).

    V1.1 FIX: the FIR now cites the bank the victim actually sent money to (the
    first hop of their own chain - chain_accounts[1]), not the ring's far
    downstream aggregator account, which the victim would have no way to know
    about and which a real complainant would never name in an FIR.
    """
    victim = universe.persons[victim_person_id]
    agent_phone_id = universe.person_phone.get(agent_person_id)
    agent_phone = universe.phones[agent_phone_id].number if agent_phone_id else "UNKNOWN"

    # deliberately mention only the victim, agent phone, amount, bank -
    # organizer/manager/mule are NOT named in the originating FIR, per Part D's
    # design that these roles surface through other evidence, not the complaint.
    first_hop_account_id = fraud_event.chain_accounts[1] if len(fraud_event.chain_accounts) > 1 else None
    bank_name = (universe.accounts[first_hop_account_id].bank_name
                 if first_hop_account_id and first_hop_account_id in universe.accounts
                 else "a bank")

    date1 = anchor_date + timedelta(days=rng.randint(0, 20))
    date2 = date1 + timedelta(days=rng.randint(1, 10))
    amount_str = f"{fraud_event.initial_amount:,.0f}"   # THE authoritative amount, not resampled

    templates = CALL_CENTRE_TEMPLATES if case_type == "call_centre_phishing" else FAKE_INVESTMENT_TEMPLATES
    template = rng.choice(templates)

    slots = {
        "victim_name": victim.canonical_name,
        "victim_address": victim.address,
        "agent_phone": agent_phone,
        "amount": amount_str,
        "bank_name": bank_name,
        "date": date1.strftime("%d-%m-%Y"),
        "date2": date2.strftime("%d-%m-%Y"),
        "police_station": police_station_name,
    }
    entity_labels = {
        "victim_name": ("PERSON", victim_person_id),
        "agent_phone": ("PHONE", agent_phone_id),
        "amount": ("AMOUNT", None),   # not tied to a master entity table - the
                                       # value itself is checked against
                                       # fraud_event.initial_amount in validation
    }

    text, annotations = _insert_and_track(template, slots, entity_labels)

    fir = FIRRecord()
    fir.fir_id = id_factory.next("fir")
    fir.case_id = universe.case_id
    fir.date_filed = date2
    fir.police_station = police_station_name
    fir.complainant_person_id = victim_person_id
    fir.legal_sections = _legal_sections_for(case_type, rng)
    fir.narrative_text = text
    fir.ner_annotations = annotations
    fir.utr_number = None if rng.random() < cfg.p_utr_missing else "".join(
        rng.choice("0123456789") for _ in range(22))
    fir.suspected_email = None if rng.random() < cfg.p_email_missing else \
        f"{agent_person_id.lower()}@mailservice.com"

    return fir
