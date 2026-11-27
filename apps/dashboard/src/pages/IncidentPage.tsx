import { useState } from 'react';
import { CausePill } from '../components/CausePill.tsx';
import { EvidenceTimeline } from '../components/EvidenceTimeline.tsx';
import { Icon } from '../components/Icon.tsx';
import { MeterMap } from '../components/MeterMap.tsx';
import { ProbabilityBars } from '../components/ProbabilityBars.tsx';
import type { Cause, Incident, Meter } from '../types.ts';
import {
  ACTION_TEXT,
  actionSentence,
  CAUSE_STYLE,
  humanise,
  needsReview,
  REVIEW_STYLE,
} from '../utils/causes.ts';
import { chooseAction, savedDollars } from '../utils/costs.ts';
import { clockTime, count, dollars, percent, timeAgo } from '../utils/format.ts';

interface Props {
  meters: Meter[];
  incidents: Incident[];
  selected: Incident | undefined;
  now: number;
  isDone: (incidentId: string) => boolean;
  onSelect: (incidentId: string) => void;
  onAct: (incidentId: string) => void;
  onShowOnMap: (incidentId: string) => void;
}

type Filter = 'ALL' | Cause;

const FILTERS: { id: Filter; label: string }[] = [
  { id: 'ALL', label: 'All' },
  { id: 'POWER', label: 'Power' },
  { id: 'NETWORK', label: 'Network' },
  { id: 'METER_FAULT', label: 'Fault' },
  { id: 'TAMPER', label: 'Tamper' },
];

/** Screen 02 in Figma: the incident queue on the left, everything about one incident on the right. */
export function IncidentPage(props: Props) {
  const { incidents, selected, now } = props;
  const [filter, setFilter] = useState<Filter>('ALL');
  const shown = filter === 'ALL' ? incidents : incidents.filter((i) => i.cause === filter);

  return (
    <main className="incident-page">
      <aside className="queue" aria-label="Incident queue">
        <div className="queue__head">
          <h1 className="queue__title">
            Incidents <span className="badge">{incidents.length} open</span>
          </h1>
          <fieldset className="chips" aria-label="Filter by cause">
            {FILTERS.map((f) => (
              <button
                key={f.id}
                type="button"
                className={`chip${f.id === filter ? ' chip--active' : ''}`}
                onClick={() => setFilter(f.id)}
              >
                {f.label}
              </button>
            ))}
          </fieldset>
        </div>
        <ul>
          {shown.map((incident) => (
            <li key={incident.incidentId}>
              <QueueRow
                incident={incident}
                now={now}
                active={incident.incidentId === selected?.incidentId}
                onClick={() => props.onSelect(incident.incidentId)}
              />
            </li>
          ))}
        </ul>
        {shown.length === 0 && <p className="muted small queue__empty">No incidents match.</p>}
      </aside>

      {selected ? (
        <IncidentDetail {...props} incident={selected} />
      ) : (
        <section className="detail detail--empty muted">Pick an incident on the left.</section>
      )}
    </main>
  );
}

function QueueRow(props: {
  incident: Incident;
  now: number;
  active: boolean;
  onClick: () => void;
}) {
  const { incident, now, active } = props;
  const review = needsReview(incident);
  return (
    <button
      type="button"
      className={`queue-row${active ? ' queue-row--active' : ''}`}
      onClick={props.onClick}
    >
      <span className="queue-row__bar" style={{ background: CAUSE_STYLE[incident.cause].color }} />
      <span className="queue-row__text">
        <span className="eyebrow">
          {incident.incidentId} <span className="muted">{timeAgo(incident.openedAt, now)}</span>
        </span>
        <strong className="queue-row__suburb">{incident.suburb}</strong>
        <span className="queue-row__tags">
          <CausePill incident={incident} />
          <span className="muted small">
            {count(incident.meterCount)} {incident.meterCount === 1 ? 'meter' : 'meters'}
          </span>
        </span>
      </span>
      <span className="queue-row__conf">
        <strong className={review ? 'text-alert' : undefined}>
          {percent(incident.confidence)}
        </strong>
        <span className="muted tiny">confidence</span>
      </span>
    </button>
  );
}

function IncidentDetail(props: Props & { incident: Incident }) {
  const { incident, meters, incidents } = props;
  const review = needsReview(incident);
  const style = review ? REVIEW_STYLE : CAUSE_STYLE[incident.cause];
  const done = props.isDone(incident.incidentId);
  const choice = chooseAction(incident.probabilities, incident.meterCount);

  return (
    <section className="detail">
      <p className="breadcrumb muted small">Incidents / {incident.incidentId}</p>

      <div className="detail__head">
        <div>
          <h1>
            {incident.suburb} {CAUSE_STYLE[incident.cause].label.toLowerCase()}
          </h1>
          <p className="muted">
            {count(incident.meterCount)} {incident.meterCount === 1 ? 'meter' : 'meters'} ·
            transformer {incident.transformerIds.join(', ')} · opened {clockTime(incident.openedAt)}
          </p>
        </div>
        <div className="button-row">
          <button type="button" className="button button--ghost" disabled title="Coming soon">
            Override
          </button>
          <button
            type="button"
            className="button button--primary"
            onClick={() => props.onAct(incident.incidentId)}
            disabled={done}
          >
            <Icon name={done ? 'check' : 'zap'} />
            {done ? ACTION_TEXT[incident.action].done : ACTION_TEXT[incident.action].button}
          </button>
        </div>
      </div>

      <div className="detail__row">
        <article className="card likely-cause">
          <span className="eyebrow eyebrow--caps">Likely cause</span>
          <div className="likely-cause__big">
            <span className="likely-cause__percent" style={{ color: style.color }}>
              {percent(incident.confidence)}
            </span>
            <div>
              <h2 className="likely-cause__name">
                {CAUSE_STYLE[incident.cause].label}
                {review && <CausePill incident={incident} />}
              </h2>
              <p className="muted small">
                {review
                  ? 'Not sure enough to act alone. An operator should check it first.'
                  : 'Confident enough to recommend an action without a human check.'}
              </p>
            </div>
          </div>
          <ProbabilityBars incident={incident} />
        </article>

        <article className="card mini-map">
          {/* key= makes React build a fresh map when the incident changes, so it re-zooms. */}
          <MeterMap
            key={incident.incidentId}
            meters={meters}
            incidents={incidents}
            selectedId={incident.incidentId}
            focusId={incident.incidentId}
          />
          <button
            type="button"
            className="map-overlay map-overlay--top map-overlay--button"
            onClick={() => props.onShowOnMap(incident.incidentId)}
          >
            <Icon name="map" /> Open on map
          </button>
        </article>
      </div>

      <div className="detail__row detail__row--bottom">
        <article className="action-card">
          <span className="eyebrow eyebrow--caps">Recommended action</span>
          <h2 className="action-card__title">{actionSentence(incident)}</h2>
          <p className="action-card__why">
            {review
              ? `Only ${percent(incident.confidence)} sure, below the 60% needed to act alone.`
              : `Expected extra cost ${dollars(choice.cost)}. The next best option (${humanise(
                  choice.runnerUp,
                )}) would cost about ${dollars(choice.runnerUpCost)}.`}
          </p>
          <div className="action-card__spacer" />
          <span className="action-card__saved">{dollars(savedDollars(incident))} saved</span>
          <span className="action-card__note">vs. sending a technician to every silent meter</span>
          <button
            type="button"
            className="button button--light"
            onClick={() => props.onAct(incident.incidentId)}
            disabled={done}
          >
            {done
              ? ACTION_TEXT[incident.action].done
              : `${ACTION_TEXT[incident.action].button} now`}
          </button>
        </article>

        <EvidenceTimeline incident={incident} />
      </div>
    </section>
  );
}
