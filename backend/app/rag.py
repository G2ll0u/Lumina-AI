
import os
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_core.documents import Document
from rank_bm25 import BM25Okapi
from sentence_transformers import CrossEncoder
from dotenv import load_dotenv
import re
import traceback
import torch
from .search import search_docs
from datetime import datetime
import uuid

load_dotenv()

CHROMA_PATH = os.path.join(os.path.dirname(__file__), "../chroma_db")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "sentence-transformers/all-MiniLM-L6-v2")

def normalize_doc_name(filename: str) -> str:
    name = os.path.splitext(filename)[0].lower()
    # Remove dots and trailing whitespace from the stem before processing versions
    name = name.strip(' ._')
    # Remove numeric versions: V1.0, v2, V1.1.2 ...
    name = re.sub(r'[_\-\s]?v\d+(?:\.\d+)*', '', name)
    # Remove common textual version markers
    for marker in ['final', 'ok', 'signe', 'signé', 'rev', 'version', 'copie', 'copy']:
        name = re.sub(rf'[_\-\s]?{marker}\d*', '', name)
    # Remove single letter version/suffix even if followed by dots (e.g. 3965 C..)
    name = re.sub(r'[_\-\s]*[a-z]\s?\.*$', '', name)
    # Collapse whitespace/separators
    name = re.sub(r'[\s_\-]+', '_', name).strip('_')
    return name

def extract_version_score(filename: str) -> tuple:
    """Returns a sortable tuple for version comparison (Higher = better)."""
    name = os.path.splitext(filename)[0].lower()
    match = re.search(r'v(\d+)(?:\.(\d+))?(?:\.(\d+))?', name)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        patch = int(match.group(3) or 0)
        return (3, major * 10000 + minor * 100 + patch)
    match = re.search(r'(?:^|[_\-\s])([a-z])(?:\.|$)', name)
    if match:
        return (2, ord(match.group(1)) - ord('a'))
    return (1, 0)

_vector_store = None
_reranker_model = None
import time
_unique_sources_cache = None
_last_sources_update = 0
_bm25_index = None
_bm25_data = None

# --- Configurable constants from .env ---
RERANKER_MODEL = os.getenv("RERANKER_MODEL", "BAAI/bge-reranker-v2-m3")
BM25_CACHE_TTL = int(os.getenv("BM25_CACHE_TTL", "3600"))  # seconds
SEARCH_MAX_TARGET_FILES = int(os.getenv("SEARCH_MAX_TARGET_FILES", "3"))
RERANKER_NOMENCLATURE_BOOST = float(os.getenv("RERANKER_NOMENCLATURE_BOOST", "0.1"))
SEARCH_TECHNICAL_CHUNK_QUOTA = int(os.getenv("SEARCH_TECHNICAL_CHUNK_QUOTA", "5"))
SEARCH_GENERIC_CHUNK_QUOTA = int(os.getenv("SEARCH_GENERIC_CHUNK_QUOTA", "1"))

def get_reranker_model():
    global _reranker_model
    if _reranker_model is None:
        print(f"  > Initializing {RERANKER_MODEL} (multilingual, first run may download ~1GB)")
        device = "cuda" if torch.cuda.is_available() else "cpu"
        _reranker_model = CrossEncoder(RERANKER_MODEL, max_length=512, device=device)
    return _reranker_model

def get_vector_store():
    global _vector_store
    if _vector_store is None:
        if os.path.exists(CHROMA_PATH):
            device = "cuda" if torch.cuda.is_available() else "cpu"
            embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME, model_kwargs={'device': device})
            _vector_store = Chroma(
                persist_directory=CHROMA_PATH,
                embedding_function=embeddings
            )
        else:
            print(f"Warning: Vector store not found at {CHROMA_PATH}. Please run ingest.py.")
            return None
    return _vector_store

def get_verified_store():
    """Load the ChromaDB collection containing expert-validated knowledge."""
    device = "cuda" if torch.cuda.is_available() else "cpu"
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME, model_kwargs={'device': device})
    return Chroma(
        persist_directory=CHROMA_PATH,
        embedding_function=embeddings,
        collection_name="verified_knowledge"
    )

def add_verified_knowledge(question: str, answer: str, asset_id: str | None = None):
    """Store an expert-validated Question/Answer pair in the verified knowledge collection."""
    store = get_verified_store()
    metadata = {
        "source": "Expert Verified Knowledge",
        "asset_id": asset_id,
        "is_verified": True,
        "timestamp": datetime.now().isoformat()
    }
    store.add_texts(texts=[answer], metadatas=[metadata], ids=[str(uuid.uuid4())])
    print(f"[OK] Expert knowledge added to verified store (Asset: {asset_id})")

def get_all_verified_knowledge() -> list[dict]:
    """Retrieve all verified knowledge entries from the ChromaDB collection."""
    try:
        store = get_verified_store()
        data = store.get(include=["documents", "metadatas"])
        
        results = []
        if "documents" in data and data["documents"]:
            for i in range(len(data["documents"])):
                results.append({
                    "id": data["ids"][i],
                    "answer": data["documents"][i],
                    "metadata": data["metadatas"][i]
                })
        return results
    except Exception as e:
        print(f"Error fetching verified knowledge: {e}")
        return []

def delete_verified_knowledge(knowledge_id: str) -> bool:
    """Delete a specific entry from the verified knowledge collection."""
    try:
        store = get_verified_store()
        store.delete(ids=[knowledge_id])
        return True
    except Exception as e:
        print(f"Error deleting verified knowledge: {e}")
        return False

def reset_vector_store():
    global _vector_store
    _vector_store = None

def build_bm25_index(force=False):
    """
    Build the BM25 index by loading all text content from ChromaDB into RAM.
    This is a heavy operation -- run it at server startup, not on every request.
    """
    global _unique_sources_cache, _last_sources_update, _bm25_index, _bm25_data
    current_time = time.time()
    
    if not force and _bm25_index is not None and (current_time - _last_sources_update <= BM25_CACHE_TTL):
        return True  # Cache still valid
        
    if force:
        print("Forcing vector store reload from disk before building BM25...")
        reset_vector_store()

    vector_store = get_vector_store()
    if not vector_store:
        return False
        
    try:
        print("\n" + "="*60)
        print("[BM25] Building search index...")
        print("Extracting all text chunks into RAM for keyword search.")
        print("This may take a few seconds (or minutes for large corpora).")
        print("="*60)
        start_time = time.time()
        
        # Paginated fetch to avoid SQLite "too many SQL variables" on large corpora
        all_documents = []
        all_metadatas = []
        batch_size = 5000
        offset = 0
        while True:
            batch = vector_store.get(
                include=["documents", "metadatas"],
                limit=batch_size,
                offset=offset
            )
            docs_batch = batch.get("documents") or []
            meta_batch = batch.get("metadatas") or []
            if not docs_batch:
                break
            all_documents.extend(docs_batch)
            all_metadatas.extend(meta_batch)
            if len(docs_batch) < batch_size:
                break
            offset += batch_size

        all_data = {"documents": all_documents, "metadatas": all_metadatas}

        if all_data["documents"]:
            _bm25_data = all_data
            
            # Simple whitespace tokenization for BM25 (lowercase split)
            tokenized_corpus = [str(doc).lower().split() for doc in all_data["documents"]]
            _bm25_index = BM25Okapi(tokenized_corpus)
            
            unique_sources = {
                meta["source"] for meta in all_data["metadatas"]
                if meta is not None and "source" in meta
            }
            _unique_sources_cache = list(unique_sources)
            _last_sources_update = current_time
            
            elapsed = time.time() - start_time
            print("="*60)
            print(f"[BM25] Index ready in {elapsed:.1f}s")
            print(f"[BM25] {len(all_data['documents'])} text chunks indexed")
            print("="*60 + "\n")
            return True
        return False
    except Exception as e:
        print(f"Warning: Could not build BM25 index ({e})")
        _unique_sources_cache = None
        return False
def search_relevant_docs(query: str, asset_id: str | None = None, n_results: int = 5,
                         include_all_versions: bool = False, rerank_query: str | None = None):
    """
    Search for relevant documents in the vector store using a hybrid approach:
    1. Keyword search on filenames (prioritize specific documents).
    2. Vector semantic search (find relevant content).
    Optional: filter by asset_id.
    Optional: include_all_versions=False (default) restricts to is_latest=True documents.
    """
    vector_store = get_vector_store()
    if not vector_store:
        print("Error: Vector store is not initialized.")
        return []
    
    try:
        all_results = []
        seen_content = set()
        
        # 0. PRIORITY: Search in the expert VERIFIED knowledge base first
        try:
            device = "cuda" if torch.cuda.is_available() else "cpu"
            embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL_NAME, model_kwargs={'device': device})
            verified_store = Chroma(
                persist_directory=CHROMA_PATH,
                embedding_function=embeddings,
                collection_name="verified_knowledge"
            )
            
            # Use a small k -- expert answers are highly curated
            # Note: similarity_search_by_vector might be better if we have the embedding, 
            # but search_relevant_docs is called with the query string.
            # We'll use similarity_search here for simplicity, or we can use the query_embedding if available.
            
            v_filter = {"asset_id": asset_id} if asset_id else None
            verified_docs = verified_store.similarity_search(query, k=2, filter=v_filter)
            
            for doc in verified_docs:
                doc.metadata["search_type"] = "expert_verified"
                doc.metadata["relevance_score"] = 1.0 # Boost maximum
                all_results.append(doc)
                seen_content.add(doc.page_content)
                print(f"  > [VERIFIED] Found a matching expert answer.")
        except Exception as e:
            print(f"Warning: Error searching verified knowledge ({e})")
        
        # --- End Priority ---
        
        # Build filter dict
        # Supports both 'asset_id' (new) and 'machine_id' (legacy from old ingestions)
        search_kwargs = {}
        chroma_filter_clauses = []
        if asset_id:
            # Accept both key names for backward compat with existing ingested data
            chroma_filter_clauses.append({"$or": [{"asset_id": asset_id}, {"machine_id": asset_id}]})
            print(f"  > Filtering by asset_id: {asset_id}")
        if not include_all_versions:
            chroma_filter_clauses.append({"is_latest": True})
            print(f"  > Filtering to latest versions only (is_latest=True)")
        if len(chroma_filter_clauses) == 1:
            search_kwargs["filter"] = chroma_filter_clauses[0]
        elif len(chroma_filter_clauses) > 1:
            search_kwargs["filter"] = {"$and": chroma_filter_clauses}

        # 0. Embed Query EXACTLY ONCE here to save 100~300ms per sub-search
        print(f"  > Embedding query: '{query}'")
        query_embedding = vector_store.embeddings.embed_query(query)

        # Extract available paths from Chroma with a 3600s TTL Cache to avoid DB bottlenecks
        global _unique_sources_cache
        
        build_bm25_index(force=False) # Will use cache if valid
        available_sources = _unique_sources_cache

        # 1. Targeted Search (Filename based)
        # Search for files matching the query (e.g. "Rapport 16.10.2017")
        print(f"Hybrid Search: Analyzing query '{query}'")
        target_files = search_docs(query, available_sources=available_sources)
        
        if target_files:
            # Filter target files by asset_id if specified
            if asset_id:
                target_files = [f for f in target_files if asset_id in f]

            print(f"  > Found {len(target_files)} relevant files by name: {[os.path.basename(f) for f in target_files]}")
            # Fetch more chunks per file to avoid missing deep sections
            chunks_per_file = max(8, n_results * 2)

            for file_path in target_files[:SEARCH_MAX_TARGET_FILES]:
                file_filter = {"source": file_path}
                filename_low = os.path.basename(file_path).lower()
                
                # SPECIAL HANDLING FOR NOMENCLATURE/SCHEMAS:
                # Vector search might miss tables. For these files, we take EVERYTHING (or at least 50 chunks).
                if any(t in filename_low for t in ["schéma", "schema", "nomenclature", "plan"]):
                    file_docs = vector_store.get(where=file_filter, limit=50).get("documents", [])
                    # Reconstruct Document objects as .get() returns raw data
                    for j in range(len(file_docs)):
                        content = file_docs[j]
                        if content not in seen_content:
                            all_results.append(Document(
                                page_content=content, 
                                metadata={"source": file_path, "search_type": "filename_match", "is_nomenclature": True}
                            ))
                            seen_content.add(content)
                else:
                    # Normal files (Manuals): Fetch more context using precomputed vector
                    file_docs = vector_store.similarity_search_by_vector(query_embedding, k=chunks_per_file, filter=file_filter)
                    for doc in file_docs:
                        if doc.page_content not in seen_content:
                            doc.metadata["search_type"] = "filename_match"
                            all_results.append(doc)
                            seen_content.add(doc.page_content)

        # 2. General Vector Search & BM25 Hybrid Search
        doc_map = {} # Maps page_content to the Document to merge ranks and prevent duplicates
        
        remaining_slots = max(20, n_results * 4) # We fetch top 20 for RRF
        
        print(f"  > Performing Vector semantic search (k={remaining_slots})...")
        general_docs = vector_store.similarity_search_by_vector(query_embedding, k=remaining_slots, **search_kwargs)
        for rank, doc in enumerate(general_docs):
            if doc.page_content not in doc_map:
                doc.metadata["vector_rank"] = rank + 1
                doc_map[doc.page_content] = doc
                
        # BM25 Keyword Search
        if _bm25_index and _bm25_data:
            print(f"  > Performing BM25 keyword search...")
            # Use only the first line of the query for BM25 (before HyDE text)
            # The HyDE text would dilute keyword signal with generic vocabulary
            bm25_query_text = query.split("\n")[0]  # Only the original sub-query part
            tokenized_query = bm25_query_text.lower().split()
            bm25_scores = _bm25_index.get_scores(tokenized_query)
            
            # Filter by asset_id and is_latest if requested
            # Supports both 'asset_id' (new) and 'machine_id' (legacy) metadata keys
            filtered_indices = []
            for i, meta in enumerate(_bm25_data["metadatas"]):
                doc_asset = meta.get("asset_id") or meta.get("machine_id")
                if asset_id and doc_asset != asset_id:
                    continue
                if not include_all_versions and not meta.get("is_latest", True):
                    continue
                filtered_indices.append(i)
                
            # Get top indices
            filtered_indices.sort(key=lambda i: bm25_scores[i], reverse=True)
            top_bm25_indices = filtered_indices[:remaining_slots]
            
            for rank, idx in enumerate(top_bm25_indices):
                score = bm25_scores[idx]
                if score > 0:
                    content = _bm25_data["documents"][idx]
                    meta = _bm25_data["metadatas"][idx]
                    
                    if content in doc_map:
                        doc_map[content].metadata["bm25_rank"] = rank + 1
                    else:
                        doc = Document(page_content=content, metadata=meta.copy())
                        doc.metadata["bm25_rank"] = rank + 1
                        doc_map[content] = doc

        # 3. Reciprocal Rank Fusion (RRF)
        combined_list = list(doc_map.values())
        print(f"  > Fusing {len(combined_list)} distinct documents using Reciprocal Rank Fusion (RRF)...")
        for doc in combined_list:
            v_rank = doc.metadata.get("vector_rank", 1000)
            b_rank = doc.metadata.get("bm25_rank", 1000)
            # RRF Formula
            doc.metadata["rrf_score"] = (1.0 / (60 + v_rank)) + (1.0 / (60 + b_rank))
            
        # Keep top candidates for the Reranker step (Increased to 100 for maximum depth)
        combined_list.sort(key=lambda x: x.metadata["rrf_score"], reverse=True)
        hybrid_results = combined_list[:100]

        # Merge with target files (search_type="filename_match")
        all_results.extend(hybrid_results)
        
        # 4. Negative Filtering (Post-retrieval)
        final_results = []
        ignore_terms = []
        
        lower_query = query.lower()
        if "ignore" in lower_query:
            parts = lower_query.split("ignore")
            if len(parts) > 1:
                potential_ignore = parts[1].split()[:3] 
                ignore_terms = [re.sub(r'[^\w]', '', t) for t in potential_ignore if len(t) > 3]

        for doc in all_results:
            source_lower = os.path.basename(doc.metadata.get("source", "")).lower()
            if any(term in source_lower for term in ignore_terms):
                continue
            final_results.append(doc)

        # Separate targeted files from general search to protect them from aggressive Reranking
        targeted_docs = [doc for doc in final_results if doc.metadata.get("search_type") == "filename_match"]
        general_docs_to_rerank = [doc for doc in final_results if doc.metadata.get("search_type") != "filename_match"]

        # 5. Reranking: direct CrossEncoder scoring for reliable relevance scores
        all_docs_to_rerank = targeted_docs + general_docs_to_rerank
        print(f"  > Reranking {len(all_docs_to_rerank)} total documents with CrossEncoder...")
        
        compressed_results = []
        if all_docs_to_rerank:
            reranker = get_reranker_model()
            # CrossEncoder uses the SHORT original query -- not the HyDE-enriched one
            query_for_reranker = rerank_query if rerank_query else query
            pairs = [(query_for_reranker, doc.page_content) for doc in all_docs_to_rerank]
            scores = reranker.predict(pairs).tolist()
            
            for doc, score in zip(all_docs_to_rerank, scores):
                # Boost for nomenclature/schema files to help them surface over generic manuals
                if doc.metadata.get("is_nomenclature"):
                    score += RERANKER_NOMENCLATURE_BOOST
                doc.metadata["relevance_score"] = score
            
            # Sort by score descending (CRITICAL: sort before deduplication)
            all_docs_to_rerank.sort(key=lambda d: d.metadata["relevance_score"], reverse=True)
            
        # 6. Final Selection & Source Diversification & Version Deduplication
        final_selection = []
        
        # Determine allowed sources (latest versions only)
        allowed_sources = set()
        if not include_all_versions:
            best_versions = {} # key: normalized -> (score, source_path)
            for doc in all_docs_to_rerank:
                source = doc.metadata.get("source", "Unknown")
                filename = os.path.basename(source)
                normalized = normalize_doc_name(filename)
                score = extract_version_score(filename)
                if normalized not in best_versions or score > best_versions[normalized][0]:
                    best_versions[normalized] = (score, source)
            allowed_sources = {v[1] for v in best_versions.values()}
        else:
            allowed_sources = {doc.metadata.get("source") for doc in all_docs_to_rerank}
            
        # Fill final_selection with SELECTIVE diversification:
        # - Technical files (schemas/nomenclatures) get up to 5 chunks (to cover all their pages)
        # - Generic docs (manuals, reports) get only 1 chunk to leave room for the technical files
        source_counts = {}
        TECHNICAL_TERMS = ["schéma", "schema", "nomenclature", "plan", "iomodule", "iocpu"]
        
        for doc in all_docs_to_rerank:
            if len(final_selection) >= n_results:
                break
            source = doc.metadata.get("source")
            if source not in allowed_sources:
                continue
            source_counts[source] = source_counts.get(source, 0) + 1
            # Selective quota: technical files (schemas/IO lists) get 5 chunks, generic docs get 1
            filename_low = os.path.basename(source or "").lower()
            is_technical = any(t in filename_low for t in TECHNICAL_TERMS)
            max_for_source = SEARCH_TECHNICAL_CHUNK_QUOTA if is_technical else SEARCH_GENERIC_CHUNK_QUOTA
            if source_counts[source] <= max_for_source:
                final_selection.append(doc)

        print(f"  > ----- RERANKER SCORES -----")
        for i, doc in enumerate(final_selection):
            score = doc.metadata.get("relevance_score", "N/A")
            source = os.path.basename(doc.metadata.get("source", "Unknown"))
            snippet = doc.page_content.replace('\n', ' ')[:50]
            print(f"  [{i+1}] Score: {score:.4f} | Source: {source}" if isinstance(score, float) else f"  [{i+1}] Score: {score} | Source: {source}")
            print(f"      Snippet: {snippet}...")
        print(f"  > -----------------------------")
        
        print(f"  > Total unique documents returned after Reranking: {len(final_selection)} (Filtered by version: {not include_all_versions})")
        return final_selection
        
    except Exception as e:
        print(f"Error during vector search: {e}")
        traceback.print_exc()
        return []
