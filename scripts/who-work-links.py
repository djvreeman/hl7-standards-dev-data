import sys
from bs4 import BeautifulSoup

# Check if the file path is provided
if len(sys.argv) != 2:
    print("Usage: python script.py <path_to_html_file>")
    sys.exit(1)

# Get the file path from the command line argument
file_path = sys.argv[1]

# Open and read the HTML file
try:
    with open(file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()
except FileNotFoundError:
    print(f"File not found: {file_path}")
    sys.exit(1)

# Parse the HTML content using BeautifulSoup
soup = BeautifulSoup(html_content, 'html.parser')

# Find all elements with the 'data-url' attribute
commit_links = soup.find_all(attrs={"data-url": True})

# Extract and print the URLs
for link in commit_links:
    commit_url = link['data-url']
    print(f"https://github.com{commit_url}")