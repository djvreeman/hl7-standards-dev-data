import requests
import json
import csv
import sys
import argparse
from bs4 import BeautifulSoup
import re
import time

def normalize_realm(realm):
    """
    Normalize realm values to ensure consistency.
    """
    if not realm:
        return ""
    
    # Normalize US Realm to United States
    if realm.strip().lower() == "us realm":
        return "United States"
    
    return realm.strip()

def get_explicit_realm_mappings():
    """
    Define explicit mappings for URLs to realms that can't be determined automatically.
    Return a dictionary mapping URLs to their corresponding realms.
    """
    # Add your explicit mappings here
    return {
        # Examples (these are already handled by the code, just for demonstration):
        # "http://hl7.org/fhir": "Universal",
        # "http://example.org/some/specific/url": "United States",
        
        # Add your custom mappings below:
        
    }

def get_explicit_key_mappings():
    """
    Define explicit mappings for keys to realms for entries that have no URL
    or where the URL-based determination fails.
    Return a dictionary mapping keys to their corresponding realms.
    """
    # Universal realm keys
    universal_keys = [
        "CDA-cda-sd", "CDA-gh", "FHIR-fhirpath", "FHIR-cds-hooks",
        "FHIR-cds-hooks-library", "FHIR-cds-hooks-patient-view", "FHIR-smart", "FHIR-cql",
        "FHIR-extensions", "FHIR-tools", "FHIR-cqif", "FHIR-gao",
        "V2-core", "V2-vtwoplus", "V2-vtwostdqc", "V2-vtwoigqc",
        "V2-vtwotofhir",
        "OTHER-ufp", "OTHER-ai-ml", "OTHER-ct-dam", "OTHER-dam-nc", "OTHER-pcd", "OTHER-pohr",
        "OTHER-stmed-profile", "OTHER-stterm-kb",
        "OTHER-sfm-consent", "OTHER-gender-harmony", "OTHER-arden-syntax",
        "OTHER-guide-arden-syntax", "OTHER-odh-dam", "OTHER-sdpi"
    ]
    
    # United States realm keys
    us_keys = [
        # Add United States realm keys here
        # For example:
        # "FHIR-us-core", "CDA-us-realm"
        "CDA-ccda", "CDA-ccda-two-one-odh", "CDA-haiaultc",
        "CDA-phcaserpt", "CDA-phcr-rr", "CDA-trds",
        "FHIR-us-helios-bulk", "FHIR-us-qr", "FHIR-us-argonaut", "FHIR-us-lab",
        "V2-ss", "V2-dar", "V2-loi", "V2-lri", "V2-edos-aoe",
        "OTHER-us-pod-fp", "OTHER-us-pchit-fp", "OTHER-hsra", "OTHER-pharm-consult",
    ]
    
    # Create mappings dictionary
    mappings = {}
    
    # Add Universal realm mappings
    for key in universal_keys:
        mappings[key] = "Universal"
    
    # Add United States realm mappings
    for key in us_keys:
        mappings[key] = "United States"
    
    # Custom realm mappings for specific keys
    custom_mappings = {
        "FHIR-au-base": "Australia",
        "FHIR-au-core": "Australia",
        "FHIR-au-erequesting": "Australia",
        "FHIR-au-pd": "Australia",
        "FHIR-au-ps": "Australia",
        "FHIR-eu-laboratory": "Europe",
        "FHIR-eu-extensions": "Europe",
        # Add more custom mappings as needed
    }
    
    # Add custom mappings (these will override any previous mappings if there are duplicates)
    mappings.update(custom_mappings)
    
    return mappings

def main():
    # Set up command-line argument parsing
    parser = argparse.ArgumentParser(
        description='Fetch SPECS.json from GitHub and extract specified fields to a CSV file.'
    )
    parser.add_argument('-o', '--output', default='specs_extracted.csv',
                        help='Path to the output CSV file (default: specs_extracted.csv)')
    parser.add_argument('--no-scrape', action='store_true',
                        help='Skip web scraping for realm information')
    parser.add_argument('--missing-realms', default='missing_realms.txt',
                        help='Path to output file listing URLs with missing realm info (default: missing_realms.txt)')
    args = parser.parse_args()

    # URL for the SPECS.json file
    url = "https://github.com/HL7/JIRA-Spec-Artifacts/raw/refs/heads/gh-pages/SPECS.json"
    output_file = args.output
    missing_realms_file = args.missing_realms
    
    # Get explicit realm mappings
    explicit_realm_mappings = get_explicit_realm_mappings()
    explicit_key_mappings = get_explicit_key_mappings()
    
    # Track URLs with missing realm information
    missing_realms = []
    # Track keys with missing realm information
    missing_keys = []
    
    try:
        # Add user-agent header to avoid potential blocking
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        # Fetch the JSON data
        print(f"Fetching data from {url}...")
        response = requests.get(url, headers=headers)
        response.raise_for_status()  # Raise an exception for HTTP errors
        
        # Parse the JSON data
        specs_data = response.json()
        print(f"Successfully fetched data. Processing...")
        
        # Extract the required fields and write to CSV
        with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
            fieldnames = ['key', 'name', 'defaultWorkgroup', 'url', 'realm']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            
            # Write header
            writer.writeheader()
            
            # Process each item in the JSON
            count = 0
            for item in specs_data:
                url = item.get('url', '')
                
                # Determine realm based on URL pattern
                realm = ''
                key = item.get('key', '')
                
                # First check explicit mappings
                if url in explicit_realm_mappings:
                    realm = explicit_realm_mappings[url]
                # Check key mappings if we have a key
                elif key and key in explicit_key_mappings:
                    realm = explicit_key_mappings[key]
                # Then try automatic detection
                elif url == 'http://hl7.org/fhir':
                    realm = 'Universal'
                elif 'http://hl7.org/fhir/uv/' in url:
                    realm = 'Universal'
                elif 'http://hl7.org/fhir/us/' in url:
                    realm = 'United States'
                elif url.startswith('http://www.hl7.org/implement/standards/product_brief.cfm?product_id=') and not args.no_scrape:
                    # For product brief URLs, scrape the web page to find the REALM
                    try:
                        print(f"Scraping realm information from {url}")
                        response = requests.get(url, headers=headers)
                        response.raise_for_status()
                        
                        # Parse the HTML
                        soup = BeautifulSoup(response.text, 'html.parser')
                        
                        # Find the REALM section
                        realm_heading = soup.find('h3', string='REALM')
                        if realm_heading:
                            # Get the list item that follows the REALM heading
                            realm_list = realm_heading.find_next('ul')
                            if realm_list:
                                realm_item = realm_list.find('li', class_='box-list')
                                if realm_item:
                                    realm = normalize_realm(realm_item.text.strip())
                        
                        # Add a small delay to avoid overwhelming the server
                        time.sleep(0.5)
                    except Exception as e:
                        print(f"Error scraping realm from {url}: {e}")
                        # Continue processing other items even if this one fails
                
                # Add to CSV
                row = {
                    'key': item.get('key', ''),
                    'name': item.get('name', ''),
                    'defaultWorkgroup': item.get('defaultWorkgroup', ''),
                    'url': url,
                    'realm': realm
                }
                
                # Track URLs with missing realm information
                if not realm:
                    if url:
                        missing_realms.append(url)
                    if key and not url:  # Only track keys with no URL
                        missing_keys.append(key)
                
                # Write the row to the CSV file
                writer.writerow(row)
                count += 1
            
        print(f"Successfully extracted {count} items to {output_file}")
        
        # Write missing realms to file
        with open(missing_realms_file, 'w', encoding='utf-8') as f:
            if missing_realms:
                f.write("# URLs with missing realm information\n")
                f.write("# Add these to the explicit_realm_mappings if known\n\n")
                f.write("## URLs without realm information:\n")
                for url in sorted(missing_realms):
                    f.write(f"{url}\n")
                f.write(f"\nTotal: {len(missing_realms)} URLs\n\n")
            
            if missing_keys:
                f.write("## Keys without URLs or realm information:\n")
                f.write("# Add these to the explicit_key_mappings if known\n\n")
                for key in sorted(missing_keys):
                    f.write(f"{key}\n")
                f.write(f"\nTotal: {len(missing_keys)} keys\n")
            
            if not missing_realms and not missing_keys:
                f.write("# All entries have realm information.")
        
        print(f"Wrote {len(missing_realms)} URLs and {len(missing_keys)} keys with missing realm information to {missing_realms_file}")
        
        if not missing_realms and not missing_keys:
            print("All entries have realm information.")
        
    except requests.exceptions.RequestException as e:
        print(f"Error fetching data: {e}")
        sys.exit(1)
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON data: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()