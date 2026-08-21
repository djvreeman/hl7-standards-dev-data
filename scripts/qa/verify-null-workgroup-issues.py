#!/usr/bin/env python3
"""
Verify that "New - Only in All Year" issues had NULL Work Group during T2 period.
This explains why they were excluded from the T2 extraction due to the JQL filter.
"""

import pandas as pd
import argparse
import json
import requests
import time
import os
from datetime import datetime, timezone

# Load Jira config
try:
    with open("data/config/config.json", "r") as config_file:
        config = json.load(config_file)
    BEARER_TOKEN = config["jira_bearer_token"]
except (FileNotFoundError, KeyError) as e:
    print(f"Error loading config: {e}")
    print("Please create data/config/config.json with your JIRA bearer token.")
    exit(1)

JIRA_BASE_URL = "https://jira.hl7.org/rest/api/latest"
DEFAULT_CACHE_DIR = "data/working/cache"

def parse_time_period(period_str):
    """Parse a time period string like '2025T2' into start and end dates"""
    import re
    
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
        
        return start_date, end_date
    else:
        raise ValueError(f"Invalid time period format: {period_str}")

def load_and_prepare_data(csv_path):
    """Load CSV and prepare date columns"""
    df = pd.read_csv(csv_path)
    df.columns = df.columns.str.strip()
    
    # Convert dates
    df['Created Date'] = pd.to_datetime(df['Created Date'], errors='coerce', utc=True)
    df['Resolution Date'] = pd.to_datetime(df['Resolution Date'], errors='coerce', utc=True)
    df['is_resolved'] = df['Resolution Date'].notnull()
    
    return df

def fetch_issue_changelog(issue_key, bearer_token, cache_dir=DEFAULT_CACHE_DIR, cache_enabled=True):
    """Fetch changelog for a specific issue with caching"""
    cache_file = os.path.join(cache_dir, f"{issue_key}_changelog.json")
    
    # Check cache
    if cache_enabled and os.path.exists(cache_file):
        cache_age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
        if cache_age_hours < 24:  # Use cache if less than 24 hours old
            with open(cache_file, 'r') as f:
                return json.load(f)
    
    # Fetch from API
    url = f"{JIRA_BASE_URL}/issue/{issue_key}?expand=changelog"
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Accept': 'application/json'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            
            # Cache the result
            if cache_enabled:
                os.makedirs(cache_dir, exist_ok=True)
                with open(cache_file, 'w') as f:
                    json.dump(data, f, indent=2)
            
            return data
        else:
            print(f"  Warning: Failed to fetch {issue_key}: {response.status_code}")
            return None
    except Exception as e:
        print(f"  Warning: Error fetching {issue_key}: {e}")
        return None

def find_workgroup_set_date(changelog_data, t2_end_date):
    """Find when Work Group field was set, and if it was NULL during T2"""
    if not changelog_data or 'changelog' not in changelog_data:
        return None, None, None
    
    changelog = changelog_data.get('changelog', {})
    histories = changelog.get('histories', [])
    
    # Work Group field ID is customfield_11400
    workgroup_changes = []
    
    for history in histories:
        created_str = history.get('created', '')
        if not created_str:
            continue
        
        try:
            created_date = pd.Timestamp(created_str).tz_localize('UTC')
        except:
            continue
        
        items = history.get('items', [])
        for item in items:
            field = item.get('field', '')
            if field == 'Work Group' or field == 'customfield_11400':
                from_val = item.get('fromString') or item.get('from')
                to_val = item.get('toString') or item.get('to')
                
                workgroup_changes.append({
                    'date': created_date,
                    'from': from_val,
                    'to': to_val,
                    'fromString': item.get('fromString'),
                    'toString': item.get('toString')
                })
    
    # Sort by date
    workgroup_changes.sort(key=lambda x: x['date'])
    
    # Check if Work Group was NULL during T2
    # T2 ended on Aug 31, 2025
    t2_end = pd.Timestamp('2025-08-31T23:59:59', tz='UTC')
    
    # Find the first time Work Group was set (not NULL)
    first_set_date = None
    was_null_during_t2 = True
    
    for change in workgroup_changes:
        # If 'to' is not None/empty, Work Group was set
        if change['to'] and change['toString']:
            first_set_date = change['date']
            if first_set_date <= t2_end:
                was_null_during_t2 = False
            break
    
    # If no changes found, check current value
    current_wg = None
    if changelog_data.get('fields'):
        wg_field = changelog_data['fields'].get('customfield_11400')
        if wg_field:
            if isinstance(wg_field, list) and len(wg_field) > 0:
                current_wg = wg_field[0]
            elif isinstance(wg_field, str):
                current_wg = wg_field
    
    return was_null_during_t2, first_set_date, current_wg

def verify_null_workgroup_issues(t2_csv, all_year_csv, period='2025T2', output_csv=None, use_cache=True):
    """Verify how many 'New - Only in All Year' issues had NULL Work Group during T2"""
    
    print(f"Loading T2-specific dataset: {t2_csv}")
    t2_df = load_and_prepare_data(t2_csv)
    
    print(f"Loading All Year dataset: {all_year_csv}")
    all_year_df = load_and_prepare_data(all_year_csv)
    
    # Parse period dates
    start_date, end_date = parse_time_period(period)
    print(f"\nPeriod: {period}")
    print(f"Start: {start_date}")
    print(f"End: {end_date}\n")
    
    # Create period masks
    all_year_df['created_in_period'] = (all_year_df['Created Date'] >= start_date) & (all_year_df['Created Date'] <= end_date)
    
    # Set Issue as index
    t2_df = t2_df.set_index('Issue')
    all_year_df = all_year_df.set_index('Issue')
    
    # Find issues only in All Year dataset that are new in period
    all_year_only = set(all_year_df.index) - set(t2_df.index)
    all_year_new_issues = all_year_df.loc[list(all_year_only)]
    all_year_new_in_period = all_year_new_issues[all_year_new_issues['created_in_period']]
    
    print("=" * 80)
    print(f"ANALYZING {len(all_year_new_in_period)} 'NEW - ONLY IN ALL YEAR' ISSUES")
    print("=" * 80)
    print(f"Checking Work Group field history for each issue...\n")
    
    results = []
    null_during_t2_count = 0
    set_during_t2_count = 0
    error_count = 0
    
    for idx, (issue_key, row) in enumerate(all_year_new_in_period.iterrows(), 1):
        print(f"[{idx}/{len(all_year_new_in_period)}] Checking {issue_key}...", end=' ', flush=True)
        
        # Fetch changelog
        changelog_data = fetch_issue_changelog(issue_key, BEARER_TOKEN, cache_enabled=use_cache)
        
        if changelog_data is None:
            print("ERROR - Could not fetch changelog")
            error_count += 1
            results.append({
                'Issue': issue_key,
                'Created Date': row['Created Date'],
                'Current WG': row.get('WG', 'N/A'),
                'Current WG Name': row.get('WG Name', 'N/A'),
                'Was NULL During T2': 'ERROR',
                'First Set Date': 'ERROR',
                'Days After T2 End': 'ERROR',
                'Reporter': row.get('Reporter', 'N/A'),
            })
            continue
        
        # Check Work Group history
        was_null_during_t2, first_set_date, current_wg = find_workgroup_set_date(changelog_data, end_date)
        
        if was_null_during_t2 is None:
            print("ERROR - Could not parse changelog")
            error_count += 1
            results.append({
                'Issue': issue_key,
                'Created Date': row['Created Date'],
                'Current WG': row.get('WG', 'N/A'),
                'Current WG Name': row.get('WG Name', 'N/A'),
                'Was NULL During T2': 'ERROR',
                'First Set Date': 'ERROR',
                'Days After T2 End': 'ERROR',
                'Reporter': row.get('Reporter', 'N/A'),
            })
            continue
        
        # Calculate days after T2 end
        days_after_t2 = None
        if first_set_date:
            t2_end = pd.Timestamp('2025-08-31T23:59:59', tz='UTC')
            if first_set_date > t2_end:
                days_after_t2 = (first_set_date - t2_end).total_seconds() / 86400
        
        if was_null_during_t2:
            null_during_t2_count += 1
            status = "NULL during T2 ✓"
        else:
            set_during_t2_count += 1
            status = f"Set on {first_set_date.strftime('%Y-%m-%d')}"
        
        print(status)
        
        results.append({
            'Issue': issue_key,
            'Created Date': row['Created Date'],
            'Current WG': row.get('WG', current_wg if current_wg else 'N/A'),
            'Current WG Name': row.get('WG Name', 'N/A'),
            'Was NULL During T2': was_null_during_t2,
            'First Set Date': first_set_date.strftime('%Y-%m-%d %H:%M:%S') if first_set_date else 'Never set',
            'Days After T2 End': f"{days_after_t2:.1f}" if days_after_t2 else 'N/A',
            'Reporter': row.get('Reporter', 'N/A'),
            'Specification': row.get('Specification Display Name', 'N/A'),
        })
        
        # Rate limiting - be nice to Jira API
        time.sleep(0.5)
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total 'New - Only in All Year' issues: {len(all_year_new_in_period)}")
    print(f"  - Had NULL Work Group during T2: {null_during_t2_count} ({null_during_t2_count/len(all_year_new_in_period)*100:.1f}%)")
    print(f"  - Work Group was set during T2: {set_during_t2_count} ({set_during_t2_count/len(all_year_new_in_period)*100:.1f}%)")
    print(f"  - Errors: {error_count}")
    
    if null_during_t2_count == len(all_year_new_in_period) - error_count:
        print("\n✓ SUCCESS: All issues (excluding errors) had NULL Work Group during T2!")
        print("  This confirms the JQL filter explanation.")
    elif null_during_t2_count > 0:
        print(f"\n⚠ PARTIAL: {null_during_t2_count} issues had NULL Work Group during T2.")
        print(f"  {set_during_t2_count} issues had Work Group set during T2 (may need further investigation).")
    
    # Save results
    if output_csv:
        results_df = pd.DataFrame(results)
        results_df.to_csv(output_csv, index=False)
        print(f"\nResults saved to: {output_csv}")
    
    return results

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Verify that 'New - Only in All Year' issues had NULL Work Group during T2"
    )
    parser.add_argument(
        "--t2-csv",
        required=True,
        help="Path to T2-specific CSV file"
    )
    parser.add_argument(
        "--all-year-csv",
        required=True,
        help="Path to All Year CSV file"
    )
    parser.add_argument(
        "--period",
        default="2025T2",
        help="Period to analyze (default: 2025T2)"
    )
    parser.add_argument(
        "--output",
        help="Output CSV file for results (optional)"
    )
    parser.add_argument(
        "--no-cache",
        action="store_true",
        help="Disable caching of Jira API responses"
    )
    
    args = parser.parse_args()
    
    results = verify_null_workgroup_issues(
        args.t2_csv,
        args.all_year_csv,
        period=args.period,
        output_csv=args.output,
        use_cache=not args.no_cache
    )