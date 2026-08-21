#!/usr/bin/env python3
"""Debug script to investigate why sub-period totals don't match overall total"""

import pandas as pd
import sys
import os

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from applied_issues_analyze import parse_time_period, find_periods_in_period

# Load the data
csv_file = 'data/working/issue-analysis/2025/2025-AllYear/2025-all-resolved-issues-enhanced-v3.csv'
print(f"Loading {csv_file}...")
df = pd.read_csv(csv_file)
df.columns = df.columns.str.strip()

# Convert dates
df['Created Date'] = pd.to_datetime(df['Created Date'], errors='coerce', utc=True)

# Parse periods
year_start, year_end, year_label = parse_time_period('2025')
print(f"\nYear 2025: {year_start} to {year_end}")

sub_periods = find_periods_in_period('2025')
print(f"Sub-periods: {sub_periods}\n")

# Count issues in year
year_mask = (df['Created Date'] >= year_start) & (df['Created Date'] <= year_end)
year_count = year_mask.sum()
print(f"Issues in year 2025: {year_count}")

# Count issues in each sub-period
sub_period_counts = {}
for sp in sub_periods:
    sp_start, sp_end, sp_label = parse_time_period(sp)
    sp_mask = (df['Created Date'] >= sp_start) & (df['Created Date'] <= sp_end)
    sp_count = sp_mask.sum()
    sub_period_counts[sp_label] = sp_count
    print(f"Issues in {sp_label}: {sp_count} ({sp_start} to {sp_end})")

sub_period_sum = sum(sub_period_counts.values())
print(f"\nSum of sub-periods: {sub_period_sum}")
print(f"Difference: {year_count - sub_period_sum}")

# Find issues that are in year but not in any sub-period
in_year = df[year_mask].copy()
in_sub_period = pd.Series(False, index=df.index)

for sp in sub_periods:
    sp_start, sp_end, _ = parse_time_period(sp)
    sp_mask = (df['Created Date'] >= sp_start) & (df['Created Date'] <= sp_end)
    in_sub_period = in_sub_period | sp_mask

not_in_sub_period = in_year[~in_sub_period[year_mask]]
print(f"\nIssues in year but not in any sub-period: {len(not_in_sub_period)}")

if len(not_in_sub_period) > 0:
    print("\nSample issues:")
    print(not_in_sub_period[['Issue', 'Created Date']].head(10))
    
    # Check date ranges
    print(f"\nMin Created Date in year: {in_year['Created Date'].min()}")
    print(f"Max Created Date in year: {in_year['Created Date'].max()}")
    print(f"\nMin Created Date not in sub-periods: {not_in_sub_period['Created Date'].min()}")
    print(f"Max Created Date not in sub-periods: {not_in_sub_period['Created Date'].max()}")

# Check for issues in multiple sub-periods (shouldn't happen)
print("\nChecking for overlaps...")
for i, sp1 in enumerate(sub_periods):
    for sp2 in sub_periods[i+1:]:
        sp1_start, sp1_end, sp1_label = parse_time_period(sp1)
        sp2_start, sp2_end, sp2_label = parse_time_period(sp2)
        
        sp1_mask = (df['Created Date'] >= sp1_start) & (df['Created Date'] <= sp1_end)
        sp2_mask = (df['Created Date'] >= sp2_start) & (df['Created Date'] <= sp2_end)
        
        overlap = (sp1_mask & sp2_mask).sum()
        if overlap > 0:
            print(f"WARNING: {overlap} issues in both {sp1_label} and {sp2_label}")
