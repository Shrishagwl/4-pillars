import { randomUUID } from 'node:crypto';
import type { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import Fastify from 'fastify';
import type { Config } from './config.js';
import { LocStore } from './lib/loc-store.js';
import { loggerOptions } from './logger.js';
import { healthRoutes } from './routes/health.js';
import { lossOfConnectivityRoutes } from './routes/loss-of-connectivity.js';
import { tokenRoutes } from './routes/token.js';

export interface BuildOptions {
  /** Turn logging off in tests. */
  logger?: boolean;
  /** Pass one in to look inside it from a test. */
  locStore?: LocStore;
}

export async function buildApp(config: Config, opts: BuildOptions = {}) {
  const app = Fastify({
    logger: opts.logger === false ? false : loggerOptions(config),
    requestIdHeader: 'x-request-id',
    genReqId: () => randomUUID(),
  }).withTypeProvider<TypeBoxTypeProvider>();

  await app.register(healthRoutes, { service: config.serviceName, version: config.version });
  await app.register(tokenRoutes);
  await app.register(lossOfConnectivityRoutes, { store: opts.locStore ?? new LocStore() });

  return app;
}
