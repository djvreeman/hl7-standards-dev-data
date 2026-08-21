#!/usr/bin/env python3
# =============================================================================
# Ballot Participation Analyzer and Markdown Report Generator
#
# This script analyzes HL7 ballot participation data to evaluate voting
# patterns, participation rates, and engagement metrics across ballot cycles,
# and writes a single Markdown report.
#
# === Input Requirements ===
# - BALDEF CSV (--baldef-csv): ballot definition rows (e.g., baldef_data.csv), including
#   Ballot Cycle, Ballot Close Date, BALDEF ID, and (when used) open-ballot flags.
# - Ballot participation CSV (--ballot-csv): ballot submission rows (e.g.,
#   ballot_participation.csv), including Balloter Key, Balloter Name, Vote, Organization,
#   Ballot Cycle, BALDEF ID, etc.
#
# === Command-Line Usage ===
#
#   python3 ballot-participation-analyze.py \
#       --baldef-csv PATH \
#       --ballot-csv PATH \
#       -o OUTPUT.md \
#       -p PERIOD [PERIOD ...] \
#       [optional arguments]
#
# Required:
#   --baldef-csv PATH     BALDEF CSV path.
#   --ballot-csv PATH     Ballot participation CSV path.
#   -o, --output PATH     Output Markdown file path (directories are created if needed).
#   -p, --periods ...     One or more analysis periods (see Period Format). The first
#                         period is the *primary* period: it drives the report title date
#                         range and anchors the optional active-streak table.
#
# === Data gathering date (--data-gathering-date) ===
#
# Use this to record *when you exported or snapshot the CSVs* (the "as of" moment for the
# report). The script compares each ballot's Ballot Close Date to that moment:
#
#   - If Ballot Close Date is AFTER --data-gathering-date, the ballot is treated as still
#     open (voting not finished at export time). Those rows are labeled "open ballots"
#     and are EXCLUDED from most counts: participation rates, leaderboards, vote totals,
#     and similar metrics, so you do not mix complete ballots with partial/in-progress ones.
#   - If Ballot Close Date is on or before that date, the ballot is "closed" for this
#     analysis and included in those metrics.
#
# If you omit --data-gathering-date, the script tries to infer a timestamp from the
# baldef or ballot CSV *filename* (e.g. a datetime embedded in the name). If it still
# cannot infer a date, no ballot is classified as open (everything is treated as closed),
# which matches a historical export where every ballot had already closed.
#
# Optional (other flags):
#   --balloter KEY        Restrict the report to one balloter (Balloter Key). Mutually
#                         exclusive with --org.
#   --org, --organization NAME [NAME ...]
#                         Restrict the report to one or more organization names (combined).
#                         Mutually exclusive with --balloter.
#   --realm-mapping PATH Path to realm mapping CSV (optional; default behavior described
#                         in script help / process_data).
#   --active-vote-streak-min-cycles N
#                         If set (N >= 1), append “Ongoing Active Vote Streaks (N+ cycles) - Individual”
#                         and “Ongoing Active Vote Streaks (N+ cycles) - Organization” (same anchor rules).
#                         Lists *every* voter and *every* organization whose *ongoing* streak of *active votes*
#                         (Affirmative or Negative, not Abstain; org: at least one active vote per cycle) through
#                         the *end of the primary -p period* has length >= N. Not top-ten limited. Anchor cycle =
#                         last closed ballot cycle in that period (same rule as “Summary by Analysis Period”).
#                         Later cycles ignored.
#
# Run `python3 ballot-participation-analyze.py --help` for argparse text.
#
# === Leaderboard Semantics (streaks) ===
# - “Longest Active Vote Streak” (individual/organization): longest run of consecutive
#   ballot cycles with at least one qualifying active vote, anywhere in the closed-ballot
#   dataset. It is *not* required to extend through the latest cycle—only the best historical
#   run.
# - “Ongoing Active Vote Streaks (N+ cycles) - Individual” and “… - Organization” (only if --active-vote-streak-min-cycles):
#   *Ongoing* = streak of consecutive ballot cycles with at least one qualifying active vote per cycle (individual:
#   per voter; organization: at least one active vote from someone in that org), continuing through the last cycle
#   in the primary -p period; *active votes* = Affirmative/Negative only. Votes after that anchor excluded.
#
# === Period Format ===
# Period strings for -p:
#   - YYYY                 Full calendar year (e.g., 2024).
#   - YYYYT1 / YYYYT2 / YYYYT3
#                          HL7 triannual slices (T1 Jan–Apr, T2 May–Aug, T3 Sep–Dec).
#   - YYYY[-T[1-3]]-YYYY[-T[1-3]]
#                          Inclusive range (e.g., 2023T2-2024T1).
#
# Multiple periods: each gets a subsection under “Summary by Analysis Period.” The report
# title and active-streak anchoring use only the *first* period.
#
# === Output (Markdown) ===
# - Title and scope notes; optional filter banner if --balloter or --org.
# - Table of contents.
# - How to Read This Report / terminology.
# - Overall summary for the dataset (open ballots excluded from core metrics where noted).
# - All Time Leaderboards (closed ballots): longest active/any vote streaks, most active
#   votes, most consensus groups with active participation (individual and organization);
#   optional Ongoing Active Vote Streaks (N+ cycles) - Individual and - Organization tables.
# - Summary by Analysis Period: per -p period tables and metrics.
#
# === Example Commands ===
#
# Standard report for one triannual period:
#   python3 scripts/ballot-participation/ballot-participation-analyze.py \
#       --baldef-csv data/working/ballot-participation/baldef_data.csv \
#       --ballot-csv data/working/ballot-participation/ballot_participation.csv \
#       -o reports/2025T3_ballot_participation.md \
#       -p 2025T3
#
# Full year with data-gathering date and active-streak table (e.g., streak >= 9 cycles
# as of end of 2024):
#   python3 scripts/ballot-participation/ballot-participation-analyze.py \
#       --baldef-csv data/working/ballot-participation/baldef_data.csv \
#       --ballot-csv data/working/ballot-participation/ballot_participation.csv \
#       --data-gathering-date 2025-01-15 \
#       --active-vote-streak-min-cycles 9 \
#       -o reports/2024_ballot_participation.md \
#       -p 2024
#
# === Terminology ===
# - Ballot Cycle: ballot period as YYYYMM (e.g., 202509 for September 2025).
# - Consensus Group: a BALDEF ID (one ballot definition).
# - Vote: a ballot participation row with a BALLOT ID.
# - Casting a Vote: Vote is present and not null / “No Vote.”
# - Active Vote: Vote is “Affirmative” or “Negative.”
# - Open Ballot (for this script): Ballot Close Date is still in the future relative to the
#   data-gathering moment (export/snapshot time); excluded from most metrics so numbers
#   reflect only completed ballots.
#
# === Dependencies ===
# - pandas, numpy
# - requests (e.g., SPECS.json)
# - selenium (optional: realm info from product briefs)
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import pandas as pd
import numpy as np
import re
from datetime import datetime
import os
import csv
from collections import defaultdict
import requests
try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    import time
    SELENIUM_AVAILABLE = True
except ImportError:
    SELENIUM_AVAILABLE = False
    print("Warning: selenium not available. Web scraping for realm extraction will be disabled.")


def is_open_ballot_mask(series: pd.Series) -> pd.Series:
    """
    Coerce 'Is Open Ballot' column to a plain bool Series (False where missing).

    Using ``.fillna(False).astype(bool)`` on object-dtype columns triggers a
    pandas FutureWarning about silent downcasting; nullable ``boolean`` avoids it.
    """
    return series.astype("boolean").fillna(False).astype(bool)


def parse_time_period(period_str):
    """Parse a time period string like '2025T1', '2024', or '2024-2025T1' into start and end dates"""
    # Range format: '2024-2025T1'
    range_match = re.match(r'^(\d{4}(?:T[1-3])?)-(\d{4}(?:T[1-3])?)$', period_str)
    if range_match:
        start_period = range_match.group(1)
        end_period = range_match.group(2)
        
        start_date, _, _ = parse_time_period(start_period)
        _, end_date, _ = parse_time_period(end_period)
        
        label = f"{start_period}-{end_period}"
        return start_date, end_date, label
    
    # Full year format: '2024'
    full_year_match = re.match(r'^(\d{4})$', period_str)
    if full_year_match:
        year = int(full_year_match.group(1))
        start_date = pd.Timestamp(year=year, month=1, day=1, hour=0, minute=0, second=0, tz='UTC')
        end_date = pd.Timestamp(year=year, month=12, day=31, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        label = f"{year}"
        return start_date, end_date, label
    
    # Period format: '2025T1', '2024T2', etc.
    tri_match = re.match(r'^(\d{4})T([1-3])$', period_str)
    if tri_match:
        year = int(tri_match.group(1))
        tri = tri_match.group(2)
        
        if tri == '1':
            start_date = pd.Timestamp(year=year, month=1, day=1, hour=0, minute=0, second=0, tz='UTC')
            end_date = pd.Timestamp(year=year, month=4, day=30, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        elif tri == '2':
            start_date = pd.Timestamp(year=year, month=5, day=1, hour=0, minute=0, second=0, tz='UTC')
            end_date = pd.Timestamp(year=year, month=8, day=31, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        elif tri == '3':
            start_date = pd.Timestamp(year=year, month=9, day=1, hour=0, minute=0, second=0, tz='UTC')
            end_date = pd.Timestamp(year=year, month=12, day=31, hour=23, minute=59, second=59, microsecond=999999, tz='UTC')
        
        label = f"{year}T{tri}"
        return start_date, end_date, label
    
    raise ValueError(f"Invalid time period format: {period_str}. Use 'YYYY', 'YYYYT[1-3]', or 'YYYY[-T[1-3]]-YYYY[-T[1-3]]'")

def get_closed_ballot_cycles_in_period(closed_baldef_df, start_date, end_date):
    """
    Ballot cycles whose latest Ballot Close Date falls within [start_date, end_date].
    Same rule as Summary by Analysis Period. Returns sorted YYYYMM strings.
    """
    period_cycles = []
    for cycle in closed_baldef_df['Ballot Cycle'].dropna().unique():
        cycle_baldefs = closed_baldef_df[closed_baldef_df['Ballot Cycle'] == cycle]
        if len(cycle_baldefs) > 0:
            cycle_close_date = cycle_baldefs['Ballot Close Date'].max()
            if pd.notna(cycle_close_date) and start_date <= cycle_close_date <= end_date:
                period_cycles.append(str(cycle))
    return sorted(period_cycles)

def parse_ballot_period(period_str):
    """
    Parse Ballot Period from format like "2026-Jan" or "2025-Sep" to YYYYMM format.
    Returns tuple (year, month_num, yyyymm_str) or None if parsing fails.
    """
    if pd.isna(period_str) or not period_str:
        return None
    
    # Format: "2026-Jan" or "2025-Sep"
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

def assign_ranks_with_ties(df, value_column, name_column):
    """
    Assign ranks to a DataFrame with proper tie handling.
    Ties get the same rank, then skip to the next rank.
    Within ties, sort alphabetically by name_column.
    
    Args:
        df: DataFrame to rank
        value_column: Column name to rank by (e.g., 'Streak Length', 'Active Vote Count')
        name_column: Column name to sort alphabetically within ties
    
    Returns:
        DataFrame with 'Rank' column added
    """
    if df.empty:
        return df
    
    # Sort by value descending, then by name ascending for ties
    df_sorted = df.sort_values([value_column, name_column], ascending=[False, True]).reset_index(drop=True)
    
    # Assign ranks with proper tie handling
    ranks = []
    current_rank = 1
    prev_value = None
    
    for idx, row in df_sorted.iterrows():
        current_value = row[value_column]
        
        # If this value is different from previous, update rank
        if prev_value is not None and current_value != prev_value:
            current_rank = idx + 1
        
        ranks.append(current_rank)
        prev_value = current_value
    
    df_sorted['Rank'] = ranks
    return df_sorted

def calculate_vote_streak(votes_df, all_cycles_df, group_by_key, name_key, cycle_key, include_abstain=False):
    """
    Calculate the longest consecutive streak of votes for each group (best run over all time).
    A streak is defined as consecutive ballot cycles (in the sorted list of all cycles)
    where the group cast a vote. This is not anchored to the latest cycle—a shorter older streak
    is outranked by a longer one that ended earlier.
    
    Args:
        votes_df: DataFrame with vote data
        all_cycles_df: DataFrame with all cycles to determine consecutive order
        group_by_key: Column name to group by (e.g., 'Balloter Key' or 'Organization')
        name_key: Column name for display name (e.g., 'Balloter Name' or 'Organization')
        cycle_key: Column name for ballot cycle (YYYYMM format)
        include_abstain: If True, include Abstain votes. If False, only Affirmative/Negative (active votes)
    
    Returns:
        DataFrame with columns: [name_key, 'Streak Length', 'Streak Start', 'Streak End'] sorted by streak descending
    """
    # Filter votes based on include_abstain flag
    if include_abstain:
        # Include Affirmative, Negative, and Abstain (any vote cast)
        filtered_votes = votes_df[votes_df['Vote'].isin(['Affirmative', 'Negative', 'Abstain'])].copy()
    else:
        # Only active votes (Affirmative/Negative)
        filtered_votes = votes_df[votes_df['Vote'].isin(['Affirmative', 'Negative'])].copy()
    
    if filtered_votes.empty:
        return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])
    
    # Get all unique cycles across the entire dataset and sort them
    # Ensure cycles are strings for consistent comparison
    all_cycles_raw = all_cycles_df[cycle_key].dropna().unique()
    all_cycles = sorted([str(c) for c in all_cycles_raw])
    
    if not all_cycles:
        return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])
    
    # Create a mapping of cycle to index for quick lookup
    cycle_to_index = {cycle: idx for idx, cycle in enumerate(all_cycles)}
    
    # For each group, find the longest consecutive streak
    streaks = []
    
    for group_value in filtered_votes[group_by_key].dropna().unique():
        group_votes = filtered_votes[filtered_votes[group_by_key] == group_value]
        # Get unique cycles for this group (in case multiple votes in same cycle)
        # Ensure cycles are strings for consistent comparison
        group_cycles_raw = group_votes[cycle_key].dropna().unique()
        group_cycles = sorted([str(c) for c in group_cycles_raw])
        
        if not group_cycles:
            continue
        
        # Find longest consecutive streak in the context of all cycles
        max_streak = 1
        max_streak_start = group_cycles[0]
        max_streak_end = group_cycles[0]
        
        current_streak = 1
        current_streak_start = group_cycles[0]
        current_streak_end = group_cycles[0]
        
        for i in range(1, len(group_cycles)):
            prev_cycle = group_cycles[i-1]
            curr_cycle = group_cycles[i]
            
            # Get indices in the full cycle list (all cycles that exist, including open ballots)
            # This determines if cycles are consecutive ballot cycles, not consecutive months
            prev_idx = cycle_to_index.get(prev_cycle, -1)
            curr_idx = cycle_to_index.get(curr_cycle, -1)
            
            # Check if cycles are consecutive in the full list of ballot cycles
            # This handles Jan/May/Sep pattern and out-of-cycle ballots correctly
            if prev_idx >= 0 and curr_idx >= 0 and curr_idx == prev_idx + 1:
                current_streak += 1
                current_streak_end = curr_cycle
                
                # Update max streak if current streak is longer
                if current_streak > max_streak:
                    max_streak = current_streak
                    max_streak_start = current_streak_start
                    max_streak_end = current_streak_end
            else:
                # Not consecutive ballot cycles - reset current streak
                current_streak = 1
                current_streak_start = curr_cycle
                current_streak_end = curr_cycle
        
        # Get display name
        display_name = group_votes[name_key].iloc[0] if name_key in group_votes.columns else str(group_value)
        
        streaks.append({
            name_key: display_name,
            'Streak Length': max_streak,
            'Streak Start': max_streak_start,
            'Streak End': max_streak_end
        })
    
    result_df = pd.DataFrame(streaks)
    result_df = result_df.sort_values('Streak Length', ascending=False)
    
    return result_df

def calculate_active_vote_streak(votes_df, all_cycles_df, group_by_key, name_key, cycle_key):
    """
    Calculate the longest consecutive streak of active votes (Affirmative/Negative only).
    This is a convenience wrapper around calculate_vote_streak with include_abstain=False.
    """
    return calculate_vote_streak(votes_df, all_cycles_df, group_by_key, name_key, cycle_key, include_abstain=False)

def calculate_any_vote_streak(votes_df, all_cycles_df, group_by_key, name_key, cycle_key):
    """
    Calculate the longest consecutive streak of any votes (Affirmative/Negative/Abstain).
    This is a convenience wrapper around calculate_vote_streak with include_abstain=True.
    """
    return calculate_vote_streak(votes_df, all_cycles_df, group_by_key, name_key, cycle_key, include_abstain=True)

def calculate_current_active_vote_streak(votes_df, all_cycles_df, group_by_key, name_key, cycle_key, streak_end_cycle=None):
    """
    Trailing streak of active votes (Affirmative or Negative only—not Abstain) ending at a given cycle.
    In the report, this is the "ongoing" streak through the primary period anchor.

    streak_end_cycle: YYYYMM string for the last ballot cycle in the streak (inclusive). Votes after
    this cycle in global ballot order are ignored. When None, uses the latest closed cycle present
    in votes_df (full-dataset as of latest data).
    """
    filtered_votes = votes_df[votes_df['Vote'].isin(['Affirmative', 'Negative'])].copy()
    if filtered_votes.empty:
        return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])

    all_cycles_raw = all_cycles_df[cycle_key].dropna().unique()
    all_cycles = sorted([str(c) for c in all_cycles_raw])
    if not all_cycles:
        return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])

    if streak_end_cycle is not None:
        latest_closed = str(streak_end_cycle)
    else:
        closed_cycles = sorted(
            {str(c) for c in filtered_votes[cycle_key].dropna().unique()}
        )
        if not closed_cycles:
            return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])
        latest_closed = closed_cycles[-1]

    if latest_closed not in all_cycles:
        return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])

    end_idx = all_cycles.index(latest_closed)
    cycles_through_anchor = set(all_cycles[: end_idx + 1])
    ck = filtered_votes[cycle_key]
    filtered_votes = filtered_votes[ck.notna() & ck.astype(str).isin(cycles_through_anchor)]
    if filtered_votes.empty:
        return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])
    streaks = []

    for group_value in filtered_votes[group_by_key].dropna().unique():
        group_votes = filtered_votes[filtered_votes[group_by_key] == group_value]
        group_cycles = sorted({str(c) for c in group_votes[cycle_key].dropna().unique()})
        if not group_cycles or latest_closed not in group_cycles:
            continue

        i = end_idx
        while i >= 0 and all_cycles[i] in group_cycles:
            i -= 1
        streak_start = all_cycles[i + 1]
        streak_len = end_idx - i
        display_name = group_votes[name_key].iloc[0] if name_key in group_votes.columns else str(group_value)
        streaks.append({
            name_key: display_name,
            'Streak Length': streak_len,
            'Streak Start': streak_start,
            'Streak End': latest_closed,
        })

    result_df = pd.DataFrame(streaks)
    if result_df.empty:
        return pd.DataFrame(columns=[name_key, 'Streak Length', 'Streak Start', 'Streak End'])
    return result_df.sort_values('Streak Length', ascending=False)

def calculate_most_active_votes(votes_df, group_by_key, name_key):
    """
    Calculate the count of active votes for each group.
    
    Args:
        votes_df: DataFrame with vote data
        group_by_key: Column name to group by (e.g., 'Balloter Key' or 'Organization')
        name_key: Column name for display name (e.g., 'Balloter Name' or 'Organization')
    
    Returns:
        DataFrame with columns: [name_key, 'Active Vote Count'] sorted by count descending
    """
    # Filter to only active votes
    active_votes = votes_df[votes_df['Vote'].isin(['Affirmative', 'Negative'])].copy()
    
    if active_votes.empty:
        return pd.DataFrame(columns=[name_key, 'Active Vote Count'])
    
    # Count active votes per group
    vote_counts = active_votes.groupby(group_by_key).size().reset_index(name='Active Vote Count')
    
    # Add display names
    name_map = active_votes.groupby(group_by_key)[name_key].first().to_dict()
    vote_counts[name_key] = vote_counts[group_by_key].map(name_map)
    
    # Reorder columns and sort
    vote_counts = vote_counts[[name_key, 'Active Vote Count']]
    vote_counts = vote_counts.sort_values('Active Vote Count', ascending=False)
    
    return vote_counts

def calculate_most_consensus_groups_with_active_participation(votes_df, group_by_key, name_key):
    """
    Calculate the count of unique Consensus Groups (BALDEFs) where each group cast active votes.
    
    Args:
        votes_df: DataFrame with vote data
        group_by_key: Column name to group by (e.g., 'Balloter Key' or 'Organization')
        name_key: Column name for display name (e.g., 'Balloter Name' or 'Organization')
    
    Returns:
        DataFrame with columns: [name_key, 'Consensus Groups Count'] sorted by count descending
    """
    # Filter to only active votes
    active_votes = votes_df[votes_df['Vote'].isin(['Affirmative', 'Negative'])].copy()
    
    if active_votes.empty:
        return pd.DataFrame(columns=[name_key, 'Consensus Groups Count'])
    
    # Count unique BALDEF IDs (Consensus Groups) per group
    consensus_group_counts = active_votes.groupby(group_by_key)['BALDEF ID'].nunique().reset_index(name='Consensus Groups Count')
    
    # Add display names
    name_map = active_votes.groupby(group_by_key)[name_key].first().to_dict()
    consensus_group_counts[name_key] = consensus_group_counts[group_by_key].map(name_map)
    
    # Reorder columns and sort
    consensus_group_counts = consensus_group_counts[[name_key, 'Consensus Groups Count']]
    consensus_group_counts = consensus_group_counts.sort_values('Consensus Groups Count', ascending=False)
    
    return consensus_group_counts

def extract_timestamp_from_filename(filename):
    """
    Extract timestamp from filename like 'baldef_data-20260115-143022.csv'
    Returns pd.Timestamp or None if not found
    """
    # Pattern: YYYYMMDD-HHMMSS
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

# Specifications to exclude (HL7 affiliate pilot ballots - HL7 Australia)
EXCLUDED_SPECIFICATIONS = [
    'FHIR-au-ps',
    'FHIR-au-core',
    'FHIR-au-erequesting',
    'FHIR-au-base'
]

# =============================================================================
# Realm Resolution Functions (adapted from issue-data-enhance.py)
# =============================================================================

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
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Error loading SPECS.json: {e}")
        return []

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

def extract_realm_from_url(url):
    """
    Fetch the HTML from the given URL using Selenium and extract the REALM information.
    If the extracted realm is 'US Realm', return 'United States'; otherwise return the extracted text.
    """
    if not SELENIUM_AVAILABLE:
        print(f"Warning: Cannot extract realm from URL {url} - selenium not available")
        return None
    
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

def resolve_realm_for_specification(specification, specification_url, spec_to_realm, url_to_realm, specs_lookup, mapping_file):
    """
    Resolve realm for a single specification using multiple methods.
    
    Args:
        specification: Specification key (may be comma-separated, will use first)
        specification_url: Optional URL for the specification
        spec_to_realm: Dictionary mapping spec keys to realms
        url_to_realm: Dictionary mapping URLs to realms
        specs_lookup: Dictionary mapping spec keys to full spec objects from SPECS.json
        mapping_file: Path to mapping file for caching
    
    Returns:
        str: Realm name or None
    """
    if pd.isna(specification) or not specification:
        return None
    
    # Handle comma-separated specifications (use first one)
    spec_key = str(specification).split(',')[0].strip() if specification else None
    if not spec_key:
        return None
    
    # Check for specification key in our mapping first
    if spec_key in spec_to_realm:
        return spec_to_realm[spec_key]
    
    # Try using Specification URL directly if available
    if specification_url and pd.notna(specification_url):
        url_str = str(specification_url).strip()
        if url_str:
            # Check URL patterns first
            if url_str.startswith("http://hl7.org/fhir/uv/") or url_str.startswith("https://hl7.org/fhir/uv/"):
                realm_val = "Universal"
                spec_to_realm[spec_key] = realm_val
                url_to_realm[url_str] = realm_val
                save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                return realm_val
            elif url_str.startswith("http://hl7.org/fhir/us/") or url_str.startswith("https://hl7.org/fhir/us/"):
                realm_val = "United States"
                spec_to_realm[spec_key] = realm_val
                url_to_realm[url_str] = realm_val
                save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                return realm_val
            elif url_str == "http://hl7.org/fhir" or url_str == "https://hl7.org/fhir":
                realm_val = "Universal"
                spec_to_realm[spec_key] = realm_val
                url_to_realm[url_str] = realm_val
                save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                return realm_val
            elif url_str.startswith("http://hl7.org/cda/us/") or url_str.startswith("https://hl7.org/cda/us/"):
                realm_val = "United States"
                spec_to_realm[spec_key] = realm_val
                url_to_realm[url_str] = realm_val
                save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                return realm_val
            elif url_str.startswith("http://hl7.org/cda/stds/") or url_str.startswith("https://hl7.org/cda/stds/"):
                realm_val = "Universal"
                spec_to_realm[spec_key] = realm_val
                url_to_realm[url_str] = realm_val
                save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                return realm_val
            
            # Check URL cache
            if url_str in url_to_realm:
                realm_val = url_to_realm[url_str]
                spec_to_realm[spec_key] = realm_val
                save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                return realm_val
            
            # Try web scraping if it's a product brief URL
            if '?product_id=' in url_str:
                realm_val = extract_realm_from_url(url_str)
                if realm_val is not None:
                    url_to_realm[url_str] = realm_val
                    spec_to_realm[spec_key] = realm_val
                    save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                    return realm_val
    
    # Use SPECS.json lookup
    if specs_lookup:
        spec_obj = specs_lookup.get(spec_key)
        if spec_obj:
            url = spec_obj.get('url')
            if url:
                # Handle FHIR URL patterns
                if url.startswith("http://hl7.org/fhir/uv/") or url.startswith("https://hl7.org/fhir/uv/"):
                    realm_val = "Universal"
                    spec_to_realm[spec_key] = realm_val
                    save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                    return realm_val
                elif url.startswith("http://hl7.org/fhir/us/") or url.startswith("https://hl7.org/fhir/us/"):
                    realm_val = "United States"
                    spec_to_realm[spec_key] = realm_val
                    save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                    return realm_val
                elif url == "http://hl7.org/fhir" or url == "https://hl7.org/fhir":
                    realm_val = "Universal"
                    spec_to_realm[spec_key] = realm_val
                    save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                    return realm_val
                # Handle CDA URL patterns
                elif url.startswith("http://hl7.org/cda/us/") or url.startswith("https://hl7.org/cda/us/"):
                    realm_val = "United States"
                    spec_to_realm[spec_key] = realm_val
                    save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                    return realm_val
                elif url.startswith("http://hl7.org/cda/stds/") or url.startswith("https://hl7.org/cda/stds/"):
                    realm_val = "Universal"
                    spec_to_realm[spec_key] = realm_val
                    save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                    return realm_val
                # Otherwise, if it's a product brief URL containing '?product_id='
                elif '?product_id=' in url:
                    if url in url_to_realm:
                        realm_val = url_to_realm[url]
                        spec_to_realm[spec_key] = realm_val
                        save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                        return realm_val
                    else:
                        realm_val = extract_realm_from_url(url)
                        if realm_val is not None:
                            url_to_realm[url] = realm_val
                            spec_to_realm[spec_key] = realm_val
                            save_realm_mappings(spec_to_realm, url_to_realm, mapping_file)
                            return realm_val
    
    return None

def get_org_column_name(df):
    """
    Determine which organization column to use.
    Prefers Organization_Canonical if available, otherwise falls back to Organization.
    
    Returns:
        Column name to use for organization ('Organization_Canonical' or 'Organization')
    """
    if 'Organization_Canonical' in df.columns:
        return 'Organization_Canonical'
    elif 'Organization' in df.columns:
        return 'Organization'
    else:
        raise ValueError("Neither 'Organization' nor 'Organization_Canonical' column found in ballot data.")


def process_data(baldef_df, ballot_df, data_gathering_date=None, balloter_key=None, organization=None, realm_mapping_file=None):
    """
    Process and merge ballot data
    
    Args:
        baldef_df: DataFrame with BALDEF data
        ballot_df: DataFrame with ballot participation data
        data_gathering_date: pd.Timestamp or None - export/snapshot time; ballots with
            Ballot Close Date after this are marked open and excluded from most metrics.
            If None, inferred from filenames when possible; otherwise no open ballots.
        balloter_key: Optional string - filter to specific balloter by Balloter Key
        organization: Optional string or list of strings - filter to specific organization(s)
        realm_mapping_file: Optional string - path to realm mapping CSV file for lookup and cache
    
    Returns:
        Tuple of (baldef_df, merged_df, open_ballots_count, excluded_pre_2022_count, excluded_affiliate_count)
    """
    # Parse Ballot Period to YYYYMM format
    baldef_df['Ballot Cycle'] = baldef_df['Ballot Period'].apply(
        lambda x: parse_ballot_period(x)[2] if parse_ballot_period(x) else None
    )
    
    # Filter to only include ballots from January 2022 onwards (Jira balloting started then)
    # Ballot cycles are in YYYYMM format, so 202201 is January 2022
    initial_count = len(baldef_df)
    baldef_df = baldef_df[
        (baldef_df['Ballot Cycle'].notna()) & 
        (baldef_df['Ballot Cycle'] >= '202201')
    ].copy()
    excluded_pre_2022_count = initial_count - len(baldef_df)
    
    # Filter out HL7 affiliate pilot ballots (HL7 Australia)
    if 'Specification' in baldef_df.columns:
        before_affiliate_filter = len(baldef_df)
        baldef_df = baldef_df[~baldef_df['Specification'].isin(EXCLUDED_SPECIFICATIONS)].copy()
        excluded_affiliate_count = before_affiliate_filter - len(baldef_df)
    else:
        excluded_affiliate_count = 0
    
    # Parse dates
    baldef_df['Ballot Open Date'] = pd.to_datetime(baldef_df['Ballot Open Date'], errors='coerce', utc=True)
    baldef_df['Ballot Close Date'] = pd.to_datetime(baldef_df['Ballot Close Date'], errors='coerce', utc=True)
    
    # Validate Ballot Period matches close date year/month and flag data quality issues
    # This helps catch cases where the CSV has incorrect data
    if 'Ballot Period' in baldef_df.columns and 'Ballot Close Date' in baldef_df.columns:
        def get_period_year_month(period_str):
            """Get year and month from Ballot Period string."""
            period_parsed = parse_ballot_period(period_str)
            if period_parsed is None:
                return None, None
            year, month, _ = period_parsed
            return year, month
        
        # Check for mismatches
        mismatches = []
        for idx, row in baldef_df.iterrows():
            period_str = row.get('Ballot Period')
            close_date = row.get('Ballot Close Date')
            if pd.isna(period_str) or pd.isna(close_date):
                continue
            
            period_year, period_month = get_period_year_month(period_str)
            if period_year is None or period_month is None:
                continue
            
            close_year = close_date.year
            close_month = close_date.month
            
            # Check if period year/month matches close date year/month
            # Allow some flexibility (ballots might close in the month before/after the period)
            month_diff = abs((close_year * 12 + close_month) - (period_year * 12 + period_month))
            if month_diff > 1:
                mismatches.append({
                    'BALDEF ID': row.get('BALDEF ID'),
                    'Ballot Period': period_str,
                    'Period Year/Month': f"{period_year}-{period_month:02d}",
                    'Close Date': close_date.strftime('%Y-%m-%d'),
                    'Close Year/Month': f"{close_year}-{close_month:02d}",
                    'Month Diff': month_diff
                })
        
        if mismatches:
            print(f"Warning: Found {len(mismatches)} BALDEF(s) where Ballot Period doesn't match Ballot Close Date:")
            for mm in mismatches[:5]:
                print(f"  {mm['BALDEF ID']}: Period={mm['Ballot Period']} ({mm['Period Year/Month']}) vs Close={mm['Close Date']} ({mm['Close Year/Month']})")
            if len(mismatches) > 5:
                print(f"  ... and {len(mismatches) - 5} more")
            print("  This may indicate data quality issues in the source CSV.")
    
    # Identify open ballots (where Ballot Close Date is after data gathering date)
    # Note: This relies on Ballot Close Date being correct in the CSV
    if data_gathering_date is not None:
        baldef_df['Is Open Ballot'] = baldef_df['Ballot Close Date'] > data_gathering_date
        open_ballots_count = baldef_df['Is Open Ballot'].sum()
    else:
        baldef_df['Is Open Ballot'] = False
        open_ballots_count = 0
    
    # Resolve Realm information for each BALDEF
    print("Resolving Realm information for consensus groups...")
    if realm_mapping_file is None:
        # Default to a realm_mappings.csv in the same directory as the baldef CSV
        # For now, use a default path in data/working/cache
        realm_mapping_file = 'data/working/cache/realm_cache.csv'
    
    # Load realm mappings
    spec_to_realm, url_to_realm = load_realm_mappings(realm_mapping_file)
    
    # Load SPECS.json for realm resolution
    specs_url = "https://raw.githubusercontent.com/HL7/JIRA-Spec-Artifacts/gh-pages/SPECS.json"
    specs_data = load_specs_json(specs_url)
    specs_lookup = build_specs_lookup(specs_data) if specs_data else None
    
    # Resolve realm for each BALDEF
    def get_realm_for_row(row):
        specification = row.get('Specification')
        specification_url = row.get('Specification URL')
        return resolve_realm_for_specification(
            specification, specification_url, 
            spec_to_realm, url_to_realm, specs_lookup, realm_mapping_file
        )
    
    baldef_df['Realm'] = baldef_df.apply(get_realm_for_row, axis=1)
    realm_resolved_count = baldef_df['Realm'].notna().sum()
    print(f"Resolved Realm for {realm_resolved_count} out of {len(baldef_df)} consensus groups")
    
    # Merge ballot participation with baldef data (now including Realm)
    merged_df = ballot_df.merge(
        baldef_df[['BALDEF ID', 'Ballot Cycle', 'Ballot Open Date', 'Ballot Close Date', 'Is Open Ballot', 'Realm']],
        on='BALDEF ID',
        how='left'
    )
    
    # Filter out votes from pre-2022 ballots (where Ballot Cycle is NaN or < 202201)
    # This happens when a BALDEF was filtered out because it was pre-2022
    initial_vote_count = len(merged_df)
    merged_df = merged_df[
        (merged_df['Ballot Cycle'].notna()) & 
        (merged_df['Ballot Cycle'] >= '202201')
    ].copy()
    excluded_votes_count = initial_vote_count - len(merged_df)
    
    # Apply balloter or organization filter if specified
    if balloter_key:
        initial_filtered_count = len(merged_df)
        # Case-insensitive match for balloter key
        merged_df = merged_df[merged_df['Balloter Key'].str.lower() == balloter_key.lower()].copy()
        filtered_count = len(merged_df)
        if filtered_count == 0:
            raise ValueError(f"No votes found for balloter key '{balloter_key}'. Please check the key and try again.")
        print(f"Filtered to balloter '{balloter_key}': {filtered_count} votes (from {initial_filtered_count} total)")
    
    if organization:
        # Normalize organization to a list (handle both single string and list)
        if isinstance(organization, str):
            org_list = [organization]
        else:
            org_list = organization
        
        # Determine which organization column to use
        org_col = get_org_column_name(merged_df)
        
        # Save original for error messages
        original_merged_df = merged_df.copy()
        
        initial_filtered_count = len(merged_df)
        # Case-insensitive match with trimmed whitespace for organizations
        # Handle NaN values by converting to empty string first
        org_series = merged_df[org_col].fillna('').astype(str).str.strip().str.lower()
        # Create a set of normalized organization filters
        org_filters = {org.strip().lower() for org in org_list}
        merged_df = merged_df[org_series.isin(org_filters)].copy()
        filtered_count = len(merged_df)
        
        if filtered_count == 0:
            # Try to find similar organization names to help user
            # Use original merged_df before filtering
            all_orgs = original_merged_df[org_col].dropna().unique()
            similar_orgs = []
            for org_filter in org_list:
                similar = [org for org in all_orgs if org_filter.lower() in str(org).lower() or str(org).lower() in org_filter.lower()]
                similar_orgs.extend(similar)
            similar_orgs = list(set(similar_orgs))  # Remove duplicates
            
            org_display = ', '.join(f"'{org}'" for org in org_list)
            error_msg = f"No votes found for organization(s) {org_display}. Please check the organization name(s) and try again."
            if similar_orgs:
                error_msg += f"\nSimilar organization names found: {', '.join(similar_orgs[:5])}"
            raise ValueError(error_msg)
        
        # Get unique balloters for debug info (after organization filter, before open ballot filter)
        unique_balloters_after_org_filter = merged_df['Balloter Name'].dropna().unique() if 'Balloter Name' in merged_df.columns else []
        org_display = ', '.join(f"'{org}'" for org in org_list)
        print(f"Filtered to organization(s) {org_display}: {filtered_count} votes (from {initial_filtered_count} total)")
        print(f"  Found {len(unique_balloters_after_org_filter)} unique balloter(s) after organization filter: {', '.join(str(b) for b in unique_balloters_after_org_filter[:10])}")
        if len(unique_balloters_after_org_filter) > 10:
            print(f"  ... and {len(unique_balloters_after_org_filter) - 10} more")
    
    # Classify votes
    merged_df['Is Vote Cast'] = (
        merged_df['Vote'].notna() & 
        (merged_df['Vote'] != 'No Vote')
    )
    
    merged_df['Is Active Vote'] = merged_df['Vote'].isin(['Affirmative', 'Negative'])
    
    # Filter out votes from excluded affiliate ballots
    if 'Specification' in merged_df.columns:
        initial_vote_count_after_pre2022 = len(merged_df)
        merged_df = merged_df[~merged_df['Specification'].isin(EXCLUDED_SPECIFICATIONS)].copy()
        # Note: excluded_affiliate_count already counted above for BALDEFs
    
    return baldef_df, merged_df, open_ballots_count, excluded_pre_2022_count, excluded_affiliate_count

def generate_overall_summary(baldef_df, ballot_df, merged_df, open_ballots_count, excluded_pre_2022_count, excluded_affiliate_count, data_gathering_date=None):
    """Generate overall summary statistics"""
    md = []
    
    md.append("## Overall Summary for Dataset\n")
    
    # Filter out open ballots for calculations
    if 'Is Open Ballot' in baldef_df.columns:
        # Handle NaN values - treat them as False (not open)
        # Create a boolean mask explicitly
        is_open = is_open_ballot_mask(baldef_df['Is Open Ballot'])
        closed_baldef_df = baldef_df[~is_open].copy()
    else:
        closed_baldef_df = baldef_df.copy()
    
    if 'Is Open Ballot' in merged_df.columns:
        # Handle NaN values - treat them as False (not open)
        # Create a boolean mask explicitly
        is_open = is_open_ballot_mask(merged_df['Is Open Ballot'])
        closed_merged_df = merged_df[~is_open].copy()
    else:
        closed_merged_df = merged_df.copy()
    
    # Date range (only for closed ballots)
    # Use close dates to show when ballots closed, which is more accurate for closed ballot analysis
    earliest_close_date = closed_baldef_df['Ballot Close Date'].min()
    latest_close_date = closed_baldef_df['Ballot Close Date'].max()
    
    if pd.notna(earliest_close_date) and pd.notna(latest_close_date):
        date_range = f"{earliest_close_date.strftime('%B %d, %Y')} to {latest_close_date.strftime('%B %d, %Y')}"
    else:
        date_range = "N/A"
    
    # Total Ballot Cycles (unique Ballot Cycle values, excluding open ballots)
    unique_cycles = closed_baldef_df['Ballot Cycle'].dropna().unique()
    total_cycles = len(unique_cycles)
    
    # Consensus Groups (unique BALDEF IDs, excluding open ballots)
    total_consensus_groups = closed_baldef_df['BALDEF ID'].nunique()
    
    # Votes Cast (Vote not null and not "No Vote", excluding open ballots)
    votes_cast = closed_merged_df['Is Vote Cast'].sum()
    
    # Active Votes Cast (Vote is "Affirmative" or "Negative", excluding open ballots)
    active_votes_cast = closed_merged_df['Is Active Vote'].sum()
    
    # Total consensus groups including open ballots (for display)
    total_consensus_groups_all = baldef_df['BALDEF ID'].nunique()
    
    md.append(f"This summary includes all ballot data from **{date_range}**.\n")
    if data_gathering_date is not None:
        md.append(f"> **Note:** Metrics exclude open ballots (where Ballot Close Date is after {data_gathering_date.strftime('%B %d, %Y')}).\n")
    if excluded_pre_2022_count > 0:
        md.append(f"> **Note:** {format_count(excluded_pre_2022_count)} BALDEF record(s) from before January 2022 were excluded (Jira balloting started in January 2022).\n")
    if excluded_affiliate_count > 0:
        md.append(f"> **Note:** {format_count(excluded_affiliate_count)} BALDEF record(s) from HL7 affiliate pilots (HL7 Australia) were excluded from this analysis.\n")
    md.append(f"- **Date Range:** {date_range}")
    md.append(f"- **Total Ballot Cycles:** {format_count(total_cycles)}")
    md.append(f"- **Consensus Groups:** {format_count(total_consensus_groups)}")
    if open_ballots_count > 0:
        md.append(f"- **Open Ballots (excluded from metrics):** {format_count(open_ballots_count)}")
    md.append(f"- **Votes Cast:** {format_count(votes_cast)}")
    md.append(f"- **Active Votes Cast:** {format_count(active_votes_cast)}")
    md.append("")
    
    return md

def generate_leaderboards(merged_df, all_cycles_df, active_vote_streak_min_cycles=None, analysis_period_str=None):
    """Generate all-time leaderboards (excludes open ballots).

    If active_vote_streak_min_cycles is set, include optional sections listing every individual
    and every organization whose ongoing active-vote streak at the **end of the primary analysis period**
    (last ballot cycle in that period) meets at least that many consecutive cycles.
    """
    md = []
    
    md.append("### All Time Leaderboards\n")
    md.append("> **Note:** Leaderboards exclude open ballots to ensure fair comparison.\n")
    md.append("")
    
    # Determine which organization column to use
    org_col = get_org_column_name(merged_df)
    if org_col == 'Organization_Canonical':
        md.append("> **Note:** Using canonical organization names (normalized from Salesforce).\n")
        md.append("")
    
    # Filter out open ballots for leaderboard calculations (votes only)
    if 'Is Open Ballot' in merged_df.columns:
        # Handle NaN values - treat them as False (not open)
        # Create a boolean mask explicitly
        is_open = is_open_ballot_mask(merged_df['Is Open Ballot'])
        closed_merged_df = merged_df[~is_open].copy()
    else:
        closed_merged_df = merged_df.copy()
    
    if active_vote_streak_min_cycles is not None:
        n = active_vote_streak_min_cycles
        md.append('<a id="ongoing-active-vote-streaks-individual"></a>\n')
        md.append(f"#### 🏆 Ongoing Active Vote Streaks ({n}+ cycles) - Individual\n")
        md.append(
            "**Terminology:** **Active vote** means Affirmative or Negative (not Abstain). "
            "**Ongoing streak** means that run of consecutive ballot cycles with at least one active "
            "vote per cycle, continuing through the **last ballot cycle in the primary analysis period** "
            "(same cycle membership as *Summary by Analysis Period*: a cycle counts if its latest close "
            "date falls in that period). Votes in later cycles are ignored. "
            f"**All** voters with an ongoing streak of **{format_count(n)}** or more consecutive "
            "ballot cycles are listed (not limited to the top ten).\n"
        )
        md.append("")
        if 'Is Open Ballot' in all_cycles_df.columns:
            is_open_b = is_open_ballot_mask(all_cycles_df['Is Open Ballot'])
            closed_baldef_for_period = all_cycles_df[~is_open_b].copy()
        else:
            closed_baldef_for_period = all_cycles_df.copy()
        streak_anchor = None
        if analysis_period_str:
            p_start, p_end, p_label = parse_time_period(analysis_period_str)
            period_cycles = get_closed_ballot_cycles_in_period(closed_baldef_for_period, p_start, p_end)
            streak_anchor = period_cycles[-1] if period_cycles else None
            if streak_anchor:
                md.append(
                    f"> **Primary analysis period:** {p_label} "
                    f"(ongoing streak measured through ballot cycle **{streak_anchor}**).\n"
                )
            else:
                md.append(
                    f"> **Primary analysis period:** {p_label} — no closed ballot cycles in this range.\n"
                )
            md.append("")
        else:
            md.append(
                "> **Note:** Primary analysis period was not provided; cannot anchor the ongoing streak.\n"
            )
            md.append("")
        if streak_anchor:
            current_individual = calculate_current_active_vote_streak(
                closed_merged_df,
                all_cycles_df,
                'Balloter Key',
                'Balloter Name',
                'Ballot Cycle',
                streak_end_cycle=streak_anchor,
            )
            qualified = current_individual[
                current_individual['Streak Length'] >= active_vote_streak_min_cycles
            ].copy()
            if not qualified.empty:
                ranked_streaks = assign_ranks_with_ties(qualified, 'Streak Length', 'Balloter Name')
                md.append("| Rank | Balloter Name | Streak Length | Streak Start | Streak End |")
                md.append("|------|---------------|--------------|--------------|------------|")
                for _, row in ranked_streaks.iterrows():
                    rank = int(row['Rank'])
                    name = row['Balloter Name'] if pd.notnull(row['Balloter Name']) else "Unknown"
                    streak = int(row['Streak Length'])
                    streak_start = str(row['Streak Start']) if pd.notnull(row['Streak Start']) else "N/A"
                    streak_end = str(row['Streak End']) if pd.notnull(row['Streak End']) else "N/A"
                    md.append(f"| {rank} | {name} | {format_count(streak)} | {streak_start} | {streak_end} |")
            else:
                md.append("No voters meet the minimum ongoing streak length for this section.")

            md.append("")
            md.append('<a id="ongoing-active-vote-streaks-organization"></a>\n')
            md.append(f"#### 🏆 Ongoing Active Vote Streaks ({n}+ cycles) - Organization\n")
            md.append(
                "**Terminology:** Same as the Individual section above: **Active vote** means Affirmative or "
                "Negative (not Abstain). **Ongoing streak** means consecutive ballot cycles where **at least one** "
                "person from that organization cast an active vote in each cycle, continuing through the **last "
                "ballot cycle in the primary analysis period** (same anchor as the Individual table). "
                "Votes in later cycles are ignored. "
                f"**All** organizations with an ongoing streak of **{format_count(n)}** or more consecutive "
                "ballot cycles are listed (not limited to the top ten).\n"
            )
            md.append(
                f"> **Organization column:** `{org_col}` (same as other organization leaderboards in this report).\n"
            )
            md.append("")
            current_org = calculate_current_active_vote_streak(
                closed_merged_df,
                all_cycles_df,
                org_col,
                org_col,
                'Ballot Cycle',
                streak_end_cycle=streak_anchor,
            )
            qualified_org = current_org[
                current_org['Streak Length'] >= active_vote_streak_min_cycles
            ].copy()
            if not qualified_org.empty:
                ranked_org = assign_ranks_with_ties(qualified_org, 'Streak Length', org_col)
                md.append("| Rank | Organization | Streak Length | Streak Start | Streak End |")
                md.append("|------|-------------|--------------|--------------|------------|")
                for _, row in ranked_org.iterrows():
                    rank = int(row['Rank'])
                    org = row[org_col] if pd.notnull(row[org_col]) else "Unknown"
                    streak = int(row['Streak Length'])
                    streak_start = str(row['Streak Start']) if pd.notnull(row['Streak Start']) else "N/A"
                    streak_end = str(row['Streak End']) if pd.notnull(row['Streak End']) else "N/A"
                    md.append(f"| {rank} | {org} | {format_count(streak)} | {streak_start} | {streak_end} |")
            else:
                md.append("No organizations meet the minimum ongoing streak length for this section.")
        md.append("")

    # Top 10+ Longest Active Vote Streak - Individual
    md.append("#### 🏆 Top 10+ Longest Active Vote Streak - Individual\n")
    md.append("Includes Affirmative and Negative votes.\n")
    md.append(
        "> **Note:** This is the **longest** run of consecutive ballot cycles with an active vote "
        "anywhere in the dataset—not necessarily an ongoing streak through the latest cycle.\n"
    )
    md.append("")
    # Use all_cycles_df to determine cycle order, but closed_merged_df for votes
    individual_streaks = calculate_active_vote_streak(
        closed_merged_df,  # Only votes from closed ballots
        all_cycles_df,     # All cycles (including open) to determine consecutive order
        'Balloter Key',
        'Balloter Name',
        'Ballot Cycle'
    )

    if not individual_streaks.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_streaks = assign_ranks_with_ties(individual_streaks, 'Streak Length', 'Balloter Name')

        # Include all rows that tie with rank 10 or better
        # Get the value at position 10 (index 9) to include all ties
        if len(ranked_streaks) >= 10:
            # Get the value at the 10th position (index 9)
            rank_10_value = ranked_streaks.iloc[9]['Streak Length']
            # Include all entries with this value or better (to include all ties)
            display_streaks = ranked_streaks[ranked_streaks['Streak Length'] >= rank_10_value].copy()
        else:
            display_streaks = ranked_streaks.copy()

        md.append("| Rank | Balloter Name | Streak Length | Streak Start | Streak End |")
        md.append("|------|---------------|--------------|--------------|------------|")
        for _, row in display_streaks.iterrows():
            rank = int(row['Rank'])
            name = row['Balloter Name'] if pd.notnull(row['Balloter Name']) else "Unknown"
            streak = int(row['Streak Length'])
            streak_start = str(row['Streak Start']) if pd.notnull(row['Streak Start']) else "N/A"
            streak_end = str(row['Streak End']) if pd.notnull(row['Streak End']) else "N/A"
            md.append(f"| {rank} | {name} | {format_count(streak)} | {streak_start} | {streak_end} |")
    else:
        md.append("No data available.")
    md.append("")

    # Top 10+ Longest Active Vote Streak - Organization
    md.append("#### 🏆 Top 10+ Longest Active Vote Streak - Organization\n")
    md.append("Includes Affirmative and Negative votes.\n")
    md.append("")
    # Use all_cycles_df to determine cycle order, but closed_merged_df for votes
    org_streaks = calculate_active_vote_streak(
        closed_merged_df,  # Only votes from closed ballots
        all_cycles_df,     # All cycles (including open) to determine consecutive order
        org_col,
        org_col,
        'Ballot Cycle'
    )
    
    if not org_streaks.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_streaks = assign_ranks_with_ties(org_streaks, 'Streak Length', org_col)
        
        # Include all rows that tie with rank 10 or better
        # Get the value at position 10 (index 9) to include all ties
        if len(ranked_streaks) >= 10:
            # Get the value at the 10th position (index 9)
            rank_10_value = ranked_streaks.iloc[9]['Streak Length']
            # Include all entries with this value or better (to include all ties)
            display_streaks = ranked_streaks[ranked_streaks['Streak Length'] >= rank_10_value].copy()
        else:
            display_streaks = ranked_streaks.copy()
        
        md.append("| Rank | Organization | Streak Length | Streak Start | Streak End |")
        md.append("|------|-------------|--------------|--------------|------------|")
        for _, row in display_streaks.iterrows():
            rank = int(row['Rank'])
            org = row[org_col] if pd.notnull(row[org_col]) else "Unknown"
            streak = int(row['Streak Length'])
            streak_start = str(row['Streak Start']) if pd.notnull(row['Streak Start']) else "N/A"
            streak_end = str(row['Streak End']) if pd.notnull(row['Streak End']) else "N/A"
            md.append(f"| {rank} | {org} | {format_count(streak)} | {streak_start} | {streak_end} |")
    else:
        md.append("No data available.")
    md.append("")
    
    # Top 10+ Longest Any Vote Streak - Individual (includes Abstain)
    md.append("#### 🎖️ Top 10+ Longest Any Vote Streak - Individual\n")
    md.append("Includes Affirmative, Negative, and Abstain votes.\n")
    md.append("")
    # Use all_cycles_df to determine cycle order, but closed_merged_df for votes
    individual_any_streaks = calculate_any_vote_streak(
        closed_merged_df,  # Only votes from closed ballots
        all_cycles_df,     # All cycles (including open) to determine consecutive order
        'Balloter Key', 
        'Balloter Name',
        'Ballot Cycle'
    )
    
    if not individual_any_streaks.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_streaks = assign_ranks_with_ties(individual_any_streaks, 'Streak Length', 'Balloter Name')
        
        # Include all rows that tie with rank 10 or better
        # Get the value at position 10 (index 9) to include all ties
        if len(ranked_streaks) >= 10:
            # Get the value at the 10th position (index 9)
            rank_10_value = ranked_streaks.iloc[9]['Streak Length']
            # Include all entries with this value or better (to include all ties)
            display_streaks = ranked_streaks[ranked_streaks['Streak Length'] >= rank_10_value].copy()
        else:
            display_streaks = ranked_streaks.copy()
        
        md.append("| Rank | Balloter Name | Streak Length | Streak Start | Streak End |")
        md.append("|------|---------------|--------------|--------------|------------|")
        for _, row in display_streaks.iterrows():
            rank = int(row['Rank'])
            name = row['Balloter Name'] if pd.notnull(row['Balloter Name']) else "Unknown"
            streak = int(row['Streak Length'])
            streak_start = str(row['Streak Start']) if pd.notnull(row['Streak Start']) else "N/A"
            streak_end = str(row['Streak End']) if pd.notnull(row['Streak End']) else "N/A"
            md.append(f"| {rank} | {name} | {format_count(streak)} | {streak_start} | {streak_end} |")
    else:
        md.append("No data available.")
    md.append("")
    
    # Top 10+ Longest Any Vote Streak - Organization (includes Abstain)
    md.append("#### 🎖️ Top 10+ Longest Any Vote Streak - Organization\n")
    md.append("Includes Affirmative, Negative, and Abstain votes.\n")
    md.append("")
    # Use all_cycles_df to determine cycle order, but closed_merged_df for votes
    org_any_streaks = calculate_any_vote_streak(
        closed_merged_df,  # Only votes from closed ballots
        all_cycles_df,     # All cycles (including open) to determine consecutive order
        org_col,
        org_col,
        'Ballot Cycle'
    )
    
    if not org_any_streaks.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_streaks = assign_ranks_with_ties(org_any_streaks, 'Streak Length', org_col)
        
        # Include all rows that tie with rank 10 or better
        # Get the value at position 10 (index 9) to include all ties
        if len(ranked_streaks) >= 10:
            # Get the value at the 10th position (index 9)
            rank_10_value = ranked_streaks.iloc[9]['Streak Length']
            # Include all entries with this value or better (to include all ties)
            display_streaks = ranked_streaks[ranked_streaks['Streak Length'] >= rank_10_value].copy()
        else:
            display_streaks = ranked_streaks.copy()
        
        md.append("| Rank | Organization | Streak Length | Streak Start | Streak End |")
        md.append("|------|-------------|--------------|--------------|------------|")
        for _, row in display_streaks.iterrows():
            rank = int(row['Rank'])
            org = row[org_col] if pd.notnull(row[org_col]) else "Unknown"
            streak = int(row['Streak Length'])
            streak_start = str(row['Streak Start']) if pd.notnull(row['Streak Start']) else "N/A"
            streak_end = str(row['Streak End']) if pd.notnull(row['Streak End']) else "N/A"
            md.append(f"| {rank} | {org} | {format_count(streak)} | {streak_start} | {streak_end} |")
    else:
        md.append("No data available.")
    md.append("")
    
    # Top 10+ Most Active Votes Cast - Individual
    md.append("#### 🎯 Top 10+ Most Active Votes Cast - Individual\n")
    
    # Debug: Check if we have any active votes in closed ballots
    if 'Is Active Vote' in closed_merged_df.columns:
        total_active_in_closed = closed_merged_df['Is Active Vote'].sum()
        unique_balloters_with_active = closed_merged_df[closed_merged_df['Is Active Vote']]['Balloter Name'].nunique() if 'Balloter Name' in closed_merged_df.columns else 0
        # Debug output (commented out for production, but useful for troubleshooting)
        # print(f"DEBUG: Total active votes in closed ballots: {total_active_in_closed}")
        # print(f"DEBUG: Unique balloters with active votes in closed ballots: {unique_balloters_with_active}")
    
    individual_counts = calculate_most_active_votes(
        closed_merged_df,
        'Balloter Key',
        'Balloter Name'
    )
    
    if not individual_counts.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_counts = assign_ranks_with_ties(individual_counts, 'Active Vote Count', 'Balloter Name')
        
        # Include all rows that tie with rank 10 or better
        # Get the value at position 10 (index 9) to include all ties
        if len(ranked_counts) >= 10:
            # Get the value at the 10th position (index 9)
            rank_10_value = ranked_counts.iloc[9]['Active Vote Count']
            # Include all entries with this value or better (to include all ties)
            display_counts = ranked_counts[ranked_counts['Active Vote Count'] >= rank_10_value].copy()
        else:
            display_counts = ranked_counts.copy()
        
        md.append("| Rank | Balloter Name | Active Vote Count |")
        md.append("|------|---------------|------------------|")
        for _, row in display_counts.iterrows():
            rank = int(row['Rank'])
            name = row['Balloter Name'] if pd.notnull(row['Balloter Name']) else "Unknown"
            count = int(row['Active Vote Count'])
            md.append(f"| {rank} | {name} | {format_count(count)} |")
    else:
        md.append("No data available.")
    md.append("")
    
    # Top 10+ Most Active Votes Cast - Organization
    md.append("#### 🎯 Top 10+ Most Active Votes Cast - Organization\n")
    org_counts = calculate_most_active_votes(
        closed_merged_df,
        org_col,
        org_col
    )
    
    if not org_counts.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_counts = assign_ranks_with_ties(org_counts, 'Active Vote Count', org_col)
        
        # Include all rows that tie with rank 10 or better
        # Get the value at position 10 (index 9) to include all ties
        if len(ranked_counts) >= 10:
            # Get the value at the 10th position (index 9)
            rank_10_value = ranked_counts.iloc[9]['Active Vote Count']
            # Include all entries with this value or better (to include all ties)
            display_counts = ranked_counts[ranked_counts['Active Vote Count'] >= rank_10_value].copy()
        else:
            display_counts = ranked_counts.copy()
        
        md.append("| Rank | Organization | Active Vote Count |")
        md.append("|------|-------------|------------------|")
        for _, row in display_counts.iterrows():
            rank = int(row['Rank'])
            org = row[org_col] if pd.notnull(row[org_col]) else "Unknown"
            count = int(row['Active Vote Count'])
            md.append(f"| {rank} | {org} | {format_count(count)} |")
    else:
        md.append("No data available.")
    md.append("")
    
    # Top 10+ Most Consensus Groups with Active Participation - Individual
    md.append("#### 🎯 Top 10+ Most Consensus Groups with Active Participation - Individual\n")
    md.append("Counts unique Consensus Groups (BALDEFs) where the individual cast active votes (Affirmative or Negative).\n")
    md.append("")
    
    individual_cg_counts = calculate_most_consensus_groups_with_active_participation(
        closed_merged_df,
        'Balloter Key',
        'Balloter Name'
    )
    
    if not individual_cg_counts.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_cg_counts = assign_ranks_with_ties(individual_cg_counts, 'Consensus Groups Count', 'Balloter Name')
        
        # Include all rows that tie with rank 10 or better
        if len(ranked_cg_counts) >= 10:
            rank_10_value = ranked_cg_counts.iloc[9]['Consensus Groups Count']
            display_cg_counts = ranked_cg_counts[ranked_cg_counts['Consensus Groups Count'] >= rank_10_value].copy()
        else:
            display_cg_counts = ranked_cg_counts.copy()
        
        md.append("| Rank | Balloter Name | Consensus Groups Count |")
        md.append("|------|---------------|------------------------|")
        for _, row in display_cg_counts.iterrows():
            rank = int(row['Rank'])
            name = row['Balloter Name'] if pd.notnull(row['Balloter Name']) else "Unknown"
            count = int(row['Consensus Groups Count'])
            md.append(f"| {rank} | {name} | {format_count(count)} |")
    else:
        md.append("No data available.")
    md.append("")
    
    # Top 10+ Most Consensus Groups with Active Participation - Organization
    md.append("#### 🎯 Top 10+ Most Consensus Groups with Active Participation - Organization\n")
    md.append("Counts unique Consensus Groups (BALDEFs) where the organization cast active votes (Affirmative or Negative).\n")
    md.append("")
    
    org_cg_counts = calculate_most_consensus_groups_with_active_participation(
        closed_merged_df,
        org_col,
        org_col
    )
    
    if not org_cg_counts.empty:
        # Assign ranks with proper tie handling and alphabetical sorting
        ranked_cg_counts = assign_ranks_with_ties(org_cg_counts, 'Consensus Groups Count', org_col)
        
        # Include all rows that tie with rank 10 or better
        if len(ranked_cg_counts) >= 10:
            rank_10_value = ranked_cg_counts.iloc[9]['Consensus Groups Count']
            display_cg_counts = ranked_cg_counts[ranked_cg_counts['Consensus Groups Count'] >= rank_10_value].copy()
        else:
            display_cg_counts = ranked_cg_counts.copy()
        
        md.append("| Rank | Organization | Consensus Groups Count |")
        md.append("|------|-------------|------------------------|")
        for _, row in display_cg_counts.iterrows():
            rank = int(row['Rank'])
            org = row[org_col] if pd.notnull(row[org_col]) else "Unknown"
            count = int(row['Consensus Groups Count'])
            md.append(f"| {rank} | {org} | {format_count(count)} |")
    else:
        md.append("No data available.")
    md.append("")
    
    return md

def generate_summary_by_analysis_period(merged_df, baldef_df, analysis_periods, data_gathering_date=None):
    """
    Generate summary by analysis period showing cycles, consensus groups, and enrollment.
    
    Args:
        merged_df: DataFrame with merged ballot participation data
        baldef_df: DataFrame with BALDEF data
        analysis_periods: List of period strings (e.g., ['2025', '2025T1'])
        data_gathering_date: Optional timestamp for footnotes (open-ballot handling is already
            applied in merged_df / baldef_df before this runs).
    
    Returns:
        List of markdown strings
    """
    md = []
    
    md.append("## Summary by Analysis Period\n")
    md.append("")
    
    # Filter out open ballots for calculations
    if 'Is Open Ballot' in merged_df.columns:
        is_open = is_open_ballot_mask(merged_df['Is Open Ballot'])
        closed_merged_df = merged_df[~is_open].copy()
    else:
        closed_merged_df = merged_df.copy()
    
    if 'Is Open Ballot' in baldef_df.columns:
        is_open = is_open_ballot_mask(baldef_df['Is Open Ballot'])
        closed_baldef_df = baldef_df[~is_open].copy()
    else:
        closed_baldef_df = baldef_df.copy()
    
    # Process each analysis period
    for period_str in analysis_periods:
        start_date, end_date, label = parse_time_period(period_str)
        
        md.append(f"### Summary for {label}\n")
        md.append("")
        
        # Find cycles that fall within this period
        # Cycles are in YYYYMM format, so we need to check if the cycle's close date falls within the period
        period_cycles = []
        for cycle in closed_baldef_df['Ballot Cycle'].dropna().unique():
            # Get the close dates for this cycle
            cycle_baldefs = closed_baldef_df[closed_baldef_df['Ballot Cycle'] == cycle]
            if len(cycle_baldefs) > 0:
                # Use the latest close date for this cycle to determine if it's in the period
                cycle_close_date = cycle_baldefs['Ballot Close Date'].max()
                if pd.notna(cycle_close_date) and start_date <= cycle_close_date <= end_date:
                    period_cycles.append(cycle)
        
        # Sort cycles
        period_cycles = sorted(period_cycles)
        
        if not period_cycles:
            md.append("No ballot cycles found in this period.\n")
            md.append("")
            continue
        
        # Build table data
        table_data = []
        for cycle in period_cycles:
            # Get BALDEF records for this cycle
            cycle_baldefs = closed_baldef_df[closed_baldef_df['Ballot Cycle'] == cycle]
            consensus_groups = len(cycle_baldefs)
            
            # Get all unique balloter keys for this cycle (regardless of vote type)
            cycle_votes = closed_merged_df[closed_merged_df['Ballot Cycle'] == cycle]
            total_enrollment = cycle_votes['Balloter Key'].nunique() if 'Balloter Key' in cycle_votes.columns else 0
            
            # Calculate average enrollment per Consensus Group
            # For each BALDEF, count unique balloter keys enrolled, then average across all BALDEFs
            enrollment_per_baldef = []
            for baldef_id in cycle_baldefs['BALDEF ID'].unique():
                baldef_votes = cycle_votes[cycle_votes['BALDEF ID'] == baldef_id]
                unique_enrolled = baldef_votes['Balloter Key'].nunique() if 'Balloter Key' in baldef_votes.columns else 0
                enrollment_per_baldef.append(unique_enrolled)
            
            avg_per_cg = sum(enrollment_per_baldef) / len(enrollment_per_baldef) if enrollment_per_baldef else 0
            
            table_data.append({
                'cycle': cycle,
                'consensus_groups': consensus_groups,
                'total_enrollment': total_enrollment,
                'avg_per_cg': avg_per_cg
            })
        
        # Generate enrollment table
        md.append("| Cycle | Consensus Groups (N) | Total Voter Enrollment (N) | Ave per CG |")
        md.append("|-------|---------------------|---------------------------|------------|")
        
        for row in table_data:
            cycle = row['cycle']
            cg_count = format_count(row['consensus_groups'])
            enrollment = format_count(row['total_enrollment'])
            avg = format_number(row['avg_per_cg'], decimals=1)
            md.append(f"| {cycle} | {cg_count} | {enrollment} | {avg} |")
        
        md.append("")
        
        # Build Active Voters table data
        active_voters_data = []
        rolling_averages = []  # Track for 1 Yr Rolling calculation
        
        for cycle in period_cycles:
            cycle_votes = closed_merged_df[closed_merged_df['Ballot Cycle'] == cycle]
            cycle_baldefs = closed_baldef_df[closed_baldef_df['Ballot Cycle'] == cycle]
            
            # 1. Active Voters (N) - unique balloter keys who cast active votes in this cycle
            active_voters = cycle_votes[cycle_votes['Is Active Vote']]['Balloter Key'].nunique() if 'Is Active Vote' in cycle_votes.columns else 0
            
            # 2. Active Voters (%) - overall percentage: active voters / total enrollment
            total_enrollment = cycle_votes['Balloter Key'].nunique() if 'Balloter Key' in cycle_votes.columns else 0
            active_voters_pct = (active_voters / total_enrollment * 100) if total_enrollment > 0 else 0
            
            # 4. Active Voter % per CG (Ave) - average of percentages calculated per BALDEF
            active_pct_per_baldef = []
            for baldef_id in cycle_baldefs['BALDEF ID'].unique():
                baldef_votes = cycle_votes[cycle_votes['BALDEF ID'] == baldef_id]
                baldef_enrollment = baldef_votes['Balloter Key'].nunique() if 'Balloter Key' in baldef_votes.columns else 0
                baldef_active = baldef_votes[baldef_votes['Is Active Vote']]['Balloter Key'].nunique() if 'Is Active Vote' in baldef_votes.columns else 0
                baldef_pct = (baldef_active / baldef_enrollment * 100) if baldef_enrollment > 0 else 0
                active_pct_per_baldef.append(baldef_pct)
            
            active_voter_pct_per_cg_ave = sum(active_pct_per_baldef) / len(active_pct_per_baldef) if active_pct_per_baldef else 0
            
            # 3. 1 Yr Rolling (Ave) - average of Active Voter % per CG (Ave) over last 3 cycles
            rolling_averages.append(active_voter_pct_per_cg_ave)
            # Keep only last 3 cycles for rolling average
            if len(rolling_averages) > 3:
                rolling_averages = rolling_averages[-3:]
            one_yr_rolling_ave = sum(rolling_averages) / len(rolling_averages) if rolling_averages else 0
            
            active_voters_data.append({
                'cycle': cycle,
                'active_voters_n': active_voters,
                'active_voters_pct': active_voters_pct,
                'one_yr_rolling_ave': one_yr_rolling_ave,
                'active_voter_pct_per_cg_ave': active_voter_pct_per_cg_ave
            })
        
        # Generate Active Voters table
        md.append(f"#### Active Voters for {label}\n")
        md.append("")
        md.append("| Cycle | Active Voters (N) | Active Voters (%) | Active Voter % per CG (Ave) | 1 Yr Rolling (Ave) |")
        md.append("|-------|------------------|-------------------|----------------------------|---------------------|")
        
        for row in active_voters_data:
            cycle = row['cycle']
            active_n = format_count(row['active_voters_n'])
            active_pct = format_number(row['active_voters_pct'], decimals=1)
            pct_per_cg = format_number(row['active_voter_pct_per_cg_ave'], decimals=1)
            rolling_ave = format_number(row['one_yr_rolling_ave'], decimals=1)
            md.append(f"| {cycle} | {active_n} | {active_pct}% | {pct_per_cg}% | {rolling_ave}% |")
        
        md.append("")
        md.append("> **Note:** The \"1 Yr Rolling (Ave)\" metric calculates the average of the \"Active Voter % per CG (Ave)\" over the last 3 ballot cycles. Since ballots are tri-annual (January, May, September), this represents approximately one year of ballot activity.\n")
        md.append("")
        
        # Build Breakdown by Consensus Group table
        breakdown_data = []
        for cycle in period_cycles:
            cycle_baldefs = closed_baldef_df[closed_baldef_df['Ballot Cycle'] == cycle]
            cycle_votes = closed_merged_df[closed_merged_df['Ballot Cycle'] == cycle]
            
            for _, baldef_row in cycle_baldefs.iterrows():
                baldef_id = baldef_row['BALDEF ID']
                specification = baldef_row.get('Specification', 'N/A') if pd.notna(baldef_row.get('Specification')) else 'N/A'
                specification_url = baldef_row.get('Specification URL', None)
                ballot_type = baldef_row.get('Ballot Type', 'N/A') if pd.notna(baldef_row.get('Ballot Type')) else 'N/A'
                
                # Get votes for this BALDEF
                baldef_votes = cycle_votes[cycle_votes['BALDEF ID'] == baldef_id]
                
                # Voter Enrollment (N) - unique balloter keys enrolled in this BALDEF
                voter_enrollment = baldef_votes['Balloter Key'].nunique() if 'Balloter Key' in baldef_votes.columns else 0
                
                # Active Voters (N) - unique balloter keys who cast active votes in this BALDEF
                active_voters = baldef_votes[baldef_votes['Is Active Vote']]['Balloter Key'].nunique() if 'Is Active Vote' in baldef_votes.columns else 0
                
                # Active Voters (%) - percentage of enrolled who cast active votes
                active_voters_pct = (active_voters / voter_enrollment * 100) if voter_enrollment > 0 else 0
                
                realm = baldef_row.get('Realm', 'N/A') if pd.notna(baldef_row.get('Realm')) else 'N/A'
                
                breakdown_data.append({
                    'cycle': cycle,
                    'baldef_id': baldef_id,
                    'specification': str(specification) if pd.notna(specification) else 'N/A',
                    'specification_url': specification_url,
                    'ballot_type': ballot_type,
                    'realm': str(realm) if pd.notna(realm) else 'N/A',
                    'voter_enrollment': voter_enrollment,
                    'active_voters': active_voters,
                    'active_voters_pct': active_voters_pct
                })
        
        # Sort by Cycle, then by Specification (A->Z)
        breakdown_data.sort(key=lambda x: (x['cycle'], x['specification']))
        
        # Generate Breakdown by Consensus Group table
        md.append(f"#### Breakdown by Consensus Group for {label}\n")
        md.append("")
        md.append("| Cycle | BALDEF ID | Specification | Realm | Ballot Type | Voter Enrollment (N) | Active Voters (N) | Active Voters (%) |")
        md.append("|-------|-----------|---------------|-------|-------------|----------------------|------------------|-------------------|")
        
        for row in breakdown_data:
            cycle = row['cycle']
            baldef_id = row['baldef_id']
            baldef_link = f"[{baldef_id}](https://jira.hl7.org/browse/{baldef_id})"
            specification = str(row['specification']) if pd.notna(row['specification']) else 'N/A'
            specification_url = row.get('specification_url')
            # Format specification as hyperlink if URL is available
            if specification_url and pd.notna(specification_url) and str(specification_url).strip():
                specification_display = f"[{specification}]({specification_url})"
            else:
                specification_display = specification
            realm = str(row['realm']) if pd.notna(row['realm']) else 'N/A'
            ballot_type = str(row['ballot_type']) if pd.notna(row['ballot_type']) else 'N/A'
            enrollment = format_count(row['voter_enrollment'])
            active_n = format_count(row['active_voters'])
            active_pct = format_number(row['active_voters_pct'], decimals=1)
            md.append(f"| {cycle} | {baldef_link} | {specification_display} | {realm} | {ballot_type} | {enrollment} | {active_n} | {active_pct}% |")
        
        md.append("")
        
        # Build Breakdown by Product Family table (aggregated across all cycles in period)
        # Collect all BALDEFs and votes for the entire period
        period_baldefs = closed_baldef_df[closed_baldef_df['Ballot Cycle'].isin(period_cycles)]
        period_votes = closed_merged_df[closed_merged_df['Ballot Cycle'].isin(period_cycles)]
        
        product_family_data = []
        
        # Group by Product Family across all cycles in the period
        if 'Product Family' in period_baldefs.columns:
            # Collect all Product Families (handling comma-separated values)
            product_families_set = set()
            baldef_to_pf = {}  # Map BALDEF ID to list of Product Families
            
            for _, baldef_row in period_baldefs.iterrows():
                baldef_id = baldef_row['BALDEF ID']
                pf_value = baldef_row.get('Product Family', '')
                
                if pd.notna(pf_value) and pf_value:
                    # Handle comma-separated Product Families
                    pf_list = [pf.strip() for pf in str(pf_value).split(',') if pf.strip()]
                    if pf_list:
                        baldef_to_pf[baldef_id] = pf_list
                        product_families_set.update(pf_list)
                    else:
                        baldef_to_pf[baldef_id] = ['N/A']
                        product_families_set.add('N/A')
                else:
                    baldef_to_pf[baldef_id] = ['N/A']
                    product_families_set.add('N/A')
            
            # Calculate stats for each Product Family (across all cycles in period)
            for product_family in sorted(product_families_set):
                # Get BALDEFs that have this Product Family
                pf_baldef_ids = set()
                for baldef_id, pf_list in baldef_to_pf.items():
                    if product_family in pf_list:
                        pf_baldef_ids.add(baldef_id)
                
                # Get votes for all BALDEFs in this Product Family (across all cycles)
                pf_votes = period_votes[period_votes['BALDEF ID'].isin(pf_baldef_ids)]
                
                # Voter Enrollment (N) - unique balloter keys enrolled across all BALDEFs in this Product Family
                voter_enrollment = pf_votes['Balloter Key'].nunique() if 'Balloter Key' in pf_votes.columns else 0
                
                # Active Voters (N) - unique balloter keys who cast active votes across all BALDEFs in this Product Family
                active_voters = pf_votes[pf_votes['Is Active Vote']]['Balloter Key'].nunique() if 'Is Active Vote' in pf_votes.columns else 0
                
                # Active Voters (%) - percentage of enrolled who cast active votes
                active_voters_pct = (active_voters / voter_enrollment * 100) if voter_enrollment > 0 else 0
                
                product_family_data.append({
                    'product_family': product_family,
                    'voter_enrollment': voter_enrollment,
                    'active_voters': active_voters,
                    'active_voters_pct': active_voters_pct
                })
        else:
            # If Product Family column doesn't exist, create a single "N/A" entry
            voter_enrollment = period_votes['Balloter Key'].nunique() if 'Balloter Key' in period_votes.columns else 0
            active_voters = period_votes[period_votes['Is Active Vote']]['Balloter Key'].nunique() if 'Is Active Vote' in period_votes.columns else 0
            active_voters_pct = (active_voters / voter_enrollment * 100) if voter_enrollment > 0 else 0
            
            product_family_data.append({
                'product_family': 'N/A',
                'voter_enrollment': voter_enrollment,
                'active_voters': active_voters,
                'active_voters_pct': active_voters_pct
            })
        
        # Sort by Product Family
        product_family_data.sort(key=lambda x: x['product_family'])
        
        # Generate Breakdown by Product Family table
        md.append(f"#### Breakdown by Product Family for {label}\n")
        md.append("")
        md.append("> **Note:** Active Voters counts unique individuals who cast active votes (Affirmative or Negative) on **any** BALDEF within that Product Family across all cycles in the period.\n")
        md.append("")
        md.append("| Product Family | Voter Enrollment (N) | Active Voters (N) | Active Voters (%) |")
        md.append("|----------------|----------------------|------------------|-------------------|")
        
        for row in product_family_data:
            product_family = row['product_family']
            enrollment = format_count(row['voter_enrollment'])
            active_n = format_count(row['active_voters'])
            active_pct = format_number(row['active_voters_pct'], decimals=1)
            md.append(f"| {product_family} | {enrollment} | {active_n} | {active_pct}% |")
        
        md.append("")
        
        # Build Breakdown by Realm table (aggregated across all cycles in period)
        realm_data = []
        
        # Group by Realm across all cycles in the period
        if 'Realm' in period_baldefs.columns:
            # Collect all Realms
            realms_set = set()
            baldef_to_realm = {}  # Map BALDEF ID to Realm
            
            for _, baldef_row in period_baldefs.iterrows():
                baldef_id = baldef_row['BALDEF ID']
                realm_value = baldef_row.get('Realm', '')
                
                if pd.notna(realm_value) and realm_value:
                    realm_str = str(realm_value).strip()
                    baldef_to_realm[baldef_id] = realm_str
                    realms_set.add(realm_str)
                else:
                    baldef_to_realm[baldef_id] = 'N/A'
                    realms_set.add('N/A')
            
            # Calculate stats for each Realm (across all cycles in period)
            for realm in sorted(realms_set):
                # Get BALDEFs that have this Realm
                realm_baldef_ids = set()
                for baldef_id, realm_val in baldef_to_realm.items():
                    if realm_val == realm:
                        realm_baldef_ids.add(baldef_id)
                
                # Get votes for all BALDEFs in this Realm (across all cycles)
                realm_votes = period_votes[period_votes['BALDEF ID'].isin(realm_baldef_ids)]
                
                # Voter Enrollment (N) - unique balloter keys enrolled across all BALDEFs in this Realm
                voter_enrollment = realm_votes['Balloter Key'].nunique() if 'Balloter Key' in realm_votes.columns else 0
                
                # Active Voters (N) - unique balloter keys who cast active votes across all BALDEFs in this Realm
                active_voters = realm_votes[realm_votes['Is Active Vote']]['Balloter Key'].nunique() if 'Is Active Vote' in realm_votes.columns else 0
                
                # Active Voters (%) - percentage of enrolled who cast active votes
                active_voters_pct = (active_voters / voter_enrollment * 100) if voter_enrollment > 0 else 0
                
                realm_data.append({
                    'realm': realm,
                    'voter_enrollment': voter_enrollment,
                    'active_voters': active_voters,
                    'active_voters_pct': active_voters_pct
                })
        else:
            # If Realm column doesn't exist, create a single "N/A" entry
            voter_enrollment = period_votes['Balloter Key'].nunique() if 'Balloter Key' in period_votes.columns else 0
            active_voters = period_votes[period_votes['Is Active Vote']]['Balloter Key'].nunique() if 'Is Active Vote' in period_votes.columns else 0
            active_voters_pct = (active_voters / voter_enrollment * 100) if voter_enrollment > 0 else 0
            
            realm_data.append({
                'realm': 'N/A',
                'voter_enrollment': voter_enrollment,
                'active_voters': active_voters,
                'active_voters_pct': active_voters_pct
            })
        
        # Sort by Realm
        realm_data.sort(key=lambda x: x['realm'])
        
        # Generate Breakdown by Realm table
        md.append(f"#### Breakdown by Realm for {label}\n")
        md.append("")
        md.append("> **Note:** Active Voters counts unique individuals who cast active votes (Affirmative or Negative) on **any** BALDEF within that Realm across all cycles in the period.\n")
        md.append("")
        md.append("| Realm | Voter Enrollment (N) | Active Voters (N) | Active Voters (%) |")
        md.append("|-------|----------------------|------------------|-------------------|")
        
        for row in realm_data:
            realm = row['realm']
            enrollment = format_count(row['voter_enrollment'])
            active_n = format_count(row['active_voters'])
            active_pct = format_number(row['active_voters_pct'], decimals=1)
            md.append(f"| {realm} | {enrollment} | {active_n} | {active_pct}% |")
        
        md.append("")
    
    return md

def generate_report(baldef_df, ballot_df, merged_df, analysis_periods, open_ballots_count, excluded_pre_2022_count, excluded_affiliate_count, data_gathering_date=None, balloter_key=None, organization=None, active_vote_streak_min_cycles=None):
    """
    Generate full markdown report
    
    Args:
        organization: Optional string or list of strings - organization filter(s) applied
    """
    """Generate full markdown report"""
    md = []
    
    # Title
    md.append("# Ballot Participation Summary Report\n")
    
    # Get primary period for title
    primary_period = analysis_periods[0]
    start_date, end_date, label = parse_time_period(primary_period)
    human_readable_period = f"{start_date.strftime('%B %d, %Y')} to {end_date.strftime('%B %d, %Y')}"
    
    md.append(f"> **Analysis Period:** {human_readable_period}\n")
    md.append("")
    md.append("> **Note:** Starting in January 2022, all HL7 ballots except Reaffirmation and Withdrawal Ballots are conducted using Jira Balloting. This analysis is limited to HL7 balloting in Jira.\n")
    md.append("")
    
    # Add filter notice if applicable
    if balloter_key:
        # Get the balloter name from the data
        balloter_name = merged_df['Balloter Name'].iloc[0] if len(merged_df) > 0 and 'Balloter Name' in merged_df.columns else balloter_key
        md.append(f"> **🔍 FILTERED ANALYSIS:** This report is filtered to show data for **{balloter_name}** (Balloter Key: {balloter_key}) only.\n")
        md.append("")
    elif organization:
        # Normalize organization to a list for display
        if isinstance(organization, str):
            org_list = [organization]
        else:
            org_list = organization
        
        if len(org_list) == 1:
            md.append(f"> **🔍 FILTERED ANALYSIS:** This report is filtered to show data for **{org_list[0]}** only.\n")
        else:
            org_display = ', '.join(f"**{org}**" for org in org_list)
            md.append(f"> **🔍 FILTERED ANALYSIS:** This report is filtered to show data for {org_display} (combined).\n")
        md.append("")
    
    # Table of Contents
    md.append("## Table of Contents\n")
    md.append("- [How to Read This Report](#how-to-read-this-report)")
    md.append("- [Overall Summary for Dataset](#overall-summary-for-dataset)")
    md.append("  - [All Time Leaderboards](#all-time-leaderboards)")
    if active_vote_streak_min_cycles is not None:
        n = active_vote_streak_min_cycles
        md.append(
            f"    - [Ongoing Active Vote Streaks ({n}+ cycles) - Individual](#ongoing-active-vote-streaks-individual)"
        )
        md.append(
            f"    - [Ongoing Active Vote Streaks ({n}+ cycles) - Organization](#ongoing-active-vote-streaks-organization)"
        )
    md.append("    - [Top 10+ Longest Active Vote Streak - Individual](#-top-10-longest-active-vote-streak---individual)")
    md.append("    - [Top 10+ Longest Active Vote Streak - Organization](#-top-10-longest-active-vote-streak---organization)")
    md.append("    - [Top 10+ Longest Any Vote Streak - Individual](#-top-10-longest-any-vote-streak---individual)")
    md.append("    - [Top 10+ Longest Any Vote Streak - Organization](#-top-10-longest-any-vote-streak---organization)")
    md.append("    - [Top 10+ Most Active Votes Cast - Individual](#-top-10-most-active-votes-cast---individual)")
    md.append("    - [Top 10+ Most Active Votes Cast - Organization](#-top-10-most-active-votes-cast---organization)")
    md.append("    - [Top 10+ Most Consensus Groups with Active Participation - Individual](#-top-10-most-consensus-groups-with-active-participation---individual)")
    md.append("    - [Top 10+ Most Consensus Groups with Active Participation - Organization](#-top-10-most-consensus-groups-with-active-participation---organization)")
    md.append("- [Summary by Analysis Period](#summary-by-analysis-period)")
    md.append("")
    
    # How to Read This Report
    md.append("## How to Read This Report\n")
    md.append("### Scope\n")
    md.append("Starting in January 2022, all HL7 ballots except Reaffirmation and Withdrawal Ballots are conducted using Jira Balloting. This analysis is limited to HL7 balloting in Jira.\n")
    md.append("")
    md.append("### Terminology\n")
    md.append("- **Ballot Cycle**: The Ballot Period field, formatted as YYYYMM (e.g., 202509 for September 2025)")
    md.append("- **Consensus Group**: Each ballot definition identified by a BALDEF ID")
    md.append("- **Vote**: A record in the ballot participation data with a BALLOT ID")
    md.append("- **Casting a Vote**: A BALLOT ID where the Vote field has a value other than Null or \"No Vote\"")
    md.append("- **Active Vote**: A BALLOT ID where the Vote field is \"Affirmative\" or \"Negative\"")
    md.append(
        "- **Open Ballot**: A ballot that had not yet closed at the time the data was gathered "
        "(Ballot Close Date is after the data-gathering date). Excluded from most metrics so "
        "counts reflect completed ballots only."
    )
    md.append("")
    
    md.append("### Vote Types\n")
    md.append("- **Affirmative**: Vote in favor of the ballot")
    md.append("- **Negative**: Vote against the ballot")
    md.append("- **Abstain**: Vote indicating abstention")
    md.append("- **No Vote**: No vote was cast")
    md.append("")
    
    # Overall Summary
    md.extend(generate_overall_summary(baldef_df, ballot_df, merged_df, open_ballots_count, excluded_pre_2022_count, excluded_affiliate_count, data_gathering_date))
    
    # Leaderboards - pass baldef_df for all cycles (to determine cycle order including open ballots)
    # and merged_df will be filtered inside generate_leaderboards to exclude open ballot votes
    md.extend(
        generate_leaderboards(
            merged_df,
            baldef_df,
            active_vote_streak_min_cycles=active_vote_streak_min_cycles,
            analysis_period_str=analysis_periods[0] if analysis_periods else None,
        )
    )
    
    # Summary by Analysis Period
    md.extend(generate_summary_by_analysis_period(merged_df, baldef_df, analysis_periods, data_gathering_date))
    
    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(
        description="Analyze ballot participation data and generate a markdown summary report."
    )
    parser.add_argument(
        "--baldef-csv",
        required=True,
        help="Path to BALDEF CSV file (baldef_data.csv)"
    )
    parser.add_argument(
        "--ballot-csv",
        required=True,
        help="Path to ballot participation CSV file (ballot_participation.csv)"
    )
    parser.add_argument(
        "-o", "--output",
        required=True,
        help="Output Markdown file path"
    )
    parser.add_argument(
        "-p", "--periods",
        required=True,
        nargs="+",
        help="Analysis periods in format 'YYYY' (full year) or 'YYYYT[1-3]' (period)"
    )
    parser.add_argument(
        "--data-gathering-date",
        metavar="YYYY-MM-DD",
        help=(
            "Moment when the CSV export was taken ('as of' date). Any ballot whose Ballot Close Date "
            "is after this is treated as open and excluded from most metrics (totals, leaderboards, "
            "etc.). If omitted, a timestamp is inferred from the input CSV filenames when possible; "
            "otherwise no ballots are marked open."
        ),
    )
    parser.add_argument(
        "--balloter",
        help="Filter analysis to a specific balloter by Balloter Key (e.g., --balloter lloyd)"
    )
    parser.add_argument(
        "--org",
        "--organization",
        dest="organization",
        nargs="+",
        help='Filter analysis to one or more organizations (e.g., --org "Dogwood Health Consulting Inc." or --org "Org1" "Org2"). Useful when an organization is acquired over time.'
    )
    parser.add_argument(
        "--realm-mapping",
        dest="realm_mapping_file",
        help='Path to realm mapping CSV file for lookup and cache (optional, default: data/working/cache/realm_cache.csv)'
    )
    parser.add_argument(
        "--active-vote-streak-min-cycles",
        type=int,
        metavar="N",
        help=(
            "If set, add 'Ongoing Active Vote Streaks (N+ cycles) - Individual' and "
            "'Ongoing Active Vote Streaks (N+ cycles) - Organization': list every voter and every organization "
            "whose ongoing streak of active votes (Affirmative or Negative; not Abstain) through the end of the "
            "primary -p period is at least N consecutive ballot cycles (later cycles ignored). For organizations, "
            "at least one active vote from a member in each cycle counts. Omit to skip."
        ),
    )
    
    args = parser.parse_args()
    if args.active_vote_streak_min_cycles is not None and args.active_vote_streak_min_cycles < 1:
        parser.error("--active-vote-streak-min-cycles must be at least 1")
    
    # Validate that only one filter is specified
    if args.balloter and args.organization:
        parser.error("--balloter and --org cannot be used together. Please specify only one filter.")
    
    # Determine data gathering date
    data_gathering_date = None
    if args.data_gathering_date:
        try:
            data_gathering_date = pd.Timestamp(args.data_gathering_date, tz='UTC')
            print(f"Using provided data gathering date: {data_gathering_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
        except Exception as e:
            print(f"Warning: Could not parse data gathering date '{args.data_gathering_date}': {e}")
            print("Attempting to extract from filename...")
    
    # If not provided, try to extract from filename
    if data_gathering_date is None:
        # Try both CSV files
        for csv_file in [args.baldef_csv, args.ballot_csv]:
            timestamp = extract_timestamp_from_filename(csv_file)
            if timestamp is not None:
                data_gathering_date = timestamp
                print(f"Extracted data gathering date from filename: {data_gathering_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
                break
        
        if data_gathering_date is None:
            print("Warning: Could not determine data gathering date from filenames.")
            print("Open ballots will not be filtered. Use --data-gathering-date to specify.")
    else:
        print(f"Using data gathering date: {data_gathering_date.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    
    # Load data
    print(f"Loading BALDEF data from {args.baldef_csv}")
    try:
        baldef_df = pd.read_csv(
            args.baldef_csv,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True
        )
    except Exception as e:
        print(f"Warning: Could not read BALDEF CSV with explicit quoting parameters: {e}")
        print("Falling back to default CSV reading...")
        baldef_df = pd.read_csv(args.baldef_csv)
    
    print(f"Loading ballot participation data from {args.ballot_csv}")
    try:
        ballot_df = pd.read_csv(
            args.ballot_csv,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True
        )
    except Exception as e:
        print(f"Warning: Could not read ballot CSV with explicit quoting parameters: {e}")
        print("Falling back to default CSV reading...")
        ballot_df = pd.read_csv(args.ballot_csv)
    
    # Clean column names
    baldef_df.columns = baldef_df.columns.str.strip()
    ballot_df.columns = ballot_df.columns.str.strip()
    
    # Process data
    print("Processing data...")
    baldef_df, merged_df, open_ballots_count, excluded_pre_2022_count, excluded_affiliate_count = process_data(
        baldef_df, ballot_df, data_gathering_date, 
        balloter_key=args.balloter, 
        organization=args.organization,
        realm_mapping_file=args.realm_mapping_file
    )
    
    print(f"Processed {len(baldef_df)} BALDEF records (from January 2022 onwards)")
    if excluded_pre_2022_count > 0:
        print(f"Excluded {excluded_pre_2022_count} BALDEF record(s) from before January 2022")
    if excluded_affiliate_count > 0:
        print(f"Excluded {excluded_affiliate_count} BALDEF record(s) from HL7 affiliate pilots (HL7 Australia)")
    print(f"Processed {len(ballot_df)} ballot records")
    print(f"Merged data: {len(merged_df)} records")
    if open_ballots_count > 0:
        print(f"Found {open_ballots_count} open ballot(s) (excluded from metrics)")
    
    # Generate report
    print("Generating report...")
    report = generate_report(
        baldef_df, ballot_df, merged_df, args.periods, 
        open_ballots_count, excluded_pre_2022_count, excluded_affiliate_count, 
        data_gathering_date,
        balloter_key=args.balloter,
        organization=args.organization,
        active_vote_streak_min_cycles=args.active_vote_streak_min_cycles,
    )
    
    # Save report
    print(f"Writing report to {args.output}")
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)
        print(f"Created output directory: {output_dir}")
    
    with open(args.output, "w", encoding='utf-8') as f:
        f.write(report)
    
    print("Done!")

if __name__ == "__main__":
    main()
