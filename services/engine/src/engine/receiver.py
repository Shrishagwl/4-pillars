"""Where silent-meter events arrive from ingest-api.

Two doors, same events:
  POST /events        {"events": [MeterSilentEvent, ...]}       locally (HTTP hand-off)
  POST /pubsub/push   a Pub/Sub push message, base64 JSON body   on Cloud Run

Both pass the events to a sink. Repeats (same eventId) are dropped here, because ingest-api
passes a repeated Telstra report on again and Pub/Sub delivers at least once.
"""

import base64
import json
import logging
from collections import OrderedDict
from typing import Protocol

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, ValidationError

from .contracts import MeterSilentEvent

log = logging.getLogger(__name__)


class EventSink(Protocol):
    def accept(self, events: list[MeterSilentEvent]) -> None: ...


class LoggingSink:
    """Until the engine service runs the tracker (#24): log what arrived."""

    def __init__(self) -> None:
        self.received: list[MeterSilentEvent] = []

    def accept(self, events: list[MeterSilentEvent]) -> None:
        for e in events:
            log.info(
                "event received",
                extra={"eventId": e.eventId, "msisdn": e.msisdn, "reasonCode": e.reasonCode},
            )
        self.received.extend(events)


class SeenIds:
    """The last few thousand event ids, to drop repeats. A restart forgets them, which is fine:
    the tracker ignores an event it already has (#24)."""

    def __init__(self, size: int = 50_000) -> None:
        self._ids: OrderedDict[str, None] = OrderedDict()
        self._size = size

    def new(self, event_id: str) -> bool:
        if event_id in self._ids:
            return False
        self._ids[event_id] = None
        if len(self._ids) > self._size:
            self._ids.popitem(last=False)
        return True


class EventBatch(BaseModel):
    events: list[MeterSilentEvent]


class PushMessage(BaseModel):
    data: str
    messageId: str | None = None
    attributes: dict[str, str] | None = None


class PushEnvelope(BaseModel):
    message: PushMessage
    subscription: str | None = None


def make_router(sink: EventSink) -> APIRouter:
    router = APIRouter()
    seen = SeenIds()

    def hand_over(events: list[MeterSilentEvent]) -> int:
        fresh = [e for e in events if seen.new(e.eventId)]
        if fresh:
            sink.accept(fresh)
        return len(fresh)

    @router.post("/events", status_code=202)
    def events(batch: EventBatch) -> dict[str, int]:
        accepted = hand_over(batch.events)
        return {"accepted": accepted, "duplicates": len(batch.events) - accepted}

    @router.post("/pubsub/push", status_code=204)
    def pubsub_push(envelope: PushEnvelope) -> None:
        # A 2xx acks the message. A message we can never read gets a 400 and is not retried
        # forever: the subscription's dead-letter topic catches it after a few attempts.
        try:
            event = MeterSilentEvent.model_validate(
                json.loads(base64.b64decode(envelope.message.data))
            )
        except (ValueError, ValidationError) as err:
            log.warning(
                "unreadable Pub/Sub message", extra={"messageId": envelope.message.messageId}
            )
            raise HTTPException(400, "message data is not a MeterSilentEvent") from err
        hand_over([event])

    return router
