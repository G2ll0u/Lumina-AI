#!/bin/bash
cd "$(dirname "$0")/../.." || exit
cd backend
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "Virtual env created."
fi

.venv/bin/python uvicorn_app.py
