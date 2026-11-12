"""Command line entry point: `uv run pillars-eval run --seeds 50 --out results/`."""

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="pillars-eval", description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="run every scenario over many seeds and score the engine")
    run.add_argument("--scenarios", type=Path, default=Path("../services/twin/scenarios"))
    run.add_argument("--seeds", type=int, default=50, help="runs per scenario")
    run.add_argument("--out", type=Path, default=Path("results"))
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        # Batch runner (#27): for each scenario and seed, run the twin, feed events to the engine
        # and the baselines (#34), then write per-run results for the metrics (#38).
        raise SystemExit("batch runner not built yet, see issue #27")


if __name__ == "__main__":
    main()
