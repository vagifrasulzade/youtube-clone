# syntax=docker/dockerfile:1
# nginx image = built SPA + reverse-proxy configuration. Build context: repo root.

FROM node:24-alpine AS spa
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM nginx:1.28-alpine
COPY infra/nginx/nginx.conf /etc/nginx/nginx.conf
COPY infra/nginx/snippets/ /etc/nginx/snippets/
COPY --from=spa /src/dist /usr/share/nginx/html
# No `nginx -t` here: upstream hosts (api, minio) only resolve on the compose network.
# nginx validates the config at startup, and the compose health check goes through to
# the API, so a broken config or proxy path makes the container unhealthy.
