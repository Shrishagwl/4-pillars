import json
from datetime import timedelta
from pathlib import Path

import pytest

from twin.__main__ import main
from twin.clock import DEFAULT_START
from twin.export import write_run
from twin.run import run_scenario
from twin.scenario import ScenarioError, load_scenario, parse_scenario

SCENARIOS = Path(__file__).parent.parent / "scenarios"


def one_fault(**fault):
    base = {"kind": "power", "at_min": 10, "transformer": "random"}
    return parse_scenario({"name": "t", "duration_min": 120, "faults": [base | fault]})


# --- every run varies by seed, and only by seed -------------------------------------------------


def test_a_time_window_picks_a_minute_inside_it_per_seed():
    s = one_fault(at_min=[20, 40], restore_after_min=[10, 15])
    starts = []
    for seed in range(15):
        [incident] = run_scenario(s, seed).answer_key
        start = (incident.started_at - DEFAULT_START) / timedelta(minutes=1)
        repair = (incident.restored_at - incident.started_at) / timedelta(minutes=1)
        assert 20 <= start <= 40
        assert 10 <= repair <= 15
        starts.append(start)
    assert len(set(starts)) > 1  # the seeds really do move it around


def test_a_fixed_minute_stays_fixed_across_seeds():
    s = one_fault(at_min=25)
    starts = {run_scenario(s, seed).answer_key[0].started_at for seed in range(5)}
    assert starts == {DEFAULT_START + timedelta(minutes=25)}


@pytest.mark.parametrize("name", ["power-outage", "network-outage"])
def test_same_seed_identical_run_different_seeds_differ(name):
    s = load_scenario(SCENARIOS / f"{name}.yaml")
    assert run_scenario(s, 11) == run_scenario(s, 11)
    keys = {run_scenario(s, seed).answer_key for seed in range(5)}
    assert len(keys) == 5  # target, timing or silenced meters differ every time


@pytest.mark.parametrize(
    ("fault", "message"),
    [
        ({"at_min": [40, 20]}, "low <= high"),
        ({"restore_after_min": [0, 10]}, "at least 1 minute"),
        ({"at_min": [100, 130]}, "can start at minute 130"),
    ],
)
def test_bad_time_windows_are_rejected(fault, message):
    with pytest.raises(ScenarioError, match=message):
        one_fault(**fault)


# --- writing runs to files ----------------------------------------------------------------------


@pytest.fixture(scope="module")
def network_run():
    return run_scenario(load_scenario(SCENARIOS / "network-outage.yaml"), seed=2)


def test_events_and_answer_key_go_in_separate_files(tmp_path, network_run):
    folder = write_run(network_run, tmp_path)
    assert {p.name for p in folder.iterdir()} == {
        "loc_reports.jsonl",
        "outages.jsonl",
        "answer_key.json",
        "background.json",
        "run.json",
    }
    events = (folder / "loc_reports.jsonl").read_text(encoding="utf-8")
    assert "NETWORK" not in events and "cause" not in events  # no peeking at the answer
    answer = json.loads((folder / "answer_key.json").read_text(encoding="utf-8"))
    assert answer[0]["cause"] == "NETWORK"
    assert len(answer[0]["meterIds"]) == len(events.splitlines())


def test_written_reports_are_in_telstras_shape(tmp_path, network_run):
    folder = write_run(network_run, tmp_path)
    first = json.loads((folder / "loc_reports.jsonl").read_text(encoding="utf-8").splitlines()[0])
    assert first["monitoringType"] == "LOSS_OF_CONNECTIVITY"
    assert first["eventTime"].endswith("Z")
    [outage] = [
        json.loads(line)
        for line in (folder / "outages.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    assert outage["suburb"] == network_run.answer_key[0].target


def test_same_seed_writes_byte_identical_files(tmp_path):
    s = load_scenario(SCENARIOS / "power-outage.yaml")
    a = write_run(run_scenario(s, 4), tmp_path / "a")
    b = write_run(run_scenario(s, 4), tmp_path / "b")
    for f in a.iterdir():
        assert f.read_bytes() == (b / f.name).read_bytes()


def test_heartbeats_are_written_only_when_asked(tmp_path, network_run):
    folder = write_run(network_run, tmp_path, heartbeats=True)
    lines = (folder / "heartbeats.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(lines) == len(network_run.heartbeats)
    write_run(network_run, tmp_path)  # a later run without the flag clears the old file
    assert not (folder / "heartbeats.jsonl").exists()


# --- the command line ---------------------------------------------------------------------------


def test_command_line_runs_every_scenario_for_every_seed(tmp_path, capsys):
    files = [str(SCENARIOS / "power-outage.yaml"), str(SCENARIOS / "network-outage.yaml")]
    assert main(["run", *files, "--seeds", "2", "--out", str(tmp_path)]) == 0
    assert (tmp_path / "twin-42.json").exists()
    for name in ("power-outage", "network-outage"):
        for seed in (0, 1):
            assert (tmp_path / name / f"seed-{seed:03d}" / "answer_key.json").exists()
    printed = capsys.readouterr().out
    assert "power-outage seed 0: POWER on T-" in printed
    assert "network-outage seed 1: NETWORK on " in printed


def test_command_line_reports_a_bad_scenario_file(tmp_path, capsys):
    bad = tmp_path / "bad.yaml"
    bad.write_text("name: bad\nduration_min: -5\n", encoding="utf-8")
    assert main(["run", str(bad), "--out", str(tmp_path / "runs")]) == 2
    assert "bad.yaml" in capsys.readouterr().out
