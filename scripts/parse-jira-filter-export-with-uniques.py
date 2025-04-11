import argparse
import csv
import requests
import json
from collections import Counter
from datetime import datetime, timezone
import unicodedata

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
    'fields.resolutiondate': 'Resolution Date'
}

def fetch_jira_data(jql_filter):
    try:
        jql_query = json.loads(jql_filter)["jql"]
    except (json.JSONDecodeError, KeyError):
        print("Error: Invalid JQL filter format. Ensure it is in JSON format, e.g., '{\"jql\": \"filter = 22917\"}'")
        return []
    
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}", "Content-Type": "application/json"}
    start_at = 0
    max_results = 100
    all_issues = []
    
    while True:
        params = {"jql": jql_query, "maxResults": max_results, "startAt": start_at}
        response = requests.get(DEFAULT_BASE_URL, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Error fetching JIRA data: {response.status_code} {response.text}")
            return all_issues
        
        data = response.json()
        issues = data.get("issues", [])
        all_issues.extend(issues)
        
        if len(issues) < max_results:
            break  # Exit loop if no more results
        
        start_at += max_results
    
    return all_issues

def normalize_name(name):
    if not name:
        return None
    return unicodedata.normalize("NFKC", name).strip()

def export_to_csv(data, fields, filename, field_mappings, unique):
    reporter_counts = Counter()
    row_count = 0
    
    # Adjust fieldnames for unique mode
    fieldnames = [field_mappings.get(field, field) for field in fields]
    if unique:
        fieldnames = ['Reporter', 'Count']
    
    with open(f"{filename}.csv", 'w', newline='', encoding='utf-8') as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        
        for item in data:
            row_data = {}
            for field in fields:
                value = extract_field_value(item, field)
                if field == 'fields.creator.displayName':
                    if value:
                        normalized_value = normalize_name(value)
                        if normalized_value:
                            reporter_counts[normalized_value] += 1
                row_data[field_mappings.get(field, field)] = value
            
            if not unique:
                writer.writerow(row_data)
                row_count += 1
        
        if unique:
            for reporter, count in reporter_counts.items():
                writer.writerow({'Reporter': reporter, 'Count': count})
                row_count += 1
            print(f"Total unique issue reporters: {len(reporter_counts)}")
    
    return row_count

def extract_field_value(item, field):
    keys = field.split('.')
    value = item
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return ""
    return value

def export_to_markdown(data, fields, filename, field_mappings):
    row_count = 0
    with open(f"{filename}.md", 'w', encoding='utf-8') as file:
        mapped_fields = [field_mappings.get(field, field) for field in fields]
        file.write(" | ".join(mapped_fields) + "\n")
        file.write(" | ".join(["---"] * len(mapped_fields)) + "\n")
        for item in data:
            row_data = [str(extract_field_value(item, field)) for field in fields]
            file.write(" | ".join(row_data) + "\n")
            row_count += 1
    return row_count

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-f", "--filter", required=True, help="JQL filter JSON")
    parser.add_argument("-d", "--data-fields", required=True, help="Fields to extract")
    parser.add_argument("-o", "--output", default=DEFAULT_OUTPUT_FILENAME, help="Output filename")
    parser.add_argument("-e", "--export", choices=["csv", "markdown", "both"], required=True, help="Export format")
    parser.add_argument("-u", "--unique", action="store_true", help="Output unique issue reporters with count")
    args = parser.parse_args()
    
    data_fields = args.data_fields.split(',')
    output_filename = args.output
    unique_reporters = args.unique
    
    jira_data = fetch_jira_data(args.filter)
    
    if args.export in ["csv", "both"]:
        export_to_csv(jira_data, data_fields, output_filename, field_mappings, unique_reporters)
    
    if args.export in ["markdown", "both"]:
        export_to_markdown(jira_data, data_fields, output_filename, field_mappings)
