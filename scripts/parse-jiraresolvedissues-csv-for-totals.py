#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# This script is designed to read in an export of a JIRA query of resolved issues per product family as a CSV file
# and export total counts of resolved issues by day.

# Usage:
# python3 parse-jiraresolvedissues-csv-for-totals.py -i Resolved\ Issues/2022\ 09\ 12/fhir-export-dvreeman-2022_09_13-00_07-e96a55f33b9b4fe68d04fb35172255db.csv -o Resolved\ Issues/2022\ 09\ 12/fhir-parsed.csv
import csv
import sys
import pprint
import json
import argparse
import getopt
from datetime import datetime
from collections import defaultdict

# Function to convert a csv file to a list of dictionaries.  Takes in one variable called variables_file
def csvDictList(variables_file):
     
    # Open variable-based csv, iterate over the rows and map values to a list of dictionaries containing key/value pairs
    reader = csv.DictReader(open(variables_file, 'rt'))
    dict_list = []
    for line in reader:
        dict_list.append(line)
    return dict_list

#Get Command Line Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-i", help="file name of input CSV file", required=True)
parser.add_argument("-o", help="file name of output CSV file", required=True)

args = parser.parse_args()

# Setup file names 
csvInputFileName = args.i
csvOutputFileName = args.o

# Calls the csv_dict_list function, passing the named csv
data = csvDictList(csvInputFileName)

# Prints the results nice and pretty like
# pprint.pprint(data)
     
with open(csvOutputFileName, mode='w') as csv_file:
    cols =["resolved","count"]
    csvWriter = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    resolvedTotals = defaultdict(int)
    for issue in data:
        try: 
            #pprint.pprint(data)
            #issueDate = issue["date"]
            fullResolved = issue.get("Resolved")
            simpleResolved = datetime.strptime(fullResolved, "%Y-%m-%d %H:%M")
            simpleDate = simpleResolved.date()
            resolvedDay = simpleDate.strftime('%Y %m %d')
            # print (resolvedDay)
            resolvedTotals[resolvedDay] += 1
            #datetimeobj=datetime.strptime(issueDate, "%Y-%m-%dT%H:%M:%S")
            #simpleDate = datetimeobj.date()
            #simpleDateMonth = simpleDate.strftime('%Y %m')
            #print (simpleissueName)

            #csvWriter.writerow([simpleDateMonth,issueDate,simpleDate,issueName,simpleissueName,family])
        except:
            #issueDate = issue["date"]
            #issueName = issue["title"]["rendered"]
            #csvWriter.writerow([issueDate,issueName])
            exit
    #print(str(dict(resolvedTotals)))
    for k,v in resolvedTotals.items():
        #print (k) 
        # print (resolvedTotals[k])
        csvWriter.writerow([k,resolvedTotals[k]])
    