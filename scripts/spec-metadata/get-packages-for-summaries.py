import requests
import csv
import sys

# Check if an output filename is provided
if len(sys.argv) < 2:
    print("Usage: python script.py <output_filename.csv>")
    sys.exit(1)

output_file = sys.argv[1]

# GitHub API URL for the directory contents
url = "https://api.github.com/repos/HL7/plain-language/contents/summaries"

# Send request to GitHub API
response = requests.get(url)
if response.status_code != 200:
    print(f"Failed to fetch files. Status code: {response.status_code}")
    sys.exit(1)

# Parse the JSON response to extract filenames
data = response.json()
filenames = [item['name'].replace('.md', '') for item in data if item['name'].endswith('.md')]

# Write filenames to the specified CSV file without a header row
with open(output_file, "w", newline="") as csvfile:
    writer = csv.writer(csvfile)
    for filename in filenames:
        writer.writerow([filename])

print(f"CSV file '{output_file}' has been created.")