import os
import zipfile
import pandas as pd
import io
from datetime import datetime, timedelta
from database import get_all_workouts

def process_training_files(uploaded_files):
    """
    Process uploaded training data files (CSV, TXT, ZIP) and return a formatted context string.
    """
    context = ""
    for uploaded_file in uploaded_files:
        filename = uploaded_file.name.lower()
        
        try:
            if filename.endswith(".csv"):
                df = pd.read_csv(uploaded_file)
                context += f"\n--- Training Data from {uploaded_file.name} ---\n"
                context += df.head(5).to_string() + "\n"
                
            elif filename.endswith(".txt"):
                context += f"\n--- Text Notes from {uploaded_file.name} ---\n"
                context += uploaded_file.getvalue().decode("utf-8") + "\n"
                
            elif filename.endswith(".zip"):
                context += f"\n--- Data from ZIP archive {uploaded_file.name} ---\n"
                with zipfile.ZipFile(uploaded_file, 'r') as z:
                    for inner_filename in z.namelist():
                        if inner_filename.lower().endswith(".csv"):
                            with z.open(inner_filename) as f:
                                df = pd.read_csv(f)
                                context += f"[{inner_filename}] Data:\n"
                                context += df.head(5).to_string() + "\n"
                        elif inner_filename.lower().endswith(".txt"):
                            with z.open(inner_filename) as f:
                                context += f"[{inner_filename}] Notes:\n"
                                context += f.read().decode("utf-8") + "\n"
        except Exception as e:
            context += f"\n[Error processing {uploaded_file.name}: {str(e)}]\n"

    return context

def build_coach_training_context(user_id: str) -> str:
    """
    Analyzes the complete Polar workout history from Supabase to provide the Coach
    with weekly volume progressions, running volume trends, long run progression,
    and cross-training metrics specifically structured for Half-Marathon preparation.
    """
    workouts = get_all_workouts(user_id, limit=120)
    if not workouts:
        return "Nessun dato di allenamento Polar trovato nel database Supabase. Suggerisci all'atleta di sincronizzare Polar o inserire i volumi attuali."

    try:
        df = pd.DataFrame(workouts)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date', ascending=False)
        
        total_sessions = len(df)
        oldest_date = df['date'].min().strftime('%d/%m/%Y')
        newest_date = df['date'].max().strftime('%d/%m/%Y')
        
        # Categorizzazione sport
        def is_running(sport_name):
            s = str(sport_name).lower()
            return 'run' in s or 'corsa' in s or 'treadmill' in s or 'jog' in s
            
        df['is_running'] = df['sport'].apply(is_running)
        
        # Aggregazione per settimana (ISO calendar)
        df['year_week'] = df['date'].dt.strftime('%Y-W%W')
        
        weekly_stats = []
        for yw, group in df.groupby('year_week', sort=False):
            total_mins = group['duration_minutes'].sum()
            run_group = group[group['is_running']]
            run_mins = run_group['duration_minutes'].sum()
            run_sessions = len(run_group)
            max_run_mins = run_group['duration_minutes'].max() if not run_group.empty else 0
            avg_hr = group['heart_rate_avg'].replace(0, pd.NA).dropna().mean()
            
            weekly_stats.append({
                'week': yw,
                'total_mins': round(total_mins, 1),
                'total_hours': round(total_mins / 60.0, 1),
                'run_mins': round(run_mins, 1),
                'run_hours': round(run_mins / 60.0, 1),
                'run_sessions': run_sessions,
                'longest_run_mins': round(max_run_mins, 1) if pd.notna(max_run_mins) else 0,
                'avg_hr': round(avg_hr, 1) if pd.notna(avg_hr) else 'N/D'
            })
            
        # Ultime 6 settimane di carico
        recent_weeks = weekly_stats[:6]
        
        # Formattazione sintesi per il Coach
        summary = (
            f"--- ANALISI CARICO & STORICO POLAR (Totale: {total_sessions} allenamenti dal {oldest_date} al {newest_date}) ---\n"
            f"📊 PROGRESSIONE VOLUME SETTIMANALE RECENTE (ultime settimane registrate):\n"
        )
        
        for w in recent_weeks:
            summary += (
                f"  • Settimana {w['week']}: Corsa {w['run_mins']} min ({w['run_hours']}h in {w['run_sessions']} uscite) | "
                f"Lungo max: {w['longest_run_mins']} min | Volume Totale (tutti gli sport): {w['total_hours']}h | FC media: {w['avg_hr']} bpm\n"
            )
            
        # Dettaglio ultimi 10 allenamenti specifici
        summary += "\n📝 ULTIMI 10 ALLENAMENTI SVOLTI:\n"
        for _, row in df.head(10).iterrows():
            d_str = row['date'].strftime('%d/%m/%Y %H:%M')
            summary += f"  - [{d_str}] {row['sport']}: {row['duration_minutes']} min (FC media: {row.get('heart_rate_avg', 'N/D')} bpm). {row.get('description', '')}\n"
            
        return summary
    except Exception as e:
        print(f"Errore generazione sommario allenamenti: {e}")
        # Fallback semplice
        simple_context = "Storico allenamenti:\n"
        for w in workouts[:10]:
            simple_context += f"- {w.get('date')}: {w.get('sport')}, {w.get('duration_minutes')} min, FC: {w.get('heart_rate_avg')}\n"
        return simple_context
