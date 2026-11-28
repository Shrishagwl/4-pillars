import { timingSafeEqual } from 'node:crypto';
import { AU_MSISDN_PATTERN } from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import { Type } from 'typebox';
import type { IngestStore } from '../db/store.js';

const MeterBody = Type.Object({
  meterId: Type.String({ minLength: 1 }),
  msisdn: Type.String({ pattern: AU_MSISDN_PATTERN }),
  transformerId: Type.String({ minLength: 1 }),
  suburb: Type.String({ minLength: 1 }),
  postcode: Type.String({ pattern: '^[0-9]{4}$' }),
  state: Type.String({ minLength: 2, default: 'VIC' }),
  lat: Type.Union([Type.Number({ minimum: -90, maximum: 90 }), Type.Null()], { default: null }),
  lon: Type.Union([Type.Number({ minimum: -180, maximum: 180 }), Type.Null()], { default: null }),
});

/** True when no key is configured (local) or the header matches it. */
export function hasApiKey(header: string | string[] | undefined, key: string): boolean {
  if (!key) return true;
  if (typeof header !== 'string') return false;
  const a = Buffer.from(header);
  const b = Buffer.from(key);
  return a.length === b.length && timingSafeEqual(a, b);
}

/**
 * The meters we monitor. The twin registers its grid here; the engine reads it to know which
 * transformer and suburb each SIM belongs to.
 */
export const meterRoutes: FastifyPluginAsyncTypebox<{
  store: IngestStore;
  apiKey?: string;
}> = async (app, { store, apiKey = '' }) => {
  app.put(
    '/meters',
    {
      // ingest-api is public in the cloud (Telstra has to reach the callback), so writes need
      // the key the twin gets from Secret Manager.
      preHandler: async (req, reply) => {
        if (!hasApiKey(req.headers['x-api-key'], apiKey)) {
          return reply.code(401).send({ error: 'API key missing or wrong' });
        }
      },
      schema: { body: Type.Object({ meters: Type.Array(MeterBody, { maxItems: 10_000 }) }) },
    },
    async (req) => {
      const saved = await store.upsertMeters(
        req.body.meters.map((m) => ({ ...m, lat: m.lat ?? null, lon: m.lon ?? null })),
      );
      req.log.info({ saved }, 'meters registered');
      return { saved };
    },
  );

  app.get('/meters', async (_req, reply) => {
    reply.header('access-control-allow-origin', '*'); // the dashboard draws them on the map
    return { meters: await store.listMeters() };
  });
};
