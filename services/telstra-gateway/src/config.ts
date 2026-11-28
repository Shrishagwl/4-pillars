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
  /** Base for Loss of Connectivity and Network Availability: telstra-fake by default. */
  telstraBaseUrl: string;
  /** Base for Location Verification (Telstra serves it from its sandbox path). */
  locationBaseUrl: string;
  /** OAuth2 token URL. Defaults to Telstra's token path on the base URL's host. */
  authUrl: string;
  clientId: string;
  clientSecret: string;
  scopes: string;
  /** "v0" in the OpenAPI file, "v1" on the Getting Started page. */
  locApiVersion: 'v0' | 'v1';
  /** How long a suburb's Network Availability answer is reused. */
  outageCacheMs: number;
  timeoutMs: number;
  /** Attempts per call, including the first. */
  maxAttempts: number;
}

export const SERVICE_NAME = 'telstra-gateway';
const DEFAULT_PORT = 8082;
export const TOKEN_PATH =
  '/og-network-auth-prod/api/realms/network-auth/protocol/openid-connect/token';
const DEFAULT_SCOPES = [
  'iot-naap-network-availability:read',
  'iot-naap-loss-of-connectivity:read',
  'iot-naap-loss-of-connectivity:write',
].join(' ');

function int(value: string | undefined, fallback: number): number {
  if (value === undefined || value === '') return fallback;
  const n = Number.parseInt(value, 10);
  if (Number.isNaN(n)) throw new Error(`Expected an integer, got "${value}"`);
  return n;
}

export function loadConfig(env: NodeJS.ProcessEnv = process.env): Config {
  const telstraBaseUrl = (env.TELSTRA_BASE_URL || 'http://localhost:8083').replace(/\/$/, '');
  return {
    serviceName: SERVICE_NAME,
    version: env.APP_VERSION ?? 'dev',
    port: int(env.PORT, DEFAULT_PORT),
    host: env.HOST ?? '0.0.0.0',
    logLevel: env.LOG_LEVEL ?? 'info',
    prettyLogs: env.LOG_PRETTY === 'true',
    telstraBaseUrl,
    locationBaseUrl: (env.TELSTRA_LOCATION_BASE_URL || telstraBaseUrl).replace(/\/$/, ''),
    authUrl: env.TELSTRA_AUTH_URL || new URL(telstraBaseUrl).origin + TOKEN_PATH,
    // telstra-fake takes any id and secret; real ones come from Secret Manager (#36).
    clientId: env.TELSTRA_CLIENT_ID || 'local',
    clientSecret: env.TELSTRA_CLIENT_SECRET || 'local',
    scopes: env.TELSTRA_SCOPES || DEFAULT_SCOPES,
    locApiVersion: env.TELSTRA_LOC_VERSION === 'v1' ? 'v1' : 'v0',
    outageCacheMs: int(env.OUTAGE_CACHE_MS, 60_000),
    timeoutMs: int(env.TELSTRA_TIMEOUT_MS, 5000),
    maxAttempts: int(env.TELSTRA_MAX_ATTEMPTS, 3),
  };
}
