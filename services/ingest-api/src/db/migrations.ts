/**
 * ingest-api's tables, as numbered migrations. They live in TypeScript (not .sql files) so they
 * are compiled into dist/ and ship inside the Docker image with no extra copy step.
 *
 * Rules: never edit a migration that has been merged, add a new one instead. Each one runs once
 * per database, inside a transaction, and is recorded in ingest.schema_migrations.
 */
export interface Migration {
  version: number;
  name: string;
  sql: string;
}

export const MIGRATIONS: Migration[] = [
  {
    version: 1,
    name: 'meters and loc events',
    sql: `
      -- Every meter we monitor, so a SIM number can be turned into a meter, transformer and place.
      CREATE TABLE ingest.meters (
        meter_id        text PRIMARY KEY,
        msisdn          text NOT NULL UNIQUE,
        transformer_id  text NOT NULL,
        suburb          text NOT NULL,
        postcode        text NOT NULL,
        state           text NOT NULL DEFAULT 'VIC',
        lat             double precision,
        lon             double precision,
        updated_at      timestamptz NOT NULL DEFAULT now()
      );
      CREATE INDEX meters_transformer_idx ON ingest.meters (transformer_id);

      -- One row per LoC report Telstra (or telstra-fake) sent us.
      CREATE TABLE ingest.loc_events (
        id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        event_id         uuid NOT NULL UNIQUE,
        subscription_id  text NOT NULL,
        msisdn           text NOT NULL,
        reason_code      smallint NOT NULL CHECK (reason_code BETWEEN 0 AND 8),
        event_time       timestamptz NOT NULL,
        received_at      timestamptz NOT NULL DEFAULT now(),
        -- Telstra may send the same report twice; the second copy is ignored.
        UNIQUE (msisdn, event_time, reason_code)
      );
      CREATE INDEX loc_events_time_idx ON ingest.loc_events (event_time);
    `,
  },
];
