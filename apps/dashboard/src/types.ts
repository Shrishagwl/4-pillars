/**
 * The shapes of the data the dashboard works with.
 *
 * Cause, Action and Verdict come from the team's shared contracts package, so the dashboard
 * and the engine always agree on what a verdict looks like. If the engine changes the Verdict,
 * TypeScript will flag every place in the dashboard that needs updating.
 */
import type { Action, Cause, Verdict } from '@4p/contracts';

export type { Action, Cause, Verdict };

/** One smart meter. Same fields as the twin's Meter (services/twin/src/twin/grid.py). */
export interface Meter {
  meterId: string; // e.g. "M-0412"
  msisdn: string; // the SIM's phone number, e.g. "61412000412"
  transformerId: string; // e.g. "T-07"
  suburb: string;
  postcode: string;
  lat: number;
  lon: number;
}

/**
 * An incident is the engine's Verdict plus a few extra facts the dashboard needs to draw it.
 * `extends` means "everything in Verdict, and also these fields".
 *
 * Note for the backend: GET /incidents on ingest-api should return these extra fields too.
 */
export interface Incident extends Verdict {
  suburb: string;
  postcode: string;
  transformerIds: string[];
  meterIds: string[];
  /** When the first meter in the cluster went silent (UTC, ISO 8601). */
  openedAt: string;
}

/** The two screens. */
export type View = 'overview' | 'incidents';
