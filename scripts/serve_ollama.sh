#!/usr/bin/env bash
set -euo pipefail

# Ensure the host Ollama is serving the VLM model on :11434.
# Ollama is installed on the server host (systemd service); this script only
# checks it is up and the model is pulled.
#
# Usage (on the server):
#   bash scripts/serve_ollama.sh

MODEL="${VLM_MODEL_NAME:-qwen2.5vl:7b}"
PORT="${OLLAMA_PORT:-11434}"

if ! curl -sf "http://localhost:${PORT}/api/version" >/dev/null 2>&1; then
  echo "ERROR: Ollama is not responding on :${PORT}. Start it: sudo systemctl start ollama" >&2
  exit 1
fi

if ! ollama list 2>/dev/null | grep -q "^${MODEL}"; then
  echo "Model ${MODEL} not found — pulling..."
  ollama pull "${MODEL}"
fi

echo "Ollama ready: http://localhost:${PORT} (model: ${MODEL})"
