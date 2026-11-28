import { fromMelbourneTimestamp, NETWORK_STATUS_PATH, toMelbourneTimestamp } from '@4p/contracts';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { Clock } from '../src/lib/clock.js';
import { FAKE_OUTAGES_PATH } from '../src/routes/network-availability.js';

const HEADERS = {
  authorization: 'Bearer test-token',
  accept: 'application/json',
  'accept-charset': 'utf-8',
  'content-language': 'en-au',
  'content-type': 'application/json',
  'correlation-id': 'f7c94213-36df-44cc-935f-025bb52cad42',
};
const COBURG = 'suburb=Coburg&state=VIC&postcode=3058';
const NOW = '2026-11-25T00:10:00Z'; // 11:10 in Melbourne (daylight saving, UTC+11)

describe('fake Network Availability API', () => {
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeEach(async () => {
    const clock = new Clock();
    clock.set(new Date(NOW));
    app = await buildApp(loadConfig({}), { logger: false, clock });
  });
  afterEach(() => app.close());

  const status = (query: string, headers: Record<string, string> = HEADERS) =>
    app.inject({ method: 'GET', url: `${NETWORK_STATUS_PATH}?${query}`, headers });
  const addOutage = (body: Record<string, unknown>) =>
    app.inject({ method: 'POST', url: FAKE_OUTAGES_PATH, payload: body });

  it('answers with all four groups empty when nothing is wrong', async () => {
    const res = await status(COBURG);
    expect(res.statusCode).toBe(200);
    expect(res.headers['content-language']).toBe('en-au');
    expect(res.json()).toMatchObject({
      'correlation-id': HEADERS['correlation-id'],
      status: 200,
      timeStamp: expect.any(Number),
      past: [],
      current: [],
      near_future: [],
      far_future: [],
    });
  });

  it('a suburb with an active outage shows it in current', async () => {
    await addOutage({
      state: 'VIC',
      suburb: 'Coburg',
      postcode: '3058',
      start: '2026-11-25T00:05:00Z',
      affected_area:
        'MULTIPOLYGON(((144.95 -37.75,144.97 -37.75,144.97 -37.74,144.95 -37.74,144.95 -37.75)))',
    });
    const body = (await status(COBURG)).json();
    expect(body.current).toHaveLength(1);
    expect(body.current[0]).toMatchObject({
      state: 'VIC',
      suburb: 'COBURG',
      postcode: '3058',
      start_timestamp: '2026-11-25 11:05:00 Australia/Melbourne',
      end_timestamp: null,
      duration: 300,
      is_planned: false,
      technology: '4G',
      affected_area: expect.stringMatching(/^MULTIPOLYGON/),
    });
    // Other suburbs don't see it.
    expect((await status('suburb=Brunswick&state=VIC&postcode=3056')).json().current).toEqual([]);
  });

  it('sorts outages into past, near_future (next 24 h) and far_future', async () => {
    const at = (iso: string) => ({ state: 'vic', suburb: 'coburg', postcode: '3058', start: iso });
    await addOutage({ ...at('2026-11-24T20:00:00Z'), end: '2026-11-24T21:00:00Z' });
    await addOutage({ ...at('2026-11-25T06:00:00Z'), is_planned: true });
    await addOutage({ ...at('2026-11-28T06:00:00Z'), is_planned: true, technology: '5G' });
    await addOutage({
      state: 'NAT',
      suburb: 'ALL',
      postcode: '0000',
      start: '2026-11-25T00:00:00Z',
    });

    const body = (await status('suburb=COBURG&state=vic&postcode=3058')).json();
    expect(body.past).toHaveLength(1);
    expect(body.past[0]).toMatchObject({
      duration: 3600,
      end_timestamp: '2026-11-25 08:00:00 Australia/Melbourne',
    });
    expect(body.near_future).toHaveLength(1);
    expect(body.far_future[0].technology).toBe('5G');
    expect(body.current.map((o: { state: string }) => o.state)).toEqual(['NAT']); // national outages are included
  });

  it('an outage that ends moves from current to past', async () => {
    const { id } = (
      await addOutage({
        state: 'VIC',
        suburb: 'Coburg',
        postcode: '3058',
        start: '2026-11-25T00:00:00Z',
      })
    ).json();
    await app.inject({
      method: 'POST',
      url: `${FAKE_OUTAGES_PATH}/${id}/end`,
      payload: { end: '2026-11-25T00:08:00Z' },
    });
    const body = (await status(COBURG)).json();
    expect(body.current).toEqual([]);
    expect(body.past[0].duration).toBe(480);
  });

  it('rejects missing or bad query parameters with FIELD_MISSING / FIELD_INVALID', async () => {
    const missing = await status('state=VIC&postcode=3058');
    expect(missing.statusCode).toBe(400);
    expect(missing.json().errors[0]).toMatchObject({
      code: 'FIELD_MISSING',
      issue: 'suburb',
      field: 'suburb',
      location: 'query',
    });

    const bad = await status('suburb=Coburg&state=XX&postcode=30');
    expect(bad.json().errors.map((e: { field: string }) => e.field)).toEqual(['state', 'postcode']);

    const noToken = await status(COBURG, { ...HEADERS, authorization: '' });
    expect(noToken.statusCode).toBe(401);
    expect(noToken.json().errors[0]).toMatchObject({
      code: 'TOKEN_INVALID',
      field: 'authorization',
    });
  });

  it('formats and parses Melbourne timestamps across daylight saving', () => {
    const summer = new Date('2026-11-25T00:05:00Z');
    const winter = new Date('2026-06-25T00:05:00Z');
    expect(toMelbourneTimestamp(summer)).toBe('2026-11-25 11:05:00 Australia/Melbourne');
    expect(toMelbourneTimestamp(winter)).toBe('2026-06-25 10:05:00 Australia/Melbourne');
    expect(fromMelbourneTimestamp('2026-11-25 11:05:00 Australia/Melbourne')).toEqual(summer);
    expect(fromMelbourneTimestamp('2026-06-25 10:05:00 Australia/Melbourne')).toEqual(winter);
    expect(fromMelbourneTimestamp('2026-06-25T10:05:00Z')).toBeNull();
  });
});
