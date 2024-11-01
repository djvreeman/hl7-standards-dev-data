import requests
import json
import pandas as pd
import sys
import csv
import argparse

def fetch_fhir_ig_list():
    """Fetch the fhir-ig-list.json from the FHIR repository."""
    url = "https://raw.githubusercontent.com/FHIR/ig-registry/master/fhir-ig-list.json"
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception("Failed to fetch fhir-ig-list.json")

def load_package_ids(input_csv):
    """Load package-ids from the input CSV file."""
    data = pd.read_csv(input_csv)
    return [pid.strip().lower() for pid in data.iloc[:, 0].tolist()]  # Normalize to lowercase

def extract_package_details(package_id, fhir_ig_list):
    """Extract relevant details for a given package-id from the fhir-ig-list.json."""
    package_id = package_id.strip().lower()  # Normalize package-id

    for guide in fhir_ig_list.get("guides", []):
        if guide.get("npm-name", "").strip().lower() == package_id:
            csv_data = []
            for entry in guide.get("editions", []):
                # Extract fhirversion as a clean string, not a list
                fhirversion = ", ".join(entry.get("fhir-version", [])) if entry.get("fhir-version") else ""

                row = {
                    "package-id": package_id,
                    "canonical": guide.get("canonical", ""),
                    "title": guide.get("name", ""),
                    "version": entry.get("ig-version", ""),
                    "desc": guide.get("description", ""),
                    "path": entry.get("url", ""),
                    "status": entry.get("name", ""),
                    "fhirversion": fhirversion,
                    "country": guide.get("country", ""),
                    "editors": ""  # Blank editors field
                }
                csv_data.append(row)
            return csv_data

    print(f"No match found for package-id: {package_id}")  # Diagnostic message
    return None

def main(input_csv, success_csv, failed_csv):
    package_ids = load_package_ids(input_csv)
    fhir_ig_list = fetch_fhir_ig_list()

    successful_results = []
    failed_package_ids = []

    # Process each package-id
    for package_id in package_ids:
        result = extract_package_details(package_id, fhir_ig_list)
        if result:
            successful_results.extend(result)
        else:
            failed_package_ids.append(package_id)

    # Save successful results to CSV
    if successful_results:
        pd.DataFrame(successful_results).to_csv(success_csv, index=False)

    # Save failed package-ids to CSV
    if failed_package_ids:
        with open(failed_csv, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(["Failed Package-IDs"])
            for package_id in failed_package_ids:
                writer.writerow([package_id])

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process FHIR package-ids and extract details.")
    parser.add_argument("-i", "--input", required=True, help="Path to the input filenames.csv")
    parser.add_argument("-o", "--output", required=True, help="Path to the output CSV for successful results")
    parser.add_argument("-e", "--error", required=True, help="Path to the output CSV for failed package-ids")

    args = parser.parse_args()

    main(args.input, args.output, args.error)