"""scripts/vendor_assets.py: URL/path safety and manifest verification, with a fake opener (no network)."""
import importlib.util
import io
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("vendor_assets", ROOT / "scripts" / "vendor_assets.py")
va = importlib.util.module_from_spec(spec)
spec.loader.exec_module(va)


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def opener(url, timeout=0):
    return FakeResp(b"console.log('" + url.encode() + b"')")


GOOD = {"name": "lib", "version": "1.2.3", "url": "https://cdn.example.com/npm/lib@1.2.3/dist/lib.min.js", "path": "lib/lib.min.js"}


class RedirectResp(FakeResp):
    def geturl(self):
        return "http://evil.example/x.js"


class VendorTests(unittest.TestCase):
    def test_rejects_unpinned_non_https_and_mismatched_versions(self):
        for bad in ({**GOOD, "url": "https://cdn.example.com/npm/lib@5/dist/lib.js"}, {**GOOD, "url": "https://cdn.example.com/npm/lib@latest/x.js"},
                    {**GOOD, "url": "http://cdn.example.com/npm/lib@1.2.3/x.js"}, {**GOOD, "version": "9.9.9"}, {**GOOD, "version": ""},
                    {**GOOD, "version": "1.2", "url": "https://cdn.example.com/npm/lib@1.2/x.js"},
                    {**GOOD, "version": "1.2.3", "url": "https://cdn.example.com/npm/lib@1.2.30/x.js"}):
            with self.assertRaises(ValueError, msg=bad["url"]):
                va.check_entry(bad)
        va.check_entry(GOOD)

    def test_rejects_paths_outside_the_vendor_directory(self):
        with tempfile.TemporaryDirectory() as d:
            for rel in ("../evil.js", "/etc/passwd", "a/../../evil.js"):
                with self.assertRaises(ValueError, msg=rel):
                    va._safe_dest(Path(d), rel)

    def test_fetch_writes_manifest_and_verify_detects_tampering(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            m = va.fetch(root, [GOOD], opener=opener)
            meta = m["lib/lib.min.js"]
            self.assertTrue(meta["sri"].startswith("sha384-") and len(meta["sha256"]) == 64)
            self.assertEqual(va.verify(root), [])
            (root / "lib" / "lib.min.js").write_bytes(b"tampered")
            self.assertEqual(va.verify(root), ["hash mismatch: lib/lib.min.js"])
            (root / "lib" / "lib.min.js").unlink()
            self.assertEqual(va.verify(root), ["missing file: lib/lib.min.js"])

    def test_verify_without_manifest_and_with_escaping_manifest_entry(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            self.assertIn("missing", va.verify(root)[0])
            (root / "MANIFEST.json").write_text(json.dumps({"../x.js": {"sha256": "0" * 64}}), encoding="utf-8")
            self.assertIn("escapes", va.verify(root)[0])

    def test_example_config_is_valid_and_pinned(self):
        cfg = json.loads((ROOT / "scripts" / "vendor_assets.example.json").read_text(encoding="utf-8"))
        for entry in cfg["assets"]:
            va.check_entry(entry)


    def test_a_bad_entry_blocks_all_downloads_and_writes_nothing(self):
        calls = []
        def counting(url, timeout=0):
            calls.append(url); return opener(url)
        with tempfile.TemporaryDirectory() as d:
            bad = {**GOOD, "name": "bad", "path": "../escape.js"}
            for assets in ([GOOD, bad], [GOOD, {**GOOD, "version": "9.9.9"}], [GOOD, dict(GOOD)]):
                with self.assertRaises(ValueError):
                    va.fetch(Path(d), assets, opener=counting)
            self.assertEqual(calls, [])
            self.assertEqual(list(Path(d).iterdir()), [])

    def test_downgrade_redirects_and_oversized_downloads_are_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                va.fetch(Path(d), [GOOD], opener=lambda url, timeout=0: RedirectResp(b"x"))
            old, va.MAX_BYTES = va.MAX_BYTES, 10
            try:
                with self.assertRaises(ValueError):
                    va.fetch(Path(d), [GOOD], opener=lambda url, timeout=0: FakeResp(b"x" * 11))
            finally:
                va.MAX_BYTES = old

    def test_verify_reports_assets_the_config_lists_but_the_manifest_lacks(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            va.fetch(root, [GOOD], opener=opener)
            self.assertEqual(va.verify(root, ["lib/lib.min.js"]), [])
            self.assertEqual(va.verify(root, ["lib/lib.min.js", "tess/core.wasm"]), ["not in manifest: tess/core.wasm"])


if __name__ == "__main__":
    unittest.main()
