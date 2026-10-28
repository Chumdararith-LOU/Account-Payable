# DEPLOYMENT.md — remote deployment parameters (EMB-00)

Locked in 2026-10-10 from a live recon of the target server. Future tasks
and the demo runbook rely on these values; change them only via a new
decision in DECISIONS.md.

Target changed 2026-10-11 from `rith@100.76.126.16` to
`rith@100.127.105.9` (see D-071): the first server's CPU (i5-3570,
no AVX2) cannot run PaddlePaddle 3.3.1 (SIGILL in libphi_core.so).
Target changed 2026-10-27 from `rith@100.127.105.9` to
`rith@100.88.94.91` (see D-090): the Vivobook was a temporary target;
the new server has 2× the RAM, 8 cores, and a GPU.

For step-by-step operations (deploy, backup, restore, GPU mode,
troubleshooting), see `docs/DEPLOYMENT_RUNBOOK.md`.

## Target server

- SSH: `rith@100.88.94.91` (hostname `ubuntuvilalab-Z390-AORUS-ULTRA`)
- Tailscale: yes (100.88.94.91 is in CGNAT range 100.64.0.0/10)
- OS: Ubuntu 22.04.5 LTS, x86_64
- CPU: Intel Core i9-9900 (8 cores / 16 threads) — AVX2 + FMA
- GPU: NVIDIA RTX 2080 Ti (11 GB), driver 575.57.08 (CUDA 12.9).
  The image is CPU-only for now; GPU acceleration is deferred to
  PROD-A1. The nvidia runtime is registered in `/etc/docker/daemon.json`
  (added 2026-10-27 at the owner's request; Docker was restarted once).
- Docker: 29.6.2, Compose v5.3.1
- RAM: 31 GiB total, ~29 GiB available (2026-10-27); swap 2 GiB
- Disk: 6.2 GB free on / as of 2026-10-27 (99% full — the owner is
  freeing space; the deploy needs ~15 GB for image + models + Postgres)

## Paddle versions (measured divergence)

- Mac dev env: PaddlePaddle 3.3.1 (arm64)
- Server prod env: PaddlePaddle 3.2.2 (amd64; pinned per D-073)
- The two versions produce different OCR output on the same images
  (2.7% of text blocks differ; the pipeline-level decision is identical —
  see D-078/D-079). See docs/DETERMINISM_REPORT.md for the exact
  divergence.

## Resource budget

- Embedding model (MiniLM-L12-v2): ~500 MB resident
- OCR stack (PP-OCRv6 + PP-StructureV3): ~2.6 GB resident
- API + Python runtime: ~400 MB
- Postgres: ~200 MB
- Total expected: ~3.7 GB
- Expected headroom after deploy: ~25 GB (31 GiB RAM, 2026-10-27)
- If headroom falls below 500 MB, revisit model or sub-model choices

## Port allocation

- API: 8001 (kept from the server compose file; 8000 is free on this
  server as of 2026-10-27 but the compose mapping is unchanged)
- Postgres: no host port. Internal to the compose network only.
- Only the API is exposed to the host; Postgres is internal to the
  compose network (no `-p` flag on the postgres service in the server
  compose file — see EMB-01)
- No host-exposed Postgres port by default. The API reaches Postgres
  via the compose-internal hostname `postgres:5432`. The server never
  needs a host-exposed Postgres port. Port 5434 is free on this server
  and reserved in case the user wants an external psql connection for
  debugging; it is not required by the API container.

## Coexistence rules

- The server is a shared desktop/home lab. Existing services:
  Ollama (127.0.0.1:11434, holds a 7.4 GB model), VNC (:902), :7070,
  CUPS (:631). NEVER restart, stop, or modify any of them.
- The GPU drives the desktop display (Xorg). Ollama may load its model
  onto the GPU — check `nvidia-smi` before GPU workloads (PROD-A1).
- Never run `docker compose down` in any directory other than ours.
- Compose project name is `apmatch-demo` (set explicitly) so we
  never collide with another project.
- All our operations target `docker compose -p apmatch-demo`.

## GPU mode (default on the current server)

The server hosts an RTX 2080 Ti. The GPU image (`apmatch:dev-gpu`,
built from `Dockerfile.gpu`) runs the same pipeline on the GPU; the
CPU image (`apmatch:dev`) remains the fallback.

Build the GPU image (first time ~30-60 min; layers cache after):

```bash
cd /opt/apmatch
docker build -f Dockerfile.gpu -t apmatch:dev-gpu .
```

To use the GPU:

```bash
docker compose -f docker-compose.yml \
               -f docker-compose.server.yml \
               -f docker-compose.server.gpu.yml \
               --env-file .env.server up -d
```

To fall back to CPU (if the GPU is unavailable):

```bash
docker compose -f docker-compose.yml \
               -f docker-compose.server.yml \
               --env-file .env.server up -d
```

To verify the GPU is in use:

```bash
ssh rith@100.88.94.91 'nvidia-smi'
```

Device selection is runtime, not build-time: the four engine classes
read `APMATCH_DEVICE` (default `cpu`; the GPU overlay sets `cuda`) via
`apmatch/runtime.py`. See D-095/D-096.

Ollama (:11434) shares the GPU. If Ollama has loaded its 7.4 GB model,
the GPU pipeline will OOM. Either stop Ollama
(`sudo systemctl stop ollama`) or configure it CPU-only. Check with
`nvidia-smi` before a GPU deploy.

## Demo venue

- The server is Tailscale-only. The demo machine (Mac) must be on
  the same Tailscale account (`louchumdararith02@`).
- Test connectivity from Mac: `curl http://100.88.94.91:8001/healthz`
- Fallback: run the demo from the server's own console via SSH.

## Deploy workflow

All commands run from the Mac.

1. Provision once: `./scripts/provision_remote.sh rith@100.88.94.91`
2. Create `.env.server` on the remote (from `.env.server.example`)
3. Deploy: `./scripts/deploy_remote.sh rith@100.88.94.91`
4. Verify offline: `./scripts/verify_offline_remote.sh rith@100.88.94.91`
5. Tear down (only if needed):
   `ssh rith@100.88.94.91 "cd /opt/apmatch && docker compose -p apmatch-demo down"`

## First successful deployment

- Date: 2026-10-11
- Server: `rith@100.127.105.9` (rith-Vivobook, i3-1220P)
- Image: `apmatch:dev`, 6.72 GB
- Paddle: 3.2.2 (oneDNN enabled) — see D-073
- API memory after warm (post-`/match`): ~4.5 GB; host available ~8 GB
- Verified: healthz OK, offline verify `OFFLINE_OK (47 text blocks)`,
  `/match` returns a full result (route HUMAN_REVIEW on the fixture set).
- Note: the first build on this box took a long time (slow link + the
  laptop sleeping once). Subsequent builds reuse cached layers.
