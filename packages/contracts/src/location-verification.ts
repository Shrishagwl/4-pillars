/**
 * Location Verification API (beta), CAMARA location-verification 3.0.0 shape.
 * POST /location-verification/verify
 * Telstra sandbox: minimum radius 1,000 m, answers fixed by test phone numbers.
 */
import { type Static, Type } from 'typebox';

export const VerifyLocationRequest = Type.Object({
  device: Type.Object({
    phoneNumber: Type.String({ pattern: '^\\+[1-9][0-9]{4,14}$', examples: ['+61412345678'] }),
  }),
  area: Type.Object({
    areaType: Type.Literal('CIRCLE'),
    center: Type.Object({
      latitude: Type.Number({ minimum: -90, maximum: 90 }),
      longitude: Type.Number({ minimum: -180, maximum: 180 }),
    }),
    radius: Type.Integer({ minimum: 1 }),
  }),
  maxAge: Type.Optional(Type.Integer({ minimum: 0 })),
});
export type VerifyLocationRequest = Static<typeof VerifyLocationRequest>;

export const VerificationResult = Type.Union([
  Type.Literal('TRUE'),
  Type.Literal('FALSE'),
  Type.Literal('PARTIAL'),
  Type.Literal('UNKNOWN'),
]);
export type VerificationResult = Static<typeof VerificationResult>;

export const VerifyLocationResponse = Type.Object({
  verificationResult: VerificationResult,
  /** Only present when verificationResult is PARTIAL. */
  matchRate: Type.Optional(Type.Integer({ minimum: 1, maximum: 99 })),
  lastLocationTime: Type.String({ format: 'date-time' }),
});
export type VerifyLocationResponse = Static<typeof VerifyLocationResponse>;
