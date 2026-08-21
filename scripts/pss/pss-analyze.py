#!/usr/bin/env python3
# =============================================================================
# PSS (Project Scope Statement) Approval Metrics Analyzer and Markdown Report Generator
#
# This script analyzes HL7 PSS approval data to evaluate PSS approvals over time.
#
# It computes approval counts by time period, realm breakdowns, and project 
# facilitator statistics.
#
# === Input Requirements ===
# - A CSV file with PSS approval data that includes:
#     - Issue (PSS number)
#     - Approval Date
#     - Realm
#     - Project Facilitator
#     - Other optional fields (Summary, Creator, Publishing Facilitator)
#
# === Period Format ===
# Periods must be specified in one of the following formats:
#   - 'YYYY'           → Full year (e.g., 2024)
#   - 'YYYYT[1-3]'     → Tri-year quarter (e.g., 2024T2)
#   - 'YYYY[-T[1-3]]-YYYY[-T[1-3]]' → Ranges (e.g., 2023T2–2024T1)
#   - If not specified, analyzes all time
#
# === Output ===
# - A Markdown report file containing:
#     - Overall summary
#     - Counts by time period (T1, T2, T3, and full years)
#     - Breakdowns by Realm
#     - Project Facilitator leaderboards and statistics
#
# === Example Usage ===
# python pss-analyze.py \
#     -i data/working/pss-approved/All\ -\ PSS\ Approved.csv \
#     -o reports/pss_approvals.md
#
# python pss-analyze.py \
#     -i data/working/pss-approved/All\ -\ PSS\ Approved.csv \
#     -o reports/pss_approvals_2025.md \
#     -p 2025
#
# === Dependencies ===
# - pandas
# - numpy
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import pandas as pd
import numpy as np
import re
from datetime import datetime
import os

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
        start_date = pd.Timestamp(year=year, month=1, day=1, hour=0, minute=0, second=0, tz='UTC')
        # End of year: Dec 31 at 23:59:59.999999
        end_date = pd.Timestamp(year=year, month=12, day=31, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        label = f"{year}"
        return start_date, end_date, label
    
    # Period format: '2025T1', '2024T2', etc.
    tri_match = re.match(r'^(\d{4})T([1-3])$', period_str)
    if tri_match:
        year = int(tri_match.group(1))
        tri = tri_match.group(2)
        
        if tri == '1':
            # T1: Jan 1 00:00:00 to Apr 30 23:59:59.999999
            start_date = pd.Timestamp(year=year, month=1, day=1, hour=0, minute=0, second=0, tz='UTC')
            end_date = pd.Timestamp(year=year, month=4, day=30, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        elif tri == '2':
            # T2: May 1 00:00:00 to Aug 31 23:59:59.999999
            start_date = pd.Timestamp(year=year, month=5, day=1, hour=0, minute=0, second=0, tz='UTC')
            end_date = pd.Timestamp(year=year, month=8, day=31, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        elif tri == '3':
            # T3: Sep 1 00:00:00 to Dec 31 23:59:59.999999
            start_date = pd.Timestamp(year=year, month=9, day=1, hour=0, minute=0, second=0, tz='UTC')
            end_date = pd.Timestamp(year=year, month=12, day=31, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        
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

def find_all_years_in_data(df):
    """Find all years present in the Approval Date column"""
    if 'Approval Date' not in df.columns:
        return []
    
    df['Approval Date'] = pd.to_datetime(df['Approval Date'], errors='coerce', utc=True)
    years = df['Approval Date'].dt.year.dropna().unique()
    return sorted([int(y) for y in years if not pd.isna(y)])

def format_count(value):
    """Format a count (integer) with thousands separators"""
    try:
        if value is None:
            return "N/A"
        if pd.isna(value):
            return "N/A"
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "N/A"

def process_data(df, analysis_periods=None):
    """Process dataframe and add analysis fields"""
    # Convert Approval Date to datetime with UTC timezone
    df['Approval Date'] = pd.to_datetime(df['Approval Date'], errors='coerce', utc=True)
    
    # Filter out rows with missing Approval Date
    initial_count = len(df)
    df = df[df['Approval Date'].notna()].copy()
    filtered_count = len(df)
    if initial_count != filtered_count:
        print(f"Note: Filtered out {initial_count - filtered_count} rows with missing Approval Date")
    
    # Add period fields
    df['approval_year'] = df['Approval Date'].dt.year
    df['approval_month'] = df['Approval Date'].dt.month
    df['approval_tri'] = df['approval_month'].apply(get_tri_section)
    
    # Create period analysis flags if periods are specified
    if analysis_periods:
        for period_str in analysis_periods:
            start_date, end_date, label = parse_time_period(period_str)
            
            # PSSs approved in this period
            df[f'approved_in_{label}'] = (
                (df['Approval Date'] >= start_date) & 
                (df['Approval Date'] <= end_date)
            )
    
    return df

def filter_df_to_periods(df, periods):
    """
    Filter the dataframe to rows whose Approval Date falls within ANY of the specified periods.

    This is used to ensure that when an analysis period is requested (e.g., 2026T1), the report
    contains only approvals from that period and does not include later approvals in other totals.
    """
    if not periods:
        return df

    masks = []
    for period_str in periods:
        start_date, end_date, _ = parse_time_period(period_str)
        masks.append((df['Approval Date'] >= start_date) & (df['Approval Date'] <= end_date))

    if not masks:
        return df

    combined_mask = masks[0]
    for m in masks[1:]:
        combined_mask = combined_mask | m

    return df.loc[combined_mask].copy()

def get_period_counts(df, period_str):
    """Get count of PSSs approved in a specific period"""
    start_date, end_date, label = parse_time_period(period_str)
    
    approved_mask = (
        (df['Approval Date'] >= start_date) & 
        (df['Approval Date'] <= end_date)
    )
    
    return approved_mask.sum()

def get_period_counts_by_realm(df, period_str):
    """Get count of PSSs approved in a period, broken down by Realm"""
    start_date, end_date, label = parse_time_period(period_str)
    
    approved_mask = (
        (df['Approval Date'] >= start_date) & 
        (df['Approval Date'] <= end_date)
    )
    
    approved_df = df[approved_mask]
    
    if 'Realm' not in approved_df.columns:
        return None
    
    realm_counts = approved_df['Realm'].value_counts().reset_index()
    realm_counts.columns = ['Realm', 'Count']
    
    # Handle empty/NaN realms
    realm_counts['Realm'] = realm_counts['Realm'].fillna('Unknown')
    
    return realm_counts

def analyze_facilitators(df, period_str=None, staff_list=None):
    """Analyze Project Facilitators for a specific period or all time"""
    if period_str:
        start_date, end_date, label = parse_time_period(period_str)
    else:
        # All time analysis
        start_date = df['Approval Date'].min()
        end_date = df['Approval Date'].max()
        label = "All Time"
    
    # Get earliest date in the dataset
    earliest_date = df['Approval Date'].min()
    
    # Get all data from start of dataset through end of analysis period
    historical_mask = (df['Approval Date'] >= earliest_date) & (df['Approval Date'] <= end_date)
    historical_df = df[historical_mask]
    
    # Get all facilitators through the end of the analysis period
    all_facilitators = set(historical_df['Project Facilitator'].dropna().unique())
    total_facilitators_ever = len(all_facilitators)
    
    # Get facilitators before this period
    before_period_mask = df['Approval Date'] < start_date
    before_period_facilitators = set(df.loc[before_period_mask, 'Project Facilitator'].dropna().unique())
    
    # Get facilitators in this period
    period_mask = (df['Approval Date'] >= start_date) & (df['Approval Date'] <= end_date)
    period_facilitators = set(df.loc[period_mask, 'Project Facilitator'].dropna().unique())
    total_facilitators_in_period = len(period_facilitators)
    
    # Find new facilitators in this period
    new_facilitators = period_facilitators - before_period_facilitators
    total_new_facilitators = len(new_facilitators)
    
    # Calculate percentage of new facilitators relative to this period
    if total_facilitators_in_period > 0:
        new_facilitator_percent = (total_new_facilitators / total_facilitators_in_period) * 100
    else:
        new_facilitator_percent = 0
    
    # Get top facilitators during this period (excluding staff if provided)
    period_facilitator_counts = df[period_mask].groupby('Project Facilitator').size().reset_index(name='PSS Count')
    if staff_list:
        period_facilitator_counts = period_facilitator_counts[~period_facilitator_counts['Project Facilitator'].isin(staff_list)]
    period_facilitator_counts = period_facilitator_counts.sort_values(by='PSS Count', ascending=False)
    top_period_facilitators = period_facilitator_counts.head(10)
    
    # Get top facilitators of all time through end of analysis period (excluding staff if provided)
    all_time_facilitator_counts = historical_df.groupby('Project Facilitator').size().reset_index(name='PSS Count')
    if staff_list:
        all_time_facilitator_counts = all_time_facilitator_counts[~all_time_facilitator_counts['Project Facilitator'].isin(staff_list)]
    all_time_facilitator_counts = all_time_facilitator_counts.sort_values(by='PSS Count', ascending=False)
    top_all_time_facilitators = all_time_facilitator_counts.head(10)
    
    return {
        'total_facilitators_ever': total_facilitators_ever,
        'total_facilitators_in_period': total_facilitators_in_period,
        'total_new_facilitators': total_new_facilitators,
        'new_facilitator_percent': new_facilitator_percent,
        'top_period_facilitators': top_period_facilitators,
        'top_all_time_facilitators': top_all_time_facilitators
    }

def generate_report(df, analysis_periods=None, staff_list=None):
    """Generate full markdown report"""
    md = []
    
    # Determine analysis scope
    if analysis_periods:
        primary_period = analysis_periods[0]
        start_date, end_date, label = parse_time_period(primary_period)
        human_readable_period = get_period_label(start_date, end_date)
        period_title = f" for {label}"
    else:
        # All time analysis
        earliest_date = df['Approval Date'].min()
        latest_date = df['Approval Date'].max()
        human_readable_period = get_period_label(earliest_date, latest_date)
        period_title = " (All Time)"
    
    # Title
    md.append("# PSS Approval Summary Report" + period_title + "\n")
    if analysis_periods:
        md.append(f"> **Analysis Period:** {human_readable_period}\n")
    else:
        md.append(f"> **Date Range:** {human_readable_period}\n")
    
    # Add table of contents
    md.append("## Table of Contents\n")
    md.append("- [Overall Summary](#overall-summary)")
    if analysis_periods:
        md.append("- [Summary by Analysis Period](#summary-by-analysis-period)")
        md.append("- [Breakdown by Period within Analysis Period](#breakdown-by-period-within-analysis-period)")
    md.append("- [Breakdown by Year](#breakdown-by-year)")
    md.append("- [Breakdown by Realm](#breakdown-by-realm)")
    md.append("- [Project Facilitators](#project-facilitators)")
    md.append("")
    
    # Overall summary
    total = len(df)
    earliest_date = df['Approval Date'].min()
    latest_date = df['Approval Date'].max()
    date_range = f"{earliest_date.strftime('%B %d, %Y')} to {latest_date.strftime('%B %d, %Y')}"
    
    md.append("## Overall Summary\n")
    md.append(f"This summary includes all PSSs in the dataset from **{date_range}**.\n")
    md.append(f"- **Total PSSs Approved:** {format_count(total)}")
    md.append("")
    
    # Summary by Analysis Period (if specified)
    if analysis_periods:
        md.append("## Summary by Analysis Period\n")
        
        for period in analysis_periods:
            _, _, label = parse_time_period(period)
            count = get_period_counts(df, period)
            
            md.append(f"### {label}\n")
            md.append(f"- **PSSs Approved:** {format_count(count)}")
            md.append("")
        
        # Breakdown by period within each analysis period
        md.append("## Breakdown by Period within Analysis Period\n")
        
        for period in analysis_periods:
            start_date, end_date, label = parse_time_period(period)
            human_readable_range = get_period_label(start_date, end_date)
            
            md.append(f"### {label}\n")
            md.append(f"This breakdown covers **{human_readable_range}**.\n")
            md.append("")
            md.append("| Period | PSSs Approved |")
            md.append("|--------|---------------|")
            
            tri_periods = find_periods_in_period(period)
            for tri in tri_periods:
                tri_count = get_period_counts(df, tri)
                md.append(f"| {tri} | {format_count(tri_count)} |")
            
            md.append("")
    
    # Breakdown by Year
    md.append("## Breakdown by Year\n")
    md.append("| Year | PSSs Approved |")
    md.append("|------|---------------|")
    
    all_years = find_all_years_in_data(df)
    for year in all_years:
        year_count = get_period_counts(df, str(year))
        md.append(f"| {year} | {format_count(year_count)} |")
    
    md.append("")
    
    # Breakdown by Year and Trimester
    md.append("### Breakdown by Year and Trimester\n")
    md.append("| Year | T1 | T2 | T3 | Total |")
    md.append("|------|----|----|----|-------|")
    
    for year in all_years:
        t1_count = get_period_counts(df, f"{year}T1")
        t2_count = get_period_counts(df, f"{year}T2")
        t3_count = get_period_counts(df, f"{year}T3")
        year_total = get_period_counts(df, str(year))
        md.append(f"| {year} | {format_count(t1_count)} | {format_count(t2_count)} | {format_count(t3_count)} | {format_count(year_total)} |")
    
    md.append("")
    
    # Breakdown by Realm
    md.append("## Breakdown by Realm\n")
    
    if 'Realm' in df.columns:
        # Overall realm breakdown
        md.append("### Overall Realm Breakdown\n")
        realm_counts = df['Realm'].value_counts().reset_index()
        realm_counts.columns = ['Realm', 'Count']
        realm_counts['Realm'] = realm_counts['Realm'].fillna('Unknown')
        realm_counts['Percentage'] = (realm_counts['Count'] / realm_counts['Count'].sum() * 100).round(1)
        
        md.append("| Realm | Count | Percentage |")
        md.append("|-------|-------|------------|")
        for _, row in realm_counts.iterrows():
            md.append(f"| {row['Realm']} | {format_count(row['Count'])} | {row['Percentage']:.1f}% |")
        
        md.append("")
        
        # Realm breakdown by period (if periods specified)
        if analysis_periods:
            md.append("### Realm Breakdown by Analysis Period\n")
            md.append("| Period | Realm | Count |")
            md.append("|--------|-------|-------|")
            
            # Collect all data first, then sort
            period_realm_data = []
            for period in analysis_periods:
                _, _, label = parse_time_period(period)
                realm_period_counts = get_period_counts_by_realm(df, period)
                
                if realm_period_counts is not None:
                    for _, row in realm_period_counts.iterrows():
                        period_realm_data.append({
                            'Period': label,
                            'Realm': row['Realm'],
                            'Count': row['Count']
                        })
            
            # Sort by Period, then Realm
            period_realm_data.sort(key=lambda x: (x['Period'], x['Realm']))
            
            # Output sorted data
            for item in period_realm_data:
                md.append(f"| {item['Period']} | {item['Realm']} | {format_count(item['Count'])} |")
            
            md.append("")
        
        # Realm breakdown by year
        md.append("### Realm Breakdown by Year\n")
        md.append("| Year | Realm | Count |")
        md.append("|------|-------|-------|")
        
        # Collect all data first, then sort
        year_realm_data = []
        for year in all_years:
            year_df = df[df['approval_year'] == year]
            realm_year_counts = year_df['Realm'].value_counts().reset_index()
            realm_year_counts.columns = ['Realm', 'Count']
            realm_year_counts['Realm'] = realm_year_counts['Realm'].fillna('Unknown')
            
            for _, row in realm_year_counts.iterrows():
                year_realm_data.append({
                    'Year': year,
                    'Realm': row['Realm'],
                    'Count': row['Count']
                })
        
        # Sort by Year, then Realm
        year_realm_data.sort(key=lambda x: (x['Year'], x['Realm']))
        
        # Output sorted data
        for item in year_realm_data:
            md.append(f"| {item['Year']} | {item['Realm']} | {format_count(item['Count'])} |")
        
        md.append("")
    else:
        md.append("Realm information not available in the dataset.\n")
    
    # Project Facilitators Analysis
    md.append("## Project Facilitators\n")
    
    if 'Project Facilitator' in df.columns:
        # Determine which period to use for facilitator analysis
        if analysis_periods:
            facilitator_period = analysis_periods[0]
            facilitator_data = analyze_facilitators(df, facilitator_period, staff_list)
        else:
            # Use all time
            facilitator_period = None
            facilitator_data = analyze_facilitators(df, None, staff_list)
        
        # Facilitator summary table
        if analysis_periods:
            md.append("### Facilitator Summary\n")
        else:
            md.append("### Facilitator Summary for All Time\n")
        md.append("| Period | Total Facilitators | New Facilitators | % New Facilitators |")
        md.append("|--------|-------------------|------------------|-------------------|")
        
        if analysis_periods:
            for period in analysis_periods:
                _, _, label = parse_time_period(period)
                period_facilitator_data = analyze_facilitators(df, period, staff_list)
                percent_new = f"{period_facilitator_data['new_facilitator_percent']:.1f}%"
                md.append(f"| {label} | {format_count(period_facilitator_data['total_facilitators_in_period'])} | {format_count(period_facilitator_data['total_new_facilitators'])} | {percent_new} |")
        else:
            percent_new = f"{facilitator_data['new_facilitator_percent']:.1f}%"
            md.append(f"| All Time | {format_count(facilitator_data['total_facilitators_in_period'])} | {format_count(facilitator_data['total_new_facilitators'])} | {percent_new} |")
        
        md.append("")
        
        # Top facilitators for the period
        if analysis_periods:
            period_label = parse_time_period(analysis_periods[0])[2]
        else:
            period_label = "All Time"
        
        if not facilitator_data['top_period_facilitators'].empty:
            md.append(f"### Top Facilitators for {period_label}\n")
            md.append("| Rank | Facilitator | PSS Count |")
            md.append("|------|-------------|-----------|")
            
            for i, (_, row) in enumerate(facilitator_data['top_period_facilitators'].iterrows(), 1):
                facilitator = row['Project Facilitator'] if pd.notnull(row['Project Facilitator']) else "Unknown"
                count = int(row['PSS Count'])
                md.append(f"| {i} | {facilitator} | {format_count(count)} |")
            
            md.append("")
        
        # Top facilitators of all time
        if not facilitator_data['top_all_time_facilitators'].empty:
            if analysis_periods:
                _, end_date, _ = parse_time_period(analysis_periods[0])
                end_date_str = end_date.strftime('%B %d, %Y')
            else:
                end_date_str = df['Approval Date'].max().strftime('%B %d, %Y')
            
            earliest_date = df['Approval Date'].min()
            start_date_str = earliest_date.strftime('%B %d, %Y')
            
            md.append(f"### Top Facilitators All Time ({start_date_str} Through {end_date_str})\n")
            md.append("| Rank | Facilitator | PSS Count |")
            md.append("|------|-------------|-----------|")
            
            for i, (_, row) in enumerate(facilitator_data['top_all_time_facilitators'].iterrows(), 1):
                facilitator = row['Project Facilitator'] if pd.notnull(row['Project Facilitator']) else "Unknown"
                count = int(row['PSS Count'])
                md.append(f"| {i} | {facilitator} | {format_count(count)} |")
            
            md.append("")
    else:
        md.append("Project Facilitator information not available in the dataset.\n")
    
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(
        description="Analyze PSS approval data and generate a markdown summary report."
    )
    parser.add_argument("-i", "--input", required=True, help="Input CSV file path")
    parser.add_argument("-o", "--output", required=True, help="Output Markdown file path")
    parser.add_argument("-p", "--periods", nargs="+", 
                    help="Analysis periods in format 'YYYY' (full year) or 'YYYYT[1-3]' (period). If not specified, analyzes all time.")
    parser.add_argument("-s", "--staff-config", default="data/config/hl7-staff.yaml",
                    help="Path to HL7 staff configuration file (optional, for excluding staff from facilitator analysis)")
    
    args = parser.parse_args()
    
    # Load staff configuration (optional)
    staff_list = []
    if args.staff_config and os.path.exists(args.staff_config):
        try:
            import yaml
            with open(args.staff_config, 'r') as file:
                staff_config = yaml.safe_load(file)
            if staff_config:
                print(f"Loaded {len(staff_config)} staff members from {args.staff_config}")
                for staff in staff_config:
                    if 'display_name' in staff:
                        staff_list.append(staff['display_name'])
        except Exception as e:
            print(f"Note: Could not load staff config file: {e}")
    
    # Load data
    print(f"Loading data from {args.input}")
    df = pd.read_csv(args.input)
    df.columns = df.columns.str.strip()
    
    # Check for required columns
    if 'Approval Date' not in df.columns:
        print("ERROR: 'Approval Date' column not found in input file.")
        print("Available columns:", ', '.join(df.columns.tolist()))
        return
    
    # Expand periods if specified
    expanded_periods = None
    if args.periods:
        expanded_periods = []
        for period in args.periods:
            expanded_periods.append(period)
            try:
                sub_periods = find_periods_in_period(period)
                expanded_periods.extend(sub_periods)
            except ValueError:
                pass  # If it's already a tri-period or invalid, skip sub-expansion
        
        # Deduplicate
        expanded_periods = sorted(set(expanded_periods))
        print(f"Processing data for periods: {', '.join(expanded_periods)}")
    else:
        print("Processing data for all time (no period filter specified)")
    
    # Process data
    try:
        df = process_data(df, expanded_periods)
    except Exception as e:
        print(f"ERROR: Failed to process data: {e}")
        import traceback
        traceback.print_exc()
        return

    # If specific analysis periods were requested, restrict the dataset to those periods.
    # (Without this, later approvals can still influence yearly totals and other sections.)
    if args.periods:
        before_filter_count = len(df)
        try:
            df = filter_df_to_periods(df, args.periods)
        except Exception as e:
            print(f"ERROR: Failed to apply period filter: {e}")
            import traceback
            traceback.print_exc()
            return
        after_filter_count = len(df)
        if after_filter_count != before_filter_count:
            print(f"Note: Period filter reduced rows from {before_filter_count} to {after_filter_count}")
    
    if df.empty:
        print("ERROR: No valid data after processing. Exiting.")
        return
    
    # Generate report
    print("Generating report")
    report = generate_report(df, analysis_periods=args.periods, staff_list=staff_list)
    
    # Save report
    print(f"Writing report to {args.output}")
    # Create output directory if it doesn't exist
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")
    
    with open(args.output, "w", encoding='utf-8') as f:
        f.write(report)
    
    print("Done!")

if __name__ == "__main__":
    main()
