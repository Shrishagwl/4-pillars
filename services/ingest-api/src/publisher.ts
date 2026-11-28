import type { MeterSilentEvent } from '@4p/contracts';

/**
 * How ingest-api hands events to the engine. Two versions behind one interface:
 *  - HTTP: POST straight to the engine. Used locally and in Docker Compose.
 *  - Pub/Sub: publish to the `meter-silent` topic; a push subscription delivers each message to
 *    the engine on Cloud Run. Pub/Sub keeps retrying if the engine is down or scaled to zero.
 */
export interface Publisher {
  readonly kind: string;
  publish(events: MeterSilentEvent[]): Promise<void>;
}

type Fetch = typeof fetch;
const METADATA =
  'http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default';

/** On Cloud Run, an ID token for calling another private Cloud Run service. */
export async function idToken(audience: string, fetchImpl: Fetch): Promise<Record<string, string>> {
  if (!process.env.K_SERVICE || !new URL(audience).hostname.endsWith('.run.app')) return {};
  const res = await fetchImpl(
    `${METADATA}/identity?audience=${encodeURIComponent(new URL(audience).origin)}`,
    {
      headers: { 'Metadata-Flavor': 'Google' },
    },
  );
  if (!res.ok) throw new Error(`metadata server answered ${res.status}`);
  return { authorization: `Bearer ${await res.text()}` };
}

export class HttpPublisher implements Publisher {
  readonly kind = 'http';

  constructor(
    private readonly engineUrl: string,
    private readonly fetchImpl: Fetch = fetch,
  ) {}

  async publish(events: MeterSilentEvent[]): Promise<void> {
    if (events.length === 0) return;
    const url = `${this.engineUrl.replace(/\/$/, '')}/events`;
    const res = await this.fetchImpl(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json', ...(await idToken(url, this.fetchImpl)) },
      body: JSON.stringify({ events }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) throw new Error(`engine answered ${res.status}`);
  }
}

/**
 * Publishes through the Pub/Sub REST API with the service account's access token from the
 * metadata server, so we don't need the full client library. One message per event; the
 * msisdn goes in an attribute so it shows up in logs without decoding the body.
 */
export class PubSubPublisher implements Publisher {
  readonly kind = 'pubsub';
  private token: { value: string; expiresAt: number } | null = null;

  constructor(
    /** projects/<project>/topics/<topic> */
    private readonly topic: string,
    private readonly fetchImpl: Fetch = fetch,
    private readonly endpoint = 'https://pubsub.googleapis.com/v1',
  ) {
    if (!/^projects\/[^/]+\/topics\/[^/]+$/.test(topic)) {
      throw new Error(
        `PUBSUB_TOPIC must look like projects/<project>/topics/<topic>, got "${topic}"`,
      );
    }
  }

  private async accessToken(): Promise<string> {
    if (this.token && this.token.expiresAt - 60_000 > Date.now()) return this.token.value;
    const res = await this.fetchImpl(`${METADATA}/token`, {
      headers: { 'Metadata-Flavor': 'Google' },
    });
    if (!res.ok) throw new Error(`metadata server answered ${res.status}`);
    const body = (await res.json()) as { access_token: string; expires_in: number };
    this.token = { value: body.access_token, expiresAt: Date.now() + body.expires_in * 1000 };
    return this.token.value;
  }

  async publish(events: MeterSilentEvent[]): Promise<void> {
    if (events.length === 0) return;
    const res = await this.fetchImpl(`${this.endpoint}/${this.topic}:publish`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        authorization: `Bearer ${await this.accessToken()}`,
      },
      body: JSON.stringify({
        messages: events.map((e) => ({
          data: Buffer.from(JSON.stringify(e)).toString('base64'),
          attributes: { eventId: e.eventId, msisdn: e.msisdn },
        })),
      }),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) throw new Error(`Pub/Sub answered ${res.status}: ${await res.text()}`);
  }
}

/** For tests and for running ingest-api on its own: keeps events in memory. */
export class MemoryPublisher implements Publisher {
  readonly kind = 'memory';
  readonly published: MeterSilentEvent[] = [];

  async publish(events: MeterSilentEvent[]): Promise<void> {
    this.published.push(...events);
  }
}

/** PUBSUB_TOPIC wins (the cloud); otherwise ENGINE_URL (local); otherwise nothing is sent. */
export function publisherFromEnv(env: {
  pubsubTopic: string;
  engineUrl: string;
}): Publisher | undefined {
  if (env.pubsubTopic) return new PubSubPublisher(env.pubsubTopic);
  if (env.engineUrl) return new HttpPublisher(env.engineUrl);
  return undefined;
}
