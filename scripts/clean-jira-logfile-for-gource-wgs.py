"""
Clean Logfile for Gource Visualization of HL7 Workgroups
========================================================

This script processes a CSV file of resolved issues and enriches it with data from an
XML file containing HL7 workgroup information. The output is formatted for visualization
in Gource, a tool that shows activity in a version control system-like timeline.

Features:
- Parses workgroup data from an XML file to map workgroup keys to human-readable names.
- Processes CSV logs to include enriched and normalized information.
- Assigns unique colors to workgroups using a predefined palette.
- Outputs a cleaned log file compatible with Gource visualization.

Dependencies:
- Python 3.x
- Modules: argparse, csv, requests, xml.etree.ElementTree, html

Usage:
------
Run the script with the following options:

    python clean-logfile-for-gource-wgs.py --xml <workgroups.xml> --csv <input.csv> --output <output.csv>

Arguments:
    --xml    Path to the XML file containing workgroup definitions.
    --csv    Path to the CSV file with resolved issues.
    --output Path to save the cleaned and processed CSV file.

Example:
--------
    python clean-logfile-for-gource-wgs.py --xml _workgroups.xml --csv all-resolved-issues-YTD-for-gource.csv --output gource-log.csv

Details:
--------
Input XML:
    - Contains workgroup data with attributes like `key` and `name`.
    - Example entry:
      <workgroup key="arb" name="Architecture Review Board" deprecated="true"/>

Input CSV:
    - Requires columns: `Resolution Date`, `Reporter`, `type`, `Specification`.
    - Example row:
      2024-01-01T05:12:48.000+0000|Lloyd McKenzie|M|FHIR-core

Output CSV:
    - Adds columns with enriched data, formatted for Gource.

"""
#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

import argparse
import csv
import os
from datetime import datetime
from itertools import cycle
import requests
import xml.etree.ElementTree as ET
import html  # For decoding HTML entities

# Predefined color palette
color_palette = [
    "FF5733", "C70039", "900C3F", "581845", "321414", "FFC300", "DAF7A6",
    "33FF57", "34CB03", "245301", "57FF33", "75FF33", "33FFAD", "33FFF5",
    "33D7FF", "3375FF", "335AFF", "5733FF", "AD33FF", "F533FF", "FF33AB",
    "FF337A", "FF6E33", "FF8233", "D2B48C", "DEB887", "F4A460", "D2691E"
]
color_cycle = cycle(color_palette)

# URL to download the workgroup XML file
wg_xml_url = 'https://raw.githubusercontent.com/HL7/JIRA-Spec-Artifacts/refs/heads/master/xml/_workgroups.xml'
 
# Function to download and parse the workgroup XML
def download_and_parse_workgroups(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        root = ET.fromstring(response.content)
        return {wg.get('key'): html.unescape(wg.get('name')) for wg in root.findall('workgroup') if wg.get('key') and wg.get('name')}
    except Exception as e:
        return None

# Fallback workgroup dictionary
fallback_workgroup_dict = {
    'fm': 'Financial Management',
    'pc': 'Patient Care',
    'pa': 'Patient Administration',
    'pher': 'Public Health',
}

# Function to clean, enrich, sort data, and generate summary statistics
def clean_and_reformat_data(input_file, output_file, workgroup_dict):
    colors = {}
    exclude_wg = {'eu', 'au-v2', 'au-fhir', 'NULL'}
    row_count = 0

    # Read and sort the input file by "Resolution Date"
    with open(input_file, 'r') as file:
        reader = csv.DictReader(file, delimiter='|')
        sorted_rows = sorted(
            [row for row in reader if row['Resolution Date'].strip()],
            key=lambda r: datetime.strptime(r['Resolution Date'], '%Y-%m-%dT%H:%M:%S.%f%z')
        )

    # Write sorted and enriched data to the output file
    with open(output_file, 'w', newline='') as output:
        fieldnames = [field for field in sorted_rows[0].keys() if field != 'WG'] + ['new_field']
        writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter='|')
        writer.writeheader()

        for row in sorted_rows:
            if row['WG'] and row['WG'] not in exclude_wg:
                wg_name = workgroup_dict.get(row['WG'], row['WG']).replace('/', '-')
                if row['WG'] not in colors:
                    colors[row['WG']] = next(color_cycle)

                spec_value = row['Specification']
                if "inputValues" in spec_value and "V2-lri" in spec_value:
                    spec_value = "V2-lri"

                row['Specification'] = f"HL7/{wg_name}/{spec_value}"
                row['new_field'] = colors[row['WG']]
                del row['WG']
                writer.writerow(row)
                row_count += 1

    # Determine output directory for the summary file
    output_dir = os.path.dirname(output_file) if os.path.dirname(output_file) else os.getcwd()
    timestamp = datetime.now().strftime("%Y %m %d %H %M")
    summary_filename = f"{timestamp} - Jira Log File Parsing - Summary Statistics.txt"
    summary_filepath = os.path.join(output_dir, summary_filename)

    # Write summary statistics
    with open(summary_filepath, 'w') as summary_file:
        summary_file.write(f"Summary Statistics\n")
        summary_file.write(f"==================\n")
        summary_file.write(f"Total Processed Rows: {row_count}\n")
        summary_file.write(f"Output File: {output_file}\n")

    print(f"Summary statistics saved to {summary_filepath}")

# Main function to handle arguments and process files
def main():
    parser = argparse.ArgumentParser(description="Cleans and reformats a '|' delimited data file.")
    parser.add_argument("-i", "--input_file", required=True, help="Path to the input file")
    parser.add_argument("-o", "--output_file", required=True, help="Path to the output file")
    args = parser.parse_args()

    workgroup_dict = download_and_parse_workgroups(wg_xml_url)
    if not workgroup_dict:
        print("Falling back to local dictionary.")
        workgroup_dict = fallback_workgroup_dict

    clean_and_reformat_data(args.input_file, args.output_file, workgroup_dict)

if __name__ == "__main__":
    main()