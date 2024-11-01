import requests
from bs4 import BeautifulSoup
import argparse
import csv
import os

# Parse command line arguments
parser = argparse.ArgumentParser(description='Extract HL7 Affiliate names from the webpage and save to a CSV file.')
parser.add_argument('-o', '--output', type=str, required=True, help='Output CSV file path')
args = parser.parse_args()

# Ensure the directory exists
output_dir = os.path.dirname(args.output)
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# URL to parse
url = "https://www.hl7.org/Special/committees/international/leadership.cfm"

# Headers dictionary with User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}

# Send a GET request with the User-Agent header
response = requests.get(url, headers=headers)

# Parse the HTML content of the page
soup = BeautifulSoup(response.content, "html.parser")

# Find all <div> elements with class 'demographics'
demographics_divs = soup.find_all("div", class_="demographics")

# Extract the text within the <b> tag for each <div class="demographics"> entry, excluding 'HL7 Affiliate'
affiliate_texts = []
for div in demographics_divs:
    b_tag = div.find("b")
    if b_tag and b_tag.text.strip() != "HL7 Affiliate":
        affiliate_texts.append([b_tag.text.strip()])

# Export to CSV
with open(args.output, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerows(affiliate_texts)

# Calculate the number of data rows written
data_rows_count = len(affiliate_texts)

# Print the count of data rows in the file
print(f"{data_rows_count} data rows have been written to {args.output}")
