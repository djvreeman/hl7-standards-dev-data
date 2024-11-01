import requests
from bs4 import BeautifulSoup
import pandas as pd
import re
import time
import argparse
import csv

# Initialize an empty list to store data
data = []

# Function to scrape a package's page and extract editor/author information
def scrape_package(package_id, url, version="unknown"):
    row_added = False  # Track if a valid row was added

    try:
        print(f"Scraping {package_id} (version: {version}) from {url}")
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"})
        response.raise_for_status()

        soup = BeautifulSoup(response.text, 'html.parser')

        # Search for "Credits" or "Authors" sections
        section = soup.find(string=re.compile(r"(credits|contributors|authors|acknowledgments)", re.I))

        if section:
            print(f"Found section: {section}")
            parent = section.find_parent()

            # Extract from table if it exists, otherwise extract from text
            if parent.find("table"):
                row_added = extract_from_table(parent, package_id, version)
            else:
                row_added = extract_from_text(parent.get_text(strip=True), package_id, version)
        else:
            print("No relevant section found.")

    except Exception as e:
        print(f"Failed to scrape {url}: {e}")

    # If no valid row was added, add a placeholder row with null values
    if not row_added:
        print("No valid data found. Adding placeholder row.")
        add_placeholder_row(package_id, version)

# Function to extract data from a table
def extract_from_table(parent, package_id, version):
    row_added = False
    for row in parent.find_all("tr"):
        columns = row.find_all("td")
        if len(columns) >= 2:
            name = columns[0].get_text(strip=True)
            email_element = columns[1].find("a", href=re.compile(r"mailto:"))
            email = email_element['href'].replace("mailto:", "") if email_element else None
            first_name, last_name = parse_name(name)
            add_data_row(package_id, version, first_name, last_name, None, email)
            row_added = True  # Mark that a row was added
    return row_added

# Function to extract data from text
def extract_from_text(text, package_id, version):
    row_added = False
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    for line in lines:
        # Skip section headers (like "Authors" or "Credits")
        if re.match(r"(credits|contributors|authors|acknowledgments)", line, re.I):
            continue

        # Try to extract name and affiliation if present
        match = re.match(r"([A-Za-z ,\(\)-]+),?\s*(.*)", line)
        if match:
            name, role = match.groups()
            first_name, last_name = parse_name(name)
            role = role if role else None
            add_data_row(package_id, version, first_name, last_name, role, None)
            row_added = True  # Mark that a row was added
    return row_added

# Function to parse names into first and last names
def parse_name(name):
    if not name:
        return None, None
    parts = name.split()
    return parts[0], " ".join(parts[1:]) if len(parts) > 1 else None

# Function to add a data row
def add_data_row(package_id, version, first_name, last_name, role, email):
    data.append([package_id, version, first_name, last_name, role, email])

# Function to add a placeholder row if no valid data is found
def add_placeholder_row(package_id, version):
    data.append([package_id, version, None, None, None, None])

# Function to save collected data to CSV
def save_to_csv(filename="package_editors.csv"):
    df = pd.DataFrame(data, columns=["package-id", "version", "editor-first-name", "editor-last-name", "role", "email"])
    df.to_csv(filename, index=False)
    print(f"Data collection complete. CSV saved as '{filename}'.")

# Function to scrape data from a CSV input file
def scrape_from_csv(input_file):
    with open(input_file, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            scrape_package(row['package-id'], row['url'], row['version'])
            time.sleep(2)  # Add delay to avoid overloading the server

# Main function to handle command-line arguments
def main():
    parser = argparse.ArgumentParser(description="Scrape package editor and author information from canonical URLs.")
    parser.add_argument("-p", "--package-id", help="The package ID to scrape")
    parser.add_argument("-v", "--version", help="The version of the package")
    parser.add_argument("-u", "--url", help="The canonical URL of the package")
    parser.add_argument("-i", "--input-csv", help="Path to input CSV file with package details")
    parser.add_argument("-o", "--output-csv", default="package_editors.csv", help="Name of the output CSV file")

    args = parser.parse_args()

    if args.input_csv:
        scrape_from_csv(args.input_csv)
    elif args.package_id and args.version and args.url:
        scrape_package(args.package_id, args.url, args.version)
    else:
        print("Error: Provide either package ID, version, and URL, or an input CSV file.")
        parser.print_help()
        return

    save_to_csv(args.output_csv)

if __name__ == "__main__":
    main()