"""Run scenarios from the command line (#32).

    uv run python -m twin run scenarios/power-outage.yaml --seeds 10
    uv run python -m twin run scenarios/*.yaml --seeds 50 --out runs/

Seeds go 0, 1, 2, ... so "--seeds 10" always means the same ten runs, on any machine.
"""

from __future__ import annotations

import argparse
import glob
from collections.abc import Sequence
from pathlib import Path

from .export import write_run, write_twin
from .grid import build_twin
from .run import run_scenario
from .scenario import ScenarioError, load_scenario


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m twin", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run", help="run scenarios over several seeds and write the results")
    run.add_argument("scenarios", nargs="+", type=Path, help="scenario YAML files")
    run.add_argument("--seeds", type=int, default=10, help="how many runs per scenario")
    run.add_argument("--first-seed", type=int, default=0)
    run.add_argument("--out", type=Path, default=Path("runs"))
    run.add_argument("--heartbeats", action="store_true", help="also write every heartbeat")
    return parser


def _expand(patterns: Sequence[Path]) -> list[Path]:
    """Expand patterns like scenarios/*.yaml ourselves. Bash does it before Python starts, but
    PowerShell and cmd pass the * through unchanged, so without this the command would fail on
    Windows. A pattern that matches nothing is kept, so the error names it."""
    paths: list[Path] = []
    for pattern in patterns:
        text = str(pattern)
        matches = sorted(glob.glob(text)) if any(c in text for c in "*?[") else []
        paths += [Path(m) for m in matches] or [pattern]
    return paths


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scenarios = [load_scenario(p) for p in _expand(args.scenarios)]
    except ScenarioError as e:
        print(f"error: {e}")
        return 2

    written_twins: set[int] = set()
    for scenario in scenarios:
        if scenario.twin_seed not in written_twins:
            write_twin(build_twin(scenario.twin_seed), args.out)
            written_twins.add(scenario.twin_seed)
        for seed in range(args.first_seed, args.first_seed + args.seeds):
            result = run_scenario(scenario, seed)
            folder = write_run(result, args.out, heartbeats=args.heartbeats)
            truth = ", ".join(
                f"{i.cause.value} on {i.target} ({len(i.meter_ids)} meters)"
                for i in result.answer_key
            )
            print(
                f"{scenario.name} seed {seed}: {truth or 'no faults'}, "
                f"{len(result.loc_reports)} LoC reports -> {folder}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
