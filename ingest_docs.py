"""
Script di utilità per indicizzare permanentemente tutti i PDF presenti nel progetto Dre2nCoach su Pinecone.
Può essere eseguito da terminale con:
    python ingest_docs.py
"""

import os
import sys
from dotenv import load_dotenv

# Carica variabili d'ambiente da .env se presente
load_dotenv()

from rag_utils import get_local_pdf_files, build_rag_index_from_local_files, get_index_stats, get_pinecone_api_key

def main():
    print("=" * 60)
    print("⚡ Dre2nCoach - Indicizzazione Libreria Permanente su Pinecone")
    print("=" * 60)
    
    api_key = get_pinecone_api_key()
    if not api_key:
        print("❌ ERRORE: PINECONE_API_KEY non trovata nelle variabili d'ambiente.")
        print("Imposta la variabile con: set PINECONE_API_KEY=la_tua_chiave (su Windows CMD/PowerShell)")
        print("oppure creala in un file .env")
        sys.exit(1)
        
    local_files = get_local_pdf_files()
    print(f"\n📚 Trovati {len(local_files)} file PDF nel progetto:")
    for i, f in enumerate(local_files, 1):
        print(f"  {i}. {f['name']} ({f['size_mb']} MB)")
        
    if not local_files:
        print("\n⚠️ Nessun PDF trovato nel progetto.")
        return
        
    print("\n⏳ Inizio elaborazione ed estrazione del testo...")
    
    def print_progress(cur, total, item_name, message):
        print(f"[{cur}/{total}] {item_name} -> {message}")
        
    success, msg = build_rag_index_from_local_files(progress_callback=print_progress)
    
    if success:
        print("\n" + "=" * 60)
        print("✅ SUCCESS!")
        print(msg)
        stats = get_index_stats()
        print(f"📊 Totale vettori salvati su Pinecone: {stats.get('vector_count', 'N/D')}")
        print("=" * 60)
        print("Ora ogni volta che avvii Dre2nCoach, il modello consulterà automaticamente questa libreria permanente!")
    else:
        print("\n" + "=" * 60)
        print("❌ ERRORE INDICIZZAZIONE:")
        print(msg)
        print("=" * 60)

if __name__ == "__main__":
    main()
