
import os
import glob
import difflib
from typing import List
from dotenv import load_dotenv

load_dotenv()

# Max number of matching files returned by a filename search
SEARCH_MAX_FILES = int(os.getenv("SEARCH_MAX_FILES", "10"))

def search_docs(query: str, available_sources: List[str] = None) -> List[str]:
    """
    Search for PDF and Word documents in DOCS_PATH or from a predefined list that match the query.
    Uses simple filename similarity matching with priorities.
    """
    if available_sources is None:
        docs_path = os.getenv("DOCS_PATH")
        if not docs_path or not os.path.exists(docs_path):
            print("Warning: DOCS_PATH not set or does not exist.")
            return []
            
        available_sources = []
        for root, dirs, files in os.walk(docs_path):
            for file in files:
                if file.lower().endswith((".pdf", ".docx")):
                    available_sources.append(os.path.join(root, file))

    if not available_sources:
        return []

    # 1. Normalize query
    import re
    # Remove punctuation for better matching
    clean_query = re.sub(r'[^\w\s]', '', query).lower()
    query_tokens = clean_query.split()
    
    # Add translation equivalences for fuzzy matching
    synonyms = {
        "manuel": "manual",
        "manual": "manuel",
        "schema": "schéma",
        "schéma": "schema"
    }
    expanded_tokens = []
    for t in query_tokens:
        expanded_tokens.append(t)
        if t in synonyms:
            expanded_tokens.append(synonyms[t])
            
    query_numbers = [t for t in expanded_tokens if any(c.isdigit() for c in t)]

    # 2. Find all matching files and score them
    scored_files = []
    
    for full_path in available_sources:
        filename = os.path.basename(full_path).lower()
        
        score = 0
        
        # Count matching tokens
        matches = 0
        for token in set(expanded_tokens):
            # Ignore tiny connector words that create false positives
            if len(token) <= 2 and not token.isdigit():
                continue
                
            if token in filename:
                if token.isdigit() and len(token) >= 3:
                    score += 100 # Huge boost for machine IDs
                else:
                    score += 15
                matches += 1
        
        # Boost for consecutive matches (phrase partial match)
        if matches > 1:
            score += matches * 20
        
        if "ignore" in query.lower() and "implantation" in query.lower():
             if "implantation" in filename:
                 score -= 1000

        # Heuristics: Prioritize manuals OVER drawings
        priority_terms = ["notice", "manuel", "manual", "instruction", "maintenance", "ba7", "mb13", "nomenclature"]
        is_manual = any(t in filename for t in priority_terms)
        if is_manual:
             # Only boost manual if it's potentially for the right machine
             # or if no machine number was in the query
             if not query_numbers or any(num in filename for num in query_numbers):
                score += 50
             else:
                score -= 30 # Deprioritize generic manuals for WRONG machines
            
        # Extra boost if the user is asking for troubleshooting and it's a manual
        troubleshooting_terms = ["défaut", "defaut", "alerte", "erreur", "panne", "alarme", "fault", "warning"]
        if is_manual and any(t in clean_query for t in troubleshooting_terms):
            score += 50
        
        # Strategy for drawings and schemas
        low_priority_terms = ["implantation", "plan", "schéma", "schema"]
        if any(t in filename for t in low_priority_terms):
            # If the user asks "how many" or "list", schemas are CRITICAL.
            # Give them a boost instead of a penalty.
            if any(t in clean_query for t in ["combien", "liste", "nombre", "how many"]):
                score += 60 # Boost for quantity questions
            elif not any(t in query.lower() for t in low_priority_terms):
                score -= 80 # Penalty otherwise
        
        if score > 0:
            scored_files.append((score, full_path))
    
    if not scored_files:
        return []
        
    # Sort by score descending and return top N files
    scored_files.sort(key=lambda x: x[0], reverse=True)
    return [path for score, path in scored_files[:SEARCH_MAX_FILES]]
