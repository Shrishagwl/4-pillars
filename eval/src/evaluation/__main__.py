"""Offline evaluation of the engine.

uv run pillars-eval run          --seeds 50 --out results/
uv run pillars-eval ablations    --seeds 50 --out results/
uv run pillars-eval sensitivity  --seeds 20 --out results/
"""

import argparse
import time
from pathlib import Path

from .experiments import ablations, api_improvements, markdown_table, sensitivity, write_rows
from .metrics import results_table
from .runner import run_batch, write_results
from .systems import B0, B1, EngineSystem
from .training import train_v2, training_examples, v2_system


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pillars-eval",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="engine v1 and v2 against the baselines on the same runs")
    run.add_argument("--seeds", type=int, default=50, help="runs per fault type")
    run.add_argument("--out", type=Path, default=Path("results"))

    abl = sub.add_parser("ablations", help="remove one clue at a time; try the proposed API")
    abl.add_argument("--seeds", type=int, default=50, help="runs per fault type")
    abl.add_argument("--out", type=Path, default=Path("results"))

    sens = sub.add_parser("sensitivity", help="change one twin setting at a time")
    sens.add_argument("--seeds", type=int, default=20, help="runs per fault type and setting")
    sens.add_argument("--out", type=Path, default=Path("results"))
    return parser


def command_run(seeds: int, out: Path) -> None:
    model = train_v2()
    out.mkdir(parents=True, exist_ok=True)
    model.save(out / "model.json")
    print(f"Trained v2 on {len(training_examples())} examples from separate seeds")

    outcomes = run_batch([EngineSystem(), v2_system(model), B0, B1], seeds=range(seeds))
    summaries = write_results(out, outcomes, title="Engine vs baselines")
    print(results_table(summaries))
    print(f"\nSaved runs.csv, summary.json, summary.md and model.json in {out}/")


def command_ablations(seeds: int, out: Path) -> None:
    for name, rows in (
        ("ablations", ablations(range(seeds))),
        ("api_improvements", api_improvements(range(seeds))),
    ):
        write_rows(out / f"{name}.csv", rows)
        (out / f"{name}.md").write_text(markdown_table(rows) + "\n", encoding="utf-8")
        print(f"\n{name}\n{markdown_table(rows)}")
    print(f"\nSaved ablations and api_improvements (.csv and .md) in {out}/")


def command_sensitivity(seeds: int, out: Path) -> None:
    rows = sensitivity(range(seeds))
    write_rows(out / "sensitivity.csv", rows)
    (out / "sensitivity.md").write_text(markdown_table(rows) + "\n", encoding="utf-8")
    print(markdown_table(rows))
    print(f"\nSaved sensitivity.csv and sensitivity.md in {out}/")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    started = time.perf_counter()
    commands = {
        "run": command_run,
        "ablations": command_ablations,
        "sensitivity": command_sensitivity,
    }
    commands[args.command](args.seeds, args.out)
    print(f"Done in {time.perf_counter() - started:.1f} s")


if __name__ == "__main__":
    main()
