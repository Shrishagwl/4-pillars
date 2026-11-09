import { randomUUID } from 'node:crypto';
import type { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import Fastify from 'fastify';
import type { Config } from './config.js';
import { loggerOptions } from './logger.js';
import { healthRoutes } from './routes/health.js';
import { locCallbackRoutes } from './routes/loc-callback.js';

export interface BuildOptions {
  /** Turn logging off in tests. */
  logger?: boolean;
}

export async function buildApp(config: Config, opts: BuildOptions = {}) {
  const app = Fastify({
    logger: opts.logger === false ? false : loggerOptions(config),
    requestIdHeader: 'x-request-id',
    genReqId: () => randomUUID(),
  }).withTypeProvider<TypeBoxTypeProvider>();

  await app.register(healthRoutes, { service: config.serviceName, version: config.version });
  await app.register(locCallbackRoutes);

  return app;
}
