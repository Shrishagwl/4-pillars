import { afterEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { toDashboard } from '../src/routes/incidents.js';

const ENGINE_INCIDENT = {
  incidentId: 'inc-0001',
  meterCount: 3,
  probabilities: { POWER: 0.9, NETWORK: 0.05, METER_FAULT: 0.03, TAMPER: 0.02 },
  cause: 'POWER',
  confidence: 0.9,
  action: 'DISPATCH_POWER_CREW',
  evidence: ['Meters: 3 silent'],
  updatedAt: '2026-11-25T00:06:00+00:00',
  summary: '3 meters went silent.',
  notice: 'We are aware of a power outage in your area.',
  openedAt: '2026-11-25T00:05:00+00:00',
  closedAt: null,
  meterIds: ['M-1', 'M-2', 'M-3'],
  transformerIds: ['T-05'],
  suburbs: ['Brunswick', 'Coburg'],
};

const meter = (meterId: string, suburb: string, postcode: string) => ({
  meterId,
  msisdn: '61412000001',
  transformerId: 'T-05',
  suburb,
  postcode,
  state: 'VIC',
  lat: null,
  lon: null,
});

/** A pretend engine whose incident list the test can change. */
function fakeEngine() {
  const state = { incidents: [ENGINE_INCIDENT] as unknown[], up: true, calls: 0 };
  const fetchImpl = (async () => {
    state.calls++;
    if (!state.up) return new Response(null, { status: 503 });
    return Response.json({ incidents: state.incidents });
  }) as unknown as typeof fetch;
  return { state, fetchImpl };
}

describe('dashboard incidents', () => {
  let app: Awaited<ReturnType<typeof buildApp>> | undefined;
  afterEach(() => app?.close());

  it('reshapes engine incidents into the dashboard Incident and picks the main suburb', () => {
    const meters = [
      meter('M-1', 'Coburg', '3058'),
      meter('M-2', 'Coburg', '3058'),
      meter('M-3', 'Brunswick', '3056'),
    ];
    const [incident] = toDashboard([ENGINE_INCIDENT as never], meters);
    expect(incident).toEqual({
      incidentId: 'inc-0001',
      meterCount: 3,
      probabilities: ENGINE_INCIDENT.probabilities,
      cause: 'POWER',
      confidence: 0.9,
      action: 'DISPATCH_POWER_CREW',
      evidence: ['Meters: 3 silent'],
      updatedAt: ENGINE_INCIDENT.updatedAt,
      summary: ENGINE_INCIDENT.summary,
      notice: ENGINE_INCIDENT.notice,
      suburb: 'Coburg',
      postcode: '3058',
      transformerIds: ['T-05'],
      meterIds: ['M-1', 'M-2', 'M-3'],
      openedAt: ENGINE_INCIDENT.openedAt,
    });
    // Closed incidents don't go to the dashboard.
    expect(toDashboard([{ ...ENGINE_INCIDENT, closedAt: 'x' } as never], meters)).toEqual([]);
  });

  it('GET /incidents serves them to the browser, or 502 when the engine is down', async () => {
    const engine = fakeEngine();
    app = await buildApp(loadConfig({ ENGINE_URL: 'http://engine:8084' }), {
      logger: false,
      fetch: engine.fetchImpl,
    });
    const res = await app.inject({ method: 'GET', url: '/incidents' });
    expect(res.statusCode).toBe(200);
    expect(res.headers['access-control-allow-origin']).toBe('*');
    expect(res.json().incidents[0]).toMatchObject({ incidentId: 'inc-0001', suburb: 'Brunswick' });
    engine.state.up = false;
    expect((await app.inject({ method: 'GET', url: '/incidents' })).statusCode).toBe(502);
  });

  it('the live stream pushes the list when it changes, without a refresh', async () => {
    const engine = fakeEngine();
    app = await buildApp(loadConfig({ ENGINE_URL: 'http://engine:8084' }), {
      logger: false,
      fetch: engine.fetchImpl,
    });
    await app.listen({ port: 0, host: '127.0.0.1' });
    const { port } = app.server.address() as { port: number };

    const controller = new AbortController();
    const res = await fetch(`http://127.0.0.1:${port}/incidents/stream`, {
      signal: controller.signal,
    });
    expect(res.headers.get('content-type')).toBe('text/event-stream');
    const reader = (res.body as ReadableStream<Uint8Array>).getReader();
    const decoder = new TextDecoder();
    const nextEvent = async () => {
      let text = '';
      while (!text.includes('event: incidents'))
        text += decoder.decode((await reader.read()).value);
      return JSON.parse(text.split('data: ')[1]?.split('\n')[0] as string);
    };

    expect((await nextEvent()).map((i: { incidentId: string }) => i.incidentId)).toEqual([
      'inc-0001',
    ]);
    engine.state.incidents = [
      ENGINE_INCIDENT,
      { ...ENGINE_INCIDENT, incidentId: 'inc-0002', openedAt: '2026-11-25T00:09:00+00:00' },
    ];
    const updated = await nextEvent(); // arrives on the next poll, no new request
    expect(updated.map((i: { incidentId: string }) => i.incidentId)).toEqual([
      'inc-0002',
      'inc-0001',
    ]);
    controller.abort();
  }, 10_000);
});
