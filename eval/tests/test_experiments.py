import csv

from engine.bayes import FEATURES

from evaluation.experiments import (
    SENSITIVITY_GRID,
    ablations,
    api_improvements,
    markdown_table,
    sensitivity,
    write_rows,
)

SEEDS = range(4)  # small on purpose: these tests check the plumbing, not the numbers


def test_ablations_has_one_row_per_clue_plus_the_full_model():
    rows = ablations(SEEDS)
    assert [r["variant"] for r in rows] == ["all clues"] + [f"without {f}" for f in FEATURES]
    assert all(0 <= r["accuracy"] <= 1 for r in rows)
    full = rows[0]["accuracy"]
    without_detached = next(r for r in rows if r["variant"] == "without detached")
    assert without_detached["accuracy"] < full  # the last gasp is what gives a power cut away


def test_api_improvements_compares_four_variants_for_three_systems():
    rows = api_improvements(SEEDS)
    assert {r["variant"] for r in rows} == {
        "today's API", "+ outage shapes", "+ restore event", "+ both",
    }  # fmt: skip
    assert {r["system"] for r in rows} == {"engine-v1", "engine-v2", "B0"}
    assert len(rows) == 12

    def false_dispatches(variant: str, system: str) -> float:
        [row] = [r for r in rows if r["variant"] == variant and r["system"] == system]
        return row["false_dispatches_per_run"]

    assert false_dispatches("+ restore event", "B0") <= false_dispatches("today's API", "B0")


def test_sensitivity_covers_the_whole_grid():
    rows = sensitivity(range(2))
    settings = {(r["parameter"], r["value"]) for r in rows}
    expected = {(p, v) for p, values in SENSITIVITY_GRID.items() for v in values}
    assert settings == expected
    assert len(rows) == len(expected) * 3  # v1, v2 and B0 for each


def test_rows_are_saved_as_csv_and_markdown(tmp_path):
    rows = [
        {"variant": "all clues", "system": "engine-v2", "accuracy": 0.975, "cost_per_run": 338.0},
        {"variant": "without size", "system": "engine-v2", "accuracy": 0.9, "cost_per_run": 400.5},
    ]
    write_rows(tmp_path / "out" / "rows.csv", rows)
    with (tmp_path / "out" / "rows.csv").open(encoding="utf-8") as handle:
        saved = list(csv.DictReader(handle))
    assert saved[0] == {
        "variant": "all clues", "system": "engine-v2", "accuracy": "0.9750",
        "cost_per_run": "338.0000",
    }  # fmt: skip

    table = markdown_table(rows)
    assert "| all clues | engine-v2 | 98% | $338 |" in table
