import { randomUUID } from 'node:crypto';
import type { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import Fastify from 'fastify';
import type pg from 'pg';
import type { Config } from './config.js';
import { IngestStore } from './db/store.js';
import { loggerOptions } from './logger.js';
import { healthRoutes } from './routes/health.js';
import { locCallbackRoutes } from './routes/loc-callback.js';
import { meterRoutes } from './routes/meters.js';

export interface BuildOptions {
  /** Turn logging off in tests. */
  logger?: boolean;
  /** The ingest database. Left out in tests that don't need one. */
  db?: pg.Pool;
}

export async function buildApp(config: Config, opts: BuildOptions = {}) {
  const app = Fastify({
    logger: opts.logger === false ? false : loggerOptions(config),
    requestIdHeader: 'x-request-id',
    genReqId: () => randomUUID(),
  }).withTypeProvider<TypeBoxTypeProvider>();

  await app.register(healthRoutes, { service: config.serviceName, version: config.version });
  const store = opts.db ? new IngestStore(opts.db) : undefined;
  await app.register(locCallbackRoutes, { store });
  if (store) await app.register(meterRoutes, { store });

  return app;
}
