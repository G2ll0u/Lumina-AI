@echo off
REM Installation des prérequis backend (Python) et frontend (Node)

echo === Backend : creation/maj de l'environnement virtuel ===
cd ../backend

if not exist ".venv" (
    echo Creation du venv Python...
    py -3.13 -m venv .venv
)

echo Installation / mise a jour des dependances Python...
".venv\Scripts\python.exe" -m pip install --upgrade pip
".venv\Scripts\python.exe" -m pip install -r requirements.txt

echo.
echo === Frontend : installation des dependances npm ===
cd ../frontend

npm install

echo.
echo Pre-requis installees pour le backend et le frontend.


