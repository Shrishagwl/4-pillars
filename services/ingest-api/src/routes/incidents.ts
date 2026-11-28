import type { Verdict } from '@4p/contracts';
import type { FastifyPluginAsyncTypebox } from '@fastify/type-provider-typebox';
import type { FastifyReply } from 'fastify';
import type { IngestStore, MeterRow } from '../db/store.js';
import { idToken } from '../publisher.js';

/** The dashboard's Incident (apps/dashboard/src/types.ts): a Verdict plus where it is. */
export interface DashboardIncident extends Verdict {
  suburb: string;
  postcode: string;
  transformerIds: string[];
  meterIds: string[];
  openedAt: string;
}

/** What the engine's GET /incidents returns per incident. */
interface EngineIncident extends Verdict {
  openedAt: string;
  closedAt: string | null;
  meterIds: string[];
  transformerIds: string[];
  suburbs: string[];
}

type Fetch = typeof fetch;

export interface IncidentOptions {
  engineUrl: string;
  store?: IngestStore;
  fetch?: Fetch;
  /** How often the live stream asks the engine for changes. */
  pollMs?: number;
}

function mostCommon(values: string[]): string | undefined {
  const counts = new Map<string, number>();
  for (const v of values) counts.set(v, (counts.get(v) ?? 0) + 1);
  return [...counts.entries()].sort((a, b) => b[1] - a[1])[0]?.[0];
}

/** Turn the engine's incidents into the dashboard's shape, using our meter table for places. */
export function toDashboard(incidents: EngineIncident[], meters: MeterRow[]): DashboardIncident[] {
  const byId = new Map(meters.map((m) => [m.meterId, m]));
  return incidents
    .filter((i) => i.closedAt === null)
    .map((i) => {
      const known = i.meterIds.map((id) => byId.get(id)).filter((m) => m !== undefined);
      const suburb = mostCommon(known.map((m) => m.suburb)) ?? i.suburbs[0] ?? '';
      const postcode = known.find((m) => m.suburb === suburb)?.postcode ?? '';
      const { closedAt: _closed, suburbs: _suburbs, ...verdict } = i;
      return { ...verdict, suburb, postcode };
    })
    .sort((a, b) => b.openedAt.localeCompare(a.openedAt)); // newest first
}

// The dashboard is served from another origin (Firebase, or :3000 locally) and only reads.
function allowBrowsers(reply: FastifyReply) {
  reply.header('access-control-allow-origin', '*');
}

export const incidentRoutes: FastifyPluginAsyncTypebox<IncidentOptions> = async (app, opts) => {
  const fetchImpl = opts.fetch ?? fetch;
  const pollMs = opts.pollMs ?? 2000;

  async function load(): Promise<DashboardIncident[]> {
    const url = `${opts.engineUrl.replace(/\/$/, '')}/incidents`;
    const res = await fetchImpl(url, {
      headers: await idToken(url, fetchImpl),
      signal: AbortSignal.timeout(5000),
    });
    if (!res.ok) throw new Error(`engine answered ${res.status}`);
    const body = (await res.json()) as { incidents: EngineIncident[] };
    const meters = opts.store ? await opts.store.listMeters() : [];
    return toDashboard(body.incidents, meters);
  }

  app.get('/incidents', async (_req, reply) => {
    allowBrowsers(reply);
    try {
      return { incidents: await load() };
    } catch (err) {
      reply.log.warn({ err: String(err) }, 'engine not reachable for incidents');
      return reply.code(502).send({ error: 'ENGINE_UNAVAILABLE' });
    }
  });

  // Server-sent events: the dashboard opens one connection and gets the full list again
  // whenever anything changes. One poll of the engine is shared by every open connection.
  const clients = new Set<FastifyReply>();
  let last = '';
  let timer: NodeJS.Timeout | null = null;

  async function poll() {
    try {
      const json = JSON.stringify(await load());
      if (json !== last) {
        last = json;
        for (const c of clients) c.raw.write(`event: incidents\ndata: ${json}\n\n`);
      } else {
        for (const c of clients) c.raw.write(': still here\n\n'); // keeps proxies from closing it
      }
    } catch (err) {
      app.log.warn({ err: String(err) }, 'engine not reachable for the live stream');
    }
  }

  app.get('/incidents/stream', async (req, reply) => {
    reply.hijack();
    reply.raw.writeHead(200, {
      'content-type': 'text/event-stream',
      'cache-control': 'no-cache',
      connection: 'keep-alive',
      'access-control-allow-origin': '*',
    });
    clients.add(reply);
    if (last) reply.raw.write(`event: incidents\ndata: ${last}\n\n`);
    if (!timer) {
      await poll();
      timer = setInterval(poll, pollMs);
    }
    req.raw.on('close', () => {
      clients.delete(reply);
      if (clients.size === 0 && timer) {
        clearInterval(timer);
        timer = null;
        last = '';
      }
    });
  });

  app.addHook('onClose', async () => {
    if (timer) clearInterval(timer);
    for (const c of clients) c.raw.end();
  });
};
