#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Overview:
#
# This script reads in the fhir-ig.json file from the FHIR IG Publisher Repo
# For each guide in the list, it attempts to gather version information 
# by calling the canonical URL and retrieving the package-list.json
# It then exports a CSV with the key metadata by package release
#
# Note: not all packages (e.g. many IHE published profiles) have a package-list.json, and thus those would not have
# any content in the CSV export
# 
# Export: this script writes the csv file to: ../data/all_packages_data.csv
# 
# Usage:
# python3 fetch-parse-fhir-ig-list-and-all-editions-onecsv.py  

import requests
import json
import csv
import os

def normalize_field(data):
    if isinstance(data, list):
        return ', '.join(data)
    return data

def parse_json_to_csv(json_data, extra_metadata):
    data_list = json_data.get("list", [])
    metadata_keys = ["package-id", "title", "canonical", "introduction", "category"]
    metadata = {key: json_data.get(key, "") for key in metadata_keys}
    metadata.update(extra_metadata)
    for item in data_list:
        item.update(metadata)
    all_keys = set()
    for item in data_list:
        all_keys.update(item.keys())
    return data_list, all_keys

def fetch_and_parse_data(canonical_url, extra_metadata):
    try:
        response_pkg = requests.get(canonical_url.rstrip("/") + "/package-list.json")
        response_pkg.raise_for_status()
        pkg_data = json.loads(response_pkg.content.decode('utf-8-sig'))
        return parse_json_to_csv(pkg_data, extra_metadata)
    except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as e:
        print(f"Failed to fetch and parse data from {canonical_url}. Error: {str(e)}")
        return [], []

def fetch_and_process_guides(url, output_filename):
    all_data = []
    all_keys = set()
    try:
        response = requests.get(url)
        response.raise_for_status()
        guides_data = json.loads(response.content.decode('utf-8-sig'))
        guides_list = guides_data["guides"]
        for guide in guides_list:
            try:
                canonical_url = guide['canonical']
                print(f"Fetching data using canonical URL: {canonical_url}")
                extra_metadata = {
                    "country": normalize_field(guide.get("country", "")),
                    "language": normalize_field(guide.get("language", ""))
                }
                guide_data, guide_keys = fetch_and_parse_data(canonical_url, extra_metadata)
                all_data.extend(guide_data)
                all_keys.update(guide_keys)
            except KeyError:
                print(f"Skipping a guide due to missing 'canonical' key. Guide data: {json.dumps(guide, indent=2)}")
            except Exception as e:
                print(f"Error processing a guide: {str(e)}. Guide data: {json.dumps(guide, indent=2)}")
        
        first_keys = ["package-id", "version", "title", "date", "status", "country", "language"]
        ordered_keys = first_keys + sorted(list(all_keys - set(first_keys)))
        
        os.makedirs(os.path.dirname(output_filename), exist_ok=True)
        with open(output_filename, mode='w', newline='', encoding='utf-8') as file:
            writer = csv.DictWriter(file, fieldnames=ordered_keys)
            writer.writeheader()
            for row_data in all_data:
                #print(f"Writing data for package-id: {row_data['package-id']}")
                writer.writerow(row_data)
        print(f"All data parsed and written to {output_filename}")
    except (requests.exceptions.RequestException, json.decoder.JSONDecodeError) as e:
        print(f"Failed to fetch data from {url}. Error: {str(e)}")

if __name__ == "__main__":
    url = "https://raw.githubusercontent.com/FHIR/ig-registry/master/fhir-ig-list.json"
    output_filename = "../data/all_packages_data.csv"
    fetch_and_process_guides(url, output_filename)
