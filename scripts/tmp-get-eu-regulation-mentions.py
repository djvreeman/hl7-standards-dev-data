import requests
import pandas as pd
import os
import json
import time
import re
from datetime import datetime

# Default path for config.json
CONFIG_PATH = "data/config/config.json"

# Load EUR-Lex API Credentials
with open(CONFIG_PATH, "r") as f:
    config = json.load(f)

EURLEX_API_URL = "https://api.europa.eu/eurlex/v1/search"
API_KEY = config.get("api_key")  # Ensure you add your API key to config.json

def fetch_eurlex_results(keyword, start_date, end_date):
    """
    Searches the EUR-Lex API for regulations containing the specified keyword within the date range.

    Args:
        keyword (str): Search keyword.
        start_date (str): Start date (YYYY-MM-DD).
        end_date (str): End date (YYYY-MM-DD).

    Returns:
        list: A list of document results from EUR-Lex.
    """
    all_results = []

    # Build CQL query for full-text search
    cql_query = f'dc_title="{keyword}" OR dc_description="{keyword}"'

    params = {
        "q": cql_query,
        "date_from": start_date,
        "date_to": end_date,
        "format": "json",
        "limit": 100  # Maximum number of results per request
    }

    headers = {
        "Accept": "application/json",
        "X-API-Key": API_KEY
    }

    response = requests.get(EURLEX_API_URL, params=params, headers=headers)

    if response.status_code == 200:
        data = response.json()
        results = data.get("results", [])

        for item in results:
            all_results.append({
                "Document Number": item.get("celex", "N/A"),
                "Title": item.get("title", "N/A"),
                "Publication Date": item.get("publication_date", "N/A"),
                "URL": item.get("url", "N/A")
            })
    else:
        print(f"❌ Error fetching results for '{keyword}': {response.status_code}")

    return all_results


def extract_eurlex_data(results, keyword, existing_entries):
    """
    Extracts relevant metadata from EUR-Lex results and ensures multiple keyword matches.

    Args:
        results (list): List of document results from EUR-Lex.
        keyword (str): The search keyword used.
        existing_entries (dict): Dictionary of existing entries to track multiple keyword matches.

    Returns:
        dict: Updated list of relevant document entries.
    """
    for item in results:
        doc_url = item["URL"]
        doc_id = item["Document Number"]
        title = item["Title"]
        pub_date = item["Publication Date"]

        entry_key = doc_url  # Use the document URL as a unique identifier

        if entry_key in existing_entries:
            existing_entries[entry_key]["Keyword Matched"].append(keyword)
        else:
            existing_entries[entry_key] = {
                "Document Number": doc_id,
                "Title": title,
                "Publication Date": pub_date,
                "Month": datetime.strptime(pub_date, "%Y-%m-%d").strftime("%Y-%m") if pub_date else "N/A",
                "URL": doc_url,
                "Keyword Matched": [keyword],
            }

    return existing_entries


def convert_to_ris(df, output_ris_folder, combined_ris_file):
    """
    Converts a DataFrame of EUR-Lex citations into RIS format.

    Args:
        df (pd.DataFrame): The citation data.
        output_ris_folder (str): Folder to save individual RIS files.
        combined_ris_file (str): Path to save the combined RIS file.
    """
    os.makedirs(output_ris_folder, exist_ok=True)

    with open(combined_ris_file, "w", encoding="utf-8") as combined_file:
        saved_ris_count = 0

        for _, row in df.iterrows():
            cleaned_keywords = [kw.strip('"') for kw in row['Keyword Matched']]
            keyword_entries = "\n".join([f"KW  - {kw}" for kw in cleaned_keywords])

            ris_entry = f"""TY  - GOVDOC
TI  - {row['Title']}
PY  - {row['Publication Date'][:4]}
DA  - {row['Publication Date']}
UR  - {row['URL']}
DB  - EUR-Lex
{keyword_entries}
ER  -

"""
            document_id = row.get("Document Number", "unknown_id")
            filepath = os.path.join(output_ris_folder, f"{document_id}.ris")

            try:
                with open(filepath, "w", encoding="utf-8") as f:
                    f.write(ris_entry)
                saved_ris_count += 1
                combined_file.write(ris_entry)
            except Exception as e:
                print(f"❌ Failed to save {filepath}: {e}")

    print(f"\n✅ Combined RIS file saved: {combined_ris_file}")
    print(f"📄 Successfully saved RIS files: {saved_ris_count}")


def save_results_to_csv(df, output_folder):
    """
    Saves search results to a CSV file.

    Args:
        df (pd.DataFrame): Data to save.
        output_folder (str): Folder where the CSV file should be saved.
    """
    os.makedirs(output_folder, exist_ok=True)
    filename = f"{output_folder}/eur_lex_citations.csv"
    df.to_csv(filename, index=False)
    print(f"✅ Data saved to {filename}")


def main():
    """
    Main function to handle command-line arguments and execute the script.
    """
    import argparse
    parser = argparse.ArgumentParser(description="""
    Search the EUR-Lex database for EU regulations mentioning specific keywords.
    
    Example usage:
        python fetch_eur_lex.py "FHIR" "HL7" "Health Level Seven" --start_date 2022-01-01 --end_date 2023-12-31 --output_folder ./eu_policy_tracking
    """, formatter_class=argparse.RawTextHelpFormatter)

    parser.add_argument("keywords", type=str, nargs="+", help="Keyword(s) to search for")
    parser.add_argument("--start_date", type=str, default="2023-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end_date", type=str, default=datetime.today().strftime("%Y-%m-%d"), help="End date (YYYY-MM-DD)")
    parser.add_argument("--output_folder", type=str, default="./eur_lex_results", help="Output folder")

    args = parser.parse_args()

    existing_entries = {}

    for keyword in args.keywords:
        print(f"\n🔍 Searching for '{keyword}' in EUR-Lex from {args.start_date} to {args.end_date}...\n")
        results = fetch_eurlex_results(keyword, args.start_date, args.end_date)

        if results:
            existing_entries = extract_eurlex_data(results, keyword, existing_entries)
        else:
            print(f"❌ No results found for '{keyword}'.")

    if existing_entries:
        combined_df = pd.DataFrame.from_dict(existing_entries, orient="index")
        save_results_to_csv(combined_df, args.output_folder)

        ris_folder = os.path.join(args.output_folder, "RIS_Files")
        combined_ris_file = os.path.join(args.output_folder, "eur_lex_combined.ris")
        convert_to_ris(combined_df, ris_folder, combined_ris_file)

        print(f"\n📊 Total unique EUR-Lex citations found: {len(combined_df)}\n")


if __name__ == "__main__":
    main()