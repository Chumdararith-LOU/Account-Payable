#!/usr/bin/env bash
set -euo pipefail
SSH_TARGET="${1:?usage: $0 <ssh-target>}"
ssh "${SSH_TARGET}" bash -s <<'REMOTE'
  set -euo pipefail
  sudo mkdir -p /opt/apmatch
  sudo chown "$(id -u):$(id -g)" /opt/apmatch
  echo "Provisioned /opt/apmatch"
  echo "Next: copy .env.server.example to /opt/apmatch/.env.server and fill in values."
REMOTE
