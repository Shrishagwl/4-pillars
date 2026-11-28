/**
 * Where the dashboard's data comes from. Mock data is still the default, so the dashboard runs
 * with nothing else started. Build with VITE_DATA_SOURCE=api to use the live backend:
 *
 *   GET  {VITE_INGEST_URL}/meters            the map
 *   GET  {VITE_INGEST_URL}/incidents         the incidents right now
 *   SSE  {VITE_INGEST_URL}/incidents/stream  the list again every time it changes
 *
 * The browser's EventSource reconnects by itself if the connection drops.
 */
import { useEffect, useState } from 'react';
import type { Incident, Meter } from '../types.ts';
import { createMockData, type DashboardData } from './mockData.ts';

export type Source = 'mock' | 'api';

export const SOURCE: Source = import.meta.env.VITE_DATA_SOURCE === 'api' ? 'api' : 'mock';
const INGEST_URL = (import.meta.env.VITE_INGEST_URL ?? 'http://localhost:8081').replace(/\/$/, '');

const mock = SOURCE === 'mock' ? createMockData() : null;

export interface LiveData extends DashboardData {
  /** False until the first answer from the backend; always true for mock data. */
  ready: boolean;
  /** Set when the backend can't be reached. */
  error: string | null;
}

export function useDashboardData(): LiveData {
  const [meters, setMeters] = useState<Meter[]>(mock?.meters ?? []);
  const [incidents, setIncidents] = useState<Incident[]>(mock?.incidents ?? []);
  const [ready, setReady] = useState(SOURCE === 'mock');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (SOURCE === 'mock') return;
    let stopped = false;

    fetch(`${INGEST_URL}/meters`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`meters: ${res.status}`))))
      .then((body: { meters: Meter[] }) => !stopped && setMeters(body.meters))
      .catch((err: Error) => !stopped && setError(err.message));

    const stream = new EventSource(`${INGEST_URL}/incidents/stream`);
    stream.addEventListener('incidents', (event) => {
      setIncidents(JSON.parse((event as MessageEvent<string>).data));
      setReady(true);
      setError(null);
    });
    stream.onerror = () => setError('Lost the connection to the backend, retrying...');

    return () => {
      stopped = true;
      stream.close();
    };
  }, []);

  return { meters, incidents, ready, error };
}
