import requests
import pandas as pd
import os
import time
import re
from datetime import datetime

def fetch_all_pages(keyword, start_date, end_date):
    """
    Fetches ALL pages of results for a keyword from the Federal Register API.

    Args:
        keyword (str): Search keyword or phrase.
        start_date (str): Start date for searching.
        end_date (str): End date for searching (defaults to today if not provided).

    Returns:
        list: Combined list of document results from all pages.
    """
    all_results = []
    page = 1

    # Wrap in double quotes for exact match
    query = f'"{keyword}"' if " " in keyword else keyword

    while True:
        url = (f"https://www.federalregister.gov/api/v1/documents.json?"
               f"conditions[term]={query}&conditions[publication_date][gte]={start_date}"
               f"&conditions[publication_date][lte]={end_date}&page={page}")

        response = requests.get(url, timeout=10)

        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            if not results:
                break  # No more pages

            all_results.extend(results)
            page += 1
            time.sleep(1)  # Prevent hitting rate limits

        else:
            print(f"❌ Error fetching page {page}: {response.status_code}")
            break

    return all_results

def extract_relevant_data(results, keyword, existing_entries):
    """
    Extracts relevant metadata and ensures multiple keyword matches are captured.

    Args:
        results (list): List of document results from the Federal Register API.
        keyword (str): The search keyword used.
        existing_entries (dict): Dictionary of existing entries to track multiple keyword matches.

    Returns:
        list: Updated list of relevant document entries.
    """
    for item in results:
        doc_url = item.get("html_url", "N/A")
        doc_id = item.get("document_number", "unknown_id")  # Get document number
        agencies = item.get("agencies", [])
        agency_names = ", ".join([a.get("name", "Unnamed Agency") for a in agencies if isinstance(a, dict)]) if agencies else "N/A"
        
        entry_key = doc_url  # Use the document URL as a unique identifier

        if entry_key in existing_entries:
            existing_entries[entry_key]["Keyword Matched"].append(keyword)
        else:
            existing_entries[entry_key] = {
                "Document Number": doc_id,
                "Title": item.get("title", "N/A"),
                "Publication Date": item.get("publication_date", "N/A"),
                "Month": datetime.strptime(item.get("publication_date", "N/A"), "%Y-%m-%d").strftime("%Y-%m") if item.get("publication_date") else "N/A",
                "Agencies": agency_names,
                "Document Type": item.get("type", "N/A"),
                "URL": doc_url,
                "Keyword Matched": [keyword],
            }

    return existing_entries

def convert_to_ris(df, output_ris_folder, combined_ris_file):
    """
    Converts a DataFrame of Federal Register citations into RIS format, using `document_number` for filenames.

    Args:
        df (pd.DataFrame): The citation data.
        output_ris_folder (str): Folder to save individual RIS files.
        combined_ris_file (str): Path to save the combined RIS file.
    """
    os.makedirs(output_ris_folder, exist_ok=True)

    failed_entries = []
    total_ris_attempts = len(df)

    with open(combined_ris_file, "w", encoding="utf-8") as combined_file:
        saved_ris_count = 0

        for _, row in df.iterrows():
            cleaned_keywords = [kw.strip('"') for kw in row['Keyword Matched']]
            cleaned_keywords.append("United States")  # Add "United States" to keywords
            keyword_entries = "\n".join([f"KW  - {kw}" for kw in cleaned_keywords])

            ris_entry = f"""TY  - GOVDOC
TI  - {row['Title']}
AU  - {row['Agencies']}
PY  - {row['Publication Date'][:4]}
DA  - {row['Publication Date']}
UR  - {row['URL']}
DB  - Federal Register
{keyword_entries}
ER  -

"""
            # Use `document_number` as the filename
            document_id = row.get("Document Number", "unknown_id")
            filepath = os.path.join(output_ris_folder, f"{document_id}.ris")

            try:
                # Save individual RIS entry
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(ris_entry)
                saved_ris_count += 1

                # Append to combined RIS file
                combined_file.write(ris_entry)
            except Exception as e:
                failed_entries.append((filepath, str(e)))

    print(f"\n✅ Combined RIS file saved: {combined_ris_file}")
    print(f"📊 Total citations in CSV: {total_ris_attempts}")
    print(f"📄 Successfully saved RIS files: {saved_ris_count}")

    if failed_entries:
        print("\n⚠️ The following RIS files failed to save:")
        for entry in failed_entries:
            print(f"❌ {entry[0]} - Error: {entry[1]}")

def save_results_to_csv(df, output_folder):
    """
    Saves search results to a CSV file in the specified output folder.

    Args:
        df (pd.DataFrame): Data to save.
        output_folder (str): Folder where the CSV file should be saved.
    """
    os.makedirs(output_folder, exist_ok=True)

    filename = f"{output_folder}/federal_register_citations.csv"
    df.to_csv(filename, index=False)
    print(f"✅ Data saved to {filename}")

def main():
    """
    Main function to handle command-line arguments and execute the script.
    """
    import argparse
    parser = argparse.ArgumentParser(description="""
    Search the U.S. Federal Register for policy documents mentioning HL7-related terms.
    
    Example usage:
        python fetch_federal_register.py "FHIR" "HL7" "Health Level Seven" --start_date 2022-01-01 --end_date 2023-12-31 --output_folder ./policy_tracking
    """, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("keywords", type=str, nargs="+", help="Keyword(s) to search for (e.g., 'FHIR', 'HL7', 'Health Level Seven')")
    parser.add_argument("--start_date", type=str, default="2023-01-01", help="Start date for searching (format: YYYY-MM-DD, default: 2023-01-01)")
    parser.add_argument("--end_date", type=str, default=datetime.today().strftime("%Y-%m-%d"), help="End date for searching (default: today's date)")
    parser.add_argument("--output_folder", type=str, default="./federal_register_results", help="Folder to save CSV and RIS files (default: ./federal_register_results)")

    args = parser.parse_args()
    
    existing_entries = {}  # Track all citations across keywords

    for keyword in args.keywords:
        print(f"\n🔍 Searching for '{keyword}' in the Federal Register from {args.start_date} to {args.end_date}...\n")
        results = fetch_all_pages(keyword, args.start_date, args.end_date)

        if results:
            existing_entries = extract_relevant_data(results, keyword, existing_entries)
        else:
            print(f"❌ No results found for '{keyword}'.")

    if existing_entries:
        combined_df = pd.DataFrame.from_dict(existing_entries, orient="index")
        save_results_to_csv(combined_df, args.output_folder)

        # Generate RIS files
        ris_folder = os.path.join(args.output_folder, "RIS_Files")
        combined_ris_file = os.path.join(args.output_folder, "federal_register_combined.ris")
        convert_to_ris(combined_df, ris_folder, combined_ris_file)

        print(f"\n📊 Total unique Federal Register citations found across all keywords: {len(combined_df)}\n")

if __name__ == "__main__":
    main()