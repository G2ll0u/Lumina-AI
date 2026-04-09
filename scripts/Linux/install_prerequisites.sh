#!/bin/bash
# Installation des prérequis backend (Python) et frontend (Node)

echo "=== Backend : creation/maj de l'environnement virtuel ==="
cd "$(dirname "$0")/../.." || exit
cd backend

if [ ! -d ".venv" ]; then
    echo "Creation du venv Python..."
    python3.13 -m venv .venv
fi

echo "Installation / mise a jour des dependances Python..."
.venv/bin/python -m pip install --upgrade pip
.venv/bin/python -m pip install -r requirements.txt

echo ""
echo "=== Frontend : installation des dependances npm ==="
cd ../frontend

npm install

echo ""
echo "Pre-requis installees pour le backend et le frontend."
