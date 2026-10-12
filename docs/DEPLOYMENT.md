# DEPLOYMENT.md — remote deployment parameters (EMB-00)

Locked in 2026-10-10 from a live recon of the target server. Future tasks
and the demo runbook rely on these values; change them only via a new
decision in DECISIONS.md.

Target changed 2026-10-11 from `rith@100.76.126.16` to
`rith@100.127.105.9` (see D-071): the first server's CPU (i5-3570,
no AVX2) cannot run PaddlePaddle 3.3.1 (SIGILL in libphi_core.so).

## Target server

- SSH: `rith@100.127.105.9` (hostname `rith-Vivobook`)
- Tailscale: yes (100.127.105.9 is in CGNAT range 100.64.0.0/10)
- OS: Ubuntu 22.04.5 LTS, x86_64
- CPU: Intel Core i3-1220P (12th gen) — AVX2 + FMA (required by
  PaddlePaddle 3.3.1; see D-071)
- Docker: 29.4.0, Compose v5.1.1
- No GPU (CPU-only inference)
- RAM: 15 GB total, ~5.4 GB available (9 GB used by other services);
  swap 2 GB, ~1.9 GB already in use
- Disk: 61 GB free on /

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
- Expected headroom after deploy: ~1.7 GB
- If headroom falls below 500 MB, revisit model or sub-model choices
- Watch swap: it was ~95% full before our deploy; if it grows further
  under load, the existing services are under memory pressure

## Port allocation

- API: 8001 (8000 is IN USE on this server by an existing python3
  service — do not use; 8080 is also in use)
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

- The server is a shared production home lab. Existing services:
  searxng (docker, 127.0.0.1:8888), a python3 app on :8000, and other
  workloads using ~9 GB RAM. NEVER restart, stop, or modify any of them.
- Never `systemctl restart docker`.
- Never run `docker compose down` in any directory other than ours.
- Compose project name is `apmatch-demo` (set explicitly) so we
  never collide with another project.
- All our operations target `docker compose -p apmatch-demo`.

## Demo venue

- The server is Tailscale-only. The demo machine (Mac) must be on
  the same Tailscale account (`louchumdararith02@`).
- Test connectivity from Mac: `curl http://100.127.105.9:8001/healthz`
- Fallback: run the demo from the server's own console via SSH.

## Deploy workflow

All commands run from the Mac.

1. Provision once: `./scripts/provision_remote.sh rith@100.127.105.9`
2. Create `.env.server` on the remote (from `.env.server.example`)
3. Deploy: `./scripts/deploy_remote.sh rith@100.127.105.9`
4. Verify offline: `./scripts/verify_offline_remote.sh rith@100.127.105.9`
5. Tear down (only if needed):
   `ssh rith@100.127.105.9 "cd /opt/apmatch && docker compose -p apmatch-demo down"`

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
