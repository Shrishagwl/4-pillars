import type { Incident } from '../types.ts';
import { CAUSE_STYLE, needsReview, REVIEW_STYLE } from '../utils/causes.ts';

/** The small coloured label, e.g. "Power outage" or "Needs review". */
export function CausePill({ incident }: { incident: Incident }) {
  const style = needsReview(incident) ? REVIEW_STYLE : CAUSE_STYLE[incident.cause];
  return (
    <span className="pill" style={{ background: style.tint }}>
      <span className="pill__dot" style={{ background: style.color }} />
      {style.label}
    </span>
  );
}

/** The colour that represents an incident on the map and in lists. */
export function incidentColor(incident: Incident): string {
  return CAUSE_STYLE[incident.cause].color;
}
