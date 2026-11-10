# DocuFlow AP frontend, served by nginx next to the API (UI-2, D-118).
#
# Built by `docker compose ... up -d --build` through docker-compose.server.yml.
# The browser talks to one origin: nginx serves the app and forwards /api/* to
# the api container, so no API URL or key is compiled into the page.

FROM oven/bun:1 AS build
WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
ENV VITE_API_URL=/api
# --bun: run vite/tsc on the bun runtime (this image has no node).
RUN bun --bun run build

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
