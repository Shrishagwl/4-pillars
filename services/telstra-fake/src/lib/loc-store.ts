import type { LocSubscription } from '@4p/contracts';
import { authHeaders } from './google-id-token.js';

/** One trigger: this SIM just lost connectivity. */
export interface LocEvent {
  msisdn: string;
  lossOfConnectReason: number;
  /** RFC 3339. Defaults to now. */
  eventTime?: string;
}

export interface Delivery {
  subscriptionId: string;
  notificationDestination: string;
  reports: number;
  status: number | null; // HTTP status from the callback, null if it could not be reached
}

/**
 * Subscriptions live in memory: one per MSISDN, like the real API (each MSISDN in a request gets
 * its own subscriptionId). A restart forgets them, which is fine for a fake.
 */
export class LocStore {
  private byId = new Map<string, LocSubscription>();
  private byMsisdn = new Map<string, string>();

  constructor(private readonly timeoutMs = 5000) {}

  add(msisdn: string, notificationDestination: string): LocSubscription | null {
    if (this.byMsisdn.has(msisdn)) return null;
    const sub = { subscriptionId: crypto.randomUUID(), msisdn, notificationDestination };
    this.byId.set(sub.subscriptionId, sub);
    this.byMsisdn.set(msisdn, sub.subscriptionId);
    return sub;
  }

  get(id: string): LocSubscription | undefined {
    return this.byId.get(id);
  }

  remove(id: string): boolean {
    const sub = this.byId.get(id);
    if (!sub) return false;
    this.byId.delete(id);
    this.byMsisdn.delete(sub.msisdn);
    return true;
  }

  /** Oldest first. The cursor is the id of the last subscription on the previous page. */
  page(limit: number, cursor?: string): { items: LocSubscription[]; nextCursor?: string } {
    const all = [...this.byId.values()];
    const start = cursor ? all.findIndex((s) => s.subscriptionId === cursor) + 1 : 0;
    const items = all.slice(start, start + limit);
    const more = start + limit < all.length;
    return { items, nextCursor: more ? items.at(-1)?.subscriptionId : undefined };
  }

  /**
   * Send each event to its subscription's callback, one POST per subscription. Events for SIMs
   * nobody subscribed are dropped, as Telstra would.
   */
  async deliver(events: LocEvent[]): Promise<{ deliveries: Delivery[]; unsubscribed: string[] }> {
    const grouped = new Map<string, LocEvent[]>();
    const unsubscribed: string[] = [];
    for (const event of events) {
      const id = this.byMsisdn.get(event.msisdn);
      if (!id) unsubscribed.push(event.msisdn);
      else grouped.set(id, [...(grouped.get(id) ?? []), event]);
    }

    const deliveries = await Promise.all(
      [...grouped].map(async ([id, list]) => {
        const sub = this.byId.get(id) as LocSubscription;
        const body = {
          subscriptionId: id,
          monitoringEventReports: list.map((e) => ({
            monitoringType: 'LOSS_OF_CONNECTIVITY',
            msisdn: e.msisdn,
            lossOfConnectReason: e.lossOfConnectReason,
            eventTime: e.eventTime ?? new Date().toISOString(),
          })),
        };
        let status: number | null = null;
        try {
          const res = await fetch(sub.notificationDestination, {
            method: 'POST',
            headers: {
              'content-type': 'application/json',
              ...(await authHeaders(sub.notificationDestination)),
            },
            body: JSON.stringify(body),
            signal: AbortSignal.timeout(this.timeoutMs),
          });
          status = res.status;
        } catch {
          status = null;
        }
        return {
          subscriptionId: id,
          notificationDestination: sub.notificationDestination,
          reports: list.length,
          status,
        };
      }),
    );
    return { deliveries, unsubscribed };
  }
}
