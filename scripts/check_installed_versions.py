"""Read-only: compare the packages installed in THIS interpreter with the declarations in pyproject.toml.

Installs nothing and changes nothing. Exact pins (==) must match exactly; ranges (>=,<) are reported as "range ok" or "OUT OF RANGE";
a missing package is reported as MISSING. Use it to decide which `PIN ME` entries can be pinned (only after the test suite passes).
Run:  python scripts/check_installed_versions.py [--dev]        (exit code 1 on any MISSING / mismatch / out-of-range)
"""
from __future__ import annotations

import importlib.metadata as md
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def parse(spec: str):
    m = re.match(r"^\s*([A-Za-z0-9_.\-]+)(?:\[[^\]]*\])?\s*(.*)$", spec.split(";")[0])
    return m.group(1), [c.strip() for c in m.group(2).split(",") if c.strip()]


_VERSION = re.compile(
    r"^\s*(?P<rel>\d+(?:\.\d+)*)(?:[-_.]?(?P<pre>a|b|c|rc|alpha|beta|pre|preview)[-_.]?(?P<pren>\d*))?"
    r"(?:[-_.]?(?:post|rev|r)[-_.]?(?P<post>\d*))?(?:[-_.]?dev[-_.]?(?P<dev>\d*))?(?:\+[A-Za-z0-9.]+)?\s*$", re.I)
_STAGE = {"dev": 0, "pre": 1, "final": 2, "post": 3}


def parse_version(v: str):
    """A small PEP 440 subset: (raw release tuple, sortable key) or None. Pre-releases and dev builds sort BEFORE the final
    release (so ``2.10.0rc1`` is not ``2.10.0``), post-releases after it, ``1.8`` equals ``1.8.0`` and a local ``+tag`` is ignored."""
    m = _VERSION.match(v or "")
    if not m:
        return None
    raw = tuple(int(x) for x in m.group("rel").split("."))
    trimmed = list(raw)
    while trimmed and trimmed[-1] == 0:
        trimmed.pop()
    if m.group("pre"):
        stage, n = _STAGE["pre"], int(m.group("pren") or 0)
    elif m.group("dev") is not None:
        stage, n = _STAGE["dev"], int(m.group("dev") or 0)
    elif m.group("post") is not None:
        stage, n = _STAGE["post"], int(m.group("post") or 0)
    else:
        stage, n = _STAGE["final"], 0
    return raw, (tuple(trimmed), stage, n)


def satisfies(version: str, clauses: list[str]) -> bool:
    """True only if EVERY clause holds. An unparseable installed version or clause is a failure, never a pass."""
    have = parse_version(version)
    if have is None:
        return False
    for c in clauses:
        m = re.match(r"^(==|>=|<=|<|>|~=|!=)\s*(.+)$", c)
        if not m:
            return False
        op, ref = m.groups()
        if op in ("==", "!=") and ref.endswith(".*"):  # prefix match, e.g. ==1.2.*
            prefix = parse_version(ref[:-2])
            hit = prefix is not None and have[0][: len(prefix[0])] == prefix[0]
            if hit != (op == "=="):
                return False
            continue
        want = parse_version(ref)
        if want is None:
            return False
        a, b = have[1], want[1]
        if op == "~=":  # compatible release: >= ref and the release prefix (all but the last part) is unchanged
            if len(want[0]) < 2 or not (a >= b and have[0][: len(want[0]) - 1] == want[0][:-1]):
                return False
            continue
        if not {"==": a == b, ">=": a >= b, "<=": a <= b, "<": a < b, ">": a > b, "!=": a != b}[op]:
            return False
    return True


def main(argv: list[str]) -> int:
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    specs = list(data["dependencies"]) + (list(data.get("optional-dependencies", {}).get("dev", [])) if "--dev" in argv else [])
    print(f"Python {sys.version.split()[0]} ({sys.executable})")
    bad = 0
    for spec in specs:
        name, clauses = parse(spec)
        try:
            have = md.version(name)
        except md.PackageNotFoundError:
            print(f"MISSING        {name} (declared {' '.join(clauses) or 'any'})"); bad += 1; continue
        exact = len(clauses) == 1 and clauses[0].startswith("==")
        ok = satisfies(have, clauses)
        label = ("exact match   " if ok else "MISMATCH      ") if exact else ("range ok      " if ok else "OUT OF RANGE  ")
        print(f"{label} {name} installed {have} (declared {' '.join(clauses)})"); bad += 0 if ok else 1
    print("RESULT:", "all declared packages present and in range" if not bad else f"{bad} problem(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
