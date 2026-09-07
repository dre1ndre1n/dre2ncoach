import os
import base64
import re
import urllib.parse
import requests
import streamlit as st
from database import save_polar_token, save_workout, get_polar_credentials

POLAR_AUTH_URL = "https://flow.polar.com/oauth2/authorization"
POLAR_TOKEN_URL = "https://polarremote.com/v2/oauth2/token"
POLAR_API_BASE = "https://www.polaraccesslink.com/v3"

def _get_secret(key: str, default: str = "") -> str:
    """Safely fetch a key from Streamlit secrets or environment variables."""
    try:
        if key in st.secrets and st.secrets[key]:
            return str(st.secrets[key]).strip()
    except Exception:
        pass
    val = os.environ.get(key, default)
    return str(val).strip() if val else default

def parse_iso_duration(duration_str: str) -> float:
    """Parse ISO 8601 duration string like PT1H30M15S into total minutes."""
    if not duration_str:
        return 0.0
    match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+(?:\.\d+)?)S)?', duration_str)
    if not match:
        return 0.0
    hours = float(match.group(1) or 0)
    minutes = float(match.group(2) or 0)
    seconds = float(match.group(3) or 0)
    return round(hours * 60 + minutes + seconds / 60, 1)

def get_polar_auth_url():
    """Generate the Polar OAuth2 authorization URL."""
    client_id = _get_secret("POLAR_CLIENT_ID")
    redirect_uri = _get_secret("STREAMLIT_URL", "http://localhost:8501/")
    if not client_id:
        return None
    encoded_redirect = urllib.parse.quote(redirect_uri, safe='')
    return f"{POLAR_AUTH_URL}?response_type=code&client_id={client_id}&redirect_uri={encoded_redirect}"

def exchange_code_for_token(code, user_id: str):
    """Exchange OAuth code for access token and save it to Supabase."""
    client_id = _get_secret("POLAR_CLIENT_ID")
    client_secret = _get_secret("POLAR_CLIENT_SECRET")
    redirect_uri = _get_secret("STREAMLIT_URL", "http://localhost:8501/")
    
    if isinstance(code, list):
        code = code[0]
    code = str(code).strip()
    
    if not client_id or not client_secret:
        st.error("Polar Client ID o Client Secret non configurati nelle impostazioni/secrets.")
        return False
    
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
    
    try:
        response = requests.post(POLAR_TOKEN_URL, data=data, headers=headers)
        if response.status_code == 200:
            token_data = response.json()
            access_token = token_data.get("access_token")
            polar_user_id = str(token_data.get("x_user_id") or token_data.get("user_id") or "")
            
            if not access_token or not polar_user_id:
                st.error("Risposta token da Polar non contiene access_token o x_user_id validi.")
                return False
            
            # Save token and polar_user_id to database
            success = save_polar_token(user_id, access_token, polar_user_id)
            
            # Register user to initiate data syncing from Polar
            register_user(access_token, polar_user_id)
            
            return success
        else:
            st.error(f"Errore scambio token Polar (HTTP {response.status_code}): {response.text}")
            return False
    except Exception as e:
        st.error(f"Eccezione durante la connessione a Polar: {e}")
        return False

def register_user(access_token: str, polar_user_id: str = None):
    """Register user to initiate data syncing from Polar."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {access_token}"
    }
    member_id = f"user_{polar_user_id}" if polar_user_id else "dre2ncoach_user"
    try:
        res = requests.post(f"{POLAR_API_BASE}/users", json={"member-id": member_id}, headers=headers)
        if res.status_code in (200, 201):
            print(f"Utente Polar registrato con successo: {res.status_code}")
        elif res.status_code == 409:
            print("Utente Polar già registrato (409 Conflict).")
        else:
            print(f"Attenzione registrazione Polar AccessLink: {res.status_code} {res.text}")
    except Exception as e:
        print(f"Errore durante la registrazione utente con Polar: {e}")

def fetch_and_save_exercises(user_id: str, access_token: str = None):
    """Fetch recent exercises via Polar Transaction and save to Supabase."""
    token, polar_user_id = get_polar_credentials(user_id)
    if not token:
        token = access_token
    
    if not token:
        st.error("Token di accesso Polar non disponibile.")
        return -1
    
    if not polar_user_id:
        st.error("Polar User ID non trovato per questo utente. Riconnetti l'account Polar.")
        return -1

    headers = {
        "Accept": "application/json",
        "Authorization": f"Bearer {token}"
    }
    
    # 1. Create transaction using actual Polar user ID (x_user_id)
    tx_url = f"{POLAR_API_BASE}/users/{polar_user_id}/exercise-transactions"
    tx_res = requests.post(tx_url, headers=headers)
    
    if tx_res.status_code == 201:
        tx_data = tx_res.json()
        resource_uri = tx_data.get("resource-uri")
        
        # 2. List exercises in transaction
        ex_res = requests.get(resource_uri, headers=headers)
        if ex_res.status_code == 200:
            exercises = ex_res.json().get("exercises", [])
            saved_count = 0
            for ex_item in exercises:
                ex_endpoint = ex_item if ex_item.startswith("http") else f"{POLAR_API_BASE}{ex_item}"
                detail_res = requests.get(ex_endpoint, headers=headers)
                if detail_res.status_code == 200:
                    detail = detail_res.json()
                    
                    duration_mins = parse_iso_duration(detail.get("duration", ""))
                    sport_info = detail.get("detailed-sport-info") or detail.get("sport") or "Allenamento"
                    
                    workout = {
                        "date": detail.get("start-time"),
                        "duration_minutes": duration_mins,
                        "heart_rate_avg": detail.get("heart-rate", {}).get("average", 0),
                        "calories": detail.get("calories", 0),
                        "sport": str(sport_info),
                        "description": f"Sincro Polar - Carico: {detail.get('training-load', 0)}"
                    }
                    if save_workout(user_id, workout):
                        saved_count += 1
            
            # 3. Commit transaction
            requests.put(resource_uri, headers=headers)
            return saved_count
        else:
            print("Errore lettura lista esercizi Polar:", ex_res.status_code, ex_res.text)
            return -1
    elif tx_res.status_code == 204:
        return 0  # No new data
    else:
        st.error(f"Errore creazione transazione Polar ({tx_res.status_code}): {tx_res.text}")
        return -1
