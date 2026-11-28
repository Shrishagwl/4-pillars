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

// ---------- Subscriptions ----------
// Field names copied from the public OpenAPI file (IoT Loss of Connectivity API 0.1.0) and the
// Getting Started page on dev.telstra.com, read 28 Nov 2026. The OpenAPI file says /v0/ and the
// Getting Started page says /v1/, so telstra-fake serves both.

export const LOC_SUBSCRIPTION_PATHS = [
  '/loss-of-connectivity/v0/subscriptions',
  '/loss-of-connectivity/v1/subscriptions',
] as const;

/** Australian mobile numbers in E.164 without the plus, starting 614 or 619. */
export const AU_MSISDN_PATTERN = '^61[49][0-9]{8}$';

export const LocSubscriptionRequest = Type.Object({
  monitoringType: Type.Literal('LOSS_OF_CONNECTIVITY'),
  subscriptions: Type.Array(
    Type.Object({
      msisdn: Type.Array(Type.String({ pattern: AU_MSISDN_PATTERN }), {
        minItems: 1,
        uniqueItems: true,
      }),
      notificationDestination: Type.String({ minLength: 1 }),
    }),
    { minItems: 1 },
  ),
});
export type LocSubscriptionRequest = Static<typeof LocSubscriptionRequest>;

export const LocSubscription = Type.Object({
  subscriptionId: Type.String(),
  msisdn: Type.String(),
  notificationDestination: Type.String(),
});
export type LocSubscription = Static<typeof LocSubscription>;

/** One per-device failure in a 207 answer. Note the hyphen in "message-content". */
export const LocSubscriptionError = Type.Object({
  type: Type.String({ examples: ['SUBSCRIPTION_EXISTS', 'AUTHORIZATION_ERROR'] }),
  'message-content': Type.String(),
  status: Type.Integer(),
  msisdn: Type.Optional(Type.String()),
  notificationDestination: Type.Optional(Type.String()),
  reason: Type.Optional(Type.String()),
});
export type LocSubscriptionError = Static<typeof LocSubscriptionError>;

/** 201 when every MSISDN was subscribed, 207 when some failed. */
export const LocSubscriptionsResponse = Type.Object({
  'correlation-id': Type.String(),
  status: Type.Integer(),
  timeStamp: Type.Integer({ description: 'Unix milliseconds' }),
  message: Type.String({ examples: ['successful', 'partial_success'] }),
  subscriptions: Type.Array(
    Type.Object({
      subscriptionId: Type.String(),
      msisdn: Type.String(),
      status: Type.Integer(),
      notificationDestination: Type.String(),
    }),
  ),
  errors: Type.Optional(Type.Array(LocSubscriptionError)),
});
export type LocSubscriptionsResponse = Static<typeof LocSubscriptionsResponse>;

export const LocSubscriptionList = Type.Object({
  subscriptions: Type.Array(LocSubscription),
  nextCursor: Type.Optional(Type.String()),
  limit: Type.Integer(),
});
export type LocSubscriptionList = Static<typeof LocSubscriptionList>;

/** The error body Telstra's LoC and Network Availability APIs use. */
export const TelstraErrorItem = Type.Object(
  {
    code: Type.String(),
    issue: Type.String(),
    suggested_action: Type.String(),
    location: Type.Optional(Type.String()),
    value: Type.Optional(Type.Unknown()),
    fieldName: Type.Optional(Type.String()),
    field: Type.Optional(Type.String()),
  },
  { additionalProperties: true },
);
export const TelstraErrors = Type.Object({ errors: Type.Array(TelstraErrorItem, { minItems: 1 }) });
export type TelstraErrors = Static<typeof TelstraErrors>;

/** lossOfConnectReason values, from the Getting Started page. */
export const LOC_REASON_NAMES: Record<number, string> = {
  0: 'UE_DETACHED_MME',
  1: 'UE_DETACHED_SGSN',
  2: 'MAX_DETECTION_TIME_EXPIRED_MME',
  3: 'MAX_DETECTION_TIME_EXPIRED_SGSN',
  4: 'UE_PURGED_MME',
  5: 'UE_PURGED_SGSN',
  6: 'DEREGISTERED (AMF)',
  7: 'MAX_DETECTION_TIME_EXPIRED (AMF)',
  8: 'PURGED (AMF)',
};
