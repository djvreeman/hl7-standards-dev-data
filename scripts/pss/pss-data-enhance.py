#!/usr/bin/env python3
# =============================================================================
# PSS (Project Scope Statement) Data Enhancer
#
# This script processes a CSV file containing HL7 PSS data and enhances it by
# extracting missing Approval Dates from History records.
#
# === Purpose ===
# PSS issues in JIRA don't always have an Approval Date field populated even
# though they have a status of "Approved". This script analyzes the history
# records (changelog) to find when the status changed to "Approved" and fills
# in the missing Approval Dates.
#
# === Input Requirements ===
# - A CSV file with PSS data that includes:
#     - Issue (PSS number)
#     - Status (should be "Approved" for PSSs we're enhancing)
#     - Approval Date (may be missing)
#     - History (changelog data) - either in CSV column or separate JSON file
#
# === Output ===
# - An enhanced CSV file with:
#     - Approval Date filled in from history where missing
#     - Additional metadata about the extraction process
#
# === Example Usage ===
# python pss-data-enhance.py \
#     -i data/working/pss-approved/All\ -\ PSS\ Approved.csv \
#     -o data/working/pss-approved/All\ -\ PSS\ Approved-enhanced.csv
#
# python pss-data-enhance.py \
#     -i data/working/pss-approved/All\ -\ PSS\ Approved.csv \
#     -o data/working/pss-approved/All\ -\ PSS\ Approved-enhanced.csv \
#     --history-json-file data/working/pss-history.json
#
# === Dependencies ===
# - pandas
# - json
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import pandas as pd
import numpy as np
import json
import os
import csv
from datetime import datetime

def load_history_from_json(history_json_file, issue_keys=None):
    """Load History data from JSON file.
    
    Args:
        history_json_file: Path to JSON file containing history data keyed by issue key
        issue_keys: Optional list of issue keys to load (if None, loads all)
        
    Returns:
        Dictionary mapping issue keys to history data lists
    """
    if not os.path.exists(history_json_file):
        print(f"History JSON file not found: {history_json_file}")
        return {}
    
    try:
        with open(history_json_file, 'r', encoding='utf-8') as f:
            all_history = json.load(f)
        
        if issue_keys:
            # Filter to only requested issue keys
            return {key: all_history.get(key, []) for key in issue_keys}
        else:
            return all_history
    except Exception as e:
        print(f"Error loading History JSON file: {e}")
        return {}

def extract_approval_date_from_history(history_data):
    """
    Extract the date when a PSS transitioned to "Approved" status.
    
    This function finds the FIRST transition to "Approved" status in the history.
    For PSSs, we want the first time they were approved, not subsequent re-approvals.
    
    Args:
        history_data: List of history entries from JIRA changelog (may be JSON string or list)
        
    Returns:
        Approval date (pd.Timestamp) or None
    """
    # Handle JSON string if needed
    if isinstance(history_data, str):
        try:
            history_data = json.loads(history_data)
        except:
            return None
    
    if not history_data or not isinstance(history_data, list):
        return None
    
    # Handle various case variations of "Approved" status
    approved_status_names = ['Approved', 'approved', 'APPROVED', 'Approve', 'APPROVE']
    first_approval_date = None
    
    # Sort history entries by date (earliest first) to find first approval
    history_entries_with_dates = []
    for history_entry in history_data:
        created_str = history_entry.get('created', '')
        if not created_str:
            continue
        
        try:
            if '+' in created_str or created_str.endswith('Z'):
                created_date = pd.Timestamp(created_str)
            else:
                created_date = pd.Timestamp(created_str).tz_localize('UTC')
            history_entries_with_dates.append((created_date, history_entry))
        except:
            continue
    
    # Sort by date ascending (earliest first) to find first approval
    history_entries_with_dates.sort(key=lambda x: x[0])
    
    # Find the first transition to "Approved"
    for created_date, history_entry in history_entries_with_dates:
        if 'items' not in history_entry:
            continue
        
        # Check if any item in this history entry is a status transition to "Approved"
        for item in history_entry.get('items', []):
            if item.get('field') == 'status':
                to_status_name = item.get('toString', '')
                
                # Check if transitioning TO "Approved" status (case-insensitive)
                if to_status_name and to_status_name.strip().lower() in [s.lower() for s in approved_status_names]:
                    if first_approval_date is None or created_date < first_approval_date:
                        first_approval_date = created_date
                    break  # Found first approval, can stop checking this entry
    
    return first_approval_date

def process_pss_data(df, history_json_file=None):
    """Process PSS dataframe and extract Approval Dates from history"""
    
    # Check for duplicate Approval Date columns (pandas may add .1, .2 suffixes when renaming)
    approval_date_cols = [col for col in df.columns if col.startswith('Approval Date')]
    if len(approval_date_cols) > 1:
        print(f"Found multiple Approval Date columns: {approval_date_cols}")
        print("  Merging duplicate columns - preferring non-null values")
        # Convert all to datetime first
        for col in approval_date_cols:
            df[col] = pd.to_datetime(df[col], errors='coerce', utc=True)
        # Merge them - use bfill (backward fill) to get first non-null value across columns
        merged_dates = df[approval_date_cols].bfill(axis=1).iloc[:, 0]
        df['Approval Date'] = merged_dates
        # Drop the duplicate columns
        df = df.drop(columns=[col for col in approval_date_cols if col != 'Approval Date'])
        print(f"  Merged into single 'Approval Date' column")
    
    # Convert Approval Date to datetime if it exists
    if 'Approval Date' in df.columns:
        df['Approval Date'] = pd.to_datetime(df['Approval Date'], errors='coerce', utc=True)
        original_approval_count = df['Approval Date'].notna().sum()
        print(f"Found {original_approval_count} PSSs with existing Approval Date")
    else:
        df['Approval Date'] = None
        original_approval_count = 0
        print("No Approval Date column found - will extract from history")
    
    # Check for history-extracted columns that might contain approval dates
    # Look for columns created by the parse script's history extraction
    history_date_columns = [col for col in df.columns if col.startswith('history_') and 'created' in col.lower()]
    # Also check for columns that might have been renamed from history_created but still exist
    # (e.g., if the parse script created both the field and history column)
    
    # If we have history-extracted columns, use them to fill missing Approval Dates
    if history_date_columns:
        print(f"Found history-extracted date columns: {history_date_columns}")
        for hist_col in history_date_columns:
            # Convert to datetime
            df[hist_col] = pd.to_datetime(df[hist_col], errors='coerce', utc=True)
            # Fill in missing Approval Dates from history column
            fill_mask = df['Approval Date'].isna() & df[hist_col].notna()
            fill_count = fill_mask.sum()
            if fill_count > 0:
                df.loc[fill_mask, 'Approval Date'] = df.loc[fill_mask, hist_col]
                print(f"  Filled {fill_count} missing Approval Dates from {hist_col}")
            
            # Also check for conflicts (both exist but differ)
            conflict_mask = df['Approval Date'].notna() & df[hist_col].notna()
            if conflict_mask.any():
                conflicts = conflict_mask.sum()
                date_diffs = (df.loc[conflict_mask, 'Approval Date'] - df.loc[conflict_mask, hist_col]).abs()
                significant_diffs = (date_diffs > pd.Timedelta(days=1)).sum()
                if significant_diffs > 0:
                    print(f"  Note: Found {conflicts} PSSs with both Approval Date and {hist_col}")
                    print(f"    {significant_diffs} have dates that differ by more than 1 day")
                    print(f"    Keeping existing Approval Date (not overwriting)")
        
        # Optionally drop the history columns after merging (they're redundant now)
        # But keep them for now in case user wants to see the source
        # df = df.drop(columns=history_date_columns)
    
    # Check for Status column
    has_status = 'Status' in df.columns
    if has_status:
        # Find PSSs with Approved status (handle case variations)
        status_series = df['Status'].astype(str).str.strip().str.lower()
        approved_status_mask = status_series.isin(['approved', 'approve', 'approval'])
        approved_count = approved_status_mask.sum()
        print(f"Found {approved_count} PSSs with 'Approved' status")
        
        # Find PSSs that are Approved but missing Approval Date
        missing_approval_mask = approved_status_mask & df['Approval Date'].isna()
        missing_count = missing_approval_mask.sum()
        print(f"Found {missing_count} PSSs with 'Approved' status but missing Approval Date")
    else:
        print("Warning: No 'Status' column found. Will attempt to extract Approval Date for all PSSs with missing dates.")
        missing_approval_mask = df['Approval Date'].isna()
        missing_count = missing_approval_mask.sum()
        print(f"Found {missing_count} PSSs with missing Approval Date")
    
    # Check for History data
    history_col = None
    history_data_from_json = {}
    
    # First check for History column in DataFrame
    for col_name in ['History', 'history', 'changelog', 'Changelog', 'History Data']:
        if col_name in df.columns:
            history_col = col_name
            break
    
    # If no History column but we have a JSON file, load from JSON
    if not history_col and history_json_file:
        print(f"Loading History data from JSON file: {history_json_file}")
        # Get issue keys from DataFrame (try 'Issue' or 'key' column)
        issue_key_col = 'Issue' if 'Issue' in df.columns else ('key' if 'key' in df.columns else None)
        if issue_key_col:
            issue_keys = df[issue_key_col].dropna().tolist()
            history_data_from_json = load_history_from_json(history_json_file, issue_keys)
            print(f"Loaded History data for {len(history_data_from_json)} PSSs from JSON file")
        else:
            print("Warning: Could not find issue key column to load History data")
    
    # Note: We'll continue processing even if no history data is found,
    # because we may have already filled dates from history-extracted columns
    # The history extraction below will only run if history_col or history_data_from_json exists
    
    # Helper function to get history for a row
    def get_history_for_row(row):
        if history_col:
            # Get from DataFrame column
            history_str = row[history_col] if history_col in row.index else None
            if pd.notna(history_str) and history_str != '':
                if isinstance(history_str, str):
                    try:
                        return json.loads(history_str)
                    except:
                        return None
                return history_str
        elif history_data_from_json:
            # Get from JSON file
            issue_key_col = 'Issue' if 'Issue' in df.columns else 'key'
            issue_key = row[issue_key_col] if issue_key_col in row.index else None
            if issue_key:
                return history_data_from_json.get(issue_key, None)
        return None
    
    # Extract Approval Date from history for PSSs that need it
    if history_col or history_data_from_json:
        if history_col:
            print(f"Found history data in '{history_col}' column, extracting Approval Dates...")
        else:
            print("Found history data in JSON file, extracting Approval Dates...")
        
        # Extract approval dates from history
        extracted_approval_dates = df.apply(
            lambda row: extract_approval_date_from_history(get_history_for_row(row)), axis=1
        )
        
        # Count how many we extracted
        extracted_count = extracted_approval_dates.notna().sum()
        print(f"  Extracted Approval Date from history for {extracted_count} PSSs")
        
        # Fill in missing Approval Dates with extracted dates
        # Only fill where Approval Date is currently missing
        fill_mask = df['Approval Date'].isna() & extracted_approval_dates.notna()
        fill_count = fill_mask.sum()
        
        if fill_count > 0:
            df.loc[fill_mask, 'Approval Date'] = extracted_approval_dates[fill_mask]
            print(f"  Filled in {fill_count} missing Approval Dates from history")
            
            # Show some examples
            if 'Issue' in df.columns:
                filled_issues = df.loc[fill_mask, 'Issue'].head(10).tolist()
                print(f"  Sample PSSs with filled Approval Dates: {', '.join(str(issue) for issue in filled_issues)}")
                if fill_count > 10:
                    print(f"    ... and {fill_count - 10} more")
        else:
            print("  No missing Approval Dates could be filled from history")
        
        # Check for conflicts (existing Approval Date vs extracted date)
        conflict_mask = df['Approval Date'].notna() & extracted_approval_dates.notna()
        if conflict_mask.any():
            conflicts = conflict_mask.sum()
            print(f"  Note: Found {conflicts} PSSs with both existing and extracted Approval Dates")
            print(f"    Keeping existing Approval Date (not overwriting)")
            
            # Check if dates differ significantly
            existing_dates = df.loc[conflict_mask, 'Approval Date']
            extracted_dates = extracted_approval_dates[conflict_mask]
            date_diffs = (existing_dates - extracted_dates).abs()
            significant_diffs = (date_diffs > pd.Timedelta(days=1)).sum()
            
            if significant_diffs > 0:
                print(f"    Warning: {significant_diffs} PSSs have Approval Dates that differ by more than 1 day")
                if 'Issue' in df.columns:
                    diff_issues = df.loc[conflict_mask & (date_diffs > pd.Timedelta(days=1)), 'Issue'].head(5).tolist()
                    print(f"    Sample PSSs with date differences: {', '.join(str(issue) for issue in diff_issues)}")
    
    # Final summary
    final_approval_count = df['Approval Date'].notna().sum()
    print(f"\nSummary:")
    print(f"  Original Approval Dates: {original_approval_count}")
    print(f"  Final Approval Dates: {final_approval_count}")
    print(f"  Added from history: {final_approval_count - original_approval_count}")
    print(f"  Still missing: {df['Approval Date'].isna().sum()}")
    
    return df

def main():
    parser = argparse.ArgumentParser(
        description="Enhance PSS CSV data by extracting Approval Dates from History records."
    )
    parser.add_argument("-i", "--input", required=True, help="Input CSV file path")
    parser.add_argument("-o", "--output", help="Output CSV file path (optional, auto-generated if omitted)")
    parser.add_argument("--history-json-file",
                    help="Path to JSON file containing History data (if History was saved separately from CSV)")
    
    args = parser.parse_args()
    
    # Generate output file name if not provided
    if args.output is None:
        directory = os.path.dirname(args.input)
        filename = os.path.basename(args.input)
        base_name, extension = os.path.splitext(filename)
        args.output = os.path.join(directory, f"{base_name}-enhanced{extension}")
    
    # Load data with proper quoting to handle JSON strings with special characters
    print(f"Loading data from {args.input}")
    try:
        df = pd.read_csv(
            args.input,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True
        )
    except (ValueError, csv.Error, Exception) as e:
        # Fall back to default reading for CSV files that weren't written with explicit quoting
        print(f"Note: Reading CSV with default parameters (explicit quoting failed: {e})")
        df = pd.read_csv(args.input)
    
    df.columns = df.columns.str.strip()
    
    # Check for required columns
    if 'Issue' not in df.columns:
        print("Warning: 'Issue' column not found. Using index as identifier.")
    
    initial_count = len(df)
    print(f"Loaded {initial_count} PSS records")
    
    # Process data
    print("\nProcessing PSS data...")
    df = process_pss_data(df, history_json_file=args.history_json_file)
    
    # Before writing to CSV, ensure Approval Date column is in consistent string format
    if 'Approval Date' in df.columns:
        # Convert datetime objects to ISO format strings
        datetime_mask = df['Approval Date'].apply(
            lambda x: pd.api.types.is_datetime64_any_dtype(type(x)) if pd.notna(x) else False
        )
        if datetime_mask.any():
            def format_datetime_for_csv(dt):
                if pd.isna(dt):
                    return None
                if isinstance(dt, str):
                    return dt  # Already a string, keep as-is
                # Convert datetime to ISO format string
                if dt.tzinfo is not None:
                    # Timezone-aware datetime - use isoformat()
                    iso_str = dt.isoformat()
                    return iso_str
                else:
                    # Naive datetime - assume UTC and add timezone
                    iso_str = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
                    iso_str = iso_str.rstrip('0').rstrip('.')
                    return iso_str + '+00:00'
            
            df.loc[datetime_mask, 'Approval Date'] = df.loc[datetime_mask, 'Approval Date'].apply(format_datetime_for_csv)
    
    # Save enhanced CSV
    print(f"\nWriting enhanced data to {args.output}")
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")
    
    df.to_csv(args.output, index=False)
    print("Done!")
    print(f"\nEnhanced CSV saved to: {args.output}")
    print("You can now use this file with pss-analyze.py to generate reports.")

if __name__ == "__main__":
    main()
