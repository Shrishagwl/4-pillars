# telstra-fake (TypeScript, Fastify) · port 8083

Our stand-in for the three Telstra APIs, built from the public docs on dev.telstra.com, so we can
build and demo without credentials. Same paths and payloads as the real APIs; the digital twin
drives what it returns.

To build: Loss of Connectivity subscriptions + callbacks (#7), Network Availability status (#10),
Location Verification (#13). Request/response schemas are in `packages/contracts`.
See [docs/telstra-apis.md](../../docs/telstra-apis.md).
