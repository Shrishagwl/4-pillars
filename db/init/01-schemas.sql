-- One Postgres database, one schema per service that keeps data.
-- Each service only reads and writes its own schema (set through search_path in DATABASE_URL).
CREATE SCHEMA IF NOT EXISTS ingest;  -- meters, LoC events (ingest-api)
CREATE SCHEMA IF NOT EXISTS engine;  -- incidents, verdicts (engine)
CREATE SCHEMA IF NOT EXISTS twin;    -- saved runs and ground truth (twin)
