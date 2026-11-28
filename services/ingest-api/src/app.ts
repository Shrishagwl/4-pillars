import { randomUUID } from 'node:crypto';
import type { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import Fastify from 'fastify';
import type pg from 'pg';
import type { Config } from './config.js';
import { IngestStore } from './db/store.js';
import { loggerOptions } from './logger.js';
import { type Publisher, publisherFromEnv } from './publisher.js';
import { healthRoutes } from './routes/health.js';
import { incidentRoutes } from './routes/incidents.js';
import { locCallbackRoutes } from './routes/loc-callback.js';
import { meterRoutes } from './routes/meters.js';

export interface BuildOptions {
  /** Turn logging off in tests. */
  logger?: boolean;
  /** The ingest database. Left out in tests that don't need one. */
  db?: pg.Pool;
  /** Where events go after they are stored. Defaults to what the config says. */
  publisher?: Publisher;
  /** Tests pass a fake fetch for calls to the engine. */
  fetch?: typeof fetch;
}

export async function buildApp(config: Config, opts: BuildOptions = {}) {
  const app = Fastify({
    logger: opts.logger === false ? false : loggerOptions(config),
    requestIdHeader: 'x-request-id',
    genReqId: () => randomUUID(),
  }).withTypeProvider<TypeBoxTypeProvider>();

  await app.register(healthRoutes, { service: config.serviceName, version: config.version });
  const store = opts.db ? new IngestStore(opts.db) : undefined;
  const publisher = opts.publisher ?? publisherFromEnv(config);
  app.log.info({ publisher: publisher?.kind ?? 'none' }, 'event hand-off');
  await app.register(locCallbackRoutes, { store, publisher });
  if (store) await app.register(meterRoutes, { store, apiKey: config.adminApiKey });
  if (config.engineUrl) {
    await app.register(incidentRoutes, { engineUrl: config.engineUrl, store, fetch: opts.fetch });
  }

  return app;
}
