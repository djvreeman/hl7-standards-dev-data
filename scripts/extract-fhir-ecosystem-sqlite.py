import sqlite3
import csv
import requests
import argparse
import os
import certifi

def download_database(url, local_db_path):
    response = requests.get(url, verify=certifi.where())
    with open(local_db_path, 'wb') as file:
        file.write(response.content)

def export_sqlite_tables_to_csv(db_path, output_folder):
    # Connect to the SQLite database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Fetch the list of tables in the database
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()

    for table_name in tables:
        table_name = table_name[0]
        print(f"Exporting table {table_name}")

        # Query the table
        cursor.execute(f"SELECT * FROM {table_name}")
        data = cursor.fetchall()
        columns = [column[0] for column in cursor.description]

        # Write data to CSV
        csv_file_path = os.path.join(output_folder, f"{table_name}.csv")
        with open(csv_file_path, "w", newline="") as csv_file:
            csv_writer = csv.writer(csv_file)
            csv_writer.writerow(columns)  # Write header
            csv_writer.writerows(data)  # Write data

    # Close the connection
    conn.close()
    print("Export completed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download SQLite database from URL and export tables to CSV.")
    parser.add_argument("-i", "--input_url", required=True, help="URL of the SQLite database")
    parser.add_argument("-o", "--output_path", required=True, help="Local path to save the downloaded database")
    parser.add_argument("-f", "--folder_path", required=True, help="Folder path to store the exported CSV files")

    args = parser.parse_args()

    # Download the database
    download_database(args.input_url, args.output_path)

    # Create the output folder if it doesn't exist
    if not os.path.exists(args.folder_path):
        os.makedirs(args.folder_path)

    # Export tables to CSV
    export_sqlite_tables_to_csv(args.output_path, args.folder_path)
