"""
Deterministic per-concern seed derivation.

The generator used to share one global seeded `random` stream across every
concern (case selection, entity attributes, background noise, FIR text).
That meant a change to how many random calls happen in one function (e.g.
adding phone-number digit generation) shifted every random decision that
happened afterward in the shared sequence - including unrelated ones, like
which motif got picked for a later case.

`derive_seed` lets each concern get its own independent `random.Random()`
instance, all derived from one user-facing `--seed`, so the whole run stays
reproducible from a single number while no stream can leak into another.
"""

import hashlib


def derive_seed(master_seed: int, stream_name: str) -> int:
    """Deterministically derives an independent sub-seed for a named stream
    from one master seed, so each concern gets its own random.Random()
    instance that unrelated code changes in another stream cannot affect."""
    digest = hashlib.sha256(f"{master_seed}-{stream_name}".encode()).hexdigest()
    return int(digest, 16) % (2**32)
