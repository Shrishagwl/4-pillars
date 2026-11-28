/**
 * All settings come from environment variables so the same image runs locally,
 * in Docker Compose and on Cloud Run (which sets PORT for us).
 */
export interface Config {
  serviceName: string;
  version: string;
  port: number;
  host: string;
  logLevel: string;
  prettyLogs: boolean;
  /** Postgres, ingest schema. Empty = run without a database (tests, quick local runs). */
  databaseUrl: string;
  /** Local hand-off: the engine's base URL. */
  engineUrl: string;
  /** Cloud hand-off: projects/<project>/topics/meter-silent. Wins over engineUrl when set. */
  pubsubTopic: string;
  /** When set, write routes other than Telstra's callback need it in `x-api-key`. */
  adminApiKey: string;
}

export const SERVICE_NAME = 'ingest-api';
const DEFAULT_PORT = 8081;

function int(value: string | undefined, fallback: number): number {
  if (value === undefined || value === '') return fallback;
  const n = Number.parseInt(value, 10);
  if (Number.isNaN(n)) throw new Error(`Expected an integer, got "${value}"`);
  return n;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  return {
    serviceName: SERVICE_NAME,
    version: env.APP_VERSION ?? 'dev',
    port: int(env.PORT, DEFAULT_PORT),
    host: env.HOST ?? '0.0.0.0',
    logLevel: env.LOG_LEVEL ?? 'info',
    prettyLogs: env.LOG_PRETTY === 'true',
    databaseUrl: env.DATABASE_URL ?? '',
    engineUrl: env.ENGINE_URL ?? '',
    pubsubTopic: env.PUBSUB_TOPIC ?? '',
    adminApiKey: env.ADMIN_API_KEY ?? '',
  };
}
