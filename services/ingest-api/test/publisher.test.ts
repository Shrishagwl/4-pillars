import type { MeterSilentEvent } from '@4p/contracts';
import pg from 'pg';
import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { migrate } from '../src/db/migrate.js';
import {
  HttpPublisher,
  MemoryPublisher,
  PubSubPublisher,
  publisherFromEnv,
} from '../src/publisher.js';
import { LOC_CALLBACK_PATH } from '../src/routes/loc-callback.js';

const EVENT: MeterSilentEvent = {
  eventId: '7d4ac9a4-1b9e-4cf6-8a43-0e7c2c1f0a11',
  subscriptionId: 'sub-1',
  msisdn: '61412000001',
  reasonCode: 0,
  reasonGroup: 'DETACHED',
  eventTime: '2026-11-25T00:05:00.000Z',
  receivedAt: '2026-11-25T00:05:02.000Z',
};

function recordingFetch(answer: (url: string) => Response) {
  const calls: Array<{ url: string; init: RequestInit }> = [];
  const fetchImpl = (async (url: string | URL, init: RequestInit = {}) => {
    calls.push({ url: String(url), init });
    return answer(String(url));
  }) as typeof fetch;
  return { fetchImpl, calls };
}

describe('publishers', () => {
  it('HTTP: posts the batch to the engine', async () => {
    const f = recordingFetch(() => new Response(null, { status: 202 }));
    await new HttpPublisher('http://engine:8084/', f.fetchImpl).publish([EVENT]);
    expect(f.calls[0]?.url).toBe('http://engine:8084/events');
    expect(JSON.parse(f.calls[0]?.init.body as string)).toEqual({ events: [EVENT] });
  });

  it('HTTP: an engine error is an error, so Telstra retries', async () => {
    const f = recordingFetch(() => new Response(null, { status: 503 }));
    await expect(
      new HttpPublisher('http://engine:8084', f.fetchImpl).publish([EVENT]),
    ).rejects.toThrow(/503/);
  });

  it('Pub/Sub: one base64 JSON message per event, with the msisdn as an attribute', async () => {
    const f = recordingFetch((url) =>
      url.endsWith('/token')
        ? Response.json({ access_token: 'at', expires_in: 3600 })
        : Response.json({ messageIds: ['1'] }),
    );
    const pub = new PubSubPublisher('projects/pillars-514405/topics/meter-silent', f.fetchImpl);
    await pub.publish([EVENT]);
    const call = f.calls[1];
    expect(call?.url).toBe(
      'https://pubsub.googleapis.com/v1/projects/pillars-514405/topics/meter-silent:publish',
    );
    expect((call?.init.headers as Record<string, string>).authorization).toBe('Bearer at');
    const [message] = JSON.parse(call?.init.body as string).messages;
    expect(JSON.parse(Buffer.from(message.data, 'base64').toString())).toEqual(EVENT);
    expect(message.attributes).toEqual({ eventId: EVENT.eventId, msisdn: EVENT.msisdn });
  });

  it('Pub/Sub wins when both are configured; neither means no hand-off', () => {
    expect(
      publisherFromEnv({ pubsubTopic: 'projects/p/topics/t', engineUrl: 'http://e' })?.kind,
    ).toBe('pubsub');
    expect(publisherFromEnv({ pubsubTopic: '', engineUrl: 'http://e' })?.kind).toBe('http');
    expect(publisherFromEnv({ pubsubTopic: '', engineUrl: '' })).toBeUndefined();
    expect(() => new PubSubPublisher('meter-silent')).toThrow(/projects/);
  });
});

const url = process.env.TEST_DATABASE_URL;

describe.skipIf(!url)('callback hand-off', () => {
  let pool: pg.Pool;
  const publisher = new MemoryPublisher();
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeAll(async () => {
    pool = new pg.Pool({ connectionString: url });
    await pool.query('DROP SCHEMA IF EXISTS ingest CASCADE');
    await migrate(pool);
    app = await buildApp(loadConfig({}), { logger: false, db: pool, publisher });
  });
  afterAll(async () => {
    await app?.close();
    await pool?.end();
  });

  it('passes stored events on, and passes a repeat on again with the same event id', async () => {
    const payload = {
      subscriptionId: 'sub-1',
      monitoringEventReports: [
        {
          monitoringType: 'LOSS_OF_CONNECTIVITY',
          msisdn: '61412000001',
          lossOfConnectReason: 0,
          eventTime: '2026-11-25T00:05:00Z',
        },
      ],
    };
    const first = await app.inject({ method: 'POST', url: LOC_CALLBACK_PATH, payload });
    const again = await app.inject({ method: 'POST', url: LOC_CALLBACK_PATH, payload });
    expect(first.json()).toEqual({ accepted: 1, duplicates: 0 });
    expect(again.json()).toEqual({ accepted: 0, duplicates: 1 });
    expect(publisher.published).toHaveLength(2);
    expect(publisher.published[0]?.eventId).toBe(publisher.published[1]?.eventId);
    expect(publisher.published[0]).toMatchObject({
      msisdn: '61412000001',
      reasonGroup: 'DETACHED',
    });
  });
});
