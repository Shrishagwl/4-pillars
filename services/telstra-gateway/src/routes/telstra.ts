import {
  fromMelbourneTimestamp,
  LOC_SUBSCRIPTION_PATHS,
  NETWORK_STATUS_PATH,
  type Outage,
} from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import type { FastifyReply, FastifyRequest } from 'fastify';
import { Type } from 'typebox';
import type { Config } from '../config.js';
import { type TelstraClient, TelstraUnavailable } from '../lib/telstra-client.js';

const GROUPS = ['past', 'current', 'near_future', 'far_future'] as const;

/** An outage as the engine gets it: Telstra's fields, with times converted to UTC ISO 8601. */
export interface GatewayOutage extends Omit<Outage, 'start_timestamp' | 'end_timestamp'> {
  start: string | null;
  end: string | null;
  start_timestamp: string;
  end_timestamp: string | null;
}

function toUtc(text: string | null): string | null {
  if (text === null) return null;
  return fromMelbourneTimestamp(text)?.toISOString() ?? null;
}

function incidentOf(req: FastifyRequest): string | undefined {
  const id = req.headers['x-incident-id'];
  return typeof id === 'string' && id ? id : undefined;
}

/** Telstra being down is a 502 for our callers, not a crash. */
function unavailable(reply: FastifyReply, err: unknown) {
  if (err instanceof TelstraUnavailable) {
    return reply.code(502).send({ error: 'TELSTRA_UNAVAILABLE', api: err.api });
  }
  throw err;
}

interface CacheEntry {
  at: number;
  body: unknown;
}

export const telstraRoutes: FastifyPluginAsyncTypebox<{
  config: Config;
  client: TelstraClient;
  now?: () => number;
}> = async (app, { config, client, now = Date.now }) => {
  // One answer per suburb is reused for a minute: during a big outage hundreds of meters in
  // the same suburb would otherwise ask Telstra the same question.
  const cache = new Map<string, CacheEntry>();

  app.get(
    '/v1/network-availability',
    {
      schema: {
        querystring: Type.Object({
          suburb: Type.String({ minLength: 1 }),
          state: Type.String({ minLength: 2 }),
          postcode: Type.String({ pattern: '^[0-9]{4}$' }),
        }),
      },
    },
    async (req, reply) => {
      const { suburb, state, postcode } = req.query;
      const key = `${suburb.toUpperCase()}|${state.toUpperCase()}|${postcode}`;
      const hit = cache.get(key);
      if (hit && now() - hit.at < config.outageCacheMs) {
        return { ...(hit.body as object), cached: true };
      }

      let res: Awaited<ReturnType<TelstraClient['call']>>;
      try {
        res = await client.call({
          api: 'network-availability',
          method: 'GET',
          url: config.telstraBaseUrl + NETWORK_STATUS_PATH,
          query: { suburb, state, postcode },
          incidentId: incidentOf(req),
        });
      } catch (err) {
        return unavailable(reply, err);
      }
      if (res.status !== 200) return reply.code(res.status).send(res.body);

      const raw = res.body as Record<(typeof GROUPS)[number], Outage[]>;
      const outages = Object.fromEntries(
        GROUPS.map((g) => [
          g,
          (raw[g] ?? []).map((o) => ({
            ...o,
            start: toUtc(o.start_timestamp),
            end: toUtc(o.end_timestamp),
          })),
        ]),
      );
      const body = { suburb, state, postcode, correlationId: res.correlationId, outages };
      cache.set(key, { at: now(), body });
      return { ...body, cached: false };
    },
  );

  app.post(
    '/v1/location-verification',
    {
      schema: {
        body: Type.Object({
          msisdn: Type.String({ pattern: '^\\+?[1-9][0-9]{4,14}$' }),
          latitude: Type.Number({ minimum: -90, maximum: 90 }),
          longitude: Type.Number({ minimum: -180, maximum: 180 }),
          radius: Type.Optional(Type.Number({ minimum: 1 })),
          maxAge: Type.Optional(Type.Integer({ minimum: 0 })),
        }),
      },
    },
    async (req, reply) => {
      const { msisdn, latitude, longitude, radius = 1000, maxAge } = req.body;
      const phoneNumber = msisdn.startsWith('+') ? msisdn : `+${msisdn}`;
      let res: Awaited<ReturnType<TelstraClient['call']>>;
      try {
        res = await client.call({
          api: 'location-verification',
          method: 'POST',
          url: `${config.locationBaseUrl}/location-verification/verify`,
          body: {
            device: { phoneNumber },
            area: { areaType: 'CIRCLE', center: { latitude, longitude }, radius },
            ...(maxAge === undefined ? {} : { maxAge }),
          },
          incidentId: incidentOf(req),
        });
      } catch (err) {
        return unavailable(reply, err);
      }
      const body = res.body as Record<string, unknown>;
      if (res.status === 200) {
        return {
          msisdn,
          verificationResult: body.verificationResult,
          ...(body.matchRate === undefined ? {} : { matchRate: body.matchRate }),
          lastLocationTime: body.lastLocationTime,
        };
      }
      // "Can't locate it" and "too old" are answers, not failures: the engine treats them as
      // "no location evidence". Anything else is passed through as an error.
      if (res.status === 422 || res.status === 404) {
        return { msisdn, verificationResult: null, error: body.code ?? 'UNKNOWN' };
      }
      return reply.code(res.status).send(body);
    },
  );

  const subscriptions = LOC_SUBSCRIPTION_PATHS[config.locApiVersion === 'v1' ? 1 : 0];

  app.post(
    '/v1/loss-of-connectivity/subscriptions',
    {
      schema: {
        body: Type.Object({
          msisdns: Type.Array(Type.String(), { minItems: 1 }),
          callbackUrl: Type.String({ minLength: 1 }),
        }),
      },
    },
    async (req, reply) => {
      try {
        const res = await client.call({
          api: 'loss-of-connectivity',
          method: 'POST',
          url: config.telstraBaseUrl + subscriptions,
          body: {
            monitoringType: 'LOSS_OF_CONNECTIVITY',
            subscriptions: [
              { msisdn: req.body.msisdns, notificationDestination: req.body.callbackUrl },
            ],
          },
        });
        return reply.code(res.status).send(res.body);
      } catch (err) {
        return unavailable(reply, err);
      }
    },
  );

  app.get('/v1/loss-of-connectivity/subscriptions', async (req, reply) => {
    try {
      const res = await client.call({
        api: 'loss-of-connectivity',
        method: 'GET',
        url: config.telstraBaseUrl + subscriptions,
        query: req.query as Record<string, string>,
      });
      return reply.code(res.status).send(res.body);
    } catch (err) {
      return unavailable(reply, err);
    }
  });

  app.delete<{ Params: { id: string } }>(
    '/v1/loss-of-connectivity/subscriptions/:id',
    async (req, reply) => {
      try {
        const res = await client.call({
          api: 'loss-of-connectivity',
          method: 'DELETE',
          url: `${config.telstraBaseUrl}${subscriptions}/${encodeURIComponent(req.params.id)}`,
        });
        return reply.code(res.status).send(res.body ?? undefined);
      } catch (err) {
        return unavailable(reply, err);
      }
    },
  );
};
