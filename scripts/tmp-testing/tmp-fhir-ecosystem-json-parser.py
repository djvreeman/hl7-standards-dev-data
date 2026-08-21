#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Overview:
#
# This script reads in a Git JSON export of a repo's release history, and 
# and exports a CSV with the release tag, published date, and author

# Usage:
# python3 github-release-json-to-csv.py -i SoftwareReleases/publisher-releases.json -o SoftwareReleases/publisher-releases.csv

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
from datetime import datetime

#Get Command Line Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-i", help="file name of input JSON file", required=True)
parser.add_argument("-o", help="file name of output CSV file", required=True)
parser.add_argument("-ig", help="dependent IG to look for", required=False)
#parser.add_argument("-r", help="name of GitHub repo e.g. fhir-ig-publisher", required=True)

args = parser.parse_args()

# Setup file names 
JsonInputFileName = args.i
csvOutputFileName = args.o
targetSpecName = args.ig

#repo = args.r


# Setup some variables
#params = "?_fields=title,date&per_page=100&order=asc&page="
dataOutput = csvOutputFileName
#fhirHeader = {}
#fhirHeader['Content-Type'] = "application/fhir+json;charset=utf-8"
#serverUrl = server + '/' + params + page 
#print(serverUrl)

# Lets get the Github JSON File

with open(JsonInputFileName) as user_file:
    file_contents = user_file.read().encode().decode('utf-8-sig')
  
#print(file_contents)
    dataJSON = json.loads(file_contents)
    #dataJSON = json.loads(user_file.read().decode(user_file.info().get_param('charset') or 'utf-8'))
#dataJSON = json.loads(r.read().decode(r.info().get_param('charset') or 'utf-8'))

with open(dataOutput, mode='w') as csv_file:
    csvWriter = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    csvWriter.writerow(["package",targetSpecName])
    for k in dataJSON['packages']:
        try:
            targetDependency = dataJSON['packages'][k]['dependencies'][targetSpecName]
            print(k + "," + targetDependency)
            csvWriter.writerow([k,targetDependency])
        except:
            #print ("oops")
            exit
        #print("Value: " + str(v))