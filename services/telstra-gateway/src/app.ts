import { randomUUID } from 'node:crypto';
import type { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import Fastify from 'fastify';
import type { Config } from './config.js';
import { TelstraClient } from './lib/telstra-client.js';
import { loggerOptions } from './logger.js';
import { healthRoutes } from './routes/health.js';
import { telstraRoutes } from './routes/telstra.js';

export interface BuildOptions {
  /** Turn logging off in tests. */
  logger?: boolean;
  /** Tests pass a fake fetch and a clock. */
  fetch?: typeof fetch;
  sleep?: (ms: number) => Promise<void>;
  now?: () => number;
}

export async function buildApp(config: Config, opts: BuildOptions = {}) {
  const app = Fastify({
    logger: opts.logger === false ? false : loggerOptions(config),
    requestIdHeader: 'x-request-id',
    genReqId: () => randomUUID(),
  }).withTypeProvider<TypeBoxTypeProvider>();

  await app.register(healthRoutes, { service: config.serviceName, version: config.version });
  const client = new TelstraClient(config, app.log, opts.fetch, opts.sleep);
  await app.register(telstraRoutes, { config, client, now: opts.now });

  return app;
}
