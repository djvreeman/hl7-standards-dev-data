#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# This script is designed to read in an export of a JIRA query of resolved issues per product family as a CSV file
# and export total counts of resolved issues by day.

# Usage:
# python3 parse-jiracommenters-unique-csv.py -i IssueSubmitters/in.csv -o IssueSubmitters/20220912-commenters-totals.csv

import csv
import sys
import pprint
import json
import argparse
import getopt
from datetime import datetime
from collections import defaultdict
import re
def natural_key(string_):
    """See https://blog.codinghorror.com/sorting-for-humans-natural-sort-order/"""
    return [int(s) if s.isdigit() else s for s in re.split(r'(\d+)', string_)]

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
    csvWriter = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    reporterTotals = defaultdict(int)
    for issue in data:
        try: 
            reporter = issue.get("Reporter")
            reporterTotals[reporter] += 1

        except:
            #issueDate = issue["date"]
            exit
    #print(str(dict(reporterTotals)))
    
    # Re-sort the dictionary by alpha
    res = {key: val for key, val in sorted(reporterTotals.items(), key = lambda ele: ele[0])}
    for k,v in res.items():
        #print (k) 
        # print (resolvedTotals[k])
        csvWriter.writerow([k,reporterTotals[k]])
    