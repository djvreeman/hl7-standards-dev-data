#!/usr/bin/env python3
"""
Manually Update Organization Mapping

This script helps you manually correct organization mappings in the mapping CSV file.
You can add, update, or remove mappings.

USAGE:
    # Add/update a mapping
    python3 update-org-mapping.py \
        --mapping org-mapping.csv \
        --jira-org "Microsoft Corporation" \
        --canonical-org "Microsoft" \
        --score 100

    # Set Status (e.g. flip a stale 'No Match' to 'Manual Override' so the
    # mapping is actually applied by apply-org-mapping.py)
    python3 update-org-mapping.py \
        --mapping org-mapping.csv \
        --jira-org "ACP" \
        --status "Manual Override"

    # Remove a mapping (set canonical to empty)
    python3 update-org-mapping.py \
        --mapping org-mapping.csv \
        --jira-org "Microsoft Corporation" \
        --canonical-org ""

    # Show current mapping for an org
    python3 update-org-mapping.py \
        --mapping org-mapping.csv \
        --jira-org "Microsoft Corporation" \
        --show

NOTE on Status:
    apply-org-mapping.py SKIPS any mapping whose Status='No Match'. Common
    valid values you can set with --status: 'Manual Override' (forces the
    mapping to be applied) or 'Matched' (used for SF-derived mappings).
"""

import argparse
import pandas as pd
import os


def load_mapping(mapping_file):
    """Load existing mapping file."""
    if not os.path.exists(mapping_file):
        # Create new file with headers
        df = pd.DataFrame(
            columns=['Jira_Organization', 'Canonical_Organization', 'Match_Score', 'SF_Account_ID', 'Status']
        )
        return df

    df = pd.read_csv(mapping_file)
    if 'Status' not in df.columns:
        df['Status'] = ''
    return df


def save_mapping(df, mapping_file):
    """Save mapping to CSV file."""
    df = df.sort_values('Jira_Organization')
    df.to_csv(mapping_file, index=False)


def update_mapping(mapping_file, jira_org, canonical_org=None, score=None, sf_account_id=None, status=None, show_only=False):
    """Update or show a mapping entry."""
    df = load_mapping(mapping_file)

    # Find existing entry
    mask = df['Jira_Organization'] == jira_org
    exists = mask.any()

    if show_only:
        if exists:
            row = df[mask].iloc[0]
            print(f"\nCurrent mapping for '{jira_org}':")
            print(f"  Canonical Organization: {row.get('Canonical_Organization', 'N/A')}")
            print(f"  Match Score: {row.get('Match_Score', 'N/A')}")
            print(f"  SF Account ID: {row.get('SF_Account_ID', 'N/A')}")
            print(f"  Status: {row.get('Status', 'N/A')}")
        else:
            print(f"\nNo mapping found for '{jira_org}'")
        return

    # Update or add entry
    if canonical_org == "":
        # Remove mapping
        if exists:
            df = df[~mask]
            print(f"✅ Removed mapping for '{jira_org}'")
        else:
            print(f"⚠️  No mapping found for '{jira_org}' to remove")
    elif canonical_org is None and status is not None and exists:
        # Status-only update (no canonical change)
        idx = df[mask].index[0]
        old_status = df.at[idx, 'Status']
        df.at[idx, 'Status'] = status
        print(f"✅ Updated Status for '{jira_org}': '{old_status}' → '{status}'")
    else:
        # Add or update mapping
        if canonical_org is None:
            print(f"⚠️  No canonical-org provided and no row to update Status on for '{jira_org}'")
            return
        if exists:
            # Update existing
            idx = df[mask].index[0]
            df.at[idx, 'Canonical_Organization'] = canonical_org
            if score is not None:
                df.at[idx, 'Match_Score'] = score
            if sf_account_id is not None:
                df.at[idx, 'SF_Account_ID'] = sf_account_id
            if status is not None:
                df.at[idx, 'Status'] = status
            print(f"✅ Updated mapping for '{jira_org}' → '{canonical_org}'"
                  + (f" (Status: '{status}')" if status is not None else ""))
        else:
            # Add new
            new_row = {
                'Jira_Organization': jira_org,
                'Canonical_Organization': canonical_org,
                'Match_Score': score if score is not None else 100,
                'SF_Account_ID': sf_account_id if sf_account_id is not None else '',
                'Status': status if status is not None else 'Manual Override'
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            print(f"✅ Added mapping for '{jira_org}' → '{canonical_org}'"
                  f" (Status: '{new_row['Status']}')")

    # Save
    save_mapping(df, mapping_file)
    print(f"💾 Saved to {mapping_file}")


def bulk_update_from_file(mapping_file, updates_file):
    """Bulk update mappings from a CSV file with columns: Jira_Organization, Canonical_Organization, Match_Score, SF_Account_ID"""
    df_mapping = load_mapping(mapping_file)
    df_updates = pd.read_csv(updates_file)
    
    required_cols = ['Jira_Organization', 'Canonical_Organization']
    missing_cols = [col for col in required_cols if col not in df_updates.columns]
    if missing_cols:
        print(f"❌ Updates file missing required columns: {', '.join(missing_cols)}")
        return
    
    updated_count = 0
    added_count = 0
    
    for _, update_row in df_updates.iterrows():
        jira_org = str(update_row['Jira_Organization']).strip()
        canonical_org = str(update_row['Canonical_Organization']).strip()

        if not jira_org:
            continue

        mask = df_mapping['Jira_Organization'] == jira_org

        if mask.any():
            # Update existing
            idx = df_mapping[mask].index[0]
            df_mapping.at[idx, 'Canonical_Organization'] = canonical_org
            if 'Match_Score' in update_row:
                df_mapping.at[idx, 'Match_Score'] = update_row['Match_Score']
            if 'SF_Account_ID' in update_row:
                df_mapping.at[idx, 'SF_Account_ID'] = update_row['SF_Account_ID']
            if 'Status' in update_row:
                df_mapping.at[idx, 'Status'] = update_row['Status']
            updated_count += 1
        else:
            # Add new
            new_row = {
                'Jira_Organization': jira_org,
                'Canonical_Organization': canonical_org,
                'Match_Score': update_row.get('Match_Score', 100),
                'SF_Account_ID': update_row.get('SF_Account_ID', ''),
                'Status': update_row.get('Status', 'Manual Override'),
            }
            df_mapping = pd.concat([df_mapping, pd.DataFrame([new_row])], ignore_index=True)
            added_count += 1
    
    save_mapping(df_mapping, mapping_file)
    print(f"✅ Updated {updated_count} mappings, added {added_count} new mappings")
    print(f"💾 Saved to {mapping_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Manually update organization mapping file"
    )
    parser.add_argument(
        '--mapping',
        required=True,
        help='Path to mapping CSV file'
    )
    parser.add_argument(
        '--jira-org',
        help='Jira organization name to update'
    )
    parser.add_argument(
        '--canonical-org',
        help='Canonical organization name (use "" to remove mapping)'
    )
    parser.add_argument(
        '--score',
        type=int,
        help='Match score (0-100, default: 100)'
    )
    parser.add_argument(
        '--sf-account-id',
        help='Salesforce Account ID'
    )
    parser.add_argument(
        '--status',
        help="Status field value (e.g. 'Manual Override', 'Matched'). "
             "Note: apply-org-mapping.py SKIPS rows whose Status='No Match'."
    )
    parser.add_argument(
        '--show',
        action='store_true',
        help='Show current mapping for jira-org (don\'t update)'
    )
    parser.add_argument(
        '--bulk-update',
        help='Bulk update from CSV file with columns: Jira_Organization, Canonical_Organization, Match_Score, SF_Account_ID'
    )
    
    args = parser.parse_args()
    
    if args.bulk_update:
        bulk_update_from_file(args.mapping, args.bulk_update)
    elif args.jira_org:
        update_mapping(
            mapping_file=args.mapping,
            jira_org=args.jira_org,
            canonical_org=args.canonical_org,
            score=args.score,
            sf_account_id=args.sf_account_id,
            status=args.status,
            show_only=args.show,
        )
    else:
        parser.error("Must specify --jira-org or --bulk-update")


if __name__ == '__main__':
    main()
