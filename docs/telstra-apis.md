# Telstra APIs we use

Our own summary of the public docs on [dev.telstra.com](https://dev.telstra.com), read on 9 Nov 2026. Check the docs again before relying on a detail; they change, and two of these APIs are in closed beta.

We haven't received hackathon credentials yet, so everything runs against **telstra-fake** for now. When credentials arrive, only `telstra-gateway` (and the LoC subscription setup) needs to change.

## Auth (all three APIs)

OAuth2 client credentials. POST to the token endpoint with our client ID and secret and the scopes we need, then send `Authorization: Bearer <token>`.

- Token URL: `https://prod.okapi.ogw.evolve.okapi.telstra.com/og-network-auth-prod/api/realms/network-auth/protocol/openid-connect/token`
- Scopes: `iot-naap-network-availability:read`, `iot-naap-loss-of-connectivity:read`, `iot-naap-loss-of-connectivity:write`

Headers on every call:

| Header | Value |
|---|---|
| `Authorization` | `Bearer <token>` |
| `Accept` | `application/json` |
| `Accept-Charset` | `utf-8` |
| `Content-Language` | `en-AU` |
| `Content-Type` | `application/json` |
| `correlation-id` | a new UUIDv4 per request (log it, it's how Telstra traces a call) |

## Loss of Connectivity (v0.1.0, closed beta)

Tells us when a SIM drops off the network.

- Subscribe SIMs and give a callback URL: `POST .../mobility/products-api/loss-of-connectivity/v1/subscriptions`
- List / get / delete: `GET .../subscriptions`, `GET` or `DELETE .../subscriptions/{id}`
- Telstra then POSTs to our callback (ingest-api `POST /loss-of-connectivity/v0/events`), and we reply **202**:

```json
{
  "subscriptionId": "…",
  "monitoringEventReports": [
    { "monitoringType": "LOSS_OF_CONNECTIVITY", "msisdn": "61412345678", "lossOfConnectReason": 7, "eventTime": "2026-11-20T03:15:00Z" }
  ]
}
```

How we group the reason codes:

| Codes | Group | What it suggests |
|---|---|---|
| 0, 1, 6 | detached / deregistered | the device left the network (for example it lost power) |
| 2, 3, 7 | maximum detection time expired | the device just went quiet |
| 4, 5, 8 | purged | the network dropped the device's record |

## Network Availability (v1.1.0)

Is there a Telstra network outage near a place?

- `GET .../mobility/products-api/network-availability/v1/status?suburb=Carlton&state=VIC&postcode=3053`
- Returns outages grouped as `past`, `current`, `near_future` and `far_future`.
- Some current outages include `affected_area`, a WKT `MULTIPOLYGON` of the outage area. We use it to check which silent meters sit inside the outage.
- Timestamps are **not ISO 8601**: `2026-05-13 00:03:00 Australia/Melbourne`. telstra-gateway converts them to UTC.
- States: QLD, NSW, ACT, VIC, TAS, SA, WA, NT.
- The docs spell the path two ways (one has an "availiblity" typo). Try the correct spelling first.
- Access needs a Telstra account rep, so we expect it through the hackathon.

## Location Verification (beta, CAMARA 3.0.0)

Is this SIM inside this circle? We use it to catch tampered or moved meters.

- `POST /location-verification/verify`

```json
{
  "device": { "phoneNumber": "+61412345678" },
  "area": { "areaType": "CIRCLE", "center": { "latitude": -37.80, "longitude": 144.96 }, "radius": 1000 },
  "maxAge": 120
}
```

- Answer: `verificationResult` of `TRUE`, `FALSE`, `PARTIAL` (with `matchRate` 1–99) or `UNKNOWN`, plus `lastLocationTime`.
- In the sandbox the minimum radius is 1,000 m, and test phone numbers return fixed answers.

## Still to confirm with Telstra

- When we get sandbox credentials, and for which APIs
- Exact LoC subscription request fields (copy them from the public page into `packages/contracts` before building telstra-fake, #7)
- The eSIM / activation guide for the first real LoC event (#17)
