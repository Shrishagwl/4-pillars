/**
 * Our own internal messages between services. These are ours to change.
 * Python services mirror them as Pydantic models (services/engine/src/engine/contracts.py).
 */
import { type Static, Type } from 'typebox';

/** Published by ingest-api (Pub/Sub topic `meter-silent`) for every LoC report it accepts. */
export const MeterSilentEvent = Type.Object({
  eventId: Type.String({ format: 'uuid' }),
  subscriptionId: Type.String(),
  msisdn: Type.String(),
  reasonCode: Type.Integer({ minimum: 0, maximum: 8 }),
  reasonGroup: Type.Union([
    Type.Literal('DETACHED'),
    Type.Literal('DETECTION_TIMEOUT'),
    Type.Literal('PURGED'),
    Type.Literal('UNKNOWN'),
  ]),
  /** When the device lost connectivity (UTC, ISO 8601). */
  eventTime: Type.String({ format: 'date-time' }),
  /** When ingest-api received the callback (UTC, ISO 8601). */
  receivedAt: Type.String({ format: 'date-time' }),
});
export type MeterSilentEvent = Static<typeof MeterSilentEvent>;

export const Cause = Type.Union([
  Type.Literal('POWER'),
  Type.Literal('NETWORK'),
  Type.Literal('METER_FAULT'),
  Type.Literal('TAMPER'),
]);
export type Cause = Static<typeof Cause>;

export const Action = Type.Union([
  Type.Literal('DISPATCH_POWER_CREW'),
  Type.Literal('WAIT_FOR_NETWORK'),
  Type.Literal('DISPATCH_METER_TECH'),
  Type.Literal('INVESTIGATE_TAMPER'),
  Type.Literal('MANUAL_REVIEW'),
]);
export type Action = Static<typeof Action>;

/** What the engine writes for each incident and the dashboard shows. */
export const Verdict = Type.Object({
  incidentId: Type.String(),
  meterCount: Type.Integer({ minimum: 1 }),
  probabilities: Type.Record(Type.String(), Type.Number({ minimum: 0, maximum: 1 })),
  cause: Cause,
  confidence: Type.Number({ minimum: 0, maximum: 1 }),
  action: Action,
  evidence: Type.Array(Type.String()),
  updatedAt: Type.String({ format: 'date-time' }),
});
export type Verdict = Static<typeof Verdict>;
