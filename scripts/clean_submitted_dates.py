import pandas as pd
import numpy as np
from datetime import datetime
import os

# Input and output file paths
input_file = os.path.join('data', 'working', 'members', '2025 07 18 - FHIR Trademark Applications Record - cleaned-dates.xlsx')
summary_csv = os.path.join('data', 'working', 'members', '2025 07 18 - FHIR Trademark Applications Record - summary-by-year.csv')

def extract_year(val):
    if pd.isnull(val):
        return None
    try:
        return str(val)[:4] if str(val)[:4].isdigit() else None
    except Exception:
        return None

def main():
    # Read all sheets
    xls = pd.ExcelFile(input_file)
    summary_rows = []
    for sheet_name in xls.sheet_names:
        df = xls.parse(sheet_name)
        # Find the 'submitted' and 'status' columns (case-insensitive)
        submitted_cols = [col for col in df.columns if col.strip().lower() == 'submitted']
        status_cols = [col for col in df.columns if col.strip().lower() == 'status']
        # Applications by year
        if submitted_cols:
            years = df[submitted_cols[0]].apply(extract_year)
            app_counts = years.value_counts().sort_index()
        else:
            app_counts = pd.Series(dtype=int)
        # Approvals by year (status == 'approved')
        if submitted_cols and status_cols:
            status_col = status_cols[0]
            submitted_col = submitted_cols[0]
            approved_mask = df[status_col].astype(str).str.strip().str.lower() == 'approved'
            approved_years = df.loc[approved_mask, submitted_col].apply(extract_year)
            appr_counts = approved_years.value_counts().sort_index()
        else:
            appr_counts = pd.Series(dtype=int)
        # Union of years
        all_years = sorted(set(app_counts.index).union(set(appr_counts.index)))
        for year in all_years:
            applications = int(app_counts.get(year, 0))
            approvals = int(appr_counts.get(year, 0))
            summary_rows.append({
                'worksheet': sheet_name,
                'year': year,
                'applications': applications,
                'approvals': approvals
            })
    # Output to CSV
    summary_df = pd.DataFrame(summary_rows)
    summary_df = summary_df.sort_values(['worksheet', 'year'])
    summary_df.to_csv(summary_csv, index=False)
    print(f"Summary by year saved as: {summary_csv}")

if __name__ == '__main__':
    main() 