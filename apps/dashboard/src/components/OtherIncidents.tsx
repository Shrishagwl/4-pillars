import type { Incident } from '../types.ts';
import { CAUSE_STYLE, needsReview, REVIEW_STYLE } from '../utils/causes.ts';
import { count, percent } from '../utils/format.ts';

interface Props {
  incidents: Incident[];
  onSelect: (incidentId: string) => void;
  onViewAll: () => void;
}

/** The short list under the verdict card on the Overview. */
export function OtherIncidents({ incidents, onSelect, onViewAll }: Props) {
  return (
    <article className="card other-incidents">
      <header className="other-incidents__head">
        <h2 className="card-title">Other incidents</h2>
        <button type="button" className="link-button" onClick={onViewAll}>
          View all
        </button>
      </header>

      {incidents.length === 0 && <p className="muted small">Nothing else open right now.</p>}

      <ul>
        {incidents.map((incident) => {
          const review = needsReview(incident);
          const label = review ? REVIEW_STYLE.label : CAUSE_STYLE[incident.cause].label;
          return (
            <li key={incident.incidentId}>
              <button
                type="button"
                className="other-incidents__row"
                onClick={() => onSelect(incident.incidentId)}
              >
                <span
                  className="dot"
                  style={{ background: CAUSE_STYLE[incident.cause].color }}
                  aria-hidden="true"
                />
                <span className="other-incidents__text">
                  <strong>{incident.suburb}</strong>
                  <span className="muted small">
                    {label} · {count(incident.meterCount)}{' '}
                    {incident.meterCount === 1 ? 'meter' : 'meters'}
                  </span>
                </span>
                <span className={`other-incidents__conf${review ? ' text-alert' : ''}`}>
                  {percent(incident.confidence)}
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </article>
  );
}
