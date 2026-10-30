"""Install the pinned dependencies from pyproject.toml (the single source of truth).

Usage:
    python scripts/install_deps.py          # production packages only (what Vercel installs)
    python scripts/install_deps.py --dev    # production + dev tools (ruff, bandit, pip-audit, playwright)
    python scripts/install_deps.py --extra argon2   # also install an optional extra
"""
import argparse
import subprocess
import sys
import tomllib
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dev", action="store_true", help="also install [project.optional-dependencies].dev")
    parser.add_argument("--extra", action="append", default=[], help="also install this optional extra (repeatable)")
    args = parser.parse_args()

    project = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    packages = list(project["dependencies"])
    extras = project.get("optional-dependencies", {})
    wanted = (["dev"] if args.dev else []) + args.extra
    for name in wanted:
        if name not in extras:
            print(f"Unknown extra '{name}'. Available: {', '.join(sorted(extras)) or 'none'}", file=sys.stderr)
            return 2
        packages += extras[name]
    return subprocess.call([sys.executable, "-m", "pip", "install", *packages])


if __name__ == "__main__":
    sys.exit(main())
