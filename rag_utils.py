import os
import tempfile
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS

INDEX_PATH = "faiss_index"

def build_rag_index(uploaded_pdfs):
    """
    Takes a list of uploaded PDF files from Streamlit, processes them,
    and builds/updates a local FAISS vector store.
    """
    if not uploaded_pdfs:
        return False
        
    docs = []
    
    # Save uploaded files temporarily so PyPDFLoader can read them
    with tempfile.TemporaryDirectory() as temp_dir:
        for uploaded_file in uploaded_pdfs:
            temp_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
                
            loader = PyPDFLoader(temp_path)
            docs.extend(loader.load())
            
    if not docs:
        return False

    text_splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    splits = text_splitter.split_documents(docs)
    
    embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
    
    # Check if index already exists
    if os.path.exists(INDEX_PATH):
        vectorstore = FAISS.load_local(INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
        vectorstore.add_documents(splits)
    else:
        vectorstore = FAISS.from_documents(splits, embeddings)
        
    vectorstore.save_local(INDEX_PATH)
    return True

def query_rag(query, k=3):
    """
    Queries the local FAISS index and returns relevant context.
    """
    if not os.path.exists(INDEX_PATH):
        return ""
        
    try:
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        vectorstore = FAISS.load_local(INDEX_PATH, embeddings, allow_dangerous_deserialization=True)
        docs = vectorstore.similarity_search(query, k=k)
        
        if not docs:
            return ""
            
        context = "\n\n--- Retrieved Knowledge Base Info ---\n"
        for i, doc in enumerate(docs):
            context += f"[Source {i+1}]: {doc.page_content}\n"
        return context
    except Exception as e:
        print(f"RAG Error: {e}")
        return ""
