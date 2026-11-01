"""Keeps pyproject.toml honest: every third-party import is declared, every declared package is used.

Some declared packages are not imported yet because the feature that needs them is still to be built
(see PLANNED below). The list is explicit so the gap is visible, and the test fails as soon as a
planned package starts being imported (remove it from PLANNED then) so the list cannot go stale.
"""
import ast
import re
import sys
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

# import name -> distribution name (only where they differ)
DIST_FOR_IMPORT = {
    "dotenv": "python-dotenv",
    "google": None,  # namespace package, resolved from the full dotted path below
    "sklearn": "scikit-learn",
    "agents": "openai-agents",
}
DIST_FOR_DOTTED = {"google.genai": "google-genai", "google.auth": "google-auth", "google.oauth2": "google-auth"}

# Imported only inside try/except or lazily as an optional model backend; not a declared dependency.
OPTIONAL_IMPORTS = {"lightgbm", "xgboost"}

# Declared for a feature that is not implemented yet (see HANDOFF.md / KPT_upgrade_prompt_v2.md).
PLANNED = {
    "requests": "Part 1 (transport for google-auth)",
    # Transitive / runtime-only: used by pandas/sklearn at load time, never imported by our code.
    "threadpoolctl": "pulled in by scikit-learn; pinned to match the serialised model",
    "scipy": "pulled in by scikit-learn; pinned to match the serialised model",
}


def _norm(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _declared() -> set[str]:
    deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
    return {_norm(re.split(r"[<>=!~\[ ;]", d, maxsplit=1)[0]) for d in deps}


def _imports() -> set[str]:
    stdlib = set(sys.stdlib_module_names)
    found: set[str] = set()
    for folder in ("backend", "scripts"):
        for path in (ROOT / folder).rglob("*.py"):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                names: list[str] = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    # `from google import genai` -> google.genai (namespace package)
                    names = [f"{node.module}.{a.name}" for a in node.names] if node.module == "google" else [node.module]
                for dotted in names:
                    top = dotted.split(".")[0]
                    if top in stdlib or top in {"backend", "scripts", "__future__"}:
                        continue
                    if top == "google":
                        key = ".".join(dotted.split(".")[:2])
                        found.add(DIST_FOR_DOTTED.get(key, key))
                    else:
                        found.add(_norm(DIST_FOR_IMPORT.get(top) or top))
    return found


class DependencyTests(unittest.TestCase):
    def test_every_import_is_declared(self):
        missing = sorted(i for i in _imports() - _declared() if i not in OPTIONAL_IMPORTS)
        # Flask pulls in werkzeug; it is part of the Flask pin, not a separate dependency.
        missing = [m for m in missing if m != "werkzeug"]
        self.assertEqual(missing, [], f"imported but not declared in pyproject.toml: {missing}")

    def test_every_declared_package_is_used_or_planned(self):
        unused = sorted(d for d in _declared() - _imports() if d not in PLANNED)
        self.assertEqual(unused, [], f"declared but never imported (add a PLANNED reason or remove): {unused}")

    def test_planned_list_does_not_go_stale(self):
        stale = sorted(d for d in PLANNED if d in _imports() and PLANNED[d] is not None)
        self.assertEqual(stale, [], f"now imported, remove from PLANNED: {stale}")

    def test_model_locked_pins_are_exact(self):
        deps = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["dependencies"]
        for name in ("scikit-learn", "numpy", "pandas", "scipy", "joblib", "threadpoolctl"):
            self.assertTrue(any(d.startswith(f"{name}==") for d in deps), f"{name} must stay pinned with ==")


if __name__ == "__main__":
    unittest.main()
