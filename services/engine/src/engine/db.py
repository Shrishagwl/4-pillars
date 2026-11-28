"""The engine's database: schema migrations, run on every start.

Migrations are the numbered .sql files in engine/migrations/. Each runs once per database,
inside a transaction, and is recorded in engine.schema_migrations. Never edit one that has been
merged; add a new file instead.
"""

import logging
from importlib import resources

import psycopg

log = logging.getLogger(__name__)

# Any fixed number; the same for every engine instance, different from ingest-api's.
LOCK_ID = 4_084


def migrations() -> list[tuple[int, str, str]]:
    """(version, name, sql) for every file in engine/migrations, oldest first."""
    found = []
    for item in resources.files("engine.migrations").iterdir():
        if item.name.endswith(".sql"):
            number, _, rest = item.name.partition("_")
            found.append((int(number), rest.removesuffix(".sql"), item.read_text("utf-8")))
    return sorted(found)


def migrate(
    conn: psycopg.Connection, pending: list[tuple[int, str, str]] | None = None
) -> list[int]:
    """Bring the engine schema up to date. Safe to run from several instances at once.
    Returns the versions applied this time."""
    pending = migrations() if pending is None else pending
    conn.autocommit = True
    conn.execute("SELECT pg_advisory_lock(%s)", (LOCK_ID,))
    try:
        # On Cloud SQL the database owner creates the schema (infra/gcp/database.sql) and this
        # user may not be allowed to, so only create it when it is missing.
        if not conn.execute("SELECT 1 FROM pg_namespace WHERE nspname = 'engine'").fetchone():
            conn.execute("CREATE SCHEMA engine")
        conn.execute(
            """CREATE TABLE IF NOT EXISTS engine.schema_migrations (
                   version integer PRIMARY KEY,
                   name text NOT NULL,
                   applied_at timestamptz NOT NULL DEFAULT now())"""
        )
        done = {row[0] for row in conn.execute("SELECT version FROM engine.schema_migrations")}
        applied = []
        for version, name, sql in sorted(pending):
            if version in done:
                continue
            try:
                with conn.transaction():
                    conn.execute(sql)
                    conn.execute(
                        "INSERT INTO engine.schema_migrations (version, name) VALUES (%s, %s)",
                        (version, name),
                    )
            except psycopg.Error as err:
                raise RuntimeError(f"migration {version} ({name}) failed: {err}") from err
            applied.append(version)
        return applied
    finally:
        conn.execute("SELECT pg_advisory_unlock(%s)", (LOCK_ID,))


def connect(database_url: str) -> psycopg.Connection:
    # The URL may carry `options=-csearch_path=engine`; we qualify table names anyway.
    return psycopg.connect(database_url)
