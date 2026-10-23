"""Server-only ownership lookup used by the verification endpoint.

Owner names live only in ``backend/datasets`` and are read here, never in ``Store`` and
never sent to a client. The only thing this module can say about a name is whether it
matches the registered owner. Previous owners are deliberately not loaded at all.
"""
from __future__ import annotations

import csv
import hmac
import re
from pathlib import Path

_TITLES = re.compile(r"\b(mr|mrs|ms|miss|dr|syed|sayyid)\b\.?", re.IGNORECASE)


def normalise_name(value: str) -> str:
    """Lower-case, drop punctuation and honorifics, collapse whitespace."""
    cleaned = re.sub(r"[^a-z\s]", " ", _TITLES.sub(" ", str(value or "").casefold()))
    return " ".join(cleaned.split())


class OwnershipIndex:
    """property id (upper-case) -> normalised registered owner name."""

    def __init__(self, data_dir: Path):
        self._owners: dict[str, str] = {}
        for path in sorted(Path(data_dir).glob("*.csv")):
            with open(path, encoding="utf-8-sig", newline="") as fh:
                for row in csv.DictReader(fh):
                    pid = (row.get("Property ID") or "").strip().upper()
                    owner = normalise_name(row.get("Owner Name") or row.get("Property Owner") or "")
                    if pid and owner:
                        self._owners[pid] = owner

    def compare(self, property_id: str, claimed_name: str) -> str:
        """Return ``match`` | ``mismatch`` | ``unable_to_verify`` (never a name)."""
        owner = self._owners.get(str(property_id or "").strip().upper())
        claimed = normalise_name(claimed_name)
        if owner is None or len(claimed) < 3:
            return "unable_to_verify"
        return "match" if hmac.compare_digest(owner.encode(), claimed.encode()) else "mismatch"
