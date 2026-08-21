#!/usr/bin/env python3
"""
Compare T2-specific dataset with All Year dataset to identify discrepancies
in issue counts for 2025T2 period.
"""

import pandas as pd
import argparse
from datetime import timezone

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

def compare_datasets(t2_csv, all_year_csv, period='2025T2', output_csv=None):
    """Compare two datasets to find discrepancies in period counts"""
    
    print(f"Loading T2-specific dataset: {t2_csv}")
    t2_df = load_and_prepare_data(t2_csv)
    
    print(f"Loading All Year dataset: {all_year_csv}")
    all_year_df = load_and_prepare_data(all_year_csv)
    
    # Parse period dates
    start_date, end_date = parse_time_period(period)
    print(f"\nPeriod: {period}")
    print(f"Start: {start_date}")
    print(f"End: {end_date}\n")
    
    # Create period masks for both datasets
    t2_df['created_in_period'] = (t2_df['Created Date'] >= start_date) & (t2_df['Created Date'] <= end_date)
    t2_df['resolved_in_period'] = t2_df['is_resolved'] & (t2_df['Resolution Date'] >= start_date) & (t2_df['Resolution Date'] <= end_date)
    
    all_year_df['created_in_period'] = (all_year_df['Created Date'] >= start_date) & (all_year_df['Created Date'] <= end_date)
    all_year_df['resolved_in_period'] = all_year_df['is_resolved'] & (all_year_df['Resolution Date'] >= start_date) & (all_year_df['Resolution Date'] <= end_date)
    
    # Count issues in each dataset
    t2_new = t2_df['created_in_period'].sum()
    t2_resolved = t2_df['resolved_in_period'].sum()
    
    all_year_new = all_year_df['created_in_period'].sum()
    all_year_resolved = all_year_df['resolved_in_period'].sum()
    
    print("=" * 80)
    print("SUMMARY COUNTS")
    print("=" * 80)
    print(f"T2 Dataset - New: {t2_new}, Resolved: {t2_resolved}")
    print(f"All Year Dataset - New: {all_year_new}, Resolved: {all_year_resolved}")
    print(f"\nDifference - New: +{all_year_new - t2_new}, Resolved: {all_year_resolved - t2_resolved}")
    print("=" * 80)
    
    # Set Issue as index for easier comparison
    t2_df = t2_df.set_index('Issue')
    all_year_df = all_year_df.set_index('Issue')
    
    # Find issues that exist in both datasets
    common_issues = set(t2_df.index) & set(all_year_df.index)
    t2_only = set(t2_df.index) - set(all_year_df.index)
    all_year_only = set(all_year_df.index) - set(t2_df.index)
    
    print(f"\nIssue Counts:")
    print(f"  T2 dataset only: {len(t2_only)}")
    print(f"  All Year dataset only: {len(all_year_only)}")
    print(f"  Common issues: {len(common_issues)}")
    
    # Track discrepancies
    discrepancies = []
    
    # 1. Issues only in All Year dataset that are new in period
    print("\n" + "=" * 80)
    print("ISSUES ONLY IN ALL YEAR DATASET (New in Period)")
    print("=" * 80)
    if all_year_only:
        all_year_new_issues = all_year_df.loc[list(all_year_only)]
        all_year_new_in_period = all_year_new_issues[all_year_new_issues['created_in_period']]
        print(f"Found {len(all_year_new_in_period)} issues only in All Year dataset that are new in {period}")
        if len(all_year_new_in_period) > 0:
            for issue_key, row in all_year_new_in_period.iterrows():
                discrepancies.append({
                    'Issue': issue_key,
                    'Type': 'New - Only in All Year',
                    'Created Date (All Year)': row['Created Date'],
                    'Resolution Date (All Year)': row['Resolution Date'],
                    'Reporter': row.get('Reporter', 'N/A'),
                    'WG Name': row.get('WG Name', 'N/A'),
                    'Specification': row.get('Specification Display Name', 'N/A'),
                })
                print(f"  {issue_key}: Created {row['Created Date']}, Reporter: {row.get('Reporter', 'N/A')}")
    else:
        print("None")
    
    # 2. Issues only in T2 dataset that are new in period
    print("\n" + "=" * 80)
    print("ISSUES ONLY IN T2 DATASET (New in Period)")
    print("=" * 80)
    if t2_only:
        t2_new_issues = t2_df.loc[list(t2_only)]
        t2_new_in_period = t2_new_issues[t2_new_issues['created_in_period']]
        print(f"Found {len(t2_new_in_period)} issues only in T2 dataset that are new in {period}")
        if len(t2_new_in_period) > 0:
            for issue_key, row in t2_new_in_period.iterrows():
                discrepancies.append({
                    'Issue': issue_key,
                    'Type': 'New - Only in T2',
                    'Created Date (T2)': row['Created Date'],
                    'Resolution Date (T2)': row['Resolution Date'],
                    'Reporter': row.get('Reporter', 'N/A'),
                    'WG Name': row.get('WG Name', 'N/A'),
                    'Specification': row.get('Specification Display Name', 'N/A'),
                })
                print(f"  {issue_key}: Created {row['Created Date']}, Reporter: {row.get('Reporter', 'N/A')}")
    else:
        print("None")
    
    # 3. Compare common issues - check for date changes
    print("\n" + "=" * 80)
    print("COMMON ISSUES WITH DATE CHANGES")
    print("=" * 80)
    
    created_date_changes = []
    resolution_date_changes = []
    period_classification_changes = []
    
    for issue_key in common_issues:
        t2_row = t2_df.loc[issue_key]
        all_year_row = all_year_df.loc[issue_key]
        
        # Check Created Date changes
        t2_created = t2_row['Created Date']
        all_year_created = all_year_row['Created Date']
        
        if pd.notna(t2_created) and pd.notna(all_year_created):
            if t2_created != all_year_created:
                created_date_changes.append({
                    'Issue': issue_key,
                    'Created Date (T2)': t2_created,
                    'Created Date (All Year)': all_year_created,
                    'Difference (days)': (all_year_created - t2_created).total_seconds() / 86400,
                    'Reporter': t2_row.get('Reporter', 'N/A'),
                    'WG Name': t2_row.get('WG Name', 'N/A'),
                })
        
        # Check Resolution Date changes
        t2_resolved = t2_row['Resolution Date']
        all_year_resolved = all_year_row['Resolution Date']
        
        if pd.notna(t2_resolved) and pd.notna(all_year_resolved):
            if t2_resolved != all_year_resolved:
                resolution_date_changes.append({
                    'Issue': issue_key,
                    'Resolution Date (T2)': t2_resolved,
                    'Resolution Date (All Year)': all_year_resolved,
                    'Difference (days)': (all_year_resolved - t2_resolved).total_seconds() / 86400,
                    'Reporter': t2_row.get('Reporter', 'N/A'),
                    'WG Name': t2_row.get('WG Name', 'N/A'),
                })
        elif pd.isna(t2_resolved) != pd.isna(all_year_resolved):
            # One is resolved, one is not
            resolution_date_changes.append({
                'Issue': issue_key,
                'Resolution Date (T2)': t2_resolved if pd.notna(t2_resolved) else 'Not Resolved',
                'Resolution Date (All Year)': all_year_resolved if pd.notna(all_year_resolved) else 'Not Resolved',
                'Difference (days)': 'N/A - Status Changed',
                'Reporter': t2_row.get('Reporter', 'N/A'),
                'WG Name': t2_row.get('WG Name', 'N/A'),
            })
        
        # Check if period classification changed
        t2_new = t2_row['created_in_period']
        all_year_new = all_year_row['created_in_period']
        t2_res = t2_row['resolved_in_period']
        all_year_res = all_year_row['resolved_in_period']
        
        if t2_new != all_year_new or t2_res != all_year_res:
            period_classification_changes.append({
                'Issue': issue_key,
                'New in T2': t2_new,
                'New in All Year': all_year_new,
                'Resolved in T2': t2_res,
                'Resolved in All Year': all_year_res,
                'Created Date (T2)': t2_created,
                'Created Date (All Year)': all_year_created,
                'Resolution Date (T2)': t2_resolved,
                'Resolution Date (All Year)': all_year_resolved,
                'Reporter': t2_row.get('Reporter', 'N/A'),
                'WG Name': t2_row.get('WG Name', 'N/A'),
            })
    
    print(f"\nCreated Date Changes: {len(created_date_changes)}")
    if created_date_changes:
        print("\nTop 20 Created Date Changes:")
        for change in sorted(created_date_changes, key=lambda x: abs(x['Difference (days)']), reverse=True)[:20]:
            print(f"  {change['Issue']}: {change['Created Date (T2)']} → {change['Created Date (All Year)']} "
                  f"({change['Difference (days)']:.1f} days)")
            discrepancies.append({
                'Issue': change['Issue'],
                'Type': 'Created Date Changed',
                'Created Date (T2)': change['Created Date (T2)'],
                'Created Date (All Year)': change['Created Date (All Year)'],
                'Difference (days)': change['Difference (days)'],
                'Reporter': change['Reporter'],
                'WG Name': change['WG Name'],
            })
    
    print(f"\nResolution Date Changes: {len(resolution_date_changes)}")
    if resolution_date_changes:
        print("\nTop 20 Resolution Date Changes:")
        for change in sorted(resolution_date_changes, key=lambda x: abs(x['Difference (days)']) if isinstance(x['Difference (days)'], (int, float)) else 999999, reverse=True)[:20]:
            diff_str = f"{change['Difference (days)']:.1f} days" if isinstance(change['Difference (days)'], (int, float)) else str(change['Difference (days)'])
            print(f"  {change['Issue']}: {change['Resolution Date (T2)']} → {change['Resolution Date (All Year)']} "
                  f"({diff_str})")
            discrepancies.append({
                'Issue': change['Issue'],
                'Type': 'Resolution Date Changed',
                'Resolution Date (T2)': change['Resolution Date (T2)'],
                'Resolution Date (All Year)': change['Resolution Date (All Year)'],
                'Difference (days)': diff_str,
                'Reporter': change['Reporter'],
                'WG Name': change['WG Name'],
            })
    
    print(f"\nPeriod Classification Changes: {len(period_classification_changes)}")
    if period_classification_changes:
        print("\nIssues where period classification changed:")
        for change in period_classification_changes[:30]:
            print(f"  {change['Issue']}: New T2={change['New in T2']}→{change['New in All Year']}, "
                  f"Resolved T2={change['Resolved in T2']}→{change['Resolved in All Year']}")
            discrepancies.append({
                'Issue': change['Issue'],
                'Type': 'Period Classification Changed',
                'New in T2': change['New in T2'],
                'New in All Year': change['New in All Year'],
                'Resolved in T2': change['Resolved in T2'],
                'Resolved in All Year': change['Resolved in All Year'],
                'Created Date (T2)': change['Created Date (T2)'],
                'Created Date (All Year)': change['Created Date (All Year)'],
                'Resolution Date (T2)': change['Resolution Date (T2)'],
                'Resolution Date (All Year)': change['Resolution Date (All Year)'],
                'Reporter': change['Reporter'],
                'WG Name': change['WG Name'],
            })
    
    # Save discrepancies to CSV if requested
    if output_csv and discrepancies:
        discrepancies_df = pd.DataFrame(discrepancies)
        discrepancies_df.to_csv(output_csv, index=False)
        print(f"\nSaved {len(discrepancies)} discrepancies to {output_csv}")
    
    return discrepancies

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Compare T2-specific dataset with All Year dataset to find discrepancies"
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
        help="Output CSV file for discrepancies (optional)"
    )
    
    args = parser.parse_args()
    
    discrepancies = compare_datasets(
        args.t2_csv,
        args.all_year_csv,
        period=args.period,
        output_csv=args.output
    )
    
    print(f"\n\nTotal discrepancies found: {len(discrepancies)}")