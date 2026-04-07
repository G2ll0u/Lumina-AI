import os
import uuid
import tempfile
import re
import pytesseract
from langchain_community.document_loaders import UnstructuredPDFLoader, Docx2txtLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from dotenv import load_dotenv
load_dotenv()

# Tesseract configuration via environment variable
tesseract_path = os.getenv("TESSERACT_PATH", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
pytesseract.pytesseract.tesseract_cmd = tesseract_path
tesseract_dir = os.path.dirname(tesseract_path)
if tesseract_dir not in os.environ.get("PATH", ""):
    os.environ["PATH"] += os.pathsep + tesseract_dir
os.environ["TESSDATA_PREFIX"] = os.path.join(tesseract_dir, 'tessdata')

def extract_asset_id(file_path):
    """
    Extrait un ID machine à 4 chiffres depuis le chemin.
    Ex: '.../3967 - Name/...' -> '3967'
    """
    parts = file_path.split(os.sep)
    for part in parts:
        match = re.search(r'^(\d{4})\b', part)
        if match:
            return match.group(1)
    return "unknown"

st.set_page_config(page_title="ChromaDB Viewer", layout="wide")
st.title("Explorateur de ChromaDB")

# No "import collection"! The collection object will be passed as a parameter.

# --- LES SUPPRESSIONS ---
def delete_by_path(col, path: str):
    col.delete(where={"source": path})
    print(f"Documents de {path} supprimés !")

def delete_by_id(col, asset_id: str):
    col.delete(where={"asset_id": asset_id})
    print(f"Documents de la machine {asset_id} supprimés !")

# To delete everything, it is easier to drop the entire collection via the client
def delete_all(client, collection_name: str):
    client.delete_collection(name=collection_name)
    print(f"Collection {collection_name} intégralement détruite !")

# --- QUERIES (don't forget the RETURN!) ---
def get_by_path(col, path: str):
    return col.get(where={"source": path})

def get_by_id(col, asset_id: str):
    return col.get(where={"asset_id": asset_id})

def get_all(col):
    return col.get() # Warning, on a large volume, this can be heavy!

# --- ADD / UPDATE (different syntax from queries!) ---
# To add, you need the actual data, not a "where" clause!
def add_new_document(col, doc_id: str, text: str, source_path: str, asset_id: str):
    col.add(
        ids=[doc_id],
        documents=[text],
        metadatas=[{"source": source_path, "asset_id": asset_id}]
    )
    print(f"Document {doc_id} ajouté !")

def clean_text(text: str) -> str:
    """
    Nettoie le texte (suppression des caractères nuls, redondances)
    avant de l'injecter dans la base.
    """
    if not text:
        return ""
    text = text.encode('utf-8', 'ignore').decode('utf-8')
    text = text.replace("\x00", "")
    text = text.replace("\ufffd", "")
    text = text.replace("âž”", "->") 
    text = text.replace("ï¬", "fi")
    text = text.replace("ï¬‚", "fl")
    text = re.sub(r'\s+', ' ', text).strip()
    return text

# Connect to the background server!
try:
    client = chromadb.HttpClient(
        host=os.getenv("CHROMA_HOST", "localhost"),
        port=int(os.getenv("CHROMA_PORT", "8000"))
    )
    collections = client.list_collections()
    
    if collections:
        st.success(f"Connecté au serveur ! {len(collections)} collection(s) trouvée(s).")
        
        # Dropdown menu to select the collection
        col_names = [c.name for c in collections]
        selected_col = st.selectbox("Choisis une collection :", col_names)
        
        if selected_col:
            collection = client.get_collection(selected_col)
            
            # --- Display options as tabs ---
            tab_view, tab_search, tab_add, tab_delete = st.tabs([
                "Aperçu", "Rechercher", "Ajouter", "Supprimer"
            ])
            
            with tab_view:
                st.write(f"Aperçu des données dans **{selected_col}** :")
                limit = st.slider("Nombre de documents à afficher", 1, 1000, 10, key="limit_slider")
                results = collection.get(limit=limit)
                st.json(results)
                
            with tab_search:
                st.subheader("Rechercher des documents par métadonnée")
                search_type = st.radio("Critère de recherche", ["Source (Path)", "Asset ID"])
                search_query = st.text_input("Valeur à rechercher :", key="search_query")
                if st.button("Chercher"):
                    if search_query:
                        if search_type == "Source (Path)":
                            res = get_by_path(collection, search_query)
                        else:
                            res = get_by_id(collection, search_query)
                        st.write(f"Résultats de la recherche (Total: {len(res['ids']) if res and 'ids' in res else 0}):")
                        st.json(res)
                    else:
                        st.warning("Veuillez entrer une valeur à rechercher.")
                    
            with tab_add:
                st.subheader("Ajouter un nouveau document")
                add_mode = st.radio("Méthode d'ajout", ["Upload de Fichier (PDF/DOCX)", "Ingestion d'un Dossier Local", "Texte Brut"])
                
                if add_mode == "Texte Brut":
                    new_id = st.text_input("ID du document (unique) :", key="new_id")
                    new_text = st.text_area("Texte du document :", key="new_text")
                    new_source = st.text_input("Chemin source (métadonnée 'source') :", key="new_source")
                    new_asset_id = st.text_input("Asset ID (métadonnée 'asset_id') :", key="new_asset_id")
                    
                    if st.button("Ajouter le texte"):
                        if new_id and new_text:
                            try:
                                add_new_document(collection, new_id, new_text, new_source, new_asset_id)
                                st.success(f"Document {new_id} ajouté avec succès !")
                            except Exception as e:
                                st.error(f"Erreur lors de l'ajout : {e}")
                        else:
                            st.error("L'ID et le texte du document sont obligatoires.")
                            
                elif add_mode == "Ingestion d'un Dossier Local":
                    st.info("Cette méthode va scanner un dossier de votre machine, trouver les PDF/DOCX et les traiter avec les mêmes règles que l'ingestion principale (exclusions, HI-RES auto, ID Machine).")
                    folder_path = st.text_input("Chemin absolu du dossier à scanner :", key="folder_path")
                    
                    if st.button("Lancer l'ingestion du dossier"):
                        if not folder_path or not os.path.exists(folder_path):
                            st.error("Dossier invalide ou introuvable.")
                        else:
                            EXCLUDED_WORDS = ["hmi", "tia", "commercial", "quote", "offer", "certificat", "checklist", "check-list", "siemens", "s210", "1fk2", "instr"]
                            HI_RES_KEYWORDS = ["table", "troubleshoot", "dépannage", "alarm", "nomenclature", "schema", "schéma", "liste", "manual", "manuel"]
                            
                            files_to_process = []
                            for root, _, files in os.walk(folder_path):
                                for file in files:
                                    file_lower = file.lower()
                                    if file_lower.endswith((".pdf", ".docx")):
                                        if any(word in file_lower for word in EXCLUDED_WORDS):
                                            continue
                                        needs_hi_res = any(kw in file_lower for kw in HI_RES_KEYWORDS)
                                        files_to_process.append((os.path.join(root, file), needs_hi_res))
                            
                            if not files_to_process:
                                st.warning("Aucun fichier valide trouvé dans ce dossier.")
                            else:
                                st.write(f"{len(files_to_process)} fichier(s) trouvé(s). Début de l'ingestion...")
                                progress_bar = st.progress(0)
                                status_text = st.empty()
                                
                                success_count = 0
                                error_count = 0
                                
                                for i, (fpath, needs_hi_res) in enumerate(files_to_process):
                                    strat_name = "HI-RES" if needs_hi_res else "FAST"
                                    status_text.text(f"Traitement [{i+1}/{len(files_to_process)}] : {os.path.basename(fpath)} ({strat_name})...")
                                    
                                    try:
                                        docs = []
                                        fpath_str = str(fpath)
                                        
                                        if fpath_str.lower().endswith(".pdf"):
                                            loader = UnstructuredPDFLoader(
                                                fpath_str,
                                                mode="elements",
                                                strategy="hi_res" if needs_hi_res else "fast",
                                                languages=["fra", "eng"] if needs_hi_res else None
                                            )
                                            raw_docs = loader.load()
                                            
                                            combined_content = ""
                                            for el in raw_docs:
                                                if el.metadata.get("category") == "Table" and el.metadata.get("text_as_html"):
                                                    combined_content += "\n\n" + el.metadata["text_as_html"] + "\n\n"
                                                else:
                                                    combined_content += "\n" + el.page_content
                                            
                                            docs = [Document(page_content=combined_content, metadata={"source": fpath_str})]
                                            
                                        elif fpath_str.lower().endswith(".docx"):
                                            loader = Docx2txtLoader(fpath_str)
                                            docs = loader.load()
                                            for d in docs:
                                                d.metadata["source"] = fpath_str
                                        
                                        asset_id = extract_asset_id(fpath_str)
                                        for doc in docs:
                                            doc.page_content = clean_text(doc.page_content)
                                            doc.metadata["asset_id"] = asset_id
                                            
                                        text_splitter = RecursiveCharacterTextSplitter(
                                            chunk_size=1000,
                                            chunk_overlap=200,
                                            length_function=len,
                                            is_separator_regex=False,
                                        )
                                        chunks = text_splitter.split_documents(docs)
                                        
                                        if chunks:
                                            collection.add(
                                                ids=[str(uuid.uuid4()) for _ in chunks],
                                                documents=[c.page_content for c in chunks],
                                                metadatas=[c.metadata for c in chunks]
                                            )
                                        success_count += 1
                                    except Exception as e:
                                        st.error(f"âŒ Erreur sur {os.path.basename(fpath)} : {e}")
                                        error_count += 1
                                    
                                    progress_bar.progress((i + 1) / len(files_to_process))
                                
                                status_text.text("Ingestion terminée !")
                                st.success(f"Bilan : {success_count} fichiers ajoutés avec succès, {error_count} erreurs.")
                                
                else:
                    uploaded_file = st.file_uploader("Choisissez un fichier PDF ou DOCX", type=["pdf", "docx"], key="file_upload")
                    strategy = st.radio("Stratégie d'extraction (PDF uniquement)", ["FAST", "HI-RES"], help="HI-RES extrait mieux les tableaux et images, mais prend plus de temps.")
                    file_source = st.text_input("Chemin source (métadonnée 'source') :", value=uploaded_file.name if uploaded_file else "", key="file_source")
                    file_asset_id = st.text_input("Asset ID (métadonnée 'asset_id') :", value="unknown", key="file_mach")
                    
                    if st.button("Traiter et Ajouter le fichier"):
                        if uploaded_file:
                            try:
                                with st.spinner("Traitement du fichier, OCR et découpage en chunks. Cela peut prendre un certain temps..."):
                                    # Save to temp file
                                    with tempfile.NamedTemporaryFile(delete=False, suffix=f".{uploaded_file.name.split('.')[-1]}") as tmp_file:
                                        tmp_file.write(uploaded_file.getvalue())
                                        tmp_path = tmp_file.name
                                        
                                    docs = []
                                    if uploaded_file.name.lower().endswith(".pdf"):
                                        strat_mapped = "hi_res" if strategy == "HI-RES" else "fast"
                                        
                                        if strat_mapped == "hi_res":
                                            loader = UnstructuredPDFLoader(
                                                tmp_path,
                                                mode="elements",
                                                strategy=strat_mapped,
                                                languages=["fra", "eng"]
                                            )
                                        else:
                                            loader = UnstructuredPDFLoader(
                                                tmp_path,
                                                mode="elements",
                                                strategy=strat_mapped
                                            )
                                        
                                        raw_docs = loader.load()
                                        
                                        # Reconstruct document using text_as_html for tables
                                        combined_content = ""
                                        for el in raw_docs:
                                            if el.metadata.get("category") == "Table" and el.metadata.get("text_as_html"):
                                                combined_content += "\n\n" + el.metadata["text_as_html"] + "\n\n"
                                            else:
                                                combined_content += "\n" + el.page_content
                                        
                                        docs = [Document(page_content=combined_content, metadata={"source": file_source})]
                                        
                                    elif uploaded_file.name.lower().endswith(".docx"):
                                        loader = Docx2txtLoader(tmp_path)
                                        docs = loader.load()
                                        for d in docs:
                                            d.metadata["source"] = file_source
                                    
                                    # Clean and Split
                                    for doc in docs:
                                        doc.page_content = clean_text(doc.page_content)
                                        doc.metadata["asset_id"] = file_asset_id
                                        
                                    text_splitter = RecursiveCharacterTextSplitter(
                                        chunk_size=1000,
                                        chunk_overlap=200,
                                        length_function=len,
                                        is_separator_regex=False,
                                    )
                                    chunks = text_splitter.split_documents(docs)
                                    
                                    # Inject in Chroma
                                    ids = [str(uuid.uuid4()) for _ in chunks]
                                    documents_text = [c.page_content for c in chunks]
                                    metadatas = [c.metadata for c in chunks]
                                    
                                    if chunks:
                                        collection.add(
                                            ids=ids,
                                            documents=documents_text,
                                            metadatas=metadatas
                                        )
                                        st.success(f"Fichier {uploaded_file.name} ajouté avec succès ! ({len(chunks)} chunks générés)")
                                    else:
                                        st.warning("Aucun texte extrait du fichier.")
                                        
                                    # Cleanup
                                    os.unlink(tmp_path)
                            except Exception as e:
                                st.error(f"Erreur pendant l'ingestion : {e}")
                                if 'tmp_path' in locals() and os.path.exists(tmp_path):
                                    os.unlink(tmp_path)
                        else:
                            st.warning("Veuillez uploader un fichier.")
                        
            with tab_delete:
                st.subheader("Supprimer des documents ou la collection entière")
                del_type = st.selectbox("Que voulez-vous supprimer ?", ["Des documents (par Source)", "Des documents (par Asset ID)", "Toute la collection"], key="del_type")
                
                if del_type == "Des documents (par Source)":
                    del_path = st.text_input("Source à supprimer :", key="del_path")
                    if st.button("Supprimer par Source"):
                        if del_path:
                            try:
                                delete_by_path(collection, del_path)
                                st.success(f"Documents avec source={del_path} supprimés !")
                            except Exception as e:
                                st.error(f"Erreur lors de la suppression : {e}")
                        else:
                            st.warning("Veuillez entrer une valeur.")
                            
                elif del_type == "Des documents (par Asset ID)":
                    del_id = st.text_input("Asset ID à supprimer :", key="del_id")
                    if st.button("Supprimer par Asset ID"):
                        if del_id:
                            try:
                                delete_by_id(collection, del_id)
                                st.success(f"Documents avec asset_id={del_id} supprimés !")
                            except Exception as e:
                                st.error(f"Erreur lors de la suppression : {e}")
                        else:
                            st.warning("Veuillez entrer une valeur.")
                            
                else:
                    st.warning(f"Attention, vous allez détruire définitivement la collection **{selected_col}** !")
                    if st.button("Détruire la collection", type="primary"):
                        try:
                            delete_all(client, selected_col)
                            st.success(f"Collection {selected_col} détruite !")
                            st.rerun() # Reload the page to update the collection list
                        except Exception as e:
                            st.error(f"Erreur lors de la suppression de la collection : {e}")
    else:
        st.warning("Aucune collection trouvée. La base est vide !")
        
except Exception as e:
    st.error(f"Erreur de connexion : {e}")
