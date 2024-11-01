import requests
from bs4 import BeautifulSoup
import argparse
import csv
import os

# Parse command line arguments
parser = argparse.ArgumentParser(description='Extract specific organization entries from the HL7 webpage and save to a CSV file.')
parser.add_argument('-o', '--output', type=str, required=True, help='Output CSV file path')
args = parser.parse_args()

# Ensure the directory exists
output_dir = os.path.dirname(args.output)
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# URL to parse
url = "https://www.hl7.org/about/benefactors.cfm"

# Headers dictionary with User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}

# Send a GET request with the User-Agent header
response = requests.get(url, headers=headers)

# Print the retrieved HTML for troubleshooting
print(response.text)  # Add this line for debugging

# Parse the HTML content of the page
soup = BeautifulSoup(response.content, "html.parser")

# Find the specific container
containers = soup.find_all('div', class_='linkboxcontainer')
target_entries = []

# Loop through each container to find the correct one
for container in containers:
    h2 = container.find('h2')
    if h2:
        # Extract the entries
        entries = container.find_all('a')
        for entry in entries:
            target_entries.append([entry.text.strip()])

# Export to CSV
with open(args.output, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerows(target_entries)

# Print the count of data rows in the file
data_rows_count = len(target_entries)
print(f"{data_rows_count} data rows have been written to {args.output}")