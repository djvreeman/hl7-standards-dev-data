#!/usr/bin/env python3
"""
Deep dive analysis for esilver's ballot participation streak and enrollment.
This script provides detailed cycle-by-cycle analysis to verify streak calculations.
"""

import pandas as pd
import csv
import re
from datetime import datetime

def parse_ballot_period(period_str):
    """Parse Ballot Period from format like "2026-Jan" or "2025-Sep" to YYYYMM format."""
    if pd.isna(period_str) or not period_str:
        return None
    
    match = re.match(r'^(\d{4})-([A-Za-z]{3})', str(period_str))
    if match:
        year = int(match.group(1))
        month_abbr = match.group(2).capitalize()
        
        month_map = {
            'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5, 'Jun': 6,
            'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10, 'Nov': 11, 'Dec': 12
        }
        
        if month_abbr in month_map:
            month_num = month_map[month_abbr]
            yyyymm_str = f"{year}{month_num:02d}"
            return (year, month_num, yyyymm_str)
    
    return None

def extract_timestamp_from_filename(filename):
    """Extract timestamp from filename like 'baldef_data-20260115-143022.csv'"""
    match = re.search(r'(\d{8})-(\d{6})', filename)
    if match:
        date_str = match.group(1)
        time_str = match.group(2)
        try:
            year = int(date_str[:4])
            month = int(date_str[4:6])
            day = int(date_str[6:8])
            hour = int(time_str[:2])
            minute = int(time_str[2:4])
            second = int(time_str[4:6])
            return pd.Timestamp(year=year, month=month, day=day, hour=hour, minute=minute, second=second, tz='UTC')
        except (ValueError, IndexError):
            pass
    return None

def analyze_esilver(baldef_csv, ballot_csv):
    """Perform deep dive analysis for esilver"""
    
    print("=" * 80)
    print("DEEP DIVE ANALYSIS: esilver Ballot Participation")
    print("=" * 80)
    print()
    
    # Load data
    print("Loading data...")
    try:
        baldef_df = pd.read_csv(
            baldef_csv,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True
        )
        ballot_df = pd.read_csv(
            ballot_csv,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True
        )
    except Exception as e:
        print(f"Error loading CSV files: {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Clean column names
    baldef_df.columns = baldef_df.columns.str.strip()
    ballot_df.columns = ballot_df.columns.str.strip()
    
    # Extract data gathering date from filename
    data_gathering_date = extract_timestamp_from_filename(baldef_csv)
    if data_gathering_date:
        print(f"Data gathering date: {data_gathering_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    else:
        print("Warning: Could not determine data gathering date from filename")
    
    # Parse Ballot Period to YYYYMM format
    baldef_df['Ballot Cycle'] = baldef_df['Ballot Period'].apply(
        lambda x: parse_ballot_period(x)[2] if parse_ballot_period(x) else None
    )
    
    # Filter to only include ballots from January 2022 onwards
    baldef_df = baldef_df[
        (baldef_df['Ballot Cycle'].notna()) & 
        (baldef_df['Ballot Cycle'] >= '202201')
    ].copy()
    
    # Parse dates
    baldef_df['Ballot Open Date'] = pd.to_datetime(baldef_df['Ballot Open Date'], errors='coerce', utc=True)
    baldef_df['Ballot Close Date'] = pd.to_datetime(baldef_df['Ballot Close Date'], errors='coerce', utc=True)
    
    # Identify open ballots
    if data_gathering_date is not None:
        baldef_df['Is Open Ballot'] = baldef_df['Ballot Close Date'] > data_gathering_date
    else:
        baldef_df['Is Open Ballot'] = False
    
    # Merge ballot participation with baldef data
    merged_df = ballot_df.merge(
        baldef_df[['BALDEF ID', 'Ballot Cycle', 'Ballot Open Date', 'Ballot Close Date', 'Is Open Ballot']],
        on='BALDEF ID',
        how='left'
    )
    
    # Filter to esilver
    merged_df = merged_df[merged_df['Balloter Key'].str.lower() == 'esilver'].copy()
    
    # Filter out votes from pre-2022 ballots
    merged_df = merged_df[
        (merged_df['Ballot Cycle'].notna()) & 
        (merged_df['Ballot Cycle'] >= '202201')
    ].copy()
    
    print(f"\nTotal BALDEF records: {len(baldef_df)}")
    print(f"Total merged records for esilver: {len(merged_df)}")
    print(f"Open ballots: {baldef_df['Is Open Ballot'].sum()}")
    
    # Get esilver's basic info
    if len(merged_df) == 0:
        print("\nERROR: No records found for esilver!")
        return
    
    esilver_name = merged_df['Balloter Name'].iloc[0] if 'Balloter Name' in merged_df.columns else "Unknown"
    print(f"\nBalloter Name: {esilver_name}")
    print(f"Balloter Key: esilver")
    
    # Get organization info
    org_col = 'Organization_Canonical' if 'Organization_Canonical' in merged_df.columns else 'Organization'
    if org_col in merged_df.columns:
        orgs = merged_df[org_col].dropna().unique()
        print(f"Organization(s): {', '.join(orgs)}")
    
    # Classify votes
    merged_df['Is Vote Cast'] = (
        merged_df['Vote'].notna() & 
        (merged_df['Vote'] != 'No Vote')
    )
    
    merged_df['Is Active Vote'] = merged_df['Vote'].isin(['Affirmative', 'Negative'])
    
    # Analyze by cycle
    print("\n" + "=" * 80)
    print("CYCLE-BY-CYCLE ANALYSIS")
    print("=" * 80)
    
    # Get all cycles
    all_cycles = sorted(merged_df['Ballot Cycle'].dropna().unique())
    print(f"\nTotal cycles with esilver votes: {len(all_cycles)}")
    print(f"Cycles: {', '.join(all_cycles)}")
    
    # Analyze each cycle
    cycle_details = []
    
    for cycle in all_cycles:
        cycle_votes = merged_df[merged_df['Ballot Cycle'] == cycle].copy()
        
        # Count vote types
        total_votes = len(cycle_votes)
        affirmative = len(cycle_votes[cycle_votes['Vote'] == 'Affirmative'])
        negative = len(cycle_votes[cycle_votes['Vote'] == 'Negative'])
        abstain = len(cycle_votes[cycle_votes['Vote'] == 'Abstain'])
        no_vote = len(cycle_votes[cycle_votes['Vote'].isna() | (cycle_votes['Vote'] == 'No Vote')])
        
        # Check if open ballot
        is_open = cycle_votes['Is Open Ballot'].iloc[0] if 'Is Open Ballot' in cycle_votes.columns and len(cycle_votes) > 0 else False
        
        # Active votes (Affirmative + Negative)
        active_votes = affirmative + negative
        any_votes = affirmative + negative + abstain
        
        cycle_details.append({
            'cycle': cycle,
            'total': total_votes,
            'affirmative': affirmative,
            'negative': negative,
            'abstain': abstain,
            'no_vote': no_vote,
            'active_votes': active_votes,
            'any_votes': any_votes,
            'is_open': is_open
        })
    
    # Print cycle details
    print("\nCycle Details:")
    print("-" * 80)
    print(f"{'Cycle':<10} {'Total':<8} {'Aff':<6} {'Neg':<6} {'Abs':<6} {'NoV':<6} {'Active':<8} {'Any':<8} {'Open':<6}")
    print("-" * 80)
    
    for detail in cycle_details:
        open_marker = "✓" if detail['is_open'] else ""
        print(f"{detail['cycle']:<10} {detail['total']:<8} {detail['affirmative']:<6} "
              f"{detail['negative']:<6} {detail['abstain']:<6} {detail['no_vote']:<6} "
              f"{detail['active_votes']:<8} {detail['any_votes']:<8} {open_marker:<6}")
    
    # Calculate streaks manually
    print("\n" + "=" * 80)
    print("STREAK ANALYSIS")
    print("=" * 80)
    
    # Get all cycles from baldef (for ordering)
    all_baldef_cycles = sorted(baldef_df['Ballot Cycle'].dropna().unique())
    
    # Filter closed ballots for streak calculation
    if 'Is Open Ballot' in merged_df.columns:
        is_open = merged_df['Is Open Ballot'].fillna(False).astype(bool)
        closed_merged_df = merged_df[~is_open].copy()
        open_merged_df = merged_df[is_open].copy()
    else:
        closed_merged_df = merged_df.copy()
        open_merged_df = pd.DataFrame()
    
    # Active vote streak (from closed ballots)
    print("\nActive Vote Streak (Affirmative/Negative only):")
    closed_active_cycles = sorted(closed_merged_df[closed_merged_df['Is Active Vote']]['Ballot Cycle'].dropna().unique())
    
    if closed_active_cycles:
        # Find longest consecutive streak
        max_streak = 1
        max_start = closed_active_cycles[0]
        max_end = closed_active_cycles[0]
        
        current_streak = 1
        current_start = closed_active_cycles[0]
        current_end = closed_active_cycles[0]
        
        cycle_to_idx = {cycle: idx for idx, cycle in enumerate(all_baldef_cycles)}
        
        for i in range(1, len(closed_active_cycles)):
            prev_cycle = closed_active_cycles[i-1]
            curr_cycle = closed_active_cycles[i]
            
            prev_idx = cycle_to_idx.get(prev_cycle, -1)
            curr_idx = cycle_to_idx.get(curr_cycle, -1)
            
            if prev_idx >= 0 and curr_idx >= 0 and curr_idx == prev_idx + 1:
                current_streak += 1
                current_end = curr_cycle
                
                if current_streak > max_streak:
                    max_streak = current_streak
                    max_start = current_start
                    max_end = current_end
            else:
                current_streak = 1
                current_start = curr_cycle
                current_end = curr_cycle
        
        # Check if streak continues into open ballots
        streak_end_idx = cycle_to_idx.get(max_end, -1)
        if streak_end_idx >= 0 and streak_end_idx + 1 < len(all_baldef_cycles):
            next_cycle = all_baldef_cycles[streak_end_idx + 1]
            # Check if esilver has active votes in next cycle (might be open)
            next_cycle_votes = merged_df[
                (merged_df['Ballot Cycle'] == next_cycle) & 
                (merged_df['Is Active Vote'])
            ]
            if not next_cycle_votes.empty:
                max_streak += 1
                max_end = next_cycle
                # Continue checking consecutive cycles
                current_idx = streak_end_idx + 1
                while current_idx + 1 < len(all_baldef_cycles):
                    next_cycle = all_baldef_cycles[current_idx + 1]
                    next_cycle_votes = merged_df[
                        (merged_df['Ballot Cycle'] == next_cycle) & 
                        (merged_df['Is Active Vote'])
                    ]
                    if not next_cycle_votes.empty:
                        max_streak += 1
                        max_end = next_cycle
                        current_idx += 1
                    else:
                        break
        
        print(f"  Streak Length: {max_streak}")
        print(f"  Streak Start: {max_start}")
        print(f"  Streak End: {max_end}")
        
        # Verify streak manually
        print("\n  Manual Verification:")
        streak_start_idx = all_baldef_cycles.index(max_start) if max_start in all_baldef_cycles else -1
        streak_end_idx = all_baldef_cycles.index(max_end) if max_end in all_baldef_cycles else -1
        
        if streak_start_idx >= 0 and streak_end_idx >= 0:
            streak_cycles = all_baldef_cycles[streak_start_idx:streak_end_idx + 1]
            print(f"    Cycles in streak: {', '.join(streak_cycles)}")
            
            # Check each cycle in streak
            for cycle in streak_cycles:
                detail = next((d for d in cycle_details if d['cycle'] == cycle), None)
                if detail:
                    has_active = detail['active_votes'] > 0
                    status = "✓" if has_active else "✗"
                    open_status = " (OPEN)" if detail['is_open'] else ""
                    print(f"      {status} {cycle}: {detail['active_votes']} active votes{open_status}")
    
    # Any vote streak (includes Abstain)
    print("\nAny Vote Streak (Affirmative/Negative/Abstain):")
    closed_any_cycles = sorted(closed_merged_df[closed_merged_df['Is Vote Cast']]['Ballot Cycle'].dropna().unique())
    
    if closed_any_cycles:
        # Find longest consecutive streak
        max_streak = 1
        max_start = closed_any_cycles[0]
        max_end = closed_any_cycles[0]
        
        current_streak = 1
        current_start = closed_any_cycles[0]
        current_end = closed_any_cycles[0]
        
        cycle_to_idx = {cycle: idx for idx, cycle in enumerate(all_baldef_cycles)}
        
        for i in range(1, len(closed_any_cycles)):
            prev_cycle = closed_any_cycles[i-1]
            curr_cycle = closed_any_cycles[i]
            
            prev_idx = cycle_to_idx.get(prev_cycle, -1)
            curr_idx = cycle_to_idx.get(curr_cycle, -1)
            
            if prev_idx >= 0 and curr_idx >= 0 and curr_idx == prev_idx + 1:
                current_streak += 1
                current_end = curr_cycle
                
                if current_streak > max_streak:
                    max_streak = current_streak
                    max_start = current_start
                    max_end = current_end
            else:
                current_streak = 1
                current_start = curr_cycle
                current_end = curr_cycle
        
        # Check if streak continues into open ballots
        streak_end_idx = cycle_to_idx.get(max_end, -1)
        if streak_end_idx >= 0 and streak_end_idx + 1 < len(all_baldef_cycles):
            next_cycle = all_baldef_cycles[streak_end_idx + 1]
            # Check if esilver has any votes in next cycle (might be open)
            next_cycle_votes = merged_df[
                (merged_df['Ballot Cycle'] == next_cycle) & 
                (merged_df['Is Vote Cast'])
            ]
            if not next_cycle_votes.empty:
                max_streak += 1
                max_end = next_cycle
                # Continue checking consecutive cycles
                current_idx = streak_end_idx + 1
                while current_idx + 1 < len(all_baldef_cycles):
                    next_cycle = all_baldef_cycles[current_idx + 1]
                    next_cycle_votes = merged_df[
                        (merged_df['Ballot Cycle'] == next_cycle) & 
                        (merged_df['Is Vote Cast'])
                    ]
                    if not next_cycle_votes.empty:
                        max_streak += 1
                        max_end = next_cycle
                        current_idx += 1
                    else:
                        break
        
        print(f"  Streak Length: {max_streak}")
        print(f"  Streak Start: {max_start}")
        print(f"  Streak End: {max_end}")
        
        # Verify streak manually
        print("\n  Manual Verification:")
        streak_start_idx = all_baldef_cycles.index(max_start) if max_start in all_baldef_cycles else -1
        streak_end_idx = all_baldef_cycles.index(max_end) if max_end in all_baldef_cycles else -1
        
        if streak_start_idx >= 0 and streak_end_idx >= 0:
            streak_cycles = all_baldef_cycles[streak_start_idx:streak_end_idx + 1]
            print(f"    Cycles in streak: {', '.join(streak_cycles)}")
            
            # Check each cycle in streak
            for cycle in streak_cycles:
                detail = next((d for d in cycle_details if d['cycle'] == cycle), None)
                if detail:
                    has_any = detail['any_votes'] > 0
                    status = "✓" if has_any else "✗"
                    open_status = " (OPEN)" if detail['is_open'] else ""
                    print(f"      {status} {cycle}: {detail['any_votes']} any votes{open_status}")
    
    # Summary statistics
    print("\n" + "=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    
    total_votes_cast = merged_df['Is Vote Cast'].sum() if 'Is Vote Cast' in merged_df.columns else 0
    total_active_votes = merged_df['Is Active Vote'].sum() if 'Is Active Vote' in merged_df.columns else 0
    
    print(f"\nTotal votes cast (all cycles): {total_votes_cast}")
    print(f"Total active votes (all cycles): {total_active_votes}")
    
    # Closed ballot stats
    closed_votes_cast = closed_merged_df['Is Vote Cast'].sum() if 'Is Vote Cast' in closed_merged_df.columns else 0
    closed_active_votes = closed_merged_df['Is Active Vote'].sum() if 'Is Active Vote' in closed_merged_df.columns else 0
    
    print(f"\nClosed ballot votes cast: {closed_votes_cast}")
    print(f"Closed ballot active votes: {closed_active_votes}")
    
    # Open ballot stats
    if len(open_merged_df) > 0:
        open_votes_cast = open_merged_df['Is Vote Cast'].sum() if 'Is Vote Cast' in open_merged_df.columns else 0
        open_active_votes = open_merged_df['Is Active Vote'].sum() if 'Is Active Vote' in open_merged_df.columns else 0
        
        print(f"\nOpen ballot votes cast: {open_votes_cast}")
        print(f"Open ballot active votes: {open_active_votes}")
    
    print("\n" + "=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Deep dive analysis for esilver's ballot participation"
    )
    parser.add_argument(
        "--baldef-csv",
        required=True,
        help="Path to BALDEF CSV file"
    )
    parser.add_argument(
        "--ballot-csv",
        required=True,
        help="Path to ballot participation CSV file"
    )
    
    args = parser.parse_args()
    
    analyze_esilver(args.baldef_csv, args.ballot_csv)
