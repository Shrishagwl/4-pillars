import { LocCallback } from '@4p/contracts';
import type { TypeBoxTypeProvider } from '@fastify/type-provider-typebox';
import Fastify from 'fastify';
import { afterAll, beforeAll, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { LOC_TRIGGER_PATH } from '../src/routes/loss-of-connectivity.js';
import { TOKEN_PATH } from '../src/routes/token.js';

const HEADERS = {
  authorization: 'Bearer test-token',
  accept: 'application/json',
  'accept-charset': 'utf-8',
  'content-language': 'en-AU',
  'content-type': 'application/json',
  'correlation-id': '550e8400-e29b-41d4-a716-446655440000',
};
const SUBS = '/loss-of-connectivity/v0/subscriptions';

// Stands in for ingest-api: validates callbacks with the same LocCallback schema and answers 202.
async function startReceiver() {
  const received: LocCallback[] = [];
  const server = Fastify().withTypeProvider<TypeBoxTypeProvider>();
  server.post(
    '/loss-of-connectivity/v0/events',
    { schema: { body: LocCallback } },
    async (req, reply) => {
      received.push(req.body);
      return reply.code(202).send({ accepted: req.body.monitoringEventReports.length });
    },
  );
  await server.listen({ port: 0, host: '127.0.0.1' });
  const { port } = server.server.address() as { port: number };
  return { server, received, url: `http://127.0.0.1:${port}/loss-of-connectivity/v0/events` };
}

describe('fake Loss of Connectivity API', () => {
  let app: Awaited<ReturnType<typeof buildApp>>;
  let receiver: Awaited<ReturnType<typeof startReceiver>>;

  beforeAll(async () => {
    receiver = await startReceiver();
  });
  beforeEach(async () => {
    app = await buildApp(loadConfig({}), { logger: false });
    receiver.received.length = 0;
  });
  afterAll(async () => {
    await app.close();
    await receiver.server.close();
  });

  const subscribe = (msisdn: string[], url = receiver.url) =>
    app.inject({
      method: 'POST',
      url: SUBS,
      headers: HEADERS,
      payload: {
        monitoringType: 'LOSS_OF_CONNECTIVITY',
        subscriptions: [{ msisdn, notificationDestination: url }],
      },
    });

  it('subscribes every MSISDN and answers 201 in the documented shape', async () => {
    const res = await subscribe(['61412345678', '61412345679']);
    expect(res.statusCode).toBe(201);
    const body = res.json();
    expect(body).toMatchObject({
      'correlation-id': HEADERS['correlation-id'],
      status: 201,
      message: 'successful',
      timeStamp: expect.any(Number),
    });
    expect(body.subscriptions).toHaveLength(2);
    expect(body.subscriptions[0]).toMatchObject({ msisdn: '61412345678', status: 201 });
  });

  it('answers 207 with SUBSCRIPTION_EXISTS when a SIM is already subscribed', async () => {
    await subscribe(['61412345678']);
    const res = await subscribe(['61412345678', '61412000001']);
    expect(res.statusCode).toBe(207);
    expect(res.json().message).toBe('partial_success');
    expect(res.json().errors[0]).toMatchObject({
      type: 'SUBSCRIPTION_EXISTS',
      status: 409,
      msisdn: '61412345678',
    });
  });

  it('rejects bad payloads and missing headers with Telstra error bodies', async () => {
    const bad = await subscribe(['0412345678']); // not E.164
    expect(bad.statusCode).toBe(400);
    expect(bad.json().errors[0]).toMatchObject({ code: 'FIELD_INVALID', location: 'body' });

    const dupe = await app.inject({
      method: 'POST',
      url: SUBS,
      headers: HEADERS,
      payload: {
        monitoringType: 'LOSS_OF_CONNECTIVITY',
        subscriptions: [
          { msisdn: ['61412345678'], notificationDestination: receiver.url },
          { msisdn: ['61412345678'], notificationDestination: receiver.url },
        ],
      },
    });
    expect(dupe.statusCode).toBe(400);

    const noAuth = await app.inject({
      method: 'GET',
      url: SUBS,
      headers: { ...HEADERS, authorization: '' },
    });
    expect(noAuth.statusCode).toBe(401);
    expect(noAuth.json().errors[0].code).toBe('TOKEN_INVALID');

    const noCorrelation = await app.inject({
      method: 'GET',
      url: SUBS,
      headers: { authorization: HEADERS.authorization },
    });
    expect(noCorrelation.statusCode).toBe(400);
  });

  it('lists with a cursor, gets one, deletes with 204 and then 404s', async () => {
    await subscribe(['61412000001', '61412000002', '61412000003']);
    const list = (query: string) =>
      app.inject({ method: 'GET', url: SUBS + query, headers: HEADERS });
    const page1 = (await list('?limit=2')).json();
    expect(page1.subscriptions).toHaveLength(2);
    expect(page1.limit).toBe(2);
    const page2 = (await list(`?limit=2&cursor=${page1.nextCursor}`)).json();
    expect(page2.subscriptions.map((s: { msisdn: string }) => s.msisdn)).toEqual(['61412000003']);
    expect(page2.nextCursor).toBeUndefined();

    const id = page1.subscriptions[0].subscriptionId;
    const one = await app.inject({ method: 'GET', url: `${SUBS}/${id}`, headers: HEADERS });
    expect(one.json()).toEqual({
      subscriptionId: id,
      msisdn: '61412000001',
      notificationDestination: receiver.url,
    });
    const del = await app.inject({ method: 'DELETE', url: `${SUBS}/${id}`, headers: HEADERS });
    expect(del.statusCode).toBe(204);
    const gone = await app.inject({ method: 'GET', url: `${SUBS}/${id}`, headers: HEADERS });
    expect(gone.statusCode).toBe(404);
    expect(gone.json().errors[0].code).toBe('RESOURCE_NOT_FOUND');
  });

  it('serves the /v1/ path from the Getting Started page too', async () => {
    const res = await app.inject({
      method: 'GET',
      url: '/loss-of-connectivity/v1/subscriptions',
      headers: HEADERS,
    });
    expect(res.statusCode).toBe(200);
  });

  it('triggering an event delivers a callback to the subscriber', async () => {
    await subscribe(['61412345678', '61412345679']);
    const res = await app.inject({
      method: 'POST',
      url: LOC_TRIGGER_PATH,
      payload: {
        events: [
          { msisdn: '61412345678', lossOfConnectReason: 0, eventTime: '2026-11-25T00:05:00Z' },
          { msisdn: '61412345679', lossOfConnectReason: 7, eventTime: '2026-11-25T00:05:30Z' },
          { msisdn: '61499999999', lossOfConnectReason: 0 }, // nobody subscribed
        ],
      },
    });
    expect(res.statusCode).toBe(200);
    expect(res.json().unsubscribed).toEqual(['61499999999']);
    expect(res.json().deliveries.every((d: { status: number }) => d.status === 202)).toBe(true);

    const reports = receiver.received.flatMap((c) => c.monitoringEventReports);
    const report = (msisdn: string, lossOfConnectReason: number, eventTime: string) => ({
      monitoringType: 'LOSS_OF_CONNECTIVITY',
      msisdn,
      lossOfConnectReason,
      eventTime,
    });
    expect(reports).toEqual(
      expect.arrayContaining([
        report('61412345678', 0, '2026-11-25T00:05:00Z'),
        report('61412345679', 7, '2026-11-25T00:05:30Z'),
      ]),
    );
  });

  it('reports an unreachable callback instead of failing', async () => {
    await subscribe(['61412345678'], 'http://127.0.0.1:1/nowhere');
    const res = await app.inject({
      method: 'POST',
      url: LOC_TRIGGER_PATH,
      payload: { msisdn: '61412345678', lossOfConnectReason: 2 },
    });
    expect(res.json().deliveries[0].status).toBeNull();
  });

  it('issues a client-credentials token on the same path as Telstra', async () => {
    const res = await app.inject({
      method: 'POST',
      url: TOKEN_PATH,
      headers: { 'content-type': 'application/x-www-form-urlencoded' },
      payload: 'grant_type=client_credentials&client_id=a&client_secret=b&scope=x',
    });
    expect(res.statusCode).toBe(200);
    expect(res.json()).toMatchObject({ token_type: 'Bearer', expires_in: 3600 });
  });
});
