"""Step 5 of the engine: say why. Every verdict carries a short list of plain-English facts.

The list always has the same lines in the same order, so the dashboard card looks the same for
every incident: meters, where, timing, reason codes, Outage API, why this cause, why this action.
"""

from datetime import datetime

from .clues import Clues
from .clustering import Cluster
from .contracts import ReasonGroup, Verdict
from .decision import Decision
from .rules import RuleResult

MAX_NAMED = 3

REASON_LABELS = {
    ReasonGroup.DETACHED: "detached (includes last gasp)",
    ReasonGroup.DETECTION_TIMEOUT: "detection timeout",
    ReasonGroup.PURGED: "purged",
    ReasonGroup.UNKNOWN: "unknown code",
}


def _names(items: list[str]) -> str:
    """'a, b, c and 17 more' so a 300-meter cluster still fits on one line."""
    shown = ", ".join(items[:MAX_NAMED])
    extra = len(items) - MAX_NAMED
    return f"{shown} and {extra} more" if extra > 0 else shown


def _clock(when: datetime) -> str:
    return when.strftime("%H:%M:%S")


def build_evidence(
    cluster: Cluster, clues: Clues, result: RuleResult, decision: Decision
) -> list[str]:
    meter_ids = [m.meter.meter_id for m in cluster.members]
    lines = [
        f"Meters: {clues.meter_count} silent ({_names(meter_ids)})",
        f"Where: transformer(s) {_names(sorted(cluster.transformer_ids))} in "
        f"{_names(sorted(cluster.suburbs))}; {clues.transformer_share:.0%} of the meters on "
        "them are silent",
        f"Timing: first drop {_clock(cluster.first_silent_at)}, "
        f"last {_clock(cluster.last_silent_at)} ({clues.spread_seconds:.0f} s apart); "
        f"{clues.burst_share:.0%} dropped in the first burst",
    ]

    mix = [
        f"{share:.0%} {REASON_LABELS[group]}"
        for group, share in sorted(clues.reason_shares.items(), key=lambda kv: -kv[1])
        if share > 0
    ]
    lines.append("Reason codes: " + ", ".join(mix))

    if clues.outage_share is None:
        lines.append("Outage API: not checked yet")
    elif clues.outage_share == 0:
        lines.append("Outage API: no outage listed for these meters")
    else:
        lines.append(f"Outage API: outage listed, covering {clues.outage_share:.0%} of the cluster")

    lines.append(
        f"Verdict: {result.cause} at {result.confidence:.0%} (rule '{result.rule}': "
        + "; ".join(result.reasons)
        + ")"
    )
    lines.append(f"Action: {decision.action} ({decision.reason})")
    return lines


def to_verdict(
    incident_id: str,
    cluster: Cluster,
    clues: Clues,
    result: RuleResult,
    decision: Decision,
    updated_at: datetime,
) -> Verdict:
    """Pack one assessment into the shape the dashboard and the database expect."""
    return Verdict(
        incidentId=incident_id,
        meterCount=cluster.size,
        probabilities=result.probabilities,
        cause=result.cause,
        confidence=result.confidence,
        action=decision.action,
        evidence=build_evidence(cluster, clues, result, decision),
        updatedAt=updated_at,
    )
