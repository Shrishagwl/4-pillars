/** Small helpers that turn numbers and dates into the text the design shows. */

const dollarFormat = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  maximumFractionDigits: 0,
});

/** 18420 -> "$18,420" */
export function dollars(value: number): string {
  return dollarFormat.format(value);
}

/** 0.92 -> "92%" */
export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** 2000 -> "2,000" */
export function count(value: number): string {
  return value.toLocaleString('en-AU');
}

/** An ISO date -> "3 min ago" */
export function timeAgo(iso: string, now: number = Date.now()): string {
  const minutes = Math.floor((now - new Date(iso).getTime()) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  return `${hours} h ago`;
}

/** An ISO date -> "14:02" in the viewer's time zone */
export function clockTime(iso: string): string {
  return new Date(iso).toLocaleTimeString('en-AU', {
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  });
}

/** Milliseconds -> "2m 40s" */
export function duration(ms: number): string {
  const totalSeconds = Math.round(ms / 1000);
  const m = Math.floor(totalSeconds / 60);
  const s = totalSeconds % 60;
  return m > 0 ? `${m}m ${s}s` : `${s}s`;
}

/** "Meters: 214 silent (M-1, M-2...)" -> { label: "Meters", detail: "214 silent (...)" } */
export function splitEvidence(line: string): { label: string; detail: string } {
  const colon = line.indexOf(':');
  if (colon === -1) return { label: '', detail: line };
  return { label: line.slice(0, colon), detail: line.slice(colon + 1).trim() };
}
