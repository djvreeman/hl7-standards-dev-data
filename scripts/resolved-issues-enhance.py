#!/usr/bin/env python3
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

def load_realm_lookup(lookup_file):
    """
    Load realm lookup data from CSV file.
    
    Args:
        lookup_file (str): Path to the lookup CSV file.
    
    Returns:
        dict: Dictionary mapping keys to realms.
    """
    if not lookup_file:
        return {}
    try:
        lookup_df = pd.read_csv(lookup_file)
        if 'key' not in lookup_df.columns or 'realm' not in lookup_df.columns:
            print(f"Warning: Lookup file {lookup_file} is missing 'key' or 'realm' columns")
            return {}
        realm_lookup = dict(zip(lookup_df['key'], lookup_df['realm']))
        print(f"Loaded {len(realm_lookup)} realm mappings from {lookup_file}")
        return realm_lookup
    except Exception as e:
        print(f"Error loading realm lookup file: {e}")
        return {}

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

# --- Cache Helper Functions ---
def load_realm_cache(cache_file='realm_cache.csv'):
    """
    Load the realm cache from a local CSV file (if it exists).
    Supports manual overrides keyed by 'key' and URL mappings keyed by 'url'.
    Returns a tuple: (manual_override, url_mapping) where each is a dict.
    """
    manual_override = {}
    url_mapping = {}
    if os.path.exists(cache_file):
        try:
            df_cache = pd.read_csv(cache_file)
            if 'key' in df_cache.columns:
                for idx, row in df_cache.iterrows():
                    key_val = row.get('key')
                    if pd.notna(key_val) and str(key_val).strip() != "":
                        manual_override[str(key_val).strip()] = str(row.get('realm')).strip() if pd.notna(row.get('realm')) else None
            if 'url' in df_cache.columns:
                for idx, row in df_cache.iterrows():
                    url_val = row.get('url')
                    if pd.notna(url_val) and str(url_val).strip() != "":
                        url_mapping[str(url_val).strip()] = str(row.get('realm')).strip() if pd.notna(row.get('realm')) else None
            return (manual_override, url_mapping)
        except Exception as e:
            print(f"Error loading realm cache from {cache_file}: {e}")
            return ({}, {})
    else:
        return ({}, {})

def save_realm_cache(manual_override, url_mapping, cache_file='realm_cache.csv'):
    """
    Save the realm cache dictionaries to a CSV file with columns 'key', 'url', and 'realm'.
    For manual override entries, 'url' is left blank.
    For URL mappings, 'key' is left blank.
    """
    try:
        rows = []
        for key, realm in manual_override.items():
            rows.append({'key': key, 'url': '', 'realm': realm})
        for url, realm in url_mapping.items():
            rows.append({'key': '', 'url': url, 'realm': realm})
        df_cache = pd.DataFrame(rows, columns=['key', 'url', 'realm'])
        df_cache.to_csv(cache_file, index=False)
    except Exception as e:
        print(f"Error saving realm cache to {cache_file}: {e}")
# --- End Cache Helper Functions ---

# --- Workgroup Lookup Functions ---
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

def process_csv(input_file, output_file=None, lookup_file=None):
    """
    Process a CSV file containing JIRA issues and add additional metrics.
    
    Args:
        input_file (str): Path to the input CSV file.
        output_file (str, optional): Path for the output file. If None, auto-generated.
        lookup_file (str, optional): Path to the realm lookup CSV file. If None, no realm mapping.
    
    Returns:
        str: Path to the enhanced output file.
    """
    if output_file is None:
        directory = os.path.dirname(input_file)
        filename = os.path.basename(input_file)
        base_name, extension = os.path.splitext(filename)
        output_file = os.path.join(directory, f"{base_name}-enhanced{extension}")
    
    df = pd.read_csv(input_file)
    
    # Load realm lookup if provided
    realm_lookup = load_realm_lookup(lookup_file)
    if realm_lookup and 'Specification' in df.columns:
        def get_realm(specification):
            if pd.isna(specification) or not specification:
                return None
            return realm_lookup.get(specification, None)
        df['Realm'] = df['Specification'].apply(get_realm)
        print(f"Added realm information to {df['Realm'].notna().sum()} records")
    
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
            manual_override, url_mapping = load_realm_cache()  # Load manual and URL caches
            failed_urls = set()
            def get_resolved_realm(specification):
                if pd.isna(specification) or not specification:
                    return None
                # Check for manual override based on SPECS.json key
                if specification in manual_override:
                    print(f"Using manual override for spec '{specification}'")
                    return manual_override[specification]
                spec_obj = specs_lookup.get(specification)
                if not spec_obj:
                    return None
                url = spec_obj.get('url')
                if url:
                    # Handle FHIR URL patterns
                    if url.startswith("http://hl7.org/fhir/uv/"):
                        print(f"Detected FHIR UV URL for {url}, returning 'Universal'")
                        return "Universal"
                    elif url.startswith("http://hl7.org/fhir/us/"):
                        print(f"Detected FHIR US URL for {url}, returning 'United States'")
                        return "United States"
                    elif url == "http://hl7.org/fhir":
                        print(f"Detected exact FHIR URL for {url}, returning 'Universal'")
                        return "Universal"
                    # Handle specific CDA URL patterns
                    if url.startswith("http://hl7.org/cda/us/"):
                        print(f"Detected CDA US URL for {url}, returning 'United States'")
                        return "United States"
                    elif url.startswith("http://hl7.org/cda/stds/"):
                        print(f"Detected CDA STDS URL for {url}, returning 'Universal'")
                        return "Universal"
                    # Otherwise, if it's a product brief URL containing '?product_id='
                    elif '?product_id=' in url:
                        if url in url_mapping:
                            print(f"Using cached realm for URL: {url}")
                            return url_mapping[url]
                        else:
                            print(f"Processing URL: {url}")
                            realm_val = extract_realm_from_url(url)
                            if realm_val is not None:
                                url_mapping[url] = realm_val
                                save_realm_cache(manual_override, url_mapping)
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
    
    # Output Specifications with no realm identified
    unresolved_specs = df.loc[df['Resolved Realm'].isna(), 'Specification'].unique()
    if unresolved_specs.size > 0:
        print("The following Specifications did not yield any Realm:")
        for spec in unresolved_specs:
            print(spec)
    
    df.to_csv(output_file, index=False)
    
    return output_file

def main():
    parser = argparse.ArgumentParser(description='Process JIRA issues CSV file and add additional metrics.')
    parser.add_argument('-i', '--input', required=True, help='Input CSV file path')
    parser.add_argument('-o', '--output', help='Output CSV file path (optional)')
    parser.add_argument('-l', '--lookup', help='Realm lookup CSV file path (optional)')
    args = parser.parse_args()
    output_file = process_csv(args.input, args.output, args.lookup)
    print(f"Processed CSV saved to: {output_file}")

if __name__ == '__main__':
    main()