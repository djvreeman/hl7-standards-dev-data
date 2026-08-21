#!/usr/bin/env python3
"""Deep investigation of Applied count discrepancy"""

import pandas as pd
import sys
import os
import csv

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from applied_issues_analyze import parse_time_period, process_data, get_period_metrics

# Load and process data
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

# Method 1: Count issues that transitioned TO Applied during the period (what report uses)
# This is what get_period_metrics() returns as 'r'
applied_mask = df['Applied Date'].notna() & \
              (df['Applied Date'] >= start_date) & \
              (df['Applied Date'] <= end_date)
applied_during_period = df[applied_mask].copy()
applied_during_count = len(applied_during_period)
print(f"\nIssues that transitioned TO Applied during {label}: {applied_during_count}")

# Method 2: Count issues that ARE Applied at the end of the period (current status)
# Check their current status
if 'Status' in df.columns:
    applied_at_end = df[df['Status'] == 'Applied'].copy()
    applied_at_end_count = len(applied_at_end)
    print(f"Issues with Status='Applied' at end of period: {applied_at_end_count}")
    
    # Find issues that were Applied during period but are NOT Applied now
    applied_during_not_now = applied_during_period[
        applied_during_period['Status'] != 'Applied'
    ]
    print(f"\nIssues Applied during period but NOT Applied now: {len(applied_during_not_now)}")
    
    if len(applied_during_not_now) > 0:
        print("\nTheir current statuses:")
        print(applied_during_not_now['Status'].value_counts())
        
        print("\nSample issues (first 10):")
        cols_to_show = ['Issue', 'Created Date', 'Applied Date', 'Status']
        available_cols = [c for c in cols_to_show if c in applied_during_not_now.columns]
        print(applied_during_not_now[available_cols].head(10).to_string())
    
    # Find issues that ARE Applied now but were NOT Applied during this period
    applied_now_not_during = applied_at_end[
        ~applied_at_end.index.isin(applied_during_period.index)
    ]
    print(f"\nIssues Applied now but NOT Applied during {label}: {len(applied_now_not_during)}")
    
    if len(applied_now_not_during) > 0:
        print("\nSample issues (first 10):")
        available_cols = [c for c in cols_to_show if c in applied_now_not_during.columns]
        print(applied_now_not_during[available_cols].head(10).to_string())
        
        # Check their Applied Date
        print("\nApplied Dates for these issues:")
        print(applied_now_not_during['Applied Date'].describe())
        print(f"\nApplied Dates before {label}: {((applied_now_not_during['Applied Date'] < start_date) & applied_now_not_during['Applied Date'].notna()).sum()}")
        print(f"Applied Dates after {label}: {((applied_now_not_during['Applied Date'] > end_date) & applied_now_not_during['Applied Date'].notna()).sum()}")
        print(f"Applied Dates null: {applied_now_not_during['Applied Date'].isna().sum()}")

# Method 3: Check for issues that went straight to Applied (no Resolved - Change Required transition)
if 'Resolved to Applied Date' in df.columns:
    direct_to_applied = applied_during_period[
        applied_during_period['Resolved to Applied Date'].isna()
    ]
    print(f"\nIssues that went straight to Applied (no valid transition): {len(direct_to_applied)}")
    
    if len(direct_to_applied) > 0:
        print("These issues have Applied Date but no Resolved to Applied Date")
        print("Sample (first 10):")
        cols_to_show = ['Issue', 'Created Date', 'Applied Date', 'Resolved to Applied Date', 'Status']
        available_cols = [c for c in cols_to_show if c in direct_to_applied.columns]
        print(direct_to_applied[available_cols].head(10).to_string())

# Check what get_period_metrics actually returns
n, r, b, _, _, _ = get_period_metrics(df, '2025')
print(f"\nget_period_metrics Applied count (r): {r}")
print(f"Direct calculation: {applied_during_count}")
print(f"Difference: {abs(r - applied_during_count)}")

# The report shows 2,481, so let's see what might be different
print(f"\nReport shows: 2,481")
print(f"QA calculates: {applied_during_count}")
print(f"Difference: {2481 - applied_during_count}")

# Check if there are issues with Applied Date exactly at boundaries
print(f"\nBoundary checks:")
print(f"Applied Date == start_date: {(df['Applied Date'] == start_date).sum()}")
print(f"Applied Date == end_date: {(df['Applied Date'] == end_date).sum()}")
print(f"Applied Date < start_date: {((df['Applied Date'] < start_date) & df['Applied Date'].notna()).sum()}")
print(f"Applied Date > end_date: {((df['Applied Date'] > end_date) & df['Applied Date'].notna()).sum()}")

# Check for issues with Applied Date in 2025 but outside our calculated range
all_2025_applied = df[
    df['Applied Date'].notna() & 
    (df['Applied Date'].dt.year == 2025)
]
print(f"\nAll issues with Applied Date in year 2025: {len(all_2025_applied)}")

# Find the 6 issues that might be the difference
if len(all_2025_applied) > applied_during_count:
    extra_issues = all_2025_applied[~all_2025_applied.index.isin(applied_during_period.index)]
    print(f"\nIssues with Applied Date in 2025 but not in our mask: {len(extra_issues)}")
    if len(extra_issues) > 0:
        print("\nThese issues:")
        cols_to_show = ['Issue', 'Created Date', 'Applied Date', 'Status']
        available_cols = [c for c in cols_to_show if c in extra_issues.columns]
        print(extra_issues[available_cols].head(20).to_string())
        
        # Check their Applied Dates
        print("\nApplied Dates:")
        for idx, row in extra_issues.head(10).iterrows():
            applied_date = row.get('Applied Date')
            if pd.notna(applied_date):
                print(f"  {row.get('Issue', idx)}: {applied_date} (vs start={start_date}, end={end_date})")
                print(f"    >= start: {applied_date >= start_date}, <= end: {applied_date <= end_date}")
