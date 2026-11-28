import base64
import json

from fastapi.testclient import TestClient

from engine.config import Settings
from engine.main import create_app
from engine.receiver import LoggingSink

EVENT = {
    "eventId": "7d4ac9a4-1b9e-4cf6-8a43-0e7c2c1f0a11",
    "subscriptionId": "sub-1",
    "msisdn": "61412000001",
    "reasonCode": 0,
    "reasonGroup": "DETACHED",
    "eventTime": "2026-11-25T00:05:00Z",
    "receivedAt": "2026-11-25T00:05:02Z",
}


def client() -> tuple[TestClient, LoggingSink]:
    sink = LoggingSink()
    return TestClient(create_app(Settings(log_json=False), sink=sink)), sink


def test_http_events_reach_the_engine_once():
    c, sink = client()
    res = c.post("/events", json={"events": [EVENT]})
    assert res.status_code == 202 and res.json() == {"accepted": 1, "duplicates": 0}
    again = c.post("/events", json={"events": [EVENT]})
    assert again.json() == {"accepted": 0, "duplicates": 1}
    assert [e.msisdn for e in sink.received] == ["61412000001"]


def test_pubsub_push_message_reaches_the_engine():
    c, sink = client()
    data = base64.b64encode(json.dumps(EVENT).encode()).decode()
    envelope = {
        "message": {"data": data, "messageId": "1", "attributes": {"msisdn": "61412000001"}},
        "subscription": "projects/p/subscriptions/meter-silent-engine",
    }
    assert c.post("/pubsub/push", json=envelope).status_code == 204
    assert c.post("/pubsub/push", json=envelope).status_code == 204  # redelivery, dropped
    assert len(sink.received) == 1 and sink.received[0].reasonCode == 0


def test_bad_messages_are_rejected():
    c, sink = client()
    bad = base64.b64encode(b'{"msisdn": "x"}').decode()
    assert c.post("/pubsub/push", json={"message": {"data": bad}}).status_code == 400
    assert c.post("/events", json={"events": [{**EVENT, "reasonCode": 12}]}).status_code == 422
    assert sink.received == []
