#!/usr/bin/env bash
set -euo pipefail

# Serve Qwen2.5-VL-7B-AWQ with vLLM on :8002, alongside the APMatch API on :8001.
#
# The 2080 Ti (11GB) runs both: vLLM takes ~7.9GB (VLM_GPU_UTIL=0.7 — the
# 6.9GB weights leave ~0.6GB for KV cache), the PaddleOCR pipeline the rest.
# Paddle's pool grows with OCR load (fresh start ~2.3GB, heavy use ~6.5GB),
# so do NOT run big OCR batches while vLLM is up — stop it first
# (docker rm -f apmatch-vlm) or lower VLM_GPU_UTIL.
#
# Usage (on the server):
#   bash scripts/serve_vlm.sh            # start (or restart) + wait for health
#   VLM_PORT=8003 bash scripts/serve_vlm.sh
#   docker rm -f apmatch-vlm             # stop

# -cu129: the host driver (575.x = CUDA 12.9) cannot run the default tag's
# CUDA 13 runtime — forward compatibility is unsupported on GeForce GPUs.
IMAGE="${VLLM_IMAGE:-vllm/vllm-openai:v0.32.0-cu129}"
MODEL_DIR="${MODEL_DIR:-/home/rith/apmatch-dev/models/vlm/Qwen2.5-VL-7B-AWQ}"
PORT="${VLM_PORT:-8002}"
GPU_UTIL="${VLM_GPU_UTIL:-0.7}"
NAME="apmatch-vlm"

if [ ! -d "$MODEL_DIR" ]; then
  echo "ERROR: model dir not found: $MODEL_DIR" >&2
  exit 2
fi

docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d --name "$NAME" \
  --gpus all \
  --network "${VLM_NETWORK:-apmatch-demo_default}" \
  -p "${PORT}:8000" \
  -v "${MODEL_DIR}:/model:ro" \
  "$IMAGE" \
  /model \
  --served-model-name qwen2.5-vl-7b-awq \
  --gpu-memory-utilization "$GPU_UTIL" \
  --max-model-len 8192 \
  --limit-mm-per-prompt '{"image": 1}' \
  --enforce-eager

echo "Waiting for vLLM on :${PORT} (model load takes a couple of minutes)..."
for _ in $(seq 1 120); do
  if curl -sf "http://localhost:${PORT}/health" >/dev/null 2>&1; then
    echo "vLLM ready: http://localhost:${PORT}/v1 (model: qwen2.5-vl-7b-awq)"
    exit 0
  fi
  if ! docker ps -q --filter "name=^${NAME}$" | grep -q .; then
    echo "ERROR: container exited during startup:" >&2
    docker logs --tail 50 "$NAME" >&2 || true
    exit 1
  fi
  sleep 5
done
echo "ERROR: vLLM not healthy after 10 min. Last logs:" >&2
docker logs --tail 50 "$NAME" >&2 || true
exit 1
