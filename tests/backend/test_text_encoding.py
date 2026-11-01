"""Windows guard: on Windows, Python 3.12 reads/writes text with the locale encoding (cp1252) unless told otherwise, so a bare
``read_text()`` / ``open(path)`` can mis-decode this repo's UTF-8 files (they contain characters such as em dashes and emoji).
Every text-mode file call in backend/, tests/ and scripts/ must pass ``encoding=`` explicitly. The same applies to
``subprocess`` calls that decode child output with ``text=True`` / ``universal_newlines=True``."""
import ast
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOT_FILES = {"webbrowser", "os", "Image", "zipfile", "tarfile", "urllib", "io"}


def missing_encoding(path: Path):
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        name = getattr(func, "attr", getattr(func, "id", ""))
        kws = {k.arg for k in node.keywords}
        if name in ("read_text", "write_text") and "encoding" not in kws:
            yield node.lineno, name
        elif name in ("run", "check_output", "Popen", "check_call", "call") and "encoding" not in kws and any(
                k.arg in ("text", "universal_newlines") and isinstance(k.value, ast.Constant) and k.value.value is True for k in node.keywords):
            yield node.lineno, f"subprocess.{name}(text=True) without encoding"
        elif name == "open" and "encoding" not in kws and (isinstance(func, ast.Name) or getattr(func.value, "id", "") not in NOT_FILES):
            mode = node.args[1].value if len(node.args) >= 2 and isinstance(node.args[1], ast.Constant) else None
            for k in node.keywords:
                if k.arg == "mode" and isinstance(k.value, ast.Constant):
                    mode = k.value.value
            if "b" not in str(mode or ""):
                yield node.lineno, "open"


class TextEncoding(unittest.TestCase):
    def test_every_text_file_call_names_its_encoding(self):
        bad = [f"{p.relative_to(ROOT).as_posix()}:{ln} {name}" for d in ("backend", "tests", "scripts") for p in (ROOT / d).rglob("*.py")
               if p.resolve() != Path(__file__).resolve() for ln, name in missing_encoding(p)]
        self.assertEqual(bad, [], "add encoding='utf-8' (Windows defaults to cp1252)")


if __name__ == "__main__":
    unittest.main()
