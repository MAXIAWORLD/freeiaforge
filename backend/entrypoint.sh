#!/bin/sh
set -e

if [ ! -f /app/.env ]; then
    echo "[freeai] No .env found — copying .env.example → .env"
    cp /app/.env.example /app/.env
fi

exec "$@"
