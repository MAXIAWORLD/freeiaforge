#!/bin/sh
set -e

if [ ! -f backend/.env ]; then
    cp backend/.env.example backend/.env
    echo ""
    echo "Created backend/.env from .env.example."
    echo "Open backend/.env in your editor and paste at least one API key."
    echo "Easiest: get a free Cerebras key at https://cloud.cerebras.ai"
    echo ""
    printf "Press Enter once you have edited backend/.env to continue..."
    read _
fi

docker compose up --build
