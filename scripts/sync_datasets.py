"""Keep the two dataset copies identical.

The backend reads CSVs from ``backend/datasets/``; the browser downloads the same files
from ``public/assets/Dataset/`` (they must be static assets). ``backend/datasets`` is the
source of truth.

    python scripts/sync_datasets.py           # copy backend -> public
    python scripts/sync_datasets.py --check   # exit 1 if they differ (used by the tests)
"""
from __future__ import annotations

import filecmp
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / "backend" / "datasets", ROOT / "public" / "assets" / "Dataset"


def main(check: bool) -> int:
    drift = []
    for src in sorted(SRC.glob("*.csv")):
        dst = DST / src.name
        if dst.exists() and filecmp.cmp(src, dst, shallow=False):
            continue
        drift.append(src.name)
        if not check:
            DST.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    extra = sorted(p.name for p in DST.glob("*.csv") if not (SRC / p.name).exists())
    if check:
        for name in drift:
            print(f"DIFFERS: {name}")
        for name in extra:
            print(f"ONLY IN public: {name}")
        return 1 if drift or extra else 0
    print(f"synced {len(drift)} file(s)" if drift else "already in sync")
    return 0


if __name__ == "__main__":
    sys.exit(main("--check" in sys.argv))
