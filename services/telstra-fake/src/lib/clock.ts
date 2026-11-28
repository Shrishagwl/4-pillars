/**
 * The fake's idea of "now". The twin replays scenarios that start at a fixed date
 * (2026-11-25 00:00 UTC), so it can move this clock to match; otherwise it is the real time.
 * Stored as an offset so time keeps moving after it is set.
 */
export class Clock {
  private offsetMs = 0;

  now(): Date {
    return new Date(Date.now() + this.offsetMs);
  }

  set(when: Date): void {
    this.offsetMs = when.getTime() - Date.now();
  }

  reset(): void {
    this.offsetMs = 0;
  }
}
