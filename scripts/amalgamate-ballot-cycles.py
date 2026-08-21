import os
import csv
import glob
import sys
import re

def get_csv_files(root_dir):
    # Recursively find all .csv files, excluding -postponed.csv, -summary.csv, and those with 'amalgamated' in the name
    pattern = os.path.join(root_dir, '**', '*.csv')
    all_files = glob.glob(pattern, recursive=True)
    filtered = [f for f in all_files if not (
        f.endswith('-postponed.csv') or 
        f.endswith('-summary.csv') or 
        'amalgamated' in os.path.basename(f).lower()
    )]
    return filtered

def clean_name_field(name):
    # Remove leading/trailing whitespace, replace linefeeds/tabs with space, collapse multiple spaces
    name = name.strip()
    name = re.sub(r'[\r\n\t]+', ' ', name)
    name = re.sub(r' +', ' ', name)
    return name

def amalgamate_csvs(csv_files, output_file):
    all_rows = []
    header = None
    for file in csv_files:
        with open(file, newline='', encoding='utf-8') as f:
            reader = csv.reader(f)
            file_header = next(reader)
            # Add SourceFile column if not already present
            if header is None:
                header = file_header + ['SourceFile']
                all_rows.append(header)
            name_idx = file_header.index('Name') if 'Name' in file_header else None
            for row in reader:
                # Pad row if it has fewer columns than header (for malformed files)
                row = row + [''] * (len(header) - 1 - len(row))
                # Clean Name field if present
                if name_idx is not None and len(row) > name_idx:
                    row[name_idx] = clean_name_field(row[name_idx])
                all_rows.append(row + [os.path.basename(file)])
    # Write amalgamated file
    with open(output_file, 'w', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        writer.writerows(all_rows)

def main():
    default_dir = 'data/working/ballot-cycles/'
    input_dir = input(f"Enter directory to search for ballot cycle CSVs [{default_dir}]: ").strip() or default_dir
    if not os.path.isdir(input_dir):
        print(f"Directory '{input_dir}' does not exist.")
        sys.exit(1)
    csv_files = get_csv_files(input_dir)
    if not csv_files:
        print("No matching CSV files found.")
        sys.exit(1)
    output_file = os.path.join(input_dir, 'all-ballot-cycles-amalgamated.csv')
    amalgamate_csvs(csv_files, output_file)
    print(f"Amalgamated CSV written to {output_file}")

if __name__ == '__main__':
    main() 