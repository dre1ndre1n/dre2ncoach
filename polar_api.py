import os
import requests
import streamlit as st
from database import save_polar_token, save_workout

POLAR_AUTH_URL = "https://flow.polar.com/oauth2/authorization"
POLAR_TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
POLAR_API_BASE = "https://www.polaraccesslink.com/v3"

def get_polar_auth_url():
    """Generate the Polar OAuth2 authorization URL."""
    client_id = st.secrets.get("POLAR_CLIENT_ID") or os.environ.get("POLAR_CLIENT_ID")
    redirect_uri = st.secrets.get("STREAMLIT_URL") or "http://localhost:8501/"
    if not client_id:
        return None
    return f"{POLAR_AUTH_URL}?response_type=code&client_id={client_id}&redirect_uri={redirect_uri}"

import base64

def exchange_code_for_token(code: str, user_id: str):
    """Exchange OAuth code for access token and save it to Supabase."""
    client_id = st.secrets.get("POLAR_CLIENT_ID") or os.environ.get("POLAR_CLIENT_ID")
    client_secret = st.secrets.get("POLAR_CLIENT_SECRET") or os.environ.get("POLAR_CLIENT_SECRET")
    redirect_uri = st.secrets.get("STREAMLIT_URL") or "http://localhost:8501/"
    
    auth_str = f"{client_id}:{client_secret}"
    encoded_auth = base64.b64encode(auth_str.encode()).decode()
    
    headers = {
        "Authorization": f"Basic {encoded_auth}",
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json"
    }
    
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri
    }
    
    response = requests.post(POLAR_TOKEN_URL, data=data, headers=headers)
    if response.status_code == 200:
        token_data = response.json()
        access_token = token_data.get("access_token")
        polar_user_id = str(token_data.get("x_user_id"))
        
        # Save to database
        success = save_polar_token(user_id, access_token, polar_user_id)
        
        # We must register the user with AccessLink
        register_user(access_token)
        
        return success
    else:
        st.error(f"Failed to get token: {response.text}")
        return False

def register_user(access_token: str):
    """Register user to initiate data syncing from Polar."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    # User info payload could be empty or have member-id
    requests.post(f"{POLAR_API_BASE}/users", json={"member-id": "dre2ncoach"}, headers=headers)

def fetch_and_save_exercises(user_id: str, access_token: str):
    """Fetch recent exercises via Transaction and save to Supabase."""
    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    
    # 1. Create transaction
    user_polar_id = "TODO_get_from_db" # simplified for now
    tx_res = requests.post(f"{POLAR_API_BASE}/users/{user_id}/exercise-transactions", headers=headers)
    
    if tx_res.status_code == 201:
        tx_data = tx_res.json()
        tx_url = tx_data.get("resource-uri")
        
        # 2. List exercises in transaction
        ex_res = requests.get(tx_url, headers=headers)
        if ex_res.status_code == 200:
            exercises = ex_res.json().get("exercises", [])
            for ex in exercises:
                ex_url = ex.replace(POLAR_API_BASE, "") # Get relative path
                detail_res = requests.get(f"{POLAR_API_BASE}{ex_url}", headers=headers)
                if detail_res.status_code == 200:
                    detail = detail_res.json()
                    
                    # Transform and save
                    workout = {
                        "date": detail.get("start-time"),
                        "duration_minutes": float(detail.get("duration", "PT0S").replace('PT','').replace('S','').replace('M','')) / 60 if 'M' in detail.get("duration", "") else 0, # Simplify parsing
                        "heart_rate_avg": detail.get("heart-rate", {}).get("average", 0),
                        "calories": detail.get("calories", 0),
                        "sport": detail.get("detailed-sport-info", "Unknown"),
                        "description": f"Polar Auto Sync - Load: {detail.get('training-load', 0)}"
                    }
                    save_workout(user_id, workout)
            
            # 3. Commit transaction
            requests.put(tx_url, headers=headers)
            return len(exercises)
    elif tx_res.status_code == 204:
        return 0 # No new data
    else:
        print("Error creating Polar transaction", tx_res.status_code)
        return -1
