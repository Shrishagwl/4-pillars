import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { Clock } from '../src/lib/clock.js';
import { compare, distanceM } from '../src/lib/device-store.js';
import { FAKE_DEVICES_PATH } from '../src/routes/location-verification.js';

const HEADERS = {
  authorization: 'Bearer test-token',
  'x-correlator': 'b4333c46-49c0-4f62-80d7-f0ef930f1c46',
};
const VERIFY = '/location-verification/verify';
const HOME = { latitude: -37.745, longitude: 144.962 }; // where the meter is registered (Coburg)
const NOW = '2026-11-25T00:10:00Z';

describe('fake Location Verification API', () => {
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeEach(async () => {
    const clock = new Clock();
    clock.set(new Date(NOW));
    app = await buildApp(loadConfig({}), { logger: false, clock });
  });
  afterEach(() => app.close());

  const place = (fix: Record<string, unknown>) =>
    app.inject({
      method: 'POST',
      url: FAKE_DEVICES_PATH,
      payload: { phoneNumber: '+61412000001', ...fix },
    });
  const verify = (body: Record<string, unknown>, headers: Record<string, string> = HEADERS) =>
    app.inject({
      method: 'POST',
      url: VERIFY,
      headers,
      payload: {
        device: { phoneNumber: '+61412000001' },
        area: { areaType: 'CIRCLE', center: HOME, radius: 1000 },
        ...body,
      },
    });

  it('a meter where it should be is TRUE', async () => {
    await place({ ...HOME, accuracy: 200, locatedAt: '2026-11-25T00:09:00Z' });
    const res = await verify({});
    expect(res.statusCode).toBe(200);
    expect(res.headers['x-correlator']).toBe(HEADERS['x-correlator']);
    expect(res.json()).toEqual({
      verificationResult: 'TRUE',
      lastLocationTime: '2026-11-25T00:09:00Z',
    });
  });

  it('a tampered meter returns FALSE for its registered area', async () => {
    // The twin moved the SIM about 3 km north (taken out of the meter box).
    await place({ latitude: -37.718, longitude: 144.962, accuracy: 300 });
    const res = await verify({});
    expect(res.json().verificationResult).toBe('FALSE');
    expect(res.json().matchRate).toBeUndefined();
  });

  it('a fix on the edge of the area is PARTIAL with a matchRate', async () => {
    await place({ latitude: -37.736, longitude: 144.962, accuracy: 300 }); // ~1 km from HOME
    const body = (await verify({})).json();
    expect(body.verificationResult).toBe('PARTIAL');
    expect(body.matchRate).toBeGreaterThanOrEqual(1);
    expect(body.matchRate).toBeLessThanOrEqual(99);
  });

  it('answers the CAMARA error codes', async () => {
    await place({ ...HOME, locatedAt: '2026-11-25T00:00:00Z' });
    const code = async (body: Record<string, unknown>, headers = HEADERS) => {
      const res = await verify(body, headers);
      return [res.statusCode, res.json().code];
    };
    expect(await code({}, { authorization: '' } as never)).toEqual([401, 'UNAUTHENTICATED']);
    expect(await code({ device: undefined })).toEqual([422, 'MISSING_IDENTIFIER']);
    expect(await code({ device: { ipv6Address: '2001:db8::1' } })).toEqual([
      422,
      'UNSUPPORTED_IDENTIFIER',
    ]);
    expect(await code({ device: { phoneNumber: '+61499999999' } })).toEqual([
      404,
      'IDENTIFIER_NOT_FOUND',
    ]);
    expect(await code({ area: { areaType: 'CIRCLE', center: HOME, radius: 500 } })).toEqual([
      422,
      'LOCATION_VERIFICATION.INVALID_AREA',
    ]);
    expect(
      await code({
        area: { areaType: 'CIRCLE', center: { latitude: 51.5, longitude: 0 }, radius: 2000 },
      }),
    ).toEqual([422, 'LOCATION_VERIFICATION.AREA_NOT_COVERED']);
    expect(await code({ maxAge: 60 })).toEqual([
      422,
      'LOCATION_VERIFICATION.UNABLE_TO_FULFILL_MAX_AGE',
    ]);
    expect(
      await code({
        area: { areaType: 'CIRCLE', center: { latitude: -95, longitude: 0 }, radius: 2000 },
      }),
    ).toEqual([400, 'OUT_OF_RANGE']);
    expect(await code({ area: { areaType: 'POLYGON' } })).toEqual([400, 'INVALID_ARGUMENT']);

    await place({ ...HOME, locatable: false });
    expect(await code({})).toEqual([422, 'LOCATION_VERIFICATION.UNABLE_TO_LOCATE']);
  });

  it('serves the CAMARA /v3/ path as well', async () => {
    await place(HOME);
    const res = await app.inject({
      method: 'POST',
      url: '/location-verification/v3/verify',
      headers: HEADERS,
      payload: {
        device: { phoneNumber: '+61412000001' },
        area: { areaType: 'CIRCLE', center: HOME, radius: 1000 },
      },
    });
    expect(res.json().verificationResult).toBe('TRUE');
  });

  it('geometry: distance and the TRUE / PARTIAL / FALSE rule', () => {
    expect(distanceM(-37.745, 144.962, -37.718, 144.962)).toBeCloseTo(3002, -1);
    expect(compare({ ...HOME, accuracy: 100 }, HOME, 1000).result).toBe('TRUE');
    // An estimate bigger than the requested area is PARTIAL, as the spec says.
    expect(compare({ ...HOME, accuracy: 2000 }, HOME, 1000)).toEqual({
      result: 'PARTIAL',
      matchRate: 25,
    });
  });
});
