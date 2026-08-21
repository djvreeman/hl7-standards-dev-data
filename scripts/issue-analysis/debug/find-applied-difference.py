#!/usr/bin/env python3
"""Find the 6-issue difference in Applied count"""

import pandas as pd
import sys
import os
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from applied_issues_analyze import parse_time_period, process_data, get_period_metrics

csv_file = 'data/working/issue-analysis/2025/2025-AllYear/2025-all-resolved-issues-enhanced-v3.csv'

print("Loading data...")
try:
    df = pd.read_csv(csv_file, quoting=csv.QUOTE_MINIMAL, doublequote=True)
except:
    df = pd.read_csv(csv_file)

df.columns = df.columns.str.strip()
if 'WG Name' not in df.columns and 'WG' in df.columns:
    df.rename(columns={'WG': 'WG Name'}, inplace=True)

print("Processing data...")
df = process_data(df, ['2025'], history_json_file=None)

start_date, end_date, label = parse_time_period('2025')

# What get_period_metrics calculates (what report uses)
n, r, b, _, _, _ = get_period_metrics(df, '2025')
print(f"\nget_period_metrics Applied count (r): {r}")

# Direct calculation (what QA uses)
applied_mask = df['Applied Date'].notna() & \
              (df['Applied Date'] >= start_date) & \
              (df['Applied Date'] <= end_date)
direct_count = applied_mask.sum()
print(f"Direct calculation: {direct_count}")

print(f"\nReport shows: 2,481")
print(f"Expected from get_period_metrics: {r}")
print(f"Expected from direct calc: {direct_count}")

# Check if r matches direct_count
if r != direct_count:
    print(f"\n⚠️ get_period_metrics returns {r} but direct calc gives {direct_count}")
else:
    print(f"\n✅ get_period_metrics matches direct calculation: {r}")

# The difference is 2481 - direct_count = 6
# So the report has 6 MORE issues than we calculate
# Let's check what those 6 might be

# Check for issues with Applied Date that might be counted differently
all_with_applied_date = df[df['Applied Date'].notna()].copy()
print(f"\nTotal issues with Applied Date: {len(all_with_applied_date)}")

# Check their statuses
if 'Status' in all_with_applied_date.columns:
    print("\nStatus distribution of issues with Applied Date:")
    print(all_with_applied_date['Status'].value_counts())

# Check issues Applied in 2025 by year
applied_2025_by_year = all_with_applied_date[all_with_applied_date['Applied Date'].dt.year == 2025]
print(f"\nIssues with Applied Date in year 2025: {len(applied_2025_by_year)}")

# Check which ones are in our mask
in_mask = applied_2025_by_year[applied_mask[applied_2025_by_year.index]]
print(f"Issues in our mask: {len(in_mask)}")
print(f"Difference: {len(applied_2025_by_year) - len(in_mask)}")

# Find issues in 2025 but not in mask
not_in_mask = applied_2025_by_year[~applied_mask[applied_2025_by_year.index]]
if len(not_in_mask) > 0:
    print(f"\nIssues with Applied Date in 2025 but NOT in mask ({len(not_in_mask)}):")
    print("\nSample (first 20):")
    cols = ['Issue', 'Applied Date', 'Status']
    available = [c for c in cols if c in not_in_mask.columns]
    print(not_in_mask[available].head(20))
    
    # Check why they're not in mask
    print("\nChecking boundary conditions...")
    for idx, row in not_in_mask.head(10).iterrows():
        ad = row['Applied Date']
        print(f"Issue {row.get('Issue', idx)}: Applied Date = {ad}")
        print(f"  >= start ({start_date}): {ad >= start_date}")
        print(f"  <= end ({end_date}): {ad <= end_date}")
        print(f"  Year: {ad.year if pd.notna(ad) else 'NaN'}")
