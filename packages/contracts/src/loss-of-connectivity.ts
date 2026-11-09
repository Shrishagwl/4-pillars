/**
 * Loss of Connectivity (LoC) API, v0.1.0 (closed beta).
 * Source: public docs on dev.telstra.com, read 9 Nov 2026. Written from those docs only.
 *
 * Telstra calls OUR callback URL with this payload whenever a subscribed SIM loses connectivity.
 * We must answer 202.
 */
import { type Static, Type } from 'typebox';

/**
 * LoC reason codes, grouped the way we use them.
 *  0, 1, 6  detached / deregistered
 *  2, 3, 7  maximum detection time expired (device went quiet)
 *  4, 5, 8  purged from the network
 */
export const LOC_REASON_GROUPS = {
  DETACHED: [0, 1, 6],
  DETECTION_TIMEOUT: [2, 3, 7],
  PURGED: [4, 5, 8],
} as const;

export type LocReasonGroup = keyof typeof LOC_REASON_GROUPS;

export function reasonGroup(code: number): LocReasonGroup | 'UNKNOWN' {
  for (const [group, codes] of Object.entries(LOC_REASON_GROUPS)) {
    if ((codes as readonly number[]).includes(code)) return group as LocReasonGroup;
  }
  return 'UNKNOWN';
}

export const MonitoringEventReport = Type.Object(
  {
    monitoringType: Type.String({ examples: ['LOSS_OF_CONNECTIVITY'] }),
    msisdn: Type.String({ minLength: 8, maxLength: 16, examples: ['61412345678'] }),
    lossOfConnectReason: Type.Integer({ minimum: 0, maximum: 8 }),
    eventTime: Type.String({ format: 'date-time' }),
  },
  { additionalProperties: true },
);
export type MonitoringEventReport = Static<typeof MonitoringEventReport>;

/** Body Telstra POSTs to our callback URL. */
export const LocCallback = Type.Object(
  {
    subscriptionId: Type.String({ minLength: 1 }),
    monitoringEventReports: Type.Array(MonitoringEventReport, { minItems: 1 }),
  },
  { additionalProperties: true },
);
export type LocCallback = Static<typeof LocCallback>;

/**
 * Subscription create/list/delete lives at
 *   POST/GET  .../mobility/products-api/loss-of-connectivity/v1/subscriptions
 *   GET/DELETE .../subscriptions/{id}
 * TODO(platform, #7): copy the exact subscription request/response field names from the
 * public docs before telstra-fake implements them. Do not guess field names here.
 */
