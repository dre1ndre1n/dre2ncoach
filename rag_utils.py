import os
import glob
import streamlit as st
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

PINECONE_INDEX_NAME = "dre2ncoach"
EMBEDDING_MODEL = "all-MiniLM-L6-v2"
EMBEDDING_DIMENSION = 384

def get_pinecone_api_key():
    """Retrieve the Pinecone API Key from environment or Streamlit secrets."""
    if hasattr(st, "secrets") and "PINECONE_API_KEY" in st.secrets:
        return st.secrets["PINECONE_API_KEY"]
    return os.environ.get("PINECONE_API_KEY")

def get_pinecone_client():
    """Get authenticated Pinecone client."""
    api_key = get_pinecone_api_key()
    if not api_key:
        return None
    return Pinecone(api_key=api_key)

def get_local_pdf_files(base_dir=None):
    """
    Finds all PDF files in the project folder and subfolders (like knowledge_base/).
    Returns a list of dicts with file metadata.
    """
    if base_dir is None:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        
    pdf_files = []
    # Search root and any subfolder
    for root, _, files in os.walk(base_dir):
        # Skip virtualenvs or git or caches
        if any(ignored in root for ignored in [".git", "__pycache__", ".venv", "venv", ".devcontainer"]):
            continue
        for f in files:
            if f.lower().endswith(".pdf"):
                full_path = os.path.join(root, f)
                size_mb = os.path.getsize(full_path) / (1024 * 1024)
                pdf_files.append({
                    "name": f,
                    "path": full_path,
                    "size_mb": round(size_mb, 2)
                })
    return pdf_files

def get_index_stats():
    """
    Retrieves statistics about the Pinecone index (e.g. vector count).
    """
    pc = get_pinecone_client()
    if not pc:
        return {"status": "no_key", "vector_count": 0}
        
    try:
        existing_indexes = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing_indexes:
            return {"status": "not_created", "vector_count": 0}
            
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        total_vectors = stats.get("total_vector_count", 0)
        return {
            "status": "ready",
            "vector_count": total_vectors,
            "dimension": stats.get("dimension", EMBEDDING_DIMENSION)
        }
    except Exception as e:
        return {"status": "error", "error": str(e), "vector_count": 0}

def ensure_pinecone_index(pc):
    """
    Ensures that the Pinecone index exists with the right configuration.
    """
    try:
        existing_indexes = [idx.name for idx in pc.list_indexes()]
        if PINECONE_INDEX_NAME not in existing_indexes:
            # Create serverless index
            pc.create_index(
                name=PINECONE_INDEX_NAME,
                dimension=EMBEDDING_DIMENSION,
                metric="cosine",
                spec=ServerlessSpec(cloud="aws", region="us-east-1")
            )
        return True
    except Exception as e:
        print(f"Index creation warning/error: {e}")
        return True

def index_pdf_file_paths(file_paths, progress_callback=None):
    """
    Loads specified PDF file paths, chunks them, and uploads embeddings to Pinecone in batches.
    file_paths: list of absolute or relative file paths.
    progress_callback: optional callable(current_file_idx, total_files, file_name, status_message)
    """
    if not file_paths:
        return False, "Nessun file PDF specificato."
        
    pc = get_pinecone_client()
    if not pc:
        return False, "Pinecone API Key mancante. Inseriscila nelle impostazioni o nei Secrets."
        
    ensure_pinecone_index(pc)
    
    embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    
    total_files = len(file_paths)
    all_splits = []
    
    for idx, path in enumerate(file_paths):
        file_name = os.path.basename(path)
        if progress_callback:
            progress_callback(idx, total_files, file_name, f"Lettura e suddivisione in corso ({idx+1}/{total_files})...")
            
        try:
            loader = PyPDFLoader(path)
            docs = loader.load()
            splits = text_splitter.split_documents(docs)
            for split in splits:
                split.metadata["source_book"] = file_name
            all_splits.extend(splits)
        except Exception as e:
            print(f"Errore caricamento PDF {file_name}: {e}")
            if progress_callback:
                progress_callback(idx, total_files, file_name, f"Errore su {file_name}: {e}")
                
    if not all_splits:
        return False, "Nessun contenuto estratto dai PDF."
        
    # Batch upsert to Pinecone to prevent payload limits
    BATCH_SIZE = 100
    total_splits = len(all_splits)
    
    try:
        vectorstore = PineconeVectorStore(index_name=PINECONE_INDEX_NAME, embedding=embeddings)
        
        for i in range(0, total_splits, BATCH_SIZE):
            batch = all_splits[i:i + BATCH_SIZE]
            if progress_callback:
                pct = int((i / total_splits) * 100)
                progress_callback(
                    total_files, total_files, "Pinecone", 
                    f"Caricamento vettori su Pinecone: {min(i + BATCH_SIZE, total_splits)}/{total_splits} chunks ({pct}%)..."
                )
            vectorstore.add_documents(batch)
            
        if progress_callback:
            progress_callback(total_files, total_files, "Completato", f"Indicizzazione completata! {total_splits} estratti caricati.")
            
        return True, f"Indicizzazione completata con successo! {total_splits} sezioni salvate nella libreria permanente."
    except Exception as e:
        return False, f"Errore durante l'upsert su Pinecone: {e}"

def build_rag_index_from_local_files(progress_callback=None):
    """
    Scans the project directory for all local PDFs and indexes them into Pinecone.
    """
    local_files = get_local_pdf_files()
    if not local_files:
        return False, "Nessun file PDF trovato nella cartella del progetto."
    file_paths = [f["path"] for f in local_files]
    return index_pdf_file_paths(file_paths, progress_callback=progress_callback)

def build_rag_index(uploaded_pdfs):
    """
    Backward compatible helper for uploaded PDF files from Streamlit file uploader.
    """
    if not uploaded_pdfs:
        return False
        
    import tempfile
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_paths = []
        for uploaded_file in uploaded_pdfs:
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            temp_paths.append(temp_path)
            
        success, _ = index_pdf_file_paths(temp_paths)
        return success

def query_rag(query, k=4):
    """
    Queries the Pinecone index and returns relevant context with source citations.
    """
    pc = get_pinecone_client()
    if not pc:
        return ""
        
    try:
        embeddings = HuggingFaceEmbeddings(model_name=EMBEDDING_MODEL)
        vectorstore = PineconeVectorStore(index_name=PINECONE_INDEX_NAME, embedding=embeddings)
        docs = vectorstore.similarity_search(query, k=k)
        
        if not docs:
            return ""
            
        context = "\n\n--- Principi Scientifici e Manuali di Triathlon (Knowledge Base) ---\n"
        for i, doc in enumerate(docs):
            source = doc.metadata.get("source_book") or os.path.basename(doc.metadata.get("source", "Manuale"))
            page = doc.metadata.get("page", "")
            page_info = f" (pag. {page + 1})" if isinstance(page, int) else ""
            context += f"[Fonte: {source}{page_info}]:\n{doc.page_content.strip()}\n\n"
        return context
    except Exception as e:
        print(f"RAG Error: {e}")
        return ""
