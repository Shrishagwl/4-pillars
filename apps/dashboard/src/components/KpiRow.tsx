import type { Incident, Meter } from '../types.ts';
import { dispatchesAvoided, savedDollars } from '../utils/costs.ts';
import { count, dollars, duration, percent } from '../utils/format.ts';

interface Props {
  meters: Meter[];
  incidents: Incident[];
  now: number;
}

/** The four numbers across the top of the Overview (and task 8's dollars-saved counter). */
export function KpiRow({ meters, incidents, now }: Props) {
  const lastHour = incidents.filter((i) => now - new Date(i.openedAt).getTime() < 3_600_000);
  const silent = incidents.reduce((sum, i) => sum + i.meterCount, 0);
  const verdictTimes = incidents.map(
    (i) => new Date(i.updatedAt).getTime() - new Date(i.openedAt).getTime(),
  );
  const avgVerdict = verdictTimes.reduce((a, b) => a + b, 0) / Math.max(verdictTimes.length, 1);
  const saved = incidents.reduce((sum, i) => sum + savedDollars(i), 0);
  const avoided = incidents.reduce((sum, i) => sum + dispatchesAvoided(i), 0);

  return (
    <section className="kpi-row" aria-label="Key numbers">
      <Kpi
        label="Open incidents"
        value={String(incidents.length)}
        note={`+${lastHour.length} in the last hour`}
        tone="warn"
      />
      <Kpi
        label="Meters silent"
        value={count(silent)}
        note={`${percent(silent / Math.max(meters.length, 1))} of fleet`}
      />
      <Kpi
        label="Time to verdict"
        value={duration(avgVerdict)}
        note="Target under 5 min"
        tone={avgVerdict < 300_000 ? 'good' : 'warn'}
      />
      <Kpi
        label="Saved today"
        value={dollars(saved)}
        note={`${count(avoided)} truck visits avoided vs. one per silent meter`}
        highlight
      />
    </section>
  );
}

interface KpiProps {
  label: string;
  value: string;
  note: string;
  tone?: 'good' | 'warn';
  highlight?: boolean;
}

function Kpi({ label, value, note, tone, highlight }: KpiProps) {
  return (
    <div className={`kpi${highlight ? ' kpi--highlight' : ''}`}>
      <span className="kpi__label">{label}</span>
      <span className="kpi__value">{value}</span>
      <span className={`kpi__note${tone ? ` kpi__note--${tone}` : ''}`}>{note}</span>
    </div>
  );
}
