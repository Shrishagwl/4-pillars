-- Run once as the database owner using psql, against the dedicated pillars database.
-- Set passwords interactively afterward with \password; never put them in this file.
\set ON_ERROR_STOP on
BEGIN;
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pillars_ingest') THEN
    CREATE ROLE pillars_ingest LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pillars_engine') THEN
    CREATE ROLE pillars_engine LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE;
  END IF;
END
$$;
CREATE SCHEMA IF NOT EXISTS ingest AUTHORIZATION pillars_ingest;
CREATE SCHEMA IF NOT EXISTS engine AUTHORIZATION pillars_engine;
ALTER SCHEMA ingest OWNER TO pillars_ingest;
ALTER SCHEMA engine OWNER TO pillars_engine;
REVOKE ALL ON SCHEMA ingest FROM PUBLIC;
REVOKE ALL ON SCHEMA engine FROM PUBLIC;
REVOKE ALL ON SCHEMA ingest FROM pillars_engine;
REVOKE ALL ON SCHEMA engine FROM pillars_ingest;
ALTER ROLE pillars_ingest SET search_path = ingest;
ALTER ROLE pillars_engine SET search_path = engine;
COMMIT;
