import os
import pandas as pd
from backend_core.config import FEATURE_MATRIX_EXPANDED_PATH, FEATURE_MATRIX_PATH

def check_data_years():
    paths = [
        str(FEATURE_MATRIX_EXPANDED_PATH),
        str(FEATURE_MATRIX_PATH)
    ]
    found = False
    for path in paths:
        if os.path.exists(path):
            print(f"\n--- Analyzing {path} ---")
            df = pd.read_csv(path)
            if 'year' in df.columns:
                years = sorted(df['year'].unique())
                print(f"Total rows: {len(df)}")
                print(f"Year range: {min(years)} to {max(years)}")
                print(f"Number of unique years: {len(years)}")
                print("\nRows per year:")
                year_counts = df['year'].value_counts().sort_index()
                print(year_counts.to_string())
                
                if 'distress_label' in df.columns:
                    print("\nDistressed companies per year:")
                    distress_counts = df[df['distress_label'] == 1]['year'].value_counts().sort_index()
                    print(distress_counts.to_string())
            else:
                print("Column 'year' not found in this file.")
            found = True
            break
            
    if not found:
        print("No feature matrix files found. Please run engineer.py or label_engine.py first.")

if __name__ == "__main__":
    check_data_years()
