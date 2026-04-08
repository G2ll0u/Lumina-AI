#!/bin/bash
cd ../backend

source .venv/bin/activate
chroma run --path ./chroma_db &
CHROMA_PID=$!

streamlit run ./app/dbmanage.py &
STREAMLIT_PID=$!

echo "Pressez Entrée pour fermer ChromaDB et le gestionnaire BDD..."
read
kill $CHROMA_PID $STREAMLIT_PID
