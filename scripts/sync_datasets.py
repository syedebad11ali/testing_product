"""Publish sanitised listing datasets for the browser.

``backend/datasets/`` is the source of truth and still contains owner columns (the
server-side ownership check needs them). The browser only ever receives a copy with the
owner columns removed, generated here into ``public/assets/Dataset/``.

    python scripts/sync_datasets.py           # regenerate the public copies
    python scripts/sync_datasets.py --check   # exit 1 if they differ from sanitised(source)
"""
from __future__ import annotations

import csv
import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC, DST = ROOT / "backend" / "datasets", ROOT / "public" / "assets" / "Dataset"

#: Columns that identify people. Never published to the browser.
OWNER_COLUMNS = ("Owner ID", "Owner Name", "Property Owner", "Previous Owner")


def sanitise(raw: bytes) -> bytes:
    """Return the CSV bytes with every owner column removed (UTF-8, LF newlines, no BOM)."""
    text = raw.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text, newline=""))
    header = next(reader)
    keep = [i for i, name in enumerate(header) if name.strip() not in OWNER_COLUMNS]
    out = io.StringIO(newline="")
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow([header[i] for i in keep])
    for row in reader:
        if row:
            writer.writerow([row[i] if i < len(row) else "" for i in keep])
    return out.getvalue().encode("utf-8")


def main(check: bool) -> int:
    drift = []
    for src in sorted(SRC.glob("*.csv")):
        wanted, dst = sanitise(src.read_bytes()), DST / src.name
        if dst.exists() and dst.read_bytes() == wanted:
            continue
        drift.append(src.name)
        if not check:
            DST.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(wanted)
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
