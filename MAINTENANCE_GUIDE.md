# Maintenance & Technical Guide - Lumina AI

This document provides technical instructions for the long-term maintenance, scaling, and troubleshooting of the Lumina AI RAG pipeline.

---

## 1. Architecture Overview

Lumina AI is a **Hybrid Retrieval-Augmented Generation (RAG)** assistant. It combines vectorial and keyword search to ensure maximum precision in industrial environments.

### Technical Stack
- **Frontend**: React 19 (Vite + TypeScript) + Tailwind (Typography).
- **Backend**: FastAPI (Python 3.13).
- **Vector DB**: ChromaDB (Persistent).
- **Keyword Search**: Rank-BM25.
- **Reranking**: BAAI/bge-reranker-v2-m3 (Cross-Encoder).
- **Inference**: Ollama (Local LLM server).

### Data Flow
1. **User Query** -> **Decomposition Agent** (Extraction of sub-queries).
2. **Retrieval** -> **ChromaDB** (Semantic) + **BM25** (Keywords).
3. **Reranking** -> **Cross-Encoder** re-scores top candidates.
4. **Context Injection** -> Top results are formatted and sent to the LLM.
5. **Streaming Response** -> Server-Sent Events (SSE) sent back to the UI.

---

## 2. Document Management

### Adding New Documents
1. Place your folders in the `DOCS_PATH` (configured in `.env`).
2. Follow the naming convention: `MachineNumber - Name/08-NMR/file.pdf`.
3. Launch ingestion via the UI ("Documents" tab) or run:
   ```powershell
   .\scripts\Windows\reset_ingestion.bat
   ```

### Ingestion Strategies
The system automatically detects the best strategy based on the filename:
- **HI-RES** (Slow, High Quality): Used for files containing patterns like `manual`, `schema`, `nomenclature`. Uses Unstructured.io + Tesseract OCR.
- **FAST** (Rapid): Used for standard text-rich documentation.

---

## 3. Security & Authentication

The API is protected by a **Bearer Token** mechanism.
- **Configuration**: Edit the `SECRET_KEY` variable in the `.env` file.
- **Client Side**: All users must enter this key in the "Settings" (gear icon) of the web interface.
- **Production Tip**: For high-security environments, deploy behind a Reverse Proxy (Nginx/Caddy) with HTTPS enabled.

---

## 4. Common Maintenance Tasks

### Update AI Models
If the models are hallucinating or outdated, pull new versions:
```bash
ollama pull phi3:latest
ollama pull llava:latest (for vision support)
```

### Database Cleanup
If the AI seems to "mix up" different machine versions, you can wipe the vector database and start fresh:
1. Delete the `backend/chroma_db/` folder.
2. Run `scripts\Windows\install_prerequisites.bat` or just `ingest.py`.

### Database Exploration
You can use the **ChromaDB Manager** to inspect exactly what's inside the brain of the AI:
```bash
.\scripts\Windows\ChromaDBManager.bat
```
(Starts a Streamlit UI for database CRUD operations).

---

## 5. Troubleshooting (FAQ)

| Issue | Cause | Solution |
| :--- | :--- | :--- |
| **401 Unauthorized** | Missing or wrong API Key. | Click Settings in UI -> Set Secret Key to match `.env`. |
| **Path not found** | Wrong directory structure. | Ensure scripts are run from the `scripts/Windows` folder or the project root. |
| **LLM Timeout** | Model is too heavy for the GPU. | Check `LLM_STREAM_TIMEOUT` in `.env` or use a smaller model. |
| **Tesseract Error** | OCR engine not found. | Check `TESSERACT_PATH` in `.env`. |

