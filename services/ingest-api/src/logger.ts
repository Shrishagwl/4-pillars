import type { FastifyServerOptions } from 'fastify';
import type { Config } from './config.js';

/** pino level -> Cloud Logging severity, so logs are filterable in the GCP console. */
const SEVERITY: Record<string, string> = {
  trace: 'DEBUG',
  debug: 'DEBUG',
  info: 'INFO',
  warn: 'WARNING',
  error: 'ERROR',
  fatal: 'CRITICAL',
};

export function loggerOptions(config: Config): FastifyServerOptions['logger'] {
  if (config.prettyLogs) {
    return { level: config.logLevel, transport: { target: 'pino-pretty' } };
  }
  return {
    level: config.logLevel,
    messageKey: 'message',
    base: { service: config.serviceName, version: config.version },
    formatters: {
      level: (label) => ({ severity: SEVERITY[label] ?? 'DEFAULT' }),
    },
  };
}
