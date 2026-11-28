# telstra-fake (TypeScript, Fastify) · port 8083

Our stand-in for the three Telstra APIs, built from the public docs on dev.telstra.com (and CAMARA
for Location Verification), so we can build and demo without credentials. Same paths, fields,
status codes and error bodies as the real APIs. The digital twin decides what it answers.
See [docs/telstra-apis.md](../../docs/telstra-apis.md); the shapes are in `packages/contracts`.

## Telstra's API (what telstra-gateway calls)

| Route | API |
|---|---|
| `POST /og-network-auth-prod/api/realms/network-auth/protocol/openid-connect/token` | OAuth2 client credentials (any id/secret works) |
| `POST/GET /loss-of-connectivity/v0/subscriptions`, `GET/DELETE .../{subscriptionId}` | Loss of Connectivity 0.1.0 (`/v1/` works too, the Getting Started page uses it) |
| `GET /network-availability/v1/status?suburb=&state=&postcode=` | Network Availability 1.1.0 |
| `POST /location-verification/verify` (Telstra sandbox) or `/location-verification/v3/verify` | Location Verification, CAMARA 3.0.0 |

Every Telstra route needs `Authorization: Bearer <token>`; LoC and Network Availability also need
a UUID v4 `correlation-id`, like the real ones.

## Fake-only routes (the twin drives these)

| Route | What it does |
|---|---|
| `POST /fake/loss-of-connectivity/events` | `{msisdn, lossOfConnectReason, eventTime}` or `{events: [...]}`: sends the LoC callback to whoever subscribed |
| `POST /fake/network-availability/outages` | add an outage (`state, suburb, postcode, start, end?, affected_area?, ...`) |
| `POST /fake/network-availability/outages/{id}/end`, `DELETE /fake/network-availability/outages` | end one, clear all |
| `POST /fake/location-verification/devices` | `{phoneNumber, latitude, longitude, accuracy?, locatedAt?, locatable?}` or `{devices: [...]}`: where each SIM really is |
| `PUT /fake/clock` `{now}` / `DELETE /fake/clock` | line the fake's clock up with a scenario's time |

On Cloud Run the fake adds a Google ID token when it calls a `*.run.app` callback, because our
services are private.

```bash
npm run dev -w @4p/telstra-fake
npm test -w @4p/telstra-fake
```
