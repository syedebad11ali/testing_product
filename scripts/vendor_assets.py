"""Owner-run helper to self-host third-party browser assets (Tesseract.js, PDF.js, ...) and verify them later.

Why a script: the build sandbox cannot reach any CDN, so nothing here was downloaded or hashed by the assistant, and no
hash is invented. YOU run it on a machine with network access; it computes the hashes from the bytes it downloaded.

    cp scripts/vendor_assets.example.json scripts/vendor_assets.json     # edit: add the Tesseract entries after choosing exact versions
    python scripts/vendor_assets.py fetch  --config scripts/vendor_assets.json     # download over https, write files + MANIFEST.json
    python scripts/vendor_assets.py verify --config scripts/vendor_assets.json     # offline: re-hash the files and compare to MANIFEST.json

Config: {"dest": "public/assets/vendor", "assets": [{"name": "...", "version": "x.y.z", "url": "https://...", "path": "pdfjs/pdf.min.js"}]}
`fetch` refuses non-https URLs, URLs that look unpinned (``@5``, ``@latest``) and destination paths outside ``dest``. The manifest
records sha256 and sha384 (the latter is what Subresource Integrity uses: ``integrity="sha384-<base64>"``) per file. Review the
files and licences yourself before committing them. Only after that, point the HTML/JS at the local copies and tighten the CSP.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MAX_BYTES = 50 * 1024 * 1024   # largest plausible asset (language data / wasm core); anything bigger is refused
PINNED = re.compile(r"@\d+\.\d+\.\d+(?:[/\-]|$)|/\d+\.\d+\.\d+/")   # an exact x.y.z version appears in the URL


def digests(data: bytes) -> dict:
    return {"sha256": hashlib.sha256(data).hexdigest(), "sri": "sha384-" + base64.b64encode(hashlib.sha384(data).digest()).decode(), "bytes": len(data)}


def _safe_dest(root: Path, rel: str) -> Path:
    target = (root / rel).resolve()
    if root.resolve() not in target.parents:
        raise ValueError(f"path escapes the vendor directory: {rel}")
    return target


def check_entry(entry: dict) -> None:
    url = entry.get("url", "")
    if not url.startswith("https://"):
        raise ValueError(f"{entry.get('name')}: only https URLs are allowed")
    if not PINNED.search(url):
        raise ValueError(f"{entry.get('name')}: URL is not pinned to an exact x.y.z version: {url}")
    version = entry.get("version") or ""
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or not (f"@{version}/" in url or f"/{version}/" in url or url.endswith(f"@{version}")):
        raise ValueError(f"{entry.get('name')}: 'version' must be an exact x.y.z that is the version segment of the URL (5.1.1 must not match 5.1.10)")


def load_config(path: Path) -> tuple[Path, list[dict]]:
    cfg = json.loads(path.read_text(encoding="utf-8"))
    return ROOT / cfg["dest"], cfg["assets"]


def fetch(root: Path, assets: list[dict], opener=urllib.request.urlopen) -> dict:
    manifest, seen = {}, set()
    for e in assets:   # validate EVERYTHING before the first download, so a bad entry never leaves a half-written vendor directory
        check_entry(e)
        _safe_dest(root, e["path"])
        if e["path"] in seen:
            raise ValueError(f"duplicate path in config: {e['path']}")
        seen.add(e["path"])
    for e in assets:
        dest = _safe_dest(root, e["path"])
        with opener(e["url"], timeout=60) as resp:  # noqa: S310 - https only, checked above
            final = getattr(resp, "geturl", lambda: e["url"])()
            if not str(final).startswith("https://"):
                raise ValueError(f"{e['name']}: redirected to a non-https URL ({final}); refusing")
            data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError(f"{e['name']}: larger than {MAX_BYTES} bytes; refusing")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        manifest[e["path"]] = {"name": e["name"], "version": e["version"], "url": e["url"], **digests(data)}
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return manifest


def verify(root: Path, expected: list[str] | None = None) -> list[str]:
    """Problems found (empty list = every file matches the manifest). Works offline.
    ``expected`` (the paths in the config) also reports assets the config lists but the manifest lacks, so dropping an entry is not silent."""
    mf = root / "MANIFEST.json"
    if not mf.exists():
        return [f"{mf} is missing: run `fetch` first"]
    recorded = json.loads(mf.read_text(encoding="utf-8"))
    problems = [f"not in manifest: {rel}" for rel in (expected or []) if rel not in recorded]
    for rel, meta in recorded.items():
        try:
            f = _safe_dest(root, rel)
        except ValueError as exc:
            problems.append(str(exc)); continue
        if not f.exists():
            problems.append(f"missing file: {rel}"); continue
        if digests(f.read_bytes())["sha256"] != meta["sha256"]:
            problems.append(f"hash mismatch: {rel}")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=("fetch", "verify"))
    ap.add_argument("--config", default=str(ROOT / "scripts" / "vendor_assets.json"))
    args = ap.parse_args(argv)
    root, assets = load_config(Path(args.config))
    if args.command == "fetch":
        m = fetch(root, assets)
        print(f"fetched {len(m)} file(s); manifest written to {root / 'MANIFEST.json'}")
        return 0
    problems = verify(root, [a["path"] for a in assets])
    print("\n".join(problems) if problems else "all vendored files match the manifest")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
