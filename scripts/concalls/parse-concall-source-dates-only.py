import pandas as pd
import argparse
from datetime import datetime

def parse_date(date_str, is_start=True):
    """Parse a flexible date format into a datetime object."""
    try:
        return datetime.strptime(date_str, "%Y %m %d")
    except ValueError:
        try:
            # Handle year and month inputs
            if is_start:
                return datetime.strptime(date_str + " 01", "%Y %m %d")  # First day of the month
            else:
                # Last day of the month at 23:59:59
                return (datetime.strptime(date_str + " 01", "%Y %m %d")
                        + pd.offsets.MonthEnd(0)).to_pydatetime().replace(hour=23, minute=59, second=59)
        except ValueError:
            # Handle year-only inputs
            if is_start:
                return datetime.strptime(date_str + " 01 01", "%Y %m %d")  # First day of the year
            else:
                return datetime.strptime(date_str + " 12 31 23:59:59", "%Y %m %d %H:%M:%S")  # Last day of the year

# Set up command-line argument parsing
parser = argparse.ArgumentParser(description="Filter rows by date range.")
parser.add_argument("-i", "--input", required=True, help="Path to the input CSV file.")
parser.add_argument("-o", "--output", required=True, help="Path to save the output CSV file.")
parser.add_argument("--start", required=True, help="Start date in the format YYYY MM DD, YYYY MM, or YYYY.")
parser.add_argument("--stop", required=True, help="Stop date in the format YYYY MM DD, YYYY MM, or YYYY.")
args = parser.parse_args()

# Parse the start and stop dates
start_date = parse_date(args.start, is_start=True)
stop_date = parse_date(args.stop, is_start=False)
print(f"Parsed Start Date: {start_date}")
print(f"Parsed Stop Date: {stop_date}")

# Load the input CSV file
data = pd.read_csv(args.input)

# Ensure the required column exists
if 'wg_concall_basestartdate' not in data.columns:
    raise ValueError("Input file must contain 'wg_concall_basestartdate' column.")

# Convert wg_concall_basestartdate to datetime
data['wg_concall_basestartdate_parsed'] = pd.to_datetime(
    data['wg_concall_basestartdate'], 
    format='%Y-%m-%d %H:%M:%S.%f', 
    errors='coerce'
)

# Identify and print rows with invalid dates
invalid_rows = data[data['wg_concall_basestartdate_parsed'].isna()]
if not invalid_rows.empty:
    print("Rows with invalid dates:")
    print(invalid_rows[['wg_concall_basestartdate']])

# Drop rows with invalid dates
valid_data = data.dropna(subset=['wg_concall_basestartdate_parsed'])

# Debug: Check the range of valid dates
print(f"Min date in dataset: {valid_data['wg_concall_basestartdate_parsed'].min()}")
print(f"Max date in dataset: {valid_data['wg_concall_basestartdate_parsed'].max()}")

# Debug: Print raw and parsed columns side by side
print("Preview of parsed datetime column:")
print(valid_data[['wg_concall_basestartdate', 'wg_concall_basestartdate_parsed']].head())

# Debug: Check filtering criteria
print(f"Start Date for Filtering: {start_date}")
print(f"Stop Date for Filtering: {stop_date}")

# Filter rows within the date range
filtered_data = valid_data[
    (valid_data['wg_concall_basestartdate_parsed'] >= start_date) & 
    (valid_data['wg_concall_basestartdate_parsed'] <= stop_date)
]

# Debug: Check filtered rows
print(f"Filtered rows count: {len(filtered_data)}")
if not filtered_data.empty:
    print("Preview of filtered rows (sample):")
    print(filtered_data[['wg_concall_basestartdate_parsed']].head())

# Debug: Inspect rows near the range boundaries
boundary_rows = valid_data[
    (valid_data['wg_concall_basestartdate_parsed'] >= start_date - pd.Timedelta(days=1)) & 
    (valid_data['wg_concall_basestartdate_parsed'] <= stop_date + pd.Timedelta(days=1))
]
print("Rows near the boundary:")
print(boundary_rows[['wg_concall_basestartdate_parsed']].head(10))

# Save the filtered data to the output file
filtered_data.to_csv(args.output, index=False)

print(f"Filtered data saved to {args.output}")