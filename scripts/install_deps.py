"""Install the pinned runtime dependencies from pyproject.toml (the single source of truth)."""
import subprocess
import sys
import tomllib
from pathlib import Path

deps = tomllib.loads((Path(__file__).resolve().parent.parent / "pyproject.toml").read_text())["project"]["dependencies"]
sys.exit(subprocess.call([sys.executable, "-m", "pip", "install", *deps]))
