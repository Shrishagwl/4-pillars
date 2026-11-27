import type { Incident } from '../types.ts';
import { CAUSE_STYLE, humanise } from '../utils/causes.ts';
import { splitEvidence } from '../utils/format.ts';

/**
 * "Why the engine thinks so" (task 6). The engine sends evidence as plain lines like
 * "Outage API: no outage listed for these meters". We split each line at the first colon
 * into a label and a detail, and colour the dot by what kind of fact it is.
 */
export function EvidenceTimeline({ incident }: { incident: Incident }) {
  return (
    <article className="card evidence">
      <span className="eyebrow eyebrow--caps">Why the engine thinks so</span>
      <ol className="evidence__list">
        {incident.evidence.map((line) => {
          const { label, detail } = splitEvidence(line);
          return (
            <li key={line} className="evidence__item">
              <span className="evidence__label">{label}</span>
              <span className="evidence__dot" style={{ background: dotColor(label, incident) }} />
              <span className="evidence__detail">{humanise(detail)}</span>
            </li>
          );
        })}
      </ol>
    </article>
  );
}

function dotColor(label: string, incident: Incident): string {
  if (label === 'Verdict' || label === 'Action') return 'var(--shamrock-60)';
  if (label === 'Outage API') return CAUSE_STYLE.NETWORK.color;
  if (label === 'Location Verification') return CAUSE_STYLE.TAMPER.color;
  if (label === 'Where') return CAUSE_STYLE[incident.cause].color;
  return 'var(--grey-30)';
}
