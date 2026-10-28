# APMatch — Deployment Runbook

Step-by-step operations guide for the production host
(`rith@100.88.94.91`). For architectural context, see
`docs/DEPLOYMENT.md`. For development setup, see `docs/DEV_WORKFLOW.md`.

## Server details

- Host: `rith@100.88.94.91` (Tailscale) / `rith@172.17.0.134` (LAN)
- CPU: Intel i9-9900 (8 cores)
- GPU: NVIDIA RTX 2080 Ti (11 GB VRAM) — NOT YET USED (see note below)
- RAM: 31 GiB
- OS: Ubuntu 22.04.5 LTS, kernel 6.8
- Docker: 29.6.2, Compose v5.3.1

The LAN IP is faster but can time out (Wi-Fi); the Tailscale IP is the
reliable fallback for SSH.

### Coexistence warning

This server hosts unrelated services (Ollama :11434, VNC :902,
:7070, CUPS :631). DO NOT:

- `systemctl restart docker` — will restart all containers
- `docker compose down` in any directory other than `/opt/apmatch`
- Bind to ports already in use (check with `ss -tuln`)

## Routine operations

All compose commands below run from `/opt/apmatch` on the server with the
server override files:

```bash
cd /opt/apmatch
alias dc='docker compose -f docker-compose.yml -f docker-compose.server.yml --env-file .env.server'
```

### Deploy the latest code

```bash
cd ~/Documents/Turing/dpai          # on the Mac (or any checkout of the repo)
./scripts/deploy_remote.sh rith@100.88.94.91
```

What it does, in order:

1. `rsync` the tree to `/opt/apmatch` (incremental; includes `models/`).
2. `docker compose up -d --build` on the server.
3. Wait up to 180 s for `/healthz` inside the container.

It is idempotent — safe to re-run. **Database migrations run
automatically at container startup** (the image entrypoint runs
`alembic upgrade head` before uvicorn), so a fresh Postgres volume gets
its schema on first start. No manual migration step is needed.

Expected tail of the output:

```
DEPLOY OK
Deploy complete.
```

### Verify a deploy

```bash
dc ps                                   # both services "healthy"
dc logs api --tail=10                   # must show:
#   [entrypoint] Applying database migrations...
#   [entrypoint] Starting application: uvicorn ...
curl -s http://100.88.94.91:8001/healthz
```

The API is published on port **8001** on the server (8000 inside the
container).

### View logs

```bash
dc logs -f api                          # follow the API
dc logs --tail=100 postgres             # Postgres
```

### Database backup

```bash
dc exec -T postgres pg_dump -U apmatch apmatch > backup_$(date +%F).sql
```

### Database restore

Stop the API first, then:

```bash
dc stop api
dc exec -T postgres psql -U apmatch -d apmatch -f - < backup_YYYY-MM-DD.sql
dc start api
```

(For a full volume-level restore, stop both services and restore the
`apmatch-demo_apmatch_pgdata` volume from a `docker run --volumes-from`
copy — see `docs/DEPLOYMENT.md` for the volume layout.)

### Apply migrations manually (rare)

Only needed if you want to migrate without restarting the API:

```bash
dc exec -T api alembic upgrade head
dc exec -T api alembic current
```

### Roll back to a previous commit

```bash
git checkout <old-commit>              # on the Mac
./scripts/deploy_remote.sh rith@100.88.94.91
```

Migrations are forward-only; rolling back code does not roll back the
schema. Only roll back to a commit whose code works with the current
schema (in practice: any recent commit — schema changes are additive).

## Emergency procedures

### API container won't start

```bash
dc logs api --tail=50
```

Common causes:

- `APMATCH_API_KEY is required` — `.env.server` missing or key unset.
- Embedding hash mismatch — `models/embeddings/` on the server is
  corrupt; re-run the model download on the server and redeploy.
- Port 8001 in use — another service grabbed it; check `ss -tuln`.

Then: `dc up -d --build api`

### Postgres won't start

```bash
dc logs postgres --tail=50
dc up -d postgres                      # the volume is preserved; data is safe
```

### Disk full

```bash
docker system df
docker image prune -a                   # removes dangling/unused images
```

The `apmatch:dev` image is ~2 GB; the Postgres volume grows with audit
rows. Check `df -h /` and the docker data-root usage.

## GPU note

The RTX 2080 Ti is installed and the Docker NVIDIA runtime is configured
(`daemon.json`), but the production image is **CPU-only** by design.
GPU acceleration is tracked as PROD-A1 and will change the image, not
the runbook.

## Vivobook decommission (2026-10-28)

The old deployment on the Vivobook (`rith@100.127.105.9`) was
decommissioned when the GPU server became the production target
(EMB-13a). What was done:

- `docker compose down` in `/opt/apmatch` on the Vivobook — containers
  `apmatch-api` and `apmatch-postgres` and the compose network were
  removed.
- The Postgres volume `apmatch-demo_apmatch_pgdata` was **kept** — the
  old audit history is still recoverable.
- The source tree in `/opt/apmatch` was left in place.

To restore the old deployment (should it ever be needed):

```bash
ssh rith@100.127.105.9
cd /opt/apmatch
docker compose -f docker-compose.yml -f docker-compose.server.yml \
  --env-file .env.server up -d
```

The kept volume is remounted automatically; the entrypoint migrates the
schema forward. Do not delete the volume until the old audit data has
been exported or is confirmed unneeded.
