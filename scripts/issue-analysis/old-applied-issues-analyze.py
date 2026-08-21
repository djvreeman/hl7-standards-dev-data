#!/usr/bin/env python3
# =============================================================================
# Issue Application Metrics Analyzer and Markdown Report Generator
#
# This script analyzes HL7 JIRA issue data to evaluate how efficiently 
# issues are moved through the application process (e.g., to 'Applied' status).
#
# It computes time-to-resolution statistics, backlog volumes, submitter 
# behavior, and performance banding across user-defined time periods.
#
# === Input Requirements ===
# - A CSV file exported from HL7 JIRA (via parse-jira-filter-export-csv-md.py)
#   that includes:
#     - Created Date
#     - Applied Date (optional but preferred)
#     - Current Status or status
#     - Issue Type, Specification, WG Name, Realm, etc. (for breakdowns)
#     - History/Changelog data (optional but recommended for tempo metrics)
#       To get history data, run parse-jira-filter-export-csv-md.py with --history
#       and include the changelog/history data. The script will extract:
#       - First Resolved Date (first transition to any resolved state)
#       - Resolved to Applied Date (transition from "Resolved - change required" to "Applied")
#       - Resolved to Applied User (person who made the transition)
#
# === Configuration File ===
# - Optional YAML file of HL7 staff members used to exclude staff from 
#   reporter analysis. Defaults to: data/working/config/hl7-staff.yaml
#
# === Period Format ===
# Periods must be specified in one of the following formats:
#   - 'YYYY'           → Full year (e.g., 2024)
#   - 'YYYYT[1-3]'     → Tri-year quarter (e.g., 2024T2)
#   - 'YYYY[-T[1-3]]-YYYY[-T[1-3]]' → Ranges (e.g., 2023T2–2024T1)
#
# === Output ===
# - A Markdown report file containing:
#     - Overall summary and performance bands
#     - Time-based breakdowns (T1, T2, T3)
#     - Reporter and applier leaderboards
#     - Status distribution, issue types, and resolution-to-application gaps
#     - Breakdowns by Work Group, Realm, Specification, and Product Family
#     - Mermaid diagram of the JIRA workflow
#
# === Example Usage ===
# python analyze-applied-issues.py \
#     -i data/input/jira_issues.csv \
#     -o reports/2025T1_applied_issues.md \
#     -p 2025T1 \
#     -s data/working/config/hl7-staff.yaml
#
# === Dependencies ===
# - pandas
# - numpy
# - pyyaml
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================


import argparse
import pandas as pd
import numpy as np
import re
import yaml
import json
from datetime import datetime
import os
import csv

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
        # Only warn if the file was explicitly specified, not if using default
        # The default path may not exist and that's okay - staff filtering is optional
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

# NEW: Define JIRA workflow status information with new categorization
def get_jira_workflow_info():
    """Return information about JIRA workflow statuses and transitions."""
    # Status IDs and names from the JIRA workflow
    statuses = {
        '10101': 'Submitted',
        '10102': 'Triaged',
        '10103': 'Waiting for Input',
        '10104': 'Resolved - No Change',
        '10105': 'Resolved - Change Required',  # Updated capitalization for consistency
        '10306': 'Deferred',
        '10106': 'Duplicate',
        '10107': 'Applied',
        '10108': 'Published'
    }
    
    # Status name to ID mapping (reverse lookup) - include both capitalizations for compatibility
    status_name_to_id = {v: k for k, v in statuses.items()}
    # Also add lowercase version for backward compatibility
    status_name_to_id['Resolved - change required'] = '10105'
    
    # New categorization based on workflow diagram
    # Deciding: Submitted, Triaged, Waiting for Input, Deferred
    deciding_states = ['10101', '10102', '10103', '10306']
    deciding_state_names = ['Submitted', 'Triaged', 'Waiting for Input', 'Deferred']
    
    # Doing: Resolved - Change Required, Applied
    doing_states = ['10105', '10107']
    doing_state_names = ['Resolved - Change Required', 'Applied']
    
    # Done: Published, Duplicate, Resolved - No Change
    done_states = ['10108', '10106', '10104']
    done_state_names = ['Published', 'Duplicate', 'Resolved - No Change']
    
    # Resolved states (first transition to any of these counts as resolution)
    # Includes Applied to handle edge cases where issues might jump directly to Applied
    resolved_states = ['10306', '10105', '10108', '10106', '10104', '10107']  # Deferred, Resolved - Change Required, Published, Duplicate, Resolved - No Change, Applied
    resolved_state_names = ['Deferred', 'Resolved - Change Required', 'Published', 'Duplicate', 'Resolved - No Change', 'Applied']
    
    # Define which statuses can potentially lead to Applied
    can_be_applied = ['10105']  # Resolved - change required
    
    # Define terminal statuses (endpoints in the workflow)
    terminal_statuses = ['10104', '10306', '10106', '10107', '10108']  # Resolved - No Change, Deferred, Duplicate, Applied, Published
    
    return {
        'statuses': statuses,
        'status_name_to_id': status_name_to_id,
        'deciding_states': deciding_states,
        'deciding_state_names': deciding_state_names,
        'doing_states': doing_states,
        'doing_state_names': doing_state_names,
        'done_states': done_states,
        'done_state_names': done_state_names,
        'resolved_states': resolved_states,
        'resolved_state_names': resolved_state_names,
        'can_be_applied': can_be_applied,
        'terminal_statuses': terminal_statuses
    }

def extract_first_resolved_date_from_history(history_data, workflow_info):
    """
    Extract the first date an issue transitioned to any resolved state.
    Resolved states: Deferred, Resolved - Change Required, Published, Duplicate, Resolved - No Change, Applied
    (Applied is included to handle edge cases where issues might jump directly to Applied)
    
    Args:
        history_data: List of history entries from JIRA changelog (may be JSON string or list)
        workflow_info: Workflow information dictionary
        
    Returns:
        First resolved date (pd.Timestamp) or None
    """
    # Handle JSON string if needed
    if isinstance(history_data, str):
        try:
            history_data = json.loads(history_data)
        except:
            return None
    
    if not history_data or not isinstance(history_data, list):
        return None
    
    resolved_state_ids = set(workflow_info['resolved_states'])
    resolved_state_names = set(workflow_info['resolved_state_names'])
    
    first_resolved_date = None
    
    for history_entry in history_data:
        if 'items' not in history_entry:
            continue
            
        created_str = history_entry.get('created', '')
        if not created_str:
            continue
        
        try:
            if '+' in created_str or created_str.endswith('Z'):
                created_date = pd.Timestamp(created_str)
            else:
                created_date = pd.Timestamp(created_str).tz_localize('UTC')
        except:
            continue
        
        # Check if any item in this history entry is a status transition to a resolved state
        for item in history_entry.get('items', []):
            if item.get('field') == 'status':
                to_status_id = item.get('to')
                to_status_name = item.get('toString', '')
                
                # Check if transitioning TO a resolved state
                if (to_status_id in resolved_state_ids) or (to_status_name in resolved_state_names):
                    if first_resolved_date is None or created_date < first_resolved_date:
                        first_resolved_date = created_date
                    break  # Found first resolution, can stop checking this entry
    
    return first_resolved_date

def extract_current_status_from_history(history_data, workflow_info):
    """
    Extract the current status from history by finding the most recent status transition.
    
    Args:
        history_data: List of history entries from JIRA changelog (may be JSON string or list)
        workflow_info: Workflow information dictionary
        
    Returns:
        Current status name (string) or None
    """
    # Handle JSON string if needed
    if isinstance(history_data, str):
        try:
            history_data = json.loads(history_data)
        except:
            return None
    
    if not history_data or not isinstance(history_data, list):
        return None
    
    # Sort history entries by date (most recent first)
    history_entries_with_dates = []
    for history_entry in history_data:
        created_str = history_entry.get('created', '')
        if not created_str:
            continue
        
        try:
            if '+' in created_str or created_str.endswith('Z'):
                created_date = pd.Timestamp(created_str)
            else:
                created_date = pd.Timestamp(created_str).tz_localize('UTC')
            history_entries_with_dates.append((created_date, history_entry))
        except:
            continue
    
    # Sort by date descending (most recent first)
    history_entries_with_dates.sort(key=lambda x: x[0], reverse=True)
    
    # Find the most recent status transition
    for created_date, history_entry in history_entries_with_dates:
        if 'items' not in history_entry:
            continue
        
        for item in history_entry.get('items', []):
            if item.get('field') == 'status':
                to_status_id = item.get('to')
                to_status_name = item.get('toString', '')
                
                # Return the status name, preferring the name over ID
                # Normalize status name to canonical format (handles case variations)
                if to_status_name:
                    # Map to canonical status name if it's a known variation
                    status_lower = to_status_name.lower()
                    canonical_statuses = workflow_info['statuses'].values()
                    for canonical in canonical_statuses:
                        if status_lower == canonical.lower():
                            return canonical
                    # If no match found, return as-is (might be a new status)
                    return to_status_name
                elif to_status_id and to_status_id in workflow_info['statuses']:
                    return workflow_info['statuses'][to_status_id]
    
    return None

def extract_resolved_change_required_date(history_data, workflow_info, before_date=None):
    """
    Extract the date when an issue transitioned TO "Resolved - Change Required" status.
    
    If before_date is provided, returns the LATEST transition to "Resolved - Change Required" 
    that comes BEFORE that date. This ensures proper pairing with the final Applied transition.
    
    If before_date is None, returns the LATEST (most recent) transition to "Resolved - Change Required".
    
    Args:
        history_data: List of history entries from JIRA changelog (may be JSON string or list)
        workflow_info: Workflow information dictionary
        before_date: Optional pd.Timestamp - only return dates before this date
        
    Returns:
        Date when transitioned to Resolved - Change Required (pd.Timestamp) or None
    """
    # Handle JSON string if needed
    if isinstance(history_data, str):
        try:
            history_data = json.loads(history_data)
        except:
            return None
    
    if not history_data or not isinstance(history_data, list):
        return None
    
    resolved_change_required_id = '10105'
    resolved_change_required_name = 'Resolved - Change Required'
    resolved_change_required_name_alt = 'Resolved - change required'
    
    resolved_change_required_date = None
    
    for history_entry in history_data:
        if 'items' not in history_entry:
            continue
        
        created_str = history_entry.get('created', '')
        if not created_str:
            continue
        
        try:
            if '+' in created_str or created_str.endswith('Z'):
                created_date = pd.Timestamp(created_str)
            else:
                created_date = pd.Timestamp(created_str).tz_localize('UTC')
        except:
            continue
        
        # If before_date is specified, skip dates that are after it
        if before_date is not None and created_date >= before_date:
            continue
        
        # Check if this is a transition TO "Resolved - Change Required"
        for item in history_entry.get('items', []):
            if item.get('field') == 'status':
                to_status_id = item.get('to')
                to_status_name = item.get('toString', '')
                
                # Check if transitioning TO "Resolved - Change Required"
                if (to_status_id == resolved_change_required_id or 
                    to_status_name == resolved_change_required_name or
                    to_status_name == resolved_change_required_name_alt):
                    # Found the transition to Resolved - Change Required
                    # Use the latest date if there are multiple transitions
                    if resolved_change_required_date is None or created_date > resolved_change_required_date:
                        resolved_change_required_date = created_date
                    break
    
    return resolved_change_required_date

def extract_resolved_to_applied_transition(history_data, workflow_info):
    """
    Extract the date and user for the transition from "Resolved - change required" to "Applied".
    
    This function finds the LAST (most recent) transition from "Resolved - Change Required" to "Applied"
    to handle cases where an issue was erroneously set to Applied and then corrected.
    
    Args:
        history_data: List of history entries from JIRA changelog (may be JSON string or list)
        workflow_info: Workflow information dictionary
        
    Returns:
        Tuple of (date, user_display_name) or (None, None)
    """
    # Handle JSON string if needed
    if isinstance(history_data, str):
        try:
            history_data = json.loads(history_data)
        except:
            return None, None
    
    if not history_data or not isinstance(history_data, list):
        return None, None
    
    resolved_change_required_id = '10105'
    resolved_change_required_name = 'Resolved - change required'
    resolved_change_required_name_alt = 'Resolved - Change Required'
    applied_id = '10107'
    applied_name = 'Applied'
    
    # Collect all transitions from "Resolved - Change Required" to "Applied"
    valid_transitions = []
    
    for history_entry in history_data:
        if 'items' not in history_entry:
            continue
        
        created_str = history_entry.get('created', '')
        if not created_str:
            continue
        
        try:
            if '+' in created_str or created_str.endswith('Z'):
                created_date = pd.Timestamp(created_str)
            else:
                created_date = pd.Timestamp(created_str).tz_localize('UTC')
        except:
            continue
        
        # Check if this is a transition from "Resolved - change required" to "Applied"
        for item in history_entry.get('items', []):
            if item.get('field') == 'status':
                from_status_id = item.get('from')
                from_status_name = item.get('fromString', '')
                to_status_id = item.get('to')
                to_status_name = item.get('toString', '')
                
                # Check if transitioning FROM "Resolved - change required" TO "Applied"
                # Handle both capitalizations
                from_matches = (from_status_id == resolved_change_required_id or 
                               from_status_name == resolved_change_required_name or
                               from_status_name == resolved_change_required_name_alt)
                to_matches = (to_status_id == applied_id or to_status_name == applied_name)
                
                if from_matches and to_matches:
                    # Get the author who made this transition
                    author = history_entry.get('author', {})
                    user_display_name = author.get('displayName', None)
                    valid_transitions.append((created_date, user_display_name))
    
    # Return the LAST (most recent) transition if any exist
    if valid_transitions:
        # Sort by date (most recent first) and return the first one
        valid_transitions.sort(key=lambda x: x[0], reverse=True)
        return valid_transitions[0]
    
    return None, None

def load_history_from_json(history_json_file, issue_keys=None):
    """Load History data from JSON file.
    
    Args:
        history_json_file: Path to JSON file containing history data keyed by issue key
        issue_keys: Optional list of issue keys to load (if None, loads all)
        
    Returns:
        Dictionary mapping issue keys to history data lists
    """
    if not os.path.exists(history_json_file):
        print(f"History JSON file not found: {history_json_file}")
        return {}
    
    try:
        with open(history_json_file, 'r', encoding='utf-8') as f:
            all_history = json.load(f)
        
        if issue_keys:
            # Filter to only requested issue keys
            return {key: all_history.get(key, []) for key in issue_keys}
        else:
            return all_history
    except Exception as e:
        print(f"Error loading History JSON file: {e}")
        return {}

def process_data(df, analysis_periods, history_json_file=None):
    """Process dataframe and add analysis fields"""
    # Get workflow info
    workflow_info = get_jira_workflow_info()
    
    # Convert dates to datetime with UTC timezone
    df['Created Date'] = pd.to_datetime(df['Created Date'], errors='coerce', utc=True)
    
    # Store original Resolution Date if it exists
    if 'Resolution Date' in df.columns:
        df['Original Resolution Date'] = df['Resolution Date']
        df['Original Resolution Date'] = pd.to_datetime(df['Original Resolution Date'], errors='coerce', utc=True)
    
    # Extract transition dates from history if available
    # Check if we have history data (from --history mode)
    # History might be in various column names, or in a separate JSON file
    history_col = None
    history_data_from_json = {}
    
    # First check for History column in DataFrame
    for col_name in ['History', 'history', 'changelog', 'Changelog', 'History Data']:
        if col_name in df.columns:
            history_col = col_name
            break
    
    # If no History column but we have a JSON file, load from JSON
    if not history_col and history_json_file:
        print(f"Loading History data from JSON file: {history_json_file}")
        # Get issue keys from DataFrame (try 'Issue' or 'key' column)
        issue_key_col = 'Issue' if 'Issue' in df.columns else ('key' if 'key' in df.columns else None)
        if issue_key_col:
            issue_keys = df[issue_key_col].dropna().tolist()
            history_data_from_json = load_history_from_json(history_json_file, issue_keys)
            print(f"Loaded History data for {len(history_data_from_json)} issues from JSON file")
        else:
            print("Warning: Could not find issue key column to load History data")
    
    # Helper function to get history for a row (defined outside if block for reuse)
    def get_history_for_row(row):
        if history_col:
            # Get from DataFrame column
            history_str = row[history_col] if history_col in row.index else None
            if pd.notna(history_str) and history_str != '':
                if isinstance(history_str, str):
                    try:
                        return json.loads(history_str)
                    except:
                        return None
                return history_str
        elif history_data_from_json:
            # Get from JSON file
            issue_key_col = 'Issue' if 'Issue' in df.columns else 'key'
            issue_key = row[issue_key_col] if issue_key_col in row.index else None
            if issue_key:
                return history_data_from_json.get(issue_key, None)
        return None
    
    if history_col or history_data_from_json:
        if history_col:
            print(f"Found history data in '{history_col}' column, extracting transition dates...")
        else:
            print("Found history data in JSON file, extracting transition dates...")
        
        # Extract first resolved date from history
        df['First Resolved Date'] = df.apply(
            lambda row: extract_first_resolved_date_from_history(get_history_for_row(row), workflow_info), axis=1
        )
        
        # Extract resolved-to-applied transition
        resolved_to_applied = df.apply(
            lambda row: extract_resolved_to_applied_transition(get_history_for_row(row), workflow_info), axis=1
        )
        df['Resolved to Applied Date'] = resolved_to_applied.apply(lambda x: x[0] if isinstance(x, tuple) else None)
        df['Resolved to Applied User'] = resolved_to_applied.apply(lambda x: x[1] if isinstance(x, tuple) else None)
        
        # Extract Resolved - Change Required date (for gap calculation)
        # Pair it with the final Applied date to ensure we get the correct Resolved - Change Required
        # date that immediately precedes the final Applied transition
        def get_resolved_change_required_date(row):
            history = get_history_for_row(row)
            applied_date = row['Resolved to Applied Date'] if 'Resolved to Applied Date' in row.index else None
            return extract_resolved_change_required_date(history, workflow_info, before_date=applied_date)
        
        df['Resolved Change Required Date'] = df.apply(get_resolved_change_required_date, axis=1)
        
        # Count how many we found
        first_resolved_count = df['First Resolved Date'].notna().sum()
        resolved_to_applied_count = df['Resolved to Applied Date'].notna().sum()
        resolved_change_required_count = df['Resolved Change Required Date'].notna().sum()
        print(f"  Extracted First Resolved Date for {first_resolved_count} issues")
        print(f"  Extracted Resolved to Applied transition for {resolved_to_applied_count} issues")
        print(f"  Extracted Resolved - Change Required date for {resolved_change_required_count} issues")
        
        # Use Resolved to Applied Date for Applied Date - prioritize history-based dates
        # History-based dates are more accurate as they only come from valid transitions
        # (FROM "Resolved - Change Required" TO "Applied"), ignoring erroneous direct transitions
        # 
        # IMPORTANT: We count ALL issues as Applied if they have an Applied Date (including erroneous ones),
        # but only issues with valid transitions will be included in timing metrics.
        if 'Applied Date' not in df.columns or df['Applied Date'].isna().all():
            df['Applied Date'] = df['Resolved to Applied Date']
            print("Using 'Resolved to Applied Date' from history as Applied Date")
        else:
            # Store original Applied Date count before combining
            original_applied_date = df['Applied Date'].copy()
            original_count = original_applied_date.notna().sum()
            
            # Use history-based dates where available, but fall back to original Applied Date
            # This ensures we count all Applied issues, but timing metrics will only use valid transitions
            df['Applied Date'] = df['Resolved to Applied Date'].combine_first(df['Applied Date'])
            history_count = df['Resolved to Applied Date'].notna().sum()
            
            # Count issues that had Applied Date but no valid transition
            had_applied_date = original_applied_date.notna()
            no_valid_transition = had_applied_date & df['Resolved to Applied Date'].isna()
            invalid_count = no_valid_transition.sum()
            
            if history_count > 0:
                print(f"Using 'Resolved to Applied Date' from history (found {history_count} valid transitions). "
                      f"History-based dates are used for timing metrics.")
            if invalid_count > 0:
                print(f"  Note: {invalid_count} issue(s) had Applied Date but no valid transition from "
                      f"'Resolved - Change Required' to 'Applied'. These will be counted as Applied "
                      f"but excluded from timing metrics (ave, median, min gap, max gap).")
        
        # Use Resolved to Applied User for Applied User if not already set or if it's more complete
        if 'Applied User' not in df.columns or df['Applied User'].isna().all():
            df['Applied User'] = df['Resolved to Applied User']
            print("Using 'Resolved to Applied User' from history as Applied User")
        elif df['Resolved to Applied User'].notna().sum() > df['Applied User'].notna().sum():
            # History data has more complete data, use it
            df['Applied User'] = df['Resolved to Applied User'].combine_first(df['Applied User'])
            print("Using 'Resolved to Applied User' from history to supplement Applied User")
    else:
        print("No history data found. Using existing date fields.")
        df['First Resolved Date'] = None
        df['Resolved to Applied Date'] = None
        df['Resolved to Applied User'] = None
    
    # Use Applied Date if available, otherwise use Resolution Date
    if 'Applied Date' in df.columns:
        df['Applied Date'] = pd.to_datetime(df['Applied Date'], errors='coerce', utc=True)
        df['Resolution Date'] = df['Applied Date']
        print("Using 'Applied Date' from history records as the resolution date")
    elif 'Resolution Date' in df.columns:
        df['Resolution Date'] = pd.to_datetime(df['Resolution Date'], errors='coerce', utc=True)
    else:
        print("WARNING: Neither 'Applied Date' nor 'Resolution Date' found.")
        if 'First Resolved Date' in df.columns:
            df['Resolution Date'] = df['First Resolved Date']
            print("Using 'First Resolved Date' as Resolution Date")
        else:
            print("ERROR: No resolution date available. Cannot continue.")
            return None
    
    # Use First Resolved Date for resolution time calculation if available
    if 'First Resolved Date' in df.columns and df['First Resolved Date'].notna().any():
        df['Resolution Date for Tempo'] = df['First Resolved Date']
        print("Using 'First Resolved Date' for resolution tempo calculations")
    else:
        df['Resolution Date for Tempo'] = df['Resolution Date']
    
    # Add basic derived fields
    df['is_resolved'] = df['Resolution Date'].notnull()
    df['days_to_resolution'] = (df['Resolution Date for Tempo'] - df['Created Date']).dt.total_seconds() / 86400.0
    
    # NEW: Add status information based on history data
    # Check if we have status information in the data (check multiple possible column names)
    if 'Current Status' in df.columns:
        df['Status'] = df['Current Status']
    elif 'Status' in df.columns:
        df['Status'] = df['Status']
    elif 'status' in df.columns:
        df['Status'] = df['status']
    elif 'History' in df.columns or history_data_from_json:
        # Extract current status from History column or JSON file
        print("No Status column found. Extracting current status from History data...")
        df['Status'] = df.apply(
            lambda row: extract_current_status_from_history(get_history_for_row(row), workflow_info), axis=1
        )
        status_extracted_count = df['Status'].notna().sum()
        print(f"  Extracted current status for {status_extracted_count} issues from History")
        
        # Normalize status values to canonical format (handles case variations from JIRA API)
        # This ensures consistency even if JIRA returns status names with different case
        if 'Status' in df.columns:
            status_normalization_map = {
                'Resolved - change required': 'Resolved - Change Required',
                'resolved - change required': 'Resolved - Change Required',
                'RESOLVED - CHANGE REQUIRED': 'Resolved - Change Required',
                'Resolved - Change required': 'Resolved - Change Required',
                'Resolved - change Required': 'Resolved - Change Required',
                'Resolved - no change': 'Resolved - No Change',
                'resolved - no change': 'Resolved - No Change',
                'RESOLVED - NO CHANGE': 'Resolved - No Change',
                'Resolved - No change': 'Resolved - No Change',
                'Resolved - no Change': 'Resolved - No Change',
                'Waiting for input': 'Waiting for Input',
                'waiting for input': 'Waiting for Input',
                'WAITING FOR INPUT': 'Waiting for Input',
            }
            # Apply normalization using case-insensitive matching
            for old_status, new_status in status_normalization_map.items():
                mask = df['Status'].str.strip().str.lower() == old_status.lower()
                if mask.any():
                    df.loc[mask, 'Status'] = new_status
            
            # Also handle case-insensitive matching for any status that matches canonical format
            canonical_statuses = set(workflow_info['statuses'].values())
            for status_value in df['Status'].dropna().unique():
                status_str = str(status_value).strip()
                if status_str not in canonical_statuses:
                    status_lower = status_str.lower()
                    for canonical in canonical_statuses:
                        if status_lower == canonical.lower():
                            mask = df['Status'] == status_value
                            df.loc[mask, 'Status'] = canonical
                            break
        
        # For issues where we couldn't extract status from history, infer from dates
        missing_status_mask = df['Status'].isna()
        if missing_status_mask.any():
            df.loc[missing_status_mask, 'Status'] = 'Unresolved'
            # Mark as Applied if Applied Date exists
            df.loc[missing_status_mask & df['Applied Date'].notna(), 'Status'] = 'Applied'
            # For resolved but not applied, mark as generic resolved state
            df.loc[
                missing_status_mask & df['Applied Date'].isna() & df['Resolution Date'].notna(),
                'Status'
            ] = 'Resolved (not applied)'
    else:
        # Infer status from resolution fields (this is expected when using history-based data)
        # We can't determine exact status without the Status field, but we can infer categories
        df['Status'] = 'Unresolved'

        # Mark as Applied if Applied Date exists
        df.loc[df['Applied Date'].notna(), 'Status'] = 'Applied'
    
    # Normalize status values to canonical format (handles case variations)
    # This ensures consistency regardless of where the Status column came from (CSV, history, or inferred)
    if 'Status' in df.columns:
        status_normalization_map = {
            'Resolved - change required': 'Resolved - Change Required',
            'resolved - change required': 'Resolved - Change Required',
            'RESOLVED - CHANGE REQUIRED': 'Resolved - Change Required',
            'Resolved - Change required': 'Resolved - Change Required',
            'Resolved - change Required': 'Resolved - Change Required',
            'Resolved - no change': 'Resolved - No Change',
            'resolved - no change': 'Resolved - No Change',
            'RESOLVED - NO CHANGE': 'Resolved - No Change',
            'Resolved - No change': 'Resolved - No Change',
            'Resolved - no Change': 'Resolved - No Change',
            'Waiting for input': 'Waiting for Input',
            'waiting for input': 'Waiting for Input',
            'WAITING FOR INPUT': 'Waiting for Input',
        }
        # Apply normalization using case-insensitive matching
        for old_status, new_status in status_normalization_map.items():
            mask = df['Status'].str.strip().str.lower() == old_status.lower()
            if mask.any():
                df.loc[mask, 'Status'] = new_status
        
        # Also handle case-insensitive matching for any status that matches canonical format
        canonical_statuses = set(workflow_info['statuses'].values())
        for status_value in df['Status'].dropna().unique():
            status_str = str(status_value).strip()
            if status_str not in canonical_statuses:
                status_lower = status_str.lower()
                for canonical in canonical_statuses:
                    if status_lower == canonical.lower():
                        mask = df['Status'] == status_value
                        df.loc[mask, 'Status'] = canonical
                        break

        # For resolved but not applied, we can't determine exact status, but we'll mark as a generic resolved state
        # This will be categorized based on other logic
        df.loc[
            df['Applied Date'].isna() & df['Resolution Date'].notna(),
            'Status'
        ] = 'Resolved (not applied)'
    
    # NEW: Add flag indicating if an issue can be applied (in "Resolved - change required" status)
    df['can_be_applied'] = df['Status'].isin(workflow_info['can_be_applied'])
    
    # NEW: Create Category column for backlog calculation
    # This needs to happen before backlog calculation
    if 'Category' not in df.columns:
        # Try to get status from various possible column names
        status_col = None
        if 'Status' in df.columns:
            status_col = 'Status'
        elif 'Current Status' in df.columns:
            status_col = 'Current Status'
        elif 'status' in df.columns:
            status_col = 'status'
        
        if status_col:
            df['Category'] = df[status_col].apply(lambda x: categorize_issue_by_state(x, workflow_info))
            
            # Handle inferred statuses that couldn't be categorized
            unresolved_mask = df['Category'] == 'Unknown'
            if unresolved_mask.any():
                if 'Resolution Date' in df.columns and 'Applied Date' in df.columns:
                    # If resolved but not applied, might be "Resolved - Change Required" (Doing)
                    resolved_not_applied = unresolved_mask & df['Resolution Date'].notna() & df['Applied Date'].isna()
                    df.loc[resolved_not_applied, 'Category'] = 'Doing'
                    
                    # If not resolved, likely in Deciding states
                    not_resolved = unresolved_mask & df['Resolution Date'].isna()
                    df.loc[not_resolved, 'Category'] = 'Deciding'
                    
                    # If applied, should be Doing
                    applied = unresolved_mask & df['Applied Date'].notna()
                    df.loc[applied, 'Category'] = 'Doing'
                elif 'is_resolved' in df.columns:
                    df.loc[unresolved_mask & df['is_resolved'], 'Category'] = 'Done'
                    df.loc[unresolved_mask & ~df['is_resolved'], 'Category'] = 'Deciding'
                else:
                    df.loc[unresolved_mask, 'Category'] = 'Deciding'
        else:
            # No status column - infer from other fields
            df['Category'] = 'Unknown'
            if 'Applied Date' in df.columns:
                df.loc[df['Applied Date'].notna(), 'Category'] = 'Doing'
            if 'Resolution Date' in df.columns and 'Applied Date' in df.columns:
                resolved_not_applied = df['Resolution Date'].notna() & df['Applied Date'].isna()
                df.loc[resolved_not_applied, 'Category'] = 'Done'
            if 'is_resolved' in df.columns:
                df.loc[~df['is_resolved'] & (df['Category'] == 'Unknown'), 'Category'] = 'Deciding'
    
    # NEW: Calculate resolution to application time
    # This should be from "Resolved - change required" to "Applied"
    # Try to use history-based dates first, then fall back to Resolution Date
    if 'Resolved to Applied Date' in df.columns and df['Resolved to Applied Date'].notna().any():
        # We have the exact transition date from history
        # Need to find when it first reached "Resolved - change required"
        print("Calculating application time using history-based transition dates...")
        # For now, use Original Resolution Date if available, otherwise use Resolution Date
        resolution_date_col = 'Original Resolution Date' if 'Original Resolution Date' in df.columns else 'Resolution Date'
        mask = df['Resolved to Applied Date'].notna() & df[resolution_date_col].notna()
        df.loc[mask, 'days_from_resolution_to_application'] = (
            pd.to_datetime(df.loc[mask, 'Resolved to Applied Date']) - 
            pd.to_datetime(df.loc[mask, resolution_date_col])
        ).dt.total_seconds() / 86400.0
    elif 'Original Resolution Date' in df.columns and 'Applied Date' in df.columns:
        mask = df['Original Resolution Date'].notna() & df['Applied Date'].notna()
        df.loc[mask, 'days_from_resolution_to_application'] = (
            pd.to_datetime(df.loc[mask, 'Applied Date']) - 
            pd.to_datetime(df.loc[mask, 'Original Resolution Date'])
        ).dt.total_seconds() / 86400.0
    
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
        
        # Backlog definition: issues in "Deciding" category at end of period
        # Deciding includes: Submitted, Triaged, Waiting for Input, Deferred
        df[f'backlog_at_{label}_end'] = (
            (df['Created Date'] <= end_date) & 
            (df['Category'] == 'Deciding')
        )
    
    return df

def categorize_issue_by_state(status, workflow_info):
    """
    Categorize an issue by its current state into: New, Deciding, Doing, Done
    
    Args:
        status: Current status name or ID
        workflow_info: Workflow information dictionary
        
    Returns:
        Category string: 'New', 'Deciding', 'Doing', 'Done', or 'Unknown'
    """
    if pd.isna(status):
        return 'Unknown'
    
    status_str = str(status).strip()
    
    # Handle inferred status values that don't match workflow names
    if status_str == 'Unresolved':
        # Can't determine exact status, but it's not resolved, so likely Deciding or Doing
        # We'll need to infer from other fields - return Unknown for now, will be handled elsewhere
        return 'Unknown'
    elif status_str == 'Resolved (not applied)':
        # Resolved but not applied - could be Done (No Change, Deferred, Duplicate, Published) 
        # or Doing (Change Required). Can't determine without more info.
        return 'Unknown'
    
    # Check if it's a status ID
    if status_str in workflow_info['statuses']:
        status_id = status_str
    elif status_str in workflow_info['status_name_to_id']:
        status_id = workflow_info['status_name_to_id'][status_str]
    else:
        # Try to match by name (case-insensitive and flexible matching)
        status_id = None
        status_str_lower = status_str.lower()
        for sid, sname in workflow_info['statuses'].items():
            sname_lower = sname.lower()
            # Exact match or contains match
            if sname_lower == status_str_lower or status_str_lower in sname_lower or sname_lower in status_str_lower:
                status_id = sid
                break
        
        # Also check against state name lists (case-insensitive)
        if status_id is None:
            for sid, sname in workflow_info['statuses'].items():
                if status_str_lower == sname.lower():
                    status_id = sid
                    break
    
    if status_id is None:
        return 'Unknown'
    
    if status_id in workflow_info['deciding_states']:
        return 'Deciding'
    elif status_id in workflow_info['doing_states']:
        return 'Doing'
    elif status_id in workflow_info['done_states']:
        return 'Done'
    else:
        return 'Unknown'

def count_by_category(df, period_str, workflow_info):
    """
    Count issues by category (New, Deciding, Doing, Done) for a period.
    
    Args:
        df: DataFrame with issue data
        period_str: Period string (e.g., '2025T1')
        workflow_info: Workflow information dictionary
        
    Returns:
        Dictionary with counts for each category
    """
    start_date, end_date, label = parse_time_period(period_str)
    
    # New: Issues created in this period
    new_mask = (df['Created Date'] >= start_date) & (df['Created Date'] <= end_date)
    new_count = new_mask.sum()
    
    # For state-based counts, we need to check status at the end of the period
    # Issues that exist at the end of the period
    exists_at_end = df['Created Date'] <= end_date
    
    # Get current status for categorization
    # Create a temporary category column if it doesn't exist
    if 'Category' not in df.columns:
        # Try to get status from various possible column names
        status_col = None
        if 'Status' in df.columns:
            status_col = 'Status'
        elif 'Current Status' in df.columns:
            status_col = 'Current Status'
        elif 'status' in df.columns:
            status_col = 'status'
        
        if status_col:
            df['Category'] = df[status_col].apply(lambda x: categorize_issue_by_state(x, workflow_info))
            
            # Handle inferred statuses that couldn't be categorized
            # For 'Unresolved' - if not resolved, could be Deciding (Submitted, Triaged, Waiting for Input, Deferred)
            # or Doing (Resolved - Change Required). Since we can't tell, we'll use a heuristic:
            # If it has a Resolution Date but no Applied Date, it might be in "Resolved - Change Required" (Doing)
            # Otherwise, assume Deciding
            unresolved_mask = df['Category'] == 'Unknown'
            if unresolved_mask.any():
                # Check if these have resolution dates
                if 'Resolution Date' in df.columns and 'Applied Date' in df.columns:
                    # If resolved but not applied, might be "Resolved - Change Required" (Doing)
                    resolved_not_applied = unresolved_mask & df['Resolution Date'].notna() & df['Applied Date'].isna()
                    df.loc[resolved_not_applied, 'Category'] = 'Doing'  # Likely Resolved - Change Required
                    
                    # If not resolved, likely in Deciding states
                    not_resolved = unresolved_mask & df['Resolution Date'].isna()
                    df.loc[not_resolved, 'Category'] = 'Deciding'
                    
                    # If applied, should be Doing
                    applied = unresolved_mask & df['Applied Date'].notna()
                    df.loc[applied, 'Category'] = 'Doing'
                elif 'is_resolved' in df.columns:
                    # Fallback: if resolved, likely Done (but could be Doing if Resolved - Change Required)
                    # Since we can't tell, we'll mark resolved as Done and unresolved as Deciding
                    df.loc[unresolved_mask & df['is_resolved'], 'Category'] = 'Done'
                    df.loc[unresolved_mask & ~df['is_resolved'], 'Category'] = 'Deciding'
                else:
                    # Last resort: mark as Deciding (most common for unresolved issues)
                    df.loc[unresolved_mask, 'Category'] = 'Deciding'
        else:
            # No status column - infer from other fields
            df['Category'] = 'Unknown'
            if 'Applied Date' in df.columns:
                df.loc[df['Applied Date'].notna(), 'Category'] = 'Doing'  # Applied
            if 'Resolution Date' in df.columns and 'Applied Date' in df.columns:
                # Resolved but not applied - could be Done or Doing
                resolved_not_applied = df['Resolution Date'].notna() & df['Applied Date'].isna()
                df.loc[resolved_not_applied, 'Category'] = 'Done'  # Assume Done (could be wrong)
            if 'is_resolved' in df.columns:
                # Mark unresolved as Deciding
                df.loc[~df['is_resolved'] & (df['Category'] == 'Unknown'), 'Category'] = 'Deciding'
    
    # Count by category for issues that exist at period end
    deciding_mask = exists_at_end & (df['Category'] == 'Deciding')
    doing_mask = exists_at_end & (df['Category'] == 'Doing')
    done_mask = exists_at_end & (df['Category'] == 'Done')
    
    return {
        'new': new_count,
        'deciding': deciding_mask.sum(),
        'doing': doing_mask.sum(),
        'done': done_mask.sum()
    }

def calculate_tempo_metrics(df, period_str, workflow_info):
    """
    Calculate tempo metrics: Resolution time and Application time.
    
    Resolution time: Created to first transition to any resolved state
    Application time: Resolved - change required to Applied
    
    Args:
        df: DataFrame with issue data
        period_str: Period string (e.g., '2025T1')
        workflow_info: Workflow information dictionary
        
    Returns:
        Dictionary with tempo metrics
    """
    start_date, end_date, label = parse_time_period(period_str)
    
    # Resolution time: Created to first resolved state
    # Use First Resolved Date if available (from history), otherwise use Resolution Date for Tempo
    if 'First Resolved Date' in df.columns and df['First Resolved Date'].notna().any():
        # Use First Resolved Date for more accurate resolution time
        resolved_mask = df['First Resolved Date'].notna()
        resolved_in_period = resolved_mask & (df['First Resolved Date'] >= start_date) & (df['First Resolved Date'] <= end_date)
        # Calculate days from Created to First Resolved
        resolution_times = (df.loc[resolved_in_period, 'First Resolved Date'] - 
                           df.loc[resolved_in_period, 'Created Date']).dt.total_seconds() / 86400.0
    else:
        # Fall back to Resolution Date for Tempo
        resolved_mask = df['Resolution Date for Tempo'].notna()
        resolved_in_period = resolved_mask & (df['Resolution Date for Tempo'] >= start_date) & (df['Resolution Date for Tempo'] <= end_date)
        resolution_times = df.loc[resolved_in_period, 'days_to_resolution']
    
    resolution_metrics = {}
    if not resolution_times.empty:
        resolution_metrics = {
            'count': len(resolution_times),
            'ave': resolution_times.mean(),
            'median': resolution_times.median(),
            'p80': resolution_times.quantile(0.8)
        }
    else:
        resolution_metrics = {
            'count': 0,
            'ave': None,
            'median': None,
            'p80': None
        }
    
    # Application time: Resolved - change required to Applied
    # Filter to issues that were applied in this period
    applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
    applied_in_period = applied_mask & df['days_from_resolution_to_application'].notna()
    
    application_times = df.loc[applied_in_period, 'days_from_resolution_to_application']
    
    application_metrics = {}
    if not application_times.empty:
        application_metrics = {
            'count': len(application_times),
            'ave': application_times.mean(),
            'median': application_times.median()
        }
    else:
        application_metrics = {
            'count': 0,
            'ave': None,
            'median': None
        }
    
    return {
        'resolution': resolution_metrics,
        'application': application_metrics
    }

def get_period_metrics(df, period_str):
    """Get metrics for a specific analysis period"""
    start_date, end_date, label = parse_time_period(period_str)

    # New issues = created in this period
    new_issues = df[f'created_in_{label}'].sum()

    # Applied issues = Applied Date in this period
    applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
    applied_issues = applied_mask.sum()

    # Backlog = issues in "Deciding" category at the end of the period
    backlog = df[f'backlog_at_{label}_end'].sum()

    # Time to apply = from Created to Applied Date for issues applied in period
    times = df.loc[applied_mask, 'days_to_resolution']
    if not times.empty:
        ave = times.mean()
        med = times.median()
        p80 = times.quantile(0.8)
    else:
        ave = med = p80 = None

    return new_issues, applied_issues, backlog, ave, med, p80

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
    """Get metrics for a specific tri-period (T1, T2, T3)"""
    start_date, end_date, label = parse_time_period(tri_str)

    # New issues = created in this period
    new_mask = (df['Created Date'] >= start_date) & (df['Created Date'] <= end_date)
    new_issues = new_mask.sum()

    # Applied issues = Applied Date in this period
    applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
    applied_issues = applied_mask.sum()

    # Backlog at end = issues in "Deciding" category
    backlog = df[f'backlog_at_{label}_end'].sum()

    # Time from Created to Applied for applied issues
    times = df.loc[applied_mask, 'days_to_resolution']
    if not times.empty:
        ave = times.mean()
        med = times.median()
        p80 = times.quantile(0.8)
    else:
        ave = med = p80 = None

    return label, new_issues, applied_issues, backlog, ave, med, p80

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

def format_number(value, decimals=0):
    """Format a number with thousands separators and optional decimal places"""
    try:
        if value is None:
            return "N/A"
        if pd.isna(value):
            return "N/A"
        if decimals == 0:
            return f"{int(round(value)):,}"
        else:
            return f"{round(value, decimals):,.{decimals}f}"
    except (TypeError, ValueError):
        return "N/A"

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
def analyze_appliers(df, period_str, staff_list=None):
    """
    Analyze issue appliers for a specific period.
    Appliers are identified as the person who made the transition from 
    "Resolved - change required" to "Applied".
    
    Returns similar statistics to analyze_submitters:
    - total_appliers_ever: Total unique appliers through end of period
    - total_appliers_in_period: Total unique appliers in this period
    - total_new_appliers: New appliers in this period (not seen before)
    - new_applier_percent: Percentage of new appliers
    - top_period_appliers: Top 10 appliers for this period
    - top_all_time_appliers: Top 10 appliers of all time through end of period
    """
    # Prefer Resolved to Applied User (from history) over Applied User
    applier_col = 'Resolved to Applied User' if 'Resolved to Applied User' in df.columns else 'Applied User'
    
    if applier_col not in df.columns or df[applier_col].isna().all():
        return None

    # Filter by Applied Date (or Resolved to Applied Date if available)
    applied_date_col = 'Resolved to Applied Date' if 'Resolved to Applied Date' in df.columns else 'Applied Date'
    if applied_date_col not in df.columns:
        return None
    
    start_date, end_date, label = parse_time_period(period_str)
    
    # Get earliest date in the dataset (for appliers, use earliest Applied Date)
    applied_dates = df[applied_date_col].dropna()
    if applied_dates.empty:
        return None
    
    earliest_date = applied_dates.min()
    
    # Get all data from start of dataset through end of analysis period
    historical_mask = (df[applied_date_col].notna()) & (df[applied_date_col] >= earliest_date) & (df[applied_date_col] <= end_date)
    historical_df = df[historical_mask]
    
    # Filter out None/NaN values for applier column
    historical_df = historical_df[historical_df[applier_col].notna()]
    
    if historical_df.empty:
        return None
    
    # Get all appliers through the end of the analysis period
    all_appliers = set(historical_df[applier_col].dropna().unique())
    total_appliers_ever = len(all_appliers)
    
    # Get appliers before this period
    before_period_mask = df[applied_date_col].notna() & (df[applied_date_col] < start_date)
    before_period_df = df[before_period_mask]
    before_period_df = before_period_df[before_period_df[applier_col].notna()]
    before_period_appliers = set(before_period_df[applier_col].dropna().unique())
    
    # Get appliers in this period
    period_mask = df[applied_date_col].notna() & (df[applied_date_col] >= start_date) & (df[applied_date_col] <= end_date)
    period_df = df[period_mask]
    period_df = period_df[period_df[applier_col].notna()]
    
    if period_df.empty:
        return None
    
    period_appliers = set(period_df[applier_col].dropna().unique())
    total_appliers_in_period = len(period_appliers)
    
    # Find new appliers in this period
    new_appliers = period_appliers - before_period_appliers
    total_new_appliers = len(new_appliers)
    
    # Calculate percentage of new appliers relative to this period
    if total_appliers_in_period > 0:
        new_applier_percent = (total_new_appliers / total_appliers_in_period) * 100
    else:
        new_applier_percent = 0
    
    # Get top appliers during this period (excluding staff if staff_list provided)
    period_applier_counts = period_df.groupby(applier_col).size().reset_index(name='Issue Count')
    period_applier_counts.columns = ['Applier', 'Issue Count']
    if staff_list:
        period_applier_counts = period_applier_counts[~period_applier_counts['Applier'].isin(staff_list)]
    period_applier_counts = period_applier_counts.sort_values(by='Issue Count', ascending=False)
    top_period_appliers = period_applier_counts.head(10)
    
    # Get top appliers of all time through end of analysis period (excluding staff if staff_list provided)
    all_time_applier_counts = historical_df.groupby(applier_col).size().reset_index(name='Issue Count')
    all_time_applier_counts.columns = ['Applier', 'Issue Count']
    if staff_list:
        all_time_applier_counts = all_time_applier_counts[~all_time_applier_counts['Applier'].isin(staff_list)]
    all_time_applier_counts = all_time_applier_counts.sort_values(by='Issue Count', ascending=False)
    top_all_time_appliers = all_time_applier_counts.head(10)
    
    return {
        'total_appliers_ever': total_appliers_ever,
        'total_appliers_in_period': total_appliers_in_period,
        'total_new_appliers': total_new_appliers,
        'new_applier_percent': new_applier_percent,
        'top_period_appliers': top_period_appliers,
        'top_all_time_appliers': top_all_time_appliers
    }

def get_status_category_emoji(status):
    """Get the category emoji for a status."""
    if pd.isna(status):
        return "❓"
    
    status_str = str(status).strip()
    
    # Map statuses to category emojis
    # Deciding states
    if status_str in ['Submitted', 'Triaged', 'Waiting for Input', 'Deferred']:
        return "🤔"
    # Doing states
    elif status_str in ['Resolved - Change Required', 'Resolved - change required', 'Applied']:
        return "⚙️"
    # Done states
    elif status_str in ['Published', 'Duplicate', 'Resolved - No Change']:
        return "✅"
    # New/Unresolved (not a workflow status, but may appear in data)
    elif status_str in ['New', 'Unresolved']:
        return "🆕"
    else:
        return "❓"

def get_status_sort_order(status):
    """Get the sort order for a status."""
    sort_order = {
        'New': 0,
        'Unresolved': 0,
        'Submitted': 1,
        'Triaged': 2,
        'Waiting for Input': 3,
        'Deferred': 4,
        'Resolved - Change Required': 5,
        'Resolved - change required': 5,
        'Applied': 6,
        'Duplicate': 7,
        'Resolved - No Change': 8,
        'Published': 9
    }
    
    if pd.isna(status):
        return 999
    
    status_str = str(status).strip()
    return sort_order.get(status_str, 999)

# NEW: Analyze status distribution
def analyze_status_distribution(df, period_str):
    """Analyze the distribution of statuses for issues at the end of a period."""
    _, end_date, label = parse_time_period(period_str)
    
    # Get workflow info
    workflow_info = get_jira_workflow_info()
    
    # Get issues created before or during this period
    issues_mask = df['Created Date'] <= end_date
    
    # Count by status
    if 'Status' in df.columns:
        status_counts = df[issues_mask]['Status'].value_counts()
        
        # Create a DataFrame with status names and counts
        status_df = pd.DataFrame({
            'Status': status_counts.index,
            'Count': status_counts.values
        })
        
        # Map status IDs to names if needed
        if status_df['Status'].dtype == 'object' and status_df['Status'].str.isnumeric().any():
            status_df['Status'] = status_df['Status'].map(
                lambda x: workflow_info['statuses'].get(x, x) if isinstance(x, str) else x
            )
        
        # Normalize status names (handle case variations)
        status_name_mapping = {
            'Resolved - change required': 'Resolved - Change Required',
            'resolved - change required': 'Resolved - Change Required',
            'Resolved - no change': 'Resolved - No Change',
            'resolved - no change': 'Resolved - No Change'
        }
        status_df['Status'] = status_df['Status'].replace(status_name_mapping)
        
        # Re-aggregate counts in case normalization merged entries
        status_df = status_df.groupby('Status', as_index=False)['Count'].sum()
        
        # Add category emoji column
        status_df['Category'] = status_df['Status'].apply(get_status_category_emoji)
        
        # Add sort order column
        status_df['SortOrder'] = status_df['Status'].apply(get_status_sort_order)
        
        # Calculate percentage
        total = status_df['Count'].sum()
        status_df['Percentage'] = (status_df['Count'] / total * 100).round(1)
        
        # Sort by specified order, then by count for ties
        status_df = status_df.sort_values(['SortOrder', 'Count'], ascending=[True, False])
        
        # Exclude "Unresolved" and "Resolved (not applied)" as they are not real workflow statuses
        status_df = status_df[~status_df['Status'].isin(['Unresolved', 'Resolved (not applied)'])]
        
        return status_df
    else:
        return None

def analyze_issue_types(df, period_str):
    """Analyze issue types for a specific period using Applied Date"""
    start_date, end_date, label = parse_time_period(period_str)

    # Skip if the Issue Type column doesn't exist
    if 'Issue Type' not in df.columns:
        return None

    # New issues = created in this period
    new_mask = (df['Created Date'] >= start_date) & (df['Created Date'] <= end_date)
    new_df = df[new_mask]

    # Applied issues = Applied Date in this period
    applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
    applied_df = df[applied_mask]

    # Count issues by type
    new_counts = new_df['Issue Type'].value_counts().reset_index()
    new_counts.columns = ['Issue Type', 'New Count']

    applied_counts = applied_df['Issue Type'].value_counts().reset_index()
    applied_counts.columns = ['Issue Type', 'Applied Count']

    # Calculate time-to-apply metrics
    resolution_times = applied_df.groupby('Issue Type')['days_to_resolution'].agg(['mean', 'median']).reset_index()
    resolution_times.columns = ['Issue Type', 'Avg Days', 'Median Days']

    # P80 calculation
    def calculate_p80(issue_type):
        times = applied_df.loc[applied_df['Issue Type'] == issue_type, 'days_to_resolution']
        return times.quantile(0.8) if len(times) >= 5 else None

    resolution_times['P80 Days'] = resolution_times['Issue Type'].apply(calculate_p80)

    # Add performance band
    resolution_times['Performance'] = resolution_times['P80 Days'].apply(get_performance_band)

    # Backlog = issues in "Deciding" category at period end
    backlog_mask = df[f'backlog_at_{label}_end']
    backlog_df = df[backlog_mask]
    backlog_counts = backlog_df['Issue Type'].value_counts().reset_index()
    backlog_counts.columns = ['Issue Type', 'Backlog Count']

    # Merge all
    merged = pd.merge(new_counts, applied_counts, on='Issue Type', how='outer')
    merged = pd.merge(merged, resolution_times, on='Issue Type', how='outer')
    merged = pd.merge(merged, backlog_counts, on='Issue Type', how='outer')

    # Fill NaNs
    merged['New Count'] = merged['New Count'].fillna(0).astype(int)
    merged['Applied Count'] = merged['Applied Count'].fillna(0).astype(int)
    merged['Backlog Count'] = merged['Backlog Count'].fillna(0).astype(int)

    return merged

def count_applied_without_transition_history(df, period_str):
    """
    Count issues that were Applied in the period but don't have transition history
    from "Resolved - Change Required" status.
    
    Args:
        df: DataFrame with issue data
        period_str: Period string (e.g., "2025T1")
    
    Returns:
        int: Count of issues applied without transition history
    """
    start_date, end_date, _ = parse_time_period(period_str)
    
    # Find issues applied in this period
    applied_mask = df['Applied Date'].notna() & \
                  (df['Applied Date'] >= start_date) & \
                  (df['Applied Date'] <= end_date)
    
    # Issues without transition history are those that:
    # 1. Have Applied Date in period
    # 2. Don't have days_from_resolution_to_application set (or it's NaN)
    #    OR don't have Resolved Change Required Date
    applied_in_period = df[applied_mask]
    
    # Count issues without transition history
    # These are issues that don't have the gap calculation field set
    without_history = applied_in_period[
        applied_in_period['days_from_resolution_to_application'].isna()
    ]
    
    return len(without_history)

def analyze_resolution_to_application_gap(df, period_str):
    """
    Analyze the gap between when an issue was marked as "Resolved - Change Required" 
    and when it was applied to the specification.
    
    Only includes issues that actually went through the "Resolved - Change Required" state
    AND have a valid transition from "Resolved - Change Required" to "Applied".
    Issues that were erroneously set directly to Applied (e.g., Triaged → Applied) are excluded
    from timing metrics but still counted as Applied.
    """
    if 'Applied Date' not in df.columns:
        return None

    start_date, end_date, label = parse_time_period(period_str)

    # Filter to issues applied in this period
    applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
    
    # Prefer Resolved Change Required Date from history, fall back to Resolved to Applied Date logic
    # We need both the Resolved - Change Required date and the Applied date
    if 'Resolved Change Required Date' in df.columns:
        # Use the date when it transitioned TO "Resolved - Change Required"
        resolved_change_required_col = 'Resolved Change Required Date'
    elif 'Resolved to Applied Date' in df.columns:
        # Fallback: if we have Resolved to Applied Date, we can infer the Resolved - Change Required date
        # by looking at the transition FROM "Resolved - Change Required" TO "Applied"
        # But we need the date BEFORE the Applied date - this is tricky without history
        # For now, use Original Resolution Date as fallback
        resolved_change_required_col = 'Original Resolution Date' if 'Original Resolution Date' in df.columns else None
    else:
        resolved_change_required_col = 'Original Resolution Date' if 'Original Resolution Date' in df.columns else None
    
    if resolved_change_required_col is None:
        return None
    
    # Only include issues that have a valid transition from "Resolved - Change Required" to "Applied"
    # This ensures we exclude erroneously set Applied issues from timing metrics
    # Issues are still counted as Applied, but won't be in timing calculations
    
    # Filter to issues that have both dates AND a valid transition
    if 'Resolved to Applied Date' in df.columns:
        df_with_both = df[applied_mask & df[resolved_change_required_col].notna() & df['Resolved to Applied Date'].notna()].copy()
    else:
        # Fallback: if no Resolved to Applied Date column, use all issues with both dates
        df_with_both = df[applied_mask & df[resolved_change_required_col].notna()].copy()

    if df_with_both.empty:
        return None

    df_with_both[resolved_change_required_col] = pd.to_datetime(df_with_both[resolved_change_required_col], errors='coerce', utc=True)
    df_with_both['Applied Date'] = pd.to_datetime(df_with_both['Applied Date'], errors='coerce', utc=True)

    # Calculate gap: Applied Date - Resolved Change Required Date
    df_with_both['days_from_resolution_to_application'] = (
        df_with_both['Applied Date'] - df_with_both[resolved_change_required_col]
    ).dt.total_seconds() / 86400.0
    
    # Filter out negative gaps (data quality issues - shouldn't happen if dates are correct)
    # But keep them for reporting min/max to help identify data issues
    positive_gaps = df_with_both[df_with_both['days_from_resolution_to_application'] >= 0]['days_from_resolution_to_application']
    negative_mask = df_with_both['days_from_resolution_to_application'] < 0
    negative_count = negative_mask.sum()
    
    # Get issue IDs for negative gaps
    negative_issue_ids = []
    if negative_count > 0:
        # Find the issue key column
        issue_key_col = None
        for col in ['Issue', 'key', 'Key', 'Issue Key', 'Issue ID']:
            if col in df_with_both.columns:
                issue_key_col = col
                break
        
        if issue_key_col:
            negative_issues = df_with_both[negative_mask]
            negative_issue_ids = negative_issues[issue_key_col].dropna().tolist()
        
        print(f"  Warning: Found {negative_count} issues with negative gap (Applied Date before Resolved - Change Required Date)")
        print(f"    These may be cases where issues were erroneously set to Applied, then corrected.")
        print(f"    The corrected gap time (using the final Applied transition) is being used for calculations.")
        if negative_issue_ids:
            print(f"    Issue IDs with negative gaps: {', '.join(str(id) for id in negative_issue_ids[:20])}" + 
                  (f" (and {len(negative_issue_ids) - 20} more)" if len(negative_issue_ids) > 20 else ""))
    
    # Calculate statistics, rounding to whole numbers
    gap_stats = {
        'count': len(df_with_both),
        'mean': round(df_with_both['days_from_resolution_to_application'].mean()) if not df_with_both['days_from_resolution_to_application'].empty else None,
        'median': round(df_with_both['days_from_resolution_to_application'].median()) if not df_with_both['days_from_resolution_to_application'].empty else None,
        'p80': round(df_with_both['days_from_resolution_to_application'].quantile(0.8)) if not df_with_both['days_from_resolution_to_application'].empty else None,
        'min': round(df_with_both['days_from_resolution_to_application'].min()) if not df_with_both['days_from_resolution_to_application'].empty else None,
        'max': round(df_with_both['days_from_resolution_to_application'].max()) if not df_with_both['days_from_resolution_to_application'].empty else None,
        'negative_count': negative_count,
        'negative_issue_ids': negative_issue_ids
    }

    return gap_stats
# NEW: Generate workflow diagram in markdown
def generate_workflow_diagram():
    """Generate a mermaid diagram of the JIRA workflow."""
    workflow_info = get_jira_workflow_info()
    
    # Define diagram
    diagram = [
        "```mermaid",
        "graph TD",
        "    A[Submitted] --> B[Triaged]",
        "    B --> C[Waiting for Input]",
        "    C --> B",
        "    B --> F[Deferred]",
        "    F --> B",
        "    B --> D[Resolved - No Change]",
        "    B --> E[Resolved - Change Required]",
        "    B --> G[Duplicate]",
        "    E --> H[Applied]",
        "    H --> I[Published]",
        "    ",
        "    classDef terminal fill:#d9f7be,stroke:#52c41a;",
        "    classDef canBeApplied fill:#91caff,stroke:#1677ff;",
        "    ",
        "    class D,G,H,I terminal;",
        "    class E canBeApplied;",
        "```"
    ]
    
    return "\n".join(diagram)

def generate_report(df, analysis_periods, staff_list):
    """Generate full markdown report"""
    md = []
    
    # Get the primary analysis period (first one specified)
    primary_period = analysis_periods[0]
    start_date, end_date, label = parse_time_period(primary_period)
    human_readable_period = get_period_label(start_date, end_date)
    
    # Get workflow info
    workflow_info = get_jira_workflow_info()
    
    # Title and analysis period
    md.append("# Issue Application Summary Report\n")
    md.append(f"> **Analysis Period:** {human_readable_period}\n")
    
    # Add table of contents
    md.append("## Table of Contents\n")
    md.append("- [How to Read This Report](#how-to-read-this-report)")
    md.append("- [Overall Summary for Dataset](#overall-summary-for-dataset)")
    md.append("- [Summary by Analysis Period](#summary-by-analysis-period)")
    
    for period in analysis_periods:
        _, _, label = parse_time_period(period)
        anchor = f"breakdown-by-period-within-{label.lower()}"
        md.append(f"- [Breakdown by Period within {label}](#{anchor})")
    
    md.append("- [Issue Reporters](#issue-reporters)")
    
    # Add Issue Appliers section to TOC if data available
    if 'Applied User' in df.columns or 'Resolved to Applied User' in df.columns:
        md.append("- [Issue Appliers](#issue-appliers)")
    
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
    
    # Workflow Overview as subsection
    md.append("### Workflow Overview\n")
    md.append("The following diagram shows the status workflow for issues in the system:\n")
    md.append(generate_workflow_diagram())
    md.append("\n- **Green boxes** represent terminal statuses (final states)")
    md.append("- **Blue box** represents the status that can lead to 'Applied'")
    md.append("- **Deferred** can and should transition back to Triaged\n")
    
    md.append("### Categories\n")
    md.append("🆕 New issues are those created during the specified time period (based on created date).\n")
    md.append("")
    md.append("As soon as an issue is created, it begins in the **Submitted** state. From there, issues can be categorized by their current workflow state:\n")
    md.append("")
    md.append("| 🤔 Deciding | ⚙️ Doing | ✅ Done |")
    md.append("|-------------|----------|--------|")
    md.append("| *Issues in decision-making states:* | *Issues in implementation states:* | *Issues in terminal states:* |")
    md.append("| • Submitted | • Resolved - Change Required | • Published |")
    md.append("| • Triaged | • Applied | • Duplicate |")
    md.append("| • Waiting for Input | | • Resolved - No Change |")
    md.append("| • Deferred | | |")
    md.append("")
    
    md.append("### Tempo Metrics\n")
    md.append("")
    md.append("| Metric | Definition | Measurement | Statistics |")
    md.append("|--------|------------|-------------|------------|")
    md.append("| **🧩 Resolution Time** | Time from creation to first transition to any resolved state (i.e. Deferred, Resolved - Change Required, Published, Duplicate, Resolved - No Change, or Applied) | Created Date → First Resolved Date | Average, Median, P80 (80th percentile) |")
    md.append("| **🟢 Application Time** | Time from 'Resolved - Change Required' to 'Applied' | Resolved - Change Required → Applied | Average, Median |")
    md.append("")
    
    md.append("### Time Periods\n")
    md.append("Periods are defined as:")
    md.append("- **T1:** January, February, March, April")
    md.append("- **T2:** May, June, July, August")
    md.append("- **T3:** September, October, November, December\n")
    
    md.append("### Performance Bands\n")
    md.append("Performance bands are based on the P80 (80th percentile) of **Resolution Time** - the time from creation to first transition to any resolved state.\n")
    md.append("")
    md.append("| Band                  | P80 Range (days) | Interpretation                                                                             |")
    md.append("|-----------------------|------------------|--------------------------------------------------------------------------------------------|")
    md.append("| **🏎️ Presto**         | ≤ 60             | 80% of tickets reach a resolved state within two months. Very fast, high performance, hypercar speed.                                      |")
    md.append("| **🚴 Allegro**              | 61 – 180         | 80% reach a resolved state within six months. Fast, responsive, moving quickly.                    |")
    md.append("| **🚶 Andante**         | 181 – 365        | 80% reach a resolved state within a year. Moderate pace, moving steady, but with opportunities to accelerate.         |")
    md.append("| **🐢 Adagio** | > 365            | 20% of tickets take *more* than a year to reach a resolved state. Very slow. Let's look for bottlenecks or resource gaps.  |\n")
    md.append("_Note: For fun, these performance band labels are inspired by the music vocabulary for tempo. For more information, see the [Tempo article on Wikipedia](https://en.wikipedia.org/wiki/Tempo)._")

    # Overall summary
    total = len(df)
    resolved = df['is_resolved'].sum()
    backlog = df[df['backlog_at_{}_end'.format(analysis_periods[0])]].shape[0]  # Use refined backlog metric for the primary analysis period
    
    # Get earliest and latest dates in dataset
    earliest_date = df['Created Date'].min()
    latest_date = df['Created Date'].max()
    date_range = f"{earliest_date.strftime('%B %d, %Y')} to {latest_date.strftime('%B %d, %Y')}"  
    times_all = df.loc[df['is_resolved'], 'days_to_resolution']
    
    if not times_all.empty:
        ave_all = times_all.mean()
        med_all = times_all.median()
        p80_all = times_all.quantile(0.8)
        ave_str = format_number(ave_all, decimals=0)
        med_str = format_number(med_all, decimals=0)
        p80_str = format_number(p80_all, decimals=0)
        band = get_performance_band(p80_all)
    else:
        ave_str = med_str = p80_str = "N/A"
        band = "N/A"
    
    md.append("## Overall Summary for Dataset\n")
    md.append(f"This summary includes all issues in the dataset from **{date_range}**.\n")
    md.append(f"- **Total Issues:** {format_count(total)}")
    md.append(f"- **Applied Issues:** {format_count(resolved)}")
    md.append(f"- **Current Application Backlog:** {format_count(backlog)}")
    md.append(f"- **Ave Time to Application (days):** {ave_str}")
    md.append(f"- **Median Time to Application (days):** {med_str}")
    md.append(f"- **P80 Time to Application (days):** {p80_str}")
    md.append(f"- **Performance Band:** {band}")
    md.append("")
    
    # NEW: Status Distribution Section
    for period in analysis_periods:
        _, _, label = parse_time_period(period)
        status_data = analyze_status_distribution(df, period)
        
        if status_data is not None and not status_data.empty:
            md.append("### Status Distribution in Dataset\n")
            md.append("| Category | Status | Count | Percentage |")
            md.append("|----------|--------|-------|------------|")
            
            for _, row in status_data.iterrows():
                category = row['Category'] if pd.notnull(row['Category']) else "❓"
                status = row['Status'] if pd.notnull(row['Status']) else "Unknown"
                count = int(row['Count'])
                percentage = f"{row['Percentage']}%"
                md.append(f"| {category} | {status} | {format_count(count)} | {percentage} |")
            
            md.append("")
    
    # Summary by Analysis Period - Consolidated section
    md.append("## Summary by Analysis Period\n")
    
    for period in analysis_periods:
        _, _, label = parse_time_period(period)
        
        # Get all metrics for this period
        n, r, b, _, _, _ = get_period_metrics(df, period)
        
        # ALWAYS verify Applied count calculation - this is critical for accuracy
        start_date, end_date, _ = parse_time_period(period)
        applied_mask_debug = df['Applied Date'].notna() & (df['Applied Date'] >= start_date) & (df['Applied Date'] <= end_date)
        applied_count_debug = applied_mask_debug.sum()
        
        # ALWAYS print for debugging
        print(f"DEBUG Applied count for {label}: get_period_metrics={r}, direct_calc={applied_count_debug}")
        
        # Check for duplicates that might affect the count
        if 'Issue' in df.columns:
            duplicate_issues = df[df.duplicated(subset=['Issue'], keep=False)]
            if len(duplicate_issues) > 0:
                print(f"  WARNING: Found {len(duplicate_issues)} rows with duplicate Issue keys (should have been removed earlier)")
                dup_counts = duplicate_issues['Issue'].value_counts()
                print(f"  Duplicate issue keys: {dup_counts.head(10).to_dict()}")
                
                # Check if duplicates have Applied Date in this period
                dup_in_period = duplicate_issues[
                    duplicate_issues['Applied Date'].notna() & 
                    (duplicate_issues['Applied Date'] >= start_date) & 
                    (duplicate_issues['Applied Date'] <= end_date)
                ]
                if len(dup_in_period) > 0:
                    print(f"  WARNING: {len(dup_in_period)} duplicate rows have Applied Date in {label}")
                    print(f"  These duplicates may be causing incorrect counts")
        
        # Always use the direct calculation as it's more reliable
        # The direct calculation uses the actual mask on the dataframe, which respects duplicate removal
        if r != applied_count_debug:
            print(f"  WARNING: get_period_metrics returned {r} but direct calculation gives {applied_count_debug}. Using direct calculation.")
            r = applied_count_debug
        
        # Log investigation information for debugging (but don't change the count)
        # This helps identify discrepancies between script and QA without hardcoding corrections
        if 'Issue' in df.columns:
            applied_issues_df = df[applied_mask_debug].copy()
            unique_issues = applied_issues_df['Issue'].nunique()
            
            # If there's a discrepancy between count and unique issues, log it
            if r != unique_issues:
                print(f"  INFO: Applied count ({r}) differs from unique issues ({unique_issues}). Difference: {r - unique_issues}")
            
            # Log comparison with 'Resolved to Applied Date' for debugging
            resolved_to_applied_count = None
            if 'Resolved to Applied Date' in df.columns:
                resolved_to_applied_mask = df['Resolved to Applied Date'].notna() & \
                                         (df['Resolved to Applied Date'] >= start_date) & \
                                         (df['Resolved to Applied Date'] <= end_date)
                resolved_to_applied_count = resolved_to_applied_mask.sum()
                if resolved_to_applied_count != r:
                    print(f"  INFO: Count using 'Resolved to Applied Date' ({resolved_to_applied_count}) differs from 'Applied Date' count ({r}). Difference: {r - resolved_to_applied_count}")
            
            # Log detailed investigation when discrepancies are detected
            # Trigger investigation if there's a significant difference between Applied Date and Resolved to Applied Date counts
            should_investigate = False
            if resolved_to_applied_count is not None and abs(resolved_to_applied_count - r) > 0:
                should_investigate = True
            
            if should_investigate and r > 0:
                print(f"\n  🔍 INVESTIGATION: Investigating discrepancies for {label} (Applied count: {r})...")
                
                # Get all issues with Applied Date in the period
                period_year = start_date.year
                all_period_applied = df[df['Applied Date'].notna() & (df['Applied Date'].dt.year == period_year)].copy()
                print(f"    Total issues with Applied Date in year {period_year}: {len(all_period_applied)}")
                
                # Check for issues that might be outside the exact period range
                not_in_mask = all_period_applied[~applied_mask_debug[all_period_applied.index]]
                if len(not_in_mask) > 0:
                    print(f"    Issues in {period_year} but not in period mask: {len(not_in_mask)}")
                
                # Method 1: Check for issues exactly at boundaries
                at_start_boundary = (all_period_applied['Applied Date'] == start_date).sum()
                at_end_boundary = (all_period_applied['Applied Date'] == end_date).sum()
                print(f"    Issues exactly at start boundary: {at_start_boundary}")
                print(f"    Issues exactly at end boundary: {at_end_boundary}")
                
                # Method 2: Check for issues with null or missing Resolved to Applied Date
                if 'Resolved to Applied Date' in all_period_applied.columns:
                    no_valid_transition = all_period_applied[
                        all_period_applied['Resolved to Applied Date'].isna()
                    ]
                    print(f"    Issues with Applied Date but no 'Resolved to Applied Date': {len(no_valid_transition)}")
                    
                    if len(no_valid_transition) > 0:
                        print(f"    ⚠️  Found {len(no_valid_transition)} issues without valid transition")
                        if 'Issue' in no_valid_transition.columns:
                            sample_issues = no_valid_transition.head(10)[['Issue', 'Applied Date', 'Resolved to Applied Date', 'Status']]
                            print(f"    Sample issues without valid transition:")
                            for idx, row in sample_issues.iterrows():
                                print(f"      {row.get('Issue', 'N/A')}: Applied Date={row.get('Applied Date')}, Status={row.get('Status', 'N/A')}")
                
                # Method 3: Check for issues that might have been deduplicated differently
                all_period_applied_sorted = all_period_applied.sort_values('Applied Date')
                if len(all_period_applied_sorted) > r:
                    # Get the last few issues (by Applied Date) that might be causing discrepancies
                    discrepancy_count = abs(resolved_to_applied_count - r) if resolved_to_applied_count is not None else 0
                    tail_count = min(discrepancy_count if discrepancy_count > 0 else 6, len(all_period_applied_sorted) - r)
                    if tail_count > 0:
                        last_issues = all_period_applied_sorted.tail(tail_count)
                        print(f"\n    Last {tail_count} issues by Applied Date (may be causing discrepancies):")
                        if 'Issue' in last_issues.columns:
                            for idx, row in last_issues.iterrows():
                                issue_id = row.get('Issue', 'N/A')
                                applied_date = row.get('Applied Date')
                                status = row.get('Status', 'N/A')
                                resolved_to_applied = row.get('Resolved to Applied Date', 'N/A')
                                print(f"      {issue_id}: Applied Date={applied_date}, Status={status}, Resolved to Applied Date={resolved_to_applied}")
                
                # Method 4: Check for issues with timezone or precision issues
                very_close_to_start = all_period_applied[
                    (all_period_applied['Applied Date'] >= start_date) &
                    (all_period_applied['Applied Date'] < start_date + pd.Timedelta(hours=1))
                ]
                very_close_to_end = all_period_applied[
                    (all_period_applied['Applied Date'] <= end_date) &
                    (all_period_applied['Applied Date'] > end_date - pd.Timedelta(hours=1))
                ]
                print(f"    Issues very close to start (< 1 hour): {len(very_close_to_start)}")
                print(f"    Issues very close to end (< 1 hour): {len(very_close_to_end)}")
                
                # Method 5: Check date-only comparison
                if len(all_period_applied) > r:
                    start_date_only = start_date.date()
                    end_date_only = end_date.date()
                    applied_dates_only = all_period_applied['Applied Date'].dt.date
                    date_only_mask = (applied_dates_only >= start_date_only) & (applied_dates_only <= end_date_only)
                    date_only_count = date_only_mask.sum()
                    print(f"    Count using date-only comparison (ignoring time): {date_only_count}")
                    
                    if date_only_count != r:
                        excluded_by_time = all_period_applied[~date_only_mask]
                        print(f"    Issues excluded by time component: {len(excluded_by_time)}")
                        if 'Issue' in excluded_by_time.columns and len(excluded_by_time) <= 10:
                            print(f"    Issues excluded due to time component:")
                            for idx, row in excluded_by_time.iterrows():
                                issue_id = row.get('Issue', 'N/A')
                                applied_date = row.get('Applied Date')
                                print(f"      {issue_id}: Applied Date={applied_date} (time component may be outside range)")
        
        category_counts = count_by_category(df, period, workflow_info)
        tempo_metrics = calculate_tempo_metrics(df, period, workflow_info)
        res_metrics = tempo_metrics['resolution']
        app_metrics = tempo_metrics['application']
        
        # Table 1: Counts by Category
        md.append(f"### Issues by Category in {label}\n")
        md.append("| Period | 🆕 New | 🤔 Deciding (Backlog) | ⚙️ Doing | 🏷️ Applied | ✅ Done |")
        md.append("|--------|--------|----------------------|----------|-------------|---------|")
        md.append(f"| {label} | {format_count(category_counts['new'])} | {format_count(category_counts['deciding'])} | {format_count(category_counts['doing'])} | {format_count(r)} | {format_count(category_counts['done'])} |")
        md.append("")
        
        # Table 2: Resolution Time
        md.append(f"### 🧩 Time to Issue Resolution in {label}\n")
        md.append("Time from creation to first transition to any resolved state (Deferred, Resolved - Change Required, Published, Duplicate, Resolved - No Change, or Applied).\n")
        md.append("")
        if res_metrics['count'] > 0:
            md.append("| Period | Count | Ave (days) | Median (days) | P80 (days) | Performance |")
            md.append("|--------|-------|------------|---------------|------------|------------|")
            p80_val = res_metrics['p80']
            band = get_performance_band(p80_val) if p80_val is not None else "N/A"
            md.append(f"| {label} | {format_count(res_metrics['count'])} | {format_number(res_metrics['ave'], decimals=0)} | {format_number(res_metrics['median'], decimals=0)} | {format_number(res_metrics['p80'], decimals=0)} | {band} |")
        else:
            md.append("| Period | Count | Ave (days) | Median (days) | P80 (days) | Performance |")
            md.append("|--------|-------|------------|---------------|------------|------------|")
            md.append(f"| {label} | No data available | N/A | N/A | N/A | N/A |")
        md.append("")
        
        # Table 3: Application Time
        md.append(f"### 🟢 Time to (Resolved) Issue Being Applied in Specification in {label}\n")
        md.append("Time from 'Resolved - Change Required' to 'Applied'.\n")
        md.append("")
        
        # Get gap statistics for Min and Max
        gap_stats = analyze_resolution_to_application_gap(df, period)
        min_gap = gap_stats['min'] if gap_stats else None
        max_gap = gap_stats['max'] if gap_stats else None
        
        if app_metrics['count'] > 0:
            md.append("| Period | Count | Ave (days) | Median (days) | Min Gap (days) | Max Gap (days) |")
            md.append("|--------|-------|------------|---------------|----------------|----------------|")
            min_str = format_number(min_gap, decimals=0) if min_gap is not None else "N/A"
            max_str = format_number(max_gap, decimals=0) if max_gap is not None else "N/A"
            ave_str = format_number(app_metrics['ave'], decimals=0) if app_metrics['ave'] is not None else "N/A"
            med_str = format_number(app_metrics['median'], decimals=0) if app_metrics['median'] is not None else "N/A"
            md.append(f"| {label} | {format_count(app_metrics['count'])} | {ave_str} | {med_str} | {min_str} | {max_str} |")
            md.append("")
            md.append("> **Note:** This metric tracks issues transitioning into 'Applied' status during the period. Their final status during the period could be something else (i.e. 'Published').\n")
            md.append("")
            
            # Add note about issues without transition history
            without_history_count = count_applied_without_transition_history(df, period)
            if without_history_count > 0:
                md.append(f"> **Note:** {without_history_count} issue(s) were in Applied status during {label} but do not have a record of transition history from 'Resolved - Change Required' status. These issues are excluded from the timing calculations above.\n")
                md.append("")
            
            # Add warning if there are negative gaps
            if gap_stats and gap_stats.get('negative_count', 0) > 0:
                negative_ids = gap_stats.get('negative_issue_ids', [])
                if negative_ids:
                    # Format issue IDs - show first 10, then indicate if there are more
                    ids_display = ', '.join(str(id) for id in negative_ids[:10])
                    if len(negative_ids) > 10:
                        ids_display += f" (and {len(negative_ids) - 10} more)"
                    md.append(f"\n_Note: {gap_stats['negative_count']} issue(s) have negative gap values, indicating cases where issues were erroneously set to Applied (e.g., Triaged → Applied), then corrected (Applied → Resolved - Change Required → Applied). The corrected gap time (using the final Applied transition) is being used for calculations. Issue IDs: {ids_display}_\n")
                else:
                    md.append(f"\n_Note: {gap_stats['negative_count']} issue(s) have negative gap values, indicating cases where issues were erroneously set to Applied, then corrected. The corrected gap time (using the final Applied transition) is being used for calculations._\n")
        else:
            md.append("| Period | Count | Ave (days) | Median (days) | Min Gap (days) | Max Gap (days) |")
            md.append("|--------|-------|------------|---------------|----------------|----------------|")
            md.append(f"| {label} | No data available | N/A | N/A | N/A | N/A |")
            md.append("")
            md.append("> **Note:** This metric tracks issues transitioning into 'Applied' status during the period. Their final status during the period could be something else (i.e. 'Published').\n")
            md.append("")
            
            # Add note about issues without transition history (even if no data available)
            without_history_count = count_applied_without_transition_history(df, period)
            if without_history_count > 0:
                md.append(f"> **Note:** {without_history_count} issue(s) were in Applied status during {label} but do not have a record of transition history from 'Resolved - Change Required' status. These issues are excluded from the timing calculations above.\n")
        md.append("")
    
    # Breakdown by period within each period
    for period in analysis_periods:
        start_date, end_date, label = parse_time_period(period)
        human_readable_range = get_period_label(start_date, end_date)
        
        md.append(f"## Breakdown by Period within {label}\n")
        md.append(f"This breakdown covers **{human_readable_range}**.\n")
        
        # Table 1: Counts by Category
        md.append(f"### Issues by Category in {label}\n")
        md.append("| Period | 🆕 New | 🤔 Deciding (Backlog) | ⚙️ Doing | 🏷️ Applied | ✅ Done |")
        md.append("|--------|--------|----------------------|----------|-------------|---------|")
        
        tri_periods = find_periods_in_period(period)
        tri_data = []
        for tri in tri_periods:
            tri_start_date, tri_end_date, tri_label = parse_time_period(tri)
            
            # Get basic metrics
            _, n, r, b, ave, med, p80 = get_tri_metrics(df, tri)
            
            # Calculate Doing and Done counts for this tri period
            # Issues that exist at the end of the tri period
            exists_at_end = df['Created Date'] <= tri_end_date
            
            # Count by category at end of tri period
            doing_mask = exists_at_end & (df['Category'] == 'Doing')
            done_mask = exists_at_end & (df['Category'] == 'Done')
            doing_count = doing_mask.sum()
            done_count = done_mask.sum()
            
            tri_data.append((tri_label, n, r, b, ave, med, p80, doing_count, done_count))
            md.append(f"| {tri_label} | {format_count(n)} | {format_count(b)} | {format_count(doing_count)} | {format_count(r)} | {format_count(done_count)} |")
        
        md.append("")
        
        # Table 2: Resolution Time Data
        md.append(f"### 🧩 Time to Issue Resolution in {label}\n")
        md.append("Time from creation to first transition to any resolved state (Deferred, Resolved - Change Required, Published, Duplicate, Resolved - No Change, or Applied).\n")
        md.append("")
        md.append("| Period | Ave (days) | Median (days) | P80 (days) | Performance |")
        md.append("|--------|------------|---------------|------------|------------|")
        
        for tri_label, n, r, b, ave, med, p80, doing_count, done_count in tri_data:
            if ave is not None:
                ave_str = format_number(ave, decimals=0)
                med_str = format_number(med, decimals=0)
                p80_str = format_number(p80, decimals=0)
                band = get_performance_band(p80)
            else:
                ave_str = med_str = p80_str = "N/A"
                band = "N/A"
            
            md.append(f"| {tri_label} | {ave_str} | {med_str} | {p80_str} | {band} |")
        
        md.append("")
        
        # Table 3: Application Time Data
        md.append(f"### 🟢 Time to (Resolved) Issue Being Applied in Specification in {label}\n")
        md.append("| Period | Ave (days) | Median (days) |")
        md.append("|--------|------------|---------------|")
        
        total_without_history = 0
        for tri in tri_periods:
            tri_start_date, tri_end_date, tri_label = parse_time_period(tri)
            
            # Calculate application time for issues applied in this tri period
            applied_mask = df['Applied Date'].notna() & (df['Applied Date'] >= tri_start_date) & (df['Applied Date'] <= tri_end_date)
            applied_in_tri = applied_mask & df['days_from_resolution_to_application'].notna()
            application_times = df.loc[applied_in_tri, 'days_from_resolution_to_application']
            
            # Count issues without transition history for this tri period
            applied_without_history = applied_mask & df['days_from_resolution_to_application'].isna()
            total_without_history += applied_without_history.sum()
            
            if not application_times.empty:
                app_ave = application_times.mean()
                app_med = application_times.median()
                app_ave_str = format_number(app_ave, decimals=0)
                app_med_str = format_number(app_med, decimals=0)
            else:
                app_ave_str = app_med_str = "N/A"
            
            md.append(f"| {tri_label} | {app_ave_str} | {app_med_str} |")
        
        md.append("")
        md.append("> **Note:** This metric tracks issues transitioning into 'Applied' status during the period. Their final status during the period could be something else (i.e. 'Published').\n")
        md.append("")
        
        # Add note about issues without transition history for this period
        if total_without_history > 0:
            md.append(f"> **Note:** {total_without_history} issue(s) were in Applied status during {label} but do not have a record of transition history from 'Resolved - Change Required' status. These issues are excluded from the timing calculations above.\n")
        
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
        
        md.append(f"| {label} | {format_count(reporter_data['total_reporters_in_period'])} | {format_count(reporter_data['total_new_reporters'])} | {percent_new} |")
    
    md.append("")
    
    # Only add leaderboards for the primary analysis period
    primary_period = analysis_periods[0]
    _, _, label = parse_time_period(primary_period)
    reporter_data = analyze_submitters(df, primary_period, staff_list)
    
    # Get end date for the all-time title
    _, end_date, _ = parse_time_period(primary_period)
    end_date_str = end_date.strftime('%B %d, %Y')
    
    # Get start date for the all-time title (earliest date in dataset)
    earliest_date = df['Created Date'].min()
    start_date_str = earliest_date.strftime('%B %d, %Y')
    
    # Top reporters for this period
    md.append(f"### Top Reporters for {label}\n")
    md.append("| Rank | Reporter | Issue Count |")
    md.append("|------|----------|-------------|")
    
    for i, (_, row) in enumerate(reporter_data['top_period_reporters'].iterrows(), 1):
        reporter = row['Reporter'] if pd.notnull(row['Reporter']) else "Unknown"
        count = int(row['Issue Count'])
        md.append(f"| {i} | {reporter} | {format_count(count)} |")
    
    md.append("")
    
    # Top reporters of all time (through end of analysis period)
    md.append(f"### Top Reporters All Time ({start_date_str} Through {end_date_str})\n")
    md.append("| Rank | Reporter | Issue Count |")
    md.append("|------|----------|-------------|")
    
    for i, (_, row) in enumerate(reporter_data['top_all_time_reporters'].iterrows(), 1):
        reporter = row['Reporter'] if pd.notnull(row['Reporter']) else "Unknown"
        count = int(row['Issue Count'])
        md.append(f"| {i} | {reporter} | {format_count(count)} |")
    
    md.append("")
        
    # Issue Appliers Analysis (if data available)
    # Check for either Applied User or Resolved to Applied User
    has_applier_data = ('Applied User' in df.columns and df['Applied User'].notna().any()) or \
                       ('Resolved to Applied User' in df.columns and df['Resolved to Applied User'].notna().any())
    
    if has_applier_data:
        md.append("## Issue Appliers\n")
        md.append("Issue Appliers are identified as the person who made the transition from 'Resolved - Change Required' to 'Applied'.\n")
        
        # Issue Appliers summary table
        md.append("### Applier Summary\n")
        md.append("| Period | Total Appliers | New Appliers | % New Appliers |")
        md.append("|--------|----------------|--------------|----------------|")
        
        # For each analysis period
        for period in analysis_periods:
            _, _, label = parse_time_period(period)
            applier_data = analyze_appliers(df, period, staff_list)
            
            if applier_data is not None:
                # Calculate percentage with proper precision
                percent_new = f"{applier_data['new_applier_percent']:.1f}%"
                
                md.append(f"| {label} | {format_count(applier_data['total_appliers_in_period'])} | {format_count(applier_data['total_new_appliers'])} | {percent_new} |")
        
        md.append("")
        
        # Only add leaderboards for the primary analysis period
        primary_period = analysis_periods[0]
        _, _, label = parse_time_period(primary_period)
        applier_data = analyze_appliers(df, primary_period, staff_list)
        
        if applier_data is not None:
            # Get end date for the all-time title
            _, end_date, _ = parse_time_period(primary_period)
            end_date_str = end_date.strftime('%B %d, %Y')
            
            # Get start date for the all-time title (earliest Applied Date in dataset)
            applied_date_col = 'Resolved to Applied Date' if 'Resolved to Applied Date' in df.columns else 'Applied Date'
            if applied_date_col in df.columns:
                applied_dates = df[applied_date_col].dropna()
                if not applied_dates.empty:
                    earliest_applied_date = applied_dates.min()
                    start_date_str = earliest_applied_date.strftime('%B %d, %Y')
                else:
                    start_date_str = "Unknown"
            else:
                start_date_str = "Unknown"
            
            # Top appliers for this period
            if not applier_data['top_period_appliers'].empty:
                md.append(f"### Top Appliers for {label}\n")
                md.append("| Rank | Applier | Issues Applied |")
                md.append("|------|---------|----------------|")
                
                for i, (_, row) in enumerate(applier_data['top_period_appliers'].iterrows(), 1):
                    applier = row['Applier'] if pd.notnull(row['Applier']) else "Unknown"
                    count = int(row['Issue Count'])
                    md.append(f"| {i} | {applier} | {format_count(count)} |")
                
                md.append("")
            
            # Top appliers of all time (through end of analysis period)
            if not applier_data['top_all_time_appliers'].empty:
                md.append(f"### Top Appliers All Time ({start_date_str} Through {end_date_str})\n")
                md.append("| Rank | Applier | Issues Applied |")
                md.append("|------|---------|----------------|")
                
                for i, (_, row) in enumerate(applier_data['top_all_time_appliers'].iterrows(), 1):
                    applier = row['Applier'] if pd.notnull(row['Applier']) else "Unknown"
                    count = int(row['Issue Count'])
                    md.append(f"| {i} | {applier} | {format_count(count)} |")
                
                md.append("")
    
    # Add Issue Type Analysis if column exists
    if 'Issue Type' in df.columns:
        md.append("## Breakdown by Issue Type\n")
        
        # For each analysis period
        for period in analysis_periods:
            _, _, period_label = parse_time_period(period)
            start_date, end_date, label = parse_time_period(period)
            issue_type_data = analyze_issue_types(df, period)
            
            if issue_type_data is not None and not issue_type_data.empty:
                # Table 1: Issue Types by Category
                md.append(f"### Issue Types by Category in {period_label}\n")
                md.append("| Issue Type | 🆕 New | 🤔 Deciding | ⚙️ Doing | 🏷️ Applied | ✅ Done |")
                md.append("|------------|--------|-------------|----------|-------------|---------|")
                
                for _, row in issue_type_data.iterrows():
                    issue_type = row['Issue Type'] if pd.notnull(row['Issue Type']) else "Unknown"
                    new_count = int(row['New Count'])
                    backlog_count = int(row['Backlog Count']) if pd.notnull(row['Backlog Count']) else 0
                    applied_count = int(row['Applied Count']) if pd.notnull(row['Applied Count']) else 0
                    
                    # Get counts for Doing and Done categories by issue type
                    issue_type_mask = df['Issue Type'] == issue_type
                    exists_at_end = df['Created Date'] <= end_date
                    doing_mask = exists_at_end & issue_type_mask & (df['Category'] == 'Doing')
                    done_mask = exists_at_end & issue_type_mask & (df['Category'] == 'Done')
                    doing_count = doing_mask.sum()
                    done_count = done_mask.sum()
                    
                    md.append(f"| {issue_type} | {format_count(new_count)} | {format_count(backlog_count)} | {format_count(doing_count)} | {format_count(applied_count)} | {format_count(done_count)} |")
                
                md.append("")
                
                # Table 2: Issue Types Time to Issue Resolution
                md.append(f"### Issue Types Time to Issue Resolution in {period_label}\n")
                md.append("| Issue Type | Ave (days) | Median (days) | P80 (days) | Performance |")
                md.append("|------------|------------|---------------|------------|------------|")
                
                for _, row in issue_type_data.iterrows():
                    issue_type = row['Issue Type'] if pd.notnull(row['Issue Type']) else "Unknown"
                    avg_days = format_number(row['Avg Days'], decimals=0) if pd.notnull(row['Avg Days']) else "N/A"
                    median_days = format_number(row['Median Days'], decimals=0) if pd.notnull(row['Median Days']) else "N/A"
                    p80_days = format_number(row['P80 Days'], decimals=0) if pd.notnull(row['P80 Days']) else "N/A"
                    performance = row['Performance'] if pd.notnull(row['Performance']) else "N/A"
                    
                    md.append(f"| {issue_type} | {avg_days} | {median_days} | {p80_days} | {performance} |")
                
                md.append("")
    
    # Helper function for category breakdowns
    def render_breakdown(title, column):
        # Skip if column doesn't exist in DataFrame
        if column not in df.columns:
            print(f"Skipping '{title}' - column '{column}' not found in data")
            return
        
        md.append(f"## {title}\n")
        
        # Collect all data first
        rows_data = []
        
        # Special case for Specification Display Name - include Realm column
        if column == "Specification Display Name":
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
                        start_date, end_date, _ = parse_time_period(period)
                        
                        # Count new issues
                        new_count = spec_realm_df[f'created_in_{label}'].sum()
                        
                        # Count resolved issues
                        resolved_count = spec_realm_df[f'resolved_in_{label}'].sum()
                        
                        # Count backlog using refined definition
                        backlog_count = spec_realm_df[f'backlog_at_{label}_end'].sum()
                        
                        # Count Doing and Done categories at end of period
                        exists_at_end = spec_realm_df['Created Date'] <= end_date
                        doing_mask = exists_at_end & (spec_realm_df['Category'] == 'Doing')
                        done_mask = exists_at_end & (spec_realm_df['Category'] == 'Done')
                        doing_count = doing_mask.sum()
                        done_count = done_mask.sum()
                        
                        # Skip rows with no activity for this period (0 new, 0 resolved, 0 backlog, 0 doing, 0 done)
                        if new_count == 0 and resolved_count == 0 and backlog_count == 0 and doing_count == 0 and done_count == 0:
                            continue
                        
                        # Calculate resolution times
                        times = spec_realm_df.loc[spec_realm_df[f'resolved_in_{label}'], 'days_to_resolution']
                        
                        if not times.empty and len(times) > 0:
                            ave = times.mean()
                            med = times.median()
                            p80 = times.quantile(0.8)
                            ave_str = format_number(ave, decimals=0)
                            med_str = format_number(med, decimals=0)
                            p80_str = format_number(p80, decimals=0)
                            band = get_performance_band(p80)
                        else:
                            ave_str = med_str = p80_str = "N/A"
                            band = "N/A"
                        
                        # Calculate application times
                        applied_mask = spec_realm_df['Applied Date'].notna() & (spec_realm_df['Applied Date'] >= start_date) & (spec_realm_df['Applied Date'] <= end_date)
                        applied_in_period = applied_mask & spec_realm_df['days_from_resolution_to_application'].notna()
                        application_times = spec_realm_df.loc[applied_in_period, 'days_from_resolution_to_application']
                        
                        # Count issues without transition history
                        applied_without_history = applied_mask & spec_realm_df['days_from_resolution_to_application'].isna()
                        without_history_count = applied_without_history.sum()
                        
                        if not application_times.empty:
                            app_ave = application_times.mean()
                            app_med = application_times.median()
                            app_ave_str = format_number(app_ave, decimals=0)
                            app_med_str = format_number(app_med, decimals=0)
                        else:
                            app_ave_str = app_med_str = "N/A"
                        
                        realm_display = realm if pd.notnull(realm) else "Unknown"
                        rows_data.append({
                            'category': category,
                            'realm': realm_display,
                            'period': label,
                            'new': new_count,
                            'applied': resolved_count,
                            'backlog': backlog_count,
                            'doing': doing_count,
                            'done': done_count,
                            'res_ave': ave_str,
                            'res_med': med_str,
                            'res_p80': p80_str,
                            'res_perf': band,
                            'app_ave': app_ave_str,
                            'app_med': app_med_str,
                            'without_history': without_history_count
                        })
        else:
            # Original implementation for other columns
            # Get categories
            categories = sorted(df[column].dropna().unique())
            
            for category in categories:
                category_df = df[df[column] == category]
                
                for period in analysis_periods:
                    _, _, label = parse_time_period(period)
                    start_date, end_date, _ = parse_time_period(period)
                    
                    # Count new issues
                    new_count = category_df[f'created_in_{label}'].sum()
                    
                    # Count resolved issues
                    resolved_count = category_df[f'resolved_in_{label}'].sum()
                    
                    # Count backlog using refined definition
                    backlog_count = category_df[f'backlog_at_{label}_end'].sum()
                    
                    # Count Doing and Done categories at end of period
                    exists_at_end = category_df['Created Date'] <= end_date
                    doing_mask = exists_at_end & (category_df['Category'] == 'Doing')
                    done_mask = exists_at_end & (category_df['Category'] == 'Done')
                    doing_count = doing_mask.sum()
                    done_count = done_mask.sum()
                    
                    # Skip rows with no activity for this period (0 new, 0 resolved, 0 backlog, 0 doing, 0 done)
                    if new_count == 0 and resolved_count == 0 and backlog_count == 0 and doing_count == 0 and done_count == 0:
                        continue
                    
                    # Calculate resolution times
                    times = category_df.loc[category_df[f'resolved_in_{label}'], 'days_to_resolution']
                    
                    if not times.empty and len(times) > 0:
                        ave = times.mean()
                        med = times.median()
                        p80 = times.quantile(0.8)
                        ave_str = format_number(ave, decimals=0)
                        med_str = format_number(med, decimals=0)
                        p80_str = format_number(p80, decimals=0)
                        band = get_performance_band(p80)
                    else:
                        ave_str = med_str = p80_str = "N/A"
                        band = "N/A"
                    
                    # Calculate application times
                    applied_mask = category_df['Applied Date'].notna() & (category_df['Applied Date'] >= start_date) & (category_df['Applied Date'] <= end_date)
                    applied_in_period = applied_mask & category_df['days_from_resolution_to_application'].notna()
                    application_times = category_df.loc[applied_in_period, 'days_from_resolution_to_application']
                    
                    # Count issues without transition history
                    applied_without_history = applied_mask & category_df['days_from_resolution_to_application'].isna()
                    without_history_count = applied_without_history.sum()
                    
                    if not application_times.empty:
                        app_ave = application_times.mean()
                        app_med = application_times.median()
                        app_ave_str = format_number(app_ave, decimals=0)
                        app_med_str = format_number(app_med, decimals=0)
                    else:
                        app_ave_str = app_med_str = "N/A"
                    
                    rows_data.append({
                        'category': category,
                        'realm': None,
                        'period': label,
                        'new': new_count,
                        'applied': resolved_count,
                        'backlog': backlog_count,
                        'doing': doing_count,
                        'done': done_count,
                        'res_ave': ave_str,
                        'res_med': med_str,
                        'res_p80': p80_str,
                        'res_perf': band,
                        'app_ave': app_ave_str,
                        'app_med': app_med_str,
                        'without_history': without_history_count
                    })
        
        # Now output 3 separate tables
        if not rows_data:
            md.append("")
            return
        
        # Table 1: Counts by Category
        md.append("### Counts by Category\n")
        if column == "Specification Display Name":
            md.append(f"| {column} | Realm | Period | 🆕 New | 🤔 Deciding | ⚙️ Doing | 🏷️ Applied | ✅ Done |")
            md.append("|" + "-" * len(column) + "|-------|--------|--------|-------------|----------|----------|---------|")
            for row in rows_data:
                md.append(f"| {row['category']} | {row['realm']} | {row['period']} | {format_count(row['new'])} | {format_count(row['backlog'])} | {format_count(row['doing'])} | {format_count(row['applied'])} | {format_count(row['done'])} |")
        else:
            md.append(f"| {column} | Period | 🆕 New | 🤔 Deciding | ⚙️ Doing | 🏷️ Applied | ✅ Done |")
            md.append("|" + "-" * len(column) + "|--------|--------|-------------|----------|----------|---------|")
            for row in rows_data:
                md.append(f"| {row['category']} | {row['period']} | {format_count(row['new'])} | {format_count(row['backlog'])} | {format_count(row['doing'])} | {format_count(row['applied'])} | {format_count(row['done'])} |")
        
        md.append("")
        
        # Table 2: Resolution Time Data
        md.append("### 🧩 Time to Issue Resolution\n")
        if column == "Specification Display Name":
            md.append(f"| {column} | Realm | Period | Ave (days) | Median (days) | P80 (days) | Performance |")
            md.append("|" + "-" * len(column) + "|-------|--------|------------|---------------|------------|------------|")
            for row in rows_data:
                md.append(f"| {row['category']} | {row['realm']} | {row['period']} | {row['res_ave']} | {row['res_med']} | {row['res_p80']} | {row['res_perf']} |")
        else:
            md.append(f"| {column} | Period | Ave (days) | Median (days) | P80 (days) | Performance |")
            md.append("|" + "-" * len(column) + "|--------|------------|---------------|------------|------------|")
            for row in rows_data:
                md.append(f"| {row['category']} | {row['period']} | {row['res_ave']} | {row['res_med']} | {row['res_p80']} | {row['res_perf']} |")
        
        md.append("")
        
        # Table 3: Application Time Data
        md.append("### 🟢 Time to (Resolved) Issue Being Applied in Spec\n")
        md.append("> **Note:** This metric tracks issues transitioning into 'Applied' status during the period. Their final status during the period could be something else (i.e. 'Published').\n")
        md.append("")
        if column == "Specification Display Name":
            md.append(f"| {column} | Realm | Period | Ave (days) | Median (days) |")
            md.append("|" + "-" * len(column) + "|-------|--------|------------|---------------|")
            for row in rows_data:
                md.append(f"| {row['category']} | {row['realm']} | {row['period']} | {row['app_ave']} | {row['app_med']} |")
        else:
            md.append(f"| {column} | Period | Ave (days) | Median (days) |")
            md.append("|" + "-" * len(column) + "|--------|------------|---------------|")
            for row in rows_data:
                md.append(f"| {row['category']} | {row['period']} | {row['app_ave']} | {row['app_med']} |")
        
        # Add note about issues without transition history
        total_without_history = sum(row.get('without_history', 0) for row in rows_data)
        if total_without_history > 0:
            md.append(f"> **Note:** {total_without_history} issue(s) were in Applied status during the period but do not have a record of transition history from 'Resolved - Change Required' status. These issues are excluded from the timing calculations above.\n")
        
        md.append("")
    
    # Breakdowns by category
    render_breakdown("Breakdown by Realm", "Realm")
    
    # Breakdown by WG Name and Realm
    if 'WG Name' in df.columns and 'Realm' in df.columns:
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
            md.append(f"| {wg} | {realm} | {format_count(total)} | {pct}% |")
        
        md.append("")
    
    # Other breakdowns
    render_breakdown("Breakdown by WG Name", "WG Name")
    render_breakdown("Breakdown by Specification", "Specification Display Name")
    render_breakdown("Breakdown by Product Family", "Product Family")
    
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(
        description="Analyze issue application data and generate a markdown summary report focusing on when issues were marked as Applied."
    )
    parser.add_argument("-i", "--input", required=True, help="Input CSV file path")
    parser.add_argument("-o", "--output", required=True, help="Output Markdown file path")
    parser.add_argument("-p", "--periods", required=True, nargs="+", 
                    help="Analysis periods in format 'YYYY' (full year) or 'YYYYT[1-3]' (period)")
    parser.add_argument("-s", "--staff-config", default="data/config/hl7-staff.yaml",
                    help="Path to HL7 staff configuration file")
    parser.add_argument("--history-json-file",
                    help="Path to JSON file containing History data (if History was saved separately from CSV)")
    
    args = parser.parse_args()
    
    # Load staff configuration
    staff_config = load_staff_config(args.staff_config)
    staff_list = []
    if staff_config:
        print(f"Loaded {len(staff_config)} staff members from {args.staff_config}")
        # Extract staff display names (Reporter field)
        for staff in staff_config:
            if 'display_name' in staff:
                staff_list.append(staff['display_name'])
    elif os.path.exists(args.staff_config):
        print(f"Note: Staff config file exists but could not be loaded: {args.staff_config}")
    # If file doesn't exist, silently continue (staff filtering is optional)
    
    # Load data with proper quoting to handle JSON strings with special characters
    print(f"Loading data from {args.input}")
    # Try reading with explicit quoting parameters first (for files written by parse-jira-filter-export-csv-md.py)
    # If that fails, fall back to default reading
    try:
        df = pd.read_csv(
            args.input,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True
        )
    except (ValueError, csv.Error, Exception) as e:
        # Fall back to default reading for CSV files that weren't written with explicit quoting
        print(f"Note: Reading CSV with default parameters (explicit quoting failed: {e})")
        df = pd.read_csv(args.input)
    df.columns = df.columns.str.strip()
    
    # Handle column name variations
    if 'WG Name' not in df.columns and 'WG' in df.columns:
        df.rename(columns={'WG':'WG Name'}, inplace=True)
    if 'Specification Display Name' not in df.columns and 'Specification' in df.columns:
        df.rename(columns={'Specification':'Specification Display Name'}, inplace=True)
    
    # Verify that we have Applied Date
    if 'Applied Date' not in df.columns:
        print("WARNING: 'Applied Date' column not found in input file. This script is designed to analyze applied dates.")
        print("Please ensure you've used parse-jira-filter-export-csv-md.py with the --history option to extract applied dates.")
    
    # Expand all periods to include sub-periods (e.g., 2024 → 2024T1, T2, T3)
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

    # Check for and remove duplicate rows (by Issue key if available)
    if 'Issue' in df.columns:
        initial_count = len(df)
        # Keep first occurrence of each Issue
        df = df.drop_duplicates(subset=['Issue'], keep='first')
        duplicate_count = initial_count - len(df)
        if duplicate_count > 0:
            print(f"WARNING: Removed {duplicate_count} duplicate rows (by Issue key). Original count: {initial_count}, After deduplication: {len(df)}")
    else:
        # If no Issue column, check for complete duplicates
        initial_count = len(df)
        df = df.drop_duplicates(keep='first')
        duplicate_count = initial_count - len(df)
        if duplicate_count > 0:
            print(f"WARNING: Removed {duplicate_count} completely duplicate rows. Original count: {initial_count}, After deduplication: {len(df)}")

    # Process data
    print(f"Processing data for periods: {', '.join(expanded_periods)}")
    df = process_data(df, expanded_periods, history_json_file=args.history_json_file)
    
    if df is None:
        print("ERROR: Could not process data due to missing required columns. Exiting.")
        return
    
    # Generate report
    print("Generating report")
    report = generate_report(df, args.periods, staff_list)
    
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