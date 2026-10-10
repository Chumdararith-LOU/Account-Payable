# DEPLOYMENT.md — remote deployment parameters (EMB-00)

Locked in 2026-10-10 from a live recon of the target server. Future tasks
and the demo runbook rely on these values; change them only via a new
decision in DECISIONS.md.

## Target server

- SSH: `rith@100.76.126.16`
- Tailscale: yes (100.76.126.16 is in CGNAT range 100.64.0.0/10)
- OS: Ubuntu 24.04.4 LTS, x86_64
- Docker: 29.5.2, Compose v5.1.4
- No GPU (CPU-only inference)
- RAM: 7.6 GB total, ~4.8 GB available
- Disk: 293 GB free on /

## Resource budget

- Embedding model (MiniLM-L12-v2): ~500 MB resident
- OCR stack (PP-OCRv6 + PP-StructureV3): ~2.6 GB resident
- API + Python runtime: ~400 MB
- Postgres: ~200 MB
- Total expected: ~3.7 GB
- Expected headroom after deploy: ~1 GB
- If headroom falls below 500 MB, revisit model or sub-model choices

## Port allocation

- Postgres: 5434 (5433 is IN USE on the server — do not use)
- API: 8000
- Only the API is exposed to the host; Postgres is internal to the
  compose network (no `-p` flag on the postgres service in the server
  compose file — see EMB-01)

## Coexistence rules

- The server is a shared production home lab. Existing services:
  Jenkins, Jellyfin, MongoDB, MariaDB, MinIO (×2), CasaOS, and one
  custom Java app. NEVER restart, stop, or modify any of them.
- Never `systemctl restart docker`.
- Never run `docker compose down` in any directory other than ours.
- Compose project name is `apmatch-demo` (set explicitly) so we
  never collide with another project.
- All our operations target `docker compose -p apmatch-demo`.

## Demo venue

- The server is Tailscale-only. The demo machine (Mac) must be on
  the same Tailscale account (`louchumdararith02@`).
- Test connectivity from Mac: `curl http://100.76.126.16:8000/healthz`
- Fallback: run the demo from the server's own console via SSH.
