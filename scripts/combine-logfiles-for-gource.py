import csv
from dateutil.parser import parse as parse_timestamp
from datetime import datetime
import pytz
import argparse
from pathlib import Path

def normalize_to_utc(dt):
    """Ensure all datetime objects are offset-aware and converted to UTC."""
    if dt.tzinfo is None:  # If naive, assume it's in local time and make it offset-aware
        local_tz = pytz.timezone('UTC')  # Replace 'UTC' with the local timezone if needed
        return local_tz.localize(dt)
    return dt.astimezone(pytz.utc)  # Convert to UTC

def process_and_combine_csv(input_files, output_file):
    combined_data = []
    invalid_rows = []
    processed_row_count = 0
    skipped_row_count = 0

    for file in input_files:
        print(f"Processing input file: {file}")
        try:
            with open(file, mode='r') as f:
                reader = csv.reader(f, delimiter='|')  # Pipe as delimiter
                header = next(reader)  # Capture the header row
                for row in reader:
                    if len(row) < len(header):
                        invalid_rows.append((row, "Incomplete row"))
                        skipped_row_count += 1
                        continue

                    try:
                        # Parse the timestamp and normalize to UTC
                        timestamp = parse_timestamp(row[0])
                        timestamp = normalize_to_utc(timestamp)
                        combined_data.append([timestamp] + row)
                        processed_row_count += 1
                    except ValueError as e:
                        invalid_rows.append((row, str(e)))
                        skipped_row_count += 1
                        continue
        except Exception as e:
            print(f"Error reading file {file}: {e}")
            continue

    if not combined_data:
        print("No valid data found in input files. Exiting.")
        return

    # Sort combined data by timestamp
    combined_data.sort(key=lambda x: x[0])

    try:
        # Write to output file
        with open(output_file, mode='w', newline='') as f:
            writer = csv.writer(f, delimiter='|')
            for row in combined_data:
                writer.writerow(row[1:])  # Write the original data (excluding parsed timestamp)
        print(f"Combined and sorted CSV written to {output_file}")
    except Exception as e:
        print(f"Error writing to output file {output_file}: {e}")

    # Summary of data processing
    print("\nSummary of Data Processing:")
    print(f"Total rows processed: {processed_row_count}")
    print(f"Total rows skipped: {skipped_row_count}")
    print("Examples of skipped rows:")
    for row, reason in invalid_rows[:5]:  # Show first 5 invalid rows
        print(f" - {row}: {reason}")

def main():
    parser = argparse.ArgumentParser(description="Combine and sort Gource log CSV files.")
    parser.add_argument(
        '-i', '--input', nargs='+', required=True, 
        help="Paths to input CSV files (space-separated list)."
    )
    parser.add_argument(
        '-o', '--output', required=True, 
        help="Path to the output CSV file."
    )
    args = parser.parse_args()

    input_files = [Path(file) for file in args.input]
    output_file = Path(args.output)

    process_and_combine_csv(input_files, output_file)

if __name__ == '__main__':
    main()