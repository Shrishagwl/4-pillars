import { LOCATION_VERIFY_PATHS, MIN_RADIUS_M, VerifyLocationRequest } from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import type { FastifyError, FastifyReply } from 'fastify';
import { Type } from 'typebox';
import type { DeviceStore } from '../lib/device-store.js';

/** Not part of the API: the twin tells the fake where each SIM really is. */
export const FAKE_DEVICES_PATH = '/fake/location-verification/devices';

const DeviceFixBody = Type.Object({
  phoneNumber: Type.String({ minLength: 5 }),
  latitude: Type.Number({ minimum: -90, maximum: 90 }),
  longitude: Type.Number({ minimum: -180, maximum: 180 }),
  accuracy: Type.Optional(Type.Number({ minimum: 1 })),
  locatedAt: Type.Optional(Type.String({ format: 'date-time' })),
  locatable: Type.Optional(Type.Boolean()),
});

// Rough box around Australia. Outside it the area is "not covered", like a real operator.
const AUSTRALIA = { south: -44.5, north: -9, west: 112, east: 154.5 };

function camaraError(reply: FastifyReply, status: number, code: string, message: string) {
  return reply.code(status).send({ status, code, message });
}

export const locationVerificationRoutes: FastifyPluginAsyncTypebox<{ store: DeviceStore }> = async (
  app,
  { store },
) => {
  // CAMARA's error body for bad requests: OUT_OF_RANGE for numbers outside their limits,
  // INVALID_ARGUMENT for everything else.
  app.setErrorHandler((err: FastifyError, _req, reply) => {
    if (err.validation) {
      const outOfRange = err.validation.some((v) => ['minimum', 'maximum'].includes(v.keyword));
      return camaraError(
        reply,
        400,
        outOfRange ? 'OUT_OF_RANGE' : 'INVALID_ARGUMENT',
        outOfRange
          ? 'Client specified an invalid range.'
          : `Client specified an invalid argument: ${err.message}`,
      );
    }
    reply.log.error(err);
    return camaraError(reply, 500, 'INTERNAL', 'Server error.');
  });

  // x-correlator is optional in the request and echoed on every answer.
  app.addHook('onSend', async (req, reply) => {
    const correlator = req.headers['x-correlator'];
    if (typeof correlator === 'string') reply.header('x-correlator', correlator);
  });

  for (const path of LOCATION_VERIFY_PATHS) {
    app.post(path, { schema: { body: VerifyLocationRequest } }, async (req, reply) => {
      if (!/^Bearer \S+$/.test(req.headers.authorization ?? '')) {
        return camaraError(
          reply,
          401,
          'UNAUTHENTICATED',
          'Request not authenticated due to missing, invalid, or expired credentials.',
        );
      }
      const { device, area, maxAge } = req.body;
      if (!device) {
        return camaraError(reply, 422, 'MISSING_IDENTIFIER', 'The device cannot be identified.');
      }
      if (!device.phoneNumber) {
        return camaraError(
          reply,
          422,
          'UNSUPPORTED_IDENTIFIER',
          'The identifier provided is not supported.',
        );
      }
      if (area.radius < MIN_RADIUS_M) {
        return camaraError(
          reply,
          422,
          'LOCATION_VERIFICATION.INVALID_AREA',
          `The requested area is too small. The minimum radius is ${MIN_RADIUS_M} m.`,
        );
      }
      const { latitude, longitude } = area.center;
      const inAustralia =
        latitude >= AUSTRALIA.south &&
        latitude <= AUSTRALIA.north &&
        longitude >= AUSTRALIA.west &&
        longitude <= AUSTRALIA.east;
      if (!inAustralia) {
        return camaraError(
          reply,
          422,
          'LOCATION_VERIFICATION.AREA_NOT_COVERED',
          'Unable to cover the requested area',
        );
      }

      const verdict = store.verify(device.phoneNumber, area.center, area.radius, maxAge);
      if ('error' in verdict) {
        if (verdict.error === 'NOT_FOUND') {
          return camaraError(reply, 404, 'IDENTIFIER_NOT_FOUND', 'Device identifier not found.');
        }
        if (verdict.error === 'UNABLE_TO_LOCATE') {
          return camaraError(
            reply,
            422,
            'LOCATION_VERIFICATION.UNABLE_TO_LOCATE',
            'Unable to locate the device.',
          );
        }
        return camaraError(
          reply,
          422,
          'LOCATION_VERIFICATION.UNABLE_TO_FULFILL_MAX_AGE',
          'Unable to provide expected freshness for location.',
        );
      }
      return {
        verificationResult: verdict.result,
        ...('matchRate' in verdict ? { matchRate: verdict.matchRate } : {}),
        lastLocationTime: verdict.lastLocationTime,
      };
    });
  }

  // One device or a batch.
  app.post(
    FAKE_DEVICES_PATH,
    {
      schema: {
        body: Type.Union([DeviceFixBody, Type.Object({ devices: Type.Array(DeviceFixBody) })]),
      },
    },
    async (req) => {
      const list = 'devices' in req.body ? req.body.devices : [req.body];
      for (const { phoneNumber, ...fix } of list) store.set(phoneNumber, fix);
      return { updated: list.length };
    },
  );

  app.delete(FAKE_DEVICES_PATH, async (_req, reply) => {
    store.clear();
    return reply.code(204).send();
  });
};
