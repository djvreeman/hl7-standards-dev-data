import csv
import argparse
import json
import requests
import os

def parse_json_to_csv(json_data, csv_filename):
    data_list = json_data["list"]
    metadata_keys = ["package-id", "title", "canonical", "introduction", "category"]
    metadata = {key: json_data[key] for key in metadata_keys}
    for item in data_list:
        item.update(metadata)
    all_keys = set()
    for item in data_list:
        all_keys.update(item.keys())
    ordered_keys = metadata_keys + [key for key in all_keys if key not in metadata_keys]
    with open(csv_filename, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=ordered_keys)
        writer.writeheader()
        writer.writerows(data_list)
    return csv_filename

def fetch_and_parse_data(url, csv_filename):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Check if the request was successful
        json_data = json.loads(response.content.decode('utf-8-sig'))  # Decode using utf-8-sig
        # Create a 'data' subdirectory at one level up if it doesn't exist
        os.makedirs('../data', exist_ok=True)
        # Name the CSV file according to the 'package-id' and store it in the 'data' subdirectory
        csv_filename = os.path.join('../data', f"{json_data['package-id']}.csv")
        csv_filename = parse_json_to_csv(json_data, csv_filename)
        print(f"Data parsed and written to {csv_filename}")
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data from {url}. Error: {str(e)}")
    except json.decoder.JSONDecodeError as e:
        print(f"Failed to decode JSON data from {url}. Error: {str(e)}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fetch FHIR data and parse into CSV")
    parser.add_argument("-c", "--canonical", type=str, required=True, help="Canonical URL to fetch JSON data")
    args = parser.parse_args()
    url = args.canonical.rstrip("/") + "/package-list.json"
    csv_filename = "parsed_data.csv"
    fetch_and_parse_data(url, csv_filename)
