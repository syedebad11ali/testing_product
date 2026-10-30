"""Line-ending policy guard. Without .gitattributes, a Windows clone (Git for Windows defaults to core.autocrlf=true) rewrites
text files to CRLF, which breaks anything that hashes file bytes (vendored libraries pinned with SRI, fixture/dataset checks).
The test is self-maintaining: every binary file type found in the repository must be declared binary (or live under a -text path)."""
import os
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SKIP = {"node_modules", ".git", ".venv", ".venv312", "__pycache__", ".local"}


def rules():
    out = []
    for line in (ROOT / ".gitattributes").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            pattern, *attrs = line.split()
            out.append((pattern, set(attrs)))
    return out


def binary_extensions():
    found = {}
    for base, dirs, files in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP]
        for name in files:
            path = Path(base) / name
            if path.suffix and b"\x00" in path.read_bytes()[:4096]:
                found.setdefault(path.suffix.lower(), path)
    return found


class GitAttributesTests(unittest.TestCase):
    def test_text_is_normalised_to_lf_for_everyone(self):
        self.assertIn(("*", {"text=auto", "eol=lf"}), rules())

    def test_vendored_files_are_never_rewritten(self):
        self.assertIn(("public/assets/vendor/**", {"-text"}), rules())

    def test_every_binary_type_in_the_repo_is_declared_binary(self):
        declared = {p[1:].lower() for p, attrs in rules() if p.startswith("*.") and ({"binary"} <= attrs or "-text" in attrs)}
        missing = {ext: str(p.relative_to(ROOT)) for ext, p in binary_extensions().items() if ext not in declared}
        self.assertEqual(missing, {}, "add '*<ext> binary' to .gitattributes")

    def test_gitattributes_file_exists(self):
        self.assertTrue((ROOT / ".gitattributes").is_file())


if __name__ == "__main__":
    unittest.main()
