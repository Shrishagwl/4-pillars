import random
from pathlib import Path

import pytest

from twin.grid import build_twin
from twin.scenario import (
    Cause,
    NetworkFault,
    PowerFault,
    ScenarioError,
    load_scenario,
    parse_scenario,
    schedule,
)

SCENARIOS = Path(__file__).parent.parent / "scenarios"


def power(**overrides):
    fault = {"kind": "power", "at_min": 10, "transformer": "T-03"}
    return fault | overrides


def scenario(*faults, **overrides):
    data = {"name": "test", "duration_min": 60, "faults": list(faults)}
    return parse_scenario(data | overrides)


# --- stage 1: is the file well formed? ---------------------------------------------------------


def test_every_scenario_file_in_the_folder_loads():
    files = sorted(SCENARIOS.glob("*.yaml"))
    assert files, "no scenario files found"
    for path in files:
        assert load_scenario(path).name == path.stem


def test_quiet_scenario_has_no_faults():
    quiet = load_scenario(SCENARIOS / "quiet.yaml")
    assert quiet.faults == []
    assert quiet.duration_min == 60


def test_kind_picks_the_fault_type_and_defaults_fill_in():
    s = scenario(power(), {"kind": "network", "at_min": 5, "suburb": "Coburg"})
    first, second = s.faults
    assert isinstance(first, PowerFault)
    assert isinstance(second, NetworkFault)
    assert first.last_gasp_share == 0.7
    assert first.restore_after_min is None
    assert first.cause is Cause.POWER
    assert second.cause is Cause.NETWORK


@pytest.mark.parametrize(
    ("bad_fault", "message"),
    [
        (power(kind="earthquake"), "kind"),  # unknown kind
        (power(at_min=-1), "at_min"),  # negative time
        (power(last_gasp_share=1.5), "last_gasp_share"),  # a share above 100%
        (power(restore_afer_min=30), "restore_afer_min"),  # typo in a field name
        (power(cause="NETWORK"), "cause"),  # a file can't choose its own answer key
        ({"kind": "power", "at_min": 10}, "transformer"),  # missing target
    ],
)
def test_bad_faults_are_rejected_with_the_field_named(bad_fault, message):
    with pytest.raises(ScenarioError, match=message):
        scenario(bad_fault)


def test_a_fault_must_start_before_the_run_ends():
    with pytest.raises(ScenarioError) as caught:
        scenario(power(at_min=60))
    # A whole-scenario check has no single field: the message reads cleanly, with no empty
    # "where" and no "Value error," noise.
    assert str(caught.value) == (
        "scenario: faults[0] starts at minute 60, but the run only lasts 60 minutes"
    )


def test_broken_yaml_is_reported_with_the_file_name(tmp_path):
    path = tmp_path / "broken.yaml"
    path.write_text("name: [unclosed\n", encoding="utf-8")
    with pytest.raises(ScenarioError, match="broken.yaml: not valid YAML"):
        load_scenario(path)


def test_a_loaded_scenario_cannot_be_changed():
    s = scenario(power())
    with pytest.raises(Exception, match="frozen"):
        s.duration_min = 10


# --- stage 2: does it make sense for this twin? ------------------------------------------------


@pytest.fixture(scope="module")
def twin():
    return build_twin(42)


def test_schedule_finds_the_meters_of_a_named_target(twin):
    [planned] = schedule(scenario(power()), twin, random.Random(0))
    assert planned.target == "T-03"
    assert set(planned.meter_ids) == {m.meter_id for m in twin.meters_on("T-03")}


def test_unknown_target_is_rejected(twin):
    with pytest.raises(ScenarioError, match="'T-99' is not in twin 42"):
        schedule(scenario(power(transformer="T-99")), twin, random.Random(0))


def test_random_targets_depend_only_on_the_seed(twin):
    s = scenario(*[power(transformer="random", at_min=m) for m in range(10)])
    picks = [p.target for p in schedule(s, twin, random.Random(7))]
    again = [p.target for p in schedule(s, twin, random.Random(7))]
    other = [p.target for p in schedule(s, twin, random.Random(8))]
    assert picks == again
    assert picks != other
    assert all(t in {tr.id for tr in twin.transformers} for t in picks)


def test_schedule_is_in_time_order_with_restore_times(twin):
    s = scenario(power(at_min=40), power(at_min=5, restore_after_min=20))
    planned = schedule(s, twin, random.Random(0))
    assert [p.at_min for p in planned] == [5, 40]
    assert [p.restore_at_min for p in planned] == [25, None]
