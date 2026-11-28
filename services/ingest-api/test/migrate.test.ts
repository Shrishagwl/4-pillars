import pg from 'pg';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { migrate } from '../src/db/migrate.js';
import { MIGRATIONS } from '../src/db/migrations.js';

// Needs a real Postgres. CI provides one; locally: docker compose up postgres, then
// TEST_DATABASE_URL=postgres://pillars:pillars-local@localhost:5432/pillars npm test
const url = process.env.TEST_DATABASE_URL;

describe.skipIf(!url)('ingest migrations', () => {
  let pool: pg.Pool;

  beforeAll(async () => {
    pool = new pg.Pool({ connectionString: url });
    await pool.query('DROP SCHEMA IF EXISTS ingest CASCADE');
  });
  afterAll(() => pool?.end());

  it('creates the tables on a fresh database', async () => {
    expect(await migrate(pool)).toEqual(MIGRATIONS.map((m) => m.version));
    const { rows } = await pool.query(
      "SELECT table_name FROM information_schema.tables WHERE table_schema = 'ingest' ORDER BY 1",
    );
    expect(rows.map((r) => r.table_name)).toEqual(['loc_events', 'meters', 'schema_migrations']);
  });

  it('is idempotent: running it again changes nothing', async () => {
    expect(await migrate(pool)).toEqual([]);
  });

  it('several instances starting at once take turns', async () => {
    await pool.query('DROP SCHEMA ingest CASCADE');
    const results = await Promise.all([migrate(pool), migrate(pool), migrate(pool)]);
    expect(results.flat().sort()).toEqual(MIGRATIONS.map((m) => m.version));
  });

  it('ignores a duplicate LoC report', async () => {
    const insert = `INSERT INTO ingest.loc_events (event_id, subscription_id, msisdn, reason_code, event_time)
      VALUES (gen_random_uuid(), 's', '61412000001', 7, '2026-11-25T00:05:00Z') ON CONFLICT DO NOTHING`;
    await pool.query(insert);
    const second = await pool.query(insert);
    expect(second.rowCount).toBe(0);
  });

  it('rolls back a broken migration and leaves nothing half done', async () => {
    const broken = [
      ...MIGRATIONS,
      { version: 999, name: 'broken', sql: 'CREATE TABLE ingest.x (id int); SELECT nope;' },
    ];
    await expect(migrate(pool, broken)).rejects.toThrow(/migration 999/);
    const { rowCount } = await pool.query(
      "SELECT 1 FROM information_schema.tables WHERE table_name = 'x'",
    );
    expect(rowCount).toBe(0);
  });
});
