const INGEST_URL = import.meta.env.VITE_INGEST_URL ?? 'http://localhost:8081';

export default function App() {
  return (
    <main className="page">
      <header>
        <h1>Meter outage triage</h1>
        <p>
          When smart meters go silent, is it a power outage, a mobile network outage, a faulty meter
          or tampering? This dashboard shows each incident, the likely cause, and what to do next.
        </p>
      </header>
      <section className="placeholder">
        <p>
          Map, incident list and verdict cards go here (issues #4, #20, #30). Live data comes from
          ingest-api at <code>{INGEST_URL}</code>.
        </p>
      </section>
    </main>
  );
}
