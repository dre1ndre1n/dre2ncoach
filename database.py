import os
from supabase import create_client, Client
import streamlit as st

def get_supabase_client() -> Client:
    """Initialize and return the Supabase client using Streamlit secrets or env vars."""
    supabase_url = st.secrets.get("SUPABASE_URL") if hasattr(st, "secrets") and "SUPABASE_URL" in st.secrets else os.environ.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY") if hasattr(st, "secrets") and "SUPABASE_KEY" in st.secrets else os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        return None
        
    try:
        return create_client(supabase_url, supabase_key)
    except Exception as e:
        print(f"Errore connessione Supabase: {e}")
        return None

def save_polar_token(user_id: str, access_token: str, user_polar_id: str):
    """Save or update the Polar OAuth token for a user."""
    client = get_supabase_client()
    if not client: return False
    
    data = {
        "user_id": user_id,
        "polar_access_token": access_token,
        "polar_user_id": user_polar_id
    }
    
    try:
        client.table("user_profiles").upsert(data).execute()
        return True
    except Exception as e:
        st.error(f"Errore nel salvataggio del token su Supabase: {e}")
        return False

def get_polar_token(user_id: str):
    """Retrieve the Polar Access Token for a user."""
    client = get_supabase_client()
    if not client: return None
    
    try:
        response = client.table("user_profiles").select("polar_access_token").eq("user_id", user_id).execute()
        if response.data and len(response.data) > 0:
            return response.data[0].get("polar_access_token")
    except Exception as e:
        print(f"Error retrieving token: {e}")
    return None

def get_polar_credentials(user_id: str):
    """Retrieve both Polar access token and polar_user_id for a user."""
    client = get_supabase_client()
    if not client: return None, None
    
    try:
        response = client.table("user_profiles").select("polar_access_token, polar_user_id").eq("user_id", user_id).execute()
        if response.data and len(response.data) > 0:
            row = response.data[0]
            return row.get("polar_access_token"), row.get("polar_user_id")
    except Exception as e:
        print(f"Error retrieving polar credentials: {e}")
    return None, None

def save_workout(user_id: str, workout_data: dict):
    """Save a workout summary to Supabase."""
    client = get_supabase_client()
    if not client: return False
    
    data = {"user_id": user_id, **workout_data}
    
    try:
        client.table("workouts").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving workout: {e}")
        return False

def get_recent_workouts(user_id: str, limit=20):
    """Fetch recent workouts for a user."""
    client = get_supabase_client()
    if not client: return []
    
    try:
        response = client.table("workouts").select("*").eq("user_id", user_id).order("date", desc=True).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching workouts: {e}")
        return []

def get_all_workouts(user_id: str, limit=150):
    """Fetch complete workout history for macrocycle analysis and volume tracking."""
    client = get_supabase_client()
    if not client: return []
    
    try:
        response = client.table("workouts").select("*").eq("user_id", user_id).order("date", desc=True).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Error fetching all workouts: {e}")
        return []

# ==========================================
# GESTIONE MEMORIA CONVERSAZIONI (CHAT HISTORY)
# ==========================================

def save_chat_message(user_id: str, role: str, content: str):
    """Save a chat message (user or assistant) to Supabase for persistent conversation memory."""
    client = get_supabase_client()
    if not client: return False
    
    data = {
        "user_id": user_id,
        "role": role,
        "content": content
    }
    
    try:
        client.table("chat_messages").insert(data).execute()
        return True
    except Exception as e:
        # Se la tabella non esiste ancora, registriamo senza bloccare l'esecuzione
        print(f"Notice: Impossibile salvare messaggio chat su Supabase (la tabella 'chat_messages' esiste?): {e}")
        return False

def get_chat_history(user_id: str, limit=40):
    """
    Retrieve stored chat messages from Supabase in chronological order.
    Returns a list of dicts: [{'role': 'user'|'assistant', 'content': str, 'created_at': str}]
    """
    client = get_supabase_client()
    if not client: return []
    
    try:
        response = client.table("chat_messages").select("*").eq("user_id", user_id).order("created_at", desc=False).limit(limit).execute()
        return response.data if response.data else []
    except Exception as e:
        print(f"Notice: Impossibile caricare storico chat da Supabase: {e}")
        return []

def clear_chat_history(user_id: str):
    """Delete chat history for a user to start a new training macrocycle."""
    client = get_supabase_client()
    if not client: return False
    
    try:
        client.table("chat_messages").delete().eq("user_id", user_id).execute()
        return True
    except Exception as e:
        print(f"Error clearing chat history: {e}")
        return False
