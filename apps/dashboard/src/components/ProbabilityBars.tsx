import type { Incident } from '../types.ts';
import { CAUSE_STYLE, CAUSES } from '../utils/causes.ts';
import { percent } from '../utils/format.ts';

/** One bar per cause showing how likely the engine thinks it is. */
export function ProbabilityBars({ incident }: { incident: Incident }) {
  return (
    <ul className="prob-bars">
      {CAUSES.map((cause) => {
        const p = incident.probabilities[cause] ?? 0;
        return (
          <li key={cause} className="prob-bars__row">
            <span className="prob-bars__label">{CAUSE_STYLE[cause].short}</span>
            <span className="prob-bars__track">
              <span
                className="prob-bars__fill"
                style={{
                  width: `${Math.max(p * 100, 1.5)}%`,
                  background: CAUSE_STYLE[cause].color,
                }}
              />
            </span>
            <span className="prob-bars__value">{percent(p)}</span>
          </li>
        );
      })}
    </ul>
  );
}
