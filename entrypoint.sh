#!/usr/bin/env bash
set -euo pipefail

# Optional .env file support: only load if it exists. In container deployments
# secrets must be provided via env vars or env_file (compose / k8s); we never
# fall back to .env.example because example credentials must not reach prod.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

if [ -z "${BOT_TOKEN:-}" ]; then
  echo "Error: BOT_TOKEN is not set" >&2
  exit 1
fi

exec python bot.py
