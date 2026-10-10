# APMatch API — self-contained, offline-capable image.
#
# Multi-stage: the builder installs Python runtime deps into a venv; the
# runtime stage is a slim image with the venv + app code + models baked in.
# The bank's IT pulls this one artifact and runs it — nothing else.
#
# CPU-only. No CUDA, no paddlepaddle-gpu.

# ── Stage 1: builder ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

# System build deps (only needed at compile time)
RUN apt-get update && apt-get install -y --no-install-recommends \
      build-essential \
      libglib2.0-0 \
      libgl1 \
      libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY requirements.txt .
RUN python -m venv /opt/venv \
    && /opt/venv/bin/pip install --upgrade pip \
    && /opt/venv/bin/pip install --no-cache-dir -r requirements.txt

# torch + torchvision (CPU-only) are runtime deps of the Khmer engine
# (tror-yong-ocr) but are NOT declared in its sdist, so requirements.txt never
# pulls them. The standard PyPI torch/torchvision for Linux bundle CUDA; install
# the CPU-only builds from the PyTorch CPU index instead (no CUDA, per the
# CPU-only constraint). Versions match the host env (torch 2.5.1 / torchvision
# 0.20.1).
RUN /opt/venv/bin/pip install --no-cache-dir torch==2.5.1 torchvision==0.20.1 \
    --index-url https://download.pytorch.org/whl/cpu

# ── Stage 2: runtime ─────────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

# Runtime system libs (for cv2, paddle, and any native deps)
RUN apt-get update && apt-get install -y --no-install-recommends \
      libglib2.0-0 \
      libgl1 \
      libgomp1 \
      libsm6 \
      libxext6 \
      libxrender1 \
      curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd --system apmatch \
    && useradd --system --gid apmatch --home-dir /app apmatch

# Offline guarantees — set BEFORE the app ever imports OCR
ENV HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Copy the venv from the builder stage
COPY --from=builder /opt/venv /opt/venv

# Copy the application code (respects .dockerignore)
COPY apmatch/ ./apmatch/

# Ops scripts (verify_offline.py et al.) + its OCR fixture, so the
# offline guarantee can be verified from inside the running container.
COPY scripts/ ./scripts/

# Copy the model cache. .dockerignore no longer excludes this.
# Ownership matters — the non-root user must be able to read.
COPY --chown=apmatch:apmatch models/ ./models/

# /app is created by WORKDIR (root-owned). PaddleX writes a cache dir
# (/app/.paddlex) at startup, so the app user must own /app.
RUN chown apmatch:apmatch /app

USER apmatch

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=60s \
            --retries=3 \
  CMD curl -fsS http://localhost:8000/healthz || exit 1

# Uvicorn in single-worker mode. Startup loads ~1.2 GB of
# models; multiple workers would multiply that. Scale
# horizontally with container replicas instead.
ENTRYPOINT ["uvicorn", "apmatch.api.app:app", \
            "--host", "0.0.0.0", "--port", "8000", \
            "--log-level", "info"]
