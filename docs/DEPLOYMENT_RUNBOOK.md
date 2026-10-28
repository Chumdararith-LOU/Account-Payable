# APMatch — Deployment Runbook

Step-by-step operations guide for the production host
(`rith@100.88.94.91`). For architectural context, see
`docs/DEPLOYMENT.md`. For development setup, see `docs/DEV_WORKFLOW.md`.

## Server details

- Host: `rith@100.88.94.91` (Tailscale) / `rith@172.17.0.134` (LAN)
- CPU: Intel i9-9900 (8 cores)
- GPU: NVIDIA RTX 2080 Ti (11 GB VRAM) — production default (see GPU mode)
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

All compose commands below run from `/opt/apmatch` on the server. **GPU is
the production default** (the `dc` alias includes the GPU overlay); `dcc`
is the CPU fallback:

```bash
cd /opt/apmatch
alias dc='docker compose -f docker-compose.yml -f docker-compose.server.yml -f docker-compose.server.gpu.yml --env-file .env.server'
alias dcc='docker compose -f docker-compose.yml -f docker-compose.server.yml --env-file .env.server'
```

### Deploy the latest code (GPU, default)

`deploy_remote.sh` syncs the code and builds/deploys the **CPU** image.
To deploy the **GPU** image (the production default), sync, build the GPU
image, then switch:

```bash
cd ~/Documents/Turing/dpai          # on the Mac (or any checkout of the repo)
./scripts/deploy_remote.sh rith@100.88.94.91   # rsync + build CPU + deploy CPU
ssh rith@100.88.94.91 'cd /opt/apmatch && \
  docker build -f Dockerfile.gpu -t apmatch:dev-gpu . && \
  docker compose -f docker-compose.yml -f docker-compose.server.yml \
    -f docker-compose.server.gpu.yml --env-file .env.server up -d'
```

The first GPU build is ~30–60 min; later builds reuse cached layers.

**Database migrations run automatically at container startup** (the image
entrypoint runs `alembic upgrade head` before uvicorn), so a fresh Postgres
volume gets its schema on first start. No manual migration step is needed.

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

## GPU mode (default) + CPU fallback

The production image is `apmatch:dev-gpu` (built from `Dockerfile.gpu`),
running on the RTX 2080 Ti via the `docker-compose.server.gpu.yml` overlay.
Device selection is a runtime env choice (`APMATCH_DEVICE=cuda`, set by the
overlay); the same code runs on CPU when the var is unset. See D-095/D-096.

- **GPU (default):** `dc up -d` (the `dc` alias includes the GPU overlay).
- **CPU fallback** (if the GPU is unavailable): `dcc up -d`.
- **Verify the GPU is in use:** `ssh rith@100.88.94.91 'nvidia-smi'` —
  expect a `python3.12` process using ~2 GB of VRAM.

Ollama (:11434) shares the GPU. If Ollama has loaded its 7.4 GB model, the
GPU pipeline will OOM. Check `nvidia-smi` before a GPU deploy; stop Ollama
(`sudo systemctl stop ollama`) or configure it CPU-only if needed.

## Vivobook decommission (done 2026-10-28 / 2026-10-29)

The old deployment on the Vivobook (`rith@100.127.105.9`) was torn down
after the migration to the GPU server (EMB-13a). Completed:

- Containers `apmatch-api` / `apmatch-postgres` and the compose network
  removed (`docker compose down`).
- The Postgres volume `apmatch-demo_apmatch_pgdata` removed (`down -v`).
- The `apmatch:dev` image removed (`docker image rm`).
- `/opt/apmatch-dev` (the dev mirror) was left intact — the dev wrappers
  still use it as a fallback.

One step needs the Vivobook's sudo password (the `/opt` dir is root-owned):

```bash
ssh rith@100.127.105.9 'sudo rm -rf /opt/apmatch'
```
