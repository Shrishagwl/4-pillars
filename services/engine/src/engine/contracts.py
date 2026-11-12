"""Python mirror of packages/contracts/src/events.ts. Change both together."""

from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class ReasonGroup(StrEnum):
    DETACHED = "DETACHED"  # LoC codes 0, 1, 6
    DETECTION_TIMEOUT = "DETECTION_TIMEOUT"  # LoC codes 2, 3, 7
    PURGED = "PURGED"  # LoC codes 4, 5, 8
    UNKNOWN = "UNKNOWN"


REASON_GROUPS: dict[int, ReasonGroup] = {
    **dict.fromkeys((0, 1, 6), ReasonGroup.DETACHED),
    **dict.fromkeys((2, 3, 7), ReasonGroup.DETECTION_TIMEOUT),
    **dict.fromkeys((4, 5, 8), ReasonGroup.PURGED),
}


def reason_group(code: int) -> ReasonGroup:
    return REASON_GROUPS.get(code, ReasonGroup.UNKNOWN)


class Cause(StrEnum):
    POWER = "POWER"
    NETWORK = "NETWORK"
    METER_FAULT = "METER_FAULT"
    TAMPER = "TAMPER"


class Action(StrEnum):
    DISPATCH_POWER_CREW = "DISPATCH_POWER_CREW"
    WAIT_FOR_NETWORK = "WAIT_FOR_NETWORK"
    DISPATCH_METER_TECH = "DISPATCH_METER_TECH"
    INVESTIGATE_TAMPER = "INVESTIGATE_TAMPER"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class MeterSilentEvent(BaseModel):
    """Published by ingest-api (Pub/Sub topic `meter-silent`) for every LoC report."""

    eventId: str
    subscriptionId: str
    msisdn: str
    reasonCode: int = Field(ge=0, le=8)
    reasonGroup: ReasonGroup
    eventTime: datetime
    receivedAt: datetime


class Verdict(BaseModel):
    """What the engine stores per incident and the dashboard shows."""

    incidentId: str
    meterCount: int = Field(ge=1)
    probabilities: dict[Cause, float]
    cause: Cause
    confidence: float = Field(ge=0, le=1)
    action: Action
    evidence: list[str]
    updatedAt: datetime
