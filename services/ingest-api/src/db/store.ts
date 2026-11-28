import { type MeterSilentEvent, type MonitoringEventReport, reasonGroup } from '@4p/contracts';
import type pg from 'pg';

/** A meter as the twin registers it and the engine reads it. */
export interface MeterRow {
  meterId: string;
  msisdn: string;
  transformerId: string;
  suburb: string;
  postcode: string;
  state: string;
  lat: number | null;
  lon: number | null;
}

/** Everything ingest-api reads and writes. Only touches the ingest schema. */
export class IngestStore {
  constructor(private readonly pool: pg.Pool) {}

  /**
   * Store LoC reports. A report Telstra already sent (same SIM, time and reason) is not stored
   * again, but it still comes back (with its original event id, `isNew: false`), so a retry
   * after a failed hand-off to the engine still reaches the engine. The engine drops repeats by
   * event id.
   */
  async addReports(
    subscriptionId: string,
    reports: MonitoringEventReport[],
    receivedAt: Date,
  ): Promise<Array<{ event: MeterSilentEvent; isNew: boolean }>> {
    const out: Array<{ event: MeterSilentEvent; isNew: boolean }> = [];
    for (const r of reports) {
      const eventTime = new Date(r.eventTime); // Telstra may send an offset like +08:00
      // The no-op update makes Postgres return the existing row on a conflict;
      // xmax = 0 is how Postgres says "this row was just inserted".
      const { rows } = await this.pool.query(
        `INSERT INTO ingest.loc_events (event_id, subscription_id, msisdn, reason_code, event_time, received_at)
         VALUES ($1, $2, $3, $4, $5, $6)
         ON CONFLICT (msisdn, event_time, reason_code) DO UPDATE SET msisdn = EXCLUDED.msisdn
         RETURNING event_id, received_at, (xmax = 0) AS is_new`,
        [
          crypto.randomUUID(),
          subscriptionId,
          r.msisdn,
          r.lossOfConnectReason,
          eventTime,
          receivedAt,
        ],
      );
      const row = rows[0];
      out.push({
        isNew: row.is_new,
        event: {
          eventId: row.event_id,
          subscriptionId,
          msisdn: r.msisdn,
          reasonCode: r.lossOfConnectReason,
          reasonGroup: reasonGroup(r.lossOfConnectReason),
          eventTime: eventTime.toISOString(),
          receivedAt: new Date(row.received_at).toISOString(),
        },
      });
    }
    return out;
  }

  /** Insert or update meters by meter id. */
  async upsertMeters(meters: MeterRow[]): Promise<number> {
    if (meters.length === 0) return 0;
    const res = await this.pool.query(
      `INSERT INTO ingest.meters (meter_id, msisdn, transformer_id, suburb, postcode, state, lat, lon)
       SELECT * FROM jsonb_to_recordset($1::jsonb) AS m(
         "meterId" text, msisdn text, "transformerId" text, suburb text, postcode text,
         state text, lat double precision, lon double precision)
       ON CONFLICT (meter_id) DO UPDATE SET
         msisdn = EXCLUDED.msisdn, transformer_id = EXCLUDED.transformer_id,
         suburb = EXCLUDED.suburb, postcode = EXCLUDED.postcode, state = EXCLUDED.state,
         lat = EXCLUDED.lat, lon = EXCLUDED.lon, updated_at = now()`,
      [JSON.stringify(meters)],
    );
    return res.rowCount ?? 0;
  }

  async listMeters(): Promise<MeterRow[]> {
    const { rows } = await this.pool.query<MeterRow>(
      `SELECT meter_id AS "meterId", msisdn, transformer_id AS "transformerId", suburb, postcode,
              state, lat, lon
       FROM ingest.meters ORDER BY meter_id`,
    );
    return rows;
  }

  /** Recent events, newest first. Used by the engine to catch up after a restart. */
  async eventsSince(since: Date, limit = 10_000): Promise<MeterSilentEvent[]> {
    const { rows } = await this.pool.query(
      `SELECT event_id, subscription_id, msisdn, reason_code, event_time, received_at
       FROM ingest.loc_events WHERE event_time >= $1 ORDER BY event_time LIMIT $2`,
      [since, limit],
    );
    return rows.map((r) => ({
      eventId: r.event_id,
      subscriptionId: r.subscription_id,
      msisdn: r.msisdn,
      reasonCode: r.reason_code,
      reasonGroup: reasonGroup(r.reason_code),
      eventTime: new Date(r.event_time).toISOString(),
      receivedAt: new Date(r.received_at).toISOString(),
    }));
  }
}
