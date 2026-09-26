import streamlit as st
import os
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from data_utils import process_training_files, build_coach_training_context
from rag_utils import (
    build_rag_index,
    query_rag,
    get_local_pdf_files,
    build_rag_index_from_local_files,
    get_index_stats
)
from polar_api import get_polar_auth_url, exchange_code_for_token, fetch_and_save_exercises
from database import (
    get_recent_workouts,
    get_polar_token,
    save_chat_message,
    get_chat_history,
    clear_chat_history
)
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
    st.markdown("<h3 style='color: #38BDF8;'>🤖 Modello IA & Chiavi</h3>", unsafe_allow_html=True)
    
    ai_provider = st.selectbox(
        "Fornitore IA",
        ["Google Gemini", "OpenAI (ChatGPT)"],
        key="ai_provider_select"
    )
    
    if ai_provider == "Google Gemini":
        active_gemini_key = os.environ.get("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets else None)
        
        # Recupero dinamico dei modelli supportati dall'account
        available_gemini_models = []
        if active_gemini_key:
            try:
                import google.generativeai as genai
                genai.configure(api_key=active_gemini_key)
                available_gemini_models = [
                    m.name.replace("models/", "")
                    for m in genai.list_models()
                    if "generateContent" in m.supported_generation_methods
                ]
            except Exception:
                pass
                
        if not available_gemini_models:
            available_gemini_models = [
                "gemini-2.5-flash",
                "gemini-2.5-pro",
                "gemini-2.0-flash",
                "gemini-1.5-flash",
                "gemini-1.5-pro",
                "gemini-pro",
                "Inserisci nome manuale"
            ]
        else:
            available_gemini_models.append("Inserisci nome manuale")
            
        chosen_option = st.selectbox(
            "Modello Gemini (Rilevati dal tuo account)",
            available_gemini_models,
            index=0,
            key="gemini_model_choice_raw"
        )
        
        if chosen_option == "Inserisci nome manuale":
            selected_model = st.text_input("Digita il nome esatto del modello (es. gemini-2.5-flash)", value="gemini-2.5-flash", key="gemini_custom_model")
        else:
            selected_model = chosen_option
            
        st.session_state["gemini_model_choice"] = selected_model
        
        gemini_input_key = st.text_input("Inserisci/Cambia Gemini Key", type="password", key="side_gemini_key")
        if gemini_input_key:
            os.environ["GOOGLE_API_KEY"] = gemini_input_key.strip()
            
        if st.button("🧪 Testa Chiave Gemini"):
            test_key = os.environ.get("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets else None)
            if not test_key:
                st.error("Nessuna chiave Google Gemini inserita o trovata nei Secrets.")
            else:
                try:
                    import google.generativeai as genai
                    genai.configure(api_key=test_key)
                    models = [m.name.replace("models/", "") for m in genai.list_models() if "generateContent" in m.supported_generation_methods]
                    if models:
                        st.success(f"✅ Connessione OK! Modelli attivi: {', '.join(models)}")
                    else:
                        st.warning("⚠️ Chiave valida ma nessun modello con generateContent trovato.")
                except Exception as ex:
                    st.error(f"❌ Errore Google API: {ex}")
    else:
        selected_model = st.selectbox(
            "Modello OpenAI",
            ["gpt-4o-mini", "gpt-4o", "gpt-3.5-turbo"],
            index=0,
            key="openai_model_choice"
        )
        openai_input_key = st.text_input("Inserisci OpenAI API Key", type="password", key="side_openai_key")
        if openai_input_key:
            os.environ["OPENAI_API_KEY"] = openai_input_key.strip()
            
        if st.button("🧪 Testa Chiave OpenAI"):
            test_key = os.environ.get("OPENAI_API_KEY") or (st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets else None)
            if not test_key:
                st.error("Nessuna chiave OpenAI inserita o trovata nei Secrets.")
            else:
                try:
                    from openai import OpenAI
                    client = OpenAI(api_key=test_key)
                    client.models.list()
                    st.success("✅ Connessione OpenAI riuscita!")
                except Exception as ex:
                    st.error(f"❌ Errore OpenAI API: {ex}")
                    
    st.markdown("</div>", unsafe_allow_html=True)
    
    st.markdown("<div class='sidebar-section'>", unsafe_allow_html=True)
    st.markdown("<h3 style='color: #A855F7;'>📚 Libreria Permanente (Knowledge Base)</h3>", unsafe_allow_html=True)
    
    # Rilevamento automatico dei PDF salvati nel progetto
    local_pdfs = get_local_pdf_files()
    if local_pdfs:
        st.markdown(f"**Manuali inclusi nel codice ({len(local_pdfs)}):**")
        for f in local_pdfs:
            # Mostra nome leggibile e dimensione
            display_name = f['name']
            if len(display_name) > 35:
                display_name = display_name[:32] + "..."
            st.markdown(f"- 📖 `{display_name}` *({f['size_mb']} MB)*")
    else:
        st.info("Nessun PDF trovato nella cartella del progetto.")
        
    # Mostra statistiche dell'indice Pinecone
    stats = get_index_stats()
    if stats.get("status") == "ready":
        count = stats.get("vector_count", 0)
        if count > 0:
            st.success(f"🟢 Database attivo: **{count} estratti** salvati su Pinecone.")
        else:
            st.warning("🟡 Indice vuoto. Clicca sotto per indicizzare i file locali.")
    elif stats.get("status") == "no_key":
        st.warning("⚠️ Inserisci la Pinecone API Key per attivare la Knowledge Base.")
    elif stats.get("status") == "not_created":
        st.info("ℹ️ L'indice Pinecone verrà creato alla prima indicizzazione.")
        
    if st.button("🔄 Sincronizza / Indicizza PDF Locali", use_container_width=True):
        if local_pdfs:
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            def update_progress(cur, total, item_name, msg):
                pct = min(1.0, (cur / max(1, total)))
                progress_bar.progress(pct)
                status_text.caption(f"⏳ **{item_name}**: {msg}")
                
            with st.spinner("Indicizzazione dei manuali locali in corso..."):
                success, msg = build_rag_index_from_local_files(progress_callback=update_progress)
                progress_bar.progress(1.0)
                if success:
                    st.success("✅ " + msg)
                    st.rerun()
                else:
                    st.error("❌ " + msg)
        else:
            st.warning("Nessun PDF locale trovato da indicizzare.")
            
    with st.expander("➕ Carica PDF Aggiuntivo"):
        extra_pdf = st.file_uploader("Upload manuale extra", type=['pdf'], accept_multiple_files=True, key="extra_pdf_upload")
        if st.button("Salva PDF extra su Pinecone"):
            if extra_pdf:
                with st.spinner("Elaborazione PDF extra..."):
                    if build_rag_index(extra_pdf):
                        st.success("Salvato su Pinecone!")
                        st.rerun()
                    else:
                        st.error("Errore di caricamento.")
            else:
                st.warning("Seleziona almeno un file.")
                
    st.markdown("</div>", unsafe_allow_html=True)

# --- MAIN TABS ---
tab_chat, tab_dash, tab_settings = st.tabs(["💬 Coach IA", "📈 Dashboards", "⚙️ Tutte le Chiavi API"])

with tab_chat:
    # Intestazione e controllo memoria
    col_info, col_reset = st.columns([4, 1])
    with col_info:
        st.markdown(
            """
            <div style='background: rgba(56, 189, 248, 0.08); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 8px; padding: 8px 14px; margin-bottom: 12px;'>
                🎯 <b>Obiettivo Attivo:</b> <span style='color: #38BDF8;'>Mezza Maratona (Novembre 2026)</span> &nbsp;|&nbsp; 
                🧠 <b>Memoria Coach:</b> <span style='color: #10B981;'>Attiva (Sincronizzata su Supabase)</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with col_reset:
        if st.button("🧹 Reset Chat", help="Cancella la memoria della conversazione per avviare una nuova fase"):
            clear_chat_history(USER_ID)
            st.session_state.messages = [
                AIMessage(content="Memoria conversazione azzerata! Ciao Samuele, sono pronto per pianificare la tua preparazione per la Mezza Maratona di Novembre. Come procediamo?")
            ]
            st.rerun()

    # Inizializzazione messaggi con recupero da Supabase
    if "messages" not in st.session_state:
        db_history = get_chat_history(USER_ID, limit=50)
        if db_history:
            st.session_state.messages = [
                HumanMessage(content=m["content"]) if m["role"] == "user" else AIMessage(content=m["content"])
                for m in db_history
            ]
        else:
            st.session_state.messages = [
                AIMessage(content="Ciao Samuele! Sono Dre2nCoach ⚡. Ho accesso a tutto il tuo storico Polar e alla libreria scientifica su Pinecone.\n\nCon la **Mezza Maratona di Novembre** come obiettivo, monitorerò la progressione del volume settimanale, i lunghi e il recupero per farti arrivare al top della forma. Come impostiamo la settimana?")
            ]

    # Visualizzazione messaggi
    for msg in st.session_state.messages:
        with st.chat_message("user" if isinstance(msg, HumanMessage) else "assistant"):
            st.write(msg.content)

    user_input = st.chat_input("Chiedimi un consiglio, un'analisi del volume o genera la scheda...")
    if user_input:
        # Registra messaggio utente localmente e su Supabase
        st.session_state.messages.append(HumanMessage(content=user_input))
        save_chat_message(USER_ID, "user", user_input)
        
        with st.chat_message("user"):
            st.write(user_input)

        with st.chat_message("assistant"):
            with st.spinner("Il Coach sta analizzando il carico Polar e la letteratura scientifica..."):
                # 1. Recupera Analisi Completa del Carico & Storico Polar da Supabase
                training_context = build_coach_training_context(USER_ID)
                
                # 2. RAG da Pinecone (Principi Scientifici da libri locali)
                rag_context = query_rag(user_input, k=4)
                
                # 3. System Prompt specializzato per Mezza Maratona & Progressione Volumi
                system_prompt_text = (
                    "Sei Dre2nCoach, Head Coach d'élite esperto in Mezza Maratona, Triathlon e Scienze dell'Allenamento.\n"
                    "Il tuo atleta (Samuele) sta preparando una MEZZA MARATONA (21.097 km) prevista per NOVEMBRE 2026.\n\n"
                    "--- I TUOI COMPITI CHIAVE COME COACH ---\n"
                    "1. MEMORIA & CONTINUITÀ: Ricorda sempre le conversazioni precedenti, le sensazioni espresse dall'atleta e le schede già concordate.\n"
                    "2. PROGRESSIONE DEL VOLUME: Analizza attentamente il volume settimanale registrato da Polar. Applica la regola dell'overload progressivo (incrementi massimi di volume del 10% a settimana per la corsa, alternati a settimane di scarico/deload ogni 3-4 settimane).\n"
                    "3. PROGRESSIONE DEI LUNGHI: Costruisci gradualmente il 'Lungo' domenicale (fino a 16-19 km in progressione prima dello scarico pre-gara).\n"
                    "4. PREVENZIONE INFORTUNI & MOBILITÀ: Integra principi da 'Becoming a Supple Leopard' (Kelly Starrett) e 'Strength Training for Triathletes' (Patrick Hagerman).\n"
                    "5. CHIAREZZA: Fornisci tabelle chiare giorno per giorno quando ti viene chiesta una scheda, specificando andature (ritmo gara vs aerobico lento Z2), durate e FC target.\n\n"
                    f"{training_context}\n"
                    f"{rag_context}"
                )
                
                # 4. Inizializzazione LLM (Gemini o OpenAI)
                current_provider = st.session_state.get("ai_provider_select", "Google Gemini")
                llm = None
                
                if current_provider == "OpenAI (ChatGPT)":
                    openai_api_key = os.environ.get("OPENAI_API_KEY") or (st.secrets.get("OPENAI_API_KEY") if hasattr(st, "secrets") and "OPENAI_API_KEY" in st.secrets else None)
                    current_model = st.session_state.get("openai_model_choice", "gpt-4o-mini")
                    if not openai_api_key:
                        st.error("⚠️ Chiave OPENAI_API_KEY mancante. Inseriscila nella barra laterale o nei Secrets.")
                    else:
                        try:
                            llm = ChatOpenAI(model=current_model, api_key=openai_api_key, temperature=0.7)
                        except Exception as e:
                            st.error(f"Errore inizializzazione OpenAI: {e}")
                else:
                    google_api_key = os.environ.get("GOOGLE_API_KEY") or (st.secrets.get("GOOGLE_API_KEY") if hasattr(st, "secrets") and "GOOGLE_API_KEY" in st.secrets else None)
                    current_model = st.session_state.get("gemini_model_choice", "gemini-2.0-flash")
                    if not google_api_key:
                        st.error("⚠️ Chiave GOOGLE_API_KEY mancante. Inseriscila nella barra laterale o nei Secrets.")
                    else:
                        try:
                            llm = ChatGoogleGenerativeAI(
                                model=current_model,
                                google_api_key=google_api_key,
                                temperature=0.7
                            )
                        except Exception as e:
                            st.error(f"Errore inizializzazione Gemini: {e}")
                
                if llm:
                    full_chat = [SystemMessage(content=system_prompt_text)]
                    full_chat.extend(st.session_state.messages)
                    try:
                        response = llm.invoke(full_chat)
                        st.write(response.content)
                        st.session_state.messages.append(AIMessage(content=response.content))
                        # Salva la risposta dell'assistente nel DB per memoria permanente
                        save_chat_message(USER_ID, "assistant", response.content)
                    except Exception as e:
                        st.error(f"Errore generazione risposta ({current_model}): {e}")
                        st.info("💡 Suggerimento: Puoi cambiare modello o fornitore (es. OpenAI GPT-4o o Gemini 2.0 / Pro) direttamente dalla barra laterale a sinistra.")

with tab_dash:
    render_dashboards(USER_ID)

with tab_settings:
    st.info("Per il deployment definitivo, inserisci queste chiavi in **Streamlit Cloud -> App settings -> Secrets**.")
    
    k_google = st.text_input("Google Gemini API Key", type="password")
    k_openai = st.text_input("OpenAI API Key (Opzionale per GPT-4o)", type="password")
    k_pinecone = st.text_input("Pinecone API Key", type="password")
    k_supa_url = st.text_input("Supabase URL")
    k_supa_key = st.text_input("Supabase Key", type="password")
    k_polar_id = st.text_input("Polar Client ID")
    k_polar_sec = st.text_input("Polar Client Secret", type="password")
    
    if st.button("💾 Salva Tutte le Chiavi Temporaneamente"):
        if k_google: os.environ["GOOGLE_API_KEY"] = k_google.strip()
        if k_openai: os.environ["OPENAI_API_KEY"] = k_openai.strip()
        if k_pinecone: os.environ["PINECONE_API_KEY"] = k_pinecone.strip()
        if k_supa_url: os.environ["SUPABASE_URL"] = k_supa_url.strip()
        if k_supa_key: os.environ["SUPABASE_KEY"] = k_supa_key.strip()
        if k_polar_id: os.environ["POLAR_CLIENT_ID"] = k_polar_id.strip()
        if k_polar_sec: os.environ["POLAR_CLIENT_SECRET"] = k_polar_sec.strip()
        st.success("Tutte le chiavi salvate nella sessione!")
        
    with st.expander("🛠️ Istruzioni Setup Tabelle Supabase (Database)"):
        st.markdown("""
        Se crei un nuovo progetto Supabase o non hai ancora configurato le tabelle, esegui questo script nel **SQL Editor** di Supabase:
        ```sql
        -- 1. Tabella Profili Utente & Token Polar
        CREATE TABLE IF NOT EXISTS user_profiles (
            user_id TEXT PRIMARY KEY,
            polar_access_token TEXT,
            polar_user_id TEXT,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
        );

        -- 2. Tabella Allenamenti Sincronizzati da Polar
        CREATE TABLE IF NOT EXISTS workouts (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            date TIMESTAMP WITH TIME ZONE NOT NULL,
            sport TEXT,
            duration_minutes FLOAT,
            heart_rate_avg INT,
            calories INT,
            description TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now())
        );

        -- 3. Tabella Memoria Chat Persistente Coach
        CREATE TABLE IF NOT EXISTS chat_messages (
            id BIGSERIAL PRIMARY KEY,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT timezone('utc'::text, now()) NOT NULL
        );
        ```
        """)
