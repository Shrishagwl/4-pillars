"""Needs a real Postgres. CI provides one; locally: docker compose up postgres, then
TEST_DATABASE_URL=postgresql://pillars:pillars-local@localhost:5432/pillars uv run pytest"""

import os
import threading

import psycopg
import pytest

from engine import db

URL = os.environ.get("TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not URL, reason="TEST_DATABASE_URL not set")


@pytest.fixture
def fresh():
    with psycopg.connect(URL, autocommit=True) as conn:
        conn.execute("DROP SCHEMA IF EXISTS engine CASCADE")
        yield conn


def tables(conn) -> list[str]:
    rows = conn.execute(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'engine' ORDER BY 1"
    )
    return [r[0] for r in rows]


def test_migrations_are_found_in_order():
    versions = [v for v, _, _ in db.migrations()]
    assert versions == sorted(versions) and versions[0] == 1


def test_creates_the_tables_then_does_nothing_the_second_time(fresh):
    assert db.migrate(fresh) == [v for v, _, _ in db.migrations()]
    assert {"incidents", "verdicts", "schema_migrations"} <= set(tables(fresh))
    assert db.migrate(fresh) == []


def test_instances_starting_together_take_turns(fresh):
    results: list[list[int]] = []

    def run():
        with psycopg.connect(URL) as conn:
            results.append(db.migrate(conn))

    threads = [threading.Thread(target=run) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(v for r in results for v in r) == [v for v, _, _ in db.migrations()]


def test_a_broken_migration_is_rolled_back(fresh):
    db.migrate(fresh)
    broken = [*db.migrations(), (999, "broken", "CREATE TABLE engine.x (id int); SELECT nope;")]
    with pytest.raises(RuntimeError, match="migration 999"):
        db.migrate(fresh, broken)
    assert "x" not in tables(fresh)


def test_verdicts_reject_an_unknown_cause(fresh):
    db.migrate(fresh)
    fresh.execute(
        "INSERT INTO engine.incidents VALUES ('inc-1', now(), now(), NULL, '{M-1}', '{T-1}', '{A}')"
    )
    with pytest.raises(psycopg.errors.CheckViolation):
        fresh.execute(
            """INSERT INTO engine.verdicts
               (incident_id, meter_count, cause, confidence, probabilities, action, evidence)
               VALUES ('inc-1', 1, 'ALIENS', 0.9, '{}', 'MANUAL_REVIEW', '[]')"""
        )
