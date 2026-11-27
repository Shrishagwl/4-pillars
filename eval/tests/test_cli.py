import pytest

from evaluation.__main__ import build_parser, main


def test_run_defaults():
    args = build_parser().parse_args(["run"])
    assert args.seeds == 50


def test_engine_and_twin_are_importable():
    # eval drives both services as libraries, in-process, so runs are fast and reproducible.
    pytest.importorskip("engine.contracts")
    pytest.importorskip("twin.config")


def test_run_command_writes_the_results(tmp_path, capsys):
    main(["run", "--seeds", "2", "--out", str(tmp_path)])

    assert (tmp_path / "runs.csv").exists()
    assert (tmp_path / "summary.md").exists()
    assert (tmp_path / "model.json").exists()
    printed = capsys.readouterr().out
    assert "| engine-v1 |" in printed and "| engine-v2 |" in printed


def test_sensitivity_default_is_smaller_because_it_runs_many_settings():
    assert build_parser().parse_args(["sensitivity"]).seeds == 20


def test_ablations_command_writes_both_tables(tmp_path):
    main(["ablations", "--seeds", "2", "--out", str(tmp_path)])

    for name in ("ablations.csv", "ablations.md", "api_improvements.csv", "api_improvements.md"):
        assert (tmp_path / name).exists()
