# dashboard (React, TypeScript, Vite) · port 5173

The screen an operator watches: every incident on a map, the likely cause with a confidence
score, the evidence behind it, and the money saved. Design: Figma file "4 Pillars Dashboard",
page "Final design" (01 Overview, 02 Incident detail). Branding: Telstra palette and Telstra
Display font.

    npm install
    npm run dev -w @4p/dashboard      # http://localhost:5173
    npm run build -w @4p/dashboard

## Where things are

| File | What it does |
|---|---|
| `src/App.tsx` | Holds the shared state (screen, selected incident, search) and picks the screen |
| `src/pages/OverviewPage.tsx` | Screen 01: numbers, map, verdict card, other incidents |
| `src/pages/IncidentPage.tsx` | Screen 02: incident queue, likely cause, action, evidence |
| `src/components/MeterMap.tsx` | Leaflet map of all meters, with a circle per incident |
| `src/components/*` | Smaller pieces: nav, KPI row, verdict card, bars, donut, evidence |
| `src/data/mockData.ts` | Mock meters and incidents, laid out like the twin (same box, suburbs, seed) |
| `src/utils/costs.ts` | The engine's cost model, used for "expected cost" and "saved" |
| `src/utils/causes.ts` | Labels and colours per cause and action |
| `src/index.css` | Design tokens: Telstra colours, font, radii |
| `src/app.css` | Layout and component styles |

Types (`Verdict`, `Cause`, `Action`) come from `@4p/contracts`, so the dashboard and the
engine always agree on the shape of a verdict.

## Switching to live data

Everything reads from `data` at the top of `App.tsx`. When ingest-api serves
`GET /incidents` and live updates, replace `createMockData()` with a fetch from
`VITE_INGEST_URL`. Each incident needs the `Verdict` fields plus `suburb`, `postcode`,
`transformerIds`, `meterIds` and `openedAt` (see `Incident` in `src/types.ts`).

## Not done yet

- Inject fault and Replay buttons (task 7, scenario controls)
- Scenarios and Evaluation tabs
- Real costs (task 3): change `src/utils/costs.ts` and the engine together
