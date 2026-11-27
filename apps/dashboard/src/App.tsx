/**
 * The top of the app. It holds the state every screen shares:
 *   - which screen is showing (Overview or Incidents)
 *   - which incident is selected
 *   - what is typed in the search box
 *   - which incidents the operator has already acted on
 * and passes it down to the screens as props.
 */
import { useEffect, useMemo, useState } from 'react';
import { TopNav } from './components/TopNav.tsx';
import { createMockData } from './data/mockData.ts';
import { IncidentPage } from './pages/IncidentPage.tsx';
import { OverviewPage } from './pages/OverviewPage.tsx';
import type { Incident, View } from './types.ts';

// For now the data is mock data (task 2). When ingest-api's GET /incidents and live updates
// are ready, this is the one line that changes.
const data = createMockData();

export default function App() {
  const [view, setView] = useState<View>('overview');
  const [selectedId, setSelectedId] = useState(data.incidents[0]?.incidentId);
  const [search, setSearch] = useState('');
  const [doneIds, setDoneIds] = useState<string[]>([]);
  const now = useClock(30_000);

  const listed = useMemo(
    () => data.incidents.filter((incident) => matchesSearch(incident, search)),
    [search],
  );
  const selected = data.incidents.find((i) => i.incidentId === selectedId);

  const isDone = (id: string) => doneIds.includes(id);
  const act = (id: string) => setDoneIds((ids) => (ids.includes(id) ? ids : [...ids, id]));
  const goTo = (nextView: View, id?: string) => {
    if (id) setSelectedId(id);
    setView(nextView);
  };

  return (
    <div className="app">
      <TopNav
        view={view}
        onViewChange={setView}
        search={search}
        onSearchChange={(text) => {
          setSearch(text);
          if (text && view === 'overview') setView('incidents'); // show results in the queue
        }}
      />
      {view === 'overview' ? (
        <OverviewPage
          meters={data.meters}
          incidents={data.incidents}
          listed={listed}
          selected={selected}
          now={now}
          isDone={isDone}
          onSelect={setSelectedId}
          onAct={act}
          onOpenDetails={(id) => goTo('incidents', id)}
          onViewAll={() => goTo('incidents')}
        />
      ) : (
        <IncidentPage
          meters={data.meters}
          incidents={listed}
          selected={selected}
          now={now}
          isDone={isDone}
          onSelect={setSelectedId}
          onAct={act}
          onShowOnMap={(id) => goTo('overview', id)}
        />
      )}
    </div>
  );
}

function matchesSearch(incident: Incident, text: string): boolean {
  const q = text.trim().toLowerCase();
  if (!q) return true;
  const haystack = [
    incident.incidentId,
    incident.suburb,
    incident.postcode,
    ...incident.transformerIds,
    ...incident.meterIds,
  ];
  return haystack.some((value) => value.toLowerCase().includes(q));
}

/** Gives the current time and refreshes it every few seconds, so "3 min ago" stays right. */
function useClock(everyMs: number): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), everyMs);
    return () => clearInterval(timer); // stop the timer if the component goes away
  }, [everyMs]);
  return now;
}
