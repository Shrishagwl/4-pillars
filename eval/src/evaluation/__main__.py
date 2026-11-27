"""Command line entry point: `uv run pillars-eval run --seeds 50 --out results/`."""

import argparse
import time
from pathlib import Path

from .metrics import results_table
from .runner import run_batch, write_results
from .systems import B0, B1, EngineSystem


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pillars-eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run every fault type over many seeds and score each system")
    run.add_argument("--seeds", type=int, default=50, help="runs per fault type")
    run.add_argument("--out", type=Path, default=Path("results"))
    return parser


def command_run(seeds: int, out: Path) -> None:
    started = time.perf_counter()
    outcomes = run_batch([EngineSystem(), B0, B1], seeds=range(seeds))
    summaries = write_results(out, outcomes, title="Engine vs baselines")
    print(results_table(summaries))
    print(f"\n{summaries[0].runs} runs per system in {time.perf_counter() - started:.1f} s")
    print(f"Saved runs.csv, summary.json and summary.md in {out}/")


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        command_run(args.seeds, args.out)


if __name__ == "__main__":
    main()
