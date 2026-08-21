#!/usr/bin/env python3
"""
Analyze status transitions to identify which resolved states can be re-opened
and how that affects resolution date tracking.
"""

import pandas as pd
import json
import requests
import time
import os
from collections import defaultdict, Counter

# Load config
try:
    with open("data/config/config.json", "r") as f:
        config = json.load(f)
    BEARER_TOKEN = config["jira_bearer_token"]
except:
    print("Error loading config")
    exit(1)

JIRA_BASE_URL = "https://jira.hl7.org/rest/api/latest"
CACHE_DIR = "data/working/cache"

# Resolved status IDs
RESOLVED_STATUS_IDS = {'10104', '10105', '10306', '10106', '10107', '10108'}
RESOLVED_STATUS_NAMES = {
    '10104': 'Resolved - No Change',
    '10105': 'Resolved - change required',
    '10306': 'Deferred',
    '10106': 'Duplicate',
    '10107': 'Applied',
    '10108': 'Published'
}

# Active status IDs
ACTIVE_STATUS_IDS = {'10101', '10102', '10103'}  # Submitted, Triaged, Waiting for Input

def fetch_issue_changelog(issue_key, cache_enabled=True):
    """Fetch changelog with caching and pagination support"""
    cache_file = os.path.join(CACHE_DIR, f"{issue_key}_changelog.json")
    
    if cache_enabled and os.path.exists(cache_file):
        cache_age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
        if cache_age_hours < 24:
            with open(cache_file, 'r') as f:
                return json.load(f)
    
    # Fetch issue with changelog, handling pagination
    url = f"{JIRA_BASE_URL}/issue/{issue_key}?expand=changelog"
    headers = {'Authorization': f'Bearer {BEARER_TOKEN}', 'Accept': 'application/json'}
    
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code == 200:
            data = response.json()
            
            # Handle pagination for changelog
            changelog = data.get('changelog', {})
            if changelog:
                total = changelog.get('total', 0)
                max_results = changelog.get('maxResults', 0)
                
                # If there are more results, fetch them
                if total > max_results:
                    all_histories = changelog.get('histories', [])
                    start_at = max_results
                    
                    while start_at < total:
                        changelog_url = f"{JIRA_BASE_URL}/issue/{issue_key}/changelog"
                        params = {'startAt': start_at, 'maxResults': 100}
                        changelog_response = requests.get(changelog_url, headers=headers, params=params, timeout=30)
                        
                        if changelog_response.status_code == 200:
                            changelog_data = changelog_response.json()
                            # Changelog endpoint returns 'values' array
                            new_histories = changelog_data.get('values', [])
                            all_histories.extend(new_histories)
                            start_at += len(new_histories)
                            if len(new_histories) == 0:
                                break
                        else:
                            break
                    
                    # Update the changelog with all histories
                    data['changelog']['histories'] = all_histories
            
            if cache_enabled:
                os.makedirs(CACHE_DIR, exist_ok=True)
                with open(cache_file, 'w') as f:
                    json.dump(data, f, indent=2)
            return data
    except Exception as e:
        print(f"  Error fetching {issue_key}: {e}")
    return None

def analyze_status_transitions(changelog_data):
    """Extract all status transitions"""
    if not changelog_data or 'changelog' not in changelog_data:
        return []
    
    transitions = []
    histories = changelog_data.get('changelog', {}).get('histories', [])
    
    for history in histories:
        created_str = history.get('created', '')
        if not created_str:
            continue
        
        try:
            # Handle timezone-aware timestamps (they come as strings like "2025-09-09T18:20:15.682+0000")
            if '+' in created_str or created_str.endswith('Z'):
                created_date = pd.Timestamp(created_str)
            else:
                created_date = pd.Timestamp(created_str).tz_localize('UTC')
        except Exception as e:
            # Skip this history entry if date parsing fails
            continue
        
        items = history.get('items', [])
        for item in items:
            if item.get('field') == 'status':
                from_status_id = item.get('from')
                to_status_id = item.get('to')
                from_status_name = item.get('fromString', '')
                to_status_name = item.get('toString', '')
                
                # Skip self-transitions (from same status to same status)
                if from_status_id and to_status_id and from_status_id == to_status_id:
                    continue
                
                # Only add if we have valid status IDs
                if from_status_id and to_status_id:
                    transitions.append({
                        'date': created_date,
                        'from_id': from_status_id,
                        'from_name': from_status_name,
                        'to_id': to_status_id,
                        'to_name': to_status_name
                    })
    
    return sorted(transitions, key=lambda x: x['date'])

def analyze_reopening_patterns(csv_file, sample_size=100, issues_list=None):
    """Analyze a sample of issues to identify re-opening patterns
    
    Args:
        csv_file: CSV file with issues
        sample_size: Number of issues to sample (if issues_list not provided)
        issues_list: Optional list of specific issue keys to analyze
    """
    
    print("Loading CSV file...")
    df = pd.read_csv(csv_file)
    df.columns = df.columns.str.strip()
    
    # Filter to resolved issues
    df['Resolution Date'] = pd.to_datetime(df['Resolution Date'], errors='coerce', utc=True)
    resolved_df = df[df['Resolution Date'].notna()].copy()
    
    print(f"Found {len(resolved_df)} resolved issues")
    
    if issues_list:
        # Use provided list of issues
        sample_issues = [issue for issue in issues_list if issue in resolved_df['Issue'].values]
        print(f"Analyzing {len(sample_issues)} specific issues from provided list...\n")
    else:
        # Sample randomly
        sample_issues = resolved_df.head(sample_size)['Issue'].tolist()
        print(f"Sampling {min(sample_size, len(resolved_df))} issues for analysis...\n")
    
    # Track patterns
    transitions_from_resolved = Counter()  # Which resolved states transition back to active
    transitions_to_resolved = Counter()  # Which active states transition to resolved
    re_opened_count = 0
    multiple_resolutions_count = 0
    resolution_date_changes = []
    
    results = []
    
    for idx, issue_key in enumerate(sample_issues, 1):
        print(f"[{idx}/{len(sample_issues)}] Analyzing {issue_key}...", end=' ', flush=True)
        
        changelog_data = fetch_issue_changelog(issue_key)
        if not changelog_data:
            print("ERROR - Failed to fetch changelog")
            continue
        
        # Debug: Check if changelog exists
        if 'changelog' not in changelog_data:
            print("ERROR - No changelog in response")
            continue
        
        transitions = analyze_status_transitions(changelog_data)
        
        # Get current resolution date from CSV and Jira
        csv_resolution_date = None
        csv_row = resolved_df[resolved_df['Issue'] == issue_key]
        if not csv_row.empty:
            csv_resolution_date = csv_row.iloc[0]['Resolution Date']
        
        current_resolution_date = None
        if changelog_data.get('fields', {}).get('resolutiondate'):
            try:
                resolution_str = changelog_data['fields']['resolutiondate']
                if '+' in resolution_str or resolution_str.endswith('Z'):
                    current_resolution_date = pd.Timestamp(resolution_str)
                else:
                    current_resolution_date = pd.Timestamp(resolution_str).tz_localize('UTC')
            except:
                pass
        
        # Check for resolution date changes in changelog even if no status transitions
        resolution_date_changes_in_history = []
        changelog = changelog_data.get('changelog', {})
        histories = changelog.get('histories', [])
        
        for history in histories:
            created_str = history.get('created', '')
            if not created_str:
                continue
            try:
                if '+' in created_str or created_str.endswith('Z'):
                    history_date = pd.Timestamp(created_str)
                else:
                    history_date = pd.Timestamp(created_str).tz_localize('UTC')
            except:
                continue
            
            for item in history.get('items', []):
                if item.get('field') == 'resolutiondate':
                    from_date = item.get('fromString')
                    to_date = item.get('toString')
                    resolution_date_changes_in_history.append({
                        'date': history_date,
                        'from': from_date,
                        'to': to_date
                    })
        
        if not transitions:
            # Check if there are any histories at all
            if histories:
                # Count status field changes
                status_changes = 0
                for history in histories:
                    for item in history.get('items', []):
                        if item.get('field') == 'status':
                            status_changes += 1
                
                msg_parts = [f"{len(histories)} histories"]
                if status_changes > 0:
                    msg_parts.append(f"{status_changes} status changes")
                if resolution_date_changes_in_history:
                    msg_parts.append(f"{len(resolution_date_changes_in_history)} resolution date changes")
                
                if resolution_date_changes_in_history or (csv_resolution_date and current_resolution_date and abs((csv_resolution_date - current_resolution_date).total_seconds()) > 86400):
                    print(f"RESOLUTION DATE CHANGE ({', '.join(msg_parts)})")
                    # Still process this issue to track resolution date changes - set empty transitions
                    transitions = []
                else:
                    print(f"No valid transitions ({', '.join(msg_parts)})")
                    continue
            else:
                print("No transitions (no histories found)")
                continue
        
        # TEMPORARY DEBUG - print first 5 issues' transitions
        if idx <= 5:
            transition_str = ' → '.join([f"{t['from_name']}→{t['to_name']}" for t in transitions[:10]])
            if len(transitions) > 10:
                transition_str += f" ... ({len(transitions)} total)"
            print(f"\n    Transitions: {transition_str}")
        
        # Analyze transitions
        resolved_transitions = []
        re_opened_transitions = []
        all_transitions_summary = []  # Track all transitions for debugging
        
        for i, trans in enumerate(transitions):
            from_id = trans['from_id']
            to_id = trans['to_id']
            
            # Track all transitions for debugging
            all_transitions_summary.append(f"{trans['from_name']} → {trans['to_name']}")
            
            # Transition TO resolved state
            if to_id in RESOLVED_STATUS_IDS:
                resolved_transitions.append({
                    'date': trans['date'],
                    'status_id': to_id,
                    'status_name': trans['to_name']
                })
            
            # Transition FROM resolved state TO active state (re-opening)
            if from_id in RESOLVED_STATUS_IDS and to_id in ACTIVE_STATUS_IDS:
                re_opened_transitions.append({
                    'date': trans['date'],
                    'from_status': trans['from_name'],
                    'to_status': trans['to_name']
                })
                transitions_from_resolved[trans['from_name']] += 1
            
            # Also track transitions BETWEEN resolved states (might indicate re-resolution)
            if from_id in RESOLVED_STATUS_IDS and to_id in RESOLVED_STATUS_IDS and from_id != to_id:
                transitions_from_resolved[f"{trans['from_name']} → {trans['to_name']}"] += 1
        
        # Check for multiple resolutions
        has_multiple_resolutions = len(resolved_transitions) > 1
        has_reopening = len(re_opened_transitions) > 0
        
        if has_reopening:
            re_opened_count += 1
            print(f"RE-OPENED ({len(re_opened_transitions)} times)")
        elif has_multiple_resolutions:
            multiple_resolutions_count += 1
            print(f"MULTIPLE RESOLUTIONS ({len(resolved_transitions)})")
        else:
            print("OK")
        
        # Track resolution date changes
        # Check if CSV resolution date differs from Jira resolution date
        if csv_resolution_date and current_resolution_date:
            if abs((csv_resolution_date - current_resolution_date).total_seconds()) > 86400:  # More than 1 day difference
                resolution_date_changes.append({
                    'issue': issue_key,
                    'csv_resolution_date': csv_resolution_date,
                    'jira_resolution_date': current_resolution_date,
                    'days_diff': (current_resolution_date - csv_resolution_date).total_seconds() / 86400,
                    'resolved_count': len(resolved_transitions),
                    'reopened': has_reopening,
                    'resolution_date_changes_in_history': len(resolution_date_changes_in_history)
                })
        
        # Also check if resolution date differs from first resolved transition
        if current_resolution_date and resolved_transitions:
            first_resolved = resolved_transitions[0]['date']
            if abs((current_resolution_date - first_resolved).total_seconds()) > 86400:  # More than 1 day difference
                resolution_date_changes.append({
                    'issue': issue_key,
                    'first_resolved': first_resolved,
                    'current_resolution_date': current_resolution_date,
                    'days_diff': (current_resolution_date - first_resolved).total_seconds() / 86400,
                    'resolved_count': len(resolved_transitions),
                    'reopened': has_reopening,
                    'type': 'first_resolved_vs_current'
                })
        
        # Format transitions summary for output
        if len(all_transitions_summary) <= 5:
            transitions_str = ' → '.join(all_transitions_summary)
        else:
            transitions_str = ' → '.join(all_transitions_summary[:3]) + f' ... ({len(all_transitions_summary)} total)'
        
        results.append({
            'Issue': issue_key,
            'Total Transitions': len(transitions),
            'Resolved Transitions': len(resolved_transitions),
            'Re-opened': has_reopening,
            'Re-opening Count': len(re_opened_transitions),
            'Multiple Resolutions': has_multiple_resolutions,
            'First Resolved Status': resolved_transitions[0]['status_name'] if resolved_transitions else None,
            'First Resolved Date': resolved_transitions[0]['date'] if resolved_transitions else None,
            'CSV Resolution Date': csv_resolution_date,
            'Jira Resolution Date': current_resolution_date,
            'Resolution Date Changed': len(resolution_date_changes_in_history) > 0 or (csv_resolution_date and current_resolution_date and abs((csv_resolution_date - current_resolution_date).total_seconds()) > 86400),
            'Re-opening From States': ', '.join([t['from_status'] for t in re_opened_transitions]),
            'All Transitions': transitions_str
        })
        
        time.sleep(0.3)  # Rate limiting
    
    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"Total issues analyzed: {len(sample_issues)}")
    print(f"  - Re-opened at least once: {re_opened_count} ({re_opened_count/len(sample_issues)*100:.1f}%)")
    print(f"  - Multiple resolutions (without re-opening): {multiple_resolutions_count}")
    print(f"  - Resolution date differs from first resolved: {len(resolution_date_changes)}")
    
    print("\n" + "=" * 80)
    print("RE-OPENING PATTERNS")
    print("=" * 80)
    if transitions_from_resolved:
        print("States that transitioned FROM resolved TO active (or between resolved states):")
        for status, count in transitions_from_resolved.most_common():
            print(f"  {status}: {count} times")
    else:
        print("No transitions from resolved states found in sample.")
    
    if resolution_date_changes:
        print("\n" + "=" * 80)
        print("RESOLUTION DATE CHANGES")
        print("=" * 80)
        print(f"Issues where resolutiondate differs from first resolved transition:")
        for change in sorted(resolution_date_changes, key=lambda x: abs(x['days_diff']), reverse=True)[:10]:
            print(f"  {change['issue']}: {change['days_diff']:.1f} days difference "
                  f"(Re-opened: {change['reopened']}, Resolved {change['resolved_count']} times)")
    
    return results

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Analyze status transitions to identify re-opening patterns")
    parser.add_argument("--csv", required=True, help="CSV file with issues")
    parser.add_argument("--sample-size", type=int, default=100, help="Number of issues to sample")
    parser.add_argument("--issues-file", help="CSV file with specific issues to analyze (must have 'Issue' column)")
    parser.add_argument("--output", help="Output CSV file")
    parser.add_argument("--no-cache", action="store_true", help="Disable caching")
    
    args = parser.parse_args()
    
    # Load specific issues if provided
    issues_list = None
    if args.issues_file:
        issues_df = pd.read_csv(args.issues_file)
        if 'Issue' in issues_df.columns:
            issues_list = issues_df['Issue'].tolist()
            print(f"Loaded {len(issues_list)} issues from {args.issues_file}")
        else:
            print(f"Warning: {args.issues_file} does not have 'Issue' column. Using random sampling.")
    
    results = analyze_reopening_patterns(args.csv, sample_size=args.sample_size, issues_list=issues_list)
    
    if args.output:
        results_df = pd.DataFrame(results)
        results_df.to_csv(args.output, index=False)
        print(f"\nResults saved to: {args.output}")