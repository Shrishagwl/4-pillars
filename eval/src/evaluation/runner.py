"""The batch runner: many seeded runs, every system on the same runs, results saved to disk.

Everything runs in this one Python process: the twin and the engine are imported as
libraries. No services, no network, so 200 runs take seconds and give the same numbers
every time.
"""

import csv
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import fields
from functools import lru_cache
from pathlib import Path

from .metrics import Summary, accuracy_by_kind, results_table, summarise_by_system
from .sim import KINDS, Run, SimSettings, simulate
from .systems import Outcome

System = Callable[[Run], Outcome]

# Seeds for scoring. The v2 model is trained on different seeds (see training.py) so that it is
# always tested on runs it has never seen.
DEFAULT_SEEDS = range(50)


@lru_cache(maxsize=4096)
def cached_run(kind: str, seed: int, settings: SimSettings) -> Run:
    return simulate(kind, seed, settings)


def run_batch(
    systems: Sequence[System],
    seeds: Iterable[int] = DEFAULT_SEEDS,
    kinds: Sequence[str] = KINDS,
    settings: SimSettings | None = None,
) -> list[Outcome]:
    """Every system on every (kind, seed). Each system sees exactly the same runs."""
    settings = settings or SimSettings()
    outcomes = []
    for kind in kinds:
        for seed in seeds:
            run = cached_run(kind, seed, settings)
            outcomes.extend(system(run) for system in systems)
    return outcomes


def write_results(out_dir: Path, outcomes: list[Outcome], title: str = "Results") -> list[Summary]:
    """Write runs.csv (one line per run and system), summary.json and summary.md."""
    out_dir.mkdir(parents=True, exist_ok=True)

    columns = [f.name for f in fields(Outcome) if f.name != "probabilities"]
    with (out_dir / "runs.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow([*columns, "correct"])
        for o in outcomes:
            writer.writerow([_cell(getattr(o, name)) for name in columns] + [int(o.correct)])

    summaries = summarise_by_system(outcomes)
    by_kind = accuracy_by_kind(outcomes)
    (out_dir / "summary.json").write_text(
        json.dumps(
            {"systems": [s.as_dict() for s in summaries], "accuracy_by_kind": by_kind}, indent=2
        )
        + "\n",
        encoding="utf-8",
    )

    kinds = sorted({o.kind for o in outcomes})
    kind_lines = ["| System | " + " | ".join(kinds) + " |", "|" + "---|" * (len(kinds) + 1)]
    for system, row in by_kind.items():
        cells = " | ".join(f"{row[k]:.0%}" for k in kinds)
        kind_lines.append(f"| {system} | {cells} |")

    (out_dir / "summary.md").write_text(
        f"# {title}\n\n{summaries[0].runs} runs per system, same seeds for all.\n\n"
        f"{results_table(summaries)}\n\n## Accuracy by fault type\n\n"
        + "\n".join(kind_lines)
        + "\n",
        encoding="utf-8",
    )
    return summaries


def _cell(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float):
        return f"{value:.4f}"
    return str(value)
