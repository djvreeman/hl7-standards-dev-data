#!/usr/bin/env python3
"""
parse-hl7-agreements-from-web.py

This script extracts organization entries and optionally downloads PDF files from the
HL7 Agreements and SOUs webpage (https://www.hl7.org/about/agreements.cfm).

USAGE:
    Basic usage - Extract entries to CSV only:
        python parse-hl7-agreements-from-web.py -o output.csv
    
    Extract entries and download PDFs:
        python parse-hl7-agreements-from-web.py -o output.csv --download-pdfs --pdf-dir ./pdfs
    
    Extract entries and download PDFs to a specific directory:
        python parse-hl7-agreements-from-web.py -o data/agreements.csv --download-pdfs --pdf-dir data/agreement-pdfs

REQUIREMENTS:
    - requests: HTTP library for fetching web pages
    - beautifulsoup4: HTML parsing library
    
    Install with:
        pip install requests beautifulsoup4

OUTPUT:
    - CSV file containing organization entries (one per row)
    - Optional: PDF files downloaded to specified directory (if --download-pdfs is used)

CSV FORMAT:
    The CSV file contains a single column with organization names extracted from the
    "HL7 Agreements and SOUs" section of the webpage.

PDF DOWNLOAD:
    When --download-pdfs is specified:
    - All PDF links found in the agreements section will be downloaded
    - PDFs are saved to the directory specified by --pdf-dir (default: ./pdfs)
    - Existing PDFs are skipped (not re-downloaded)
    - PDF filenames are sanitized to be filesystem-safe
    - Progress messages indicate successful downloads and any failures

ERROR HANDLING:
    - Network errors are caught and reported
    - Missing directories are created automatically
    - Invalid URLs are skipped with warning messages
    - Failed downloads are logged but don't stop the script

EXAMPLES:
    1. Extract entries only:
       python parse-hl7-agreements-from-web.py -o agreements.csv
    
    2. Extract entries and download PDFs to default location (./pdfs):
       python parse-hl7-agreements-from-web.py -o agreements.csv --download-pdfs
    
    3. Extract entries and download PDFs to custom directory:
       python parse-hl7-agreements-from-web.py -o data/agreements.csv --download-pdfs --pdf-dir data/agreement-pdfs
    
    4. Download PDFs only (if you already have the CSV):
       python parse-hl7-agreements-from-web.py -o temp.csv --download-pdfs --pdf-dir ./my-pdfs

NOTES:
    - The script uses a User-Agent header to avoid being blocked by the server
    - PDF links are extracted from anchor tags in the "HL7 Agreements and SOUs" section
    - Relative URLs are converted to absolute URLs using the base page URL
    - The script preserves the original PDF filenames when possible, sanitizing only
      characters that are invalid for filesystem names
"""

import requests
from bs4 import BeautifulSoup
import argparse
import csv
import os
import re
from urllib.parse import urljoin, urlparse

def sanitize_filename(filename):
    """
    Sanitize a filename to be filesystem-safe.
    
    Removes or replaces characters that are invalid in filenames on most operating systems.
    Preserves the file extension.
    
    Args:
        filename: Original filename string
        
    Returns:
        Sanitized filename string safe for filesystem use
    """
    # Remove invalid characters for filenames
    # Keep alphanumeric, spaces, dots, hyphens, underscores
    sanitized = re.sub(r'[<>:"/\\|?*]', '_', filename)
    # Remove leading/trailing spaces and dots
    sanitized = sanitized.strip(' .')
    # Replace multiple spaces/underscores with single underscore
    sanitized = re.sub(r'[_\s]+', '_', sanitized)
    return sanitized

def download_pdf(pdf_url, output_dir, headers):
    """
    Download a PDF file from a URL to a specified directory.
    
    Args:
        pdf_url: Full URL of the PDF to download
        output_dir: Directory where the PDF should be saved
        headers: HTTP headers dictionary to use for the request
        
    Returns:
        tuple: (success: bool, filename: str, error_message: str or None)
    """
    try:
        # Get the filename from the URL
        parsed_url = urlparse(pdf_url)
        filename = os.path.basename(parsed_url.path)
        
        # If no filename in URL, generate one from the URL
        if not filename or not filename.endswith('.pdf'):
            filename = sanitize_filename(parsed_url.path.split('/')[-1]) + '.pdf'
            if filename == '.pdf':
                filename = 'document.pdf'
        
        # Sanitize the filename
        filename = sanitize_filename(filename)
        if not filename.endswith('.pdf'):
            filename += '.pdf'
        
        output_path = os.path.join(output_dir, filename)
        
        # Skip if file already exists
        if os.path.exists(output_path):
            return (True, filename, "already exists")
        
        # Download the PDF with streaming for large files
        response = requests.get(pdf_url, headers=headers, stream=True, timeout=30)
        response.raise_for_status()
        
        # Check if the response is actually a PDF
        content_type = response.headers.get('Content-Type', '').lower()
        if 'pdf' not in content_type and not pdf_url.lower().endswith('.pdf'):
            return (False, filename, f"Content-Type is {content_type}, not PDF")
        
        # Write the file in chunks to handle large files
        with open(output_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        return (True, filename, None)
    
    except requests.exceptions.RequestException as e:
        return (False, filename if 'filename' in locals() else 'unknown.pdf', str(e))
    except Exception as e:
        return (False, filename if 'filename' in locals() else 'unknown.pdf', f"Unexpected error: {str(e)}")

# Parse command line arguments
parser = argparse.ArgumentParser(
    description='Extract organization entries from the HL7 Agreements webpage and optionally download PDF files.',
    formatter_class=argparse.RawDescriptionHelpFormatter,
    epilog="""
Examples:
  # Extract entries only:
  python parse-hl7-agreements-from-web.py -o agreements.csv
  
  # Extract entries and download PDFs:
  python parse-hl7-agreements-from-web.py -o agreements.csv --download-pdfs --pdf-dir ./pdfs
    """
)
parser.add_argument('-o', '--output', type=str, required=True,
                    help='Output CSV file path')
parser.add_argument('--download-pdfs', action='store_true',
                    help='Download PDF files linked on the agreements page')
parser.add_argument('--pdf-dir', type=str, default='./pdfs',
                    help='Directory to save downloaded PDFs (default: ./pdfs). Only used if --download-pdfs is specified.')
args = parser.parse_args()

# Ensure the output directory exists
output_dir = os.path.dirname(args.output)
if output_dir and not os.path.exists(output_dir):
    os.makedirs(output_dir)

# Ensure the PDF directory exists if downloading PDFs
if args.download_pdfs:
    if not os.path.exists(args.pdf_dir):
        os.makedirs(args.pdf_dir)
        print(f"Created PDF directory: {args.pdf_dir}")

# URL to parse
url = "https://www.hl7.org/about/agreements.cfm"

# Headers dictionary with User-Agent
headers = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.36'
}

# Send a GET request with the User-Agent header
try:
    print(f"Fetching page: {url}")
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
except requests.exceptions.RequestException as e:
    print(f"Error fetching webpage: {e}")
    exit(1)

# Parse the HTML content of the page
soup = BeautifulSoup(response.content, "html.parser")

# Find the specific container
containers = soup.find_all('div', class_='linkboxcontainer')
target_entries = []
pdf_links = []

# Loop through each container to find the correct one
for container in containers:
    h3 = container.find('h3')
    if h3 and 'HL7 Agreements and SOUs' in h3.text:
        # Extract the entries
        entries = container.find_all('a')
        for entry in entries:
            entry_text = entry.text.strip()
            target_entries.append([entry_text])
            
            # Extract PDF links if download is requested
            if args.download_pdfs:
                href = entry.get('href')
                if href:
                    # Convert relative URLs to absolute
                    full_url = urljoin(url, href)
                    # Check if it's a PDF link
                    if full_url.lower().endswith('.pdf') or '.pdf' in full_url.lower():
                        pdf_links.append({
                            'url': full_url,
                            'text': entry_text
                        })

# Export to CSV
with open(args.output, 'w', newline='', encoding='utf-8') as csvfile:
    writer = csv.writer(csvfile)
    writer.writerows(target_entries)

# Print the count of data rows in the file
data_rows_count = len(target_entries)
print(f"\n{data_rows_count} data rows have been written to {args.output}")

# Download PDFs if requested
if args.download_pdfs:
    if pdf_links:
        print(f"\nFound {len(pdf_links)} PDF link(s). Starting downloads...")
        successful_downloads = 0
        skipped_downloads = 0
        failed_downloads = 0
        
        for i, pdf_info in enumerate(pdf_links, 1):
            pdf_url = pdf_info['url']
            pdf_text = pdf_info['text']
            print(f"\n[{i}/{len(pdf_links)}] Processing: {pdf_text}")
            print(f"  URL: {pdf_url}")
            
            success, filename, error_msg = download_pdf(pdf_url, args.pdf_dir, headers)
            
            if success:
                if error_msg == "already exists":
                    print(f"  ✓ Skipped (already exists): {filename}")
                    skipped_downloads += 1
                else:
                    print(f"  ✓ Downloaded: {filename}")
                    successful_downloads += 1
            else:
                print(f"  ✗ Failed: {error_msg}")
                failed_downloads += 1
        
        print(f"\n{'='*60}")
        print(f"Download Summary:")
        print(f"  Successful: {successful_downloads}")
        print(f"  Skipped (already exists): {skipped_downloads}")
        print(f"  Failed: {failed_downloads}")
        print(f"  Total: {len(pdf_links)}")
        print(f"  PDFs saved to: {os.path.abspath(args.pdf_dir)}")
        print(f"{'='*60}")
    else:
        print("\nNo PDF links found in the agreements section.")