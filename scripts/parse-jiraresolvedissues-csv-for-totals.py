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

# Function to convert a csv file to a list of dictionaries. Takes in one variable called variables_file
def csvDictList(variables_file):
     
    # Open variable-based csv, iterate over the rows and map values to a list of dictionaries containing key/value pairs
    reader = csv.DictReader(open(variables_file, 'rt'))
    dict_list = []
    for line in reader:
        dict_list.append(line)
    return dict_list

# Get Command Line Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-i", help="file name of input CSV file", required=True)
parser.add_argument("-o", "--output", type=str, required=False, help="Output CSV file")
args = parser.parse_args()

# If no output file is provided, append '-parsed' before the file extension of the input file
if not args.output:
    input_file = args.i
    if '.' in input_file:
        file_base, file_extension = input_file.rsplit('.', 1)
        args.output = f"{file_base}-parsed.{file_extension}"
    else:
        args.output = f"{input_file}-parsed"

# Setup file names 
csvInputFileName = args.i
csvOutputFileName = args.output

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
            fullResolved = issue.get("Resolved")
            simpleResolved = datetime.strptime(fullResolved, "%Y-%m-%d %H:%M")
            simpleDate = simpleResolved.date()
            resolvedDay = simpleDate.strftime('%Y %m %d')
            resolvedTotals[resolvedDay] += 1
        except:
            exit
    for k,v in resolvedTotals.items():
        csvWriter.writerow([k,resolvedTotals[k]])