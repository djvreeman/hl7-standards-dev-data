#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
# =============================================================================
# HL7 JIRA Issue Export and History Extractor
#
# Description:
# This script queries the HL7 JIRA API to export issue data using JQL-based filters.
# It supports export to CSV, Markdown, or both, and can enrich results with
# history-based fields (e.g., when a ticket was marked 'Applied', by whom).
#
# Key Features:
# - Export selected fields to structured CSV and/or Markdown tables
# - Pagination and retry handling for large result sets
# - Field mappings for readable output labels
# - Optional enrichment via JIRA changelog ("history") fields
# - Two-pass export mode for faster processing of large datasets
# - Caching of issue history to avoid redundant API calls
#
# Authentication:
# You must provide a valid HL7 JIRA Personal Access Token.
# This is typically configured in: `data/config/config.json` with a structure like:
#   {
#       "jira_bearer_token": "your_personal_token_here"
#   }
#
# History Extraction Format:
# Use the `--history` argument to define history field extraction logic. Format:
#   field.path:criteria1=value1&criteria2=value2:Display Name
# Example:
#   author.displayName:items.field=status&items.toString=Applied:Applied User
#   created:items.field=status&items.toString=Applied:Applied Date
#
# Common Field Mappings:
#   - key                            → Issue Key (clickable in Markdown)
#   - fields.customfield_10612      → Related URL (clickable)
#   - fields.customfield_10618      → Resolution
#   - fields.resolutiondate         → Resolution Date
#   - history_displayName           → User who changed status to Applied
#   - history_created               → Date issue was marked as Applied
#
# === Example Usages ===
# 1. Export to CSV and Markdown (default filenames):
#    python parse-jira-filter-export-csv-md.py -f '{"jql": "filter = 16107"}' -t 'your_token' -d 'key,fields.summary' -e both
#
# 2. Export to CSV only, with custom output filename:
#    python parse-jira-filter-export-csv-md.py -f '{"jql": "filter = 16107"}' -d 'key,fields.summary' -o issues -e csv
#
# 3. Include history fields (one-pass):
#    python parse-jira-filter-export-csv-md.py -f '{"jql": "filter = 16107"}' -d 'key,fields.summary' -e both \
#        --history 'author.displayName:items.field=status&items.toString=Applied:Applied User,created:items.field=status&items.toString=Applied:Applied Date'
#
# 4. Two-pass export for large datasets:
#    # First pass
#    python parse-jira-filter-export-csv-md.py -f '{"jql": "filter = 16107"}' -d 'key,fields.summary' -o issues -e csv --two-pass --cache
#    # Second pass
#    python parse-jira-filter-export-csv-md.py --second-pass-input issues.csv --output issues_with_history \
#        --history 'author.displayName:items.field=status&items.toString=Applied:Applied User' --cache --filter-resolved
#
# === Notes ===
# - If you specify --second-pass-input, the script skips JIRA query and loads from the given CSV.
# - History fields are only extracted if explicitly specified using --history.
# - Delimiter can be customized for CSV (default: comma).
# - All output files are saved with `.csv` and/or `.md` extensions.
#
# Dependencies:
# - requests
# - pandas
# - json
#
# Author:
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import csv
import requests
import json
import time
import random
import os
import sys
import pandas as pd
from datetime import datetime
from datetime import timezone

# Default base URL
DEFAULT_BASE_URL = "https://jira.hl7.org/rest/api/latest/search"
DEFAULT_OUTPUT_FILENAME = "output"
DEFAULT_CACHE_DIR = "data/working/cache"

# Load configuration from config.json
try:
    with open("data/config/config.json", "r") as config_file:
        config = json.load(config_file)
    BEARER_TOKEN = config["jira_bearer_token"]
except (FileNotFoundError, KeyError) as e:
    print(f"Error loading config: {e}")
    print("Please create data/config/config.json with your JIRA bearer token.")
    sys.exit(1)

# Output field mappings
field_mappings = {
    'key': 'Issue',
    'fields.summary': 'Summary',
    'fields.customfield_13704.value': 'Realm',
    'fields.customfield_10612': 'Related URL',
    'fields.customfield_10618': 'Resolution',
    'fields.creator.displayName': 'Creator',
    'fields.customfield_13714.displayName': 'Project Facilitator',
    'fields.customfield_13716.displayName': 'Publishing Facilitator',
    'fields.customfield_12316': 'Approval Date',
    'fields.customfield_11302': 'Specification',
    'fields.resolutiondate': 'Resolution Date',
    'fields.created': 'Created Date',
    'fields.customfield_11400': 'WG',
    'fields.reporter.displayName': 'Reporter',
    'fields.reporter.name': 'Reporter ID',
    'fields.issuetype.name': 'Issue Type',
    # History field mappings for common use cases
    'history_displayName': 'Applied User',  # For author.displayName when status changes to Applied
    'history_created': 'Applied Date',      # For created date when status changes to Applied
    # Placeholder fields for post-hoc processing
    'fields.family': 'Product Family',
    'fields.calculated_days_to_res': 'Days to Resolution', # Derived field to be calculated post-hoc
    'fields.spec_display_name': 'Specification Display Name' # Derived from https://github.com/HL7/JIRA-Spec-Artifacts/
    # Add more mappings as needed
}

# Define a function to safely parse resolution dates
def parse_resolution_date(date_str):
    try:
        if date_str:
            return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f%z')
        else:
            # Return a minimal datetime with UTC timezone for None or empty strings
            return datetime.min.replace(tzinfo=timezone.utc)
    except ValueError:
        # Return a very large date with UTC timezone for missing or malformed dates
        return datetime.max.replace(tzinfo=timezone.utc)

def fetch_with_retry(url, headers, params=None, max_retries=5, initial_delay=1):
    """Make a request with exponential backoff retry."""
    delay = initial_delay
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=headers, params=params, timeout=60)
            # Check if we got a rate limiting response
            if response.status_code == 429:  # Too Many Requests
                # Get retry-after header if available
                retry_after = int(response.headers.get('Retry-After', delay))
                print(f"Rate limited. Waiting {retry_after} seconds...")
                time.sleep(retry_after)
                continue
            
            # For 5xx errors, retry
            if 500 <= response.status_code < 600:
                print(f"Server error: {response.status_code}. Retrying...")
                time.sleep(delay)
                delay *= 2  # Exponential backoff
                continue
                
            return response
            
        except (requests.exceptions.RequestException, requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            print(f"Attempt {attempt+1} failed: {e}")
            if attempt < max_retries - 1:
                # Exponential backoff with jitter
                sleep_time = delay + random.uniform(0, 1)
                print(f"Retrying in {sleep_time:.2f} seconds...")
                time.sleep(sleep_time)
                delay *= 2  # Exponential backoff
            else:
                print("Max retries exceeded.")
                raise
    
    return None

def query_jira(base_url, query_params, bearer_token, fields):
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Accept': 'application/json'
    }

    all_results = []
    start_at = 0
    total_results = float('inf')  # Initialize to an arbitrary large number
    
    while start_at < total_results:
        query_params['startAt'] = start_at
        response = fetch_with_retry(base_url, headers, query_params)
        
        if response is None or response.status_code != 200:
            print(f"Error querying JIRA API: {response.status_code if response else 'No response'}")
            raise Exception(f"Error querying JIRA API")

        response_json = response.json()
        if not isinstance(response_json, dict):
            raise TypeError("Response JSON is not a dictionary.")

        issues = response_json.get('issues', [])
        if not isinstance(issues, list):
            raise TypeError("'issues' in response JSON is not a list.")

        all_results.extend(issues)  # Assuming 'issues' contains the results

        # Update total_results and start_at for next iteration
        total_results = response_json.get('total', 0)
        start_at += len(issues)
        
        # Print progress
        print(f"Fetched {len(all_results)}/{total_results} issues...")

    return all_results

def fetch_issue_history_with_cache(issue_key, bearer_token, cache_dir=DEFAULT_CACHE_DIR, cache_enabled=True, max_age_hours=24):
    """Fetch history data for a specific issue with caching."""
    # Create cache directory if it doesn't exist and caching is enabled
    if cache_enabled:
        os.makedirs(cache_dir, exist_ok=True)
        
        # Define cache file path
        cache_file = os.path.join(cache_dir, f"{issue_key}_history.json")
        
        # Check if we have a cached result
        if os.path.exists(cache_file):
            # Check if cache is recent
            cache_age_hours = (time.time() - os.path.getmtime(cache_file)) / 3600
            if cache_age_hours < max_age_hours:
                try:
                    with open(cache_file, 'r') as f:
                        return json.load(f)
                except (json.JSONDecodeError, IOError) as e:
                    print(f"Error reading cache for {issue_key}: {e}")
                    # Continue to fetch from API if cache is invalid
    
    # If not cached, cache disabled, or cache is old/invalid, fetch from API
    history_url = f"https://jira.hl7.org/rest/api/latest/issue/{issue_key}?expand=changelog"
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Accept': 'application/json'
    }
    
    try:
        response = fetch_with_retry(history_url, headers)
        if response and response.status_code == 200:
            histories = response.json().get('changelog', {}).get('histories', [])
            
            # Cache the result if caching is enabled
            if cache_enabled:
                try:
                    with open(cache_file, 'w') as f:
                        json.dump(histories, f)
                except IOError as e:
                    print(f"Error writing cache for {issue_key}: {e}")
            
            return histories
        else:
            print(f"Error fetching history for issue {issue_key}: {response.status_code if response else 'No response'}")
            return []
    except Exception as e:
        print(f"Exception fetching history for {issue_key}: {e}")
        return []

def fetch_issue_histories_in_batches(issue_keys, bearer_token, batch_size=50, cache_dir=DEFAULT_CACHE_DIR, cache_enabled=True):
    """Fetch history data for multiple issues in batches."""
    all_histories = {}
    total_issues = len(issue_keys)
    
    print(f"Fetching history for {total_issues} issues in batches of {batch_size}...")
    
    # First check cache for all issues
    if cache_enabled:
        cached_count = 0
        for issue_key in issue_keys:
            cache_file = os.path.join(cache_dir, f"{issue_key}_history.json")
            if os.path.exists(cache_file):
                try:
                    with open(cache_file, 'r') as f:
                        all_histories[issue_key] = json.load(f)
                        cached_count += 1
                except (json.JSONDecodeError, IOError):
                    # Will fetch this issue in the batch processing
                    pass
        
        if cached_count > 0:
            print(f"Loaded {cached_count} issues from cache")
    
    # Determine which issues still need to be fetched
    keys_to_fetch = [key for key in issue_keys if key not in all_histories]
    
    if not keys_to_fetch:
        print("All histories loaded from cache")
        return all_histories
    
    print(f"Fetching {len(keys_to_fetch)} remaining issues from API")
    
    # Process remaining issues in batches
    for i in range(0, len(keys_to_fetch), batch_size):
        batch = keys_to_fetch[i:i+batch_size]
        batch_end = min(i + batch_size, len(keys_to_fetch))
        print(f"Processing batch {i+1}-{batch_end} of {len(keys_to_fetch)} issues...")
        
        # Use JQL to fetch multiple issues with their changelogs in one request
        jql = f"key in ({','.join(batch)})"
        query_params = {
            'jql': jql,
            'fields': 'key',  # Minimize data by only requesting the key
            'expand': 'changelog',  # Include changelog (history)
            'maxResults': batch_size
        }
        
        url = DEFAULT_BASE_URL
        headers = {
            'Authorization': f'Bearer {bearer_token}',
            'Accept': 'application/json'
        }
        
        try:
            response = fetch_with_retry(url, headers, query_params)
            
            if response and response.status_code == 200:
                issues = response.json().get('issues', [])
                for issue in issues:
                    key = issue.get('key')
                    changelog = issue.get('changelog', {})
                    histories = changelog.get('histories', [])
                    all_histories[key] = histories
                    
                    # Cache the history if caching is enabled
                    if cache_enabled:
                        try:
                            cache_file = os.path.join(cache_dir, f"{key}_history.json")
                            with open(cache_file, 'w') as f:
                                json.dump(histories, f)
                        except IOError as e:
                            print(f"Error writing cache for {key}: {e}")
            else:
                print(f"Error fetching batch {i//batch_size + 1}: {response.status_code if response else 'No response'}")
                # Add delay to avoid overwhelming the server
                time.sleep(5)
        except Exception as e:
            print(f"Error in batch {i//batch_size + 1}: {e}")
            time.sleep(10)  # Longer delay on exception
    
    print(f"Successfully fetched history for {len(all_histories)} issues")
    return all_histories

def get_nested_value(dictionary, nested_keys):
    """Safely extract nested values from a dictionary."""
    if dictionary is None:
        return None
        
    for key in nested_keys.split('.'):
        # Check if the key exists and is not None
        if dictionary is not None and key in dictionary:
            dictionary = dictionary[key]
        else:
            # Return None or a default value if the key is not found
            return None
    return dictionary

def sanitize_for_csv(text):
    """Encapsulate fields in double quotes and escape internal quotes for CSV."""
    if isinstance(text, str):
        return '"' + text.replace('"', '""') + '"'
    return text

def sanitize_for_markdown(text):
    """Replace line feeds with spaces and escape special characters for Markdown compatibility."""
    if isinstance(text, str):
        # Replace line breaks with a space
        text = text.replace('\n', ' ').replace('\r', ' ')

        # Escape Markdown special characters
        replacements = {
            '|': '\\|',
            '\\': '\\\\',
            '*': '\\*',
            '_': '\\_',
            '`': '\\`',
            # Add more replacements if needed
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

    return text

def parse_history_field_specs(history_spec):
    """Parse history field specifications into field paths, criteria, and display names."""
    if not history_spec:
        return []
    
    field_specs = []
    for spec in history_spec.split(','):
        parts = spec.split(':', 2)  # Split into up to 3 parts (field_path, criteria, display_name)
        
        field_path = parts[0]
        criteria = {}
        display_name = None
        
        if len(parts) > 1:
            criteria_raw = parts[1]
            for crit in criteria_raw.split('&'):
                if '=' in crit:
                    crit_field, crit_value = crit.split('=', 1)
                    criteria[crit_field] = crit_value
        
        if len(parts) > 2:
            display_name = parts[2]
        
        field_specs.append((field_path, criteria, display_name))
    
    return field_specs

def extract_history_fields(histories, field_specs, debug_key=None):
    """Extract fields from history entries that match the criteria."""
    results = {}
    
    if debug_key:
        print(f"Extracting history fields for {debug_key} from {len(histories)} history entries")
    
    for field_path, criteria, display_name in field_specs:
        field_name = field_path.split('.')[-1]  # Use the last part of the path as field name
        
        # Create a field name for this history field
        history_field_name = f"history_{field_name}"
        
        # Store matching values for this field
        matching_values = []
        
        if debug_key:
            print(f"Looking for {field_path} where {criteria} in history")
        
        for history in histories:
            # Check if history entry matches criteria
            matches_criteria = True
            
            # Process criteria that apply to items array
            if any(k.startswith('items.') for k in criteria):
                item_criteria = {k.replace('items.', ''): v for k, v in criteria.items() if k.startswith('items.')}
                
                if item_criteria:
                    # Check if any item in items array matches criteria
                    item_matches = False
                    for item in history.get('items', []):
                        item_match = True
                        for ic_key, ic_value in item_criteria.items():
                            if item.get(ic_key) != ic_value:
                                item_match = False
                                break
                        if item_match:
                            item_matches = True
                            if debug_key:
                                print(f"Found matching item: {item}")
                            break
                    
                    matches_criteria = matches_criteria and item_matches
            
            # Process criteria that apply to the history entry itself
            direct_criteria = {k: v for k, v in criteria.items() if not k.startswith('items.')}
            for key, value in direct_criteria.items():
                if get_nested_value(history, key) != value:
                    matches_criteria = False
                    break
            
            # Extract field value if criteria match
            if matches_criteria:
                value = get_nested_value(history, field_path)
                if value is not None:
                    matching_values.append(value)
                    if debug_key:
                        print(f"Extracted value: {value}")
        
        # Store the first matching value (or None if no matches)
        results[history_field_name] = matching_values[0] if matching_values else None
        
        if debug_key:
            print(f"Final value for {history_field_name}: {results[history_field_name]}")
    
    return results

def should_fetch_history(item, filter_resolved=False):
    """Determine if we should fetch history for this issue."""
    if not filter_resolved:
        return True
        
    # Only fetch history for issues that have been resolved
    resolution_date = get_nested_value(item, 'fields.resolutiondate')
    return resolution_date is not None and resolution_date != ""

def process_history_data(data_to_export, field_specs, bearer_token, batch_size=50, cache_dir=DEFAULT_CACHE_DIR, 
                        cache_enabled=True, filter_resolved=False):
    """
    Process history data for the exported items in batches.
    
    Args:
        data_to_export: List of issue data from JIRA API
        field_specs: List of tuples (field_path, criteria, display_name)
        bearer_token: JIRA API bearer token
        batch_size: Number of issues to process in each batch
        cache_dir: Directory for caching history data
        cache_enabled: Whether to use caching
        filter_resolved: Only process issues that have resolution dates
        
    Returns:
        Updated data_to_export with history fields added
    """
    if not field_specs:
        return data_to_export
    
    # Filter issues if needed
    if filter_resolved:
        filtered_items = [item for item in data_to_export if 'Resolution Date' in item and item['Resolution Date']]
        print(f"Filtered {len(filtered_items)} resolved issues out of {len(data_to_export)} total issues")
    else:
        filtered_items = data_to_export
    
    # Get keys of issues to fetch history for
    issue_keys = [item.get('key') for item in filtered_items if item.get('key')]
    
    if not issue_keys:
        print("No issues to fetch history for")
        return data_to_export
    
    # Map field specs to display names for the output CSV
    for field_path, criteria, display_name in field_specs:
        field_name = field_path.split('.')[-1]
        history_field_name = f"history_{field_name}"
        
        if display_name:
            field_mappings[history_field_name] = display_name
    
    # Fetch histories in batches
    all_histories = fetch_issue_histories_in_batches(
        issue_keys, 
        bearer_token, 
        batch_size, 
        cache_dir, 
        cache_enabled
    )
    
    # Add history fields to each issue
    history_field_counts = {f"history_{spec[0].split('.')[-1]}": 0 for spec in field_specs}
    
    print(f"Processing history data for {len(data_to_export)} issues...")
    
    for i, item in enumerate(data_to_export):
        issue_key = item.get('key')
        if issue_key in all_histories:
            histories = all_histories[issue_key]
            # Extract history fields based on criteria
            history_fields = extract_history_fields(histories, field_specs, issue_key if issue_key == 'FHIR-31820' else None)
            # Add extracted fields to the item
            for field_name, value in history_fields.items():
                item[field_name] = value
                if value is not None:
                    history_field_counts[field_name] += 1
        
        # Print progress every 1000 issues
        if (i+1) % 1000 == 0 or i+1 == len(data_to_export):
            print(f"Processed history for {i+1}/{len(data_to_export)} issues...")
    
    # Print summary of fields found
    print("\nHistory fields extracted:")
    for field, count in history_field_counts.items():
        display_name = field_mappings.get(field, field)
        print(f"  {display_name}: {count} issues with data")
    
    # Sample of processed data with history fields
    print("\nSample of processed data with history fields:")
    sample_items = [item for item in data_to_export[:1000] if 'history_displayName' in item and item['history_displayName'] is not None][:5]
    
    if sample_items:
        for item in sample_items:
            print(f"Issue key: {item.get('key')}")
            print(f"  history_displayName: {item.get('history_displayName')}")
            print(f"  history_created: {item.get('history_created')}")
            original_fields = [f for f in item.keys() if not f.startswith('history_')][:5]
            print(f"  Sample original fields: {original_fields}")
            for field in original_fields:
                print(f"    {field}: {item.get(field)}")
    else:
        print("No items with history data found in sample")
    
    return data_to_export

def export_to_csv(data, fields, filename, field_mappings, chosen_delimiter, add_type):
    row_count = 0
    
    # Get all unique columns from the data
    all_columns = set()
    for item in data:
        all_columns.update(item.keys())
    
    # Identify history fields
    history_fields = {k for k in all_columns if k.startswith('history_')}
    
    print(f"Found {len(all_columns)} total columns and {len(history_fields)} history fields")
    
    # Create dataframe from data
    import pandas as pd
    df = pd.DataFrame(data)
    
    # Rename history columns using field_mappings
    rename_map = {}
    for key in history_fields:
        if key in field_mappings:
            rename_map[key] = field_mappings[key]
    
    if rename_map:
        df = df.rename(columns=rename_map)
        print(f"Renamed columns: {rename_map}")
    
    # Add type column if needed
    if add_type:
        df.insert(2, 'type', 'M')
    
    # Debug: check for specific issues with history data
    print("\nChecking for issues with history data:")
    sample_with_history = [item for item in data[:1000] if item.get('history_displayName') is not None][:5]
    if sample_with_history:
        print(f"Found {len(sample_with_history)} issues with history data in first 1000 issues")
        for item in sample_with_history:
            print(f"Issue {item.get('key')} has Applied User: {item.get('history_displayName')}, Applied Date: {item.get('history_created')}")
    else:
        print("No issues with history data found in first 1000 issues")
    
    # Look for specific issue
    fhir_issue = df[df['key'] == 'FHIR-31820']
    if not fhir_issue.empty:
        print(f"\nFHIR-31820 in DataFrame: {fhir_issue.iloc[0][['key', 'Applied User', 'Applied Date']].to_dict()}")
    else:
        print("\nFHIR-31820 not found in DataFrame")
    
    # Save to CSV
    print(f"Saving CSV with {len(df.columns)} columns: {list(df.columns)[:10]}...")
    df.to_csv(f"{filename}.csv", index=False, sep=chosen_delimiter)
    row_count = len(df)
    
    # Report on CSV
    print(f"CSV saved with {row_count} rows and {len(df.columns)} columns")
    
    # Check for history data in final CSV
    history_cols = [col for col in df.columns if 'Applied' in col]
    if history_cols:
        non_empty_history = df[history_cols].notna().sum()
        print(f"Non-empty history counts: {non_empty_history.to_dict()}")
        
        # Sample of rows with history data
        applied_rows = df[df[history_cols[0]].notna()]
        if not applied_rows.empty:
            print(f"\nFound {len(applied_rows)} rows with history data")
            print("Sample rows with history data:")
            sample_cols = ['key'] + history_cols
            print(applied_rows[sample_cols].head(5).to_string())
    
    return row_count

def export_to_markdown(data, fields, filename, field_mappings):
    row_count = 0
    
    # Add history fields if they exist in any of the items
    history_fields = set()
    for item in data:
        for key in item.keys():
            if key.startswith('history_'):
                history_fields.add(key)
    
    for history_field in history_fields:
        if history_field not in fields:
            fields.append(history_field)
    
    with open(f"{filename}.md", 'w', encoding='utf-8') as file:
        mapped_fields = [field_mappings.get(field, field) for field in fields]
        file.write('| ' + ' | '.join(mapped_fields) + ' |\n')
        file.write('|' + ' --- |' * len(mapped_fields) + '\n')
        for item in data:
            row_data = []
            for field in fields:
                value = get_nested_value(item, field)
                if field == 'key' and value:
                    # Format 'key' as a clickable JIRA link
                    value = f'[{value}](https://jira.hl7.org/browse/{value})'
                elif field == 'fields.customfield_10612' and value:
                    # Format 'fields.customfield_10612' as a clickable URL
                    value = f'[{value}]({value})'
                else:
                    value = sanitize_for_markdown(value)
                row_data.append(str(value) if value is not None else '')
            file.write('| ' + ' | '.join(row_data) + ' |\n')
            row_count += 1
    return row_count

def load_csv_to_dict(csv_file, field_mappings):
    """Load CSV file back into dictionary format compatible with the export functions."""
    # Read CSV
    df = pd.read_csv(csv_file)
    
    # Create reverse mapping for column names
    reverse_mapping = {v: k for k, v in field_mappings.items()}
    
    # Add debug info
    print(f"CSV columns: {list(df.columns)}")
    print(f"First few reverse mappings: {list(reverse_mapping.items())[:5]}")
    
    # Check original CSV for history columns
    print(f"\nOriginal CSV contains these columns: {list(df.columns)}")
    
    # Check if history columns already exist
    history_cols = [col for col in df.columns if 'Applied' in col]
    if history_cols:
        print(f"Original CSV already has history columns: {history_cols}")
        print(f"Non-empty values in these columns: {df[history_cols].notna().sum()}")
    
    # Convert DataFrame to list of dictionaries
    data = []
    for idx, row in df.iterrows():
        item = {}
        
        # Keep all original columns directly in the item dictionary
        for col in df.columns:
            item[col] = row[col]
        
        # Ensure 'key' field exists (important for history lookup)
        if 'Issue' in df.columns and 'key' not in item:
            item['key'] = row['Issue']
            
        data.append(item)
    
    # Check if key field is present
    if data and 'key' not in data[0]:
        print("WARNING: 'key' field not found in loaded data. This may cause issues.")
    else:
        print(f"Sample key: {data[0]['key']}")
        
    return data

def second_pass_processing(input_file, output_file, history_field_specs, bearer_token, export_format, 
                          delimiter, add_type, batch_size, cache_dir, cache_enabled, filter_resolved):
    """Process the second pass of a two-pass approach, adding history data to an existing CSV."""
    print(f"Loading data from {input_file}...")
    
    # Load CSV
    try:
        data = load_csv_to_dict(input_file, field_mappings)
        print(f"Loaded {len(data)} issues from CSV")
        
        # Debug: Check field names in the loaded data
        print("Sample field names in loaded data:")
        if data and len(data) > 0:
            print(list(data[0].keys())[:10])  # Print first 10 field names from first item
        
        # Process history data
        print("Processing history data...")
        data = process_history_data(
            data, 
            history_field_specs, 
            bearer_token, 
            batch_size, 
            cache_dir, 
            cache_enabled,
            filter_resolved
        )
        
        # Debug: Check if history fields were added
        if data and len(data) > 0:
            history_fields = [field for field in data[0].keys() if field.startswith('history_')]
            print(f"History fields found after processing: {history_fields}")
        
        # Debug: Examine a few specific issues (add some FHIR issue keys you know should have Applied status)
        debug_keys = ["FHIR-31820"]  # Add known issue keys here
        for item in data:
            if 'key' in item and item['key'] in debug_keys:
                print(f"\nDebug info for issue {item['key']}:")
                for field in item.keys():
                    if field.startswith('history_'):
                        print(f"  {field}: {item[field]}")
                        
                # Load history from cache to verify extraction
                cache_file = os.path.join(cache_dir, f"{item['key']}_history.json")
                if os.path.exists(cache_file):
                    with open(cache_file, 'r') as f:
                        histories = json.load(f)
                        applied_entries = [h for h in histories if any(
                            i.get('field') == 'status' and i.get('toString') == 'Applied' 
                            for i in h.get('items', []))]
                        if applied_entries:
                            print(f"  Found {len(applied_entries)} entries with 'Applied' status in history:")
                            for entry in applied_entries:
                                print(f"    Author: {entry.get('author', {}).get('displayName')}")
                                print(f"    Created: {entry.get('created')}")
        
        # Export data
        if export_format in ['csv', 'both']:
            # Debug: Print all available fields before export
            all_fields = list(field_mappings.keys())
            print(f"\nExporting with {len(all_fields)} fields")
            print(f"First 10 fields: {all_fields[:10]}")
            
            # Debug: Check history field mappings
            history_mappings = {k: v for k, v in field_mappings.items() if k.startswith('history_')}
            print(f"History field mappings: {history_mappings}")
            
            fields = list(field_mappings.keys())  # Use all available fields
            csv_row_count = export_to_csv(data, fields, output_file, field_mappings, delimiter, add_type)
            print(f"Data exported to CSV successfully with {csv_row_count} rows in file: {output_file}.csv")

            # Debug: Check first few rows of exported CSV
            try:
                import pandas as pd
                df = pd.read_csv(f"{output_file}.csv")
                print("\nFirst row of exported CSV:")
                if not df.empty:
                    print(df.iloc[0])
                    history_cols = [col for col in df.columns if 'Applied' in col]
                    print(f"History columns in CSV: {history_cols}")
                    non_empty_count = df[history_cols].notna().sum().sum()
                    print(f"Non-empty history field count: {non_empty_count}")
            except Exception as e:
                print(f"Error checking exported CSV: {e}")

        if export_format in ['markdown', 'both']:
            fields = list(field_mappings.keys())  # Use all available fields
            md_row_count = export_to_markdown(data, fields, output_file, field_mappings)
            print(f"Data exported to Markdown successfully with {md_row_count} rows in file: {output_file}.md")
            
        return True
    except Exception as e:
        print(f"Error in second pass processing: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query JIRA API and export specified fields to CSV and Markdown.")
    parser.add_argument("-u", "--url", help="Base URL for the JIRA API", default=DEFAULT_BASE_URL)
    parser.add_argument("-f", "--filters", help="Query parameters in JSON format")
    parser.add_argument("-d", "--fields", help="Comma-separated data fields to export")
    parser.add_argument("-o", "--output", help="Output file name (without extension)", default=DEFAULT_OUTPUT_FILENAME)
    parser.add_argument('-del', '--delimiter', type=str, default=',', help='Delimiter to use in the CSV file (default: comma)')
    parser.add_argument("-e", "--export-format", 
                    help="Specify the export format: 'csv', 'markdown', or 'both'", 
                    choices=['csv', 'markdown', 'both'], 
                    default='both')
    parser.add_argument('--add-type', action='store_true', help='Include a "type" field with each row set to "M"')
    parser.add_argument("--history", "--hist", 
                   help="Comma-separated history fields to extract (format: field1.subfield1:criteria_field=criteria_value:display_name)", 
                   default="")
    parser.add_argument("--batch-size", type=int, default=50,
                   help="Number of issues to fetch in each batch for history data (default: 50)")
    parser.add_argument("--cache", action="store_true",
                   help="Enable caching of JIRA API responses")
    parser.add_argument("--cache-dir", default=DEFAULT_CACHE_DIR,
                   help=f"Directory to store cache files (default: {DEFAULT_CACHE_DIR})")
    parser.add_argument("--two-pass", action="store_true",
                   help="Run in two-pass mode: first fetch issues, then add history")
    parser.add_argument("--second-pass-input", 
                   help="Input CSV file for second pass of a two-pass process")
    parser.add_argument("--filter-resolved", action="store_true",
                   help="Only process history for issues with resolution dates")
    parser.add_argument("--max-retries", type=int, default=5,
                   help="Maximum number of retry attempts for API calls (default: 5)")

    args = parser.parse_args()
    
# Validate arguments
    if args.second_pass_input:
        # Second pass mode - don't need filters or fields
        if not args.history:
            parser.error("--history is required with --second-pass-input")
        if not args.output:
            parser.error("--output is required with --second-pass-input")
    else:
        # Normal mode - need filters and fields
        if not args.filters:
            parser.error("--filters is required unless using --second-pass-input")
        if not args.fields:
            parser.error("--fields is required unless using --second-pass-input")

    chosen_delimiter = args.delimiter

    try:
        # Parse history field specifications if provided
        history_field_specs = parse_history_field_specs(args.history)
        
        # Second pass mode
        if args.second_pass_input:
            print("Running in second pass mode...")
            success = second_pass_processing(
                args.second_pass_input,
                args.output,
                history_field_specs,
                BEARER_TOKEN,
                args.export_format,
                args.delimiter,
                args.add_type,
                args.batch_size,
                args.cache_dir,
                args.cache,
                args.filter_resolved
            )
            if not success:
                sys.exit(1)
        else:
            # First pass or normal mode
            query_params = json.loads(args.filters)
            fields = args.fields.split(',')

            # First pass in two-pass mode
            if args.two_pass and history_field_specs:
                print("Running in two-pass mode (first pass)...")
                
                # First pass: Fetch issues without history
                print("Fetching issue data from JIRA...")
                data_to_export = query_jira(args.url, query_params, BEARER_TOKEN, fields)
                print(f"Successfully fetched {len(data_to_export)} issues")
                
                # Sort data if needed
                if data_to_export and 'fields' in data_to_export[0] and 'resolutiondate' in data_to_export[0]['fields']:
                    data_to_export.sort(key=lambda x: parse_resolution_date(x.get('fields', {}).get('resolutiondate', '9999-12-31T23:59:59.000+0000')))
                
                # Export data to CSV for second pass
                print(f"Exporting first pass data to CSV: {args.output}.csv")
                csv_row_count = export_to_csv(data_to_export, fields, args.output, field_mappings, args.delimiter, args.add_type)
                print(f"First pass data exported to CSV with {csv_row_count} rows")
                
                # Ask if user wants to continue to second pass
                print("\nFirst pass complete. Run the second pass with:")
                print(f"python3 {sys.argv[0]} --second-pass-input {args.output}.csv --output {args.output}_with_history --history '{args.history}' --cache --filter-resolved")
            else:
                # Normal mode: Fetch issues and history in one pass
                print("Running in normal mode...")
                
                # Fetch issues
                print("Fetching issue data from JIRA...")
                data_to_export = query_jira(args.url, query_params, BEARER_TOKEN, fields)
                print(f"Successfully fetched {len(data_to_export)} issues")
                
                # Process history data if requested
                if history_field_specs:
                    print("Processing history data...")
                    data_to_export = process_history_data(
                        data_to_export, 
                        history_field_specs, 
                        BEARER_TOKEN,
                        args.batch_size,
                        args.cache_dir,
                        args.cache,
                        args.filter_resolved
                    )

                # Sort data if needed
                if data_to_export and 'fields' in data_to_export[0] and 'resolutiondate' in data_to_export[0]['fields']:
                    data_to_export.sort(key=lambda x: parse_resolution_date(x.get('fields', {}).get('resolutiondate', '9999-12-31T23:59:59.000+0000')))

                # Export data
                if args.export_format in ['csv', 'both']:
                    print(f"Exporting data to CSV: {args.output}.csv")
                    csv_row_count = export_to_csv(data_to_export, fields, args.output, field_mappings, args.delimiter, args.add_type)
                    print(f"Data exported to CSV successfully with {csv_row_count} rows")

                if args.export_format in ['markdown', 'both']:
                    print(f"Exporting data to Markdown: {args.output}.md")
                    md_row_count = export_to_markdown(data_to_export, fields, args.output, field_mappings)
                    print(f"Data exported to Markdown successfully with {md_row_count} rows")

    except Exception as e:
        print(f"An error occurred: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)