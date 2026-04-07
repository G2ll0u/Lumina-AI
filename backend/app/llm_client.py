from __future__ import annotations
import os
from dotenv import load_dotenv
from typing import Any, Dict, List
import json
from typing import AsyncGenerator
import httpx
import ast
import re

load_dotenv()

# --- LLM Connection ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:11434")
LLM_API_KEY = os.getenv("LLM_API_KEY")
LLM_MODEL = os.getenv("LLM_MODEL", "mistral")

# --- Task-specific models (fall back to LLM_MODEL if not set) ---
CHAT_MODEL = os.getenv("CHAT_MODEL") or LLM_MODEL
DECOMPOSE_MODEL = os.getenv("DECOMPOSE_MODEL") or LLM_MODEL
HYDE_MODEL = os.getenv("HYDE_MODEL") or LLM_MODEL
VISION_MODEL = os.getenv("VISION_MODEL", "llava")

# --- LLM Inference parameters ---
LLM_NUM_CTX = int(os.getenv("LLM_NUM_CTX", "4096"))
LLM_NUM_PREDICT = int(os.getenv("LLM_NUM_PREDICT", "1024"))
HYDE_NUM_PREDICT = int(os.getenv("HYDE_NUM_PREDICT", "150"))
VISION_NUM_GPU = int(os.getenv("VISION_NUM_GPU", "0"))

# --- Timeouts (seconds) ---
LLM_STREAM_TIMEOUT = float(os.getenv("LLM_STREAM_TIMEOUT", "600.0"))
LLM_DECOMPOSE_TIMEOUT = float(os.getenv("LLM_DECOMPOSE_TIMEOUT", "15.0"))
LLM_HYDE_TIMEOUT = float(os.getenv("LLM_HYDE_TIMEOUT", "20.0"))
LLM_VISION_TIMEOUT = float(os.getenv("LLM_VISION_TIMEOUT", "120.0"))


class LLMError(RuntimeError):
    pass

async def stream_chat_completion(messages: List[Dict[str, str]], model_name: str | None = None, temperature: float | None = 0.1) -> AsyncGenerator[str, None]:
    """
    Calls a local LLM server in streaming mode (Ollama-compatible API).
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/api/chat"

    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    payload: Dict[str, Any] = {
        "model": model_name if model_name else CHAT_MODEL,
        "messages": messages,
        "stream": True,
        "options": {
            "temperature": temperature,
            "repeat_penalty": 1.0,
            "num_ctx": LLM_NUM_CTX,
            "num_predict": LLM_NUM_PREDICT,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_STREAM_TIMEOUT) as client:
            async with client.stream("POST", url, json=payload, headers=headers) as response:
                if response.status_code != 200:
                    error_text = await response.aread()
                    raise LLMError(f"LLM error {response.status_code}: {error_text.decode('utf-8')}")

                async for line in response.aiter_lines():
                    if not line:
                        continue

                    try:
                        # Ollama sends one JSON object per line
                        data = json.loads(line)
                        message = data.get("message") or {}
                        content = message.get("content", "")
                        if content:
                            yield content

                        if data.get("done"):
                            break
                    except json.JSONDecodeError as jde:
                        print(f"JSON Error on line (ignoring): {line} - Error: {jde}")
                        continue
                    except Exception as e:
                        print(f"Stream Error: {e}")
                        raise
    except httpx.RequestError as exc:
        raise LLMError(f"Cannot reach LLM server: {exc}") from exc

async def decompose_query(query: str, model_name: str | None = None) -> List[str]:
    """
    Asks the LLM to extract 1-3 key technical concepts from a question for document search.
    Returns a list of sub-queries, or the original query on failure.
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/api/chat"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    system_prompt = (
        "Ton but est d'extraire les 1 à 3 mots-clés techniques principaux de la question pour une recherche documentaire.\n"
        "CONSIGNES :\n"
        "1. Garde TOUJOURS les noms (ex: 'pompe', 'capteur', 'moteur'). Ne les remplace pas par des concepts généraux.\n"
        "2. Si la question est simple, renvoie juste le mot-clé principal.\n"
        "3. Ne change pas le sens de la question (ex: 'pompe installée' -> ['pompe']).\n"
        "Renvoie UNIQUEMENT un tableau JSON [\"mot1\", \"mot2\"]."
    )

    payload = {
        "model": model_name if model_name else DECOMPOSE_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Question : {query}\nFormat strict: [\"concept 1\", \"concept 2\"]"}
        ],
        "stream": False,
        "options": {
            "temperature": 0.0
        }
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_DECOMPOSE_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                content = data.get("message", {}).get("content", "[]")
                try:
                    # Extract list using regex to handle cases with text before/after the JSON array
                    match = re.search(r"\[\s*['\"].*['\"]\s*\]", content, re.DOTALL)
                    if match:
                        clean_content = match.group(0)
                        queries = ast.literal_eval(clean_content)
                        if isinstance(queries, list) and len(queries) > 0:
                            # Anti-drift check: ensure key technical terms are preserved
                            technical_terms = ["pompe", "moteur", "vitesse", "capteur", "température", "pression", "chauffage", "vidange"]
                            query_lower = query.lower()
                            present_tech = [t for t in technical_terms if t in query_lower]

                            if present_tech:
                                sub_queries_lower = " ".join(queries).lower()
                                if not any(t in sub_queries_lower for t in present_tech):
                                    print(f"  > [Decomposer] Drift detected! Term '{present_tech[0]}' missing. Falling back.")
                                    return [query]

                            # Post-filter: reject sub-queries that are too short (noise)
                            filtered = [str(q) for q in queries if len(str(q).split()) >= 2]
                            if not filtered:
                                filtered = [query]
                            # Cap at 3 sub-queries to avoid overwhelming the pipeline
                            return filtered[:3]
                except Exception as e:
                    print(f"  > [Decomposer] Failed to parse list: {content.strip()[:50]}... Error: {e}")
            return [query]
    except Exception as e:
        return [query]

async def generate_hyde_document(query: str, model_name: str | None = None) -> str:
    """
    HyDE (Hypothetical Document Embeddings): asks the LLM to generate a short
    hypothetical response to the query. This synthetic text is concatenated to the
    original query to bridge vocabulary gaps between the query and the corpus.
    Example: 'puissance electrique' <-> 'puissance installee : 119 kW'
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/api/chat"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    system_prompt = (
        "Tu es un expert en documentation technique industrielle. "
        "Génère EN MAXIMUM 2 PHRASES un extrait simulant une fiche technique ou notice de maintenance.\n"
        "L'extrait doit être factuel et utiliser le vocabulaire exact d'une notice (spécifications, repères, valeurs).\n"
        "EXEMPLE 1: 'Puissance installée : 45 kW. Tension alimentation : 400V AC triphasé.'\n"
        "EXEMPLE 2: 'Pompe de lavage (-11MP1) : Débit 15m3/h, Pression 3 bars. Pompe de vidange (-12MP1) installée en fond de cuve.'\n"
        "Donne directement l'extrait sans introduction."
    )
    payload = {
        "model": model_name if model_name else HYDE_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Question : {query}"}
        ],
        "stream": False,
        "options": {"temperature": 0.3, "num_predict": HYDE_NUM_PREDICT}
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_HYDE_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                hyde_text = data.get("message", {}).get("content", "").strip()
                if hyde_text:
                    print(f"  > [HyDE] Generated hypothetical doc: '{hyde_text[:80]}...'")
                    return hyde_text
    except Exception as e:
        print(f"  > [HyDE] Failed, continuing without: {e}")
    return ""


async def analyze_image_with_llava(prompt: str, base64_image: str) -> str:
    """
    Calls the local vision model (llava or compatible) to analyze a base64 image.
    """
    url = f"{LLM_BASE_URL.rstrip('/')}/api/generate"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if LLM_API_KEY:
        headers["Authorization"] = f"Bearer {LLM_API_KEY}"

    # Strip base64 prefix if sent as a Data URI from the frontend
    if "base64," in base64_image:
        base64_image = base64_image.split("base64,")[1]

    payload: Dict[str, Any] = {
        "model": VISION_MODEL,
        "prompt": prompt if prompt else "Décris cette image en détail.",
        "images": [base64_image],
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": LLM_NUM_PREDICT,
            "num_gpu": VISION_NUM_GPU
        }
    }

    try:
        async with httpx.AsyncClient(timeout=LLM_VISION_TIMEOUT) as client:
            response = await client.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                data = response.json()
                return data.get("response", "Sorry, could not analyze the image.")
            else:
                error_text = response.text
                print(f"  > [LLaVA] Error {response.status_code}: {error_text}")
                return "Error communicating with the vision model."
    except Exception as e:
        print(f"  > [LLaVA] API Error: {e}")
        return "Unexpected error during image analysis."
