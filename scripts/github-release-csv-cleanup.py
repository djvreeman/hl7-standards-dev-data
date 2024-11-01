#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# This script processes a CSV file containing software release data.
# It reads the input CSV file, processes the 'published_at' field to extract the publication date,
# and writes the modified data into a new output CSV file.
#
# The input CSV file must have the following columns:
# - Column 1: Software name
# - Column 2: Published timestamp in ISO 8601 format (e.g., "2023-08-01T12:34:56Z")
# - Column 3 and 4: Additional fields (optional)
#
# If the output file is not specified, the script will automatically generate an output file
# by appending '-parsed' to the input filename before the extension.
#
# Usage:
# python3 github-release-csv-cleanup.py -i input-file.csv [-o output-file.csv]

import csv
import sys
import pprint
import json
import argparse
import getopt
from datetime import datetime
from collections import defaultdict

# Get Command Line Arguments
parser = argparse.ArgumentParser()
parser.add_argument("-i", help="file name of input CSV file", required=True)
parser.add_argument("-o", help="file name of output CSV file", required=False)

args = parser.parse_args()

# Setup file names
csvInputFileName = args.i

# If no output file is specified, append '-parsed' before the file extension of the input file
if args.o:
    csvOutputFileName = args.o
else:
    input_name_parts = csvInputFileName.rsplit('.', 1)
    csvOutputFileName = f"{input_name_parts[0]}-parsed.{input_name_parts[1]}"

with open(csvOutputFileName, mode='w') as csv_file:
    csvWriter = csv.writer(csv_file, quoting=csv.QUOTE_ALL)
    with open(csvInputFileName, mode='r') as dataCSV:
        reader = csv.reader(dataCSV)

        for row in reader:
            publishedAt = datetime.strptime(row[1], '%Y-%m-%dT%H:%M:%SZ')
            simpleDate = publishedAt.date()
            publishedDay = simpleDate.strftime('%Y %m %d')
            try:
                csvWriter.writerow([row[0], row[1], publishedDay, row[2], row[3]])
            except:
                exit