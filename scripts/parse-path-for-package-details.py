#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
"""
This script processes a FHIR specification's `package-list.json` file and extracts relevant details based on a given URL path. The script performs the following functions:

1. **Fetch FHIR package-list.json**: The script constructs the URL to the `package-list.json` file by trimming the input URL and appending `/package-list.json`. It then fetches the data from this URL.

2. **Normalize URLs**: To ensure consistency when comparing paths, the input URL and the paths within the `package-list.json` are normalized by converting them to lowercase and using `https://`.

3. **Extract Path Information**: The script compares the normalized input URL with paths found in the `package-list.json`. If matches are found, it collects details such as the version, description, status, and other relevant metadata.

4. **Write to CSV**: The extracted information is saved to a CSV file. If an output directory is provided, the file will be saved there; otherwise, a default directory is used.

### Usage:
The script requires the following arguments:
- `--url (-u)`: The URL of the FHIR specification to process.
- `--output (-o)`: Optional. The output directory or file path where the CSV will be saved.

If no matching entries are found for the given URL, the script will exit without generating a CSV file.

Example command:
    python parse-path-for-package-details.py -u “https://example.com/fhir/package” -o “./output”

"""

import argparse
import json
import os
import urllib.request
import csv

DEFAULT_OUTPUT_DIR = "data/working/package-path-details"

def fetch_package_list(url):
    try:
        print(f"Fetching package-list.json from: {url}")
        with urllib.request.urlopen(url) as response:
            data = response.read()
            return json.loads(data)
    except Exception as e:
        print(f"Failed to fetch package-list.json from {url}: {e}")
        return None

def normalize_url(url):
    return url.lower().replace("http://", "https://").rstrip('/')

def extract_path_info(package_list, path):
    normalized_path = normalize_url(path)
    print(f"Normalized input path: {normalized_path}")
    
    package_id = package_list.get("package-id", "N/A")
    canonical = package_list.get("canonical", "N/A")
    title = package_list.get("title", "N/A")
    
    matched_entries = []
    for entry in package_list.get("list", []):
        entry_path = normalize_url(entry.get("path", ""))
        print(f"Comparing with entry path: {entry_path}")
        if entry_path == normalized_path:
            matched_entries.append(entry)
    
    return package_id, canonical, title, matched_entries

def write_to_csv(package_id, canonical, title, matched_entries, output_file):
    # Define the specific fields to extract
    fieldnames = ["package-id", "canonical", "title", "version", "desc", "path", "status", "sequence", "fhirversion", "date", "current"]

    if os.path.isdir(output_file):
        output_file = os.path.join(output_file, f"{package_id.replace('.', '_')}_entries.csv")
    
    with open(output_file, 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        
        writer.writeheader()
        for entry in matched_entries:
            # Only include the specified fields
            row = {
                "package-id": package_id,
                "canonical": canonical,
                "title": title,
                "version": entry.get("version", ""),
                "desc": entry.get("desc", ""),
                "path": entry.get("path", ""),
                "status": entry.get("status", ""),
                "sequence": entry.get("sequence", ""),
                "fhirversion": entry.get("fhirversion", ""),
                "date": entry.get("date", ""),
                "current": entry.get("current", "")
            }
            writer.writerow(row)

def main():
    parser = argparse.ArgumentParser(description='Process FHIR package-list.json')
    parser.add_argument('-u', '--url', type=str, required=True, help='The URL path of the FHIR specification')
    parser.add_argument('-o', '--output', type=str, help='Optional output file path for the CSV file')
    args = parser.parse_args()
    
    base_url = '/'.join(args.url.rstrip('/').split('/')[:-1])
    package_list_url = f"{base_url}/package-list.json"
    
    print(f"Constructed package-list.json URL: {package_list_url}")
    
    package_list = fetch_package_list(package_list_url)
    if not package_list:
        return
    
    package_id, canonical, title, matched_entries = extract_path_info(package_list, args.url)
    
    if not matched_entries:
        print(f"No matching entries found for the path: {args.url}")
        return
    
    output_file = args.output if args.output else DEFAULT_OUTPUT_DIR
    
    write_to_csv(package_id, canonical, title, matched_entries, output_file)
    print(f"CSV file '{output_file}' generated successfully.")

if __name__ == "__main__":
    main()