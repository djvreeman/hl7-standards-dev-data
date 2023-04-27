#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Usage:
# python3 github-release-csv-cleanup.py -i SoftwareReleases/publisher-releases.csv -o SoftwareReleases/publisher-releases-cleaned.csv
import csv
import sys
import pprint
import json
import argparse
import getopt
from datetime import datetime
from collections import defaultdict

#Get Command Line Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-i", help="file name of input CSV file", required=True)
parser.add_argument("-o", help="file name of output CSV file", required=True)

args = parser.parse_args()

# Setup file names 
csvInputFileName = args.i
csvOutputFileName = args.o


with open(csvOutputFileName, mode='w') as csv_file:
    csvWriter = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    with open(csvInputFileName, mode='r') as dataCSV:
        reader = csv.reader(dataCSV)
        #print (reader)

        for row in reader:
            #print (row[0] + ' ' + row[1])
            #print (row)
            #print (publishedDay)
            publishedAt = datetime.strptime(row[1], '%Y-%m-%dT%H:%M:%SZ')
            #print (publishedAt)
            simpleDate = publishedAt.date()
            publishedDay = simpleDate.strftime('%Y %m %d')
            try:  
            #assumed input as "name,published_at"

            # Parse the timestamp string into a datetime object
                #publishedAt = datetime.strptime(row[1], '%Y-%m-%d %H:%M:%S')
                csvWriter.writerow([row[0],row[1],publishedDay,row[2],row[3]])
            except:
                #issueDate = issue["date"]
                #issueName = issue["title"]["rendered"]
                #csvWriter.writerow([issueDate,issueName])
                exit

    