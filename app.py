import streamlit as st
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from data_utils import process_training_files
from rag_utils import build_rag_index, query_rag
from polar_api import get_polar_auth_url, exchange_code_for_token, fetch_and_save_exercises
from database import get_recent_workouts, get_polar_token
from dashboards import render_dashboards

# --- PAGE CONFIG ---
st.set_page_config(
    page_title="Dre2nCoach | Advanced AI Triathlon Coach",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Dummy user ID for this single-user app
USER_ID = "samuele_default"

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
    .sidebar-section {
        background: rgba(30, 41, 59, 0.45);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
        padding: 15px;
        margin-bottom: 20px;
    }
</style>
""", unsafe_allow_html=True)

# --- HANDLE OAUTH CALLBACK ---
query_params = st.query_params
if "code" in query_params:
    auth_code = query_params["code"]
    if isinstance(auth_code, list):
        auth_code = auth_code[0]
    st.info("Ricevuto codice di autorizzazione Polar! Sto elaborando...")
    if exchange_code_for_token(auth_code, USER_ID):
        st.success("Account Polar connesso con successo!")
    else:
        st.error("Errore durante il salvataggio o l'autenticazione. Controlla che le tabelle Supabase esistano e le chiavi siano corrette.")
    # Clear query param
    st.query_params.clear()


st.markdown("<div class='title-text'>Dre2nCoach ⚡</div>", unsafe_allow_html=True)
st.caption("AI Triathlon Training & Science-Backed Nutrition Coach (Cloud Connected)")

# --- SIDEBAR ---
with st.sidebar:
    st.markdown("<h3 style='color: #10B981;'>🔗 Polar Sync</h3>", unsafe_allow_html=True)
    polar_token = get_polar_token(USER_ID)
    if not polar_token:
        auth_url = get_polar_auth_url()
        if auth_url:
            st.markdown(f"[Connetti Account Polar]({auth_url})")
        else:
            st.warning("Configura POLAR_CLIENT_ID nelle Secrets per connettere Polar.")
    else:
        st.success("Polar Connesso")
        if st.button("Sincronizza Allenamenti"):
            with st.spinner("Sincronizzazione da Polar AccessLink..."):
                count = fetch_and_save_exercises(USER_ID, polar_token)
                if count > 0:
                    st.success(f"Sincronizzati {count} nuovi allenamenti!")
                elif count == 0:
                    st.info("Nessun nuovo allenamento trovato.")
                else:
                    st.error("Errore di sincronizzazione.")

    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #A855F7;'>📚 Libreria Permanente</h3>", unsafe_allow_html=True)
    pdf_files = st.file_uploader("Carica PDF (Manuali/Scienza)", type=['pdf'], accept_multiple_files=True)
    if st.button("Salva nella Libreria (Pinecone)"):
        if pdf_files:
            with st.spinner("Elaborazione e salvataggio sul database vettoriale..."):
                if build_rag_index(pdf_files):
                    st.success("Salvato permanentemente!")
                else:
                    st.error("Errore di salvataggio (controlla API Key Pinecone).")
        else:
            st.warning("Carica prima un PDF.")
    st.markdown("</div>", unsafe_allow_html=True)

# --- MAIN TABS ---
tab_chat, tab_dash, tab_settings = st.tabs(["💬 Coach IA", "📈 Dashboards", "⚙️ Impostazioni API"])

with tab_chat:
    if "messages" not in st.session_state:
        st.session_state.messages = [AIMessage(content="Ciao! Sono Dre2nCoach. Ho accesso al tuo storico Polar (se sincronizzato) e alla libreria scientifica su Pinecone. Come impostiamo la settimana?")]

    for msg in st.session_state.messages:
        with st.chat_message("user" if isinstance(msg, HumanMessage) else "assistant"):
            st.write(msg.content)

    user_input = st.chat_input("Chiedimi un consiglio o genera una scheda...")
    if user_input:
        st.session_state.messages.append(HumanMessage(content=user_input))
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Il Coach sta analizzando..."):
                # 1. Recupera Allenamenti Recenti da Supabase
                recent_workouts = get_recent_workouts(USER_ID, limit=14)
                workout_context = "Nessun allenamento recente trovato nel DB."
                if recent_workouts:
                    workout_context = "Storico recenti allenamenti (da Supabase):\n"
                    for w in recent_workouts:
                        workout_context += f"- {w['date']}: {w['sport']} per {w['duration_minutes']} min, FC media: {w['heart_rate_avg']}. Note: {w['description']}\n"
                
                # 2. RAG da Pinecone
                rag_context = query_rag(user_input, k=3)
                
                # 3. Router Logica
                # Se l'utente chiede una scheda, usiamo un prompt pesante. Altrimenti chat veloce.
                if "scheda" in user_input.lower() or "piano" in user_input.lower():
                    system_prompt_text = (
                        "Sei Dre2nCoach, esperto coach di Triathlon. Genera un piano di allenamento dettagliato.\n"
                        f"{workout_context}\n"
                        f"Usa questi principi scientifici: {rag_context}"
                    )
                else:
                    system_prompt_text = (
                        "Sei Dre2nCoach, assistente conversazionale di Triathlon. Rispondi in modo conciso.\n"
                        f"{workout_context}\n{rag_context}"
                    )
                
                google_api_key = os.environ.get("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets else None)
                if google_api_key:
                    os.environ["GOOGLE_API_KEY"] = google_api_key
                    
                if not google_api_key:
                    st.error("Google Gemini API Key mancante. Aggiungila nei Secrets di Streamlit Cloud o nel tab 'Impostazioni API'.")
                else:
                    try:
                        selected_model = st.session_state.get("gemini_model_choice", "gemini-1.5-flash")
                        llm = ChatGoogleGenerativeAI(
                            model=selected_model,
                            google_api_key=google_api_key,
                            temperature=0.7
                        )
                        full_chat = [SystemMessage(content=system_prompt_text)]
                        full_chat.extend(st.session_state.messages)
                        response = llm.invoke(full_chat)
                        st.write(response.content)
                        st.session_state.messages.append(AIMessage(content=response.content))
                    except Exception as e:
                        st.error(f"Errore LLM ({selected_model}): {e}")
                        st.info("💡 Vai nel tab **⚙️ Impostazioni API** e clicca su **'Testa Connessione Gemini'** per verificare la chiave e scoprire quali modelli sono abilitati sul tuo account Google.")

with tab_dash:
    render_dashboards(USER_ID)

with tab_settings:
    st.info("Per il deployment, salva queste chiavi in **Streamlit Cloud -> Advanced Settings -> Secrets**. Se le inserisci qui, verranno usate come variabili d'ambiente temporanee.")
    
    st.markdown("### 🤖 Configurazione Modello IA")
    gemini_model = st.selectbox(
        "Modello Gemini da utilizzare",
        ["gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro", "gemini-pro"],
        key="gemini_model_choice"
    )
    
    st.markdown("### 🔑 Chiavi API")
    k_google = st.text_input("Google Gemini API Key", type="password")
    k_pinecone = st.text_input("Pinecone API Key", type="password")
    k_supa_url = st.text_input("Supabase URL")
    k_supa_key = st.text_input("Supabase Key", type="password")
    k_polar_id = st.text_input("Polar Client ID")
    k_polar_sec = st.text_input("Polar Client Secret", type="password")
    
    col_save, col_test = st.columns(2)
    with col_save:
        if st.button("💾 Salva Chiavi Temporaneamente"):
            if k_google: os.environ["GOOGLE_API_KEY"] = k_google.strip()
            if k_pinecone: os.environ["PINECONE_API_KEY"] = k_pinecone.strip()
            if k_supa_url: os.environ["SUPABASE_URL"] = k_supa_url.strip()
            if k_supa_key: os.environ["SUPABASE_KEY"] = k_supa_key.strip()
            if k_polar_id: os.environ["POLAR_CLIENT_ID"] = k_polar_id.strip()
            if k_polar_sec: os.environ["POLAR_CLIENT_SECRET"] = k_polar_sec.strip()
            st.success("Chiavi salvate nella sessione!")
            
    with col_test:
        if st.button("🧪 Testa Connessione Gemini"):
            test_key = k_google.strip() if k_google else (os.environ.get("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets else None))
            if not test_key:
                st.error("Nessuna chiave Google Gemini trovata per il test.")
            else:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=test_key)
                    models = [m.name.replace("models/", "") for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
                    if models:
                        st.success(f"✅ Connessione riuscita! Modelli disponibili con questa chiave: {', '.join(models[:6])}")
                    else:
                        st.warning("⚠️ Connessione effettuata, ma nessun modello ha il permesso 'generateContent'.")
                except Exception as ex:
                    st.error(f"❌ Errore test Google Gemini: {ex}")
                    st.info("Consiglio: crea una chiave gratuita direttamente su https://aistudio.google.com/app/apikey")
