"""Step 3 of the engine, version 2: a naive Bayes model that learns from labelled runs.

The v1 rules use thresholds and confidence numbers we made up. This model learns its numbers
from training runs where we know the real cause.

How it works, in three steps:

  1. Every clue is put into a few buckets, e.g. burst share becomes "<25%", "25-50%",
     "50-75%" or "75%+". Each bucketed clue is called a feature.
  2. Training counts. For each cause it counts how often every bucket showed up, which gives
     P(bucket | cause): "in power cuts, burst share was 75%+ in 70% of the examples".
  3. Scoring multiplies. For a new cluster:
         score(cause) = P(cause) x P(bucket 1 | cause) x P(bucket 2 | cause) x ...
     and the scores are scaled to add up to 1. Those are the probabilities.

"Naive" means it treats the clues as independent of each other, which is not quite true but
works well and keeps the model small enough to read: it is just a table of counts.

Two details:
  - Smoothing: we add 1 to every count, so a bucket never seen with a cause gets a small
    probability and not zero (one zero would wipe out the whole product).
  - Logs: we add log-probabilities instead of multiplying, because many small numbers
    multiplied together underflow to 0.
"""

import json
import math
from collections import Counter
from collections.abc import Collection, Iterable
from dataclasses import dataclass
from pathlib import Path

from .clues import Clues
from .contracts import Cause, ReasonGroup
from .rules import RuleResult


def _bucket(value: float, edges: tuple[float, ...], names: tuple[str, ...]) -> str:
    """names[i] for the first edge the value is below; the last name if above all of them."""
    for edge, name in zip(edges, names, strict=False):
        if value < edge:
            return name
    return names[-1]


def _size(c: Clues) -> str:
    return _bucket(c.meter_count, (2, 6, 31), ("1", "2-5", "6-30", "31+"))


def _worst_transformer(c: Clues) -> str:
    return _bucket(c.max_transformer_share, (0.05, 0.4, 0.8), ("<5%", "5-40%", "40-80%", "80%+"))


def _spread_across(c: Clues) -> str:
    return _bucket(c.transformer_count, (2, 3), ("1 transformer", "2", "3+"))


def _burst(c: Clues) -> str:
    return _bucket(c.burst_share, (0.25, 0.5, 0.75), ("<25%", "25-50%", "50-75%", "75%+"))


def _detached(c: Clues) -> str:
    return _bucket(c.reason_shares[ReasonGroup.DETACHED], (0.01, 0.5), ("none", "<50%", "50%+"))


def _duration(c: Clues) -> str:
    return _bucket(c.spread_seconds, (30, 120), ("<30 s", "30 s-2 min", "2 min+"))


def _outage(c: Clues) -> str:
    if c.outage_share is None:
        return "not checked"
    return _bucket(c.outage_share, (0.01, 0.5), ("not listed", "partly listed", "listed"))


def _location(c: Clues) -> str:
    if c.location_mismatch_share is None:
        return "not checked"
    return "moved" if c.location_mismatch_share >= 0.5 else "in place"


# name -> (function that buckets the clue, every bucket it can return)
FEATURES = {
    "size": (_size, ("1", "2-5", "6-30", "31+")),
    "worst_transformer": (_worst_transformer, ("<5%", "5-40%", "40-80%", "80%+")),
    "spread_across": (_spread_across, ("1 transformer", "2", "3+")),
    "burst": (_burst, ("<25%", "25-50%", "50-75%", "75%+")),
    "detached": (_detached, ("none", "<50%", "50%+")),
    "duration": (_duration, ("<30 s", "30 s-2 min", "2 min+")),
    "outage": (_outage, ("not checked", "not listed", "partly listed", "listed")),
    "location": (_location, ("not checked", "in place", "moved")),
}


def featurise(clues: Clues, drop: Collection[str] = ()) -> dict[str, str]:
    return {name: fn(clues) for name, (fn, _) in FEATURES.items() if name not in drop}


@dataclass(frozen=True)
class NaiveBayes:
    """A trained model. Build one with `NaiveBayes.fit(...)`, not directly."""

    cause_counts: dict[Cause, int]
    # bucket_counts[cause][feature][bucket] = how many training examples
    bucket_counts: dict[Cause, dict[str, dict[str, int]]]
    dropped: tuple[str, ...] = ()
    alpha: float = 1.0  # the smoothing amount added to every count

    @classmethod
    def fit(
        cls,
        examples: Iterable[tuple[Clues, Cause]],
        drop: Collection[str] = (),
        alpha: float = 1.0,
    ) -> "NaiveBayes":
        """Learn from (clues, real cause) pairs. `drop` leaves features out (for ablations)."""
        unknown = set(drop) - set(FEATURES)
        if unknown:
            raise ValueError(f"unknown features: {sorted(unknown)}")
        cause_counts: Counter[Cause] = Counter()
        bucket_counts = {
            cause: {name: Counter() for name in FEATURES if name not in drop} for cause in Cause
        }
        for clues, cause in examples:
            cause_counts[cause] += 1
            for name, bucket in featurise(clues, drop).items():
                bucket_counts[cause][name][bucket] += 1
        if not cause_counts:
            raise ValueError("cannot train on zero examples")
        return cls(
            cause_counts={cause: cause_counts[cause] for cause in Cause},
            bucket_counts={
                cause: {name: dict(counts) for name, counts in per_feature.items()}
                for cause, per_feature in bucket_counts.items()
            },
            dropped=tuple(sorted(drop)),
            alpha=alpha,
        )

    def _log_prior(self, cause: Cause) -> float:
        total = sum(self.cause_counts.values())
        return math.log((self.cause_counts[cause] + self.alpha) / (total + self.alpha * len(Cause)))

    def _log_likelihood(self, cause: Cause, feature: str, bucket: str) -> float:
        """log P(bucket | cause), smoothed."""
        buckets = FEATURES[feature][1]
        seen = self.bucket_counts[cause][feature].get(bucket, 0)
        return math.log(
            (seen + self.alpha) / (self.cause_counts[cause] + self.alpha * len(buckets))
        )

    def probabilities(self, clues: Clues) -> dict[Cause, float]:
        features = featurise(clues, self.dropped)
        log_scores = {
            cause: self._log_prior(cause)
            + sum(self._log_likelihood(cause, name, bucket) for name, bucket in features.items())
            for cause in Cause
        }
        # Back from logs to probabilities that add up to 1. Subtracting the biggest first
        # keeps exp() away from numbers too small to represent.
        top = max(log_scores.values())
        scores = {cause: math.exp(value - top) for cause, value in log_scores.items()}
        total = sum(scores.values())
        return {cause: score / total for cause, score in scores.items()}

    def score(self, clues: Clues) -> RuleResult:
        """Same shape as the v1 rules return, so the rest of the engine does not care which
        one it is using."""
        probabilities = self.probabilities(clues)
        ranked = sorted(probabilities, key=probabilities.get, reverse=True)
        cause, runner_up = ranked[0], ranked[1]

        # The clues that pushed hardest towards this cause and away from the runner-up.
        features = featurise(clues, self.dropped)
        pull = {
            name: self._log_likelihood(cause, name, bucket)
            - self._log_likelihood(runner_up, name, bucket)
            for name, bucket in features.items()
        }
        strongest = sorted(pull, key=pull.get, reverse=True)[:3]
        reasons = tuple(
            f"{name} = {features[name]} is {math.exp(pull[name]):.1f}x more common in {cause} "
            f"than in {runner_up}"
            for name in strongest
            if pull[name] > 0
        )
        return RuleResult(cause, probabilities[cause], probabilities, "naive-bayes", reasons)

    def to_json(self) -> str:
        return json.dumps(
            {
                "alpha": self.alpha,
                "dropped": list(self.dropped),
                "cause_counts": {cause.value: n for cause, n in self.cause_counts.items()},
                "bucket_counts": {
                    cause.value: per_feature for cause, per_feature in self.bucket_counts.items()
                },
            },
            indent=2,
        )

    @classmethod
    def from_json(cls, text: str) -> "NaiveBayes":
        data = json.loads(text)
        return cls(
            cause_counts={Cause(name): n for name, n in data["cause_counts"].items()},
            bucket_counts={Cause(name): per for name, per in data["bucket_counts"].items()},
            dropped=tuple(data["dropped"]),
            alpha=data["alpha"],
        )

    def save(self, path: Path) -> None:
        path.write_text(self.to_json() + "\n", encoding="utf-8")

    @classmethod
    def load(cls, path: Path) -> "NaiveBayes":
        return cls.from_json(path.read_text(encoding="utf-8"))
