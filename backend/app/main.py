from datetime import datetime
import os
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Depends, UploadFile, File, BackgroundTasks
import subprocess
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, model_validator
import json
from fastapi.responses import StreamingResponse, FileResponse
from .llm_client import LLMError, stream_chat_completion, decompose_query, analyze_image_with_llava, generate_hyde_document
from .auth import get_current_user
from .rag import search_relevant_docs, build_bm25_index, add_verified_knowledge, get_all_verified_knowledge, delete_verified_knowledge
from .web_search import search_web_duckduckgo
from .history import init_db, create_session, get_session, get_all_sessions, update_session_title, delete_session, add_message, get_message_context
from .feedback_manager import get_all_feedback, delete_feedback_by_index, add_feedback_entry
from contextlib import asynccontextmanager
import uuid
import asyncio

load_dotenv()

class ChatRequest(BaseModel):
    message: str
    asset_id: str | None = None
    machine_number: str | None = None  # legacy alias kept for frontend compat
    history: list[dict] = []
    session_id: str | None = None
    model: str | None = None
    
    # Settings dynamiques locaux
    temperature: float | None = 0.1
    system_prompt: str | None = None
    rag_top_k: int | None = 6
    use_decomposition: bool | None = True
    max_context_length: int | None = 15000
    include_all_versions: bool | None = False
    use_search: bool | None = False

    @model_validator(mode="after")
    def coerce_asset_id(self):
        """Accept legacy 'machine_number' field as asset_id."""
        if self.asset_id is None and self.machine_number is not None:
            self.asset_id = self.machine_number
        return self


class ChatResponse(BaseModel):
    answer: str
    sources: list[str] = []


class FeedbackRequest(BaseModel):
    message_id: str
    reason: str
    is_valid: bool | None = None

class VerifiedKnowledgeRequest(BaseModel):
    question: str
    answer: str
    asset_id: str | None = None
    feedback_index: int | None = None # Optionnel: index du feedback à  supprimer après validation

class ImageRequest(BaseModel):
    message: str
    image_base64: str

# Prompts loaded from .env (configurable without redeployment)
BASE_SYSTEM_PROMPT_DEFAULT = os.getenv(
    "BASE_SYSTEM_PROMPT",
    "Tu es un assistant expert en maintenance industrielle. Reponds de facon precise et concise."
)
CRITICAL_INSTRUCTIONS_DEFAULT = os.getenv(
    "CRITICAL_INSTRUCTIONS",
    "\nIMPORTANT:\n"
    "1. Tu dois TOUJOURS repondre en FRANCAIS.\n"
    "2. Utilise UNIQUEMENT le contexte fourni. Si la reponse n'est pas dans le contexte, dis-le clairement.\n"
    "3. Ne melange pas les informations distinctes de differents documents.\n"
    "4. Base-toi scrupuleusement sur les sources."
)

# Quantity-question keywords (JSON array or comma-separated via env)
_raw_qty_kw = os.getenv("QUANTITY_KEYWORDS", '["combien", "liste", "nombre", "how many"]')
try:
    QUANTITY_KEYWORDS: list[str] = json.loads(_raw_qty_kw)
except json.JSONDecodeError:
    QUANTITY_KEYWORDS = ["combien", "liste", "nombre", "how many"]

# Context length limits (chars)
MAX_CONTEXT_QUANTITY = int(os.getenv("MAX_CONTEXT_QUANTITY", "30000"))
MAX_CONTEXT_DEFAULT = int(os.getenv("MAX_CONTEXT_DEFAULT", "15000"))

# Web search
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "3"))

# App metadata
APP_TITLE = os.getenv("APP_TITLE", "Lumina AI - RAG Backend")


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[INFO] Demarrage du serveur AI Backend...")
    # Pre-load the BM25 index into RAM before accepting requests
    build_bm25_index()
    yield
    print("[INFO] Arret du serveur AI Backend...")

app = FastAPI(
    title=APP_TITLE,
    version="0.1.0",
    lifespan=lifespan
)

# Initialisation de la base SQLite
init_db()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # À restreindre (domaines du frontend) en production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Sources"],
)


@app.get("/health")
def healthcheck() -> dict:
    return {"status": "ok"}

@app.get("/api/file")
def get_local_file(path: str):
    """
    Sert un fichier local (contournement de la restriction file:/// du navigateur).
    On pourrait ajouter une vérification de sécurité ici pour empêcher le path traversal.
    """
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Fichier introuvable sur le serveur local")
    return FileResponse(path)




@app.post("/chat")
async def chat(request: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Endpoint de chat connecté à  un modèle local avec RAG et Streaming.
    """
    
    # 1. Décomposition de la requête (Agent LLM) si activée
    all_rag_results = []
    seen_contents = set()
    
    if request.use_decomposition:
        print(f"\n--- [AGENT] Analyse de la question : '{request.message}' ---")
        sub_queries = await decompose_query(request.message, request.model)
        print(f"  > Question décomposée en {len(sub_queries)} sous-recherches : {sub_queries}")
    else:
        # Sans décomposition, on cherche uniquement la requête brute
        sub_queries = [request.message]
    
    for sub_q in sub_queries:
        search_query = sub_q
        if request.asset_id:
            search_query = f"Machine {request.asset_id} {sub_q}"
        
        # 2b. HyDE enrichissement sémantique de la requête
        hyde_text = await generate_hyde_document(sub_q, request.model)
        if hyde_text:
            # Concaténation : la requête originale + la réponse fictive du LLM
            # Le vecteur d'intégration capture les deux espaces sémantiques
            search_query = f"{search_query}\n{hyde_text}"
        
        # Dynamic n_results: increase for quantity questions to ensure all components are found
        n_results_to_use = 15 if any(t in sub_q.lower() for t in QUANTITY_KEYWORDS) else 10
        
        results = search_relevant_docs(
            search_query,
            asset_id=request.asset_id,
            n_results=n_results_to_use,
            include_all_versions=request.include_all_versions or False,
            rerank_query=sub_q
        )
        
        for res in results:
            if res.page_content not in seen_contents:
                seen_contents.add(res.page_content)
                all_rag_results.append(res)
                
    # 3. Tri final global
    # rag.py ajoute un 'relevance_score' aux documents grâce au CrossEncoder
    all_rag_results.sort(key=lambda x: x.metadata.get("relevance_score", -100), reverse=True)
    
    # On isole les documents hyper pertinents de la flotte (Top K absolu dynamique)
    rag_results = all_rag_results[:request.rag_top_k]
    
    doc_context = ""
    sources = []
    
    if rag_results:
        context_parts = []
        for doc in rag_results:
            source = doc.metadata.get("source", "Inconnu")
            sources.append(source)
            # On ajoute un extrait du contenu
            context_parts.append(f"Source: {os.path.basename(source)}\nContenu: {doc.page_content}")
        
        doc_context = "\n\nDocuments pertinents trouvés (RAG Local) :\n" + "\n---\n".join(context_parts)
    
    # 4. Supplementary web search (if requested)
    web_results_text = None
    if request.use_search:
        print(f"  > [Web Search] Performing DuckDuckGo search for: {request.message}")
        web_results = search_web_duckduckgo(request.message, max_results=WEB_SEARCH_MAX_RESULTS)
        if web_results:
            web_results_text = web_results
            doc_context += "\n\n==========================\n"
            doc_context += f"Web Search (DuckDuckGo for '{request.message}'):\n{web_results}"
            sources.append("Web Search (DuckDuckGo)")
            print(f"  > [Web Search] Found external sources, appended to context.")
    
    # DEBUG: Print context to see what causes the crash
    try:
        print(f"--- RAG CONTEXT SENT TO LLM ---\n{doc_context}\n-------------------------------")
    except UnicodeEncodeError:
        safe_context = doc_context.encode('ascii', errors='replace').decode('ascii')
        print(f"--- RAG CONTEXT SENT TO LLM ---\n{safe_context}\n-------------------------------")
    
    # PRE-PROCESSING: For quantity questions, extract MP tags programmatically
    # to help the LLM reason correctly (workaround for small models like Llama 3B)
    is_quantity_q = any(t in sub_q.lower() for t in QUANTITY_KEYWORDS)
    if is_quantity_q:
        import re as _re
        # Find all unique MP tags in the context (e.g. 13MP1W, 16MP1R, QMP2W)
        mp_tags = list(dict.fromkeys(_re.findall(r'(?<!\w)(?:[A-Z0-9]+)?MP\d+[A-Z]*', doc_context)))
        if mp_tags:
            tag_summary = "[AUTO-EXTRACTION - Pump Codes (MP) found in documents]\n"
            tag_summary += "\n".join(f"- {tag}" for tag in mp_tags)
            tag_summary += f"\nTotal unique MP codes: {len(mp_tags)}\n\n"
            doc_context = tag_summary + doc_context
            print(f"  > [Pre-processing] Injected {len(mp_tags)} MP tags: {mp_tags}")

    # Dynamic context length limit to prevent crash
    MAX_CONTEXT_LENGTH = MAX_CONTEXT_QUANTITY if is_quantity_q else (request.max_context_length or MAX_CONTEXT_DEFAULT)
    print(datetime.now().strftime("%H:%M:%S"))
    if len(doc_context) > MAX_CONTEXT_LENGTH:
        print(f"  > WARNING: Context too long ({len(doc_context)} chars). Truncating to {MAX_CONTEXT_LENGTH}.")
        doc_context = doc_context[:MAX_CONTEXT_LENGTH] + "\n[...Truncated for safety...]"

    BASE_SYSTEM_PROMPT = request.system_prompt if request.system_prompt else BASE_SYSTEM_PROMPT_DEFAULT


    system_message = {
        "role": "system",
        "content": (
            f"{BASE_SYSTEM_PROMPT}\n\n"
            "Utilise les informations contextuelles ci-dessous pour répondre.\n\n"
            "CONTEXTE DOCUMENTAIRE :\n"
            f"{doc_context}"
        ),
    }

    user_message_parts = []
    if request.asset_id:
        user_message_parts.append(f"Numéro de machine: {request.asset_id}")
    user_message_parts.append(f"Question: {request.message}")
    
    # Critical instructions appended directly to the user message to prevent truncation loss
    user_message_parts.append(CRITICAL_INSTRUCTIONS_DEFAULT)
    
    # Build conversation history (Last 3 turns max to save context)
    history_messages = []
    if request.history:
        # Take last 6 messages (3 exchanges)
        for msg in request.history[-6:]:
            role = msg.get("role")
            content = msg.get("content")
            if role in ["user", "assistant"] and content:
                history_messages.append({"role": role, "content": content})

    messages = [system_message] + history_messages + [
        {
            "role": "user",
            "content": "\n".join(user_message_parts),
        },
    ]

    # Prepare headers with sources
    headers = {
        "X-Sources": json.dumps(sources)
    }

    async def stream_with_logging(generator, session_id: str | None, user_msg: str):
        full_response = ""
        source_nodes = []
        is_new_session = False
        
        # Get a session ID if none provided or if it is a temporary frontend ID
        if not session_id or session_id.startswith("temp-"):
            session_id = str(uuid.uuid4())
            is_new_session = True
            
        try:
            # Immediately save the user message to the database
            add_message(session_id, "user", user_msg)
            
            # Emit the session ID so the frontend can track the new session
            if is_new_session:
                yield f"data: {json.dumps({'sessionId': session_id})}\n\n"
            
            # Yield sources as the next chunk
            if rag_results:
                for doc in rag_results:
                    source_nodes.append({
                        "url": doc.metadata.get("source", "Inconnu"),
                        "snippet": doc.page_content
                    })
            if getattr(request, "use_search", False) and web_results_text:
                source_nodes.append({
                    "url": "Recherche Web (DuckDuckGo)",
                    "snippet": web_results_text
                })
            
            if source_nodes:
                yield f"data: {json.dumps({'sources': source_nodes})}\n\n"

            async for chunk in generator:
                full_response += chunk
                # Wrap in SSE format to safely escape newlines and prevent client-side parsing crashes
                safe_chunk = json.dumps({"text": chunk})
                yield f"data: {safe_chunk}\n\n"
        finally:
            if session_id:
                try:
                    # Save the assistant response (with sources) at the end of the stream
                    add_message(session_id, "assistant", full_response, source_nodes=source_nodes)
                except Exception as e:
                    print(f"Error logging assistant message to DB: {e}")
                
                if is_new_session:
                    # Background task to generate a title AFTER the main stream is fully done
                    async def generate_title():
                        title_messages = [
                            {"role": "system", "content": "Génère un titre très court (maximum 5 mots) qui résume parfaitement ce problème ou cette question. Ne mets pas de guillemets, ni de point à  la fin."},
                            {"role": "user", "content": user_msg}
                        ]
                        try:
                            title_text = ""
                            async for chunk in stream_chat_completion(title_messages, model_name=request.model, temperature=0.7):
                                title_text += chunk
                            title_text = title_text.strip().strip('"').strip("'")
                            if title_text:
                                update_session_title(session_id, title_text)
                        except Exception as e:
                            print(f"Failed to generate title: {e}")
                    
                    asyncio.create_task(generate_title())

    try:
        return StreamingResponse(
            stream_with_logging(stream_chat_completion(messages, model_name=request.model, temperature=request.temperature), request.session_id, request.message),
            media_type="text/event-stream",
            headers=headers
        )
    except LLMError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/feedback")
def feedback_endpoint(payload: FeedbackRequest, user: dict = Depends(get_current_user)) -> dict:
    """
    Réception d'un signalement de réponse erronée.
    Enrichit le feedback avec le contexte (question/réponse/RAG) et sauvegarde.
    """
    try:
        # 1. Récupérer le contexte complet via history.py
        context = get_message_context(payload.message_id)
        
        feedback_data = payload.model_dump()
        feedback_data["timestamp"] = datetime.now().isoformat()
        feedback_data["user"] = user.get("sub", "anonymous")
        
        if context:
            feedback_data["context"] = context
        
        # 2. Sauvegarder via le feedback_manager
        add_feedback_entry(feedback_data)
            
        return {"status": "received"}
    except Exception as e:
        print(f"Error saving feedback: {e}")
        raise HTTPException(status_code=500, detail="Failed to save feedback")

@app.get("/api/feedback")
def api_get_all_feedback(user: dict = Depends(get_current_user)):
    """List all recorded feedback entries for review/export."""
    return get_all_feedback()

@app.delete("/api/feedback/{index}")
def api_delete_feedback(index: int, user: dict = Depends(get_current_user)):
    """Supprime un feedback (abusif ou déjà  traité)."""
    if delete_feedback_by_index(index):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Feedback non trouvé")

@app.post("/api/verified_knowledge")
async def api_add_verified_knowledge(req: VerifiedKnowledgeRequest, user: dict = Depends(get_current_user)):
    """Store an expert-validated answer into ChromaDB for future retrieval."""
    try:
        add_verified_knowledge(req.question, req.answer, req.asset_id)
        
        # If a feedback index is provided, delete it since it has been "handled"
        if req.feedback_index is not None:
            delete_feedback_by_index(req.feedback_index)
            
        return {"status": "ok", "message": "Connaissance enregistrée et priorisée."}
        return {"status": "ok", "message": "Knowledge saved and prioritized."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/verified_knowledge")
def api_get_all_verified_knowledge(user: dict = Depends(get_current_user)):
    """List all expert-validated knowledge entries already injected."""
    return get_all_verified_knowledge()

@app.delete("/api/verified_knowledge/{id}")
def api_delete_verified_knowledge(id: str, user: dict = Depends(get_current_user)):
    """Delete a verified knowledge entry from the ChromaDB database."""
    if delete_verified_knowledge(id):
        return {"status": "deleted"}
    raise HTTPException(status_code=404, detail="Knowledge not found")

@app.post("/analyze_image")
async def analyze_image_endpoint(request: ImageRequest, user: dict = Depends(get_current_user)):
    """
    Endpoint to send an image and text to the VLM (LLaVA).
    """
    try:
        response = await analyze_image_with_llava(request.message, request.image_base64)
        return {"response": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

class SessionRenameRequest(BaseModel):
    title: str

@app.get("/api/sessions")
def api_get_sessions():
    """Return the session list sorted by last update date."""
    return get_all_sessions()

@app.post("/api/sessions")
def api_create_session():
    """Create a new empty session in the database and return its ID."""
    session_id = str(uuid.uuid4())
    create_session(session_id, "Nouvelle discussion")
    return {"id": session_id, "title": "Nouvelle discussion"}

@app.get("/api/sessions/{session_id}")
def api_get_session(session_id: str):
    """Retrieve a session and all its associated messages."""
    # Silently handle temporary sessions generated by the frontend before the first assistant reply
    if session_id.startswith("temp-"):
        return {"id": session_id, "title": "Nouvelle discussion", "updated_at": datetime.now().isoformat(), "messages": []}
        
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session non trouvée")
    return session

@app.put("/api/sessions/{session_id}/title")
def api_rename_session(session_id: str, req: SessionRenameRequest):
    """Update the title of a session from the client UI (rename)."""
    update_session_title(session_id, req.title)
    return {"status": "ok"}

@app.delete("/api/sessions/{session_id}")
def api_delete_session(session_id: str):
    """Delete a session and its entire message history."""
    delete_session(session_id)
    return {"status": "ok"}

# --- ROUTES GESTION DOCUMENTAIRE ---

@app.get("/api/documents")
def api_get_documents():
    """List all documents present in the configured DOCS_PATH folder."""
    docs_path = os.getenv("DOCS_PATH", "./machine_docs")
    if not os.path.exists(docs_path):
        return []
    
    documents = []
    # Recursively find PDF and DOCX files
    for root, _, files in os.walk(docs_path):
        for file in files:
            if file.lower().endswith(('.pdf', '.docx', '.txt', '.md')):
                full_path = os.path.join(root, file)
                rel_path = os.path.relpath(full_path, docs_path)
                # Obtenir la taille et la date
                try:
                    stat = os.stat(full_path)
                    documents.append({
                        "name": file,
                        "path": rel_path.replace('\\', '/'),
                        "size": stat.st_size,
                        "updated_at": datetime.fromtimestamp(stat.st_mtime).isoformat()
                    })
                except Exception:
                    pass
    
    return sorted(documents, key=lambda x: x["updated_at"], reverse=True)

@app.post("/api/documents")
async def api_upload_document(path: str = "", file: UploadFile = File(...)):
    """Upload un document dans le dossier configuré (ex: dossier principal ou composant)"""
    docs_path = os.getenv("DOCS_PATH", "./machine_docs")
    target_folder_name = os.getenv("TARGET_FOLDER", "08-NMR")
    
    # Sécurité basique contre le path traversal
    safe_path = os.path.normpath(path).replace('\\', '/')
    if ".." in safe_path or safe_path.startswith('/'):
        raise HTTPException(status_code=400, detail="Chemin invalide")
        
    # Ergonomie: Si l'utilisateur tape "3986" sans "08-NMR", on l'ajoute automatiquement
    if safe_path and safe_path != "." and not safe_path.endswith(target_folder_name):
        safe_path = os.path.join(safe_path, target_folder_name).replace('\\', '/')
    
    target_dir = os.path.join(docs_path, safe_path)
    os.makedirs(target_dir, exist_ok=True)
    
    file_path = os.path.join(target_dir, file.filename)
    
    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)
        return {"status": "ok", "message": f"Fichier {file.filename} uploadé avec succès"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de l'upload: {str(e)}")

@app.delete("/api/documents/{file_path:path}")
def api_delete_document(file_path: str):
    """Supprime un document physiquement"""
    docs_path = os.getenv("DOCS_PATH", "./machine_docs")
    
    # Sécurité
    safe_path = os.path.normpath(file_path).replace('\\', '/')
    if ".." in safe_path or safe_path.startswith('/'):
        raise HTTPException(status_code=400, detail="Chemin invalide")
        
    full_path = os.path.join(docs_path, safe_path)
    if not os.path.exists(full_path):
        raise HTTPException(status_code=404, detail="Fichier non trouvé")
        
    try:
        os.remove(full_path)
        return {"status": "ok", "message": "Fichier supprimé avec succès"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erreur lors de la suppression: {str(e)}")

# État global de l'ingestion
ingestion_status = {"is_running": False, "last_run": None, "logs": ""}

def run_ingestion_script(target_dir: str = ""):
    global ingestion_status
    ingestion_status["is_running"] = True
    ingestion_status["logs"] = "Démarrage de l'ingestion...\n"
    if target_dir:
        ingestion_status["logs"] += f"Cible spécifique demandée: {target_dir}\n"
    
    try:
        # On utilise le python de l'environnement virtuel actuel
        python_exe = os.sys.executable
        ingest_script = os.path.join(os.path.dirname(__file__), "ingest.py")
        
        # The server runs from ./backend -- ingest.py expects to be launched from there
        cwd = os.path.dirname(os.path.dirname(__file__))
        
        cmd = [python_exe, ingest_script]
        if target_dir:
            cmd.extend(["--target", target_dir])
            
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=cwd
        )
        
        for line in process.stdout:
            ingestion_status["logs"] += line
            print(f"[INGEST] {line}", end="")
            
        process.wait()
        ingestion_status["logs"] += f"\nTerminé avec le code {process.returncode}"
    except Exception as e:
        ingestion_status["logs"] += f"\nErreur critique: {str(e)}"
    finally:
        # Refresh the BM25 index in RAM with the newly ingested documents
        ingestion_status["logs"] += "\n[SYSTEM] Mise à jour de l'index de recherche BM25 en RAM...\n"
        build_bm25_index(force=True)
        ingestion_status["logs"] += "[SYSTEM] Index BM25 mis à jour avec succès.\n"
        
        ingestion_status["is_running"] = False
        ingestion_status["last_run"] = datetime.now().isoformat()

class IngestionRequest(BaseModel):
    target_dir: str | None = None

@app.post("/api/documents/ingest")
def api_start_ingestion(req: IngestionRequest, background_tasks: BackgroundTasks):
    """Déclenche l'ingestion documentaire en tâche de fond (complète ou ciblée)"""
    global ingestion_status
    if ingestion_status["is_running"]:
        raise HTTPException(status_code=400, detail="Une ingestion est déjà en cours")
        
    target = req.target_dir or ""
    # If the frontend sends "3986/08-NMR", keep only the machine ID "3986" -- ingest.py adds the subfolder.
    target_folder_name = os.getenv("TARGET_FOLDER", "08-NMR")
    if target.endswith(f"/{target_folder_name}") or target.endswith(f"\\{target_folder_name}"):
        target = target[:-len(target_folder_name)-1]
        
    background_tasks.add_task(run_ingestion_script, target)
    return {"status": "ok", "message": f"Ingestion démarrée for {target if target else 'all'}"}

@app.get("/api/documents/ingest/status")
def api_get_ingestion_status():
    """Récupère l'état actuel de l'ingestion"""
    return ingestion_status
