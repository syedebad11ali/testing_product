"""Database layer: ``Database`` facade (SQLite locally, Postgres in production), migrations, seed."""
from backend.db.connection import Database, open_database

__all__ = ["Database", "open_database"]
