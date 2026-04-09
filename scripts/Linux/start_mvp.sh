#!/bin/bash

echo "======================================================="
echo "   Lancement des services du MVP Lumina AI (POC-IA)"
echo "======================================================="
echo ""

echo "[1/3] Demarrage d'Ollama (Mode silencieux si deja lance)..."
ollama serve > /dev/null 2>&1 &
OLLAMA_PID=$!

echo ""
echo "[2/3] Demarrage du Backend FastAPI..."
cd "$(dirname "$0")/../.." || exit
cd backend
if [ -f "venv/bin/python" ]; then
    VENV_PYTHON="venv/bin/python"
elif [ -f ".venv/bin/python" ]; then
    VENV_PYTHON=".venv/bin/python"
else
    echo "Environnement virtuel introuvable"
    exit 1
fi
$VENV_PYTHON uvicorn_app.py &
BACKEND_PID=$!

echo ""
echo "[3/3] Demarrage du Frontend React/Vite..."
cd ../frontend
npm run dev &
FRONTEND_PID=$!

echo ""
echo "======================================================="
echo "[OK] Tous les services ont ete demarres avec succes !"
echo "- Frontend : http://localhost:3000"
echo "- Backend  : http://localhost:8000"
echo "======================================================="
echo "Appuyez sur Entrée pour arrêter tous les services..."
read
kill $OLLAMA_PID $BACKEND_PID $FRONTEND_PID
