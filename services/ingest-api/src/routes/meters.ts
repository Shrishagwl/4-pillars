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

/**
 * The meters we monitor. The twin registers its grid here; the engine reads it to know which
 * transformer and suburb each SIM belongs to.
 */
export const meterRoutes: FastifyPluginAsyncTypebox<{ store: IngestStore }> = async (
  app,
  { store },
) => {
  app.put(
    '/meters',
    { schema: { body: Type.Object({ meters: Type.Array(MeterBody, { maxItems: 10_000 }) }) } },
    async (req) => {
      const saved = await store.upsertMeters(
        req.body.meters.map((m) => ({ ...m, lat: m.lat ?? null, lon: m.lon ?? null })),
      );
      req.log.info({ saved }, 'meters registered');
      return { saved };
    },
  );

  app.get('/meters', async () => ({ meters: await store.listMeters() }));
};
