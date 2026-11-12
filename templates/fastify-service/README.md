# Fastify service template (TypeScript)

Starting point for every TypeScript service. Copy this folder, then change `SERVICE_NAME`
and `DEFAULT_PORT` in `src/config.ts` and the `name` in `package.json`.

What you get:
- Fastify 5 with TypeBox schemas: request validation and typed handlers from one schema
- `GET /health`
- JSON logs with Cloud Logging `severity` (set `LOG_PRETTY=true` locally for readable logs)
- Settings from env vars (`PORT`, `LOG_LEVEL`, `APP_VERSION`, ...)
- Graceful shutdown on SIGTERM (Cloud Run)
- Vitest using `app.inject()`, so tests need no open port

Build the image from the repo root:

    docker build -f services/node.Dockerfile --build-arg SERVICE_DIR=templates/fastify-service .
