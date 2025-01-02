"""
Script: parse-concall-source.py

Description:
This script processes a CSV file of conference call data for use with Gource, a software visualization tool. 
It generates a log file in Gource-compatible format, allowing visual representation of activity over time.
The log file uses ISO 8601 formatted timestamps for better readability and compliance.

Key Features:
1. Parses CSV data containing information about HL7 workgroup conference calls.
2. Fetches additional workgroup names dynamically from a remote XML source.
3. Uses fuzzy matching and manual review to match workgroup short names to canonical names.
4. Filters and formats data to fit Gource visualization requirements.
5. Outputs a summary of statistics on calls (e.g., total calls, average calls per month, total hours).

Requirements:
- Python 3.7 or later.
- Install required Python packages:
  `pip install pandas thefuzz requests python-dateutil`
- A valid input CSV file containing at least the following columns:
  - `wg_concall_basestartdate`: Date of the call (required, format: YYYY-MM-DD).
  - `wg_concall_status`: Status of the call (e.g., "CANCELLED").
  - `wg_shortname`: Short name of the workgroup.

Usage:
1. Prepare a CSV file with the necessary data.
2. Run the script with the following arguments:
   - `-i` or `--input`: Path to the input CSV file.
   - `-o` or `--output`: Path to save the output Gource-compatible log file.
   - `--start`: Start date of the filtering range (format: YYYY-MM-DD).
   - `--stop`: End date of the filtering range (format: YYYY-MM-DD).

Example Command:

python parse-concall-source.py -i input.csv -o output.log –start “2023-01-01” –stop “2023-12-31”

Output:
1. A Gource-compatible log file containing the filtered and formatted data.
2. A `summary_statistics.txt` file with insights into the processed data:
   - Total calls within the time period.
   - Average calls per month.
   - Total hours of calls.
   - Number of calls per workgroup.

Notes:
- Rows with invalid or missing dates in `wg_concall_basestartdate` will be excluded.
- The script interacts with a remote XML source to fetch workgroup names; ensure an active internet connection.
- During execution, the script may prompt for manual review to resolve ambiguous workgroup matches.
"""

import csv
import re
import requests
import xml.etree.ElementTree as ET
import pandas as pd
from datetime import datetime
from thefuzz import process
import argparse
import html
import os

# Predefined manual review mappings
MANUAL_REVIEW_MAPPINGS = {
    "Helios": "Public Health",
    "Orders and Observations": "Orders & Observations",
    "Da Vinci Project": "Financial Mgmt",
    "Financial Management": "Financial Mgmt",
    "US Realm Steering Committee": None,
    "Gravity": "Patient Care",
    "FHIR Management Group": "FHIR Mgmt Group",
    "FAST": "FHIR Infrastructure",
    "Clinical Information Modeling Initiative": "CIMI",
    "Argonaut Project": "FHIR Infrastructure",
    "CARIN": "Financial Mgmt",
    "Vulcan": "Biomedical Research & Regulation",
    "Business Process Management": None,
    "FHIR Community Process Coordination Committee": None,
    "V2 Management Group": "V2 Mgmt Group",
    "Payer/Provider Information Exchange": "Payer-Provider Information Exchange"
}

# Flexible Date Parsing
def parse_date(date_str, is_start=True):
    try:
        return datetime.strptime(date_str, "%Y %m %d")
    except ValueError:
        try:
            if is_start:
                return datetime.strptime(date_str + " 01", "%Y %m %d")
            else:
                return (datetime.strptime(date_str + " 01", "%Y %m %d") 
                        + pd.offsets.MonthEnd(0)).to_pydatetime().replace(hour=23, minute=59, second=59)
        except ValueError:
            if is_start:
                return datetime.strptime(date_str + " 01 01", "%Y %m %d")
            else:
                return datetime.strptime(date_str + " 12 31 23:59:59", "%Y %m %d %H:%M:%S")

# Fetch Work Group Names from URL
def fetch_workgroup_names_from_url(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        work_group_names = [
            html.unescape(wg.get('name')) for wg in root.findall('.//workgroup') if wg.get('name')
        ]
        print(f"Fetched {len(work_group_names)} workgroup names: {work_group_names[:5]}")
        return work_group_names
    except Exception as e:
        print(f"Error fetching or parsing workgroup names from URL: {e}")
        return []

# Fuzzy Matching for Work Groups
def get_best_match(shortname, choices, threshold=80):
    if not shortname or not choices:
        return None, 0
    result = process.extractOne(shortname, choices)
    if result:
        match, score = result
        return (match, score) if score >= threshold else (None, 0)
    print(f"No match found for '{shortname}'")
    return None, 0

# Manual Review
def manual_review(matches):
    print("\nReview the suggested matches:")
    print("Current WG Name -> Suggested Canonical Name (Confidence Score)")
    print("-" * 60)
    confirmed_matches = {}
    accept_all = False

    for original, (suggested, score) in matches.items():
        if original in MANUAL_REVIEW_MAPPINGS:
            confirmed_matches[original] = MANUAL_REVIEW_MAPPINGS[original]
            continue

        if accept_all:
            confirmed_matches[original] = suggested
            continue

        print(f"{original} -> {suggested} ({score}%)")
        user_input = input(f"Confirm? [Y/n/edit/yes to all]: ").strip().lower()
        if user_input in ['n', 'no']:
            confirmed_matches[original] = original  # Keep original if rejected
        elif user_input == 'edit':
            edited_name = input("Enter the correct canonical name: ").strip()
            confirmed_matches[original] = edited_name  # Save the edited name
        elif user_input == '' or user_input in ['y', 'yes']:
            confirmed_matches[original] = suggested
        elif user_input == 'yes to all':
            accept_all = True
            confirmed_matches[original] = suggested
        else:
            print("Invalid input. Defaulting to confirming the suggested match.")
            confirmed_matches[original] = suggested
    return confirmed_matches

# Calculate and save summary statistics
def calculate_summary_statistics(data, output_file):
    data = data[data['wg_concall_status'].str.strip().str.upper() != "CANCELLED"]

    total_calls = len(data)
    monthly_calls = data.groupby(data['wg_concall_basestartdate_parsed'].dt.to_period('M')).size()
    avg_calls_per_month = monthly_calls.mean()
    calls_per_workgroup = data.groupby('wg_name').size()
    total_hours = data['wg_concall_duration'].sum()

    print("\nSummary Statistics:")
    print(f"1. Total Calls for the Time Period: {total_calls}")
    print(f"2. Average Calls per Month: {avg_calls_per_month:.2f}")
    print(f"3. Total Hours of Calls: {total_hours:.2f} hours")
    print("4. Total Calls per Work Group:")
    print(calls_per_workgroup.to_string(index=True))

    # Determine directory and filename for the stats output file
    output_dir = os.path.dirname(output_file) if os.path.dirname(output_file) else os.getcwd()
    timestamp = datetime.now().strftime("%Y %m %d %H %M")
    stats_output_filename = f"{timestamp} - ConCall Summary Statistics.txt"
    stats_output_filepath = os.path.join(output_dir, stats_output_filename)

    with open(stats_output_filepath, "w") as f:
        f.write("Summary Statistics:\n")
        f.write(f"1. Total Calls for the Time Period: {total_calls}\n")
        f.write(f"2. Average Calls per Month: {avg_calls_per_month:.2f}\n")
        f.write(f"3. Total Hours of Calls: {total_hours:.2f} hours\n")
        f.write("4. Total Calls per Work Group:\n")
        f.write(calls_per_workgroup.to_string(index=True))
    print(f"\nSummary statistics saved to {stats_output_filepath}")

# Process CSV for Gource Format
def process_csv_for_gource(input_file, output_file, work_group_names, start_date, stop_date):
    matches = {}
    data = pd.read_csv(input_file)

    if 'wg_concall_basestartdate' not in data.columns or 'wg_concall_status' not in data.columns:
        raise ValueError("Input file must contain 'wg_concall_basestartdate' and 'wg_concall_status' columns.")

    data['wg_concall_basestartdate_parsed'] = pd.to_datetime(
        data['wg_concall_basestartdate'], errors='coerce'
    )

    invalid_rows = data[data['wg_concall_basestartdate_parsed'].isna()]
    if not invalid_rows.empty:
        print("Rows with invalid dates:")
        print(invalid_rows[['wg_concall_basestartdate']])

    valid_data = data.dropna(subset=['wg_concall_basestartdate_parsed'])
    filtered_data = valid_data[
        (valid_data['wg_concall_basestartdate_parsed'] >= start_date) &
        (valid_data['wg_concall_basestartdate_parsed'] <= stop_date)
    ]

    for row in filtered_data.itertuples():
        shortname = getattr(row, 'wg_shortname', None)
        if shortname and isinstance(shortname, str):
            best_match, score = get_best_match(shortname, work_group_names)
            matches[shortname] = (best_match, score)
        else:
            matches[shortname] = (None, 0)
    
    confirmed_matches = manual_review(matches)

    filtered_data = filtered_data.copy()
    filtered_data['wg_name'] = filtered_data['wg_shortname'].map(confirmed_matches).fillna(filtered_data['wg_shortname'])

    gource_data = []
    for row in filtered_data.itertuples():
        wg_name = getattr(row, 'wg_name', None)
        timestamp = row.wg_concall_basestartdate_parsed.isoformat()

        status = getattr(row, "wg_concall_status", "")
        if not isinstance(status, str):
            status = ""

        action = "D" if status.strip().upper() == "CANCEL" else "A"
        path = f'HL7/{wg_name}/Conference Call'
        gource_data.append([timestamp, "HL7 International", action, path])

    # Sort by timestamp
    gource_data.sort(key=lambda x: x[0])  # Ensure chronological order for Gource

    # Save the Gource-compatible log
    with open(output_file, "w") as f:
        for entry in gource_data:
            f.write("|".join(map(str, entry)) + "\n")
    print(f"Gource-compatible log saved to {output_file}")

    calculate_summary_statistics(filtered_data, output_file)

# Main Function
def main():
    parser = argparse.ArgumentParser(description="Prepare CSV for Gource visualization.")
    parser.add_argument('-i', '--input', required=True, help="Path to the input CSV file.")
    parser.add_argument('-o', '--output', required=True, help="Path to save the output Gource-compatible log file.")
    parser.add_argument('--start', required=True, help="Start date in the format YYYY MM DD, YYYY MM, or YYYY.")
    parser.add_argument('--stop', required=True, help="Stop date in the format YYYY MM DD, YYYY MM, or YYYY.")
    args = parser.parse_args()

    start_date = parse_date(args.start, is_start=True)
    stop_date = parse_date(args.stop, is_start=False)
    print(f"Parsed Start Date: {start_date}")
    print(f"Parsed Stop Date: {stop_date}")

    url = 'https://raw.githubusercontent.com/HL7/JIRA-Spec-Artifacts/refs/heads/master/xml/_workgroups.xml'
    work_group_names = fetch_workgroup_names_from_url(url)

    process_csv_for_gource(args.input, args.output, work_group_names, start_date, stop_date)

if __name__ == "__main__":
    main()