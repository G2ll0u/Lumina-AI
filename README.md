# Lumina AI - Local RAG Assistant for Technical Documentation

Lumina is an open-source AI assistant that answers questions from **your own technical documents**. It runs 100% locally — no cloud, no data leakage.

Built for teams managing complex documentation (maintenance manuals, electrical schematics, spare parts lists, etc.) who need fast, accurate answers without sending data to external APIs.

---

## Features

- **Hybrid RAG + Reranking** — Combines semantic search (vector) and keyword search (BM25) with a CrossEncoder reranker for high-precision retrieval.
- **Expert Knowledge Loop** — Experts can correct wrong answers via thumbs-down feedback. Corrections are stored as verified knowledge and prioritized in future searches.
- **Multi-asset filtering** — Organize documents by asset ID (equipment, machine, product line...). Queries are scoped to the selected asset.
- **Integrated document management** — Upload, delete and re-index PDF/DOCX files directly from the UI.
- **Session history** — Persistent conversation history with auto-naming and session management.
- **100% local** — All inference and embeddings run on your hardware via Ollama or any OpenAI-compatible API.

---

## Architecture

```text
backend/                   # FastAPI (Python)
  app/
    main.py                # API endpoints & chat logic
    rag.py                 # Hybrid RAG engine (BM25 + ChromaDB + CrossEncoder)
    ingest.py              # Document ingestion pipeline (SHA-256, OCR, chunking)
    llm_client.py          # LLM interface (Ollama / OpenAI-compatible)
    auth.py                # Bearer token authentication
    history.py             # SQLite session & message persistence
  requirements.txt

frontend/                  # React + Vite + TypeScript
  components/              # Chat UI, settings modal, expert review modal
  services/                # API client

scripts/                   # Windows batch launchers
```

---

## Installation

### 1. System prerequisites

> These tools are not included in the repo. Install them before anything else.

#### Tesseract OCR (required for image-based PDFs)
- Download: [github.com/UB-Mannheim/tesseract](https://github.com/UB-Mannheim/tesseract/wiki)
- Install path (default): `C:\Program Files\Tesseract-OCR\`
- During install, select language packs that apply **for your case**

#### Poppler (required for PDF-to-image conversion)
- Download: [github.com/oschwartz10612/poppler-windows/releases](https://github.com/oschwartz10612/poppler-windows/releases)
- Unzip into: `backend/poppler/` (must contain `Library/bin/pdftoppm.exe`)

#### Ollama (local LLM runtime)
- Download: [ollama.com/download](https://ollama.com/download)
- Pull a model: `ollama pull llama3`

### 2. Backend setup

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Post-install steps (mandatory):**
```bash
# spaCy language model
python -m spacy download en_core_web_sm

# Optional: GPU acceleration with CUDA 12.4
pip uninstall torch torchaudio torchvision onnxruntime -y
pip install torch==2.6.0+cu124 torchaudio==2.6.0+cu124 torchvision==0.21.0+cu124 onnxruntime-gpu==1.24.2 --index-url https://download.pytorch.org/whl/cu124
```

**Environment configuration:**

Copy `backend/.env.example` to `backend/.env` and fill in the values:

```env
# Path to your documents folder
DOCS_PATH = "C:\\Path\\To\\Your\\Documents"

# LLM endpoint (Ollama default)
LLM_BASE_URL = "http://localhost:11434/v1"
LLM_API_KEY = "ollama"
CHAT_MODEL = "llama3"

# Tesseract path
TESSERACT_PATH = "C:\\Program Files\\Tesseract-OCR\\tesseract.exe"

# API security (leave empty for open dev mode)
SECRET_KEY = "your-secret-key-here"
```

### 3. Frontend setup

```bash
cd frontend
npm install
npm run dev
```

### 4. Start the backend

```bash
cd backend
python uvicorn_app.py
```

### 5. Ingest your documents

```bash
cd backend
python -m app.ingest
```

---

## Authentication

- **Dev mode** (no `SECRET_KEY` set): API is fully open, a warning is logged at startup.
- **Production**: set `SECRET_KEY` in `.env`. All API calls must include `Authorization: Bearer <your-key>`.

---

## Expert Knowledge

Lumina learns from your domain experts:

1. User clicks thumbs-down on a wrong answer.
2. Expert opens the review modal, reads the RAG context, types the correct answer.
3. Correction is stored in a dedicated ChromaDB collection with score 1.0.
4. Future similar questions retrieve the expert answer first.

---

## Document Organization

Documents are organized by **asset ID** — a free-form string that groups related files (e.g., equipment serial number, project code, product line).

The asset ID is extracted automatically from the folder structure: a folder named `3965 - Machine Name` gives asset ID `3965`. You can also set it manually via the document manager UI.

---

## Tech Stack

| Component | Technology |
|---|---|
| LLM | Ollama / any OpenAI-compatible API |
| Embeddings | `sentence-transformers/all-MiniLM-L6-v2` (local) |
| Reranker | `BAAI/bge-reranker-v2-m3` (local CrossEncoder) |
| Vector DB | ChromaDB |
| Keyword search | BM25 (rank-bm25) |
| Backend | FastAPI + Python |
| Frontend | React + Vite + TypeScript |
| OCR | Tesseract + Unstructured |

---

## License

MIT — free to use, modify and distribute.
