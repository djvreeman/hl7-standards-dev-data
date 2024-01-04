#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Overview:
#
# This script reads in the FHIR build server repo watch list and exports a CSV list of all the org/repos that are
# hooked up to the pipeline.

# Usage:
# python3 scripts/parse-builds-web.py -o data/working/builds/build-repos.csv

import csv
import argparse
import requests
import datetime

# Format current date and time as YYYYMMDD-HHMMSS
current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


def parse_json_and_write_csv(output_file):
    # Fetch the JSON data from the URL
    # This is the Build Server
    response = requests.get("https://build.fhir.org/ig/builds.json")
    data = response.json()

    # Parse the entries by the "/", keeping only the first and second fields
    parsed_entries = ["/".join(entry.split("/")[:2]) for entry in data if isinstance(entry, str)]
    
    # Create a non-duplicated list of parsed entries
    unique_parsed_entries = list(set(parsed_entries))

    # Sort the unique parsed entries in alphabetical order
    unique_parsed_entries.sort()

    # Write the sorted entries to a CSV file
    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.writer(csvfile)
        for entry in unique_parsed_entries:
            writer.writerow([entry])

    return unique_parsed_entries

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Fetch JSON from URL and write to CSV.')
    parser.add_argument('-o', '--output', default=f"data/working/builds/{current_time}-build-repos.csv", help='Path to the output CSV file.')

    args = parser.parse_args()

    unique_parsed_entries = parse_json_and_write_csv(args.output)
    print(f"Data has been written to: {args.output}\nNumber of entries: {len(unique_parsed_entries)}")