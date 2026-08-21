#!/usr/bin/env python3

"""
HL7 JIRA Issue Enhancer
-----------------------

This script processes a CSV file containing HL7 JIRA issues and enhances it with additional
metadata such as specification details, workgroup information, and realm (country/region) data.

USAGE NOTES:
------------
1. Purpose: Enrich HL7 JIRA issue data with metadata to enable better analytics and
   reporting, particularly for realm/region identification and workgroup tracking.

2. Requirements:
   - Python 3.6+
   - Required packages: pandas, requests, selenium, webdriver_manager
   - Chrome browser (for headless web scraping to extract realm information)
   - Internet connection to access GitHub repositories and HL7 resources

3. Basic Usage:
   python enhance_jira.py -i INPUT_FILE.csv [-o OUTPUT_FILE.csv] [-m REALM_MAPPINGS.csv]

4. Arguments:
   - -i, --input: Path to input CSV file containing JIRA issues (required)
   - -o, --output: Path for enhanced output CSV file (optional, auto-generated if omitted)
   - -m, --mapping: Path to realm mapping file that serves as both lookup and cache (optional, default: realm_mappings.csv)
   - --include-realm: Keep only rows whose resolved Realm matches one of these values.
       * Repeatable and/or comma-separated (e.g., --include-realm "United States,Universal")
       * Special token: "All" disables include filtering
       * Special tokens: "Unknown"/"None" match missing Realm values
   - --exclude-realm: Drop rows whose resolved Realm matches one of these values.
       * Repeatable and/or comma-separated (e.g., --exclude-realm Australia)
       * Special tokens: "Unknown"/"None" match missing Realm values
   - --append-missing-realm-stubs: Append stub rows (spec key with blank realm) for any Specifications
     that did not yield a Realm into the mapping CSV (for manual follow-up edits).

5. What This Script Does:
   - Adds specification display names from HL7's SPECS.json
   - Determines realm/region information using several methods:
     * Specified mapping file (for known specifications)
     * URL pattern analysis (FHIR US/UV detection)
     * Web scraping product briefs for REALM information
     * Caching previously discovered realms for efficiency
   - Adds workgroup names based on JIRA workgroup keys
   - Calculates timing metrics like 'Days to Resolution'
   - Adds month-based aggregation fields for trend analysis

6. Output Enhancements:
   - Specification Display Name: Human-readable specification name
   - Realm: Geographic region (United States, Universal, etc.)
   - WG Name: Full workgroup name
   - Days to Resolution: Time between creation and resolution
   - Creation/Resolution Month: YYYY-MM format for temporal analysis

7. Notes:
   - Uses and maintains a single mapping file that serves as both lookup and cache
   - Special handling for V2 Core specifications
   - Provides console feedback on realm resolution success/failure
   - Always prints a diagnostic list of Specifications that did not yield any Realm (before any realm filtering)
   - When --append-missing-realm-stubs is enabled, stubs are only appended for keys not already present
   - Automatically reorders columns for logical grouping
"""

import argparse
import os
import pandas as pd
from datetime import datetime
import requests
import re
import html
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time

# Global utility function for timestamp formatting
def format_iso_timestamp(timestamp):
    """Format ISO timestamps for proper parsing."""
    if not timestamp or not isinstance(timestamp, str):
        return None
    # Handle +0000 format (convert to +00:00 for fromisoformat)
    if "+0000" in timestamp:
        timestamp = timestamp.replace("+0000", "+00:00")
    # Handle Z format
    if timestamp.endswith("Z"):
        timestamp = timestamp.replace("Z", "+00:00")
    return timestamp

def _normalize_realm_name(realm):
    """
    Normalize realm strings for comparisons / CLI filtering.
    Keeps original realm values in the dataframe; this is for matching only.
    """
    if realm is None:
        return None
    if pd.isna(realm):
        return None
    s = str(realm).strip()
    if s == "":
        return None
    s_lower = s.lower()
    # Common variants / typos
    if s_lower in {"univeral"}:
        return "universal"
    if s_lower in {"us realm", "u.s.", "u.s", "usa"}:
        return "united states"
    return s_lower

def _parse_realm_cli_values(values):
    """
    Parse include/exclude realm arguments.
    Accepts repeated flags and comma-separated lists.
    Special tokens:
      - All: disables include filtering
      - Unknown / None: matches missing Realm
    """
    if not values:
        return []
    parsed = []
    for v in values:
        if v is None:
            continue
        # Allow comma-separated: "United States,Universal"
        parts = [p.strip() for p in str(v).split(",")]
        for p in parts:
            if p:
                parsed.append(p)
    return parsed

def append_missing_realm_stubs_to_mapping(mapping_file, missing_spec_keys):
    """
    Append stub rows to the realm mapping CSV for specs that are missing Realm.
    This is meant for manual follow-up edits (fill in the realm later).
    
    Behavior:
    - Only appends when the spec key is not already present in the file.
    - If a key exists with a blank/missing realm, it is left as-is (no duplicates).
    - Preserves existing rows and appends new rows to the end.
    """
    if not mapping_file:
        return
    if not missing_spec_keys:
        return
    
    # Normalize and de-duplicate incoming keys
    normalized = []
    for k in missing_spec_keys:
        if k is None or (isinstance(k, float) and pd.isna(k)):
            continue
        s = str(k).strip()
        if s:
            normalized.append(s)
    missing_spec_keys = sorted(set(normalized))
    if not missing_spec_keys:
        return
    
    # Load existing mapping file if present, else create empty frame
    if os.path.exists(mapping_file):
        try:
            existing = pd.read_csv(mapping_file)
        except Exception as e:
            print(f"⚠️  Could not read mapping file '{mapping_file}' to append stubs: {e}")
            return
    else:
        existing = pd.DataFrame(columns=['key', 'url', 'realm'])
    
    # Ensure expected columns exist
    for col in ['key', 'url', 'realm']:
        if col not in existing.columns:
            existing[col] = ""
    existing = existing[['key', 'url', 'realm']]
    
    # Build set of existing keys (non-empty)
    existing_keys = set(
        str(v).strip()
        for v in existing['key'].dropna().tolist()
        if str(v).strip() != ""
    )
    
    to_add = [k for k in missing_spec_keys if k not in existing_keys]
    if not to_add:
        # Still useful to warn about already-present blank entries
        blank_mask = existing['key'].isin(missing_spec_keys) & (existing['realm'].isna() | (existing['realm'].astype(str).str.strip() == ""))
        blank_existing = existing.loc[blank_mask, 'key'].dropna().astype(str).str.strip().unique().tolist()
        if blank_existing:
            print(f"Realm mapping already has {len(blank_existing)} stub/blank realm entries (no new stubs appended).")
        return
    
    new_rows = pd.DataFrame([{'key': k, 'url': '', 'realm': ''} for k in to_add], columns=['key', 'url', 'realm'])
    updated = pd.concat([existing, new_rows], ignore_index=True)
    try:
        updated.to_csv(mapping_file, index=False)
        print(f"Appended {len(to_add)} missing-realm stub(s) to mapping file: {mapping_file}")
    except Exception as e:
        print(f"⚠️  Could not write updated mapping file '{mapping_file}': {e}")

def load_realm_mappings(mapping_file):
    """
    Load realm mappings from a single CSV file that serves as both
    lookup and cache.
    
    Args:
        mapping_file (str): Path to the mapping CSV file.
    
    Returns:
        tuple: (spec_to_realm, url_to_realm) dictionaries for lookups
    """
    spec_to_realm = {}
    url_to_realm = {}
    
    if not mapping_file or not os.path.exists(mapping_file):
        return (spec_to_realm, url_to_realm)
        
    try:
        df_mappings = pd.read_csv(mapping_file)
        # Process specification key mappings
        if 'key' in df_mappings.columns and 'realm' in df_mappings.columns:
            for idx, row in df_mappings.iterrows():
                key_val = row.get('key')
                if pd.notna(key_val) and str(key_val).strip() != "":
                    spec_to_realm[str(key_val).strip()] = str(row.get('realm')).strip() if pd.notna(row.get('realm')) else None
        
        # Process URL mappings
        if 'url' in df_mappings.columns and 'realm' in df_mappings.columns:
            for idx, row in df_mappings.iterrows():
                url_val = row.get('url')
                if pd.notna(url_val) and str(url_val).strip() != "":
                    url_to_realm[str(url_val).strip()] = str(row.get('realm')).strip() if pd.notna(row.get('realm')) else None
        
        print(f"Loaded {len(spec_to_realm)} specification mappings and {len(url_to_realm)} URL mappings from {mapping_file}")
        return (spec_to_realm, url_to_realm)
    except Exception as e:
        print(f"Error loading mappings from {mapping_file}: {e}")
        return ({}, {})

def save_realm_mappings(spec_to_realm, url_to_realm, mapping_file):
    """
    Save realm mappings to a single CSV file that serves as both
    lookup and cache.
    
    Args:
        spec_to_realm (dict): Mapping of specification keys to realms.
        url_to_realm (dict): Mapping of URLs to realms.
        mapping_file (str): Path to the mapping CSV file.
    """
    try:
        # Ensure the directory exists
        mapping_dir = os.path.dirname(mapping_file)
        if mapping_dir and not os.path.exists(mapping_dir):
            os.makedirs(mapping_dir)
            
        rows = []
        # Add specification key mappings
        for key, realm in spec_to_realm.items():
            rows.append({'key': key, 'url': '', 'realm': realm})
        
        # Add URL mappings
        for url, realm in url_to_realm.items():
            rows.append({'key': '', 'url': url, 'realm': realm})
        
        df_mappings = pd.DataFrame(rows, columns=['key', 'url', 'realm'])
        df_mappings.to_csv(mapping_file, index=False)
        print(f"Saved {len(spec_to_realm)} specification mappings and {len(url_to_realm)} URL mappings to {mapping_file}")
    except Exception as e:
        print(f"Error saving mappings to {mapping_file}: {e}")

def load_specs_json(url):
    """
    Download and return the SPECS.json data from the given URL.
    
    Args:
        url (str): URL to the SPECS.json file.
    
    Returns:
        list: Parsed JSON data as a list, or an empty list on error.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error loading SPECS.json: {e}")
        return []

def build_specs_mapping(specs_data):
    """
    Build a mapping from the SPECS.json data.
    
    Args:
        specs_data (list): List of specification dictionaries.
    
    Returns:
        dict: Mapping of specification key to display name.
    """
    mapping = {}
    for spec in specs_data:
        spec_key = spec.get("key")
        display_name = spec.get("name")
        if spec_key and display_name:
            mapping[spec_key] = display_name
    return mapping

def extract_realm_from_url(url):
    """
    Fetch the HTML from the given URL using Selenium and extract the REALM information.
    If the extracted realm is 'US Realm', return 'United States'; otherwise return the extracted text.
    """
    try:
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        driver = webdriver.Chrome(options=options)
        driver.get(url)
        time.sleep(3)  # Allow dynamic content to load
        html_content = driver.page_source
        driver.quit()
        pattern = r'<h3>\s*REALM\s*</h3>.*?<li[^>]*>(.*?)</li>'
        match = re.search(pattern, html_content, re.IGNORECASE | re.DOTALL)
        if match:
            realm_text = match.group(1).strip()
            if realm_text == 'US Realm':
                return 'United States'
            else:
                return realm_text
        return None
    except Exception as e:
        print(f"Error fetching realm info from {url}: {e}")
        return None

def build_specs_lookup(specs_data):
    """
    Build a lookup dictionary from SPECS.json data mapping spec key to the full spec object.
    
    Args:
        specs_data (list): List of specification dictionaries.
    
    Returns:
        dict: Mapping of specification key to the full spec object.
    """
    lookup = {}
    for spec in specs_data:
        key = spec.get('key')
        if key:
            lookup[key] = spec
    return lookup

def load_workgroups_json(url):
    """
    Download and return the workgroups JSON data from the given URL.
    
    Args:
        url (str): URL to the workgroups JSON file.
    
    Returns:
        list: Parsed JSON data as a list, or an empty list on error.
    """
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error loading workgroups JSON: {e}")
        return []

def build_workgroup_lookup(workgroups_data):
    """
    Build a lookup dictionary from workgroups JSON data mapping workgroup key to its name.
    HTML-encoded names are unescaped.
    
    Args:
        workgroups_data (list): List of workgroup dictionaries.
    
    Returns:
        dict: Mapping of workgroup key to workgroup name.
    """
    lookup = {}
    for wg in workgroups_data:
        key = wg.get("key")
        name = wg.get("name")
        if key and name:
            # Unescape HTML entities
            lookup[key] = html.unescape(name)
    return lookup

def determine_merge_decisions(group):
    """
    Determine what values would be chosen for each field when merging.
    
    Args:
        group: DataFrame containing all rows for the same Issue ID
    
    Returns:
        dict: Merge decisions and conflicts
    """
    decisions = {}
    conflicts = []
    
    date_fields = ['Created Date', 'Resolution Date', 'Applied Date', 'Approval Date']
    status_fields = ['Status', 'Resolution']
    history_fields = ['Applied Date', 'Applied User', 'History', 'Resolved to Applied Date']
    metadata_fields = ['Specification', 'WG', 'Realm', 'Summary', 'Reporter', 'Issue Type']
    
    # Analyze each field category
    for field in group.columns:
        if field == 'Issue':
            continue
            
        non_null_values = group[field].dropna()
        
        if len(non_null_values) == 0:
            decisions[field] = {
                'strategy': 'all_null',
                'chosen_value': None,
                'source_row': None,
                'alternatives': []
            }
        elif len(non_null_values) == 1:
            # Only one non-null value - easy choice
            chosen_idx = non_null_values.index[0]
            decisions[field] = {
                'strategy': 'single_value',
                'chosen_value': non_null_values.iloc[0],
                'source_row': chosen_idx,
                'alternatives': []
            }
        else:
            # Multiple non-null values - need to decide
            unique_values = non_null_values.unique()
            
            if field in date_fields:
                # For dates, choose the latest
                try:
                    dates = pd.to_datetime(non_null_values, errors='coerce', utc=True)
                    latest_idx = dates.idxmax()
                    decisions[field] = {
                        'strategy': 'latest_date',
                        'chosen_value': group.loc[latest_idx, field],
                        'source_row': latest_idx,
                        'alternatives': [{'row': idx, 'value': val} 
                                       for idx, val in non_null_values.items() 
                                       if idx != latest_idx]
                    }
                    if len(unique_values) > 1:
                        conflicts.append({
                            'field': field,
                            'type': 'date_variation',
                            'values': [str(v) for v in unique_values],
                            'chosen': str(group.loc[latest_idx, field])
                        })
                except:
                    # Fallback: use last non-null
                    last_idx = non_null_values.index[-1]
                    decisions[field] = {
                        'strategy': 'last_non_null',
                        'chosen_value': group.loc[last_idx, field],
                        'source_row': last_idx,
                        'alternatives': [{'row': idx, 'value': val} 
                                       for idx, val in non_null_values.items() 
                                       if idx != last_idx]
                    }
                    
            elif field in status_fields:
                # For status, take the last (most recent)
                last_idx = non_null_values.index[-1]
                decisions[field] = {
                    'strategy': 'most_recent',
                    'chosen_value': group.loc[last_idx, field],
                    'source_row': last_idx,
                    'alternatives': [{'row': idx, 'value': val} 
                                   for idx, val in non_null_values.items() 
                                   if idx != last_idx]
                }
                if len(unique_values) > 1:
                    conflicts.append({
                        'field': field,
                        'type': 'status_change',
                        'values': [str(v) for v in unique_values],
                        'chosen': str(group.loc[last_idx, field])
                    })
                    
            elif field == 'History':
                # For History JSON, choose the longest/most complete
                history_lengths = non_null_values.apply(lambda x: len(str(x)) if x else 0)
                best_idx = history_lengths.idxmax()
                decisions[field] = {
                    'strategy': 'most_complete',
                    'chosen_value': group.loc[best_idx, field],
                    'source_row': best_idx,
                    'alternatives': [{'row': idx, 'value': f"<{len(str(val))} chars>" 
                                     if val else None} 
                                   for idx, val in non_null_values.items() 
                                   if idx != best_idx]
                }
                
            elif field in metadata_fields:
                # For metadata, take the last non-null (assuming corrections)
                last_idx = non_null_values.index[-1]
                decisions[field] = {
                    'strategy': 'last_non_null',
                    'chosen_value': group.loc[last_idx, field],
                    'source_row': last_idx,
                    'alternatives': [{'row': idx, 'value': val} 
                                   for idx, val in non_null_values.items() 
                                   if idx != last_idx]
                }
                if len(unique_values) > 1:
                    conflicts.append({
                        'field': field,
                        'type': 'metadata_conflict',
                        'values': [str(v) for v in unique_values],
                        'chosen': str(group.loc[last_idx, field])
                    })
            else:
                # Default: last non-null
                last_idx = non_null_values.index[-1]
                decisions[field] = {
                    'strategy': 'last_non_null',
                    'chosen_value': group.loc[last_idx, field],
                    'source_row': last_idx,
                    'alternatives': [{'row': idx, 'value': val} 
                                   for idx, val in non_null_values.items() 
                                   if idx != last_idx]
                }
    
    return {
        'decisions': decisions,
        'conflicts': conflicts
    }

def normalize_status_values(df):
    """
    Normalize status values to match canonical workflow status names.
    Handles case variations and common inconsistencies.
    
    Args:
        df: DataFrame to normalize
    
    Returns:
        DataFrame: DataFrame with normalized status values
    """
    if 'Status' not in df.columns:
        return df
    
    # Define status normalization mapping
    # Maps common variations to canonical status names
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
    
    # Define canonical status names (from workflow definition)
    canonical_statuses = {
        'Submitted',
        'Triaged',
        'Waiting for Input',
        'Resolved - No Change',
        'Resolved - Change Required',
        'Deferred',
        'Duplicate',
        'Applied',
        'Published'
    }
    
    # Track normalization
    normalization_summary = {}
    
    # Apply normalization using case-insensitive matching for known variations
    for old_status, new_status in status_normalization_map.items():
        mask = df['Status'].str.strip().str.lower() == old_status.lower()
        if mask.any():
            count = mask.sum()
            normalization_summary[old_status] = {'to': new_status, 'count': count}
            df.loc[mask, 'Status'] = new_status
    
    # Also handle case-insensitive matching for any status that's close to canonical
    # This catches any other case variations we might have missed
    for status_value in df['Status'].dropna().unique():
        status_str = str(status_value).strip()
        # Skip if already canonical
        if status_str in canonical_statuses:
            continue
        
        # Try case-insensitive match against canonical statuses
        status_lower = status_str.lower()
        for canonical in canonical_statuses:
            if status_lower == canonical.lower():
                # Found a case variation - normalize it
                mask = df['Status'] == status_value
                count = mask.sum()
                if status_value not in normalization_summary:
                    normalization_summary[status_value] = {'to': canonical, 'count': count}
                df.loc[mask, 'Status'] = canonical
                break
    
    # Report normalization
    total_normalized = sum(info['count'] for info in normalization_summary.values())
    if total_normalized > 0:
        print(f"Normalized {total_normalized} status value(s) to canonical format:")
        for old_status, info in normalization_summary.items():
            print(f"  • '{old_status}' → '{info['to']}' ({info['count']} issue(s))")
    
    return df

def analyze_missing_created_date(df):
    """
    Analyze missing Created Date values in the dataset.
    
    Args:
        df: DataFrame to analyze
    
    Returns:
        dict: Analysis results with details about missing Created Date values
    """
    if 'Created Date' not in df.columns:
        return {
            'has_missing_column': True,
            'missing_column': 'Created Date',
            'missing_count': len(df),
            'issues_with_missing': []
        }
    
    missing_mask = df['Created Date'].isna()
    missing_count = missing_mask.sum()
    
    if missing_count == 0:
        return {
            'has_missing_column': False,
            'missing_column': None,
            'missing_count': 0,
            'issues_with_missing': []
        }
    
    # Identify which issues have missing Created Date
    issues_with_missing = []
    if 'Issue' in df.columns:
        issues_with_missing = df.loc[missing_mask, 'Issue'].tolist()
    else:
        # If no Issue column, use index
        missing_indices = df[missing_mask].index.tolist()
        issues_with_missing = [f"Row {idx}" for idx in missing_indices]
    
    # Get additional context for missing issues
    missing_details = []
    
    # Also check for unparseable dates (simulating what applied-issues-analyze.py does)
    # The analysis script uses pd.to_datetime(..., errors='coerce') which converts unparseable dates to NaT
    unparseable_mask = pd.Series([False] * len(df), index=df.index)
    unparseable_count = 0
    try:
        parsed_dates = pd.to_datetime(df['Created Date'], errors='coerce', utc=True)
        # Find dates that exist but couldn't be parsed (became NaT)
        unparseable_mask = df['Created Date'].notna() & parsed_dates.isna()
        unparseable_count = unparseable_mask.sum()
    except Exception:
        pass  # If parsing fails entirely, skip this check
    
    # Combine missing and unparseable
    all_problematic_mask = missing_mask | unparseable_mask
    
    for idx in df[all_problematic_mask].index:
        is_missing = missing_mask.loc[idx] if idx in missing_mask.index else False
        is_unparseable = unparseable_mask.loc[idx] if idx in unparseable_mask.index else False
        created_date_value = df.loc[idx, 'Created Date'] if 'Created Date' in df.columns else None
        
        issue_info = {
            'index': idx,
            'issue_id': df.loc[idx, 'Issue'] if 'Issue' in df.columns else f"Row {idx}",
            'is_missing': is_missing,
            'is_unparseable': is_unparseable,
            'created_date_value': str(created_date_value) if created_date_value is not None else None,
            'has_resolution_date': pd.notna(df.loc[idx, 'Resolution Date']) if 'Resolution Date' in df.columns else False,
            'has_applied_date': pd.notna(df.loc[idx, 'Applied Date']) if 'Applied Date' in df.columns else False,
            'has_history': pd.notna(df.loc[idx, 'History']) if 'History' in df.columns else False,
            'status': df.loc[idx, 'Status'] if 'Status' in df.columns else None
        }
        missing_details.append(issue_info)
    
    # Calculate total problematic issues
    total_problematic = missing_count + unparseable_count
    
    return {
        'has_missing_column': False,
        'missing_column': None,
        'missing_count': missing_count,
        'unparseable_count': unparseable_count,
        'total_problematic': total_problematic,
        'issues_with_missing': issues_with_missing,
        'missing_details': missing_details,
        'total_issues': len(df)
    }

def print_missing_created_date_report(analysis):
    """
    Print a detailed report about missing Created Date values.
    
    Args:
        analysis: Analysis results from analyze_missing_created_date
    """
    if analysis['has_missing_column']:
        print(f"\n{'='*80}")
        print(f"❌ ERROR: Required column '{analysis['missing_column']}' is missing from the dataset")
        print(f"{'='*80}\n")
        return
    
    if analysis['missing_count'] == 0 and analysis.get('unparseable_count', 0) == 0:
        print(f"\n✅ All issues have Created Date values that can be parsed. No missing data detected.")
        return
    
    print(f"\n{'='*80}")
    print(f"⚠️  MISSING CREATED DATE DETECTION REPORT")
    print(f"{'='*80}")
    
    total_issues = analysis['total_issues']
    missing_count = analysis['missing_count']
    missing_pct = (missing_count / total_issues * 100) if total_issues > 0 else 0
    
    missing_count = analysis['missing_count']
    unparseable_count = analysis.get('unparseable_count', 0)
    total_problematic = analysis.get('total_problematic', missing_count)
    
    print(f"\nSummary:")
    print(f"  • Total issues in dataset: {total_issues}")
    if missing_count > 0:
        print(f"  • Issues with missing Created Date (null values): {missing_count}")
    if unparseable_count > 0:
        print(f"  • Issues with unparseable Created Date (will become NaT): {unparseable_count}")
    print(f"  • Total problematic issues: {total_problematic} ({total_problematic/total_issues*100:.2f}%)")
    print(f"  • Issues with valid Created Date: {total_issues - total_problematic}")
    
    if analysis['missing_details']:
        print(f"\n{'='*80}")
        print(f"Detailed Analysis of Issues with Missing Created Date:")
        print(f"{'='*80}\n")
        
        # Group by potential recovery sources
        has_resolution = [d for d in analysis['missing_details'] if d['has_resolution_date']]
        has_applied = [d for d in analysis['missing_details'] if d['has_applied_date']]
        has_history = [d for d in analysis['missing_details'] if d['has_history']]
        
        print(f"Potential Recovery Sources:")
        print(f"  • Issues with Resolution Date: {len(has_resolution)} (could use as fallback)")
        print(f"  • Issues with Applied Date: {len(has_applied)} (could use as fallback)")
        print(f"  • Issues with History data: {len(has_history)} (could extract from history)")
        
        print(f"\nIssues with Missing or Unparseable Created Date:")
        for i, detail in enumerate(analysis['missing_details'], 1):
            issue_id = detail['issue_id']
            status = detail['status'] if detail['status'] else 'N/A'
            recovery_options = []
            
            problem_type = []
            if detail.get('is_missing', False):
                problem_type.append("Missing (null value)")
            if detail.get('is_unparseable', False):
                problem_type.append("Unparseable")
            
            problem_str = " and ".join(problem_type) if problem_type else "Unknown issue"
            
            if detail['has_resolution_date']:
                recovery_options.append("Resolution Date available")
            if detail['has_applied_date']:
                recovery_options.append("Applied Date available")
            if detail['has_history']:
                recovery_options.append("History data available")
            
            recovery_str = ", ".join(recovery_options) if recovery_options else "No obvious recovery source"
            
            print(f"  {i}. {issue_id}")
            print(f"     Problem: {problem_str}")
            if detail.get('created_date_value'):
                print(f"     Created Date value: '{detail['created_date_value']}'")
            print(f"     Status: {status}")
            print(f"     Recovery options: {recovery_str}")
        
        # Show sample issue IDs
        if len(analysis['issues_with_missing']) <= 20:
            print(f"\nAll issue IDs with missing Created Date:")
            print(f"  {', '.join(str(issue) for issue in analysis['issues_with_missing'])}")
        else:
            print(f"\nSample issue IDs with missing Created Date (showing first 20):")
            print(f"  {', '.join(str(issue) for issue in analysis['issues_with_missing'][:20])}")
            print(f"  ... and {len(analysis['issues_with_missing']) - 20} more")
    
    print(f"\n{'='*80}")
    print(f"Recommendation:")
    print(f"  These issues may be recoverable from History data if available.")
    print(f"  Consider implementing Created Date extraction from History transitions.")
    print(f"{'='*80}\n")

def analyze_duplicates_for_dry_run(df):
    """
    Analyze duplicates and generate a detailed report of what would be merged.
    
    Args:
        df: DataFrame to analyze
    
    Returns:
        dict: Analysis results with details about duplicates
    """
    if 'Issue' not in df.columns:
        return {
            'has_duplicates': False,
            'duplicate_groups': [],
            'total_duplicate_rows': 0,
            'unique_issues_with_duplicates': 0
        }
    
    duplicates = df[df.duplicated(subset=['Issue'], keep=False)]
    
    if len(duplicates) == 0:
        return {
            'has_duplicates': False,
            'duplicate_groups': [],
            'total_duplicate_rows': 0,
            'unique_issues_with_duplicates': 0
        }
    
    # Group by Issue ID
    duplicate_groups = []
    for issue_id, group in duplicates.groupby('Issue'):
        group_info = {
            'issue_id': issue_id,
            'row_count': len(group),
            'rows': [],
            'merge_decisions': {},
            'conflicts': []
        }
        
        # Analyze each row in the group
        for idx, row in group.iterrows():
            row_data = {}
            for col in group.columns:
                value = row[col]
                row_data[col] = value if pd.notna(value) else None
            group_info['rows'].append({
                'index': idx,
                'data': row_data
            })
        
        # Determine what would be merged
        merge_decisions = determine_merge_decisions(group)
        group_info['merge_decisions'] = merge_decisions
        group_info['conflicts'] = merge_decisions.get('conflicts', [])
        
        duplicate_groups.append(group_info)
    
    return {
        'has_duplicates': True,
        'duplicate_groups': duplicate_groups,
        'total_duplicate_rows': len(duplicates),
        'unique_issues_with_duplicates': len(duplicate_groups),
        'rows_to_remove': len(duplicates) - len(duplicate_groups)
    }

def print_dry_run_report(analysis):
    """
    Print a detailed dry-run report showing what would be merged.
    
    Args:
        analysis: Analysis results from analyze_duplicates_for_dry_run
    """
    if not analysis['has_duplicates']:
        print("\n✅ No duplicate Issue IDs found. Nothing to merge.")
        return
    
    print(f"\n{'='*80}")
    print(f"DRY-RUN REPORT: Duplicate Issue ID Analysis")
    print(f"{'='*80}")
    initial_count = analysis.get('initial_count', 0)
    final_count = initial_count - analysis['rows_to_remove'] if initial_count > 0 else analysis['unique_issues_with_duplicates']
    
    print(f"\nSummary:")
    print(f"  • Initial row count: {initial_count}")
    print(f"  • Total duplicate rows found: {analysis['total_duplicate_rows']}")
    print(f"  • Unique issues with duplicates: {analysis['unique_issues_with_duplicates']}")
    print(f"  • Rows that would be removed: {analysis['rows_to_remove']}")
    print(f"  • Final row count after merge: {final_count}")
    
    print(f"\n{'='*80}")
    print(f"Detailed Analysis by Issue:")
    print(f"{'='*80}\n")
    
    for i, group_info in enumerate(analysis['duplicate_groups'], 1):
        issue_id = group_info['issue_id']
        row_count = group_info['row_count']
        conflicts = group_info['conflicts']
        
        print(f"\n{i}. Issue: {issue_id}")
        print(f"   Duplicate rows: {row_count}")
        
        if conflicts:
            print(f"   ⚠️  CONFLICTS DETECTED:")
            for conflict in conflicts:
                print(f"      • {conflict['field']}: {conflict['type']}")
                print(f"        Values: {conflict['values']}")
                print(f"        Chosen: {conflict['chosen']}")
        
        # Show merge decisions for key fields
        decisions = group_info['merge_decisions'].get('decisions', {})
        key_fields = ['Status', 'Specification', 'WG', 'Resolution Date', 'Applied Date', 
                     'Created Date', 'Realm']
        
        print(f"   Merge decisions for key fields:")
        for field in key_fields:
            if field in decisions:
                decision = decisions[field]
                strategy = decision['strategy']
                value = decision['chosen_value']
                source_row = decision['source_row']
                
                if value is not None:
                    # Truncate long values
                    display_value = str(value)
                    if len(display_value) > 50:
                        display_value = display_value[:47] + "..."
                    print(f"      • {field}: '{display_value}' (from row {source_row}, strategy: {strategy})")
                    
                    # Show alternatives if any
                    if decision.get('alternatives'):
                        alt_count = len(decision['alternatives'])
                        print(f"        ({alt_count} alternative value(s) would be discarded)")
        
        # Show all rows being merged
        print(f"   Rows being merged:")
        for j, row_info in enumerate(group_info['rows'], 1):
            idx = row_info['index']
            data = row_info['data']
            print(f"      Row {j} (index {idx}):")
            
            # Show key fields
            key_data = {k: v for k, v in data.items() 
                       if k in ['Status', 'Specification', 'WG', 'Resolution Date', 
                               'Applied Date', 'Created Date'] and v is not None}
            if key_data:
                for key, val in key_data.items():
                    display_val = str(val)
                    if len(display_val) > 40:
                        display_val = display_val[:37] + "..."
                    print(f"        {key}: {display_val}")
    
    print(f"\n{'='*80}")
    print(f"End of Dry-Run Report")
    print(f"{'='*80}\n")

def merge_duplicate_group(group, issue_id):
    """
    Merge a group of duplicate rows for the same Issue ID.
    
    Args:
        group: DataFrame containing all rows for the same Issue ID
        issue_id: The Issue ID being merged
    
    Returns:
        Series: Single merged row
    """
    # Start with the first row as base
    merged = group.iloc[0].copy()
    
    # Define field categories for different merge strategies
    date_fields = ['Created Date', 'Resolution Date', 'Applied Date', 'Approval Date']
    status_fields = ['Status', 'Resolution']
    history_fields = ['Applied Date', 'Applied User', 'History', 'Resolved to Applied Date']
    metadata_fields = ['Specification', 'WG', 'Realm', 'Summary', 'Reporter', 'Issue Type']
    calculated_fields = ['Days to Resolution', 'Creation Month', 'Resolution Month']
    
    # Strategy 1: For date fields, keep the LATEST non-null value
    for field in date_fields:
        if field in group.columns:
            non_null_dates = group[field].dropna()
            if len(non_null_dates) > 0:
                # Parse dates and get the latest (for comparison only)
                try:
                    dates = pd.to_datetime(non_null_dates, errors='coerce', utc=True)
                    # Filter out NaT values (unparseable dates)
                    valid_dates = dates[dates.notna()]
                    if len(valid_dates) > 0:
                        # Find the index of the latest date
                        latest_idx = valid_dates.idxmax()
                        # Preserve the ORIGINAL string value from that row, not the datetime object
                        # This ensures the format is preserved for CSV writing
                        original_value = group.loc[latest_idx, field]
                        merged[field] = original_value
                    else:
                        # All dates became NaT - keep the original string value from first row
                        merged[field] = non_null_dates.iloc[0]
                except Exception as e:
                    # If parsing fails entirely, use the last non-null value (preserve original format)
                    merged[field] = non_null_dates.iloc[-1]
    
    # Strategy 2: For status fields, keep the MOST RECENT (assume later rows are more recent)
    for field in status_fields:
        if field in group.columns:
            non_null_statuses = group[field].dropna()
            if len(non_null_statuses) > 0:
                # Take the last non-null status (assuming rows are in chronological order)
                merged[field] = non_null_statuses.iloc[-1]
    
    # Strategy 3: For history fields, prefer the most complete history data
    for field in history_fields:
        if field in group.columns:
            non_null_values = group[field].dropna()
            if len(non_null_values) > 0:
                # For History JSON, prefer the longest/most complete
                if field == 'History':
                    # Find the row with the most complete history
                    history_lengths = non_null_values.apply(lambda x: len(str(x)) if x else 0)
                    best_idx = history_lengths.idxmax()
                    merged[field] = group.loc[best_idx, field]
                else:
                    # For other history fields, take latest non-null
                    merged[field] = non_null_values.iloc[-1]
    
    # Strategy 4: For metadata fields, prefer non-null values, with preference for later rows
    for field in metadata_fields:
        if field in group.columns:
            non_null_values = group[field].dropna()
            if len(non_null_values) > 0:
                # Take the last non-null value (assuming corrections in later exports)
                merged[field] = non_null_values.iloc[-1]
    
    # Strategy 5: Recalculate calculated fields after merging
    # (These will be recalculated later in the script anyway)
    for field in calculated_fields:
        if field in merged.index:
            merged[field] = None  # Will be recalculated
    
    return merged

def merge_duplicate_issues(df, dry_run=False):
    """
    Intelligently merge rows with duplicate Issue IDs.
    
    Args:
        df: DataFrame to process
        dry_run: If True, only analyze and report, don't actually merge
    
    Returns:
        DataFrame: Merged DataFrame (or original if dry_run=True)
    """
    if 'Issue' not in df.columns:
        if dry_run:
            print("No 'Issue' column found. Cannot detect duplicates.")
        return df
    
    initial_count = len(df)
    duplicates = df[df.duplicated(subset=['Issue'], keep=False)]
    
    if len(duplicates) == 0:
        if dry_run:
            print("\n✅ No duplicate Issue IDs found. Nothing to merge.")
        return df
    
    if dry_run:
        # Analyze and report
        analysis = analyze_duplicates_for_dry_run(df)
        analysis['initial_count'] = initial_count
        print_dry_run_report(analysis)
        return df  # Return original, don't modify
    
    # Actual merge
    merged_rows = []
    
    for issue_id, group in df.groupby('Issue'):
        if len(group) == 1:
            merged_rows.append(group.iloc[0])
            continue
        
        # Multiple rows for same issue - merge them
        merged_row = merge_duplicate_group(group, issue_id)
        merged_rows.append(merged_row)
    
    result_df = pd.DataFrame(merged_rows)
    final_count = len(result_df)
    removed_count = initial_count - final_count
    
    print(f"\n✅ Merged {removed_count} duplicate rows. Final count: {final_count}")
    return result_df

def process_csv(input_file, output_file=None, mapping_file='realm_mappings.csv', df=None,
                include_realms=None, exclude_realms=None,
                append_missing_realm_stubs=False):
    """
    Process a CSV file containing JIRA issues and add additional metrics.
    
    Args:
        input_file (str): Path to the input CSV file (used for output path if df provided).
        output_file (str, optional): Path for the output file. If None, auto-generated.
        mapping_file (str, optional): Path to the combined lookup/cache file. 
                                     Default is 'realm_mappings.csv'.
        df (DataFrame, optional): Pre-loaded DataFrame (if None, loads from input_file)
    
    Returns:
        str: Path to the enhanced output file.
    """
    # Generate output file name if not provided
    if output_file is None:
        directory = os.path.dirname(input_file)
        filename = os.path.basename(input_file)
        base_name, extension = os.path.splitext(filename)
        output_file = os.path.join(directory, f"{base_name}-enhanced{extension}")
    
    # Load CSV if not provided
    if df is None:
        df = pd.read_csv(input_file)
        # Merge duplicates when loading from file (if not already merged)
        df = merge_duplicate_issues(df, dry_run=False)
    # Note: If df is provided, it should already be deduplicated (e.g., from main() with dry-run handling)
    
    # Normalize status values to canonical format (handles case variations)
    df = normalize_status_values(df)
    
    # Check for missing Created Date (warn but continue)
    if 'Created Date' in df.columns:
        # Check for missing values BEFORE date conversion
        missing_before = df['Created Date'].isna().sum()
        
        # Try to parse dates to detect unparseable values (like the analysis script does)
        # This simulates what pd.to_datetime(..., errors='coerce') will do
        try:
            parsed_dates = pd.to_datetime(df['Created Date'], errors='coerce', utc=True)
            missing_after_parse = parsed_dates.isna().sum()
            unparseable_count = missing_after_parse - missing_before
            
            if missing_before > 0:
                print(f"\n⚠️  WARNING: Found {missing_before} issue(s) with missing Created Date (null values)")
                if 'Issue' in df.columns:
                    missing_issues = df[df['Created Date'].isna()]['Issue'].tolist()
                    if len(missing_issues) <= 10:
                        print(f"   Issues with null Created Date: {', '.join(str(issue) for issue in missing_issues)}")
                    else:
                        print(f"   Sample issues with null Created Date: {', '.join(str(issue) for issue in missing_issues[:10])} ... and {len(missing_issues) - 10} more")
            
            if unparseable_count > 0:
                print(f"\n⚠️  WARNING: Found {unparseable_count} issue(s) with Created Date values that cannot be parsed")
                print(f"   These will become NaT (missing) when processed by the analysis script.")
                if 'Issue' in df.columns:
                    # Find issues where Created Date exists but can't be parsed
                    unparseable_mask = df['Created Date'].notna() & parsed_dates.isna()
                    unparseable_issues = df[unparseable_mask]
                    if len(unparseable_issues) > 0:
                        sample_issues = unparseable_issues.head(10)
                        print(f"   Sample issues with unparseable Created Date:")
                        for idx, row in sample_issues.iterrows():
                            issue_id = row.get('Issue', f"Row {idx}")
                            created_date_value = row['Created Date']
                            print(f"     • {issue_id}: '{created_date_value}' (type: {type(created_date_value).__name__})")
                        if len(unparseable_issues) > 10:
                            print(f"     ... and {len(unparseable_issues) - 10} more")
            
            total_missing = missing_after_parse
            if total_missing > 0:
                print(f"\n   Total issues that will have missing Created Date after processing: {total_missing}")
                print(f"   These issues may cause errors in downstream processing.")
                print(f"   Consider extracting Created Date from History data if available.")
        except Exception as e:
            print(f"\n⚠️  WARNING: Could not validate Created Date parsing: {e}")
            # Fall back to simple check
            missing_created_count = df['Created Date'].isna().sum()
            if missing_created_count > 0:
                print(f"   Found {missing_created_count} issue(s) with missing Created Date")
    else:
        print(f"\n❌ ERROR: Required column 'Created Date' is missing from the dataset")
        raise ValueError("Required column 'Created Date' is missing from the dataset")
    
    # Error corrections
    
    # Error correction 1: Change Specification to "V2-lri" for Issue "V2-25638"
    if 'Issue' in df.columns and 'Specification' in df.columns:
        df.loc[df['Issue'] == 'V2-25638', 'Specification'] = 'V2-lri'
        print("Applied error correction: Updated Specification to 'V2-lri' for Issue 'V2-25638'")
    
    # Error correction 2: Assign WG "v2mg" for Issue "V2-15528" 
    if 'Issue' in df.columns and 'WG' in df.columns:
        df.loc[df['Issue'] == 'V2-15528', 'WG'] = 'v2mg'
        print("Applied error correction: Updated WG to 'v2mg' for Issue 'V2-15528'")
    
    # Load combined mappings
    spec_to_realm, url_to_realm = load_realm_mappings(mapping_file)
    
    # Apply specification-based realm mapping
    if 'Specification' in df.columns:
        def get_realm(specification):
            if pd.isna(specification) or not specification:
                return None
            return spec_to_realm.get(specification, None)
        df['Realm'] = df['Specification'].apply(get_realm)
        print(f"Added realm information to {df['Realm'].notna().sum()} records from specification mappings")
    
    # Enhance CSV with Specification Display Name from SPECS.json
    if 'Specification' in df.columns:
        specs_url = "https://raw.githubusercontent.com/HL7/JIRA-Spec-Artifacts/gh-pages/SPECS.json"
        specs_data = load_specs_json(specs_url)
        if specs_data:
            specs_mapping = build_specs_mapping(specs_data)
            
            # --- original display-name lookup ---
            def get_spec_display_name(specification):
                if pd.isna(specification) or not specification:
                    return None
                return specs_mapping.get(specification, None)
            df["Specification Display Name"] = df["Specification"].apply(get_spec_display_name)
            
            # --- override for core / V2 ---
            # ensure Product Family exists
            if 'Product Family' not in df.columns:
                df['Product Family'] = df['Issue'].str.split('-').str[0]
            # apply override mask
            mask = (df['Specification'] == 'core') & (df['Product Family'] == 'V2')
            df.loc[mask, 'Specification Display Name'] = 'V2 Core (V2)'
            
            print(f"Added specification display names for {df['Specification Display Name'].notna().sum()} records")
            
            # Determine REALM information using SPECS.json and associated URL
            specs_lookup = build_specs_lookup(specs_data)
            failed_urls = set()
            def get_resolved_realm(specification):
                if pd.isna(specification) or not specification:
                    return None
                # Check for specification key in our mapping
                if specification in spec_to_realm:
                    print(f"Using existing mapping for spec '{specification}'")
                    return spec_to_realm[specification]
                spec_obj = specs_lookup.get(specification)
                if not spec_obj:
                    return None
                url = spec_obj.get('url')
                if url:
                    # Handle FHIR URL patterns
                    if url.startswith("http://hl7.org/fhir/uv/"):
                        print(f"Detected FHIR UV URL for {url}, returning 'Universal'")
                        realm_val = "Universal"
                        # Add to mappings
                        spec_to_realm[specification] = realm_val
                        save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                        return realm_val
                    elif url.startswith("http://hl7.org/fhir/us/"):
                        print(f"Detected FHIR US URL for {url}, returning 'United States'")
                        realm_val = "United States"
                        # Add to mappings
                        spec_to_realm[specification] = realm_val
                        save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                        return realm_val
                    elif url == "http://hl7.org/fhir":
                        print(f"Detected exact FHIR URL for {url}, returning 'Universal'")
                        realm_val = "Universal"
                        # Add to mappings
                        spec_to_realm[specification] = realm_val
                        save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                        return realm_val
                    # Handle specific CDA URL patterns
                    if url.startswith("http://hl7.org/cda/us/"):
                        print(f"Detected CDA US URL for {url}, returning 'United States'")
                        realm_val = "United States"
                        # Add to mappings
                        spec_to_realm[specification] = realm_val
                        save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                        return realm_val
                    elif url.startswith("http://hl7.org/cda/stds/"):
                        print(f"Detected CDA STDS URL for {url}, returning 'Universal'")
                        realm_val = "Universal"
                        # Add to mappings
                        spec_to_realm[specification] = realm_val
                        save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                        return realm_val
                    # Otherwise, if it's a product brief URL containing '?product_id='
                    elif '?product_id=' in url:
                        if url in url_to_realm:
                            print(f"Using cached realm for URL: {url}")
                            realm_val = url_to_realm[url]
                            # Also add to specification mapping
                            spec_to_realm[specification] = realm_val
                            save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                            return realm_val
                        else:
                            print(f"Processing URL: {url}")
                            realm_val = extract_realm_from_url(url)
                            if realm_val is not None:
                                # Update both dictionaries
                                url_to_realm[url] = realm_val
                                spec_to_realm[specification] = realm_val
                                save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                            else:
                                failed_urls.add(url)
                            return realm_val
                return None
            df['Resolved Realm'] = df['Specification'].apply(get_resolved_realm)
            print(f"Added resolved realm information for {df['Resolved Realm'].notna().sum()} records")
            if failed_urls:
                print("Failed to extract realm for the following URLs:")
                for failed_url in failed_urls:
                    print(failed_url)
        else:
            print("Warning: Could not load SPECS.json, so 'Specification Display Name' not added.")
    
    # Update the 'Realm' column with non-null values from 'Resolved Realm'
    if 'Resolved Realm' in df.columns:
        if 'Realm' in df.columns:
            df['Realm'] = df['Realm'].astype('object')
        else:
            df['Realm'] = None
        df.loc[df['Resolved Realm'].notna(), 'Realm'] = df.loc[df['Resolved Realm'].notna(), 'Resolved Realm']
        print("Updated 'Realm' column with resolved realm data where available.")

    # Diagnostics: always report specs with missing Realm (before include/exclude filtering)
    unresolved_specs = []
    if 'Specification' in df.columns and 'Realm' in df.columns:
        unresolved_specs = sorted(
            set(
                str(s).strip()
                for s in df.loc[df['Specification'].notna() & df['Realm'].isna(), 'Specification'].tolist()
                if str(s).strip() != ""
            )
        )
        if unresolved_specs:
            print("The following Specifications did not yield any Realm:")
            for spec in unresolved_specs:
                print(spec)
    
    if append_missing_realm_stubs and unresolved_specs:
        append_missing_realm_stubs_to_mapping(mapping_file, unresolved_specs)

    # Realm filtering (after realm is fully resolved from cache + dynamic lookups)
    include_realms = include_realms or []
    exclude_realms = exclude_realms or []
    include_tokens = [_normalize_realm_name(x) for x in include_realms]
    exclude_tokens = [_normalize_realm_name(x) for x in exclude_realms]

    include_tokens = [t for t in include_tokens if t is not None]
    exclude_tokens = [t for t in exclude_tokens if t is not None]

    if include_tokens and "all" in include_tokens:
        include_tokens = []

    # Support including/excluding missing realm via "unknown"/"none"
    include_unknown = any(t in {"unknown", "none", "null"} for t in include_tokens)
    exclude_unknown = any(t in {"unknown", "none", "null"} for t in exclude_tokens)
    include_tokens = [t for t in include_tokens if t not in {"unknown", "none", "null"}]
    exclude_tokens = [t for t in exclude_tokens if t not in {"unknown", "none", "null"}]

    if 'Realm' in df.columns and (include_tokens or exclude_tokens or include_unknown or exclude_unknown):
        initial_rows = len(df)
        realm_norm = df['Realm'].apply(_normalize_realm_name)
        is_unknown = realm_norm.isna()

        keep_mask = pd.Series([True] * len(df), index=df.index)

        if include_tokens or include_unknown:
            keep_mask = pd.Series([False] * len(df), index=df.index)
            if include_tokens:
                keep_mask = keep_mask | realm_norm.isin(include_tokens)
            if include_unknown:
                keep_mask = keep_mask | is_unknown

        if exclude_tokens:
            keep_mask = keep_mask & (~realm_norm.isin(exclude_tokens))
        if exclude_unknown:
            keep_mask = keep_mask & (~is_unknown)

        df = df.loc[keep_mask].copy()
        removed = initial_rows - len(df)
        print(f"Realm filter applied. Kept {len(df)} rows, removed {removed} rows.")
    
    # Add WG Name based on the WG field and workgroups JSON
    if "WG" in df.columns:
        workgroups_url = "https://raw.githubusercontent.com/HL7/JIRA-Spec-Artifacts/refs/heads/gh-pages/workgroups.json"
        workgroups_data = load_workgroups_json(workgroups_url)
        if workgroups_data:
            wg_lookup = build_workgroup_lookup(workgroups_data)
            df["WG Name"] = df["WG"].apply(lambda x: wg_lookup.get(x) if pd.notna(x) else None)
            print(f"Added WG Name for {df['WG Name'].notna().sum()} records")
            # Reorder columns so that WG Name appears right after WG
            cols = list(df.columns)
            if "WG" in cols and "WG Name" in cols:
                wg_index = cols.index("WG")
                cols.remove("WG Name")
                cols.insert(wg_index + 1, "WG Name")
                df = df[cols]
        else:
            print("Warning: Could not load workgroups JSON; 'WG Name' not added.")
    
    # Ensure Product Family exists (again, if not already)
    if 'Product Family' not in df.columns:
        df['Product Family'] = df['Issue'].str.split('-').str[0]
    
    def calculate_time_to_resolution(row):
        try:
            created_date_str = format_iso_timestamp(row['Created Date'])
            resolution_date_str = format_iso_timestamp(row['Resolution Date'])
            if not created_date_str or not resolution_date_str:
                return None
            created_date = datetime.fromisoformat(created_date_str)
            resolution_date = datetime.fromisoformat(resolution_date_str)
            delta = resolution_date - created_date
            days = delta.total_seconds() / (24 * 60 * 60)
            return float(f"{days:.3g}")
        except (ValueError, TypeError, AttributeError) as e:
            print(f"Error processing dates: {row['Created Date']} - {row['Resolution Date']}: {e}")
            return None
    
    df['Days to Resolution'] = df.apply(calculate_time_to_resolution, axis=1)
    
    def extract_month_year(date_str):
        try:
            date_str = format_iso_timestamp(date_str)
            if not date_str:
                return None
            date_obj = datetime.fromisoformat(date_str)
            return f"{date_obj.year}-{date_obj.month:02d}"
        except (ValueError, TypeError):
            return None
    
    df['Creation Month'] = df['Created Date'].apply(extract_month_year)
    df['Resolution Month'] = df['Resolution Date'].apply(extract_month_year)
    
    # Before writing to CSV, ensure all datetime columns are in consistent string format
    # This prevents parsing issues when the CSV is read back
    date_columns = ['Created Date', 'Resolution Date', 'Applied Date', 'Approval Date']
    for col in date_columns:
        if col in df.columns:
            # Check if column contains datetime objects (not just strings)
            # Convert datetime objects to ISO format strings
            datetime_mask = df[col].apply(
                lambda x: pd.api.types.is_datetime64_any_dtype(type(x)) if pd.notna(x) else False
            )
            if datetime_mask.any():
                # Convert datetime objects to ISO format strings with timezone
                def format_datetime_for_csv(dt):
                    if pd.isna(dt):
                        return None
                    if isinstance(dt, str):
                        return dt  # Already a string, keep as-is
                    # Convert datetime to ISO format string
                    if dt.tzinfo is not None:
                        # Timezone-aware datetime - use isoformat() which handles timezone correctly
                        iso_str = dt.isoformat()
                        # Normalize timezone format (+00:00 is standard ISO format)
                        return iso_str
                    else:
                        # Naive datetime - assume UTC and add timezone
                        iso_str = dt.strftime('%Y-%m-%dT%H:%M:%S.%f')
                        # Remove trailing zeros from microseconds for cleaner format
                        iso_str = iso_str.rstrip('0').rstrip('.')
                        return iso_str + '+00:00'
                
                df.loc[datetime_mask, col] = df.loc[datetime_mask, col].apply(format_datetime_for_csv)
    
    # Final validation: Check for missing Created Date after all processing
    if 'Created Date' in df.columns:
        # Check after date parsing (simulating what analysis script will do)
        try:
            parsed_dates = pd.to_datetime(df['Created Date'], errors='coerce', utc=True)
            final_missing = parsed_dates.isna().sum()
            if final_missing > 0:
                print(f"\n⚠️  FINAL WARNING: After processing, {final_missing} issue(s) will have missing Created Date")
                print(f"   (These values exist but cannot be parsed, or were lost during duplicate merging)")
                if 'Issue' in df.columns:
                    missing_issues = df[parsed_dates.isna()]['Issue'].tolist()
                    if len(missing_issues) <= 10:
                        print(f"   Issues: {', '.join(str(issue) for issue in missing_issues)}")
                    else:
                        print(f"   Sample issues: {', '.join(str(issue) for issue in missing_issues[:10])} ... and {len(missing_issues) - 10} more")
        except Exception as e:
            print(f"\n⚠️  Could not validate final Created Date parsing: {e}")
    
    df.to_csv(output_file, index=False)
    
    return output_file

def main():
    parser = argparse.ArgumentParser(description='Process JIRA issues CSV file and add additional metrics.')
    parser.add_argument('-i', '--input', required=True, help='Input CSV file path')
    parser.add_argument('-o', '--output', help='Output CSV file path (optional)')
    parser.add_argument('-m', '--mapping', default='realm_mappings.csv', 
                        help='Realm mapping file path for lookup and cache (optional, default: realm_mappings.csv)')
    parser.add_argument('--include-realm', action='append',
                        help='Keep only rows whose Realm matches one of these values. '
                             'Repeatable and/or comma-separated. Examples: '
                             '--include-realm "United States,Universal" or --include-realm All. '
                             'Special: Unknown/None to match missing Realm.')
    parser.add_argument('--exclude-realm', action='append',
                        help='Drop rows whose Realm matches one of these values. '
                             'Repeatable and/or comma-separated. '
                             'Special: Unknown/None to match missing Realm.')
    parser.add_argument('--append-missing-realm-stubs', action='store_true',
                        help='Append stub rows (key with blank realm) for any Specifications that '
                             'did not yield a Realm into the mapping CSV (-m/--mapping).')
    parser.add_argument('--dry-run', action='store_true',
                        help='Show what would be merged without actually merging (duplicate detection only)')
    args = parser.parse_args()
    
    # Load CSV
    df = pd.read_csv(args.input)
    initial_count = len(df)
    
    # In dry-run mode, analyze and report on missing Created Date first
    if args.dry_run:
        print(f"\n{'='*80}")
        print(f"DRY-RUN MODE: Data Quality Analysis")
        print(f"{'='*80}")
        print(f"\nLoaded {initial_count} rows from {args.input}")
        
        # Check for missing Created Date
        missing_created_analysis = analyze_missing_created_date(df)
        print_missing_created_date_report(missing_created_analysis)
    
    # Merge duplicates (with dry-run support)
    df = merge_duplicate_issues(df, dry_run=args.dry_run)
    
    if args.dry_run:
        print(f"\nDry-run complete. Original row count: {initial_count}")
        print("No changes made. Re-run without --dry-run to perform the merge and enhancement.")
        return
    
    # Continue with rest of processing...
    include_realms = _parse_realm_cli_values(args.include_realm)
    exclude_realms = _parse_realm_cli_values(args.exclude_realm)
    output_file = process_csv(
        args.input,
        args.output,
        args.mapping,
        df=df,
        include_realms=include_realms,
        exclude_realms=exclude_realms,
        append_missing_realm_stubs=args.append_missing_realm_stubs
    )
    print(f"Processed CSV saved to: {output_file}")

if __name__ == '__main__':
    main()