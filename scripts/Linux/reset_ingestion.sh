#!/bin/bash
cd ../backend
echo "=== Suppression de la base de donnees vectorielle existante ==="
if [ -d "chroma_db" ]; then
    rm -rf chroma_db
    echo "Dossier chroma_db supprime."
else
    echo "chroma_db n'existe pas encore."
fi

echo ""
echo "=== Lancement de l'ingestion ==="
export CUDA_VISIBLE_DEVICES=0
.venv/bin/python app/ingest.py

read -p "Appuyez sur Entrée pour continuer..."
