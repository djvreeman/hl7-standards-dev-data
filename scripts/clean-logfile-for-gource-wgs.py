#!/usr/local/bin/python3
# -*- coding: utf-8 -*-
import argparse
import csv
from itertools import cycle
import requests
import xml.etree.ElementTree as ET
import html  # Import the html module for decoding HTML entities

# Predefined color palette
color_palette = [
    "FF5733", "C70039", "900C3F", "581845", "321414", "FFC300", "DAF7A6", "FFC312", "AEF35A",
    "33FF57", "34CB03", "245301", "57FF33", "75FF33", "33FFAD", "33FFF5", "33D7FF", "3375FF",
    "335AFF", "5733FF", "AD33FF", "F533FF", "FF33AB", "FF337A", "FF5733", "FF6E33", "FF8233",
    "D2B48C", "DEB887", "F4A460", "D2691E", "8B4513", "FFF8DC", "FFEBCD", "FFE4C4", "FFDEAD",
    "F5DEB3", "DEB887", "D2B48C", "BC8F8F", "F4A460", "DAA520", "B8860B", "CD853F", "D2691E",
    "808000", "6B8E23", "556B2F", "66CDAA", "8FBC8B", "20B2AA", "008B8B", "008080", "4682B4",
    "5F9EA0", "6495ED", "00BFFF", "1E90FF", "4169E1", "0000FF", "0000CD", "00008B", "000080",
    "191970", "8B008B", "800080", "4B0082", "483D8B", "6A5ACD", "7B68EE", "9370DB", "8A2BE2"
]
color_cycle = cycle(color_palette)

# URL to download the workgroup XML file
wg_xml_url = "https://raw.githubusercontent.com/HL7/JIRA-Spec-Artifacts/882815ca39da091054ad0156844725a74997626f/xml/_workgroups.xml"

def download_and_parse_workgroups(url):
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raises HTTPError for bad responses
        root = ET.fromstring(response.content)
        return {wg.get('key'): html.unescape(wg.get('name')) for wg in root.findall('workgroup') if wg.get('key') and wg.get('name')}
    except Exception as e:
        return None

# Fallback workgroup dictionary from the XML file
fallback_workgroup_dict = {
    # Include your fallback dictionary here
}

def clean_and_reformat_data(input_file, output_file, workgroup_dict):
    colors = {}  # Dictionary to keep track of assigned colors
    exclude_wg = {'eu', 'au-v2', 'au-fhir', 'NULL'}  # Define the set of WG to exclude

    with open(input_file, 'r') as file:
        reader = csv.DictReader(file, delimiter='|')
        fields = [field for field in reader.fieldnames if field != 'WG'] + ['new_field']
        with open(output_file, 'w', newline='') as output:
            for row in reader:
                # Skip rows with no 'Resolution Date'
                if not row['Resolution Date'].strip():
                    continue

                if row['WG'] and row['WG'] not in exclude_wg:
                    wg_name = workgroup_dict.get(row['WG'], row['WG']).replace('/', '-')
                    if row['WG'] not in colors:
                        colors[row['WG']] = next(color_cycle)

                    # Check for specific erroneous 'Specification' value and correct it
                    spec_value = row['Specification']
                    if "inputValues" in spec_value and "V2-lri" in spec_value:
                        spec_value = "V2-lri"

                    row['Specification'] = f"HL7/{wg_name}/{spec_value}"
                    row['new_field'] = colors[row['WG']]
                    del row['WG']
                    csv.DictWriter(output, fieldnames=fields, delimiter='|').writerow(row)


def main():
    parser = argparse.ArgumentParser(description="Cleans and reformats a '|' delimited data file.")
    parser.add_argument("-i", "--input_file", required=True, help="Path to the input file")
    parser.add_argument("-o", "--output_file", required=True, help="Path to the output file")
    args = parser.parse_args()
    
    # Try to download and parse the XML for workgroup dictionary
    workgroup_dict = download_and_parse_workgroups(wg_xml_url)
    if not workgroup_dict:
        workgroup_dict = fallback_workgroup_dict
    
    clean_and_reformat_data(args.input_file, args.output_file, workgroup_dict)

if __name__ == "__main__":
    main()
