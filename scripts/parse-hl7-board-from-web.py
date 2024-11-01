import requests
from bs4 import BeautifulSoup
import argparse
import csv
import os

# Parse command line arguments
parser = argparse.ArgumentParser(description='Extract HL7 Board of Directors details from the webpage and save to a CSV file.')
parser.add_argument('-o', '--output', type=str, required=True, help='Output CSV file path')
args = parser.parse_args()

# Ensure the directory exists
output_dir = os.path.dirname(args.output)
if not os.path.exists(output_dir):
    os.makedirs(output_dir)

# URL to parse
url = "https://www.hl7.org/about/hl7board.cfm"

# Headers dictionary with User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}

# Send a GET request with the User-Agent header
response = requests.get(url, headers=headers)

# Parse the HTML content of the page
soup = BeautifulSoup(response.content, "html.parser")

# Find all directory-member divs
members_divs = soup.find_all("div", class_="directory-member")

# Extract the title, name, and term expiry date
board_members = []
for div in members_divs:
    title_tag = div.find("b")
    name_tag = div.find("span", style="font-weight:400")
    term_tag = div.find("span", class_="directory-term")
    
    if title_tag and name_tag:
        title = title_tag.text.strip()
        name = name_tag.text.strip()
        term_expiry = term_tag.text.strip() if term_tag else "N/A"
        board_members.append([title, name, term_expiry])

# Export to CSV
with open(args.output, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerow(["Title", "Name", "Term Expiry"])
    writer.writerows(board_members)

# Calculate the number of data rows written
data_rows_count = len(board_members)

# Print the count of data rows in the file
print(f"{data_rows_count} data rows have been written to {args.output}")