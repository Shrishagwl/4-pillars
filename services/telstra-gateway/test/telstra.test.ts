import { afterEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';

interface Seen {
  url: string;
  method: string;
  headers: Record<string, string>;
  body?: string;
}

/**
 * A pretend Telstra: answers the token call, then hands out the queued answers in order.
 * Records every request so the tests can check headers and paths.
 */
function fakeTelstra(answers: Array<{ status: number; body?: unknown } | 'network-error'>) {
  const seen: Seen[] = [];
  let tokens = 0;
  const fetchImpl = (async (input: string | URL, init: RequestInit = {}) => {
    const url = String(input);
    const headers = Object.fromEntries(
      Object.entries((init.headers ?? {}) as Record<string, string>),
    );
    seen.push({ url, method: init.method ?? 'GET', headers, body: init.body?.toString() });
    if (url.endsWith('/openid-connect/token')) {
      tokens++;
      return Response.json({
        access_token: `token-${tokens}`,
        token_type: 'Bearer',
        expires_in: 3600,
      });
    }
    const next = answers.shift() ?? { status: 500 };
    if (next === 'network-error') throw new TypeError('fetch failed');
    return new Response(next.body === undefined ? null : JSON.stringify(next.body), {
      status: next.status,
    });
  }) as typeof fetch;
  return { fetchImpl, seen, tokenCalls: () => tokens };
}

const OUTAGE = {
  'correlation-id': 'x',
  status: 200,
  timeStamp: 1,
  past: [],
  near_future: [],
  far_future: [],
  current: [
    {
      state: 'VIC',
      suburb: 'COBURG',
      postcode: '3058',
      start_timestamp: '2026-11-25 11:05:00 Australia/Melbourne',
      end_timestamp: null,
      root_cause: 'Telstra Network (Hardware/Software/Config)',
      duration: 300,
      description: 'x',
      is_planned: false,
      technology: '4G',
      affected_area: 'MULTIPOLYGON(((144.95 -37.75,144.97 -37.75,144.97 -37.74,144.95 -37.75)))',
    },
  ],
};
const QUERY = '/v1/network-availability?suburb=Coburg&state=VIC&postcode=3058';

describe('telstra-gateway', () => {
  let app: Awaited<ReturnType<typeof buildApp>> | undefined;
  afterEach(() => app?.close());

  async function start(t: ReturnType<typeof fakeTelstra>, now = () => 0) {
    app = await buildApp(loadConfig({ TELSTRA_BASE_URL: 'http://fake:8083' }), {
      logger: false,
      fetch: t.fetchImpl,
      sleep: async () => {},
      now,
    });
    return app;
  }

  it('sends every header Telstra requires, with a fresh UUID correlation id', async () => {
    const t = fakeTelstra([{ status: 200, body: OUTAGE }]);
    await (await start(t)).inject({
      method: 'GET',
      url: QUERY,
      headers: { 'x-incident-id': 'inc-0001' },
    });
    const call = t.seen[1] as Seen;
    expect(call.url).toBe(
      'http://fake:8083/network-availability/v1/status?suburb=Coburg&state=VIC&postcode=3058',
    );
    expect(call.headers).toMatchObject({
      authorization: 'Bearer token-1',
      accept: 'application/json',
      'accept-charset': 'utf-8',
      'content-language': 'en-AU',
      'content-type': 'application/json',
    });
    expect(call.headers['correlation-id']).toMatch(
      /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/,
    );
    // The token request used Telstra's token path and client credentials.
    expect(t.seen[0]?.url).toBe(
      'http://fake:8083/og-network-auth-prod/api/realms/network-auth/protocol/openid-connect/token',
    );
    expect(t.seen[0]?.body).toContain('grant_type=client_credentials');
  });

  it('converts Melbourne timestamps to UTC and keeps the outage fields', async () => {
    const t = fakeTelstra([{ status: 200, body: OUTAGE }]);
    const res = await (await start(t)).inject({ method: 'GET', url: QUERY });
    const body = res.json();
    expect(body.outages.current[0]).toMatchObject({
      start: '2026-11-25T00:05:00.000Z',
      end: null,
      start_timestamp: '2026-11-25 11:05:00 Australia/Melbourne',
      affected_area: expect.stringMatching(/^MULTIPOLYGON/),
    });
    expect(body.cached).toBe(false);
  });

  it('caches each suburb for a minute', async () => {
    const t = fakeTelstra([
      { status: 200, body: OUTAGE },
      { status: 200, body: OUTAGE },
    ]);
    let clock = 0;
    const gw = await start(t, () => clock);
    await gw.inject({ method: 'GET', url: QUERY });
    clock = 30_000;
    expect(
      (await gw.inject({ method: 'GET', url: QUERY.replace('Coburg', 'COBURG') })).json().cached,
    ).toBe(true);
    clock = 61_000;
    expect((await gw.inject({ method: 'GET', url: QUERY })).json().cached).toBe(false);
    expect(t.seen.filter((s) => s.url.includes('/status')).length).toBe(2);
  });

  it('retries throttling, server errors and network failures, then gives up with 502', async () => {
    const t = fakeTelstra([{ status: 429 }, 'network-error', { status: 200, body: OUTAGE }]);
    const res = await (await start(t)).inject({ method: 'GET', url: QUERY });
    expect(res.statusCode).toBe(200);
    const statusCalls = t.seen.filter((s) => s.url.includes('/status'));
    expect(statusCalls).toHaveLength(3);
    // Same correlation id across the retries of one call.
    expect(new Set(statusCalls.map((s) => s.headers['correlation-id'])).size).toBe(1);

    const down = fakeTelstra([{ status: 503 }, { status: 503 }, { status: 503 }]);
    app?.close();
    const failed = await (await start(down)).inject({ method: 'GET', url: QUERY });
    expect(failed.statusCode).toBe(502);
    expect(failed.json()).toEqual({ error: 'TELSTRA_UNAVAILABLE', api: 'network-availability' });
  });

  it('gets a new token once when Telstra says the old one is invalid', async () => {
    const t = fakeTelstra([{ status: 401 }, { status: 200, body: OUTAGE }]);
    const res = await (await start(t)).inject({ method: 'GET', url: QUERY });
    expect(res.statusCode).toBe(200);
    expect(t.tokenCalls()).toBe(2);
  });

  it('passes Telstra 4xx errors straight through', async () => {
    const error = { errors: [{ code: 'FIELD_INVALID', issue: 'state', suggested_action: 'x' }] };
    const t = fakeTelstra([{ status: 400, body: error }]);
    const res = await (await start(t)).inject({ method: 'GET', url: QUERY });
    expect(res.statusCode).toBe(400);
    expect(res.json()).toEqual(error);
  });

  it('asks Location Verification in CAMARA shape and returns the answer', async () => {
    const t = fakeTelstra([
      {
        status: 200,
        body: { verificationResult: 'FALSE', lastLocationTime: '2026-11-25T00:09:00Z' },
      },
    ]);
    const res = await (await start(t)).inject({
      method: 'POST',
      url: '/v1/location-verification',
      headers: { 'x-incident-id': 'inc-0007' },
      payload: { msisdn: '61412000001', latitude: -37.745, longitude: 144.962 },
    });
    expect(res.json()).toEqual({
      msisdn: '61412000001',
      verificationResult: 'FALSE',
      lastLocationTime: '2026-11-25T00:09:00Z',
    });
    const call = t.seen[1] as Seen;
    expect(call.url).toBe('http://fake:8083/location-verification/verify');
    expect(JSON.parse(call.body as string)).toEqual({
      device: { phoneNumber: '+61412000001' },
      area: { areaType: 'CIRCLE', center: { latitude: -37.745, longitude: 144.962 }, radius: 1000 },
    });
  });

  it("turns can't-locate into a null result instead of an error", async () => {
    const t = fakeTelstra([
      {
        status: 422,
        body: { status: 422, code: 'LOCATION_VERIFICATION.UNABLE_TO_LOCATE', message: 'x' },
      },
    ]);
    const res = await (await start(t)).inject({
      method: 'POST',
      url: '/v1/location-verification',
      payload: { msisdn: '61412000001', latitude: -37.745, longitude: 144.962 },
    });
    expect(res.json()).toEqual({
      msisdn: '61412000001',
      verificationResult: null,
      error: 'LOCATION_VERIFICATION.UNABLE_TO_LOCATE',
    });
  });

  it('subscribes SIMs to Loss of Connectivity in the documented body', async () => {
    const t = fakeTelstra([{ status: 201, body: { status: 201, subscriptions: [] } }]);
    const res = await (await start(t)).inject({
      method: 'POST',
      url: '/v1/loss-of-connectivity/subscriptions',
      payload: {
        msisdns: ['61412000001'],
        callbackUrl: 'http://ingest:8081/loss-of-connectivity/v0/events',
      },
    });
    expect(res.statusCode).toBe(201);
    const call = t.seen[1] as Seen;
    expect(call.url).toBe('http://fake:8083/loss-of-connectivity/v0/subscriptions');
    expect(JSON.parse(call.body as string)).toEqual({
      monitoringType: 'LOSS_OF_CONNECTIVITY',
      subscriptions: [
        {
          msisdn: ['61412000001'],
          notificationDestination: 'http://ingest:8081/loss-of-connectivity/v0/events',
        },
      ],
    });
  });

  it('builds the real Telstra URLs from config', () => {
    const real = loadConfig({
      TELSTRA_BASE_URL: 'https://prod.okapi.ogw.evolve.okapi.telstra.com/mobility/products-api',
      TELSTRA_LOCATION_BASE_URL:
        'https://prod.okapi.ogw.evolve.okapi.telstra.com/telstradev/v1/sandbox',
    });
    expect(real.authUrl).toBe(
      'https://prod.okapi.ogw.evolve.okapi.telstra.com/og-network-auth-prod/api/realms/network-auth/protocol/openid-connect/token',
    );
    expect(real.locationBaseUrl).toContain('/telstradev/v1/sandbox');
  });
});
