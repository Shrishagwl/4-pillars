import pg from 'pg';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { migrate } from '../src/db/migrate.js';
import { LOC_CALLBACK_PATH } from '../src/routes/loc-callback.js';

const url = process.env.TEST_DATABASE_URL;

const callback = (msisdn: string, reason: number, eventTime: string) => ({
  subscriptionId: 'sub-1',
  monitoringEventReports: [
    { monitoringType: 'LOSS_OF_CONNECTIVITY', msisdn, lossOfConnectReason: reason, eventTime },
  ],
});

describe.skipIf(!url)('ingest-api with a database', () => {
  let pool: pg.Pool;
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeAll(async () => {
    pool = new pg.Pool({ connectionString: url });
    await pool.query('DROP SCHEMA IF EXISTS ingest CASCADE');
    await migrate(pool);
    app = await buildApp(loadConfig({}), { logger: false, db: pool });
  });
  beforeEach(() => pool.query('TRUNCATE ingest.loc_events, ingest.meters'));
  afterAll(async () => {
    await app?.close();
    await pool?.end();
  });

  it('stores a LoC callback and answers 202', async () => {
    const res = await app.inject({
      method: 'POST',
      url: LOC_CALLBACK_PATH,
      payload: callback('61412000001', 0, '2028-01-31T00:15:00+08:00'), // the docs' example time
    });
    expect(res.statusCode).toBe(202);
    expect(res.json()).toEqual({ accepted: 1, duplicates: 0 });
    const { rows } = await pool.query(
      'SELECT msisdn, reason_code, event_time FROM ingest.loc_events',
    );
    expect(rows).toEqual([
      { msisdn: '61412000001', reason_code: 0, event_time: new Date('2028-01-30T16:15:00Z') },
    ]);
  });

  it('stores a repeated report only once', async () => {
    const body = callback('61412000001', 7, '2026-11-25T00:05:00Z');
    await app.inject({ method: 'POST', url: LOC_CALLBACK_PATH, payload: body });
    const again = await app.inject({ method: 'POST', url: LOC_CALLBACK_PATH, payload: body });
    expect(again.json()).toEqual({ accepted: 0, duplicates: 1 });
    expect((await pool.query('SELECT count(*)::int AS n FROM ingest.loc_events')).rows[0].n).toBe(
      1,
    );
  });

  it('answers 400 and stores nothing for a bad payload', async () => {
    const res = await app.inject({
      method: 'POST',
      url: LOC_CALLBACK_PATH,
      payload: callback('61412000001', 12, '2026-11-25T00:05:00Z'),
    });
    expect(res.statusCode).toBe(400);
    expect((await pool.query('SELECT count(*)::int AS n FROM ingest.loc_events')).rows[0].n).toBe(
      0,
    );
  });

  it('registers meters and lists them, updating on a second PUT', async () => {
    const meter = {
      meterId: 'M-0001',
      msisdn: '61412000001',
      transformerId: 'T-01',
      suburb: 'Coburg',
      postcode: '3058',
      lat: -37.745,
      lon: 144.962,
    };
    const put = (meters: unknown[]) =>
      app.inject({ method: 'PUT', url: '/meters', payload: { meters } });
    expect((await put([meter])).json()).toEqual({ saved: 1 });
    await put([{ ...meter, transformerId: 'T-02' }]);
    const list = (await app.inject({ method: 'GET', url: '/meters' })).json();
    expect(list.meters).toEqual([{ ...meter, transformerId: 'T-02', state: 'VIC' }]);
    expect((await put([{ ...meter, msisdn: '0412' }])).statusCode).toBe(400);
  });
});
