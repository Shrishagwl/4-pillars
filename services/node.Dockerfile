# Shared image for every TypeScript service. Build from the repo root:
#   docker build -f services/node.Dockerfile --build-arg SERVICE_DIR=services/ingest-api .
FROM node:22-alpine AS base
WORKDIR /repo
COPY . .

FROM base AS build
ARG SERVICE_DIR
RUN npm ci --workspace ${SERVICE_DIR} --include-workspace-root --ignore-scripts \
 && npm run build -w @4p/contracts \
 && npm run build -w ${SERVICE_DIR}

FROM base AS deps
ARG SERVICE_DIR
RUN npm ci --workspace ${SERVICE_DIR} --omit=dev --ignore-scripts

FROM node:22-alpine
ARG SERVICE_DIR
ARG APP_VERSION=dev
ENV NODE_ENV=production APP_VERSION=${APP_VERSION}
WORKDIR /repo
COPY --from=deps /repo/node_modules ./node_modules
COPY --from=build /repo/packages/contracts/package.json ./packages/contracts/package.json
COPY --from=build /repo/packages/contracts/dist ./packages/contracts/dist
COPY --from=build /repo/${SERVICE_DIR}/package.json ./${SERVICE_DIR}/package.json
COPY --from=build /repo/${SERVICE_DIR}/dist ./${SERVICE_DIR}/dist
WORKDIR /repo/${SERVICE_DIR}
USER node
CMD ["node", "dist/server.js"]
