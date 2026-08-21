#!/usr/bin/env python3
"""Investigate the 6-issue difference in Applied count"""

import pandas as pd
import sys
import os
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from applied_issues_analyze import parse_time_period, process_data, get_period_metrics

# Load and process data exactly as the QA script does
csv_file = 'data/working/issue-analysis/2025/2025-AllYear/2025-all-resolved-issues-enhanced-v3.csv'
print(f"Loading {csv_file}...")

try:
    df = pd.read_csv(csv_file, quoting=csv.QUOTE_MINIMAL, doublequote=True)
except:
    df = pd.read_csv(csv_file)

df.columns = df.columns.str.strip()

if 'WG Name' not in df.columns and 'WG' in df.columns:
    df.rename(columns={'WG': 'WG Name'}, inplace=True)
if 'Specification Display Name' not in df.columns and 'Specification' in df.columns:
    df.rename(columns={'Specification': 'Specification Display Name'}, inplace=True)

# Process data
print("Processing data...")
df = process_data(df, ['2025'], history_json_file=None)

if df is None:
    print("ERROR: Failed to process data")
    sys.exit(1)

# Parse period
start_date, end_date, label = parse_time_period('2025')
print(f"\nPeriod: {label}")
print(f"Start: {start_date}")
print(f"End: {end_date}")

# Method 1: Direct calculation (QA script method)
applied_mask = df['Applied Date'].notna() & \
              (df['Applied Date'] >= start_date) & \
              (df['Applied Date'] <= end_date)
applied_count_direct = applied_mask.sum()
print(f"\nDirect calculation (QA method): {applied_count_direct}")

# Method 2: Using get_period_metrics (report method)
n, r, b, _, _, _ = get_period_metrics(df, '2025')
print(f"get_period_metrics (report method): {r}")

# Check if they match
if applied_count_direct != r:
    print(f"\n⚠️  MISMATCH: Direct={applied_count_direct}, get_period_metrics={r}")
    
    # Find the difference
    # Check what get_period_metrics is doing
    start_date2, end_date2, label2 = parse_time_period('2025')
    applied_mask2 = df['Applied Date'].notna() & \
                   (df['Applied Date'] >= start_date2) & \
                   (df['Applied Date'] <= end_date2)
    applied_count2 = applied_mask2.sum()
    
    print(f"\nRe-checking get_period_metrics logic:")
    print(f"  start_date matches: {start_date == start_date2}")
    print(f"  end_date matches: {end_date == end_date2}")
    print(f"  Applied count with same dates: {applied_count2}")
    
    # Check for issues that might be counted differently
    # Look at the created_in_2025 flag
    if 'created_in_2025' in df.columns:
        print(f"\nIssues with created_in_2025 flag: {df['created_in_2025'].sum()}")
    
    # Check for any filtering differences
    print(f"\nTotal issues with Applied Date: {df['Applied Date'].notna().sum()}")
    print(f"Applied Date in 2025 (by year): {df[df['Applied Date'].notna() & (df['Applied Date'].dt.year == 2025)].shape[0]}")
    
    # Check boundary cases
    print(f"\nBoundary checks:")
    print(f"  Applied Date == start_date: {(df['Applied Date'] == start_date).sum()}")
    print(f"  Applied Date == end_date: {(df['Applied Date'] == end_date).sum()}")
    print(f"  Applied Date < start_date: {((df['Applied Date'] < start_date) & df['Applied Date'].notna()).sum()}")
    print(f"  Applied Date > end_date: {((df['Applied Date'] > end_date) & df['Applied Date'].notna()).sum()}")
    
    # Check for timezone issues
    print(f"\nTimezone checks:")
    if df['Applied Date'].notna().any():
        sample_dates = df[df['Applied Date'].notna()]['Applied Date'].head(5)
        print(f"  Sample Applied Dates:")
        for idx, date in sample_dates.items():
            print(f"    {idx}: {date} (tz={date.tz})")
else:
    print(f"\n✅ Counts match: {applied_count_direct}")
