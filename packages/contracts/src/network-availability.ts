/**
 * Network Availability API v1.1.0.
 * GET .../mobility/products-api/network-availability/v1/status?suburb=&state=&postcode=
 *
 * Field names copied from the public OpenAPI file on dev.telstra.com (IoT Network Availability
 * API 1.1.0), read 28 Nov 2026.
 *  - outages come back grouped as past / current / near_future (next 24 h) / far_future
 *  - timestamps look like "2025-09-29 21:43:00 Australia/Melbourne" (not ISO 8601)
 *  - some outages carry `affected_area`, a WKT MULTIPOLYGON in lon lat order
 */
import { type Static, Type } from 'typebox';

export const NETWORK_STATUS_PATH = '/network-availability/v1/status';

/** NAT is a national outage; INT and OT are also accepted by the API. */
export const AU_STATES = [
  'QLD',
  'NSW',
  'ACT',
  'VIC',
  'TAS',
  'SA',
  'WA',
  'NAT',
  'NT',
  'INT',
  'OT',
] as const;

export const NetworkStatusQuery = Type.Object({
  suburb: Type.String({ minLength: 1 }),
  state: Type.String({ minLength: 1 }), // case-insensitive, checked against AU_STATES
  postcode: Type.String({ pattern: '^[0-9]{4}$' }),
});
export type NetworkStatusQuery = Static<typeof NetworkStatusQuery>;

export const Outage = Type.Object(
  {
    state: Type.String(),
    suburb: Type.String(), // upper case in the examples, e.g. "MELBOURNE"
    postcode: Type.String(),
    start_timestamp: Type.String({ examples: ['2025-09-29 21:43:00 Australia/Melbourne'] }),
    end_timestamp: Type.Union([Type.String(), Type.Null()]), // null while ongoing
    root_cause: Type.String(),
    duration: Type.Integer({ description: 'seconds' }),
    description: Type.String(),
    is_planned: Type.Boolean(),
    technology: Type.String({ examples: ['4G', '5G'] }),
    /** WKT MULTIPOLYGON, only on some outages. */
    affected_area: Type.Optional(Type.String()),
  },
  { additionalProperties: true },
);
export type Outage = Static<typeof Outage>;

export const NetworkStatusResponse = Type.Object(
  {
    'correlation-id': Type.String(),
    status: Type.Integer(),
    timeStamp: Type.Integer({ description: 'Unix milliseconds' }),
    past: Type.Array(Outage),
    current: Type.Array(Outage),
    near_future: Type.Array(Outage),
    far_future: Type.Array(Outage),
  },
  { additionalProperties: true },
);
export type NetworkStatusResponse = Static<typeof NetworkStatusResponse>;

const MELBOURNE = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'Australia/Melbourne',
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
  hourCycle: 'h23',
});

/** A Date as Telstra writes it: "2026-11-25 11:05:00 Australia/Melbourne". */
export function toMelbourneTimestamp(date: Date): string {
  const p = Object.fromEntries(MELBOURNE.formatToParts(date).map((x) => [x.type, x.value]));
  return `${p.year}-${p.month}-${p.day} ${p.hour}:${p.minute}:${p.second} Australia/Melbourne`;
}

/**
 * The reverse: "2026-11-25 11:05:00 Australia/Melbourne" to a Date. Melbourne is UTC+10 or +11
 * depending on daylight saving, so we try both offsets and keep the one that formats back to the
 * same wall-clock time. Returns null for anything else.
 */
export function fromMelbourneTimestamp(text: string): Date | null {
  const m = /^(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2}):(\d{2}) Australia\/Melbourne$/.exec(text);
  if (!m) return null;
  const [y, mo, d, h, mi, s] = m.slice(1).map(Number) as [
    number,
    number,
    number,
    number,
    number,
    number,
  ];
  for (const offsetHours of [11, 10]) {
    const date = new Date(Date.UTC(y, mo - 1, d, h - offsetHours, mi, s));
    if (toMelbourneTimestamp(date) === text) return date;
  }
  return null;
}
