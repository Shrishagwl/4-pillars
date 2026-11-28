-- One row per incident the engine has opened. Updated as the incident grows or closes.
CREATE TABLE engine.incidents (
    incident_id      text PRIMARY KEY,
    opened_at        timestamptz NOT NULL,  -- when the first meter in it went silent
    updated_at       timestamptz NOT NULL,
    closed_at        timestamptz,           -- null while open
    meter_ids        text[] NOT NULL,
    transformer_ids  text[] NOT NULL,
    suburbs          text[] NOT NULL
);
CREATE INDEX incidents_open_idx ON engine.incidents (closed_at) WHERE closed_at IS NULL;

-- Every verdict the engine gave, newest last, so the dashboard can show how it changed.
CREATE TABLE engine.verdicts (
    id             bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    incident_id    text NOT NULL REFERENCES engine.incidents (incident_id) ON DELETE CASCADE,
    meter_count    integer NOT NULL CHECK (meter_count >= 1),
    cause          text NOT NULL CHECK (cause IN ('POWER', 'NETWORK', 'METER_FAULT', 'TAMPER')),
    confidence     double precision NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    probabilities  jsonb NOT NULL,
    action         text NOT NULL,
    evidence       jsonb NOT NULL,
    summary        text,
    notice         text,
    created_at     timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX verdicts_incident_idx ON engine.verdicts (incident_id, id DESC);
