# Local/offline demo image. In the cloud the dashboard is hosted on Firebase Hosting (#44).
# Build from the repo root:  docker build -f apps/dashboard/Dockerfile .
FROM node:22-alpine AS build
WORKDIR /repo
COPY . .
ARG VITE_INGEST_URL=http://localhost:8081
ENV VITE_INGEST_URL=${VITE_INGEST_URL}
RUN npm ci --workspace apps/dashboard --include-workspace-root --ignore-scripts \
 && npm run build -w @4p/dashboard

FROM nginx:1.29-alpine
COPY --from=build /repo/apps/dashboard/dist /usr/share/nginx/html
EXPOSE 80
