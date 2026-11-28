import type { Incident } from '../types.ts';
import { ACTION_TEXT, CAUSE_STYLE, needsReview, REVIEW_STYLE } from '../utils/causes.ts';
import { timeAgo } from '../utils/format.ts';
import { CausePill } from './CausePill.tsx';
import { ConfidenceDonut } from './ConfidenceDonut.tsx';
import { ProbabilityBars } from './ProbabilityBars.tsx';

interface Props {
  incident: Incident;
  now: number;
  done: boolean;
  onAct: () => void;
  onDetails: () => void;
}

/** The card on the right of the Overview: cause, confidence and what to do (task 6). */
export function VerdictCard({ incident, now, done, onAct, onDetails }: Props) {
  const review = needsReview(incident);
  const color = review ? REVIEW_STYLE.color : CAUSE_STYLE[incident.cause].color;

  return (
    <article className="card verdict-card">
      <header className="verdict-card__head">
        <div>
          <span className="eyebrow">
            {incident.incidentId} · {timeAgo(incident.openedAt, now)}
          </span>
          <h2 className="verdict-card__title">{incident.suburb}</h2>
        </div>
        <CausePill incident={incident} />
      </header>

      <div className="verdict-card__confidence">
        <ConfidenceDonut value={incident.confidence} color={color} size={64} />
        <div>
          <h3 className="verdict-card__level">{review ? 'Needs a person' : 'High confidence'}</h3>
          <p className="muted small">
            {review
              ? 'Below the 60% threshold, so the engine asks an operator to decide.'
              : 'Above the 60% threshold, so the engine recommends an action on its own.'}
          </p>
        </div>
      </div>

      {incident.summary && (
        <section className="verdict-card__summary">
          <h3 className="eyebrow eyebrow--caps">Summary</h3>
          <p className="small">{incident.summary}</p>
          {incident.notice && (
            <>
              <h3 className="eyebrow eyebrow--caps verdict-card__notice">Draft customer notice</h3>
              <p className="small muted">{incident.notice}</p>
            </>
          )}
        </section>
      )}

      <ProbabilityBars incident={incident} />

      <div className="button-row">
        <button type="button" className="button button--primary" onClick={onAct} disabled={done}>
          {done ? ACTION_TEXT[incident.action].done : ACTION_TEXT[incident.action].button}
        </button>
        <button type="button" className="button button--ghost" onClick={onDetails}>
          Details
        </button>
      </div>
    </article>
  );
}
