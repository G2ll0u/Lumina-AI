@echo off
cd /d "%~dp0..\..\backend"
if not exist ".venv" (
    python -m venv .venv
    echo Virtual env created.
)

.venv\Scripts\python.exe uvicorn_app.py