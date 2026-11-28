import pg from 'pg';
import { buildApp } from './app.js';
import { loadConfig } from './config.js';
import { migrate } from './db/migrate.js';

const config = loadConfig();
const db = config.databaseUrl
  ? new pg.Pool({ connectionString: config.databaseUrl, max: 5 })
  : undefined;
const app = await buildApp(config, { db });

// Bring the schema up to date before taking traffic. Safe to run on every start.
if (db) {
  const applied = await migrate(db);
  app.log.info({ applied }, applied.length ? 'migrations applied' : 'schema up to date');
} else {
  app.log.warn('DATABASE_URL is not set: running without a database');
}

// Cloud Run sends SIGTERM before stopping an instance; finish in-flight requests first.
for (const signal of ['SIGTERM', 'SIGINT'] as const) {
  process.once(signal, async () => {
    app.log.info({ signal }, 'shutting down');
    await app.close();
    await db?.end();
    process.exit(0);
  });
}

try {
  await app.listen({ port: config.port, host: config.host });
} catch (err) {
  app.log.error(err, 'failed to start');
  process.exit(1);
}
