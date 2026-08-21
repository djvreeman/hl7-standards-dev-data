#!/usr/bin/env python3
"""Debug script to investigate Applied count discrepancy"""

import pandas as pd
import sys
import os
import csv

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from applied_issues_analyze import parse_time_period, process_data, get_period_metrics

# Load the data
csv_file = 'data/working/issue-analysis/2025/2025-AllYear/2025-all-resolved-issues-enhanced-v3.csv'
print(f"Loading {csv_file}...")

try:
    df = pd.read_csv(csv_file, quoting=csv.QUOTE_MINIMAL, doublequote=True)
except:
    df = pd.read_csv(csv_file)

df.columns = df.columns.str.strip()

# Handle column name variations
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

# Count Applied issues using the same logic as get_period_metrics
applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
applied_count = applied_mask.sum()

print(f"\nApplied count: {applied_count}")

# Get period metrics
n, r, b, _, _, _ = get_period_metrics(df, '2025')
print(f"get_period_metrics Applied count (r): {r}")

# Check for issues at boundaries
print(f"\nChecking boundary conditions...")
print(f"Applied Date min: {df[applied_mask]['Applied Date'].min()}")
print(f"Applied Date max: {df[applied_mask]['Applied Date'].max()}")

# Check for issues exactly at boundaries
at_start = (df['Applied Date'] == start_date).sum()
at_end = (df['Applied Date'] == end_date).sum()
print(f"Issues with Applied Date exactly at start: {at_start}")
print(f"Issues with Applied Date exactly at end: {at_end}")

# Check for issues just outside boundaries
before_start = ((df['Applied Date'] < start_date) & df['Applied Date'].notna()).sum()
after_end = ((df['Applied Date'] > end_date) & df['Applied Date'].notna()).sum()
print(f"Issues with Applied Date before start: {before_start}")
print(f"Issues with Applied Date after end: {after_end}")

# Check if there are issues with Applied Date in 2025 but not matching the mask
all_2025_applied = df[
    df['Applied Date'].notna() & 
    (df['Applied Date'].dt.year == 2025)
]
print(f"\nAll issues with Applied Date in year 2025: {len(all_2025_applied)}")

# Find issues that are in 2025 but not in the mask
in_2025_not_in_mask = all_2025_applied[~applied_mask[all_2025_applied.index]]
if len(in_2025_not_in_mask) > 0:
    print(f"\nIssues in 2025 but not matching mask: {len(in_2025_not_in_mask)}")
    print("Sample dates:")
    print(in_2025_not_in_mask[['Issue', 'Applied Date']].head(10))
