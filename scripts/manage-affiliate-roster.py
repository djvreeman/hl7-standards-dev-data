#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

"""
Script to manage the HL7 affiliate roster CSV file.

This script:
1. Updates the affiliate list by fetching current affiliates from the website
2. Adds new affiliates and marks inactive ones
3. Updates Build Prefixes by analyzing the build server repos
4. Calculates Build Counts for each affiliate
"""

import csv
import subprocess
import sys
import os
import argparse
from datetime import datetime
from pathlib import Path
import re

# Default paths
DEFAULT_ROSTER_FILE = "data/working/affiliates/main-affiliate-roster.csv"
AFFILIATE_PARSER_SCRIPT = "scripts/parse-hl7-affiliates-from-web.py"
BUILDS_PARSER_SCRIPT = "scripts/parse-builds-web.py"
EXCLUSION_LIST_FILE = "data/working/affiliates/build-prefix-exclusions.txt"


def run_script(script_path, *args):
    """Run a Python script and return its output file path."""
    try:
        cmd = [sys.executable, script_path] + list(args)
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        # Try to extract the output file from the script's print statement
        # Most scripts print something like "X data rows have been written to path/to/file.csv"
        # or "Data has been written to: path/to/file.csv"
        for line in result.stdout.split('\n'):
            if 'written to' in line.lower() or 'has been written' in line.lower():
                # Extract file path from the output
                parts = line.split()
                for i, part in enumerate(parts):
                    if part.endswith('.csv'):
                        return part.strip()
        return None
    except subprocess.CalledProcessError as e:
        print(f"Warning: Error running {script_path}: {e.stderr}", file=sys.stderr)
        # Return None to indicate failure - caller should handle fallback
        return None


def read_csv_column(file_path, column_index=0):
    """Read a single column from a CSV file."""
    values = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and len(row) > column_index:
                value = row[column_index].strip()
                if value:  # Skip empty rows
                    values.append(value)
    return values


def read_roster(file_path):
    """Read the roster CSV and return as list of dictionaries."""
    roster = []
    with open(file_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            roster.append(row)
    return roster


def write_roster(file_path, roster, fieldnames):
    """Write the roster to CSV file."""
    with open(file_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(roster)


def normalize_affiliate_name(name):
    """Normalize affiliate name for comparison."""
    return name.strip().lower()


def match_build_prefix_to_affiliate(build_prefix, affiliate_name):
    """Try to match a build prefix to an affiliate. Returns True if they match."""
    prefix_lower = build_prefix.lower()
    affiliate_normalized = normalize_affiliate_name(affiliate_name)
    
    # Known mappings (prefix -> affiliate)
    known_mappings = {
        'interop-sante': 'hl7 france',
        'hl7au': 'hl7 australia',
        'hl7-be': 'hl7 belgium',
        'hl7-eu': 'hl7 europe',
        'hl7-it': 'hl7 italy',
        'hl7-pt': 'hl7 portugal',
        'hl7-uk': 'hl7 uk',
        'hl7-cz': 'hl7 czech republic',
        'hl7ch': 'hl7 switzerland',
        'hl7dk': 'hl7 denmark',
        'hl7nz': 'hl7 new zealand',
        'hl7austria': 'hl7 austria',
        'hl7chile': 'hl7 chile',
        'hl7ee': 'hl7 estonia',
        'hl7sweden': 'hl7 sweden',
        'hl7-canada': 'hl7 canada',
        'hl7-poland': 'hl7 poland',
    }
    
    # Check known mappings first
    if prefix_lower in known_mappings:
        return known_mappings[prefix_lower] == affiliate_normalized
    
    # Extract country/region name from affiliate (e.g., "HL7 Canada" -> "canada")
    country_match = re.search(r'hl7\s+(.+)$', affiliate_normalized)
    if not country_match:
        return False
    
    country = country_match.group(1).strip()
    
    # Check if prefix contains the country name (e.g., "HL7Austria" contains "austria")
    if country in prefix_lower:
        return True
    
    # Check common abbreviations
    country_abbrevs = {
        'australia': 'au',
        'austria': 'at',
        'belgium': 'be',
        'brazil': 'br',
        'canada': 'ca',
        'chile': 'cl',
        'china': 'cn',
        'colombia': 'co',
        'czech republic': 'cz',
        'denmark': 'dk',
        'france': 'fr',
        'germany': 'de',
        'italy': 'it',
        'japan': 'jp',
        'korea': 'kr',
        'mexico': 'mx',
        'netherlands': 'nl',
        'new zealand': 'nz',
        'norway': 'no',
        'poland': 'pl',
        'portugal': 'pt',
        'russia': 'ru',
        'spain': 'es',
        'sweden': 'se',
        'switzerland': 'ch',
        'taiwan': 'tw',
        'uk': 'uk',
        'united kingdom': 'uk',
    }
    
    if country in country_abbrevs:
        abbrev = country_abbrevs[country]
        # Check if prefix contains the abbreviation (e.g., "hl7au" contains "au")
        if abbrev in prefix_lower:
            return True
    
    # Check if prefix contains "hl7" and try various patterns
    if 'hl7' in prefix_lower:
        # Try patterns like "HL7Austria", "HL7-Austria", "hl7austria"
        # Remove spaces and hyphens from country for comparison
        country_clean = country.replace(' ', '').replace('-', '')
        prefix_clean = prefix_lower.replace('-', '').replace('_', '')
        
        # Check if prefix contains country name without spaces/hyphens
        if country_clean in prefix_clean:
            return True
        
        # Check patterns like "hl7-canada", "hl7canada", "hl7-can"
        patterns = [
            f'hl7-{country[:3]}',  # hl7-can
            f'hl7{country[:2]}',   # hl7ca
            f'hl7-{country}',      # hl7-canada
            f'hl7{country_clean}', # hl7canada
        ]
        for pattern in patterns:
            if pattern in prefix_lower:
                return True
    
    return False


def update_affiliate_list(roster_file, current_affiliates, verbose=False):
    """Update the roster with current affiliates from website."""
    roster = read_roster(roster_file)
    fieldnames = list(roster[0].keys()) if roster else ['Affiliate', 'Inactive', 'Package Root', 'Build Prefix', 'Build Count', 'Canonical Root', 'Home', 'Example', 'Notes']
    
    # Create a set of current affiliate names (normalized)
    current_affiliate_set = {normalize_affiliate_name(aff) for aff in current_affiliates}
    
    # Create a dictionary of existing affiliates by normalized name
    existing_affiliates = {}
    for row in roster:
        aff_name = row.get('Affiliate', '').strip()
        if aff_name:
            existing_affiliates[normalize_affiliate_name(aff_name)] = row
    
    # Track changes
    marked_inactive = []
    marked_active = []
    new_affiliates = []
    
    # Update existing affiliates: mark as inactive if not in current list
    for row in roster:
        aff_name = row.get('Affiliate', '').strip()
        if aff_name:
            normalized = normalize_affiliate_name(aff_name)
            was_inactive = row.get('Inactive', '').strip() == 'X'
            if normalized not in current_affiliate_set:
                row['Inactive'] = 'X'  # Mark as inactive
                if not was_inactive:
                    marked_inactive.append(aff_name)
            else:
                row['Inactive'] = ''  # Clear inactive flag
                if was_inactive:
                    marked_active.append(aff_name)
    
    # Add new affiliates
    for aff_name in current_affiliates:
        normalized = normalize_affiliate_name(aff_name)
        if normalized not in existing_affiliates:
            # Create new row
            new_row = {field: '' for field in fieldnames}
            new_row['Affiliate'] = aff_name
            roster.append(new_row)
            new_affiliates.append(aff_name)
    
    # Sort roster alphabetically by Affiliate name
    roster.sort(key=lambda x: normalize_affiliate_name(x.get('Affiliate', '')))
    
    # Print summary
    if verbose or marked_inactive or marked_active or new_affiliates:
        if marked_inactive:
            print(f"  Marked as inactive: {', '.join(marked_inactive)}")
        if marked_active:
            print(f"  Marked as active: {', '.join(marked_active)}")
        if new_affiliates:
            print(f"  Added new affiliates: {', '.join(new_affiliates)}")
        if not (marked_inactive or marked_active or new_affiliates):
            print("  No changes to affiliate list")
    
    return roster, fieldnames


def load_exclusion_list(exclusion_file):
    """Load exclusion patterns from a text file."""
    exclusion_patterns = []
    if os.path.exists(exclusion_file):
        with open(exclusion_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # Skip empty lines and comments
                if line and not line.startswith('#'):
                    exclusion_patterns.append(line.lower())
    return exclusion_patterns


def analyze_build_prefixes(build_repos_file):
    """Analyze build repos to extract build prefixes and counts."""
    build_prefixes = {}
    
    with open(build_repos_file, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and row[0]:
                repo_path = row[0].strip()
                # Extract build prefix (first part before "/")
                if '/' in repo_path:
                    build_prefix = repo_path.split('/')[0]
                    build_prefixes[build_prefix] = build_prefixes.get(build_prefix, 0) + 1
    
    return build_prefixes


def find_proposed_build_prefix_mappings(roster, build_prefixes, exclusion_file=EXCLUSION_LIST_FILE):
    """Find proposed build prefix mappings without applying them. Returns proposed mappings."""
    # Load exclusion patterns
    exclusion_patterns = load_exclusion_list(exclusion_file)
    
    # Create a mapping of build prefix to affiliate name
    prefix_to_affiliate = {}
    
    # First, check existing mappings in roster (these are already approved)
    for row in roster:
        affiliate = row.get('Affiliate', '').strip()
        existing_prefix = row.get('Build Prefix', '').strip()
        if existing_prefix:
            prefix_to_affiliate[existing_prefix] = affiliate
    
    # Try to match unmatched build prefixes to affiliates
    unmatched_prefixes = set(build_prefixes.keys()) - set(prefix_to_affiliate.keys())
    
    # Filter for HL7-related prefixes
    hl7_related_prefixes = []
    
    for prefix in unmatched_prefixes:
        prefix_lower = prefix.lower()
        
        # Exclude prefixes that match exclusion patterns
        if any(pattern in prefix_lower for pattern in exclusion_patterns):
            continue
        
        # Include if starts with "hl7" (e.g., "HL7-Canada", "hl7au", "HL7Austria", "hl7germany")
        # Known exceptions like "Interop-Sante" are already in the roster CSV, so we don't need
        # to hardcode them here - they'll be matched through the existing prefix_to_affiliate mapping
        if prefix_lower.startswith('hl7'):
            hl7_related_prefixes.append(prefix)
    
    # Track new matches
    proposed_mappings = []
    
    # Try to match HL7-related prefixes to affiliates
    for prefix in hl7_related_prefixes:
        best_match = None
        for row in roster:
            affiliate = row.get('Affiliate', '').strip()
            if not affiliate:
                continue
            
            # Skip if already has a build prefix (unless it's empty or the same)
            existing_prefix = row.get('Build Prefix', '').strip()
            if existing_prefix and existing_prefix != prefix:
                # Check if this affiliate already has a different prefix assigned
                if prefix_to_affiliate.get(existing_prefix) == affiliate:
                    continue
            
            if match_build_prefix_to_affiliate(prefix, affiliate):
                best_match = affiliate
                break
        
        if best_match:
            proposed_mappings.append({
                'prefix': prefix,
                'affiliate': best_match,
                'build_count': build_prefixes.get(prefix, 0),
                'existing_prefix': next((r.get('Build Prefix', '').strip() for r in roster if r.get('Affiliate', '').strip() == best_match), '')
            })
    
    return proposed_mappings


def display_proposed_mappings(proposed_mappings):
    """Display proposed mappings in a readable format."""
    if not proposed_mappings:
        print("  No new build prefix mappings found.")
        return
    
    print(f"\n  Found {len(proposed_mappings)} proposed build prefix mapping(s):")
    print("  " + "=" * 80)
    for i, mapping in enumerate(proposed_mappings, 1):
        existing = mapping['existing_prefix']
        prefix = mapping['prefix']
        affiliate = mapping['affiliate']
        count = mapping['build_count']
        
        if existing:
            print(f"  {i}. {affiliate}")
            print(f"     Current: {existing} -> Proposed: {prefix} ({count} repos)")
        else:
            print(f"  {i}. {affiliate}")
            print(f"     Proposed: {prefix} ({count} repos)")
    print("  " + "=" * 80)


def update_build_prefixes(roster, build_prefixes, verbose=False, apply_mappings=None, proposed_mappings=None, exclusion_file=EXCLUSION_LIST_FILE):
    """Update build prefixes and counts in the roster.
    
    Args:
        roster: The roster data
        build_prefixes: Dictionary of build prefix -> count
        verbose: Whether to print verbose output
        apply_mappings: List of proposed mappings to apply (if None, auto-applies all; if empty list, applies none)
        proposed_mappings: Pre-computed proposed mappings (optional, to avoid recomputing)
        exclusion_file: Path to exclusion list file
    """
    # Create a mapping of build prefix to affiliate name
    prefix_to_affiliate = {}
    
    # First, check existing mappings in roster
    for row in roster:
        affiliate = row.get('Affiliate', '').strip()
        existing_prefix = row.get('Build Prefix', '').strip()
        if existing_prefix:
            prefix_to_affiliate[existing_prefix] = affiliate
    
    # Get proposed mappings if not provided
    if proposed_mappings is None:
        proposed_mappings = find_proposed_build_prefix_mappings(roster, build_prefixes, exclusion_file)
    
    # Track new matches that will be applied
    new_matches = []
    
    # Apply mappings (either all or filtered by apply_mappings)
    if apply_mappings is None:
        # Apply all proposed mappings (default behavior)
        for mapping in proposed_mappings:
            prefix = mapping['prefix']
            affiliate = mapping['affiliate']
            prefix_to_affiliate[prefix] = affiliate
            new_matches.append((prefix, affiliate))
    elif isinstance(apply_mappings, list):
        # Apply only approved mappings (empty list means apply none)
        for mapping in apply_mappings:
            prefix = mapping['prefix']
            affiliate = mapping['affiliate']
            prefix_to_affiliate[prefix] = affiliate
            new_matches.append((prefix, affiliate))
    
    # Track updates
    prefix_updates = []
    count_updates = []
    
    # Update roster with build prefixes and counts
    for row in roster:
        affiliate = row.get('Affiliate', '').strip()
        if not affiliate:
            continue
        
        # Find all matching build prefixes for this affiliate
        matching_prefixes = []
        for prefix, aff in prefix_to_affiliate.items():
            if aff == affiliate:
                matching_prefixes.append(prefix)
        
        # Prefer existing prefix if it matches, otherwise use first match
        existing_prefix = row.get('Build Prefix', '').strip()
        old_count = row.get('Build Count', '').strip()
        
        if existing_prefix and existing_prefix in matching_prefixes:
            matching_prefix = existing_prefix
        elif matching_prefixes:
            matching_prefix = matching_prefixes[0]  # Use first match
        else:
            matching_prefix = None
        
        if matching_prefix:
            row['Build Prefix'] = matching_prefix
            new_count = str(build_prefixes.get(matching_prefix, 0))
            row['Build Count'] = new_count
            if matching_prefix != existing_prefix:
                prefix_updates.append(f"{affiliate}: {existing_prefix or '(none)'} -> {matching_prefix}")
            if new_count != old_count:
                count_updates.append(f"{affiliate}: {old_count or '0'} -> {new_count}")
        elif existing_prefix and existing_prefix in build_prefixes:
            # If no new match but existing prefix is in build list, update count
            new_count = str(build_prefixes[existing_prefix])
            row['Build Count'] = new_count
            if new_count != old_count:
                count_updates.append(f"{affiliate}: {old_count or '0'} -> {new_count}")
        elif existing_prefix:
            # Existing prefix but not in current build list, set count to 0
            row['Build Count'] = '0'
            if old_count != '0':
                count_updates.append(f"{affiliate}: {old_count} -> 0")
    
    # Print summary
    if verbose or new_matches or prefix_updates or count_updates:
        if new_matches:
            print(f"  New build prefix matches:")
            for prefix, affiliate in new_matches:
                print(f"    {prefix} -> {affiliate}")
        if prefix_updates:
            print(f"  Updated build prefixes:")
            for update in prefix_updates:
                print(f"    {update}")
        if count_updates:
            print(f"  Updated build counts:")
            for update in count_updates[:10]:  # Limit output
                print(f"    {update}")
            if len(count_updates) > 10:
                print(f"    ... and {len(count_updates) - 10} more")
        if not (new_matches or prefix_updates or count_updates):
            print("  No changes to build prefixes or counts")
    
    return roster


def main():
    parser = argparse.ArgumentParser(
        description='Manage HL7 affiliate roster: update affiliate list and build prefixes'
    )
    parser.add_argument(
        '-r', '--roster',
        default=DEFAULT_ROSTER_FILE,
        help=f'Path to the main affiliate roster CSV file (default: {DEFAULT_ROSTER_FILE})'
    )
    parser.add_argument(
        '--no-update-affiliates',
        action='store_true',
        help='Skip updating the affiliate list from website'
    )
    parser.add_argument(
        '--no-update-builds',
        action='store_true',
        help='Skip updating build prefixes and counts'
    )
    parser.add_argument(
        '--backup',
        action='store_true',
        help='Create a backup of the roster file before updating'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be changed without actually updating the roster file'
    )
    parser.add_argument(
        '--interactive',
        action='store_true',
        help='Interactively confirm build prefix mappings before applying'
    )
    
    args = parser.parse_args()
    
    # Ensure roster file exists
    if not os.path.exists(args.roster):
        print(f"Error: Roster file not found: {args.roster}", file=sys.stderr)
        sys.exit(1)
    
    # Create backup if requested
    if args.backup:
        backup_path = f"{args.roster}.backup.{datetime.now().strftime('%Y%m%d-%H%M%S')}"
        import shutil
        shutil.copy2(args.roster, backup_path)
        print(f"Created backup: {backup_path}")
    
    # Read current roster
    roster = read_roster(args.roster)
    fieldnames = list(roster[0].keys()) if roster else ['Affiliate', 'Inactive', 'Package Root', 'Build Prefix', 'Build Count', 'Canonical Root', 'Home', 'Example', 'Notes']
    
    # Step 1: Update affiliate list
    if not args.no_update_affiliates:
        print("Step 1: Fetching current affiliates from website...")
        try:
            affiliate_csv = run_script(AFFILIATE_PARSER_SCRIPT)
            if not affiliate_csv:
                # Try to construct the default path
                today_date = datetime.now().strftime("%Y%m%d")
                affiliate_csv = f"data/working/affiliates/{today_date}-affiliates.csv"
            
            # If script failed, try to find the most recent affiliate CSV file
            if not os.path.exists(affiliate_csv):
                affiliates_dir = "data/working/affiliates"
                if os.path.exists(affiliates_dir):
                    affiliate_files = sorted(Path(affiliates_dir).glob("*-affiliates.csv"), reverse=True)
                    if affiliate_files:
                        affiliate_csv = str(affiliate_files[0])
                        print(f"  Using existing file: {affiliate_csv}")
            
            if os.path.exists(affiliate_csv):
                current_affiliates = read_csv_column(affiliate_csv, 0)
                print(f"Found {len(current_affiliates)} current affiliates")
                
                roster, fieldnames = update_affiliate_list(args.roster, current_affiliates, verbose=True)
                print(f"Updated affiliate list: {len(roster)} total affiliates")
            else:
                print(f"Warning: Could not find affiliate CSV file: {affiliate_csv}", file=sys.stderr)
                print("  Skipping affiliate list update.", file=sys.stderr)
        except Exception as e:
            print(f"Error updating affiliate list: {e}", file=sys.stderr)
            if not args.no_update_builds:
                print("Continuing with build prefix update...")
    
    # Step 2: Update build prefixes and counts
    if not args.no_update_builds:
        print("\nStep 2: Analyzing build server repos...")
        try:
            build_repos_csv = run_script(BUILDS_PARSER_SCRIPT)
            # If script failed, try to find the most recent build repos file
            if not build_repos_csv or not os.path.exists(build_repos_csv):
                builds_dir = "data/working/builds"
                if os.path.exists(builds_dir):
                    build_files = sorted(Path(builds_dir).glob("*-build-repos.csv"), reverse=True)
                    if build_files:
                        build_repos_csv = str(build_files[0])
                        print(f"  Using existing file: {build_repos_csv}")
            
            if build_repos_csv and os.path.exists(build_repos_csv):
                build_prefixes = analyze_build_prefixes(build_repos_csv)
                print(f"Found {len(build_prefixes)} unique build prefixes")
                
                # Find proposed mappings
                proposed_mappings = find_proposed_build_prefix_mappings(roster, build_prefixes, EXCLUSION_LIST_FILE)
                display_proposed_mappings(proposed_mappings)
                
                # Handle interactive confirmation or dry-run
                mappings_to_apply = None
                if args.interactive and proposed_mappings:
                    # Check if we're in an interactive terminal
                    if not sys.stdin.isatty():
                        print("\n  Warning: Not running in an interactive terminal.")
                        print("  Interactive mode requires a TTY. Use --dry-run to review changes first.")
                        mappings_to_apply = []  # Skip all if not interactive
                    else:
                        print("\n  Review proposed mappings above.")
                        try:
                            response = input("  Apply all proposed mappings? [y/N/a=apply all/s=skip all]: ").strip().lower()
                            if response == 'y' or response == 'a':
                                mappings_to_apply = proposed_mappings
                                print("  Applying all proposed mappings...")
                            elif response == 's':
                                mappings_to_apply = []
                                print("  Skipping all proposed mappings...")
                            else:
                                # Individual confirmation
                                mappings_to_apply = []
                                for mapping in proposed_mappings:
                                    existing = mapping['existing_prefix']
                                    prefix = mapping['prefix']
                                    affiliate = mapping['affiliate']
                                    count = mapping['build_count']
                                    
                                    prompt = f"  Apply '{prefix}' -> '{affiliate}' ({count} repos)?"
                                    if existing:
                                        prompt += f" [replaces '{existing}']"
                                    prompt += " [y/N]: "
                                    
                                    if input(prompt).strip().lower() == 'y':
                                        mappings_to_apply.append(mapping)
                                        print(f"    ✓ Approved")
                                    else:
                                        print(f"    ✗ Skipped")
                        except (EOFError, KeyboardInterrupt):
                            print("\n  Interactive input cancelled. Skipping all proposed mappings.")
                            mappings_to_apply = []
                elif args.dry_run:
                    print("\n  DRY RUN MODE: No changes will be made to the roster file.")
                    mappings_to_apply = None  # Will show what would be applied
                else:
                    # Auto-apply all (default behavior)
                    mappings_to_apply = proposed_mappings
                
                # Update roster with approved mappings
                roster = update_build_prefixes(roster, build_prefixes, verbose=True, apply_mappings=mappings_to_apply, proposed_mappings=proposed_mappings)
                print("Updated build prefixes and counts")
            else:
                print(f"Warning: Could not find build repos CSV file", file=sys.stderr)
                print("  Skipping build prefix update.", file=sys.stderr)
        except Exception as e:
            print(f"Error updating build prefixes: {e}", file=sys.stderr)
            import traceback
            if args.dry_run or args.interactive:
                traceback.print_exc()
    
    # Write updated roster (unless dry-run)
    if not args.dry_run:
        print(f"\nWriting updated roster to: {args.roster}")
        write_roster(args.roster, roster, fieldnames)
        print("Done!")
    else:
        print(f"\nDRY RUN: Would write updated roster to: {args.roster}")
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
