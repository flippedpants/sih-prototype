"""
ids.py

Sequential ID generation per E.1's prefix conventions. One counter per entity type,
scoped to a single generation run (reset per dataset build, not global).
"""

from collections import defaultdict


class IdFactory:
    """Hands out sequential, prefixed IDs. One instance per dataset-generation run."""

    _PREFIXES = {
        "case": "CYB",              # special-cased: CYB-{year}-{seq:03d}
        "person": "P",
        "organization": "ORG",
        "phone": "PH",
        "account": "ACC",
        "vehicle": "VEH",
        "location": "LOC",
        "evidence_file": "EVD",
        "call": "CALL",
        "transaction": "TXN",
        "fir": "FIR",
        "relationship": "REL",
    }

    _WIDTH = {
        "case": 3, "person": 6, "organization": 4, "phone": 6, "account": 6,
        "vehicle": 4, "location": 4, "evidence_file": 6, "call": 7,
        "transaction": 7, "fir": 4, "relationship": 7,
    }

    def __init__(self):
        self._counters = defaultdict(int)

    def next(self, kind: str) -> str:
        self._counters[kind] += 1
        n = self._counters[kind]
        prefix = self._PREFIXES[kind]
        width = self._WIDTH[kind]
        return f"{prefix}-{n:0{width}d}"

    def next_case_id(self, year: int) -> str:
        self._counters["case"] += 1
        return f"CYB-{year}-{self._counters['case']:03d}"
