
#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
"""
This script processes a FHIR specification's `package-list.json` file and extracts relevant details, including country,
based on a given URL path. The script performs the following functions:

1. **Fetch FHIR package-list.json**: The script constructs the URL to the `package-list.json` file by trimming the input URL 
and appending `/package-list.json`. It then fetches the data from this URL.

2. **Normalize URLs**: To ensure consistency when comparing paths, the input URL and the paths within the `package-list.json` 
are normalized by converting them to lowercase and using `https://`.

3. **Extract Path Information**: The script compares the normalized input URL with paths found in the `package-list.json`. 
If matches are found, it collects details such as the version, description, status, and country metadata.

4. **Fetch country from FHIR IG List**: Using `package-id` and `version`, the script fetches country details from the 
FHIR IG list.

5. **Write to CSV**: The extracted information is saved to a CSV file. If an output directory is provided, the file will 
be saved there; otherwise, a default directory is used.

### Usage:
The script requires the following arguments:
- `--url (-u)`: The URL of the FHIR specification to process.
- `--output (-o)`: Optional. The output directory or file path where the CSV will be saved.

Example command:
    python3 scripts/parse-path-for-package-details-and-realm.py -u https://hl7.org/fhir/us/vrdr/STU3/ -o data/working/package-path-details
"""

import argparse
import json
import os
import urllib.request
import csv

DEFAULT_OUTPUT_DIR = "data/working/package-path-details"
FHIR_IG_LIST_URL = "https://raw.githubusercontent.com/FHIR/ig-registry/master/fhir-ig-list.json"

# Function to fetch package-list.json from a constructed URL
def fetch_package_list(url):
    try:
        print(f"Fetching package-list.json from: {url}")
        with urllib.request.urlopen(url) as response:
            data = response.read()
            return json.loads(data)
    except Exception as e:
        print(f"Failed to fetch package-list.json from {url}: {e}")
        return None

# Function to normalize URLs for comparison
def normalize_url(url):
    return url.lower().replace("http://", "https://")

# Function to fetch the FHIR IG list containing package details like country
def fetch_fhir_ig_list():
    try:
        print(f"Fetching FHIR IG list from: {FHIR_IG_LIST_URL}")
        with urllib.request.urlopen(FHIR_IG_LIST_URL) as response:
            data = response.read()
            return json.loads(data)["guides"]
    except Exception as e:
        print(f"Failed to fetch FHIR IG list: {e}")
        return None

# Function to extract the country from the fhir-ig-list.json based on package-id (not by version)
def get_country_from_fhir_ig_list(package_id, fhir_ig_list):
    for guide in fhir_ig_list:
        if guide.get("npm-name") == package_id:
            return guide.get("country", "")
    return ""

# Function to process and save details into a CSV
def process_package_details(url, output_dir=None):
    # Construct the package-list.json URL
    base_url = '/'.join(url.rstrip('/').split('/')[:-1])
    package_list_url = f"{base_url}/package-list.json"

    # Fetch package-list.json
    package_list = fetch_package_list(package_list_url)
    if not package_list:
        return
    
    # Fetch the FHIR IG list to match package-id with country
    fhir_ig_list = fetch_fhir_ig_list()
    if not fhir_ig_list:
        return

    # Normalize input URL for comparison
    normalized_url = normalize_url(url)

    # Create output directory if it doesn't exist
    if not output_dir:
        output_dir = DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    # Initialize data list to be written to CSV
    csv_data = []

    # Iterate over the list of paths in package-list.json and collect relevant details
    for entry in package_list.get("list", []):
        package_id = package_list.get("package-id", "")
        canonical = package_list.get("canonical", "")
        title = package_list.get("title", "")
        version = entry.get("version", "")
        desc = entry.get("desc", "")
        path = entry.get("path", "")
        status = entry.get("status", "")
        sequence = entry.get("sequence", "")
        fhirversion = entry.get("fhirversion", "")
        date = entry.get("date", "")
        current = entry.get("current", False)
        
        # Get country information from the fhir-ig-list.json based on package-id
        country = get_country_from_fhir_ig_list(package_id, fhir_ig_list)
        
        # Prepare a row for the CSV
        row = {
            "package-id": package_id,
            "canonical": canonical,
            "title": title,
            "version": version,
            "desc": desc,
            "path": path,
            "status": status,
            "sequence": sequence,
            "fhirversion": fhirversion,
            "date": date,
            "current": current,
            "country": country
        }
        csv_data.append(row)

    # Define output file name based on package-id
    if os.path.isdir(output_dir):
        output_csv_path = os.path.join(output_dir, f"{package_id.replace('.', '_')}_entries.csv")
    else:
        output_csv_path = output_dir

    # Write the collected data to the CSV file
    with open(output_csv_path, mode="w", newline="", encoding="utf-8") as csvfile:
        fieldnames = ["package-id", "canonical", "title", "version", "desc", "path", "status", "sequence", 
                      "fhirversion", "date", "current", "country"]
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_data)

    print(f"Data successfully written to {output_csv_path}")

# Command-line interface for the script
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process a FHIR package's package-list.json and extract details including country.")
    parser.add_argument("-u", "--url", required=True, help="The URL of the FHIR package to process.")
    parser.add_argument("-o", "--output", help="Optional: The output directory to save the CSV file.")
    
    args = parser.parse_args()
    process_package_details(args.url, args.output)