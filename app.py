import streamlit as st
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.schema import HumanMessage, SystemMessage, AIMessage

from data_utils import process_training_files
from rag_utils import build_rag_index, query_rag

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Dre2nCoach | AI Triathlon & Nutrition",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CUSTOM CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;500;600;700&display=swap');
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    .stApp {
        background-color: #0F172A;
        color: #E2E8F0;
    }
    .title-text {
        font-weight: 700;
        background: linear-gradient(135deg, #38BDF8 0%, #A855F7 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        font-size: 3rem;
        margin-bottom: 0.5rem;
    }
    .subtitle-text {
        font-size: 1.2rem;
        color: #94A3B8;
        margin-bottom: 2rem;
    }
    .sidebar-section {
        background: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 20px;
    }
    .stChatMessage {
        background: rgba(30, 41, 59, 0.45) !important;
        border: 1px solid rgba(255, 255, 255, 0.08) !important;
        border-radius: 12px !important;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("<div class='title-text'>Dre2nCoach ⚡</div>", unsafe_allow_html=True)
st.markdown("<div class='subtitle-text'>AI Triathlon Training & Science-Backed Nutrition Coach</div>", unsafe_allow_html=True)

# --- STATE INITIALIZATION ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    # Add initial greeting
    st.session_state.messages.append(AIMessage(content="Ciao! Sono Dre2nCoach, il tuo allenatore IA di Triathlon. Carica i tuoi dati di allenamento o i PDF scientifici nella sidebar, e chiedimi come impostare la tua settimana!"))

if "athlete_context" not in st.session_state:
    st.session_state.athlete_context = ""

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("<h3 style='color: #38BDF8;'>⚙️ Settings</h3>", unsafe_allow_html=True)
    api_key = st.text_input("Google Gemini API Key", type="password", help="Required to chat with the AI.")
    if api_key:
        os.environ["GOOGLE_API_KEY"] = api_key
        
    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #10B981;'>📈 Section A: Training Data</h3>", unsafe_allow_html=True)
    st.caption("Upload Polar CSVs, TXT plans, or ZIP files.")
    training_files = st.file_uploader("Upload Data", type=['csv', 'txt', 'zip'], accept_multiple_files=True)
    
    if st.button("Process Training Data"):
        if training_files:
            with st.spinner("Processing files..."):
                context = process_training_files(training_files)
                st.session_state.athlete_context = context
                st.success("Training data loaded into context!")
        else:
            st.warning("Please upload files first.")
            
    if st.session_state.athlete_context:
        st.info("✅ Athlete context is active.")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #A855F7;'>📚 Section B: Knowledge Base</h3>", unsafe_allow_html=True)
    st.caption("Upload PDFs (e.g. Monique Ryan's book) to enhance the coach's knowledge via RAG.")
    pdf_files = st.file_uploader("Upload PDFs", type=['pdf'], accept_multiple_files=True)
    
    if st.button("Build Knowledge Base"):
        if pdf_files:
            with st.spinner("Chunking text and building FAISS index (this may take a minute)..."):
                success = build_rag_index(pdf_files)
                if success:
                    st.success("Knowledge Base updated!")
                else:
                    st.error("Failed to build index.")
        else:
            st.warning("Please upload PDFs first.")
    st.markdown("</div>", unsafe_allow_html=True)

# --- MAIN CHAT INTERFACE ---
for msg in st.session_state.messages:
    if isinstance(msg, HumanMessage):
        with st.chat_message("user"):
            st.write(msg.content)
    elif isinstance(msg, AIMessage):
        with st.chat_message("assistant"):
            st.write(msg.content)

# Chat Input
user_input = st.chat_input("Ask Dre2nCoach about your training plan...")

if user_input:
    if not os.environ.get("GOOGLE_API_KEY"):
        st.error("Please enter your Google Gemini API Key in the sidebar to chat.")
        st.stop()

    # Add user message to state and display
    st.session_state.messages.append(HumanMessage(content=user_input))
    with st.chat_message("user"):
        st.write(user_input)

    # Generate response
    with st.chat_message("assistant"):
        with st.spinner("Dre2nCoach is thinking..."):
            try:
                # 1. Retrieve RAG context
                rag_context = query_rag(user_input, k=3)
                
                # 2. Build System Prompt
                system_prompt_text = (
                    "Sei Dre2nCoach, un esperto allenatore di Triathlon e nutrizionista sportivo. "
                    "Segui i principi scientifici di Monique Ryan (Sports Nutrition for Endurance Athletes). "
                    "Sei formattato per rispondere in modo professionale, motivante e analitico."
                )
                
                if st.session_state.athlete_context:
                    system_prompt_text += f"\n\nEcco i dati di allenamento attuali dell'atleta:\n{st.session_state.athlete_context}"
                    
                if rag_context:
                    system_prompt_text += f"\n\nEcco alcune informazioni pertinenti dalla tua base di conoscenza scientifica:\n{rag_context}"
                
                # 3. Call LLM
                llm = ChatGoogleGenerativeAI(model="gemini-1.5-pro", temperature=0.7)
                
                # Reconstruct full conversation for the LLM
                full_chat = [SystemMessage(content=system_prompt_text)]
                full_chat.extend(st.session_state.messages)
                
                response = llm.invoke(full_chat)
                
                # Display response
                st.write(response.content)
                
                # Save to state
                st.session_state.messages.append(AIMessage(content=response.content))
                
            except Exception as e:
                st.error(f"An error occurred: {e}")
