@echo off
chcp 65001 >nul
color 0B
echo =======================================================
echo    Lancement des services du MVP Lumina AI (POC-IA)
echo =======================================================
echo.

echo [1/3] Demarrage d'Ollama (Mode silencieux si deja lance)...
start "Ollama Serve" cmd /k "echo Serveur Ollama & ollama serve"

echo.
echo [2/3] Demarrage du Backend FastAPI...
cd /d "%~dp0..\..\backend"
start "Backend FastAPI" cmd /k "echo Serveur API Backend... & if exist venv\Scripts\python.exe (venv\Scripts\python.exe uvicorn_app.py) else if exist .venv\Scripts\python.exe (.venv\Scripts\python.exe uvicorn_app.py) else (echo Environnement virtuel introuvable & pause)"

echo.
echo [3/3] Demarrage du Frontend React/Vite...
cd /d "%~dp0..\..\frontend"
start "Frontend Vite" cmd /k "echo Serveur Web Frontend... & npm.cmd run dev"

echo.
echo =======================================================
echo [OK] Tous les services ont ete demarres avec succes !
echo - Frontend : http://localhost:3000
echo - Backend  : http://localhost:8000
echo =======================================================
pause
