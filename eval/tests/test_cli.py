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
    assert "| engine-v1 |" in capsys.readouterr().out
