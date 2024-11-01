#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Overview:
#
import argparse
from bs4 import BeautifulSoup
import csv
import os

def extract_table_to_csv(input_file_path, output_file_base=None):
    # Determine the base path for output files based on the input file path if not provided
    if output_file_base is None:
        output_file_base = os.path.splitext(input_file_path)[0]
    
    # Define the output file names
    output_file_main = f'{output_file_base}.csv'
    output_file_postponed = f'{output_file_base}-postponed.csv'
    output_file_summary = f'{output_file_base}-summary.csv'

    # Load the HTML content from the file
    with open(input_file_path, 'r', encoding='utf-8') as file:
        html_content = file.read()

    # Parse the HTML content
    soup = BeautifulSoup(html_content, 'html.parser')

    # Find the table with class 'bd-documents-table'
    table = soup.find('table', {'class': 'bd-documents-table'})

    # Extract table headers and rows
    main_table_rows = []
    postponed_table_rows = []
    
    headers_extracted = False
    total_data_rows = 0
    total_totp = 0

    for row in table.find_all('tr'):
        cols = row.find_all(['td', 'th'])
        row_data = []
        is_postponed_row = False
        for i, col in enumerate(cols):
            # Check for 'colspan' attribute
            colspan = col.get('colspan')
            cell_text = col.text.strip()
            if colspan:
                # If "Postponed" is in the cell, mark the row as postponed
                if 'Postponed' in cell_text:
                    is_postponed_row = True
                    cell_text = 'Postponed'
                # Add the cell text for each spanned column
                row_data.extend([cell_text for _ in range(int(colspan))])
            else:
                row_data.append(cell_text)
            # Sum TotP. values if this is not a header or postponed row
            if headers_extracted and not is_postponed_row and i == 7:  # TotP. is at index 7 after header correction
                try:
                    total_totp += float(cell_text.replace(',', ''))  # Remove commas for proper conversion
                except ValueError:
                    pass  # If conversion fails, skip the cell

        if not headers_extracted:  # First row, extract as headers
            main_table_rows.append(row_data)
            postponed_table_rows.append(row_data)
            headers_extracted = True
        elif is_postponed_row:
            postponed_table_rows.append(row_data)
        else:
            main_table_rows.append(row_data)
            total_data_rows += 1

    # Write the main table data into a CSV file
    with open(output_file_main, mode='w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(main_table_rows)

    # Write the postponed data into a separate CSV file
    with open(output_file_postponed, mode='w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerows(postponed_table_rows)

    # Write summary statistics to a separate CSV file
    with open(output_file_summary, mode='w', newline='', encoding='utf-8') as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(['Count of Data Rows', 'Sum of TotP.'])
        writer.writerow([total_data_rows, total_totp])

    print(f'Main table has been successfully extracted to {output_file_main}')
    print(f'Postponed rows have been successfully extracted to {output_file_postponed}')
    print(f'Summary statistics have been successfully extracted to {output_file_summary}')

if __name__ == "__main__":
    # Set up argument parsing
    parser = argparse.ArgumentParser(description='Extract HTML table to CSV, separating postponed rows')
    parser.add_argument('-i', '--input', required=True, help='Input HTML file path')
    parser.add_argument('-o', '--output', help='Base output CSV file path (optional, without extension)')

    # Parse arguments
    args = parser.parse_args()

    # Run the function with the provided arguments
    extract_table_to_csv(args.input, args.output)
