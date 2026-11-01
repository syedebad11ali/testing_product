"""Purge old private messages and resolved reports (see docs/MESSAGING.md, "Retention").

Dry run by default: prints counts only (never message text). Nothing is deleted without --apply, and nothing runs at all
unless a retention period is configured:

    MESSAGE_RETENTION_DAYS=365 REPORT_RETENTION_DAYS=730 python scripts/purge_messages.py            # dry run
    MESSAGE_RETENTION_DAYS=365 REPORT_RETENTION_DAYS=730 python scripts/purge_messages.py --apply    # delete one batch

Repeat (or schedule) until it reports zeros. It is idempotent and bounded by --batch (default 1000 rows per step).
No scheduler is configured by this repository: use Vercel Cron or any external scheduler to call it.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.config import Settings  # noqa: E402
from backend.db import open_database  # noqa: E402
from backend.services.retention_service import RetentionService  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="really delete (default is a dry run)")
    ap.add_argument("--batch", type=int, default=1000)
    args = ap.parse_args(argv)
    s = Settings.from_env()
    if s.message_retention_days <= 0:
        print("Retention is disabled: set MESSAGE_RETENTION_DAYS (> 0) after the owner has approved a period. Nothing done.")
        return 0
    db = open_database(s.database_url, local_path=s.local_db_path)
    result = RetentionService(db).run(s.message_retention_days, s.report_retention_days, args.batch, apply=args.apply)
    print({**result, "mode": "APPLIED" if args.apply else "dry-run"})
    return 0


if __name__ == "__main__":
    sys.exit(main())
