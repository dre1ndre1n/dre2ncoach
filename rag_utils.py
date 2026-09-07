import os
import tempfile
import streamlit as st
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone, ServerlessSpec

PINECONE_INDEX_NAME = "dre2ncoach"

def get_pinecone_client():
    api_key = st.secrets.get("PINECONE_API_KEY") or os.environ.get("PINECONE_API_KEY")
    if not api_key:
        return None
    return Pinecone(api_key=api_key)

def build_rag_index(uploaded_pdfs):
    """
    Takes uploaded PDF files, processes them, and uploads embeddings to Pinecone.
    """
    if not uploaded_pdfs:
        return False
        
    pc = get_pinecone_client()
    if not pc:
        st.error("Pinecone API Key is missing.")
        return False
        
    docs = []
    
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
    
    try:
        PineconeVectorStore.from_documents(splits, embeddings, index_name=PINECONE_INDEX_NAME)
        return True
    except Exception as e:
        print(f"Error building Pinecone index: {e}")
        return False

def query_rag(query, k=3):
    """
    Queries the Pinecone index and returns relevant context.
    """
    pc = get_pinecone_client()
    if not pc: return ""
        
    try:
        embeddings = HuggingFaceEmbeddings(model_name="all-MiniLM-L6-v2")
        vectorstore = PineconeVectorStore(index_name=PINECONE_INDEX_NAME, embedding=embeddings)
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
