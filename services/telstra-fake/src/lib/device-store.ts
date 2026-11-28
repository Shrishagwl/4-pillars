import type { Clock } from './clock.js';

/** Where the network thinks a SIM is. The twin sets this; the fake never makes it up. */
export interface DeviceFix {
  latitude: number;
  longitude: number;
  /** Radius of the network's estimate in metres. Cell-based fixes are rough. */
  accuracy: number;
  /** When the network last located it (ISO 8601). */
  locatedAt: string;
  /** False when the network can't locate it at all (for example the SIM has no power). */
  locatable: boolean;
}

export type Verdict =
  | { result: 'TRUE' | 'FALSE'; lastLocationTime: string }
  | { result: 'PARTIAL'; matchRate: number; lastLocationTime: string }
  | { error: 'NOT_FOUND' | 'UNABLE_TO_LOCATE' | 'TOO_OLD' };

const EARTH_RADIUS_M = 6_371_000;
export const DEFAULT_ACCURACY_M = 300;

/** Great-circle distance in metres. */
export function distanceM(lat1: number, lon1: number, lat2: number, lon2: number): number {
  const rad = Math.PI / 180;
  const dLat = (lat2 - lat1) * rad;
  const dLon = (lon2 - lon1) * rad;
  const a =
    Math.sin(dLat / 2) ** 2 + Math.cos(lat1 * rad) * Math.cos(lat2 * rad) * Math.sin(dLon / 2) ** 2;
  return 2 * EARTH_RADIUS_M * Math.asin(Math.sqrt(a));
}

/** Area where two circles overlap (radii r and R, centres d apart). */
function overlapArea(r: number, R: number, d: number): number {
  if (d >= r + R) return 0;
  if (d <= Math.abs(R - r)) return Math.PI * Math.min(r, R) ** 2;
  const a = r * r * Math.acos((d * d + r * r - R * R) / (2 * d * r));
  const b = R * R * Math.acos((d * d + R * R - r * r) / (2 * d * R));
  const c = 0.5 * Math.sqrt((-d + r + R) * (d + r - R) * (d - r + R) * (d + r + R));
  return a + b - c;
}

/**
 * CAMARA's rule, with the network's estimate as a circle:
 *  - estimate fully inside the requested area -> TRUE
 *  - no overlap at all -> FALSE
 *  - partly overlapping, or the estimate is bigger than the area -> PARTIAL, and matchRate is
 *    the share of the estimate that falls inside the area (1-99)
 */
export function compare(
  fix: Pick<DeviceFix, 'latitude' | 'longitude' | 'accuracy'>,
  center: { latitude: number; longitude: number },
  radius: number,
): { result: 'TRUE' | 'FALSE' } | { result: 'PARTIAL'; matchRate: number } {
  const d = distanceM(fix.latitude, fix.longitude, center.latitude, center.longitude);
  const u = fix.accuracy;
  if (d + u <= radius) return { result: 'TRUE' };
  if (d >= radius + u) return { result: 'FALSE' };
  const share = overlapArea(u, radius, d) / (Math.PI * u * u);
  return { result: 'PARTIAL', matchRate: Math.min(99, Math.max(1, Math.round(share * 100))) };
}

/** Phone numbers are stored in E.164 with the plus, the way CAMARA sends them. */
export function e164(phone: string): string {
  return phone.startsWith('+') ? phone : `+${phone}`;
}

export class DeviceStore {
  private fixes = new Map<string, DeviceFix>();

  constructor(private readonly clock: Clock) {}

  set(phone: string, fix: Partial<DeviceFix> & { latitude: number; longitude: number }): void {
    this.fixes.set(e164(phone), {
      accuracy: DEFAULT_ACCURACY_M,
      locatedAt: this.clock.now().toISOString(),
      locatable: true,
      ...fix,
    });
  }

  clear(): void {
    this.fixes.clear();
  }

  verify(
    phone: string,
    center: { latitude: number; longitude: number },
    radius: number,
    maxAge?: number,
  ): Verdict {
    const fix = this.fixes.get(e164(phone));
    if (!fix) return { error: 'NOT_FOUND' };
    if (!fix.locatable) return { error: 'UNABLE_TO_LOCATE' };
    const ageS = (this.clock.now().getTime() - Date.parse(fix.locatedAt)) / 1000;
    if (maxAge !== undefined && ageS > maxAge) return { error: 'TOO_OLD' };
    return { ...compare(fix, center, radius), lastLocationTime: fix.locatedAt };
  }
}
