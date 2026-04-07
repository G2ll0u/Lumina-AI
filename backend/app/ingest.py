import os
import sys
import io
import glob
import re
import torch
import hashlib
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from dotenv import load_dotenv

os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
import logging
logging.getLogger("transformers").setLevel(logging.ERROR)

# Force UTF-8 for Windows console output (prevents cp1252 crashes on accented characters)
if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
if sys.stderr.encoding.lower() != 'utf-8':
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_chroma import Chroma
from langchain_community.document_loaders import Docx2txtLoader
import pytesseract
from pdf2image import convert_from_path
from PIL import Image
from langchain_community.document_loaders import UnstructuredPDFLoader
from langchain_core.documents import Document

load_dotenv()

# Configure Tesseract from environment variable (set TESSERACT_PATH in .env)
tesseract_path = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = tesseract_path

# Configure Tesseract for Unstructured by modifying system PATH and TESSDATA_PREFIX
tesseract_dir = os.path.dirname(tesseract_path)
if tesseract_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + tesseract_dir
os.environ["TESSDATA_PREFIX"] = os.path.join(tesseract_dir, 'tessdata')
import json


# Configuration
DOCS_PATH = os.getenv("DOCS_PATH")
CHROMA_PATH = os.path.join(os.path.dirname(__file__), "../chroma_db")
EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
TARGET_FOLDER = os.getenv("TARGET_FOLDER")

# Component extraction patterns (JSON dict: {"Label": "regex_pattern"})
# Example: {"Pump (MP)": "\\b\\d{2}MP\\d+[A-Z]*\\b", "Motor (M)": "\\b\\d{2}M\\d+[A-Z]*\\b"}
raw_patterns = os.getenv("COMPONENT_EXTRACTION_PATTERNS", "{}")
try:
    COMPONENT_EXTRACTION_PATTERNS = json.loads(raw_patterns)
except json.JSONDecodeError:
    print("Warning: COMPONENT_EXTRACTION_PATTERNS is not valid JSON. Disabled.")
    COMPONENT_EXTRACTION_PATTERNS = {}


def extract_component_summary(chunks: list, asset_id: str, source: str, is_latest: bool) -> list:
    """
    Scans all chunks of a document and extracts unique component codes
    using the regex patterns defined in COMPONENT_EXTRACTION_PATTERNS.
    Returns a list with one synthetic summary Document, or empty list if no patterns configured.
    """
    if not COMPONENT_EXTRACTION_PATTERNS:
        return []

    full_text = " ".join(chunk.page_content for chunk in chunks)
    found: dict[str, list[str]] = {}

    for label, pattern in COMPONENT_EXTRACTION_PATTERNS.items():
        try:
            matches = sorted(set(re.findall(pattern, full_text, re.IGNORECASE)))
            if matches:
                found[label] = matches
        except re.error as e:
            print(f"  > [COMPONENT_EXTRACT] Invalid regex for '{label}': {e}")

    if not found:
        return []

    filename = os.path.basename(source)
    lines = [f"[COMPOSANTS EXTRAITS - {filename} - Asset {asset_id}]"]
    for label, codes in found.items():
        lines.append(f"\n{label} ({len(codes)} unique) :")
        for code in codes:
            lines.append(f"  - {code}")
    lines.append(f"\nTotal categories: {len(found)}")

    summary_text = "\n".join(lines)
    summary_doc = Document(
        page_content=summary_text,
        metadata={
            "asset_id": asset_id,
            "source": source,
            "is_latest": is_latest,
            "is_component_summary": True,
            "document_scope": "machine",
        }
    )
    print(f"  > [COMPONENT_EXTRACT] Created summary chunk with {sum(len(v) for v in found.values())} codes across {len(found)} categories.")
    return [summary_doc]


# Parse list env vars from JSON format (e.g. ["word1", "word2"])
def parse_list_env(var_name: str) -> list:
    raw = os.getenv(var_name, "[]")
    try:
        parsed = json.loads(raw)
        return [str(item).lower() for item in parsed]
    except json.JSONDecodeError:
        print(f"Warning: Could not parse {var_name} as JSON list. Got: {raw}")
        return []

EXCLUDED_WORDS = parse_list_env("EXCLUDED_WORDS")
HI_RES_KEYWORDS = parse_list_env("HI_RES_KEYWORDS")

# Repetitive footer/header patterns to strip from PDFs (configured via FOOTER_PATTERNS in .env)
_FOOTER_PATTERNS = parse_list_env("FOOTER_PATTERNS")

def clean_text(text: str) -> str:
    """Clean text by stripping repetitive footers, control characters and OCR noise."""
    # Strip repetitive footers/headers
    for pattern in _FOOTER_PATTERNS:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
    # OCR checkbox symbols
    text = re.sub(r'[☐☑☒☚☛□■▪]', '', text)
    # Long runs of repeated special characters
    text = re.sub(r'_{3,}', '', text)
    text = re.sub(r'\*{3,}', '', text)
    text = re.sub(r'-{4,}', '', text)
    # Collapse excessive blank lines
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()
def get_file_hash(filepath: str) -> str:
    """
    Computes a SHA-256 hash of the file contents.
    This acts as a unique fingerprint to prevent re-ingesting duplicate files.
    """
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read and update hash in chunks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def html_table_to_markdown(html: str) -> str:
    """
    Converts an HTML table string extracted by Unstructured into a clean Markdown table.
    Falls back to the raw text if parsing fails.
    """
    try:
        # Remove all attributes from tags for cleaner parsing
        html_clean = re.sub(r'<(\w+)[^>]*>', r'<\1>', html)
        
        rows = re.findall(r'<tr>(.*?)</tr>', html_clean, re.DOTALL | re.IGNORECASE)
        if not rows:
            return html
        
        md_rows = []
        for i, row_html in enumerate(rows):
            cells = re.findall(r'<t[dh]>(.*?)</t[dh]>', row_html, re.DOTALL | re.IGNORECASE)
            # Clean cell content: strip whitespace and remove remaining nested tags
            cells = [re.sub(r'<[^>]+>', '', c).strip() for c in cells]
            cells = [' '.join(c.split()) for c in cells]  # Normalize inner whitespace
            if not cells:
                continue
            md_rows.append('| ' + ' | '.join(cells) + ' |')
            if i == 0:  # Add Markdown separator after the header row
                md_rows.append('| ' + ' | '.join(['---'] * len(cells)) + ' |')
        
        return '\n'.join(md_rows) if md_rows else html
    except Exception:
        return html  # Graceful fallback

def extract_asset_id(file_path):
    """
    Extracts a 4-digit machine ID from the file path.
    Assumes structure like '.../3967 - Name/...'
    Returns "unknown" if not found.
    """
    # Look for a directory component that starts with 4 digits
    parts = file_path.split(os.sep)
    for part in parts:
        match = re.search(r'^(\d{4})\b', part)
        if match:
            return match.group(1)
    return "unknown"

def clean_text(text: str) -> str:
    
    # Cleans text to remove encoding artifacts while preserving French accents.
    if not text:
        return ""
    
    # Force valid UTF-8 by stripping surrogates/invalid bytes
    text = text.encode('utf-8', 'ignore').decode('utf-8')
    
    # Replace null bytes and common artifacts
    text = text.replace("\x00", "")
    text = text.replace("\ufffd", "") # Remove replacement character

    # Remove OCR checkbox symbols
    text = re.sub(r'[☐☑☒☚☛□■▪]', '', text)
    # Remove repeated underscores
    text = re.sub(r'_{3,}', '', text)
    # Collapse repeated newlines
    text = re.sub(r'\n{3,}', '\n\n', text)


    # Normalize special characters that might confuse the model
    text = text.replace("âž”", "->") 
    text = text.replace("ï¬", "fi")
    text = text.replace("ï¬‚", "fl")
    
    # Normalize whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def normalize_doc_name(filename: str) -> str:
    """
    Strips extension, version markers and common suffixes to create a
    grouping key (i.e. two versions of the same doc get the same key).
    """
    name = os.path.splitext(filename)[0].lower()
    # Remove numeric versions: V1.0, v2, V1.1.2 ...
    name = re.sub(r'[_\-\s]?v\d+(?:\.\d+)*', '', name)
    # Remove common textual version markers
    for marker in ['final', 'ok', 'signe', 'signé', 'rev', 'version', 'copie', 'copy']:
        name = re.sub(rf'[_\-\s]?{marker}\d*', '', name)
    # Remove trailing single letter version (e.g. _A, _B, -C)
    name = re.sub(r'[_\-\s][a-z]$', '', name)
    # Collapse whitespace
    name = re.sub(r'[\s_\-]+', '_', name).strip('_')
    return name


def extract_version_score(filename: str, mtime: float) -> tuple:
    """
    Returns a sortable tuple for version comparison. Higher = more recent.
    Priority:
      3 â†’ Numeric version found (V1.2, v2.0 ...)
      2 â†’ Single letter version found (_A, _B ...)
      1 â†’ Fallback to file mtime
    """
    name = os.path.splitext(filename)[0].lower()

    # Priority 3: Numeric version Vx.x
    match = re.search(r'v(\d+)(?:\.(\d+))?(?:\.(\d+))?', name)
    if match:
        major = int(match.group(1))
        minor = int(match.group(2) or 0)
        patch = int(match.group(3) or 0)
        return (3, major * 10000 + minor * 100 + patch, 0)

    # Priority 2: Single letter suffix _A, _B, -C (not part of a word)
    match = re.search(r'(?:^|[_\-\s])([a-z])(?:\.|$)', name)
    if match:
        return (2, ord(match.group(1)) - ord('a'), 0)

    # Priority 1: Fallback on mtime
    return (1, 0, mtime)


def compute_latest_flags(files_to_process: list) -> dict:
    """
    Groups files by (parent_directory, normalized_base_name) and determines
    which file is considered the latest version.
    Returns a dict: {filepath -> is_latest (bool)}
    """
    groups: dict = {}  # key -> list of (score_tuple, filepath)

    for file_path, _ in files_to_process:
        filename = os.path.basename(file_path)
        parent = os.path.dirname(file_path)
        mtime = os.path.getmtime(file_path)
        normalized = normalize_doc_name(filename)
        key = (parent, normalized)
        score = extract_version_score(filename, mtime)
        groups.setdefault(key, []).append((score, file_path))

    result = {}
    for group_files in groups.values():
        # Sort descending -- highest score = latest version
        group_files.sort(key=lambda x: x[0], reverse=True)
        latest_path = group_files[0][1]
        for _, path in group_files:
            result[path] = (path == latest_path)
            if len(group_files) > 1:
                status = "LATEST" if path == latest_path else "older"
                print(f"  [version] {status}: {os.path.basename(path)}")

    return result

def main():
    print(f"\n--- DIAGNOSTIC MATÉRIEL ---")
    print(f"PyTorch version: {torch.__version__} | CUDA: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU Détecté par PyTorch : {torch.cuda.get_device_name(0)}")
        
    try:
        import onnxruntime as ort
        print(f"ONNXRuntime version: {ort.__version__}")
        providers = ort.get_available_providers()
        print(f"ONNX Providers : {providers}")
        if 'CUDAExecutionProvider' in providers:
            print("=> Accélération matérielle ONNX (Unstructured) ACTIVE")
    except ImportError:
        pass
    print(f"---------------------------\n")

    parser = argparse.ArgumentParser(description='Ingest documents into ChromaDB.')
    parser.add_argument('--target', type=str, default="", help='Specific machine folder to target (e.g. "3986 - IC3").')
    args = parser.parse_args()

    if not DOCS_PATH or not os.path.exists(DOCS_PATH):
        print(f"Error: DOCS_PATH is not set or does not exist: {DOCS_PATH}")
        return

    # Determine scan path:
    # If --target is provided, build path: DOCS_PATH / target / TARGET_FOLDER
    if args.target.strip() and args.target.strip() != "racine":
        scan_path = os.path.join(DOCS_PATH, args.target.strip(), TARGET_FOLDER)
        print(f"SCAN CIBLÉ ACTIVÉ: Injection directe sur {scan_path}")
    else:
        scan_path = DOCS_PATH
        print(f"Scanning for PDFs globally in {scan_path}...")
    
    documents = []

    
    # Temporary: process only this specific file
    # TARGET_FILE_ONLY = "3967 - MB13 - ADIMA AEROSPACE/08-NMR/Notice de mise en service - 3967 V1.2.pdf"

    # Walk through the directory to find PDFs and Word docs
    files_to_process = []
    try:
        files_to_process.append((os.path.join(DOCS_PATH, TARGET_FILE_ONLY), True))
    except:
        # The target folder does not exist (e.g. new machine not yet on disk)
        if not os.path.exists(scan_path):
            print(f"Le dossier cible n'existe pas: {scan_path}")
            print(f"Aucun document trouvé pour la cible spécifiée.")
            return

        for root, dirs, files in os.walk(scan_path):
            # Only process files inside the TARGET_FOLDER subfolder
            if TARGET_FOLDER in root: 
                for file in files:
                    file_lower = file.lower()
                    # Exclure les fichiers temporaires Word (~$) et copies
                    if file.startswith("~$"):
                        print(f"Skipping temp Word file: {file}")
                        continue
                    if file_lower.endswith((".pdf", ".docx")):
                        if any(word in file_lower for word in EXCLUDED_WORDS):
                            print(f"Skipping excluded file: {file}")
                            continue
                        # Tag metadata for extraction strategy
                        needs_hi_res = any(kw in file_lower for kw in HI_RES_KEYWORDS)
                        files_to_process.append((os.path.join(root, file), needs_hi_res))
    
    # --- DEDUP: If a file exists as both DOCX and PDF (same stem), keep only the DOCX ---
    grouped_by_stem: dict = {}
    for fp, hi_res in files_to_process:
        stem = os.path.splitext(os.path.basename(fp))[0].lower()
        ext = os.path.splitext(fp)[1].lower()
        key = (os.path.dirname(fp), stem)
        if key not in grouped_by_stem:
            grouped_by_stem[key] = []
        grouped_by_stem[key].append((fp, hi_res, ext))
    
    deduped_files = []
    for key, entries in grouped_by_stem.items():
        if len(entries) > 1:
            # Prefer DOCX over PDF if both exist for the same stem
            docx_entries = [e for e in entries if e[2] == ".docx"]
            if docx_entries:
                print(f"Dedup: keeping DOCX, skipping PDF(s) for {os.path.basename(docx_entries[0][0])}")
                deduped_files.extend([(fp, hr) for fp, hr, _ in docx_entries])
            else:
                deduped_files.extend([(fp, hr) for fp, hr, _ in entries])
        else:
            deduped_files.extend([(fp, hr) for fp, hr, _ in entries])
    
    files_to_process = deduped_files
    
    print(f"Found {len(files_to_process)} documents.")
    for fp, _ in files_to_process:
        print(f"  - {os.path.basename(fp)}")
    
    if not files_to_process:
        print("No documents to ingest.")
        return

    # --- VERSIONING: compute is_latest flags for all files BEFORE ingestion ---
    print("Computing version flags (is_latest)...")
    latest_flags = compute_latest_flags(files_to_process)

    # Initialize text splitter, embeddings and vector store ONCE before the loop
    # --- OPTIMIZATION MAXIMALE: Dédoublonnage RAPIDE sans charger PyTorch ---
    print("Vérification rapide des doublons dans ChromaDB...")
    try:
        # Lightweight init without embedding model -- just to query existing metadata
        vstore_lite = Chroma(persist_directory=CHROMA_PATH)
        
        new_files_to_process = []
        for file_item in files_to_process:
            file_path, needs_hi_res = file_item
            asset_id = extract_asset_id(file_path)
            file_hash = get_file_hash(file_path)
            
            existing_docs = vstore_lite.get(
                where={
                    "$and": [
                        {"file_hash": file_hash},
                        {"asset_id": asset_id}
                    ]
                }
            )
            if existing_docs and len(existing_docs.get("ids", [])) > 0:
                print(f"SKIPPED {os.path.basename(file_path)} : Exactly identical file already ingested.")
            else:
                new_files_to_process.append(file_item)
                
        files_to_process = new_files_to_process
    except Exception as e:
        print(f"Erreur lors de la vérification rapide des doublons: {e}")
        pass

    if not files_to_process:
        print("\nTous les documents sont déjà à jour ! Aucun nouveau contenu à ingérer.")
        return

    # --- OPTIMIZATION 1: batch_size=16 to protect GTX 1650 Ti's 4GB VRAM ---
    print("\nNouveaux documents détectés. Initializing heavy embedding model...")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    embeddings = HuggingFaceEmbeddings(
        model_name=EMBEDDING_MODEL_NAME,
        model_kwargs={'device': device},
        encode_kwargs={'batch_size': 16}  # Safe for 4GB VRAM
    )
    vector_store = Chroma(persist_directory=CHROMA_PATH, embedding_function=embeddings)
    
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=1000,
        chunk_overlap=200,
        length_function=len,
        separators=["\n\n\n", "\n\n", "\n", " ", ""],
    )
    
    total_chunks_added = 0
    
    # Load, split and embed documents FILE BY FILE
    # --- OPTIMIZATION 3: per-file ingestion to avoid accumulating all docs in RAM ---
    for i, file_item in enumerate(files_to_process):
        try:
            # Unpack the tuple
            file_path, needs_hi_res = file_item
            strategy_name = "HI-RES" if needs_hi_res else "FAST"
            
            # Extract machine ID for metadata enrichment
            asset_id = extract_asset_id(file_path)
            file_hash = get_file_hash(file_path)

            print(f"[{i+1}/{len(files_to_process)}] Loading {os.path.basename(file_path)} [{strategy_name}] at {datetime.now().strftime('%H:%M:%S')}...")
            
            docs = []
            file_path_str = str(file_path)
            if file_path_str.lower().endswith(".pdf"):
                if needs_hi_res:
                    loader = UnstructuredPDFLoader(
                        file_path,
                        mode="elements",
                        strategy="hi_res",
                        pdf_infer_table_structure=True,
                        languages=["fra", "eng"]
                    )
                else:
                    loader = UnstructuredPDFLoader(
                        file_path,
                        mode="elements",
                        strategy="fast"
                    )
                raw_elements = loader.load()
                
                # --- STRUCTURE-PRESERVING CHUNKING ---
                # Instead of merging everything into a blob, we group elements
                # by logical section (a title + its following paragraphs).
                # Tables are kept as isolated, self-contained chunks.
                current_section_title = ""
                current_section_text = ""
                
                for el in raw_elements:
                    category = el.metadata.get("category", "")
                    content = el.page_content.strip()
                    
                    if not content:
                        continue

                    if category == "Table":
                        # 1. Flush current section before the table
                        if current_section_text.strip():
                            docs.append(Document(
                                page_content=clean_text(current_section_text.strip()),
                                metadata={"source": file_path, "section_title": current_section_title}
                            ))
                            current_section_text = ""
                        
                        # 2. Create an isolated chunk for the table itself using Markdown
                        # Prefix with the section title for context
                        table_html = el.metadata.get("text_as_html", content)
                        table_markdown = html_table_to_markdown(table_html)
                        table_chunk_content = f"[Section: {current_section_title}]\n{table_markdown}" if current_section_title else table_markdown
                        docs.append(Document(
                            page_content=clean_text(table_chunk_content),
                            metadata={"source": file_path, "element_type": "table"}
                        ))
                    
                    elif category in ("Title", "Header"):
                        # 3. A new title = flush previous section
                        if current_section_text.strip():
                            docs.append(Document(
                                page_content=clean_text(current_section_text.strip()),
                                metadata={"source": file_path, "section_title": current_section_title}
                            ))
                        # Start a fresh section
                        current_section_title = content
                        current_section_text = f"# {content}\n"
                    
                    else:
                        # 4. Normal text: append to current section
                        current_section_text += content + "\n"
                
                # Flush the last section
                if current_section_text.strip():
                    docs.append(Document(
                        page_content=clean_text(current_section_text.strip()),
                        metadata={"source": file_path, "section_title": current_section_title}
                    ))
                
                # --- OPTIMIZATION 2: Parallel OCR using i7 threads ---
                total_text_len = sum(len(d.page_content) for d in docs)
                if total_text_len < 100:
                    print(f"  > Low text content ({total_text_len} chars). Attempting Parallel OCR...")
                    try:
                        poppler_path = os.path.join(os.path.dirname(__file__), "..", "poppler", "poppler-24.08.0", "Library", "bin")
                        images = convert_from_path(file_path, poppler_path=poppler_path)
                        
                        def ocr_page(img):
                            return pytesseract.image_to_string(img, lang='fra+eng')
                        
                        ocr_text = ""
                        with ThreadPoolExecutor(max_workers=4) as executor:
                            futures = {executor.submit(ocr_page, img): idx for idx, img in enumerate(images)}
                            results = {}
                            for future in as_completed(futures):
                                results[futures[future]] = future.result()
                            for idx in sorted(results):
                                ocr_text += results[idx] + "\n"
                        
                        if len(ocr_text.strip()) > 0:
                            docs = [Document(page_content=ocr_text, metadata={"source": file_path})]
                            print(f"  > OCR successful ({len(images)} pages in parallel). Extracted {len(ocr_text)} chars.")
                    except Exception as ocr_err:
                        print(f"  > OCR failed: {ocr_err}")
                
            elif file_path_str.lower().endswith(".docx"):
                loader = Docx2txtLoader(file_path)
                docs = loader.load()
            else:
                continue
                
            # Add machine metadata + versioning + document scope
            is_latest = latest_flags.get(file_path, True)  # default True if not grouped
            # Detect document scope: component docs live in a subfolder of the machine folder
            path_parts = file_path.replace("\\", "/").lower()
            doc_scope = "component" if "documentation composants" in path_parts or "documentation_composants" in path_parts else "machine"
            
            for doc in docs:
                doc.metadata["asset_id"] = asset_id
                doc.metadata["source"] = file_path
                doc.metadata["file_hash"] = file_hash
                doc.metadata["is_latest"] = is_latest
                doc.metadata["document_scope"] = doc_scope
                doc.page_content = clean_text(doc.page_content)

            # --- OPTIMIZATION 3: Split and embed immediately, don't accumulate in RAM ---
            chunks = text_splitter.split_documents(docs)
            
            # --- SECTION TITLE RE-INJECTION ---
            # After splitting, sub-chunks may lose the section title (only the first chunk kept it).
            # We re-inject the title as a prefix to maintain searchability and context.
            for chunk in chunks:
                section_title = chunk.metadata.get("section_title", "")
                if section_title and not chunk.page_content.startswith(f"# {section_title}"):
                    chunk.page_content = f"[Section: {section_title}]\n{chunk.page_content}"
            
            if chunks:
                # --- COMPONENT EXTRACTION: create a synthetic summary chunk ---
                summary_chunks = extract_component_summary(
                    chunks, asset_id, str(file_path), is_latest
                )
                all_new_chunks = chunks + summary_chunks
                vector_store.add_documents(all_new_chunks)
                total_chunks_added += len(all_new_chunks)
                print(f"  > Added {len(all_new_chunks)} chunks to ChromaDB (total: {total_chunks_added})")
            
        except Exception as e:
            print(f"Error loading {file_path}: {e}")

    print(f"\nIngestion complete! {total_chunks_added} total chunks indexed.")

if __name__ == "__main__":
    main()
