/**
 * Location Verification API (Telstra beta), CAMARA location-verification 3.0.0.
 * Sources, read 28 Nov 2026:
 *  - CAMARA DeviceLocation release r3.2, code/API_definitions/location-verification.yaml (3.0.0)
 *  - Telstra's beta OpenAPI file on dev.telstra.com: server .../telstradev/v1/sandbox,
 *    path /location-verification/verify (CAMARA itself uses /location-verification/v3/verify)
 *
 * 3.0.0 dropped the UNKNOWN result: "can't locate it" is now a 422 UNABLE_TO_LOCATE error.
 */
import { type Static, Type } from 'typebox';

export const LOCATION_VERIFY_PATHS = [
  '/location-verification/verify', // Telstra sandbox
  '/location-verification/v3/verify', // CAMARA
] as const;

/** Telstra's sandbox enforces this; CAMARA lets operators set a larger minimum. */
export const MIN_RADIUS_M = 1000;

export const Device = Type.Object(
  {
    phoneNumber: Type.Optional(
      Type.String({ pattern: '^\\+[1-9][0-9]{4,14}$', examples: ['+61412345678'] }),
    ),
    networkAccessIdentifier: Type.Optional(Type.String()),
    ipv4Address: Type.Optional(
      Type.Object({
        publicAddress: Type.String(),
        privateAddress: Type.Optional(Type.String()),
        publicPort: Type.Optional(Type.Integer({ minimum: 0, maximum: 65535 })),
      }),
    ),
    ipv6Address: Type.Optional(Type.String()),
  },
  { minProperties: 1 },
);

export const VerifyLocationRequest = Type.Object({
  device: Type.Optional(Device),
  area: Type.Object({
    areaType: Type.Literal('CIRCLE'),
    center: Type.Object({
      latitude: Type.Number({ minimum: -90, maximum: 90 }),
      longitude: Type.Number({ minimum: -180, maximum: 180 }),
    }),
    radius: Type.Number({ minimum: 1 }),
  }),
  maxAge: Type.Optional(Type.Integer()),
});
export type VerifyLocationRequest = Static<typeof VerifyLocationRequest>;

export const VerificationResult = Type.Union([
  Type.Literal('TRUE'),
  Type.Literal('FALSE'),
  Type.Literal('PARTIAL'),
]);
export type VerificationResult = Static<typeof VerificationResult>;

export const VerifyLocationResponse = Type.Object({
  verificationResult: VerificationResult,
  /** Only present when verificationResult is PARTIAL. */
  matchRate: Type.Optional(Type.Integer({ minimum: 1, maximum: 99 })),
  /** RFC 3339 with a time zone, e.g. "2023-09-07T10:40:52Z". */
  lastLocationTime: Type.String({ format: 'date-time' }),
  device: Type.Optional(Device),
});
export type VerifyLocationResponse = Static<typeof VerifyLocationResponse>;

/** CAMARA's error body (different from the LoC / Network Availability `errors` array). */
export const CamaraError = Type.Object({
  status: Type.Integer(),
  code: Type.String({
    examples: [
      'INVALID_ARGUMENT',
      'OUT_OF_RANGE',
      'UNAUTHENTICATED',
      'PERMISSION_DENIED',
      'IDENTIFIER_NOT_FOUND',
      'MISSING_IDENTIFIER',
      'LOCATION_VERIFICATION.AREA_NOT_COVERED',
      'LOCATION_VERIFICATION.INVALID_AREA',
      'LOCATION_VERIFICATION.UNABLE_TO_FULFILL_MAX_AGE',
      'LOCATION_VERIFICATION.UNABLE_TO_LOCATE',
    ],
  }),
  message: Type.String(),
});
export type CamaraError = Static<typeof CamaraError>;
