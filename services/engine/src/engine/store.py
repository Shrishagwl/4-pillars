"""Reads and writes for the engine schema: events, incidents and verdicts."""

import json
from datetime import datetime

import psycopg
from psycopg.types.json import Jsonb

from .contracts import MeterSilentEvent, Verdict, reason_group


class EngineStore:
    def __init__(self, conn: psycopg.Connection) -> None:
        self._conn = conn
        conn.autocommit = True

    def add_events(self, events: list[MeterSilentEvent]) -> list[MeterSilentEvent]:
        """Store events; returns the ones that were new (repeats are dropped by the database)."""
        new = []
        for e in events:
            row = self._conn.execute(
                """INSERT INTO engine.events
                       (event_id, subscription_id, msisdn, reason_code, event_time, received_at)
                   VALUES (%s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING RETURNING event_id""",
                (e.eventId, e.subscriptionId, e.msisdn, e.reasonCode, e.eventTime, e.receivedAt),
            ).fetchone()
            if row:
                new.append(e)
        return new

    def events_since(self, since: datetime) -> list[MeterSilentEvent]:
        rows = self._conn.execute(
            """SELECT event_id, subscription_id, msisdn, reason_code, event_time, received_at
               FROM engine.events WHERE event_time >= %s ORDER BY event_time""",
            (since,),
        ).fetchall()
        return [
            MeterSilentEvent(
                eventId=str(r[0]),
                subscriptionId=r[1],
                msisdn=r[2],
                reasonCode=r[3],
                reasonGroup=reason_group(r[3]),
                eventTime=r[4],
                receivedAt=r[5],
            )
            for r in rows
        ]

    def open_incidents(self) -> dict[str, frozenset[str]]:
        """incident_id -> meter ids, for incidents not closed yet."""
        rows = self._conn.execute(
            "SELECT incident_id, meter_ids FROM engine.incidents WHERE closed_at IS NULL"
        ).fetchall()
        return {r[0]: frozenset(r[1]) for r in rows}

    def highest_incident_number(self) -> int:
        row = self._conn.execute(
            """SELECT max(substring(incident_id FROM '[0-9]+$')::int) FROM engine.incidents"""
        ).fetchone()
        return row[0] or 0

    def save_incident(
        self,
        incident_id: str,
        opened_at: datetime,
        updated_at: datetime,
        closed_at: datetime | None,
        meter_ids: list[str],
        transformer_ids: list[str],
        suburbs: list[str],
    ) -> None:
        self._conn.execute(
            """INSERT INTO engine.incidents
                   (incident_id, opened_at, updated_at, closed_at,
                    meter_ids, transformer_ids, suburbs)
               VALUES (%s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (incident_id) DO UPDATE SET
                   updated_at = EXCLUDED.updated_at, closed_at = EXCLUDED.closed_at,
                   meter_ids = EXCLUDED.meter_ids, transformer_ids = EXCLUDED.transformer_ids,
                   suburbs = EXCLUDED.suburbs""",
            (incident_id, opened_at, updated_at, closed_at, meter_ids, transformer_ids, suburbs),
        )

    def close_incident(self, incident_id: str, closed_at: datetime) -> None:
        self._conn.execute(
            "UPDATE engine.incidents SET closed_at = %s, updated_at = %s WHERE incident_id = %s",
            (closed_at, closed_at, incident_id),
        )

    def add_verdict(self, v: Verdict) -> None:
        self._conn.execute(
            """INSERT INTO engine.verdicts (incident_id, meter_count, cause, confidence,
                   probabilities, action, evidence, summary, notice, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
            (
                v.incidentId,
                v.meterCount,
                v.cause.value,
                v.confidence,
                Jsonb(
                    {k.value if hasattr(k, "value") else k: p for k, p in v.probabilities.items()}
                ),
                v.action.value,
                Jsonb(v.evidence),
                v.summary,
                v.notice,
                v.updatedAt,
            ),
        )

    def latest_verdicts(self, include_closed_since: datetime | None = None) -> list[dict]:
        """The newest verdict of every open incident (and of incidents closed since a time),
        joined with the incident row: what the dashboard shows."""
        rows = self._conn.execute(
            """SELECT DISTINCT ON (i.incident_id)
                   i.incident_id, i.opened_at, i.updated_at, i.closed_at, i.meter_ids,
                   i.transformer_ids, i.suburbs, v.meter_count, v.cause, v.confidence,
                   v.probabilities, v.action, v.evidence, v.summary, v.notice, v.created_at
               FROM engine.incidents i JOIN engine.verdicts v USING (incident_id)
               WHERE i.closed_at IS NULL OR i.closed_at >= %s
               ORDER BY i.incident_id, v.id DESC""",
            (include_closed_since or datetime.max.replace(tzinfo=None),),
        ).fetchall()
        keys = [
            "incidentId", "openedAt", "incidentUpdatedAt", "closedAt", "meterIds",
            "transformerIds", "suburbs", "meterCount", "cause", "confidence", "probabilities",
            "action", "evidence", "summary", "notice", "updatedAt",
        ]  # fmt: skip
        out = []
        for r in rows:
            item = dict(zip(keys, r, strict=True))
            for k in ("openedAt", "incidentUpdatedAt", "closedAt", "updatedAt"):
                item[k] = item[k].isoformat() if item[k] else None
            if isinstance(item["probabilities"], str):
                item["probabilities"] = json.loads(item["probabilities"])
            out.append(item)
        return out
