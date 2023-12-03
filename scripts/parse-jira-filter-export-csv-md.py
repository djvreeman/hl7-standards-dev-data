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
   python parse-jira-filter-export-csv.py -f '{"jql": "filter = 16107"}' -t 'your_bearer_token' -d 'key,fields.customfield_10612,fields.customfield_10618' -e 'both'

2. Export data only to CSV with a custom output filename:
   python parse-jira-filter-export-csv.py -f '{"jql": "filter = 16107"}' -t 'your_bearer_token' -d 'key,fields.customfield_10612,fields.customfield_10618' -o "da-vinci-formulary-stu2-issues-filter-16017" -e 'csv'

3. Export data only to Markdown:
   python parse-jira-filter-export-csv.py -f '{"jql": "filter = 16107"}' -t 'your_bearer_token' -d 'key,fields.customfield_10612,fields.customfield_10618' -o "da-vinci-formulary-stu2-issues-filter-16017" -e 'markdown'
"""

import argparse
import csv
import requests
import json

# Default base URL
DEFAULT_BASE_URL = "https://jira.hl7.org/rest/api/latest/search"
DEFAULT_OUTPUT_FILENAME = "output"

# Output field mappings
field_mappings = {
    'key': 'Issue',
    'fields.customfield_10612': 'Related URL',
    'fields.customfield_10618': 'Resolution',
    # Add more mappings as needed
}

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
        dictionary = dictionary.get(key, {})
    return dictionary if isinstance(dictionary, str) else ''

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


def export_to_csv(data, fields, filename, field_mappings):
    row_count = 0
    with open(f"{filename}.csv", 'w', newline='', encoding='utf-8') as file:
        mapped_fields = [field_mappings.get(field, field) for field in fields]
        writer = csv.DictWriter(file, fieldnames=mapped_fields, quoting=csv.QUOTE_MINIMAL)
        writer.writeheader()
        for item in data:
            row_data = {field_mappings.get(field, field): get_nested_value(item, field) for field in fields}
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
    parser.add_argument("-t", "--token", help="Bearer token for authentication", required=True)
    parser.add_argument("-d", "--fields", help="Comma-separated data fields to export", required=True)
    parser.add_argument("-o", "--output", help="Output file name (without extension)", default=DEFAULT_OUTPUT_FILENAME)
    parser.add_argument("-e", "--export-format", 
                    help="Specify the export format: 'csv', 'markdown', or 'both'", 
                    choices=['csv', 'markdown', 'both'], 
                    default='both')

    args = parser.parse_args()

    try:
        query_params = json.loads(args.filters)
        fields = args.fields.split(',')

        response_data = query_jira(args.url, query_params, args.token, fields)

        # Since response_data is already a list of issues, we don't need to extract 'issues' from it
        data_to_export = response_data
        if not data_to_export:
            print("No issues found.")
            sys.exit(1)

    # Determine the export format
        if args.export_format in ['csv', 'both']:
                csv_row_count = export_to_csv(data_to_export, fields, args.output, field_mappings)
                print(f"Data exported to CSV successfully with {csv_row_count} rows in file: {args.output}.csv")

        if args.export_format in ['markdown', 'both']:
            md_row_count = export_to_markdown(data_to_export, fields, args.output, field_mappings)
            print(f"Data exported to Markdown successfully with {md_row_count} rows in file: {args.output}.md")
    except Exception as e:
            print(f"An error occurred: {e}")
