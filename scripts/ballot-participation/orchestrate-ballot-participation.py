#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
# =============================================================================
# HL7 Ballot Participation Data Orchestrator
#
# Description:
# This script orchestrates the collection of HL7 ballot participation data:
# 1. Fetches all BALDEF (Ballot Definition) issues using filter 23875
# 2. For each BALDEF, fetches all linked BALLOT (Ballot Submission) issues
# 3. Extracts key data from both BALDEF and BALLOT issues
# 4. Exports two CSV files:
#    - baldef_data.csv: BALDEF information
#    - ballot_participation.csv: BALLOT participation data with BALDEF linkage
#
# Usage:
#   # Full process (fetch BALDEF from API, then fetch ballots)
#   python3 orchestrate-ballot-participation.py
#
#   # Only create BALDEF CSV from API (skip ballot participation phase)
#   python3 orchestrate-ballot-participation.py --phase1-only
#
#   # Use existing BALDEF CSV and fetch ballots (skip BALDEF API query)
#   python3 orchestrate-ballot-participation.py --baldef-csv data/working/ballot-participation/baldef_data.csv
#
#   # Create files without timestamps (may overwrite existing files)
#   python3 orchestrate-ballot-participation.py --no-timestamp
#
#   # Force overwrite existing files
#   python3 orchestrate-ballot-participation.py --no-timestamp --force
#
#   # Custom output directory with timestamps
#   python3 orchestrate-ballot-participation.py --phase1-only --output-dir custom/path
#
# Command-Line Arguments:
#   --baldef-csv PATH      Use existing BALDEF CSV file (skips API query for BALDEF data)
#                          Cannot be used with --phase1-only
#
#   --phase1-only          Only run phase 1: fetch BALDEF from API and create CSV, then stop
#                          Cannot be used with --baldef-csv
#
#   --output-dir PATH      Output directory for CSV files
#                          Default: data/working/ballot-participation
#
#   --no-timestamp         Do not add timestamp to filenames (may overwrite existing files)
#                          By default, timestamps are added to prevent overwriting
#
#   --force                Allow overwriting existing files without prompt
#                          Use with caution
#
# Output:
#   By default, files are created with timestamps to prevent overwriting:
#   - data/working/ballot-participation/baldef_data-YYYYMMDD-HHMMSS.csv
#   - data/working/ballot-participation/ballot_participation-YYYYMMDD-HHMMSS.csv
#
#   If --no-timestamp is used, files are created without timestamps:
#   - data/working/ballot-participation/baldef_data.csv
#   - data/working/ballot-participation/ballot_participation.csv
#
# Safeguards:
#   - Timestamps are added to filenames by default to prevent accidental overwrites
#   - Script checks for existing files and exits with error if found (unless --force is used)
#   - Use --force flag to explicitly allow overwriting existing files
#   - Use --output-dir to write files to different locations for different runs
#
# Dependencies:
#   - Uses functions from parse-jira-filter-export-csv-md.py
#   - Requires data/config/config.json with jira_bearer_token
#
# Author:
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import sys
import os
import json
import csv
import time
import argparse
import importlib.util
from datetime import datetime
import pandas as pd

# Determine project root (script is in scripts/ballot-participation/ directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)  # scripts/ directory
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)  # project root

# Change to project root directory so config paths work correctly
os.chdir(PROJECT_ROOT)

# Add scripts directory to path to import from parse-jira-filter-export-csv-md.py
sys.path.insert(0, SCRIPTS_DIR)

# Import functions from parse-jira-filter-export-csv-md.py
# Use importlib to handle the hyphenated filename
spec = importlib.util.spec_from_file_location(
    "parse_jira_filter_export_csv_md",
    os.path.join(SCRIPTS_DIR, "parse-jira-filter-export-csv-md.py")
)
parse_jira_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(parse_jira_module)

# Import needed functions and constants
query_jira = parse_jira_module.query_jira
fetch_with_retry = parse_jira_module.fetch_with_retry
get_nested_value = parse_jira_module.get_nested_value
DEFAULT_BASE_URL = parse_jira_module.DEFAULT_BASE_URL
BEARER_TOKEN = parse_jira_module.BEARER_TOKEN

# Default output directory (relative to project root)
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "data/working/ballot-participation")

# BALDEF field mappings based on JSON structure and UI
BALDEF_FIELD_MAPPINGS = {
    'key': 'BALDEF ID',
    'fields.summary': 'Summary',
    'fields.customfield_11302': 'Specification',  # Array of specifications
    'fields.customfield_10900': 'Ballot Open Date',
    'fields.customfield_10901': 'Ballot Close Date',
    'fields.customfield_11704': 'Ballot Period',  # e.g., "2025-Sep"
    'fields.customfield_11604': 'Ballot Type',  # e.g., "STU"
    'fields.customfield_11610': 'Ballot Status',  # e.g., "Passing (so far)"
    'fields.customfield_11706': 'Specification URL',
    'fields.customfield_12105': 'Product Family',  # e.g., ["FHIR"]
    'fields.customfield_11806': 'Voting Summary',  # Table with voting breakdown
    'fields.creator.displayName': 'Creator',
    'fields.created': 'Created Date',
    'fields.status.name': 'Status',
    'fields.customfield_14904': 'Related Issues',  # HTML links
}

# BALLOT field mappings
BALLOT_FIELD_MAPPINGS = {
    'BALDEF_ID': 'BALDEF ID',
    'BALLOT_ID': 'BALLOT ID',
    'BALLOTER_KEY': 'Balloter Key',
    'BALLOTER_NAME': 'Balloter Name',
    'ORGANIZATION': 'Organization',
    'ORG_CATEGORY': 'Org Category',
    'VOTE': 'Vote',
}

def get_nested_value_safe(dictionary, nested_keys, default=None):
    """Safely extract nested values from a dictionary."""
    if dictionary is None:
        return default
        
    keys = nested_keys.split('.')
    current = dictionary
    
    for key in keys:
        if isinstance(current, dict) and key in current:
            current = current[key]
        elif isinstance(current, list) and len(current) > 0:
            # Handle list values - return first element or join
            if len(current) == 1:
                current = current[0]
            else:
                # For lists, return as comma-separated string
                return ', '.join(str(v) for v in current)
        else:
            return default
    
    # Handle dict values that might have nested structure (like customfield options)
    if isinstance(current, dict):
        # Check if it's a customfield option dict with 'value' key
        if 'value' in current:
            return current['value']
        # Otherwise return the dict as string representation
        return str(current)
    
    return current if current is not None else default

def process_baldef_data(raw_baldef_data):
    """Process raw BALDEF data from JIRA API into structured format."""
    processed_data = []
    
    for item in raw_baldef_data:
        processed_item = {}
        
        # Extract each field using mappings
        for field_path, display_name in BALDEF_FIELD_MAPPINGS.items():
            if field_path == 'key':
                value = item.get('key')
            else:
                value = get_nested_value_safe(item, field_path)
            
            # Handle special cases
            if field_path == 'fields.customfield_11302' and isinstance(value, list):
                # Specification field is an array
                value = ', '.join(str(v) for v in value) if value else ''
            elif field_path == 'fields.customfield_12105' and isinstance(value, list):
                # Product Family is an array
                value = ', '.join(str(v) for v in value) if value else ''
            elif field_path == 'fields.customfield_11610' and isinstance(value, dict):
                # Ballot Status is a dict with 'value'
                value = value.get('value', '') if value else ''
            elif field_path == 'fields.customfield_11704' and isinstance(value, dict):
                # Ballot Period is a dict with 'value', may have 'child' with additional info
                period_value = value.get('value', '') if value else ''
                child = value.get('child', {})
                if child and isinstance(child, dict):
                    child_value = child.get('value', '')
                    if child_value:
                        period_value = f"{period_value} - {child_value}"
                value = period_value
            elif field_path == 'fields.customfield_11604' and isinstance(value, dict):
                # Ballot Type is a dict with 'value'
                value = value.get('value', '') if value else ''
            
            processed_item[display_name] = value
        
        processed_data.append(processed_item)
    
    return processed_data

def fetch_linked_ballot_issues(baldef_key, bearer_token):
    """Fetch all linked BALLOT issues for a given BALDEF."""
    jql = f'issue in linkedIssues("{baldef_key}")'
    query_params = {
        'jql': jql,
        'fields': 'key,summary,creator,reporter,customfield_10601,customfield_11805,customfield_10519',
        'maxResults': 1000  # Adjust if needed
    }
    
    all_ballots = []
    start_at = 0
    total_results = float('inf')
    
    while start_at < total_results:
        query_params['startAt'] = start_at
        response = fetch_with_retry(DEFAULT_BASE_URL, {'Authorization': f'Bearer {bearer_token}', 'Accept': 'application/json'}, query_params)
        
        if response is None or response.status_code != 200:
            print(f"Error fetching linked ballots for {baldef_key}: {response.status_code if response else 'No response'}")
            break
        
        response_json = response.json()
        issues = response_json.get('issues', [])
        all_ballots.extend(issues)
        
        total_results = response_json.get('total', 0)
        start_at += len(issues)
        
        if len(issues) == 0:
            break
    
    return all_ballots

def process_ballot_data(ballot_issues, baldef_key):
    """Process raw BALLOT data into structured format."""
    processed_data = []
    
    for ballot in ballot_issues:
        fields = ballot.get('fields', {})
        
        # Extract balloter info (prefer reporter, fallback to creator)
        reporter = fields.get('reporter', {})
        creator = fields.get('creator', {})
        
        balloter_key = reporter.get('name') if reporter else creator.get('name', '')
        balloter_name = reporter.get('displayName') if reporter else creator.get('displayName', '')
        
        # Extract organization
        organization = get_nested_value_safe(fields, 'customfield_10601', '')
        
        # Extract org category (customfield_11805 is a dict with 'value')
        org_category_obj = fields.get('customfield_11805')
        org_category = org_category_obj.get('value', '') if isinstance(org_category_obj, dict) else ''
        
        # Extract vote (customfield_10519 is a dict with 'value')
        vote_obj = fields.get('customfield_10519')
        vote = vote_obj.get('value', '') if isinstance(vote_obj, dict) else ''
        
        processed_item = {
            'BALDEF_ID': baldef_key,
            'BALLOT_ID': ballot.get('key', ''),
            'BALLOTER_KEY': balloter_key,
            'BALLOTER_NAME': balloter_name,
            'ORGANIZATION': organization,
            'ORG_CATEGORY': org_category,
            'VOTE': vote,
        }
        
        processed_data.append(processed_item)
    
    return processed_data

def load_baldef_from_csv(csv_file):
    """Load BALDEF data from an existing CSV file."""
    print(f"Loading BALDEF data from {csv_file}...")
    
    try:
        df = pd.read_csv(
            csv_file,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True
        )
    except Exception as e:
        print(f"Warning: Could not read CSV with explicit quoting parameters: {e}")
        print("Falling back to default CSV reading...")
        df = pd.read_csv(csv_file)
    
    # Convert DataFrame to list of dictionaries
    # The CSV columns are display names, so we keep them as-is
    data = []
    for idx, row in df.iterrows():
        item = {}
        for col in df.columns:
            # Handle NaN values
            value = row[col]
            if pd.isna(value):
                item[col] = ''
            else:
                item[col] = value
        data.append(item)
    
    print(f"Loaded {len(data)} BALDEF records from CSV")
    return data

def export_to_csv(data, filename, field_mappings):
    """Export data to CSV file."""
    if not data:
        print(f"No data to export to {filename}")
        return 0
    
    # Create output directory if it doesn't exist
    os.makedirs(os.path.dirname(filename), exist_ok=True)
    
    # Get all column names from field mappings (display names)
    columns = list(field_mappings.values())
    
    # Create reverse mapping: display_name -> internal_key
    reverse_mapping = {v: k for k, v in field_mappings.items()}
    
    # Write CSV
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=columns, extrasaction='ignore')
        writer.writeheader()
        
        for row in data:
            # Map internal keys to display names for CSV
            mapped_row = {}
            for display_name in columns:
                internal_key = reverse_mapping.get(display_name)
                if internal_key and internal_key in row:
                    mapped_row[display_name] = row[internal_key]
                else:
                    # Try direct match in case keys already match display names
                    if display_name in row:
                        mapped_row[display_name] = row[display_name]
            writer.writerow(mapped_row)
    
    print(f"Exported {len(data)} rows to {filename}")
    return len(data)

def main():
    """Main orchestrator function."""
    parser = argparse.ArgumentParser(
        description="HL7 Ballot Participation Data Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run full process (fetch BALDEF from API, then fetch ballots)
  # Files will have timestamps: baldef_data-20260115-143022.csv
  python3 orchestrate-ballot-participation.py

  # Only create BALDEF CSV from API (skip ballot participation phase)
  python3 orchestrate-ballot-participation.py --phase1-only

  # Use existing BALDEF CSV and fetch ballots (skip BALDEF API query)
  python3 orchestrate-ballot-participation.py --baldef-csv data/working/ballot-participation/baldef_data.csv

  # Create files without timestamps (may overwrite existing files)
  python3 orchestrate-ballot-participation.py --no-timestamp

  # Force overwrite existing files
  python3 orchestrate-ballot-participation.py --no-timestamp --force

  # Custom output directory with timestamps
  python3 orchestrate-ballot-participation.py --phase1-only --output-dir custom/path
        """
    )
    parser.add_argument(
        '--baldef-csv',
        help='Path to existing BALDEF CSV file (skips API query for BALDEF data). Cannot be used with --phase1-only.'
    )
    parser.add_argument(
        '--phase1-only',
        '--baldef-only',
        action='store_true',
        help='Only run phase 1: fetch BALDEF from API and create CSV, then stop (skip ballot participation phase). Cannot be used with --baldef-csv.'
    )
    parser.add_argument(
        '--output-dir',
        help=f'Output directory for CSV files (default: {DEFAULT_OUTPUT_DIR})'
    )
    parser.add_argument(
        '--no-timestamp',
        dest='timestamp',
        action='store_false',
        default=True,
        help='Do not add timestamp to filenames (may overwrite existing files). By default, timestamps are added to prevent overwriting.'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Allow overwriting existing files without prompt (use with caution)'
    )
    
    args = parser.parse_args()
    
    # Validate mutually exclusive arguments
    if args.baldef_csv and args.phase1_only:
        parser.error("--baldef-csv and --phase1-only cannot be used together. "
                    "Use --phase1-only to CREATE the BALDEF CSV from API, "
                    "or use --baldef-csv to USE an existing BALDEF CSV for ballot participation.")
    
    # Determine output directory
    if args.output_dir:
        output_dir = os.path.abspath(args.output_dir)
    else:
        output_dir = DEFAULT_OUTPUT_DIR
    
    # Generate filenames with optional timestamp
    def generate_filename(base_name, use_timestamp=args.timestamp):
        """Generate filename with optional timestamp suffix."""
        if use_timestamp:
            timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            name, ext = os.path.splitext(base_name)
            return f"{name}-{timestamp}{ext}"
        return base_name
    
    baldef_csv = os.path.join(output_dir, generate_filename("baldef_data.csv"))
    ballot_participation_csv = os.path.join(output_dir, generate_filename("ballot_participation.csv"))
    
    # Check for existing files and warn/error
    def check_file_exists(filepath, file_description):
        """Check if file exists and handle accordingly."""
        if os.path.exists(filepath):
            if args.force:
                print(f"Warning: {file_description} already exists: {filepath}")
                print("  --force flag set, will overwrite existing file.")
                return True
            else:
                print(f"Error: {file_description} already exists: {filepath}")
                print("  Use --force to overwrite, or remove --no-timestamp to create timestamped file.")
                return False
        return True
    
    # Check output files before proceeding
    if not check_file_exists(baldef_csv, "BALDEF CSV"):
        sys.exit(1)
    if not args.phase1_only and not check_file_exists(ballot_participation_csv, "Ballot participation CSV"):
        sys.exit(1)
    
    print("=" * 80)
    print("HL7 Ballot Participation Data Orchestrator")
    print("=" * 80)
    print()
    print(f"Output files will be written to:")
    print(f"  BALDEF CSV: {baldef_csv}")
    if not args.phase1_only:
        print(f"  Ballot Participation CSV: {ballot_participation_csv}")
    print()
    
    # Step 1: Get BALDEF data (from API or CSV)
    # Note: --phase1-only always fetches from API (creates new CSV)
    if args.baldef_csv and not args.phase1_only:
        # Load from existing CSV (only if --baldef-csv provided and NOT phase1-only)
        print("Step 1: Loading BALDEF data from CSV file...")
        try:
            baldef_data = load_baldef_from_csv(args.baldef_csv)
        except Exception as e:
            print(f"Error loading BALDEF CSV: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
    else:
        # Fetch from API (default behavior, or when --phase1-only is used)
        print("Step 1: Fetching BALDEF data from filter 23875...")
        query_params = {
            'jql': 'filter = 23875',
            'fields': 'key,summary,creator,created,status,customfield_11302,customfield_10900,customfield_10901,customfield_11704,customfield_11604,customfield_11610,customfield_11706,customfield_12105,customfield_11806,customfield_14904',
            'maxResults': 1000
        }
        
        try:
            raw_baldef_data = query_jira(DEFAULT_BASE_URL, query_params, BEARER_TOKEN, [])
            print(f"Successfully fetched {len(raw_baldef_data)} BALDEF issues")
        except Exception as e:
            print(f"Error fetching BALDEF data: {e}")
            import traceback
            traceback.print_exc()
            sys.exit(1)
        
        # Step 2: Process BALDEF data
        print("\nStep 2: Processing BALDEF data...")
        baldef_data = process_baldef_data(raw_baldef_data)
        print(f"Processed {len(baldef_data)} BALDEF records")
    
    # Step 3: Export BALDEF CSV
    print("\nStep 3: Exporting BALDEF data to CSV...")
    export_to_csv(baldef_data, baldef_csv, BALDEF_FIELD_MAPPINGS)
    
    # Check if we should skip phase 2
    if args.phase1_only:
        print("\n" + "=" * 80)
        print("Phase 1 Complete (BALDEF CSV created)")
        print("=" * 80)
        print(f"BALDEF records: {len(baldef_data)}")
        print(f"Output file: {baldef_csv}")
        print("\nTo run phase 2 (ballot participation), run:")
        print(f"  python3 {sys.argv[0]} --baldef-csv {baldef_csv}")
        print("\nDone!")
        return
    
    
    # Step 4: Fetch linked BALLOT issues for each BALDEF
    print("\nStep 4: Fetching linked BALLOT issues for each BALDEF...")
    all_ballot_data = []
    total_baldefs = len(baldef_data)
    
    for idx, baldef in enumerate(baldef_data, 1):
        baldef_key = baldef.get('BALDEF ID', '')
        if not baldef_key:
            continue
        
        print(f"  [{idx}/{total_baldefs}] Fetching ballots for {baldef_key}...")
        
        try:
            ballot_issues = fetch_linked_ballot_issues(baldef_key, BEARER_TOKEN)
            ballot_data = process_ballot_data(ballot_issues, baldef_key)
            all_ballot_data.extend(ballot_data)
            print(f"    Found {len(ballot_data)} ballot submissions")
            
            # Add small delay to avoid rate limiting
            time.sleep(0.5)
        except Exception as e:
            print(f"    Error fetching ballots for {baldef_key}: {e}")
            continue
    
    print(f"\nTotal ballot submissions collected: {len(all_ballot_data)}")
    
    # Step 5: Export BALLOT participation CSV
    print("\nStep 5: Exporting ballot participation data to CSV...")
    export_to_csv(all_ballot_data, ballot_participation_csv, BALLOT_FIELD_MAPPINGS)
    
    # Summary
    print("\n" + "=" * 80)
    print("Summary")
    print("=" * 80)
    print(f"BALDEF records: {len(baldef_data)}")
    print(f"Ballot participation records: {len(all_ballot_data)}")
    print(f"\nOutput files:")
    print(f"  - {baldef_csv}")
    print(f"  - {ballot_participation_csv}")
    print("\nDone!")

if __name__ == "__main__":
    main()
