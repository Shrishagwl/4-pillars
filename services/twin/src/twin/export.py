"""Write runs to files (#32), keeping what the engine may see apart from the truth.

    runs/
      twin-42.json                    the map: suburbs, transformers, meters
      power-outage/seed-003/
        loc_reports.jsonl             the event stream, exactly as Telstra would send it
        outages.jsonl                 what Network Availability lists, and from when
        heartbeats.jsonl              (only with --heartbeats: large)
        answer_key.json               the truth: cause, target, times, silenced meters
        background.json               the truth about normal-day dropouts (not incidents)
        run.json                      what produced this folder

The answer key never goes in the same file as the events, so nothing that reads the event
stream (the engine, a baseline, the dashboard) can accidentally see the answer.

The eval (#27) can call `run_scenario` directly and skip the files; these are for replaying a
run into telstra-fake, loading the dashboard, and looking at a run by hand.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime
from pathlib import Path

from .grid import Twin
from .run import RunResult


def _iso(when: datetime | None) -> str | None:
    return None if when is None else when.isoformat().replace("+00:00", "Z")


def _write_jsonl(path: Path, rows: Iterable[dict[str, object]]) -> None:
    # JSON Lines: one JSON object per line. Easy to stream, append and read a line at a time.
    with path.open("w", encoding="utf-8", newline="\n") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")


def _write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8", newline="\n")


def write_twin(twin: Twin, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    path = out / f"twin-{twin.seed}.json"
    _write_json(
        path,
        {
            "seed": twin.seed,
            "suburbs": [asdict(s) for s in twin.suburbs],
            "transformers": [asdict(t) for t in twin.transformers],
            "meters": [asdict(m) for m in twin.meters],
        },
    )
    return path


def write_run(result: RunResult, out: Path, heartbeats: bool = False) -> Path:
    folder = out / result.scenario / f"seed-{result.seed:03d}"
    folder.mkdir(parents=True, exist_ok=True)

    _write_jsonl(folder / "loc_reports.jsonl", (r.to_telstra() for r in result.loc_reports))
    _write_jsonl(
        folder / "outages.jsonl",
        (
            {
                "suburb": o.suburb,
                "postcode": o.postcode,
                "state": "VIC",
                "startedAt": _iso(o.started_at),
                "listedAt": _iso(o.listed_at),
                "restoredAt": _iso(o.restored_at),
            }
            for o in result.outages
        ),
    )
    hb_path = folder / "heartbeats.jsonl"
    if heartbeats:
        _write_jsonl(
            hb_path,
            ({"msisdn": b.msisdn, "time": _iso(b.time)} for b in result.heartbeats),
        )
    elif hb_path.exists():
        hb_path.unlink()  # don't leave a stale file from an earlier --heartbeats run

    _write_json(
        folder / "answer_key.json",
        [
            {
                "incidentId": i.incident_id,
                "cause": i.cause.value,
                "target": i.target,
                "startedAt": _iso(i.started_at),
                "restoredAt": _iso(i.restored_at),
                "meterIds": list(i.meter_ids),
            }
            for i in result.answer_key
        ],
    )
    _write_json(
        folder / "background.json",
        [
            {
                "meterId": d.meter_id,
                "msisdn": d.msisdn,
                "droppedAt": _iso(d.dropped_at),
                "backAt": _iso(d.back_at),
                "reported": d.reported,
            }
            for d in result.background
        ],
    )
    _write_json(
        folder / "run.json",
        {
            "scenario": result.scenario,
            "seed": result.seed,
            "twinSeed": result.twin_seed,
            "locReports": len(result.loc_reports),
            "outages": len(result.outages),
            "heartbeats": len(result.heartbeats),
            "incidents": len(result.answer_key),
            "backgroundDropouts": len(result.background),
        },
    )
    return folder
