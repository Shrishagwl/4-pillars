-- Every silent-meter event the engine accepted, so a restarted instance can rebuild its
-- incidents from the database instead of starting blank.
CREATE TABLE engine.events (
    event_id         uuid PRIMARY KEY,
    subscription_id  text NOT NULL,
    msisdn           text NOT NULL,
    reason_code      smallint NOT NULL CHECK (reason_code BETWEEN 0 AND 8),
    event_time       timestamptz NOT NULL,
    received_at      timestamptz NOT NULL,
    -- The same report under a new event id is still the same report.
    UNIQUE (msisdn, event_time, reason_code)
);
CREATE INDEX events_time_idx ON engine.events (event_time);
