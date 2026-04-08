@echo off
cd ../backend
REM

start "ChromaDB" cmd /k ".venv\Scripts\chroma.exe run --path ./chroma_db"

start "BDD Manager" cmd /k ".venv\Scripts\streamlit.exe run ./app/dbmanage.py"

