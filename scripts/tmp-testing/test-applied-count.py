#!/usr/bin/env python3
"""Test script to find the exact 6-issue discrepancy"""

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
if 'Specification Display Name' not in df.columns and 'Specification' in df.columns:
    df.rename(columns={'Specification': 'Specification Display Name'}, inplace=True)

print(f"Initial row count: {len(df)}")

# Check for duplicates BEFORE processing
if 'Issue' in df.columns:
    initial_count = len(df)
    duplicates = df[df.duplicated(subset=['Issue'], keep=False)]
    if len(duplicates) > 0:
        print(f"\nFound {len(duplicates)} rows with duplicate Issue keys:")
        dup_counts = duplicates['Issue'].value_counts()
        print(f"  Unique duplicate issues: {len(dup_counts)}")
        print(f"  Sample duplicates:\n{dup_counts.head(10)}")
        
        # Show the actual duplicate rows
        print(f"\nFirst 10 duplicate rows:")
        print(duplicates[['Issue', 'Applied Date', 'Created Date']].head(10).to_string())
    
    # Remove duplicates
    df = df.drop_duplicates(subset=['Issue'], keep='first')
    duplicate_count = initial_count - len(df)
    if duplicate_count > 0:
        print(f"\nRemoved {duplicate_count} duplicate rows. New count: {len(df)}")

print("\nProcessing data...")
df = process_data(df, ['2025'], history_json_file=None)

if df is None:
    print("ERROR: Failed to process data")
    sys.exit(1)

start_date, end_date, label = parse_time_period('2025')
print(f"\nPeriod: {label}")
print(f"Start: {start_date}")
print(f"End: {end_date}")

# Method 1: get_period_metrics
n, r, b, _, _, _ = get_period_metrics(df, '2025')
print(f"\nget_period_metrics Applied count: {r}")

# Method 2: Direct calculation
applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
direct_count = applied_mask.sum()
print(f"Direct calculation: {direct_count}")

if r != direct_count:
    print(f"\n⚠️ MISMATCH: get_period_metrics={r}, direct={direct_count}, difference={r - direct_count}")
    
    # Find which issues are different
    # Recalculate get_period_metrics logic
    start_date2, end_date2, label2 = parse_time_period('2025')
    applied_mask2 = df['Applied Date'].notna() & (df['Applied Date'] >= start_date2) & (df['Applied Date'] <= end_date2)
    count2 = applied_mask2.sum()
    print(f"Re-check: start_date match={start_date == start_date2}, end_date match={end_date == end_date2}")
    print(f"Re-check count: {count2}")
    
    # Check for issues that might be counted differently
    if 'Issue' in df.columns:
        applied_issues = df[applied_mask].copy()
        print(f"\nIssues in direct mask ({len(applied_issues)}):")
        print(f"  First 5: {applied_issues['Issue'].head(5).tolist()}")
        print(f"  Last 5: {applied_issues['Issue'].tail(5).tolist()}")
        
        # Check if there are any issues with Applied Date that fall outside our range
        all_applied = df[df['Applied Date'].notna()].copy()
        print(f"\nTotal issues with Applied Date: {len(all_applied)}")
        
        # Check for issues in 2025 but outside our exact range
        year_2025_mask = all_applied['Applied Date'].dt.year == 2025
        year_2025_issues = all_applied[year_2025_mask]
        print(f"Issues with Applied Date in year 2025: {len(year_2025_issues)}")
        
        not_in_range = year_2025_issues[~applied_mask[year_2025_issues.index]]
        if len(not_in_range) > 0:
            print(f"\n⚠️ Found {len(not_in_range)} issues with Applied Date in 2025 but outside period range:")
            print(not_in_range[['Issue', 'Applied Date']].head(10).to_string())
else:
    print(f"\n✅ get_period_metrics matches direct calculation: {r}")

print(f"\nReport shows: 2,481")
print(f"Expected: {r if r == direct_count else direct_count}")
print(f"Difference from report: {2481 - (r if r == direct_count else direct_count)}")
