#!/usr/bin/env python3
# =============================================================================
# HL7 Jira Issue Resolution Summary Report Generator
#
# Description:
# This script analyzes HL7 JIRA issue data from a CSV export and generates a
# detailed Markdown report. The report includes summary statistics for new,
# resolved, and unresolved (backlog) issues, resolution times (average, median,
# 80th percentile), performance bands, issue reporter insights, and breakdowns
# by realm, working group, specification, and product family.
#
# Features:
# - Time period-based metrics for any combination of years or trimesters (e.g., 2025, 2025T1)
# - Derived fields including days to resolution and performance band
# - Reporter analysis, including new contributors and top issue submitters
# - Breakdown by issue type (if available in the data)
# - Markdown report with automatic Table of Contents and section anchors
# - YAML-configurable HL7 staff filter for excluding internal submitters from rankings
#
# Accepted Time Period Formats:
#   - Full year: '2024'
#   - Trimester: '2025T1', '2025T2', '2025T3'
#   - Ranges: '2023-2025T2', '2024T2-2025T1'
#
# Performance Bands:
#   - 🏎️ Presto: ≤ 60 days
#   - 🚴 Allegro: 61–180 days
#   - 🚶 Andante: 181–365 days
#   - 🐢 Adagio: > 365 days
#
# Requirements:
#   - Python 3.7+
#   - pandas, numpy, pyyaml
#
# Inputs:
#   - CSV file with issue data (must include columns: "Created Date", "Resolution Date", "Reporter")
#   - Optional YAML file listing HL7 staff to exclude from reporter rankings
#
# Example YAML structure (`hl7-staff.yaml`):
#   - display_name: Jane Smith
#   - display_name: John Doe
#
# === Example Usage ===
#
# 1. Analyze a full year and generate a report:
#    python analyze-issue-resolution.py \
#       -i "jira-issues.csv" \
#       -o "summary-report.md" \
#       -p 2024
#
# 2. Analyze multiple periods (e.g., a full year plus a specific trimester):
#    python analyze-issue-resolution.py \
#       -i "jira-issues.csv" \
#       -o "summary-report.md" \
#       -p 2024 2025T1
#
# 3. Use a custom YAML staff list for filtering reporters:
#    python analyze-issue-resolution.py \
#       -i "jira-issues.csv" \
#       -o "summary-report.md" \
#       -p 2025T1 \
#       -s "data/working/config/custom-staff.yaml"
#
# Output:
#   - A Markdown file summarizing issue metrics and reporter analysis
#   - Includes detailed breakdown tables and performance insights
#
# Author:
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import pandas as pd
import numpy as np
import re
import yaml
from datetime import datetime
import os

def load_staff_config(config_path):
    """Load HL7 staff configuration from YAML file"""
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as file:
                return yaml.safe_load(file)
        except Exception as e:
            print(f"Warning: Could not load staff config file: {e}")
            return []
    else:
        print(f"Warning: Staff config file not found at {config_path}")
        return []

def parse_time_period(period_str):
    """Parse a time period string like '2025T1', '2024', or '2024-2025T1' into start and end dates"""
    # Range format: '2024-2025T1'
    range_match = re.match(r'^(\d{4}(?:T[1-3])?)-(\d{4}(?:T[1-3])?)$', period_str)
    if range_match:
        # Get start and end periods
        start_period = range_match.group(1)
        end_period = range_match.group(2)
        
        # Parse start and end dates
        start_date, _, _ = parse_time_period(start_period)
        _, end_date, _ = parse_time_period(end_period)
        
        # Create label
        label = f"{start_period}-{end_period}"
        return start_date, end_date, label
    
    # Full year format: '2024'
    full_year_match = re.match(r'^(\d{4})$', period_str)
    if full_year_match:
        year = int(full_year_match.group(1))
        start_date = pd.Timestamp(year=year, month=1, day=1, tz='UTC')
        end_date = pd.Timestamp(year=year, month=12, day=31, tz='UTC')
        label = f"{year}"
        return start_date, end_date, label
    
    # Period format: '2025T1', '2024T2', etc.
    tri_match = re.match(r'^(\d{4})T([1-3])$', period_str)
    if tri_match:
        year = int(tri_match.group(1))
        tri = tri_match.group(2)
        
        if tri == '1':
            start_date = pd.Timestamp(year=year, month=1, day=1, tz='UTC')
            end_date = pd.Timestamp(year=year, month=4, day=30, tz='UTC')
        elif tri == '2':
            start_date = pd.Timestamp(year=year, month=5, day=1, tz='UTC')
            end_date = pd.Timestamp(year=year, month=8, day=31, tz='UTC')
        elif tri == '3':
            start_date = pd.Timestamp(year=year, month=9, day=1, tz='UTC')
            end_date = pd.Timestamp(year=year, month=12, day=31, tz='UTC')
        
        label = f"{year}T{tri}"
        return start_date, end_date, label
    
    # If we got here, the format is invalid
    raise ValueError(f"Invalid time period format: {period_str}. Use 'YYYY', 'YYYYT[1-3]', or 'YYYY[-T[1-3]]-YYYY[-T[1-3]]'")

def get_period_label(start_date, end_date):
    """Get a human-readable label for a date range"""
    start_str = start_date.strftime("%B %d, %Y")
    end_str = end_date.strftime("%B %d, %Y")
    return f"{start_str} to {end_str}"

def get_tri_section(month_num):
    """Convert month number to period label"""
    if pd.isna(month_num):
        return "Unknown"
    month_num = int(month_num)
    if month_num in [1, 2, 3, 4]:
        return "T1"
    elif month_num in [5, 6, 7, 8]:
        return "T2"
    elif month_num in [9, 10, 11, 12]:
        return "T3"
    else:
        return "Unknown"

def process_data(df, analysis_periods):
    """Process dataframe and add analysis fields"""
    # Convert dates to datetime with UTC timezone
    df['Created Date'] = pd.to_datetime(df['Created Date'], errors='coerce', utc=True)
    df['Resolution Date'] = pd.to_datetime(df['Resolution Date'], errors='coerce', utc=True)
    
    # Add basic derived fields
    df['is_resolved'] = df['Resolution Date'].notnull()
    df['days_to_resolution'] = (df['Resolution Date'] - df['Created Date']).dt.total_seconds() / 86400.0
    
    # Add month and period fields
    df['creation_month'] = df['Created Date'].dt.month
    df['creation_year'] = df['Created Date'].dt.year
    df['creation_tri'] = df['creation_month'].apply(get_tri_section)
    df['resolution_month'] = df['Resolution Date'].dt.month
    df['resolution_year'] = df['Resolution Date'].dt.year
    df['resolution_tri'] = df['resolution_month'].apply(get_tri_section)
    
    # Create period analysis flags
    for period_str in analysis_periods:
        start_date, end_date, label = parse_time_period(period_str)
        
        # Issues created in this period
        df[f'created_in_{label}'] = (
            (df['Created Date'] >= start_date) & 
            (df['Created Date'] <= end_date)
        )
        
        # Issues resolved in this period
        df[f'resolved_in_{label}'] = (
            df['is_resolved'] & 
            (df['Resolution Date'] >= start_date) & 
            (df['Resolution Date'] <= end_date)
        )
        
        # Backlog at end of period (created before or during, not resolved or resolved after)
        df[f'backlog_at_{label}_end'] = (
            (df['Created Date'] <= end_date) & 
            ((~df['is_resolved']) | (df['Resolution Date'] > end_date))
        )
    
    return df

def get_period_metrics(df, period_str):
    """Get metrics for a specific analysis period"""
    _, _, label = parse_time_period(period_str)
    
    # Count basic metrics
    new_issues = df[f'created_in_{label}'].sum()
    resolved_issues = df[f'resolved_in_{label}'].sum()
    backlog = df[f'backlog_at_{label}_end'].sum()
    
    # Calculate resolution times
    times = df.loc[df[f'resolved_in_{label}'], 'days_to_resolution']
    
    if not times.empty:
        ave = times.mean()
        med = times.median()
        p80 = times.quantile(0.8)
    else:
        ave = med = p80 = None
    
    return new_issues, resolved_issues, backlog, ave, med, p80

def find_periods_in_period(period_str):
    """Find all periods within a period"""
    start_date, end_date, _ = parse_time_period(period_str)
    
    tri_periods = []
    
    # Get years covered
    start_year = start_date.year
    end_year = end_date.year
    
    # For each year
    for year in range(start_year, end_year + 1):
        # Determine periods to include
        if year == start_year:
            start_month = start_date.month
            start_tri = (start_month - 1) // 4 + 1
        else:
            start_tri = 1
            
        if year == end_year:
            end_month = end_date.month
            end_tri = (end_month - 1) // 4 + 1
        else:
            end_tri = 3
        
        # Add periods
        for tri in range(start_tri, end_tri + 1):
            tri_periods.append(f"{year}T{tri}")
    
    return tri_periods

def get_tri_metrics(df, tri_str):
    """Get metrics for a specific period"""
    start_date, end_date, label = parse_time_period(tri_str)
    
    # New issues in this period
    new_mask = (df['Created Date'] >= start_date) & (df['Created Date'] <= end_date)
    new_issues = new_mask.sum()
    
    # Resolved issues in this period
    resolved_mask = df['is_resolved'] & (df['Resolution Date'] >= start_date) & (df['Resolution Date'] <= end_date)
    resolved = resolved_mask.sum()
    
    # Backlog at end of period
    backlog_mask = (df['Created Date'] <= end_date) & ((~df['is_resolved']) | (df['Resolution Date'] > end_date))
    backlog = backlog_mask.sum()
    
    # Resolution times
    times = df.loc[resolved_mask, 'days_to_resolution']
    if not times.empty:
        ave = times.mean()
        med = times.median()
        p80 = times.quantile(0.8)
    else:
        ave = med = p80 = None
    
    return label, new_issues, resolved, backlog, ave, med, p80

def get_performance_band(p80_value):
    """Return the performance band label based on P80 value"""
    if p80_value is None:
        return "N/A"
    if p80_value <= 60:
        return "🏎️ Presto"
    elif p80_value <= 180:
        return "🚴 Allegro"
    elif p80_value <= 365:
        return "🚶 Andante"
    else:
        return "🐢 Adagio"

def analyze_submitters(df, period_str, staff_list):
    """Analyze issue reporters for a specific period"""
    start_date, end_date, label = parse_time_period(period_str)
    
    # Get earliest date in the dataset
    earliest_date = df['Created Date'].min()
    
    # Get all data from start of dataset through end of analysis period
    historical_mask = (df['Created Date'] >= earliest_date) & (df['Created Date'] <= end_date)
    historical_df = df[historical_mask]
    
    # Get all reporters through the end of the analysis period
    all_reporters = set(historical_df['Reporter'].dropna().unique())
    total_reporters_ever = len(all_reporters)
    
    # Get reporters before this period
    before_period_mask = df['Created Date'] < start_date
    before_period_reporters = set(df.loc[before_period_mask, 'Reporter'].dropna().unique())
    
    # Get reporters in this period
    period_mask = (df['Created Date'] >= start_date) & (df['Created Date'] <= end_date)
    period_reporters = set(df.loc[period_mask, 'Reporter'].dropna().unique())
    total_reporters_in_period = len(period_reporters)
    
    # Find new reporters in this period
    new_reporters = period_reporters - before_period_reporters
    total_new_reporters = len(new_reporters)
    
    # Calculate percentage of new reporters relative to this period
    if total_reporters_in_period > 0:
        new_reporter_percent = (total_new_reporters / total_reporters_in_period) * 100
    else:
        new_reporter_percent = 0
    
    # Get top reporters during this period (excluding staff)
    period_reporter_counts = df[period_mask].groupby('Reporter').size().reset_index(name='Issue Count')
    period_reporter_counts = period_reporter_counts[~period_reporter_counts['Reporter'].isin(staff_list)]
    period_reporter_counts = period_reporter_counts.sort_values(by='Issue Count', ascending=False)
    top_period_reporters = period_reporter_counts.head(10)
    
    # Get top reporters of all time through end of analysis period (excluding staff)
    all_time_reporter_counts = historical_df.groupby('Reporter').size().reset_index(name='Issue Count')
    all_time_reporter_counts = all_time_reporter_counts[~all_time_reporter_counts['Reporter'].isin(staff_list)]
    all_time_reporter_counts = all_time_reporter_counts.sort_values(by='Issue Count', ascending=False)
    top_all_time_reporters = all_time_reporter_counts.head(10)
    
    return {
        'total_reporters_ever': total_reporters_ever,
        'total_reporters_in_period': total_reporters_in_period,
        'total_new_reporters': total_new_reporters,
        'new_reporter_percent': new_reporter_percent,
        'top_period_reporters': top_period_reporters,
        'top_all_time_reporters': top_all_time_reporters
    }

def analyze_issue_types(df, period_str):
    """Analyze issue types for a specific period"""
    start_date, end_date, label = parse_time_period(period_str)
    
    # Skip if the Issue Type column doesn't exist
    if 'Issue Type' not in df.columns:
        return None

    # Get issues created in this period
    period_mask = (df['Created Date'] >= start_date) & (df['Created Date'] <= end_date)
    period_df = df[period_mask]
    
    # Get issues resolved in this period
    resolved_mask = df['is_resolved'] & (df['Resolution Date'] >= start_date) & (df['Resolution Date'] <= end_date)
    resolved_df = df[resolved_mask]
    
    # Count issues by type
    issue_type_counts = period_df['Issue Type'].value_counts().reset_index()
    issue_type_counts.columns = ['Issue Type', 'New Count']
    
    # Count resolved issues by type
    resolved_counts = resolved_df['Issue Type'].value_counts().reset_index()
    resolved_counts.columns = ['Issue Type', 'Resolved Count']
    
    # Calculate average resolution time by type
    resolution_times = resolved_df.groupby('Issue Type')['days_to_resolution'].agg(['mean', 'median', 'count']).reset_index()
    resolution_times.columns = ['Issue Type', 'Avg Days', 'Median Days', 'Resolved Count']
    
    # Merge the data
    merged = pd.merge(issue_type_counts, resolution_times, on='Issue Type', how='outer')
    
    # Calculate backlog at end of period
    backlog_mask = (df['Created Date'] <= end_date) & ((~df['is_resolved']) | (df['Resolution Date'] > end_date))
    backlog_df = df[backlog_mask]
    backlog_counts = backlog_df['Issue Type'].value_counts().reset_index()
    backlog_counts.columns = ['Issue Type', 'Backlog Count']
    
    # Merge backlog data
    merged = pd.merge(merged, backlog_counts, on='Issue Type', how='outer')
    
    # Fill NaN values with 0 for counts and N/A for time metrics
    merged['New Count'] = merged['New Count'].fillna(0).astype(int)
    merged['Resolved Count'] = merged['Resolved Count'].fillna(0).astype(int)
    merged['Backlog Count'] = merged['Backlog Count'].fillna(0).astype(int)
    
    # Sort by New Count (descending)
    merged = merged.sort_values(by='New Count', ascending=False)
    
    # Calculate P80 for each issue type
    def calculate_p80(issue_type):
        times = resolved_df.loc[resolved_df['Issue Type'] == issue_type, 'days_to_resolution']
        if not times.empty and len(times) >= 5:  # Only calculate P80 if we have at least 5 data points
            return times.quantile(0.8)
        return None
    
    # Add P80 column
    merged['P80 Days'] = merged['Issue Type'].apply(calculate_p80)
    
    # Add performance band
    merged['Performance'] = merged['P80 Days'].apply(get_performance_band)
    
    return merged

def generate_report(df, analysis_periods, staff_list):
    """Generate full markdown report"""
    md = []
    
    # Get the primary analysis period (first one specified)
    primary_period = analysis_periods[0]
    start_date, end_date, label = parse_time_period(primary_period)
    human_readable_period = get_period_label(start_date, end_date)
    
    # Title and analysis period
    md.append("# Issue Resolution Summary Report\n")
    md.append(f"> **Analysis Period:** {human_readable_period}\n")
    
    # Add table of contents
    md.append("## Table of Contents\n")
    md.append("- [How to Read This Report](#how-to-read-this-report)")
    md.append("- [Overall Summary](#overall-summary)")
    md.append("- [Summary by Analysis Period](#summary-by-analysis-period)")
    
    for period in analysis_periods:
        _, _, label = parse_time_period(period)
        # Fix anchor links - converting to lowercase and replacing spaces with hyphens
        anchor = f"breakdown-by-period-within-{label.lower()}"
        md.append(f"- [Breakdown by Period within {label}](#{anchor})")
    
    md.append("- [Issue Reporters](#issue-reporters)")
    
    # Add Issue Type section to TOC if the column exists
    if 'Issue Type' in df.columns:
        md.append("- [Breakdown by Issue Type](#breakdown-by-issue-type)")
    
    md.append("- [Breakdown by Realm](#breakdown-by-realm)")
    md.append("- [Breakdown by WG Name and Realm](#breakdown-by-wg-name-and-realm)")
    md.append("- [Breakdown by WG Name](#breakdown-by-wg-name)")
    md.append("- [Breakdown by Specification](#breakdown-by-specification)")
    md.append("- [Breakdown by Product Family](#breakdown-by-product-family)")
    md.append("")
    
    # How to Read This Report (after TOC as requested)
    md.append("## How to Read This Report\n")
    md.append("### Key Metrics\n")
    md.append("- **New:** Issues created during the specified time period")
    md.append("- **Resolved:** Issues with a resolution date during the specified time period. Note: the resolution date in Jira is assigned early -- when an issue is given a (proposed) disposition. This is not necessarily when the change is applied to the specification.")
    md.append("- **Backlog:** Issues created at any time before the end of the specified period that remain unresolved at the end of that period")
    md.append("- **Ave (days):** Average time to resolution for issues resolved in this period")
    md.append("- **Median (days):** Median time to resolution (50% of issues resolved faster than this)")
    md.append("- **P80 (days):** 80th percentile resolution time (80% of issues resolved faster than this)\n")
    
    md.append("### Time Periods\n")
    md.append("Periods are defined as:")
    md.append("- **T1:** January, February, March, April")
    md.append("- **T2:** May, June, July, August")
    md.append("- **T3:** September, October, November, December\n")
    
    md.append("### Performance Bands\n")
    md.append("| Band                  | P80 Range (days) | Interpretation                                                                             |")
    md.append("|-----------------------|------------------|--------------------------------------------------------------------------------------------|")
    md.append("| **🏎️ Presto**         | ≤ 60             | 80% of tickets close within two months. Very fast, high performance, hypercar speed.                                      |")
    md.append("| **🚴 Allegro**              | 61 – 180         | 80% close within six months. Fast, responsive, moving quickly.                    |")
    md.append("| **🚶 Andante**         | 181 – 365        | 80% close within a year. Moderate pace, moving steady, but with opportunities to accelerate.         |")
    md.append("| **🐢 Adagio** | > 365            | 20% of tickets take *more* than a year. Very slow. Let's look for bottlenecks or resource gaps.  |\n")
    md.append("_Note: For fun, these performance band labels are inspired by the music vocabulary for tempo. For more information, see the [Tempo article on Wikipedia](https://en.wikipedia.org/wiki/Tempo)._")

    # Overall summary
    total = len(df)
    resolved = df['is_resolved'].sum()
    backlog = total - resolved
    
    # Get earliest and latest dates in dataset
    earliest_date = df['Created Date'].min()
    latest_date = df['Created Date'].max()
    date_range = f"{earliest_date.strftime('%B %d, %Y')} to {latest_date.strftime('%B %d, %Y')}"
    
    times_all = df.loc[df['is_resolved'], 'days_to_resolution']
    if not times_all.empty:
        ave_all = times_all.mean()
        med_all = times_all.median()
        p80_all = times_all.quantile(0.8)
        ave_str = f"{ave_all:.2f}"
        med_str = f"{med_all:.2f}"
        p80_str = f"{p80_all:.2f}"
        band = get_performance_band(p80_all)
    else:
        ave_str = med_str = p80_str = "N/A"
        band = "N/A"
    
    md.append("## Overall Summary\n")
    md.append(f"This summary includes all issues in the dataset from **{date_range}**.\n")
    md.append(f"- **Total Issues:** {total}")
    md.append(f"- **Resolved Issues:** {resolved}")
    md.append(f"- **Current Backlog (Unresolved):** {backlog}")
    md.append(f"- **Ave Resolution Time (days):** {ave_str}")
    md.append(f"- **Median Resolution Time (days):** {med_str}")
    md.append(f"- **P80 Resolution Time (days):** {p80_str}")
    md.append(f"- **Performance Band:** {band}")
    md.append("")
    
    # Summary by Analysis Period
    md.append("## Summary by Analysis Period\n")
    md.append("| Period | New | Resolved | Backlog | Ave (days) | Median (days) | P80 (days) | Performance |")
    md.append("|--------|-----|----------|---------|------------|---------------|------------|------------|")
    
    for period in analysis_periods:
        _, _, label = parse_time_period(period)
        n, r, b, ave, med, p80 = get_period_metrics(df, period)
        
        if ave is not None:
            ave_str = f"{ave:.2f}"
            med_str = f"{med:.2f}"
            p80_str = f"{p80:.2f}"
            band = get_performance_band(p80)
        else:
            ave_str = med_str = p80_str = "N/A"
            band = "N/A"
        
        md.append(f"| {label} | {n} | {r} | {b} | {ave_str} | {med_str} | {p80_str} | {band} |")
    
    md.append("")
    
    # Breakdown by period within each period
    for period in analysis_periods:
        start_date, end_date, label = parse_time_period(period)
        human_readable_range = get_period_label(start_date, end_date)
        
        md.append(f"## Breakdown by Period within {label}\n")
        md.append(f"This breakdown covers **{human_readable_range}**.\n")
        
        md.append("| Period | New | Resolved | Backlog | Ave (days) | Median (days) | P80 (days) | Performance |")
        md.append("|--------|-----|----------|---------|------------|---------------|------------|------------|")
        
        # Get metrics for each period
        tri_periods = find_periods_in_period(period)
        
        for tri in tri_periods:
            tri_label, n, r, b, ave, med, p80 = get_tri_metrics(df, tri)
            
            if ave is not None:
                ave_str = f"{ave:.2f}"
                med_str = f"{med:.2f}"
                p80_str = f"{p80:.2f}"
                band = get_performance_band(p80)
            else:
                ave_str = med_str = p80_str = "N/A"
                band = "N/A"
            
            md.append(f"| {tri_label} | {n} | {r} | {b} | {ave_str} | {med_str} | {p80_str} | {band} |")
        
        md.append("")
    
    # Issue Reporters Analysis
    md.append("## Issue Reporters\n")
    
    # Issue Reporters summary table
    md.append("### Reporter Summary\n")
    md.append("| Period | Total Reporters | New Reporters | % New Reporters |")
    md.append("|--------|------------------|----------------|-----------------|")
    
    # For each analysis period
    for period in analysis_periods:
        _, _, label = parse_time_period(period)
        reporter_data = analyze_submitters(df, period, staff_list)
        
        # Calculate percentage with proper precision
        percent_new = f"{reporter_data['new_reporter_percent']:.1f}%"
        
        md.append(f"| {label} | {reporter_data['total_reporters_in_period']} | {reporter_data['total_new_reporters']} | {percent_new} |")
    
    md.append("")
    
    # Only add leaderboards for the primary analysis period
    primary_period = analysis_periods[0]
    _, _, label = parse_time_period(primary_period)
    reporter_data = analyze_submitters(df, primary_period, staff_list)
    
    # Get end date for the all-time title
    _, end_date, _ = parse_time_period(primary_period)
    end_date_str = end_date.strftime('%B %d, %Y')
    
    # Top reporters for this period
    md.append(f"### Top Reporters for {label}\n")
    md.append("| Rank | Reporter | Issue Count |")
    md.append("|------|----------|-------------|")
    
    for i, (_, row) in enumerate(reporter_data['top_period_reporters'].iterrows(), 1):
        reporter = row['Reporter'] if pd.notnull(row['Reporter']) else "Unknown"
        count = int(row['Issue Count'])
        md.append(f"| {i} | {reporter} | {count} |")
    
    md.append("")
    
    # Top reporters of all time (through end of analysis period)
    md.append(f"### Top Reporters (Through {end_date_str})\n")
    md.append("| Rank | Reporter | Issue Count |")
    md.append("|------|----------|-------------|")
    
    for i, (_, row) in enumerate(reporter_data['top_all_time_reporters'].iterrows(), 1):
        reporter = row['Reporter'] if pd.notnull(row['Reporter']) else "Unknown"
        count = int(row['Issue Count'])
        md.append(f"| {i} | {reporter} | {count} |")
    
    md.append("")
    
    # Add Issue Type Analysis if column exists
    if 'Issue Type' in df.columns:
        md.append("## Breakdown by Issue Type\n")
        
        # For each analysis period
        for period in analysis_periods:
            _, _, period_label = parse_time_period(period)
            issue_type_data = analyze_issue_types(df, period)
            
            if issue_type_data is not None and not issue_type_data.empty:
                md.append(f"### Issue Types for {period_label}\n")
                md.append("| Issue Type | New | Resolved | Backlog | Avg Days | Median Days | P80 Days | Performance |")
                md.append("|------------|-----|----------|---------|----------|-------------|----------|------------|")
                
                for _, row in issue_type_data.iterrows():
                    issue_type = row['Issue Type'] if pd.notnull(row['Issue Type']) else "Unknown"
                    new_count = int(row['New Count'])
                    resolved_count = int(row['Resolved Count']) if pd.notnull(row['Resolved Count']) else 0
                    backlog_count = int(row['Backlog Count']) if pd.notnull(row['Backlog Count']) else 0
                    
                    avg_days = f"{row['Avg Days']:.2f}" if pd.notnull(row['Avg Days']) else "N/A"
                    median_days = f"{row['Median Days']:.2f}" if pd.notnull(row['Median Days']) else "N/A"
                    p80_days = f"{row['P80 Days']:.2f}" if pd.notnull(row['P80 Days']) else "N/A"
                    performance = row['Performance'] if pd.notnull(row['Performance']) else "N/A"
                    
                    md.append(f"| {issue_type} | {new_count} | {resolved_count} | {backlog_count} | {avg_days} | {median_days} | {p80_days} | {performance} |")
                
                md.append("")
        
        # Removed "Issue Types by Realm" and "Issue Types by Workgroup" sections as requested
    
    # Helper function for category breakdowns
    def render_breakdown(title, column):
        md.append(f"## {title}\n")
        
        # Special case for Specification Display Name - include Realm column
        if column == "Specification Display Name":
            md.append(f"| {column} | Realm | Period | New | Resolved | Backlog | Ave (days) | Median (days) | P80 (days) | Performance |")
            md.append("|" + "-" * len(column) + "|-------|--------|-----|----------|---------|------------|---------------|------------|------------|")
            
            # Get categories
            categories = sorted(df[column].dropna().unique())
            
            for category in categories:
                category_df = df[df[column] == category]
                
                # Get the realms for this specification
                realms = category_df['Realm'].dropna().unique()
                
                # If no realms found, use "Unknown"
                if len(realms) == 0:
                    realms = ["Unknown"]
                
                for realm in realms:
                    # Filter by both specification and realm
                    spec_realm_df = category_df[category_df['Realm'] == realm] if pd.notnull(realm) else category_df[category_df['Realm'].isna()]
                    
                    for period in analysis_periods:
                        _, _, label = parse_time_period(period)
                        
                        # Count new issues
                        new_count = spec_realm_df[f'created_in_{label}'].sum()
                        
                        # Count resolved issues
                        resolved_count = spec_realm_df[f'resolved_in_{label}'].sum()
                        
                        # Count backlog
                        backlog_count = spec_realm_df[f'backlog_at_{label}_end'].sum()
                        
                        # Skip rows with no activity for this period (0 new, 0 resolved, 0 backlog)
                        if new_count == 0 and resolved_count == 0 and backlog_count == 0:
                            continue
                        
                        # Calculate resolution times
                        times = spec_realm_df.loc[spec_realm_df[f'resolved_in_{label}'], 'days_to_resolution']
                        
                        if not times.empty and len(times) > 0:
                            ave = times.mean()
                            med = times.median()
                            p80 = times.quantile(0.8)
                            ave_str = f"{ave:.2f}"
                            med_str = f"{med:.2f}"
                            p80_str = f"{p80:.2f}"
                            band = get_performance_band(p80)
                        else:
                            ave_str = med_str = p80_str = "N/A"
                            band = "N/A"
                        
                        realm_display = realm if pd.notnull(realm) else "Unknown"
                        md.append(f"| {category} | {realm_display} | {label} | {new_count} | {resolved_count} | {backlog_count} | {ave_str} | {med_str} | {p80_str} | {band} |")
        else:
            # Original implementation for other columns
            md.append(f"| {column} | Period | New | Resolved | Backlog | Ave (days) | Median (days) | P80 (days) | Performance |")
            md.append("|" + "-" * len(column) + "|--------|-----|----------|---------|------------|---------------|------------|------------|")
            
            # Get categories
            categories = sorted(df[column].dropna().unique())
            
            for category in categories:
                category_df = df[df[column] == category]
                
                for period in analysis_periods:
                    _, _, label = parse_time_period(period)
                    
                    # Count new issues
                    new_count = category_df[f'created_in_{label}'].sum()
                    
                    # Count resolved issues
                    resolved_count = category_df[f'resolved_in_{label}'].sum()
                    
                    # Count backlog
                    backlog_count = category_df[f'backlog_at_{label}_end'].sum()
                    
                    # Skip rows with no activity for this period (0 new, 0 resolved, 0 backlog)
                    if column == "Specification Display Name" and new_count == 0 and resolved_count == 0 and backlog_count == 0:
                        continue
                    
                    # Calculate resolution times
                    times = category_df.loc[category_df[f'resolved_in_{label}'], 'days_to_resolution']
                    
                    if not times.empty and len(times) > 0:
                        ave = times.mean()
                        med = times.median()
                        p80 = times.quantile(0.8)
                        ave_str = f"{ave:.2f}"
                        med_str = f"{med:.2f}"
                        p80_str = f"{p80:.2f}"
                        band = get_performance_band(p80)
                    else:
                        ave_str = med_str = p80_str = "N/A"
                        band = "N/A"
                    
                    md.append(f"| {category} | {label} | {new_count} | {resolved_count} | {backlog_count} | {ave_str} | {med_str} | {p80_str} | {band} |")
        
        md.append("")
    
    # Breakdowns by category
    render_breakdown("Breakdown by Realm", "Realm")
    
    # Breakdown by WG Name and Realm
    md.append("## Breakdown by WG Name and Realm\n")
    grouped = df.groupby(['WG Name', 'Realm']).size().reset_index(name='Total Issues')
    
    # Calculate percentages
    wg_totals = grouped.groupby('WG Name')['Total Issues'].transform('sum')
    grouped['% within WG'] = (grouped['Total Issues'] / wg_totals * 100).round(1)
    grouped = grouped.sort_values(by=['WG Name', 'Total Issues'], ascending=[True, False])
    
    md.append("| WG Name | Realm | Total Issues | % within WG |")
    md.append("|---------|--------|---------------|--------------|")
    
    for _, row in grouped.iterrows():
        wg = row['WG Name'] if pd.notnull(row['WG Name']) else "Unknown"
        realm = row['Realm'] if pd.notnull(row['Realm']) else "Unknown"
        total = int(row['Total Issues'])
        pct = f"{row['% within WG']:.1f}"
        md.append(f"| {wg} | {realm} | {total} | {pct}% |")
    
    md.append("")
    
    # Other breakdowns
    render_breakdown("Breakdown by WG Name", "WG Name")
    render_breakdown("Breakdown by Specification", "Specification Display Name")
    render_breakdown("Breakdown by Product Family", "Product Family")
    
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(
        description="Analyze issue resolutions and generate a markdown summary report with TOC, median, and P80."
    )
    parser.add_argument("-i", "--input", required=True, help="Input CSV file path")
    parser.add_argument("-o", "--output", required=True, help="Output Markdown file path")
    parser.add_argument("-p", "--periods", required=True, nargs="+", 
                       help="Analysis periods in format 'YYYY' (full year) or 'YYYYT[1-3]' (period)")
    parser.add_argument("-s", "--staff-config", default="data/working/config/hl7-staff.yaml",
                       help="Path to HL7 staff configuration file")
    
    args = parser.parse_args()
    
    # Load staff configuration
    print(f"Loading staff configuration from {args.staff_config}")
    staff_config = load_staff_config(args.staff_config)
    staff_list = []
    if staff_config:
        # Extract staff display names (Reporter field)
        for staff in staff_config:
            if 'display_name' in staff:
                staff_list.append(staff['display_name'])
    
    # Load data
    print(f"Loading data from {args.input}")
    df = pd.read_csv(args.input)
    df.columns = df.columns.str.strip()
    
    # Handle column name variations
    if 'WG Name' not in df.columns and 'WG' in df.columns:
        df.rename(columns={'WG':'WG Name'}, inplace=True)
    if 'Specification Display Name' not in df.columns and 'Specification' in df.columns:
        df.rename(columns={'Specification':'Specification Display Name'}, inplace=True)
    
    # Process data
    print(f"Processing data for periods: {', '.join(args.periods)}")
    df = process_data(df, args.periods)
    
    # Generate report
    print("Generating report")
    report = generate_report(df, args.periods, staff_list)
    
    # Save report
    print(f"Writing report to {args.output}")
    with open(args.output, "w") as f:
        f.write(report)
    
    print("Done!")

if __name__ == "__main__":
    main()