"""Static checks that keep SQLite-tested SQL safe for the PostgreSQL adapter (these are NOT a substitute for running the database
modules against PostgreSQL). ``PostgresDatabase`` rewrites ``?`` to ``%s``, so SQL text must not contain a literal ``%`` or a quoted
``?`` (values and LIKE patterns go in parameters), and SQLite-only syntax must not creep into shared SQL or migrations."""
import ast
import re
import unittest
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2] / "backend"
SQL_START = re.compile(r"^\s*(SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|WITH|DROP)\b", re.I)
SQLITE_ONLY = re.compile(r"\b(INSERT\s+OR\s+(IGNORE|REPLACE)|AUTOINCREMENT|PRAGMA|GLOB|IFNULL|STRFTIME|DATETIME\s*\(|ROWID|WITHOUT\s+ROWID)\b", re.I)


def sql_strings():
    for path in BACKEND.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            text = None
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                text = node.value
            elif isinstance(node, ast.JoinedStr):
                text = "".join(p.value for p in node.values if isinstance(p, ast.Constant))
            if text and SQL_START.match(text):
                yield f"{path.relative_to(BACKEND)}:{node.lineno}", text
    for path in (BACKEND / "db" / "migrations").glob("*.sql"):
        yield path.name, path.read_text(encoding="utf-8")


class SqlPortability(unittest.TestCase):
    def test_there_is_sql_to_check(self):
        self.assertGreater(sum(1 for _ in sql_strings()), 50)

    def test_no_literal_percent_or_quoted_question_mark(self):
        bad = [w for w, t in sql_strings() if "%" in t or any("?" in lit for lit in re.findall(r"'[^']*'", t))]
        self.assertEqual(bad, [], "psycopg would mis-handle these: pass patterns/values as parameters")

    def test_no_sqlite_only_syntax(self):
        bad = [(w, m.group(0)) for w, t in sql_strings() for m in [SQLITE_ONLY.search(t)] if m]
        self.assertEqual(bad, [])


if __name__ == "__main__":
    unittest.main()
