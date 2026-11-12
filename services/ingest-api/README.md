# ingest-api (TypeScript, Fastify) · port 8081

Front door for meter events. Telstra (or telstra-fake) calls our Loss of Connectivity callback here.

| Endpoint | Status |
|---|---|
| `GET /health` | done |
| `POST /loss-of-connectivity/v0/events` | validates and replies 202; storing (#14) and Pub/Sub (#22) still to do |
| incidents + live updates (SSE) | #29 |

    npm run dev -w @4p/ingest-api      # LOG_PRETTY=true for readable logs
    npm test -w @4p/ingest-api
