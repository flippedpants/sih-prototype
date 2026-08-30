"""
evidence_cdr.py

Generates the CALLS table. Per E.10: calls are generated ONLY from planted
CALLED-type relationships - never independently. MULE roles deliberately generate
no calls to organizer/victim (that absence is itself the detectable signature);
only the RECRUITER->MULE onboarding burst exists in the call graph for mules.
"""

import random
from datetime import timedelta

from config import GenerationConfig
from topology import CaseUniverse


class CallRecord:
    __slots__ = ("call_id", "caller_phone_id", "receiver_phone_id", "timestamp",
                 "duration_seconds", "tower_location_id", "source_evidence_file_id",
                 "caller_person_id", "receiver_person_id")

    def to_row(self):
        return {
            "call_id": self.call_id,
            "caller_phone_id": self.caller_phone_id,
            "receiver_phone_id": self.receiver_phone_id,
            "timestamp": self.timestamp.isoformat(),
            "duration_seconds": self.duration_seconds,
            "tower_location_id": self.tower_location_id,
            "source_evidence_file_id": self.source_evidence_file_id or "",
        }


def _make_call(id_factory, caller_pid, receiver_pid, universe, ts, duration):
    c = CallRecord()
    c.call_id = id_factory.next("call")
    c.caller_person_id = caller_pid
    c.receiver_person_id = receiver_pid
    c.caller_phone_id = universe.person_phone.get(caller_pid)
    c.receiver_phone_id = universe.person_phone.get(receiver_pid)
    c.timestamp = ts
    c.duration_seconds = duration
    c.source_evidence_file_id = None  # linked later by export.py
    # tower = caller's clustered location; approximated by a synthetic id per district
    c.tower_location_id = f"TOWER-{universe.persons[caller_pid].district if caller_pid in universe.persons else 'NA'}"
    return c


def generate_calls(id_factory, cfg: GenerationConfig, rng: random.Random,
                    universe: CaseUniverse, anchor_date) -> list:
    calls = []

    for rel in universe.planted_relationships:
        if rel.relationship_type != "CALLED":
            continue
        pair = rel.role_pair

        if pair == ("ORGANIZER", "MANAGER"):
            n_calls = rng.randint(2, 5)
            t = anchor_date
            for _ in range(n_calls):
                gap_days = rng.randint(*cfg.organizer_manager_call_interval_days)
                t = t + timedelta(days=gap_days)
                dur = rng.randint(*cfg.organizer_manager_call_duration_sec)
                calls.append(_make_call(id_factory, rel.source_id, rel.target_id,
                                         universe, t, dur))

        elif pair == ("MANAGER", "AGENT"):
            n_calls = rng.randint(5, 12)
            t = anchor_date
            for _ in range(n_calls):
                # Poisson-ish interval via exponential draw
                gap_days = max(1, int(rng.expovariate(cfg.manager_agent_call_interval_days_lambda)))
                t = t + timedelta(days=gap_days)
                dur = rng.randint(*cfg.manager_agent_call_duration_sec)
                calls.append(_make_call(id_factory, rel.source_id, rel.target_id,
                                         universe, t, dur))

        elif pair == ("AGENT", "VICTIM"):
            burst_n = rng.randint(*cfg.agent_victim_call_burst)
            base_t = anchor_date + timedelta(days=rng.randint(0, 30),
                                              hours=rng.randint(9, 18))
            for _ in range(burst_n):
                offset = timedelta(minutes=rng.randint(0, cfg.agent_victim_call_window_minutes))
                dur = rng.randint(*cfg.agent_victim_call_duration_sec)
                calls.append(_make_call(id_factory, rel.source_id, rel.target_id,
                                         universe, base_t + offset, dur))

        elif pair == ("RECRUITER", "MULE"):
            burst_n = rng.randint(*cfg.recruiter_mule_onboarding_calls)
            base_t = anchor_date + timedelta(days=rng.randint(0, 15))
            for _ in range(burst_n):
                offset = timedelta(minutes=rng.randint(0, 30))
                dur = rng.randint(30, 300)
                calls.append(_make_call(id_factory, rel.source_id, rel.target_id,
                                         universe, base_t + offset, dur))
            # then silence - no further calls generated for this pair, by design

        elif pair == ("INNOCENT_ANCHOR", "INNOCENT_CONTACT"):
            n_calls = rng.randint(3, 20)   # ordinary, unremarkable frequency
            t = anchor_date
            for _ in range(n_calls):
                gap_days = rng.randint(1, 20)
                t = t + timedelta(days=gap_days)
                dur = rng.randint(30, 1200)
                calls.append(_make_call(id_factory, rel.source_id, rel.target_id,
                                         universe, t, dur))

        # MULE<->ORGANIZER/VICTIM: deliberately absent - no branch generates these.

    return calls
