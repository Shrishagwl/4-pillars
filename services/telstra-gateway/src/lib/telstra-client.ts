import type { FastifyBaseLogger } from 'fastify';
import type { Config } from '../config.js';
import { authHeaders } from './google-id-token.js';

export interface CallOptions {
  /** Which API, for the log line: "loc", "network-availability", "location-verification". */
  api: string;
  method: 'GET' | 'POST' | 'DELETE';
  url: string;
  query?: Record<string, string | number | undefined>;
  body?: unknown;
  /** The engine passes the incident it is working on, so each call can be traced back to it. */
  incidentId?: string;
}

export interface TelstraResponse {
  status: number;
  body: unknown;
  correlationId: string;
}

type Fetch = typeof fetch;
type Sleep = (ms: number) => Promise<void>;

const RETRY_STATUSES = new Set([429, 500, 502, 503, 504]);

/**
 * The only code that talks to Telstra (or telstra-fake). It gets and caches the OAuth token,
 * sends the headers every Telstra API requires, retries throttling, server errors and network
 * failures with exponential backoff, and logs one line per call with the incident id.
 */
export class TelstraClient {
  private token: { value: string; expiresAt: number } | null = null;

  constructor(
    private readonly config: Config,
    private readonly log: FastifyBaseLogger,
    private readonly fetchImpl: Fetch = fetch,
    private readonly sleep: Sleep = (ms) => new Promise((r) => setTimeout(r, ms)),
  ) {}

  async call(opts: CallOptions): Promise<TelstraResponse> {
    const url = new URL(opts.url);
    for (const [k, v] of Object.entries(opts.query ?? {})) {
      if (v !== undefined) url.searchParams.set(k, String(v));
    }
    const correlationId = crypto.randomUUID(); // one per logical call, kept across retries
    const started = Date.now();
    let lastError: unknown = null;
    let refreshedToken = false;

    for (let attempt = 1; attempt <= this.config.maxAttempts; attempt++) {
      try {
        const res = await this.fetchImpl(url, {
          method: opts.method,
          headers: {
            authorization: `Bearer ${await this.accessToken()}`,
            accept: 'application/json',
            'accept-charset': 'utf-8',
            'content-language': 'en-AU',
            'content-type': 'application/json',
            'correlation-id': correlationId,
            ...(await authHeaders(url.toString())),
          },
          body: opts.body === undefined ? undefined : JSON.stringify(opts.body),
          signal: AbortSignal.timeout(this.config.timeoutMs),
        });
        // An expired token: get a new one and try again straight away, once.
        if (res.status === 401 && !refreshedToken) {
          refreshedToken = true;
          this.token = null;
          attempt--;
          continue;
        }
        if (RETRY_STATUSES.has(res.status)) {
          lastError = new Error(`HTTP ${res.status}`);
          if (attempt < this.config.maxAttempts) {
            await this.sleep(this.backoff(attempt, res.headers.get('retry-after')));
          }
          continue; // after the last attempt this falls through to "unavailable" below
        }
        const text = await res.text();
        const body = text ? safeJson(text) : null;
        this.logCall(opts, url, res.status, attempt, started, correlationId);
        return { status: res.status, body, correlationId };
      } catch (err) {
        lastError = err;
        if (attempt < this.config.maxAttempts) await this.sleep(this.backoff(attempt, null));
      }
    }
    this.logCall(opts, url, null, this.config.maxAttempts, started, correlationId, lastError);
    throw new TelstraUnavailable(opts.api, lastError);
  }

  /** 200 ms, 400 ms, 800 ms ... plus up to 100 ms of jitter, or what Retry-After asks for. */
  private backoff(attempt: number, retryAfter: string | null): number {
    const asked = retryAfter ? Number.parseInt(retryAfter, 10) * 1000 : Number.NaN;
    if (!Number.isNaN(asked)) return Math.min(asked, 10_000);
    return 200 * 2 ** (attempt - 1) + Math.floor(Math.random() * 100);
  }

  private async accessToken(): Promise<string> {
    // Refresh a minute early so a token never expires halfway through a call.
    if (this.token && this.token.expiresAt - 60_000 > Date.now()) return this.token.value;
    const res = await this.fetchImpl(this.config.authUrl, {
      method: 'POST',
      headers: {
        'content-type': 'application/x-www-form-urlencoded',
        ...(await authHeaders(this.config.authUrl)),
      },
      body: new URLSearchParams({
        grant_type: 'client_credentials',
        client_id: this.config.clientId,
        client_secret: this.config.clientSecret,
        scope: this.config.scopes,
      }),
      signal: AbortSignal.timeout(this.config.timeoutMs),
    });
    if (!res.ok) throw new Error(`token endpoint answered ${res.status}`);
    const body = (await res.json()) as { access_token: string; expires_in?: number };
    this.token = {
      value: body.access_token,
      expiresAt: Date.now() + (body.expires_in ?? 300) * 1000,
    };
    return this.token.value;
  }

  private logCall(
    opts: CallOptions,
    url: URL,
    status: number | null,
    attempts: number,
    started: number,
    correlationId: string,
    err?: unknown,
  ) {
    const line = {
      api: opts.api,
      method: opts.method,
      path: url.pathname, // never the query string or headers: no tokens or secrets in logs
      status,
      attempts,
      ms: Date.now() - started,
      correlationId,
      incidentId: opts.incidentId ?? null,
    };
    if (status === null) this.log.error({ ...line, err: String(err) }, 'telstra call failed');
    else this.log.info(line, 'telstra call');
  }
}

export class TelstraUnavailable extends Error {
  constructor(
    readonly api: string,
    cause: unknown,
  ) {
    super(`${api} did not answer: ${String(cause)}`);
  }
}

function safeJson(text: string): unknown {
  try {
    return JSON.parse(text);
  } catch {
    return text;
  }
}
