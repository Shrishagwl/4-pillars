"""Turn a pile of per-run Outcomes into one row of numbers per system.

accuracy          share of runs where the cause was right
macro F1          F1 per cause, then averaged, so a rare cause counts as much as a common one
jaccard           overlap of blamed meters and really affected meters (1 = identical sets)
time to verdict   median seconds from the fault until the verdict was right and stayed right
false dispatches  people sent out for nothing, per run
cost              avoidable dollars per run; "saved" is the difference to a baseline
API calls         Telstra API calls per run
Brier             how honest the probabilities are (0 = perfect, lower is better)
"""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from statistics import mean, median

from engine.contracts import Cause

from .systems import Outcome


@dataclass(frozen=True)
class Summary:
    system: str
    runs: int
    accuracy: float
    macro_f1: float
    jaccard: float
    median_seconds_to_correct: float | None
    never_correct: float  # share of runs that never reached the right verdict
    false_dispatches_per_run: float
    cost_per_run: float
    api_calls_per_run: float
    brier: float

    def as_dict(self) -> dict:
        return asdict(self)


def f1_per_cause(outcomes: list[Outcome]) -> dict[Cause, float]:
    scores = {}
    for cause in Cause:
        true_positive = sum(1 for o in outcomes if o.truth is cause and o.predicted is cause)
        predicted = sum(1 for o in outcomes if o.predicted is cause)
        actual = sum(1 for o in outcomes if o.truth is cause)
        if actual == 0:
            continue  # this cause never happened in these runs, so it cannot be scored
        precision = true_positive / predicted if predicted else 0.0
        recall = true_positive / actual
        total = precision + recall
        scores[cause] = 2 * precision * recall / total if total else 0.0
    return scores


def brier(outcome: Outcome) -> float:
    """Squared distance between the probabilities and the truth (1 for the real cause, 0 else).

    A system that never noticed the fault is scored as if it said 25% for everything.
    """
    probabilities = outcome.probabilities or dict.fromkeys(Cause, 1 / len(Cause))
    return sum(
        (probabilities.get(cause, 0.0) - (1.0 if cause is outcome.truth else 0.0)) ** 2
        for cause in Cause
    )


def summarise(outcomes: list[Outcome]) -> Summary:
    if not outcomes:
        raise ValueError("no outcomes to summarise")
    times = [o.seconds_to_correct for o in outcomes if o.seconds_to_correct is not None]
    f1 = f1_per_cause(outcomes)
    return Summary(
        system=outcomes[0].system,
        runs=len(outcomes),
        accuracy=mean(o.correct for o in outcomes),
        macro_f1=mean(f1.values()),
        jaccard=mean(o.jaccard for o in outcomes),
        median_seconds_to_correct=median(times) if times else None,
        never_correct=1 - len(times) / len(outcomes),
        false_dispatches_per_run=mean(o.false_dispatches for o in outcomes),
        cost_per_run=mean(o.cost for o in outcomes),
        api_calls_per_run=mean(o.api_calls for o in outcomes),
        brier=mean(brier(o) for o in outcomes),
    )


def summarise_by_system(outcomes: Iterable[Outcome]) -> list[Summary]:
    grouped: dict[str, list[Outcome]] = defaultdict(list)
    for outcome in outcomes:
        grouped[outcome.system].append(outcome)
    return [summarise(group) for group in grouped.values()]


def accuracy_by_kind(outcomes: Iterable[Outcome]) -> dict[str, dict[str, float]]:
    """{system: {kind: accuracy}}, to see which fault type a system struggles with."""
    grouped: dict[tuple[str, str], list[bool]] = defaultdict(list)
    for o in outcomes:
        grouped[(o.system, o.kind)].append(o.correct)
    table: dict[str, dict[str, float]] = defaultdict(dict)
    for (system, kind), hits in grouped.items():
        table[system][kind] = mean(hits)
    return dict(table)


def results_table(summaries: list[Summary], baseline: str = "B0") -> str:
    """Markdown table, one row per system, with dollars saved against the baseline."""
    base = next((s for s in summaries if s.system == baseline), None)
    header = (
        "| System | Accuracy | Macro F1 | Jaccard | Time to verdict | Never right | "
        f"False dispatches / run | Cost / run | Saved vs {baseline} | API calls / run | Brier |"
    )
    lines = [header, "|" + "---|" * 11]
    for s in summaries:
        seconds = s.median_seconds_to_correct
        saved = f"${base.cost_per_run - s.cost_per_run:,.0f}" if base else "n/a"
        lines.append(
            f"| {s.system} | {s.accuracy:.0%} | {s.macro_f1:.2f} | {s.jaccard:.2f} | "
            f"{f'{seconds:.0f} s' if seconds is not None else 'n/a'} | {s.never_correct:.0%} | "
            f"{s.false_dispatches_per_run:.2f} | ${s.cost_per_run:,.0f} | {saved} | "
            f"{s.api_calls_per_run:.1f} | {s.brier:.3f} |"
        )
    return "\n".join(lines)
