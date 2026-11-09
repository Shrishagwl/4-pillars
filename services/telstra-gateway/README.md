# telstra-gateway (TypeScript, Fastify) · port 8082

The only service that talks to Telstra. Everything else (mainly the engine) calls this instead.
Points at telstra-fake by default (`TELSTRA_BASE_URL`), switches to the real sandbox later (#36).

To build (#25): required headers (Bearer token, `correlation-id` UUIDv4, `Content-Language: en-AU`, ...),
OAuth2 client-credentials token caching, retries, parsing `YYYY-MM-DD HH:MM:SS Australia/Melbourne`
timestamps to UTC, per-suburb cache for Network Availability, and a log line per Telstra call.
See [docs/telstra-apis.md](../../docs/telstra-apis.md).
