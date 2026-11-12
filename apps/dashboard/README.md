# dashboard (React, TypeScript, Vite)

What an operator sees: map of meters and incidents, verdict card with evidence, scenario
controls, dollars saved. Hosted on Firebase Hosting in the cloud; Docker image for the offline demo.

    npm run dev -w @4p/dashboard        # http://localhost:5173
    VITE_INGEST_URL=http://localhost:8081 sets where live data comes from
