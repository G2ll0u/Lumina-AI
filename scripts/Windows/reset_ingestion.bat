@echo off
cd /d "%~dp0..\..\backend"
echo === Suppression de la base de donnees vectorielle existante ===
if exist "chroma_db" (
    rmdir /s /q "chroma_db"
    echo Dossier chroma_db supprime.
) else (
    echo chroma_db n'existe pas encore.
)

echo.
echo === Lancement de l'ingestion ===
set CUDA_VISIBLE_DEVICES=0
".venv\Scripts\python.exe" app/ingest.py

pause
