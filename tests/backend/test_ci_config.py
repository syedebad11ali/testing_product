"""Static checks of .github/ (workflow + Dependabot) that can be proven locally. They do NOT prove GitHub Actions passes:
the workflow has never run on GitHub. They catch typos that would only show up after a push (missing test file, unknown
npm script, wrong Python version, tools not declared in the dev extra)."""
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CI = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
DEPENDABOT = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
# Browser tests that are intentionally NOT in CI (none today). Anything else in tests/browser must be listed in the workflow.
NOT_IN_CI: set[str] = set()


class CiConfigTests(unittest.TestCase):
    def test_yaml_is_valid_when_a_parser_is_available(self):
        try:
            import yaml
        except ImportError:  # PyYAML is not a project dependency; the regex checks below still run
            return
        wf = yaml.safe_load(CI)
        self.assertEqual(set(wf["jobs"]), {"test", "browser", "audit"})
        self.assertEqual(wf["permissions"], {"contents": "read"}, "workflow must stay least-privilege")
        for name, job in wf["jobs"].items():
            self.assertIn("timeout-minutes", job, name)
            self.assertTrue(all("uses" in s or "run" in s for s in job["steps"]), name)
        self.assertEqual(yaml.safe_load(DEPENDABOT)["version"], 2)

    def test_python_version_matches_the_repo(self):
        wanted = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
        versions = set(re.findall(r'python-version:\s*"?([0-9.]+)"?', CI))
        self.assertEqual(versions, {wanted}, "CI must test the Python version the project pins")

    def test_every_npm_script_and_python_file_it_calls_exists(self):
        scripts = json.loads((ROOT / "package.json").read_text(encoding="utf-8"))["scripts"]
        for name in re.findall(r"npm run ([\w:-]+)", CI):
            self.assertIn(name, scripts)
        for path in re.findall(r"python (scripts/[\w./-]+\.py)", CI):
            self.assertTrue((ROOT / path).is_file(), path)

    def test_browser_job_runs_exactly_the_browser_tests_that_exist(self):
        listed = set(re.search(r"for t in ([\w ]+); do", CI).group(1).split())
        existing = {p.stem for p in (ROOT / "tests" / "browser").glob("*.py")}
        self.assertEqual(listed - existing, set(), "workflow lists a browser test that does not exist")
        self.assertEqual(existing - listed - NOT_IN_CI, set(), "browser test exists but CI never runs it")

    def test_audit_tools_are_declared_in_the_dev_extra(self):
        dev = " ".join(tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["optional-dependencies"]["dev"]).lower()
        for module, package in (("bandit", "bandit"), ("pip_audit", "pip-audit"), ("playwright", "playwright")):
            if f"python -m {module}" in CI or f"python -m {module} " in CI or module == "playwright":
                self.assertIn(package, dev, f"CI uses {module} but the dev extra does not install it")

    def test_actions_are_pinned_to_a_major_version_and_dependabot_keeps_them_fresh(self):
        uses = re.findall(r"uses:\s*([\w./-]+)@([\w.]+)", CI)
        self.assertTrue(uses)
        for action, ref in uses:
            self.assertRegex(ref, r"^v\d+$", f"{action} must be pinned to a tag, never a branch")
        for ecosystem in re.findall(r"package-ecosystem:\s*([\w-]+)", DEPENDABOT):
            self.assertIn(ecosystem, {"pip", "github-actions", "npm"})
        self.assertIn("github-actions", DEPENDABOT)
        self.assertEqual(len(re.findall(r"directory:\s*/\s*$", DEPENDABOT, re.M)), len(re.findall(r"package-ecosystem:", DEPENDABOT)))


if __name__ == "__main__":
    unittest.main()
