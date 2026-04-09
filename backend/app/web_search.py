from duckduckgo_search import DDGS

def search_web_duckduckgo(query: str, max_results: int = 3) -> str:
    """
    Performs a web search using DuckDuckGo and returns a formatted string
    of the top results. Used when the local RAG doesn't have the answer
    or needs external context.
    """
    try:
        results = ""
        # The DDGS context manager handles the session
        with DDGS() as ddgs:
            # We use text search, getting up to max_results
            search_results = list(ddgs.text(query, max_results=max_results))
            
            if not search_results:
                return "Aucun résultat trouvé sur Internet pour cette requête."
                
            for i, res in enumerate(search_results):
                title = res.get('title', 'Sans titre')
                body = res.get('body', '')
                href = res.get('href', '')
                
                results += f"[{i+1}] {title}\n"
                results += f"Extrait: {body}\n"
                results += f"Source: {href}\n\n"
                
        return results.strip()
    except Exception as e:
        print(f"Error during DuckDuckGo web search: {e}")
        return f"Erreur lors de la recherche DuckDuckGo : {str(e)}"
