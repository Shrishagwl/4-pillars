/**
 * Network Availability API v1.1.0.
 * GET .../mobility/products-api/network-availability/v1/status?suburb=&state=&postcode=
 *
 * Known from the public docs:
 *  - the response groups outages into past / current / near_future / far_future
 *  - some current outages carry `affected_area` as a WKT MULTIPOLYGON
 *  - timestamps look like "2026-05-13 00:03:00 Australia/Melbourne" (not ISO 8601)
 *
 * TODO(platform, #10): fill in the remaining outage field names from the public docs.
 * Until then extra fields pass through untouched.
 */
import { type Static, Type } from 'typebox';

export const AU_STATES = ['QLD', 'NSW', 'ACT', 'VIC', 'TAS', 'SA', 'WA', 'NT'] as const;

export const NetworkStatusQuery = Type.Object({
  suburb: Type.String({ minLength: 1 }),
  state: Type.Union(AU_STATES.map((s) => Type.Literal(s))),
  postcode: Type.String({ pattern: '^[0-9]{4}$' }),
});
export type NetworkStatusQuery = Static<typeof NetworkStatusQuery>;

export const Outage = Type.Object(
  {
    /** WKT MULTIPOLYGON, only on selected current outages. */
    affected_area: Type.Optional(Type.String()),
  },
  { additionalProperties: true },
);
export type Outage = Static<typeof Outage>;

export const NetworkStatusResponse = Type.Object(
  {
    past: Type.Optional(Type.Array(Outage)),
    current: Type.Optional(Type.Array(Outage)),
    near_future: Type.Optional(Type.Array(Outage)),
    far_future: Type.Optional(Type.Array(Outage)),
  },
  { additionalProperties: true },
);
export type NetworkStatusResponse = Static<typeof NetworkStatusResponse>;
