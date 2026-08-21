#!/usr/bin/env python3
"""
Normalize Organization Names in Ballot Participation Data

This script uses Salesforce to create canonical organization names by directly
matching organization names from Jira data to Salesforce Account records. It
identifies name variations (e.g., "Academy of Nutrition & Dietetics" vs 
"Academy of Nutrition and Dietetics") and normalizes them to the canonical 
Salesforce name, preserving historical associations.

USAGE:
    python3 normalize-org-names.py \
        -c data/config/sf-config.yaml \
        -i ballot_participation.csv \
        -o ballot_participation_normalized.csv \
        --mapping org-mapping.csv

ARGUMENTS:
    -c / --config    Path to Salesforce YAML config file (required)
    -i / --input     Path to input ballot participation CSV (required)
    -o / --output    Path to output normalized CSV (required)
    --mapping        Optional path to save org name mapping CSV
    --threshold      Fuzzy matching threshold (0-100, default: 85)
    --limit          Max number of SF Accounts to fetch for matching (default: 10000)
"""

import argparse
import pandas as pd
import requests
import yaml
import urllib.parse
import csv
import os
from collections import defaultdict
from fuzzywuzzy import fuzz, process
import re


def load_config(path):
    """Load configuration from YAML file."""
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def get_access_token(config):
    """Get Salesforce access token."""
    url = f"{config['prod_server']}/services/oauth2/token"
    params = {
        'grant_type': 'password',
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'username': config['username'],
        'password': config['password']
    }
    response = requests.post(url, data=params)
    response.raise_for_status()
    return response.json()['access_token']


def query_salesforce(config, access_token, query):
    """Execute a SOQL query."""
    encoded_query = urllib.parse.quote(query, safe='')
    url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_query}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    all_records = []
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        all_records.extend(result.get('records', []))
        url = result.get('nextRecordsUrl')
        if url:
            url = f"{config['prod_server']}{url}"
    
    return all_records


def fetch_all_accounts(config, access_token, limit=10000):
    """
    Fetch all Account records from Salesforce (or up to limit).
    Returns list of Account records with Id and Name.
    """
    query = f"SELECT Id, Name FROM Account ORDER BY Name LIMIT {limit}"
    return query_salesforce(config, access_token, query)


def normalize_org_name(name):
    """
    Normalize organization name for comparison.
    - Convert to lowercase
    - Remove extra whitespace
    - Normalize common punctuation variations
    - Remove common stop words that don't help matching
    """
    if pd.isna(name) or not name:
        return ""
    
    normalized = str(name).strip().lower()
    
    # Normalize common punctuation variations
    normalized = re.sub(r'\s+', ' ', normalized)  # Multiple spaces to single
    normalized = normalized.replace('&', 'and')  # & to and
    normalized = normalized.replace('+', 'and')  # + to and
    normalized = normalized.replace('.', '')     # Remove periods
    normalized = normalized.replace(',', '')     # Remove commas
    normalized = normalized.replace("'", '')     # Remove apostrophes
    normalized = normalized.replace('"', '')     # Remove quotes
    normalized = normalized.replace('-', ' ')    # Replace hyphens with spaces
    normalized = normalized.replace('(', ' ')     # Replace parens with spaces
    normalized = normalized.replace(')', ' ')
    
    # Remove common words that don't help matching (but keep them for very short orgs)
    # Only remove if org name is long enough
    if len(normalized.split()) > 2:
        stop_words = {'the', 'of', 'for', 'and', 'or', 'inc', 'llc', 'corp', 'corporation', 
                     'ltd', 'limited', 'co', 'company', 'association', 'assoc', 'institute', 
                     'inst', 'national', 'nat', 'international', 'intl'}
        words = normalized.split()
        words = [w for w in words if w not in stop_words]
        normalized = ' '.join(words)
    
    return normalized.strip()


def find_best_match(jira_org, sf_accounts, threshold=85):
    """
    Find the best matching Salesforce Account for a Jira organization name.
    Uses weighted scoring to prioritize token-based matches over substring matches.
    Returns (best_match_account, match_score) or (None, 0) if no match above threshold.
    """
    if not jira_org or not sf_accounts:
        return (None, 0)
    
    jira_norm = normalize_org_name(jira_org)
    jira_words = set(jira_norm.split())
    
    # Try exact match first (case-insensitive, normalized)
    for acc in sf_accounts:
        sf_norm = normalize_org_name(acc['Name'])
        if jira_norm == sf_norm:
            return (acc, 100)
    
    # Use weighted fuzzy matching to find best match
    # Prioritize token-based matches over substring matches
    best_match = None
    best_score = 0
    
    for acc in sf_accounts:
        sf_name = acc['Name']
        sf_norm = normalize_org_name(sf_name)
        sf_words = set(sf_norm.split())
        
        # Calculate multiple similarity scores
        ratio = fuzz.ratio(jira_norm, sf_norm)
        token_sort_ratio = fuzz.token_sort_ratio(jira_norm, sf_norm)
        token_set_ratio = fuzz.token_set_ratio(jira_norm, sf_norm)
        
        # Calculate word overlap (how many words match)
        word_overlap = len(jira_words.intersection(sf_words))
        total_words = len(jira_words.union(sf_words))
        word_overlap_ratio = (word_overlap / total_words * 100) if total_words > 0 else 0
        
        # Weighted scoring:
        # - token_sort_ratio: Best for word order differences (weight: 0.4)
        # - token_set_ratio: Good for partial word matches (weight: 0.3)
        # - word_overlap_ratio: Ensures significant word overlap (weight: 0.2)
        # - ratio: Character-level similarity (weight: 0.1)
        # - partial_ratio: Only used if other scores are high (penalized)
        
        # Base score from token-based matching
        weighted_score = (
            token_sort_ratio * 0.4 +
            token_set_ratio * 0.3 +
            word_overlap_ratio * 0.2 +
            ratio * 0.1
        )
        
        # Penalize if partial_ratio is much higher than other scores (indicates substring match)
        partial_ratio = fuzz.partial_ratio(jira_norm, sf_norm)
        if partial_ratio > weighted_score + 20:  # Partial ratio is suspiciously high
            # This is likely a substring match - heavily penalize
            weighted_score = weighted_score * 0.5
        
        # Require minimum word overlap for short org names
        # If org name has 3+ words, require at least 2 words to match
        if len(jira_words) >= 3 and word_overlap < 2:
            weighted_score = weighted_score * 0.7  # Penalize low word overlap
        
        # Require minimum length similarity to avoid very short substring matches
        length_diff = abs(len(jira_norm) - len(sf_norm))
        length_ratio = min(len(jira_norm), len(sf_norm)) / max(len(jira_norm), len(sf_norm)) if max(len(jira_norm), len(sf_norm)) > 0 else 0
        if length_ratio < 0.5:  # Lengths are very different
            weighted_score = weighted_score * 0.8  # Penalize length mismatch
        
        if weighted_score > best_score:
            best_score = weighted_score
            best_match = acc
    
    # Only return if above threshold
    if best_score >= threshold:
        return (best_match, best_score)
    else:
        return (None, 0)


def load_manual_mapping(mapping_file):
    """
    Load manual overrides from an existing mapping CSV file.
    Returns dict mapping jira_org -> canonical_info
    Only loads entries that have a canonical org set (not empty/No Match status)
    """
    if not mapping_file or not os.path.exists(mapping_file):
        return {}
    
    try:
        df = pd.read_csv(mapping_file)
        manual_mapping = {}
        
        # Check for required columns
        if 'Jira_Organization' not in df.columns or 'Canonical_Organization' not in df.columns:
            print(f"⚠️  Mapping file missing required columns, skipping manual overrides")
            return {}
        
        for _, row in df.iterrows():
            jira_org = str(row['Jira_Organization']).strip()
            canonical_org = str(row['Canonical_Organization']).strip()
            status = str(row.get('Status', '')).strip() if 'Status' in row else ''
            
            # Only load entries that have a valid canonical org (not empty, not "No Match" status)
            if jira_org and canonical_org and canonical_org != jira_org and status != 'No Match':
                manual_mapping[jira_org] = {
                    'canonical_org': canonical_org,
                    'match_score': row.get('Match_Score', 100) if 'Match_Score' in row else 100,
                    'sf_account_id': str(row.get('SF_Account_ID', '')) if 'SF_Account_ID' in row else '',
                    'status': 'Manual Override' if status != 'Matched' else 'Matched'
                }
        
        print(f"✅ Loaded {len(manual_mapping)} manual overrides from {mapping_file}")
        return manual_mapping
    except Exception as e:
        print(f"⚠️  Error loading manual mapping file: {e}")
        return {}


def create_org_mapping(jira_orgs, sf_accounts, threshold=85, manual_overrides=None, include_all=True):
    """
    Create mapping from Jira organization names to canonical Salesforce names.
    
    Args:
        jira_orgs: List of unique organization names from Jira data
        sf_accounts: List of Salesforce Account records
        threshold: Fuzzy matching threshold
        manual_overrides: Dict of manual overrides (from previous mapping file)
        include_all: If True, include all orgs even if no match found
    
    Returns:
        Dict mapping jira_org -> {'canonical_org': sf_name, 'match_score': score, 'sf_account_id': id, 'status': status}
    """
    org_mapping = {}
    
    # Start with manual overrides
    if manual_overrides:
        org_mapping.update(manual_overrides)
        print(f"  Using {len(manual_overrides)} manual overrides")
    
    print(f"  Matching {len(jira_orgs)} unique organizations...")
    
    matched_count = 0
    no_match_count = 0
    
    for i, jira_org in enumerate(jira_orgs, 1):
        jira_org_str = str(jira_org).strip()
        
        if pd.isna(jira_org) or not jira_org_str:
            continue
        
        # Skip if we already have a manual override
        if jira_org_str in org_mapping:
            continue
        
        if i % 100 == 0:
            print(f"    Processed {i}/{len(jira_orgs)}... (matched: {matched_count}, no match: {no_match_count})")
        
        best_match, match_score = find_best_match(jira_org_str, sf_accounts, threshold)
        
        if best_match:
            org_mapping[jira_org_str] = {
                'canonical_org': best_match['Name'],
                'match_score': match_score,
                'sf_account_id': best_match['Id'],
                'status': 'Matched'
            }
            matched_count += 1
        elif include_all:
            # Include even if no match found (for manual review)
            org_mapping[jira_org_str] = {
                'canonical_org': jira_org_str,  # Keep original if no match
                'match_score': 0,
                'sf_account_id': '',
                'status': 'No Match'
            }
            no_match_count += 1
    
    print(f"    Final: matched: {matched_count}, no match: {no_match_count}")
    
    return org_mapping


def apply_org_mapping(df, org_mapping):
    """
    Apply organization mapping to ballot data.
    
    Args:
        df: DataFrame with ballot participation data
        org_mapping: Dict mapping jira_org -> canonical info
    
    Returns:
        DataFrame with added 'Organization_Canonical' column
    """
    df = df.copy()
    
    # Initialize canonical org column
    df['Organization_Canonical'] = df['Organization'].copy()
    
    # Apply mappings (only for matched entries, keep original for "No Match")
    for idx, row in df.iterrows():
        jira_org = row.get('Organization')
        
        if pd.isna(jira_org):
            continue
        
        jira_org_str = str(jira_org).strip()
        if jira_org_str in org_mapping:
            mapping_info = org_mapping[jira_org_str]
            # Only apply if it's a match (not "No Match" status)
            if mapping_info.get('status') == 'Matched' or mapping_info.get('status') == 'Manual Override':
                df.at[idx, 'Organization_Canonical'] = mapping_info['canonical_org']
            # For "No Match", keep original (already set above)
    
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Normalize organization names using Salesforce canonical names"
    )
    parser.add_argument(
        '-c', '--config',
        required=True,
        help='Path to Salesforce YAML config file'
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to input ballot participation CSV'
    )
    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Path to output normalized CSV'
    )
    parser.add_argument(
        '--mapping',
        help='Optional path to save org name mapping CSV'
    )
    parser.add_argument(
        '--threshold',
        type=int,
        default=85,
        help='Fuzzy matching threshold (0-100, default: 85)'
    )
    parser.add_argument(
        '--limit',
        type=int,
        default=10000,
        help='Max number of SF Accounts to fetch (default: 10000)'
    )
    parser.add_argument(
        '--use-existing-mapping',
        action='store_true',
        help='Load and use existing mapping file as manual overrides (prevents re-matching)'
    )
    
    args = parser.parse_args()
    
    # Load config
    print(f"Loading configuration from {args.config}...")
    try:
        config = load_config(args.config)
        print("✅ Config loaded")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return
    
    # Get access token
    print("🔑 Getting access token...")
    try:
        access_token = get_access_token(config)
        print("✅ Access token obtained")
    except Exception as e:
        print(f"❌ Error getting access token: {e}")
        return
    
    # Load ballot data
    print(f"\n📂 Loading ballot data from {args.input}...")
    try:
        df = pd.read_csv(args.input, quoting=csv.QUOTE_MINIMAL, doublequote=True)
        df.columns = df.columns.str.strip()
        print(f"✅ Loaded {len(df)} records")
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
        return
    
    # Check required columns
    if 'Organization' not in df.columns:
        print(f"❌ Missing required column: Organization")
        return
    
    # Extract unique organizations from ballot data
    print(f"\n🔍 Extracting unique organizations from ballot data...")
    unique_orgs = df['Organization'].dropna().unique()
    unique_orgs = [str(org).strip() for org in unique_orgs if str(org).strip()]
    print(f"✅ Found {len(unique_orgs)} unique organizations")
    
    # Fetch all Salesforce Accounts
    print(f"\n🔍 Fetching Salesforce Accounts (limit: {args.limit})...")
    try:
        sf_accounts = fetch_all_accounts(config, access_token, args.limit)
        print(f"✅ Fetched {len(sf_accounts)} Salesforce Accounts")
    except Exception as e:
        print(f"❌ Error fetching Salesforce Accounts: {e}")
        return
    
    # Load manual overrides if requested
    manual_overrides = {}
    if args.use_existing_mapping and args.mapping and os.path.exists(args.mapping):
        manual_overrides = load_manual_mapping(args.mapping)
    
    # Create organization mapping
    print(f"\n🔄 Creating organization mapping (threshold: {args.threshold})...")
    org_mapping = create_org_mapping(unique_orgs, sf_accounts, args.threshold, manual_overrides, include_all=True)
    
    print(f"✅ Created {len(org_mapping)} organization mappings")
    
    # Show sample mappings
    if org_mapping:
        matched_mappings = {k: v for k, v in org_mapping.items() if v.get('status') == 'Matched'}
        no_match_mappings = {k: v for k, v in org_mapping.items() if v.get('status') == 'No Match'}
        
        print(f"\n📋 Sample mappings:")
        if matched_mappings:
            print(f"  Matched ({len(matched_mappings)}):")
            for jira_org, mapping_info in list(matched_mappings.items())[:5]:
                print(f"    '{jira_org}' → '{mapping_info['canonical_org']}' "
                      f"(score: {mapping_info['match_score']:.1f}%)")
            if len(matched_mappings) > 5:
                print(f"    ... and {len(matched_mappings) - 5} more matches")
        
        if no_match_mappings:
            print(f"  No Match ({len(no_match_mappings)}):")
            for jira_org in list(no_match_mappings.keys())[:5]:
                print(f"    '{jira_org}' (needs manual review)")
            if len(no_match_mappings) > 5:
                print(f"    ... and {len(no_match_mappings) - 5} more")
    
    # Apply mapping to ballot data
    print(f"\n🔄 Applying organization mapping to ballot data...")
    df_normalized = apply_org_mapping(df, org_mapping)
    
    # Count how many records were normalized
    normalized_count = 0
    for idx, row in df.iterrows():
        original_org = row.get('Organization')
        canonical_org = df_normalized.at[idx, 'Organization_Canonical']
        if pd.notna(original_org) and pd.notna(canonical_org) and str(original_org) != str(canonical_org):
            normalized_count += 1
    
    print(f"✅ Normalized {normalized_count} records")
    
    # Save normalized CSV
    print(f"\n💾 Saving normalized data to {args.output}...")
    try:
        df_normalized.to_csv(args.output, index=False, quoting=csv.QUOTE_MINIMAL, doublequote=True)
        print("✅ Normalized CSV saved")
    except Exception as e:
        print(f"❌ Error saving CSV: {e}")
        return
    
    # Save mapping file if requested
    if args.mapping:
        print(f"\n💾 Saving organization mapping to {args.mapping}...")
        try:
            mapping_rows = []
            for jira_org, mapping_info in org_mapping.items():
                mapping_rows.append({
                    'Jira_Organization': jira_org,
                    'Canonical_Organization': mapping_info['canonical_org'],
                    'Match_Score': mapping_info['match_score'],
                    'SF_Account_ID': mapping_info.get('sf_account_id', ''),
                    'Status': mapping_info.get('status', 'Unknown')
                })
            
            if mapping_rows:
                mapping_df = pd.DataFrame(mapping_rows)
                mapping_df = mapping_df.sort_values('Jira_Organization')
                mapping_df.to_csv(args.mapping, index=False)
                print(f"✅ Mapping file saved ({len(mapping_rows)} mappings)")
            else:
                print("⚠️  No mappings to save")
        except Exception as e:
            print(f"⚠️  Error saving mapping file: {e}")
    
    # Summary statistics
    print(f"\n📊 Summary:")
    print(f"  Total records: {len(df_normalized)}")
    print(f"  Records normalized: {normalized_count}")
    
    # Count unique organizations
    original_orgs = df['Organization'].dropna().nunique()
    canonical_orgs = df_normalized['Organization_Canonical'].dropna().nunique()
    print(f"  Unique organizations (original): {original_orgs}")
    print(f"  Unique organizations (canonical): {canonical_orgs}")
    if original_orgs > canonical_orgs:
        print(f"  ✅ Reduced from {original_orgs} to {canonical_orgs} unique organizations")
    
    print("\n✅ Done!")


if __name__ == '__main__':
    main()
