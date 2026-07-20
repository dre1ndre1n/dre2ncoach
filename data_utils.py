import os
import zipfile
import pandas as pd
import io

def process_training_files(uploaded_files):
    """
    Process uploaded training data files (CSV, TXT, ZIP) and return a formatted context string.
    """
    context = ""
    for uploaded_file in uploaded_files:
        filename = uploaded_file.name.lower()
        
        try:
            if filename.endswith(".csv"):
                # Usually Polar summary data is in the second row, but let's try to parse general stats
                df = pd.read_csv(uploaded_file)
                # Keep it simple for context: convert to string, maybe head
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
