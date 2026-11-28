# telstra-gateway (TypeScript, Fastify) · port 8082

The only service that talks to Telstra. Everything else (mainly the engine) calls this instead.
Points at telstra-fake by default; the real sandbox is a config change (#36).

What it does on every Telstra call:

- gets an OAuth2 client-credentials token and reuses it until a minute before it expires
  (a 401 gets a fresh token once)
- sends the headers Telstra requires: `Authorization`, `Accept`, `Accept-Charset`,
  `Content-Language: en-AU`, `Content-Type` and a new UUID v4 `correlation-id`
- retries 429, 5xx and network failures up to 3 times with backoff (200 ms, 400 ms, ...,
  or what `Retry-After` says), then answers 502 `TELSTRA_UNAVAILABLE`
- logs one line per call: API, path, status, attempts, time, correlation id and the incident id
  the caller sent in `x-incident-id` (never the query string, token or secrets)

## Routes for our services

| Route | Telstra API |
|---|---|
| `GET /v1/network-availability?suburb=&state=&postcode=` | Network Availability. Melbourne timestamps also come back as UTC `start`/`end`; each suburb is cached for 60 s |
| `POST /v1/location-verification` `{msisdn, latitude, longitude, radius?, maxAge?}` | Location Verification. `verificationResult` TRUE/FALSE/PARTIAL, or `null` with the error code when the network can't locate the SIM |
| `POST/GET /v1/loss-of-connectivity/subscriptions`, `DELETE .../{id}` | Loss of Connectivity subscriptions |

## Settings

| Env var | Default |
|---|---|
| `TELSTRA_BASE_URL` | `http://localhost:8083` (telstra-fake). Real: `https://prod.okapi.ogw.evolve.okapi.telstra.com/mobility/products-api` |
| `TELSTRA_LOCATION_BASE_URL` | same as the base. Real sandbox: `.../telstradev/v1/sandbox` |
| `TELSTRA_AUTH_URL` | Telstra's token path on the base URL's host |
| `TELSTRA_CLIENT_ID`, `TELSTRA_CLIENT_SECRET` | `local` (the fake takes anything). Real ones come from Secret Manager |
| `TELSTRA_LOC_VERSION` | `v0` (the OpenAPI file; the Getting Started page says `v1`) |
| `OUTAGE_CACHE_MS`, `TELSTRA_TIMEOUT_MS`, `TELSTRA_MAX_ATTEMPTS` | 60000, 5000, 3 |

The engine's side is `services/engine/src/engine/gateway.py`, which turns these answers into the
engine's signals (suburbs with an outage, SIMs inside an outage area, SIMs that moved).

```bash
npm run dev -w @4p/telstra-gateway
npm test -w @4p/telstra-gateway
```
