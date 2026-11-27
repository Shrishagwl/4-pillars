"""The experiments that go beyond the main results table.

  ablations         take one clue away from the v2 model at a time and re-measure. A big drop
                    means that clue matters; no drop means we could do without it.
  API improvements  switch on the two changes we propose to Telstra (exact outage areas,
                    a restore event) and re-measure. Shows what the changes would be worth.
  sensitivity       change one twin setting at a time (last-gasp rate, detection delay,
                    Outage API lag, noise) and re-measure. Shows where the engine breaks.

Each function returns plain rows (a list of dicts) that `write_rows` saves as CSV for charts.
"""

import csv
from collections.abc import Iterable
from dataclasses import replace
from pathlib import Path

from engine.bayes import FEATURES

from .metrics import summarise_by_system
from .runner import DEFAULT_SEEDS, run_batch
from .sim import SimSettings
from .systems import B0, Baseline, EngineSystem
from .training import train_v2, v2_system

SENSITIVITY_GRID: dict[str, tuple[float, ...]] = {
    "last_gasp_rate": (0.0, 0.25, 0.5, 0.7, 0.9, 1.0),
    "detection_delay_s": (30, 90, 180, 360, 600),
    "outage_api_lag_s": (0, 300, 600, 1200, 1800),
    "blips_per_hour": (0, 2, 4, 15, 60),  # the twin allows up to 60 an hour
}

METRIC_COLUMNS = (
    "accuracy",
    "macro_f1",
    "false_dispatches_per_run",
    "cost_per_run",
    "api_calls_per_run",
    "brier",
)


def _rows(labels: dict, systems, seeds: Iterable[int], settings: SimSettings | None = None):
    """Run the systems and return one row per system: the labels plus the metric columns."""
    outcomes = run_batch(systems, seeds=seeds, settings=settings)
    return [
        {**labels, "system": s.system, **{name: getattr(s, name) for name in METRIC_COLUMNS}}
        for s in summarise_by_system(outcomes)
    ]


def ablations(seeds: Iterable[int] = DEFAULT_SEEDS) -> list[dict]:
    seeds = tuple(seeds)
    rows = _rows({"variant": "all clues"}, [v2_system(train_v2())], seeds)
    for feature in FEATURES:
        model = train_v2(drop=(feature,))
        rows += _rows({"variant": f"without {feature}"}, [v2_system(model)], seeds)
    return rows


def api_improvements(seeds: Iterable[int] = DEFAULT_SEEDS) -> list[dict]:
    seeds = tuple(seeds)
    variants = {
        "today's API": {},
        "+ outage shapes": {"outage_shapes": True},
        "+ restore event": {"restore_events": True},
        "+ both": {"outage_shapes": True, "restore_events": True},
    }
    rows = []
    for variant, flags in variants.items():
        # The model is retrained for each variant, so it learns to use the new information.
        model = train_v2(**flags)
        systems = [
            EngineSystem(**flags),
            v2_system(model, **flags),
            # The baseline only benefits from knowing a meter came back.
            Baseline("B0", restore_events=flags.get("restore_events", False)),
        ]
        rows += _rows({"variant": variant}, systems, seeds)
    return rows


def sensitivity(seeds: Iterable[int] = range(20)) -> list[dict]:
    """The v2 model is trained once on the default settings and then tested on changed ones,
    which is the honest test: the real world will not match what we trained on."""
    seeds = tuple(seeds)
    systems = [EngineSystem(), v2_system(train_v2()), B0]
    rows = []
    for parameter, values in SENSITIVITY_GRID.items():
        for value in values:
            settings = replace(SimSettings(), **{parameter: value})
            rows += _rows({"parameter": parameter, "value": value}, systems, seeds, settings)
    return rows


def write_rows(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        for row in rows:
            writer.writerow({k: f"{v:.4f}" if isinstance(v, float) else v for k, v in row.items()})


def markdown_table(rows: list[dict]) -> str:
    columns = list(rows[0])
    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    for row in rows:
        cells = []
        for name in columns:
            value = row[name]
            if name in ("accuracy",):
                cells.append(f"{value:.0%}")
            elif name == "cost_per_run":
                cells.append(f"${value:,.0f}")
            elif isinstance(value, float):
                cells.append(f"{value:.2f}")
            else:
                cells.append(str(value))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)
