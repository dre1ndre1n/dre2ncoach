import os
from supabase import create_client, Client
import streamlit as st

def get_supabase_client() -> Client:
    """Initialize and return the Supabase client using Streamlit secrets or env vars."""
    supabase_url = st.secrets.get("SUPABASE_URL") or os.environ.get("SUPABASE_URL")
    supabase_key = st.secrets.get("SUPABASE_KEY") or os.environ.get("SUPABASE_KEY")
    
    if not supabase_url or not supabase_key:
        st.warning("Supabase credentials are not set. Database features will not work.")
        return None
        
    return create_client(supabase_url, supabase_key)

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
        # Upsert based on user_id
        client.table("user_profiles").upsert(data).execute()
        return True
    except Exception as e:
        st.error(f"Errore nel salvataggio del token su Supabase (hai creato la tabella?): {e}")
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
    
    # workout_data should contain: date, duration_minutes, heart_rate_avg, calories, sport, description
    data = {"user_id": user_id, **workout_data}
    
    try:
        client.table("workouts").insert(data).execute()
        return True
    except Exception as e:
        print(f"Error saving workout: {e}")
        return False

def get_recent_workouts(user_id: str, limit=10):
    """Fetch recent workouts for a user."""
    client = get_supabase_client()
    if not client: return []
    
    try:
        response = client.table("workouts").select("*").eq("user_id", user_id).order("date", desc=True).limit(limit).execute()
        return response.data
    except Exception as e:
        print(f"Error fetching workouts: {e}")
        return []
