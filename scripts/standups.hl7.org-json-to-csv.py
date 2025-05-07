#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Overview:
#
# This simple script calls the standups.hl7.org json API and returns a cleaned-up csv file.
#
# Example usage:
# python3 scripts/standups.hl7.org-json-to-csv.py -p 4


try:
    # For Python 3.0 and later
    from urllib.request import urlopen
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import urlopen

import getopt
import re    
import json
import csv
import sys
import urllib
import argparse
import getpass
import datetime

# Format current date and time as YYYYMMDD-HHMMSS
current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

# Get Command Line Arguments
parser = argparse.ArgumentParser(
    formatter_class=argparse.ArgumentDefaultsHelpFormatter)
parser.add_argument("-p", help="enter page of search results", default="1")
# Adding '-o' argument for output filename
parser.add_argument('-o', '--output', type=str, default=f"data/working/standups.hl7.org/{current_time}_standups.hl7.org.csv", help='The output CSV file name')
    
args = parser.parse_args()
password = getpass.getpass("Remote Password (or skip for no auth): ")

# Setup some variables
server = "http://standups.hl7.org/wp-json/wp/v2/posts"
page = args.p
params = "?_fields=title,date&per_page=100&order=asc&page="
dataOutput = "data/working/standups.hl7.org/standups.hl7.org" + page + ".csv"
fhirHeader = {}
#fhirHeader['Content-Type'] = "application/fhir+json;charset=utf-8"

serverUrl = server + '/' + params + page 
print(serverUrl)

# create an authorization handler if needed

if password:
    p = urllib.request.HTTPPasswordMgrWithDefaultRealm()
    p.add_password(None, fhirServer, args.username, password)

    auth_handler = urllib.request.HTTPBasicAuthHandler(p)
    opener = urllib.request.build_opener(auth_handler)
    urllib.request.install_opener(opener)
    req = urllib.request.Request(url=serverUrl, headers=fhirHeader, method='GET')
    r = opener.open(req)
else:
    req = urllib.request.Request(url=serverUrl, headers=fhirHeader, method='GET')
    r = urllib.request.urlopen(req)

dataJSON = json.loads(r.read().decode(r.info().get_param('charset') or 'utf-8'))

with open(args.output, mode='w') as csv_file:
    csvWriter = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    for spec in dataJSON:
        try: 
            specDate = spec["date"]
            datetimeobj=datetime.datetime.strptime(specDate, "%Y-%m-%dT%H:%M:%S")
            simpleDate = datetimeobj.date()
            simpleDateMonth = simpleDate.strftime('%Y %m')
            #print (simpleDateMonth)
            specName = spec["title"]["rendered"]
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
            #print (family)
            csvWriter.writerow([simpleDateMonth,specDate,simpleDate,specName,simpleSpecName,family])
        except:
            specDate = spec["date"]
            specName = spec["title"]["rendered"]
            csvWriter.writerow([specDate,specName])