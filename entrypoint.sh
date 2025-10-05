#!/usr/bin/env bash
set -euo pipefail

if [ ! -f .env ]; then
  if [ -f .env.example ]; then
    cp .env.example .env
  else
    echo "Error: .env.example not found" >&2
    exit 1
  fi
fi

set -a
. ./.env
set +a

if [ -z "${BOT_TOKEN:-}" ]; then
  echo "Error: BOT_TOKEN not set"
  exit 1
fi

python bot.py
