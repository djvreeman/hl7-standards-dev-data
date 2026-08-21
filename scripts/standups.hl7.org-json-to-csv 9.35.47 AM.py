#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Overview:
#
# This simple script calls the standups.hl7.org json API and returns a cleaned-up csv file.
# By default, it fetches all pages. Use -p to fetch a specific page only.
#
# Example usage:
# python3 scripts/standups.hl7.org-json-to-csv.py              # Fetch all pages
# python3 scripts/standups.hl7.org-json-to-csv.py -p 4          # Fetch only page 4


import json
import csv
import urllib.request
import argparse
import datetime
import html
import re

# Format current date and time as YYYYMMDD-HHMMSS
current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

# Get Command Line Arguments
parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-p", help="enter specific page of search results (if not specified, all pages will be fetched)", type=int, default=None)
# Adding '-o' argument for output filename
parser.add_argument('-o', '--output', type=str, default=f"data/working/standups.hl7.org/{current_time}_standups.hl7.org.csv", help='The output CSV file name')
    
args = parser.parse_args()

# Setup some variables
server = "http://standups.hl7.org/wp-json/wp/v2/posts"
params = "?_fields=title,date&per_page=100&order=asc&page="
headers = {}

def fetch_page(page_num):
    """Fetch a single page from the API and return the JSON data and total pages."""
    serverUrl = server + '/' + params + str(page_num)
    print(f"Fetching page {page_num}: {serverUrl}")
    
    req = urllib.request.Request(url=serverUrl, headers=headers, method='GET')
    r = urllib.request.urlopen(req)
    
    # Get total pages from response headers if available
    total_pages = None
    if 'X-WP-TotalPages' in r.headers:
        total_pages = int(r.headers['X-WP-TotalPages'])
    
    dataJSON = json.loads(r.read().decode(r.info().get_param('charset') or 'utf-8'))
    return dataJSON, total_pages

def process_spec(spec, csvWriter):
    """Process a single spec entry and write it to CSV."""
    try: 
        specDate = spec["date"]
        datetimeobj=datetime.datetime.strptime(specDate, "%Y-%m-%dT%H:%M:%S")
        simpleDate = datetimeobj.date()
        simpleDateMonth = simpleDate.strftime('%Y %m')
        #print (simpleDateMonth)
        specName = spec["title"]["rendered"]
        # Decode HTML entities first
        specName = html.unescape(specName)
        simpleSpecName = specName.replace(" Publication of",":")
        simpleSpecName = simpleSpecName.replace(" publication of",":")
        simpleSpecName = simpleSpecName.replace("Implementation Guide","IG")
        simpleSpecName = simpleSpecName.replace("&#8211;","-")
        simpleSpecName = simpleSpecName.replace("HL7 ","")
        print (simpleSpecName)
        if "FHIR" in simpleSpecName:
            family = "FHIR"
        elif "Version 2" in simpleSpecName:
            family = "V2"
        elif "V2" in simpleSpecName:
            family = "V2"
        elif "Version 3" in simpleSpecName:
            family = "V3"
        elif "V3" in simpleSpecName:
            family = "V3"
        elif "CDA" in simpleSpecName:
            family = "CDA"
        elif "Clinical Document Architecture" in simpleSpecName:
            family = "CDA"
        else:
            family = "OTHER"
        
        # Determine publication status based on title
        if re.search(r'(?i)(retirement|retired)', simpleSpecName):
            pubStatus = "Retirement"
        elif re.search(r'(?i)reaffirmation', simpleSpecName):
            pubStatus = "Reaffirmation"
        else:
            pubStatus = "Publication"
        
        #print (family)
        csvWriter.writerow([simpleDateMonth,specDate,simpleDate,specName,simpleSpecName,pubStatus,family])
    except:
        specDate = spec["date"]
        specName = spec["title"]["rendered"]
        # Decode HTML entities in exception case too
        specName = html.unescape(specName)
        # Default values for exception case
        simpleSpecName = specName
        pubStatus = "Publication"  # Default to Publication if we can't parse
        family = "OTHER"  # Default to OTHER if we can't parse
        csvWriter.writerow([specDate,specDate,specDate,specName,simpleSpecName,pubStatus,family])

# Open CSV file and write header
with open(args.output, mode='w', encoding='utf-8-sig') as csv_file:
    csvWriter = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    # Write header row
    csvWriter.writerow(['Date_Month', 'Date_Full', 'Date_Simple', 'Title_Original', 'Title_Cleaned', 'Pub Status', 'Family'])
    
    if args.p is not None:
        # Fetch only the specified page
        dataJSON, _ = fetch_page(args.p)
        for spec in dataJSON:
            process_spec(spec, csvWriter)
    else:
        # Fetch all pages
        page_num = 1
        total_pages = None
        
        while True:
            dataJSON, total_pages = fetch_page(page_num)
            
            # If no data returned, we're done
            if not dataJSON:
                break
            
            # Process all specs in this page
            for spec in dataJSON:
                process_spec(spec, csvWriter)
            
            # If we know the total pages and we've reached it, stop
            if total_pages is not None and page_num >= total_pages:
                break
            
            # If we got fewer than per_page items, we're likely on the last page
            if len(dataJSON) < 100:
                break
            
            page_num += 1
        
        print(f"\nCompleted fetching all pages. Total pages processed: {page_num}")