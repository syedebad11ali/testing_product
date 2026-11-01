"""scripts/check_installed_versions.py must compare versions the way pip does, or its verdicts cannot be used to decide pins."""
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("check_installed_versions", ROOT / "scripts" / "check_installed_versions.py")
civ = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(civ)


class Comparison(unittest.TestCase):
    def test_exact_pin_requires_the_final_release(self):
        self.assertTrue(civ.satisfies("2.10.0", ["==2.10.0"]))
        for installed in ("2.10.0rc1", "2.10.0.dev3", "2.10.0a1", "2.10.0b2", "2.10.1", "2.10.0.post1"):
            self.assertFalse(civ.satisfies(installed, ["==2.10.0"]), installed)

    def test_trailing_zeros_and_local_tags_do_not_matter(self):
        self.assertTrue(civ.satisfies("1.8", ["==1.8.0"]))
        self.assertTrue(civ.satisfies("1.8.0.0", ["==1.8"]))
        self.assertTrue(civ.satisfies("2.1.0+cpu", ["==2.1.0"]))

    def test_every_version_part_counts_not_just_the_first_four(self):
        self.assertFalse(civ.satisfies("1.2.3.4.5", ["==1.2.3.4.6"]))
        self.assertTrue(civ.satisfies("1.2.3.4.5", ["==1.2.3.4.5"]))

    def test_ranges(self):
        self.assertTrue(civ.satisfies("46.0.6", [">=46", "<47"]))
        self.assertFalse(civ.satisfies("47.0.0", [">=46", "<47"]))
        self.assertFalse(civ.satisfies("45.9", [">=46"]))
        self.assertFalse(civ.satisfies("47.0.0rc1", [">=47"]))  # a pre-release is older than the release it precedes
        self.assertTrue(civ.satisfies("3.2.1", [">=3.2", "<4"]))

    def test_compatible_release_operator(self):
        self.assertTrue(civ.satisfies("1.9.2", ["~=1.8"]))
        self.assertFalse(civ.satisfies("2.0.0", ["~=1.8"]))
        self.assertFalse(civ.satisfies("1.7.9", ["~=1.8"]))
        self.assertTrue(civ.satisfies("1.4.5", ["~=1.4.2"]))
        self.assertFalse(civ.satisfies("1.5.0", ["~=1.4.2"]))

    def test_wildcards_and_exclusions(self):
        self.assertTrue(civ.satisfies("1.2.9", ["==1.2.*"]))
        self.assertFalse(civ.satisfies("1.3.0", ["==1.2.*"]))
        self.assertTrue(civ.satisfies("1.3.0", ["!=1.2.*"]))
        self.assertFalse(civ.satisfies("1.2.1", ["!=1.2.1"]))

    def test_unparseable_input_fails_instead_of_passing(self):
        self.assertFalse(civ.satisfies("garbage", ["==1"]))
        self.assertFalse(civ.satisfies("", [">=1"]))
        self.assertFalse(civ.satisfies("1.0", ["=>1"]))
        self.assertFalse(civ.satisfies("1.0", [">=banana"]))

    def test_the_script_only_reads(self):
        src = (ROOT / "scripts" / "check_installed_versions.py").read_text(encoding="utf-8")
        for needle in ("subprocess", "os.system", "pip install", "write_text", "open("):
            self.assertNotIn(needle, src, needle)


if __name__ == "__main__":
    unittest.main()
