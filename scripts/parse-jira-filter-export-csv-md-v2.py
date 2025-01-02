#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

"""
Script Description:
This script interacts with the HL7 JIRA API to fetch issue data based on specified query parameters.
It allows for exporting the retrieved data into either CSV, Markdown format, or both. The script
supports pagination to handle large datasets and exports fields as specified in the command-line
arguments. Additional features include formatting specific fields like URLs and JIRA keys as clickable
links in the Markdown output.

Authorization: You need to supply your HL7 Jira Personalized Access Token as the bearer token.
You can create/find your Personalized Access Token in your JIRA Profile.

Some HL7 JIRA Fields of Note:
    fields.customfield_10612 = Related URL
    fields.customfield_10618 = Resolution

Example Usage:
1. Export data to both CSV and Markdown with default output filenames:
   python parse-jira-filter-export-csv-md.py -f '{"jql": "filter = 16107"}' -t 'your_bearer_token' -d 'key,fields.customfield_10612,fields.customfield_10618' -e 'both'

2. Export data only to CSV with a custom output filename:
   python parse-jira-filter-export-csv-md.py -f '{"jql": "filter = 16107"}' -t 'your_bearer_token' -d 'key,fields.customfield_10612,fields.customfield_10618' -o "da-vinci-formulary-stu2-issues-filter-16017" -e 'csv'

3. Export data only to Markdown:
   python parse-jira-filter-export-csv-md.py -f '{"jql": "filter = 16107"}' -t 'your_bearer_token' -d 'key,fields.customfield_10612,fields.customfield_10618' -o "da-vinci-formulary-stu2-issues-filter-16017" -e 'markdown'
"""

import argparse
import csv
import requests
import json
from datetime import datetime
from datetime import timezone

# Default base URL
DEFAULT_BASE_URL = "https://jira.hl7.org/rest/api/latest/search"
DEFAULT_OUTPUT_FILENAME = "output"

# Load configuration from config.json
with open("data/config/config.json", "r") as config_file:
    config = json.load(config_file)

BEARER_TOKEN = config["jira_bearer_token"]

# Output field mappings
field_mappings = {
    'key': 'Issue',
    'fields.summary': 'Summary',
    'fields.customfield_13704.value': 'Realm',
    'fields.customfield_10612': 'Related URL',
    'fields.customfield_10618': 'Resolution',
    'fields.creator.displayName': 'Reporter',
    'fields.customfield_13714.displayName': 'Project Facilitator',
    'fields.customfield_13716.displayName': 'Publishing Facilitator',
    'fields.customfield_12316': 'Approval Date',
    'fields.customfield_11302': 'Specification',
    'fields.resolutiondate': 'Resolution Date',
    'fields.customfield_11400': 'WG'
    # Add more mappings as needed
}

# Define a function to safely parse resolution dates
def parse_resolution_date(date_str):
    try:
        if date_str:
            return datetime.strptime(date_str, '%Y-%m-%dT%H:%M:%S.%f%z')
        else:
            # Return a minimal datetime with UTC timezone for None or empty strings
            return datetime.min.replace(tzinfo=timezone.utc)
    except ValueError:
        # Return a very large date with UTC timezone for missing or malformed dates
        return datetime.max.replace(tzinfo=timezone.utc)

def query_jira(base_url, query_params, bearer_token, fields):
    headers = {
        'Authorization': f'Bearer {bearer_token}',
        'Accept': 'application/json'
    }

    all_results = []
    start_at = 0
    total_results = float('inf')  # Initialize to an arbitrary large number
    
    while start_at < total_results:
        query_params['startAt'] = start_at
        response = requests.get(base_url, headers=headers, params=query_params)
        if response.status_code != 200:
            print(f"Full Request URL: {response.url}")
            print(f"Response Content: {response.text}")
            raise Exception(f"Error querying JIRA API: {response.status_code}")

        response_json = response.json()
        if not isinstance(response_json, dict):
            raise TypeError("Response JSON is not a dictionary.")

        issues = response_json.get('issues', [])
        if not isinstance(issues, list):
            raise TypeError("'issues' in response JSON is not a list.")

        all_results.extend(issues)  # Assuming 'issues' contains the results

        # Update total_results and start_at for next iteration
        total_results = response_json.get('total', 0)
        start_at += len(issues)

    return all_results

def get_nested_value(dictionary, nested_keys):
    """Safely extract nested values from a dictionary."""
    for key in nested_keys.split('.'):
        # Check if the key exists and is not None
        if dictionary is not None and key in dictionary:
            dictionary = dictionary[key]
        else:
            # Return None or a default value if the key is not found
            return None
    return dictionary

def sanitize_for_csv(text):
    """Encapsulate fields in double quotes and escape internal quotes for CSV."""
    if isinstance(text, str):
        return '"' + text.replace('"', '""') + '"'
    return text

def sanitize_for_markdown(text):
    """Replace line feeds with spaces and escape special characters for Markdown compatibility."""
    if isinstance(text, str):
        # Replace line breaks with a space
        text = text.replace('\n', ' ').replace('\r', ' ')

        # Escape Markdown special characters
        replacements = {
            '|': '\\|',
            '\\': '\\\\',
            '*': '\\*',
            '_': '\\_',
            '`': '\\`',
            # Add more replacements if needed
        }
        for old, new in replacements.items():
            text = text.replace(old, new)

    return text

def export_to_csv(data, fields, filename, field_mappings, chosen_delimiter, add_type):
    row_count = 0
    fieldnames = [field_mappings.get(field, field) for field in fields]
    # Insert 'type' as the third field if add_type is True
    if add_type:
        fieldnames.insert(2, 'type')  # Insert 'type' at the third position

    with open(f"{filename}.csv", 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, delimiter=chosen_delimiter, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for item in data:
            row_data = {}
            for field in fields:
                value = get_nested_value(item, field)
                if isinstance(value, list) and len(value) == 1:
                    value = value[0]
                row_data[field_mappings.get(field, field)] = value
            if add_type:
                row_data['type'] = 'M'  # Add 'type' field with value 'M'
            writer.writerow(row_data)
            row_count += 1
    return row_count

def export_to_markdown(data, fields, filename, field_mappings):
    row_count = 0
    with open(f"{filename}.md", 'w', encoding='utf-8') as file:
        mapped_fields = [field_mappings.get(field, field) for field in fields]
        file.write('| ' + ' | '.join(mapped_fields) + ' |\n')
        file.write('|' + ' --- |' * len(mapped_fields) + '\n')
        for item in data:
            row_data = []
            for field in fields:
                value = get_nested_value(item, field)
                if field == 'key' and value:
                    # Format 'key' as a clickable JIRA link
                    value = f'[{value}](https://jira.hl7.org/browse/{value})'
                elif field == 'fields.customfield_10612' and value:
                    # Format 'fields.customfield_10612' as a clickable URL
                    value = f'[{value}]({value})'
                else:
                    value = sanitize_for_markdown(value)
                row_data.append(value)
            file.write('| ' + ' | '.join(row_data) + ' |\n')
            row_count += 1
    return row_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Query JIRA API and export specified fields to CSV and Markdown.")
    parser.add_argument("-u", "--url", help="Base URL for the JIRA API", default=DEFAULT_BASE_URL)
    parser.add_argument("-f", "--filters", help="Query parameters in JSON format", required=True)
    #parser.add_argument("-t", "--token", help="Bearer token for authentication", required=True)
    parser.add_argument("-d", "--fields", help="Comma-separated data fields to export", required=True)
    parser.add_argument("-o", "--output", help="Output file name (without extension)", default=DEFAULT_OUTPUT_FILENAME)
    parser.add_argument('-del', '--delimiter', type=str, default=',', help='Delimiter to use in the CSV file (default: comma)')
    parser.add_argument("-e", "--export-format", 
                    help="Specify the export format: 'csv', 'markdown', or 'both'", 
                    choices=['csv', 'markdown', 'both'], 
                    default='both')
    parser.add_argument('--add-type', action='store_true', help='Include a "type" field with each row set to "M"')

    args = parser.parse_args()
    chosen_delimiter = args.delimiter

    try:
        query_params = json.loads(args.filters)
        fields = args.fields.split(',')

        # Fetch data
        data_to_export = query_jira(args.url, query_params, BEARER_TOKEN, fields)

        # Check and sort data
        if data_to_export and 'resolutiondate' in data_to_export[0].get('fields', {}):
            data_to_export.sort(key=lambda x: parse_resolution_date(x.get('fields', {}).get('resolutiondate', '9999-12-31T23:59:59.000+0000')))

        # Export data
        if args.export_format in ['csv', 'both']:
            csv_row_count = export_to_csv(data_to_export, fields, args.output, field_mappings, args.delimiter, args.add_type)
            print(f"Data exported to CSV successfully with {csv_row_count} rows in file: {args.output}.csv")

        if args.export_format in ['markdown', 'both']:
            md_row_count = export_to_markdown(data_to_export, fields, args.output, field_mappings)
            print(f"Data exported to Markdown successfully with {md_row_count} rows in file: {args.output}.md")

    except Exception as e:
        print(f"An error occurred: {e}")
