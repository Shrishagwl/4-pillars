"""Step 3 of the engine, version 1: hand-written rules that pick a cause from the clues.

The rules are checked in order and the first match wins:

  1. POWER        most of a transformer is silent and most of the cluster dropped in a burst
  2. NETWORK      Telstra lists an outage where most of the cluster is
  3. NETWORK      (weaker) parts of several transformers are silent, no outage listed yet
  4. METER_FAULT  a single meter
  5. METER_FAULT  (weak) anything left over

The confidence numbers are our own judgement, not learned from data. Version 2 (naive Bayes)
replaces them with probabilities learned from twin runs. TAMPER is never picked here because
it needs Location Verification, which v1 does not look at.
"""

from dataclasses import dataclass

from .clues import Clues
from .contracts import Cause


@dataclass(frozen=True, slots=True)
class RuleThresholds:
    # POWER: at least this share of the touched transformers is silent ...
    power_transformer_share: float = 0.6
    # ... and at least this share of the cluster dropped in the first burst.
    power_burst_share: float = 0.5
    # NETWORK: at least this share of the cluster is in a suburb with a listed outage.
    network_outage_share: float = 0.5

    confidence_power: float = 0.9
    confidence_power_during_outage: float = 0.6
    confidence_network_listed: float = 0.85
    confidence_network_unlisted: float = 0.55
    confidence_single_meter: float = 0.7
    confidence_unclear: float = 0.4


DEFAULT_THRESHOLDS = RuleThresholds()


@dataclass(frozen=True, slots=True)
class RuleResult:
    cause: Cause
    confidence: float
    probabilities: dict[Cause, float]  # every cause, adds up to 1
    rule: str  # which rule fired, for the evidence list and for debugging
    reasons: tuple[str, ...]


def _result(cause: Cause, confidence: float, rule: str, *reasons: str) -> RuleResult:
    # The winning cause gets `confidence`; the rest is shared equally by the other causes.
    others = [c for c in Cause if c is not cause]
    probabilities = {c: (1 - confidence) / len(others) for c in others}
    probabilities[cause] = confidence
    return RuleResult(cause, confidence, probabilities, rule, reasons)


def _pct(share: float) -> str:
    return f"{share:.0%}"


def score_v1(clues: Clues, thresholds: RuleThresholds = DEFAULT_THRESHOLDS) -> RuleResult:
    t = thresholds
    outage_listed = clues.outage_share is not None and clues.outage_share >= t.network_outage_share
    outage_reason = (
        "Outage API not checked yet"
        if clues.outage_share is None
        else f"{_pct(clues.outage_share)} of the cluster is in a suburb with a listed outage"
    )

    # 1. POWER: whole transformer + fast drops.
    if (
        clues.meter_count >= 2
        and clues.transformer_share >= t.power_transformer_share
        and clues.burst_share >= t.power_burst_share
    ):
        confidence = t.confidence_power_during_outage if outage_listed else t.confidence_power
        return _result(
            Cause.POWER,
            confidence,
            "power",
            f"{_pct(clues.transformer_share)} of the meters on {clues.transformer_count} "
            "transformer(s) are silent",
            f"{_pct(clues.burst_share)} of them dropped in the first burst",
            outage_reason,
        )

    # 2. NETWORK: Telstra says so.
    if outage_listed:
        return _result(
            Cause.NETWORK,
            t.confidence_network_listed,
            "network-listed",
            outage_reason,
            f"{clues.meter_count} meters across {clues.transformer_count} transformer(s)",
        )

    # 3. NETWORK, weaker: looks like a network outage but nothing is listed (yet).
    if clues.crosses_transformers:
        return _result(
            Cause.NETWORK,
            t.confidence_network_unlisted,
            "network-unlisted",
            f"{clues.meter_count} meters across {clues.transformer_count} transformers, "
            f"only {_pct(clues.transformer_share)} of them silent",
            f"drops spread over {clues.spread_seconds:.0f} s",
            outage_reason,
        )

    # 4. METER_FAULT: one meter on its own.
    if clues.meter_count == 1:
        return _result(
            Cause.METER_FAULT,
            t.confidence_single_meter,
            "single-meter",
            "one meter is silent and nothing around it",
            outage_reason,
        )

    # 5. Nothing fits well: a few meters on one transformer, not enough to call it power.
    return _result(
        Cause.METER_FAULT,
        t.confidence_unclear,
        "unclear",
        f"{clues.meter_count} meters on one transformer, "
        f"only {_pct(clues.transformer_share)} of it silent",
        outage_reason,
    )
