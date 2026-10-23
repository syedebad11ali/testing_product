"""Owner-name check. No Flask imports; returns a bare verdict and never owner details."""
from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from backend.records.ownership import OwnershipIndex

audit = logging.getLogger("kpt.audit")
VERDICTS = ("match", "mismatch", "unable_to_verify")


class VerificationService:
    def __init__(self, data_dir: Path):
        self._index = OwnershipIndex(data_dir)

    def check(self, property_id: str, claimed_name: str, actor: str = "anonymous") -> dict:
        verdict = self._index.compare(property_id, claimed_name)
        # Audit trail: who asked about which listing and the verdict. The claimed name is not logged.
        audit.info("verification_check property=%s verdict=%s actor=%s", property_id.strip().upper()[:40], verdict,
                   hashlib.sha256(actor.encode()).hexdigest()[:12])
        return {"result": verdict, "indicative": True,
                "note": "Indicative only. A dataset comparison is not proof of ownership."}
