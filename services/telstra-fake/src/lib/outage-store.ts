import { type Outage, toMelbourneTimestamp } from '@4p/contracts';
import type { Clock } from './clock.js';

/** What the twin sends to add an outage. Times are ISO 8601; the store formats them. */
export interface NewOutage {
  state: string;
  suburb: string;
  postcode: string;
  start: string;
  /** Leave out for an outage that is still going. */
  end?: string;
  root_cause?: string;
  description?: string;
  is_planned?: boolean;
  technology?: string;
  affected_area?: string;
}

interface Stored extends NewOutage {
  id: string;
}

const DAY_MS = 24 * 60 * 60 * 1000;

export type Grouped = Record<'past' | 'current' | 'near_future' | 'far_future', Outage[]>;

/**
 * Outages the twin has added, answered in Network Availability's shape. Which group an outage
 * is in depends on the clock: started and not ended is `current`, starting in the next 24 hours
 * is `near_future` (the spec's wording), later than that is `far_future`.
 */
export class OutageStore {
  private outages = new Map<string, Stored>();

  constructor(private readonly clock: Clock) {}

  add(outage: NewOutage): string {
    const id = crypto.randomUUID();
    this.outages.set(id, { ...outage, id });
    return id;
  }

  /** Mark an outage as over (the twin calls this when the network comes back). */
  end(id: string, when: string): boolean {
    const outage = this.outages.get(id);
    if (!outage) return false;
    outage.end = when;
    return true;
  }

  clear(): void {
    this.outages.clear();
  }

  /** Outages for one place, plus national (NAT) ones, which the API says may be included. */
  query(suburb: string, state: string, postcode: string): Grouped {
    const now = this.clock.now().getTime();
    const groups: Grouped = { past: [], current: [], near_future: [], far_future: [] };
    for (const o of this.outages.values()) {
      const national = o.state.toUpperCase() === 'NAT';
      const here =
        o.suburb.toUpperCase() === suburb.toUpperCase() &&
        o.state.toUpperCase() === state.toUpperCase() &&
        o.postcode === postcode;
      if (!here && !national) continue;

      const start = Date.parse(o.start);
      const end = o.end ? Date.parse(o.end) : null;
      const group =
        end !== null && end <= now
          ? 'past'
          : start <= now
            ? 'current'
            : start - now <= DAY_MS
              ? 'near_future'
              : 'far_future';
      groups[group].push(this.format(o, start, end, now));
    }
    return groups;
  }

  private format(o: Stored, start: number, end: number | null, now: number): Outage {
    // Ongoing outages report their duration so far.
    const duration = Math.max(0, Math.round(((end ?? Math.max(now, start)) - start) / 1000));
    return {
      state: o.state.toUpperCase(),
      suburb: o.suburb.toUpperCase(),
      postcode: o.postcode,
      start_timestamp: toMelbourneTimestamp(new Date(start)),
      end_timestamp: end === null ? null : toMelbourneTimestamp(new Date(end)),
      root_cause: o.root_cause ?? 'Telstra Network (Hardware/Software/Config)',
      duration,
      description:
        o.description ??
        'Customers may experience difficulties making and receiving calls or using data via their mobile service.',
      is_planned: o.is_planned ?? false,
      technology: o.technology ?? '4G',
      ...(o.affected_area ? { affected_area: o.affected_area } : {}),
    };
  }
}
