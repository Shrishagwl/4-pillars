import type pg from 'pg';
import { MIGRATIONS, type Migration } from './migrations.js';

// Any fixed number works; it just has to be the same for every ingest-api instance.
const LOCK_ID = 4_081;

/**
 * Brings the ingest schema up to date. Safe to run on every start and from several instances
 * at once: an advisory lock makes them take turns, and applied versions are skipped.
 * Returns the versions it applied this time.
 */
export async function migrate(
  pool: pg.Pool,
  migrations: Migration[] = MIGRATIONS,
): Promise<number[]> {
  const client = await pool.connect();
  try {
    await client.query('SELECT pg_advisory_lock($1)', [LOCK_ID]);
    // On Cloud SQL the schema is created by the database owner (infra/gcp/database.sql) and
    // this user may not be allowed to create schemas, so only create it when it is missing.
    const { rowCount } = await client.query("SELECT 1 FROM pg_namespace WHERE nspname = 'ingest'");
    if (!rowCount) await client.query('CREATE SCHEMA ingest');
    await client.query(`
      CREATE TABLE IF NOT EXISTS ingest.schema_migrations (
        version     integer PRIMARY KEY,
        name        text NOT NULL,
        applied_at  timestamptz NOT NULL DEFAULT now()
      )`);
    const done = new Set(
      (
        await client.query<{ version: number }>('SELECT version FROM ingest.schema_migrations')
      ).rows.map((r) => r.version),
    );

    const applied: number[] = [];
    for (const m of [...migrations].sort((a, b) => a.version - b.version)) {
      if (done.has(m.version)) continue;
      await client.query('BEGIN');
      try {
        await client.query(m.sql);
        await client.query('INSERT INTO ingest.schema_migrations (version, name) VALUES ($1, $2)', [
          m.version,
          m.name,
        ]);
        await client.query('COMMIT');
        applied.push(m.version);
      } catch (err) {
        await client.query('ROLLBACK');
        throw new Error(`migration ${m.version} (${m.name}) failed: ${(err as Error).message}`);
      }
    }
    return applied;
  } finally {
    await client.query('SELECT pg_advisory_unlock($1)', [LOCK_ID]).catch(() => {});
    client.release();
  }
}
