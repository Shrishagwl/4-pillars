import { afterAll, beforeAll, describe, expect, it } from 'vitest';
import { buildApp } from '../src/app.js';
import { loadConfig } from '../src/config.js';
import { LOC_CALLBACK_PATH } from '../src/routes/loc-callback.js';

describe(`POST ${LOC_CALLBACK_PATH}`, () => {
  let app: Awaited<ReturnType<typeof buildApp>>;

  beforeAll(async () => {
    app = await buildApp(loadConfig({}), { logger: false });
  });
  afterAll(() => app.close());

  const valid = {
    subscriptionId: 'sub-123',
    monitoringEventReports: [
      {
        monitoringType: 'LOSS_OF_CONNECTIVITY',
        msisdn: '61412345678',
        lossOfConnectReason: 7,
        eventTime: '2026-11-20T03:15:00Z',
      },
    ],
  };

  it('accepts a valid callback with 202', async () => {
    const res = await app.inject({ method: 'POST', url: LOC_CALLBACK_PATH, payload: valid });
    expect(res.statusCode).toBe(202);
    expect(res.json()).toEqual({ accepted: 1 });
  });

  it('rejects a reason code outside 0-8', async () => {
    const bad = {
      ...valid,
      monitoringEventReports: [{ ...valid.monitoringEventReports[0], lossOfConnectReason: 12 }],
    };
    const res = await app.inject({ method: 'POST', url: LOC_CALLBACK_PATH, payload: bad });
    expect(res.statusCode).toBe(400);
  });

  it('rejects an empty report list', async () => {
    const res = await app.inject({
      method: 'POST',
      url: LOC_CALLBACK_PATH,
      payload: { subscriptionId: 'sub-123', monitoringEventReports: [] },
    });
    expect(res.statusCode).toBe(400);
  });
});
