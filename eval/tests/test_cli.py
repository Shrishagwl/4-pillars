import pytest

from evaluation.__main__ import build_parser


def test_run_defaults():
    args = build_parser().parse_args(["run"])
    assert args.seeds == 50


def test_engine_and_twin_are_importable():
    # eval drives both services as libraries, in-process, so runs are fast and reproducible.
    pytest.importorskip("engine.contracts")
    pytest.importorskip("twin.config")
