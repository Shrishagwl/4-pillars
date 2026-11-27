import { Icon } from '../components/Icon.tsx';
import { KpiRow } from '../components/KpiRow.tsx';
import { MeterMap } from '../components/MeterMap.tsx';
import { OtherIncidents } from '../components/OtherIncidents.tsx';
import { VerdictCard } from '../components/VerdictCard.tsx';
import type { Incident, Meter } from '../types.ts';
import { CAUSE_STYLE, CAUSES } from '../utils/causes.ts';
import { count, timeAgo } from '../utils/format.ts';

interface Props {
  meters: Meter[];
  incidents: Incident[]; // everything, for the map and the numbers
  listed: Incident[]; // what matches the search box
  selected: Incident | undefined;
  now: number;
  isDone: (incidentId: string) => boolean;
  onSelect: (incidentId: string) => void;
  onAct: (incidentId: string) => void;
  onOpenDetails: (incidentId: string) => void;
  onViewAll: () => void;
}

/** Screen 01 in Figma: numbers on top, the map, and the selected incident on the right. */
export function OverviewPage(props: Props) {
  const { meters, incidents, listed, selected, now } = props;
  const lastUpdate = incidents
    .map((i) => i.updatedAt)
    .sort()
    .at(-1);

  return (
    <main className="page overview">
      <div className="page-header">
        <div>
          <h1>Grid &amp; network triage</h1>
          <p className="muted">
            {count(meters.length)} smart meters across Coburg and Brunswick · updated{' '}
            {lastUpdate ? timeAgo(lastUpdate, now) : 'never'}
          </p>
        </div>
        <div className="page-header__actions">
          <fieldset className="segmented" aria-label="Data source">
            <button type="button" className="segmented__item segmented__item--active">
              Live
            </button>
            <button type="button" className="segmented__item" disabled title="Coming soon">
              Replay
            </button>
          </fieldset>
          {/* Wired up in task 7 (scenario controls), which calls the twin service. */}
          <button type="button" className="button button--primary" disabled title="Task 7">
            <Icon name="play" /> Inject fault
          </button>
        </div>
      </div>

      <KpiRow meters={meters} incidents={incidents} now={now} />

      <div className="overview__main">
        <section className="card map-card" aria-label="Map of meters">
          <MeterMap
            meters={meters}
            incidents={incidents}
            selectedId={selected?.incidentId}
            onSelect={props.onSelect}
          />
          <div className="map-overlay map-overlay--top">
            <Icon name="map" />
            Coburg &amp; Brunswick · {incidents.length} active incidents
          </div>
          <ul className="map-overlay map-overlay--legend">
            {CAUSES.map((cause) => (
              <li key={cause}>
                <span className="dot" style={{ background: CAUSE_STYLE[cause].color }} />
                {CAUSE_STYLE[cause].label}
              </li>
            ))}
            <li>
              <span className="dot dot--online" />
              Reporting normally
            </li>
          </ul>
        </section>

        <div className="overview__side">
          {selected ? (
            <VerdictCard
              incident={selected}
              now={now}
              done={props.isDone(selected.incidentId)}
              onAct={() => props.onAct(selected.incidentId)}
              onDetails={() => props.onOpenDetails(selected.incidentId)}
            />
          ) : (
            <article className="card empty-card">
              <span className="dot" style={{ background: 'var(--shamrock-60)' }} />
              No open incidents. All meters are reporting.
            </article>
          )}
          <OtherIncidents
            incidents={listed.filter((i) => i.incidentId !== selected?.incidentId)}
            onSelect={props.onSelect}
            onViewAll={props.onViewAll}
          />
        </div>
      </div>
    </main>
  );
}
