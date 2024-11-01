import requests
import pandas as pd
import sys
import csv
import argparse
import os

def fetch_package_details(canonical_url):
    """Fetch package-list.json from the given canonical URL and extract relevant details."""
    try:
        # Construct the URL for package-list.json
        package_list_url = canonical_url.rstrip('/') + "/package-list.json"
        response = requests.get(package_list_url)

        if response.status_code != 200:
            print(f"Failed to fetch {package_list_url}")
            return None, None

        package_data = response.json()
        package_id = package_data.get("package-id", "")  # Extract package-id

        csv_data = []

        # Extract package details from the list entries
        for entry in package_data.get("list", []):
            fhirversion = entry.get("fhirversion", [])
            fhirversion_str = ", ".join(fhirversion) if isinstance(fhirversion, list) else str(fhirversion)

            row = {
                "package-id": package_id,
                "canonical": package_data.get("canonical", ""),
                "title": package_data.get("title", ""),
                "version": entry.get("version", ""),
                "desc": entry.get("desc", ""),
                "path": entry.get("path", ""),
                "status": entry.get("status", ""),
                "sequence": entry.get("sequence", ""),
                "fhirversion": fhirversion_str,
                "date": entry.get("date", ""),
                "current": entry.get("current", False),
                "country": package_data.get("country", ""),
                "editors": ""  # Blank editors field
            }
            csv_data.append(row)
        return package_id, csv_data

    except Exception as e:
        print(f"Error processing {canonical_url}: {e}")
        return None, None

def save_results_to_csv(package_id, data, output_dir):
    """Save the details of a package to a CSV file in the specified directory."""
    # Define the output filename using the unmodified package-id
    if os.path.isdir(output_dir):
        output_csv_path = os.path.join(output_dir, f"{package_id}_entries.csv")
    else:
        output_csv_path = output_dir

    # Ensure the output directory exists
    os.makedirs(os.path.dirname(output_csv_path), exist_ok=True)

    # Save the data to the CSV file
    pd.DataFrame(data).to_csv(output_csv_path, index=False)
    print(f"Saved results for {package_id} to {output_csv_path}")

def main(canonical_url, input_csv, field_name, output_dir):
    # Determine URLs to process
    if canonical_url:
        urls = [canonical_url]
    elif input_csv and field_name:
        data = pd.read_csv(input_csv)
        if field_name not in data.columns:
            print(f"Field '{field_name}' not found in the input CSV.")
            sys.exit(1)
        urls = data[field_name].dropna().tolist()  # Extract URLs from the specified field
    else:
        print("Either a canonical URL or an input CSV with a field name must be provided.")
        sys.exit(1)

    # Process each canonical URL
    for url in urls:
        package_id, result = fetch_package_details(url)
        if result:
            save_results_to_csv(package_id, result, output_dir)
        else:
            print(f"No data processed for {url}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Process canonical URLs and extract package details.")
    parser.add_argument("-u", "--url", help="A single canonical URL to process")
    parser.add_argument("-i", "--input", help="Path to the input CSV containing canonical URLs")
    parser.add_argument("-f", "--field", help="Field name in the input CSV that contains canonical URLs")
    parser.add_argument("-o", "--output", required=True, help="Directory where the output CSVs will be saved")

    args = parser.parse_args()

    main(args.url, args.input, args.field, args.output)