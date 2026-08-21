#!/usr/bin/env python3
"""
Apply Organization Mapping (and optional Balloter Overrides) to Ballot Participation Data

This script applies an existing organization-name mapping CSV to ballot
participation data and, by default, also merges any per-BALLOT-ID overrides
from ``balloter-overrides.csv`` so the entire normalization runs in a single
step. Output is one CSV: mapped + overridden.

USAGE:
    # Mapping + overrides (overrides auto-applied when balloter-overrides.csv
    # is present beside -m, or when --overrides PATH is supplied)
    python3 apply-org-mapping.py \\
        -i ballot_participation.csv \\
        -m org-mapping.csv \\
        -o ballot_participation_normalized.csv

    # Mapping only (skip overrides even if default file exists)
    python3 apply-org-mapping.py -i ... -m ... -o ... --no-overrides

    # Specify a different overrides file explicitly
    python3 apply-org-mapping.py -i ... -m ... -o ... --overrides path/to/overrides.csv
"""

import argparse
import pandas as pd
import csv
import importlib.util
import os
import sys


def _load_overrides_module():
    """Load apply-balloter-overrides.py as a module despite the hyphenated filename."""
    here = os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(here, "apply-balloter-overrides.py")
    spec = importlib.util.spec_from_file_location("apply_balloter_overrides", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load module at {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_overrides_mod = _load_overrides_module()


def load_mapping(mapping_file):
    """Load organization mapping from CSV file."""
    if not os.path.exists(mapping_file):
        print(f"❌ Mapping file not found: {mapping_file}")
        return {}
    
    try:
        df = pd.read_csv(mapping_file)
        
        if 'Jira_Organization' not in df.columns or 'Canonical_Organization' not in df.columns:
            print(f"❌ Mapping file missing required columns: Jira_Organization, Canonical_Organization")
            return {}
        
        org_mapping = {}
        for _, row in df.iterrows():
            jira_org = str(row['Jira_Organization']).strip()
            canonical_org = str(row['Canonical_Organization']).strip()
            status = str(row.get('Status', '')).strip() if 'Status' in row else ''
            
            # Only include entries with valid canonical orgs (not empty, not "No Match")
            if jira_org and canonical_org and canonical_org != jira_org and status != 'No Match':
                org_mapping[jira_org] = canonical_org
        
        print(f"✅ Loaded {len(org_mapping)} organization mappings from {mapping_file}")
        return org_mapping
    except Exception as e:
        print(f"❌ Error loading mapping file: {e}")
        return {}


def apply_mapping(df, org_mapping):
    """Apply organization mapping to ballot data."""
    df = df.copy()
    
    # Initialize canonical org column
    df['Organization_Canonical'] = df['Organization'].copy()
    
    # Apply mappings
    applied_count = 0
    for idx, row in df.iterrows():
        jira_org = row.get('Organization')
        
        if pd.isna(jira_org):
            continue
        
        jira_org_str = str(jira_org).strip()
        if jira_org_str in org_mapping:
            df.at[idx, 'Organization_Canonical'] = org_mapping[jira_org_str]
            applied_count += 1
    
    return df, applied_count


def main():
    parser = argparse.ArgumentParser(
        description="Apply organization mapping to ballot participation data"
    )
    parser.add_argument(
        '-i', '--input',
        required=True,
        help='Path to input ballot participation CSV'
    )
    parser.add_argument(
        '-m', '--mapping',
        required=True,
        help='Path to organization mapping CSV file'
    )
    parser.add_argument(
        '-o', '--output',
        required=True,
        help='Path to output normalized CSV'
    )
    parser.add_argument(
        '--overrides',
        default=None,
        help='Path to balloter-overrides.csv to merge after mapping. '
             'If omitted, looks for "balloter-overrides.csv" beside -m.'
    )
    parser.add_argument(
        '--no-overrides',
        action='store_true',
        help='Skip the balloter-overrides merge even if a default file exists.'
    )
    parser.add_argument(
        '--strict',
        action='store_true',
        help='Forwarded to override merge: error on conflicts (override differs '
             'from existing non-empty value).'
    )
    
    args = parser.parse_args()
    
    # Load ballot data
    print(f"📂 Loading ballot data from {args.input}...")
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
    
    # Load mapping
    print(f"\n📋 Loading organization mapping...")
    org_mapping = load_mapping(args.mapping)
    
    if not org_mapping:
        print(f"⚠️  No mappings loaded. Output will be identical to input.")
    
    # Apply mapping
    print(f"\n🔄 Applying organization mapping...")
    df_normalized, applied_count = apply_mapping(df, org_mapping)
    
    print(f"✅ Applied {applied_count} organization mappings")

    # Merge per-BALLOT-ID balloter overrides (one-step normalization)
    overrides_path = None
    if not args.no_overrides:
        if args.overrides:
            overrides_path = args.overrides
            if not os.path.exists(overrides_path):
                print(f"❌ --overrides path does not exist: {overrides_path}")
                return
        else:
            overrides_path = _overrides_mod.resolve_default_overrides_path(args.mapping)

    if overrides_path:
        print(f"\n📋 Merging balloter overrides from {overrides_path}...")
        try:
            df_overrides = _overrides_mod.load_overrides(overrides_path)
        except Exception as e:
            print(f"❌ Error loading overrides CSV: {e}")
            return
        total_rows, with_id = _overrides_mod.count_override_rows(df_overrides)
        print(f"✅ Overrides file: {total_rows} data row(s), {with_id} row(s) with a BALLOT ID.")
        if total_rows == 0:
            print(
                "\nℹ️  No data rows in overrides file — merge is a no-op. Edits saved only in "
                "missing-orgs-audit-*.csv are not applied. Copy curated rows into "
                "balloter-overrides.csv (same directory as org-mapping), or pass e.g.\n"
                "    --overrides path/to/your-audit-or-overrides.csv"
            )
        elif with_id == 0:
            print(
                "\n⚠️  Overrides file has rows but no usable BALLOT ID — merge will do nothing. "
                "Format the BALLOT ID column as text in Excel, or use values like BALLOT-18632 "
                "(plain numbers are auto-prefixed when possible)."
            )

        try:
            df_normalized, ov_summary = _overrides_mod.apply_overrides(
                df_normalized, df_overrides, strict=args.strict
            )
        except ValueError as e:
            print(f"❌ {e}")
            sys.exit(2)
        _overrides_mod.print_summary(ov_summary, skip_file_row_count=True)
    else:
        if args.no_overrides:
            print("\nℹ️  Skipping balloter overrides merge (--no-overrides)")
        else:
            print(f"\nℹ️  No balloter-overrides.csv found beside {args.mapping}; "
                  f"skipping overrides merge. Use --overrides PATH to specify one.")

    # Save normalized CSV
    print(f"\n💾 Saving normalized data to {args.output}...")
    try:
        df_normalized.to_csv(args.output, index=False, quoting=csv.QUOTE_MINIMAL, doublequote=True)
        print("✅ Normalized CSV saved")
    except Exception as e:
        print(f"❌ Error saving CSV: {e}")
        return
    
    # Summary statistics
    print(f"\n📊 Summary:")
    print(f"  Total records: {len(df_normalized)}")
    print(f"  Records normalized: {applied_count}")
    
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
