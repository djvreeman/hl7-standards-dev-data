"""
Federal Register Citation Fetcher
--------------------------------

This script searches the U.S. Federal Register for documents matching specific keywords
and exports the results to both CSV and RIS (citation) formats.

USAGE NOTES:
------------
1. Purpose: Search and extract policy documents from the Federal Register API that
   mention specified healthcare interoperability terms (like HL7, FHIR).

2. Requirements:
   - Python 3.6+
   - Required packages: requests, pandas, re, datetime
   - Internet connection to access the Federal Register API

3. Basic Usage:
   python fetch_federal_register.py "KEYWORD1" "KEYWORD2" --start_date YYYY-MM-DD --end_date YYYY-MM-DD

4. Examples:
   # Search for FHIR and HL7 mentions in 2023
   python fetch_federal_register.py "FHIR" "HL7" --start_date 2023-01-01 --end_date 2023-12-31
   
   # Search for exact phrase with multiple keywords
   python fetch_federal_register.py "Health Level Seven" "FHIR" --output_folder ./policy_tracking

5. Arguments:
   - keywords: One or more search terms (required)
   - --start_date: Start date for search period (default: 2023-01-01)
   - --end_date: End date for search period (default: today)
   - --output_folder: Where to save results (default: ./federal_register_results)
   - --debug: Enable detailed API response debugging

6. Output Files:
   - CSV file with all citations
   - Individual RIS citation files (named by document number)
   - Combined RIS file with all citations

7. Notes:
   - For multi-word phrases, the script automatically adds quotes for exact matching
   - Rate limiting is implemented to prevent API timeout
   - Agency information is extracted using multiple methods for better accuracy
   - United States is automatically added as a keyword to all RIS exports
"""

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
    Enhanced to provide better agency information.

    Args:
        results (list): List of document results from the Federal Register API.
        keyword (str): The search keyword used.
        existing_entries (dict): Dictionary of existing entries to track multiple keyword matches.

    Returns:
        list: Updated list of relevant document entries.
    """
    # Print debug information for the first result
    if results and len(results) > 0:
        first_result = results[0]
        print("\n📝 DEBUG: Examining API Response Structure")
        print(f"Document: {first_result.get('document_number', 'N/A')} - {first_result.get('title', 'N/A')}")
        
        # Display available fields in the response
        print("\nAvailable top-level fields in API response:")
        print(sorted(first_result.keys()))
        
        # Show detailed agency information
        agencies = first_result.get("agencies", [])
        print("\nAgency field structure:")
        print(agencies)
        
        if agencies and isinstance(agencies[0], dict):
            print(f"\nFields available in first agency object:")
            for key, value in agencies[0].items():
                print(f"  - {key}: {value}")
        
        # Look for agency information in other fields
        for field in ["abstract", "raw_text", "full_text", "body", "html_url"]:
            if field in first_result:
                print(f"\nField '{field}' exists")
                if isinstance(first_result[field], str) and len(first_result[field]) < 500:
                    print(f"Content: {first_result[field]}")
    
    for item in results:
        doc_url = item.get("html_url", "N/A")
        doc_id = item.get("document_number", "unknown_id")
        agencies = item.get("agencies", [])
        
        # 1. Improved standard agency extraction
        agency_names = []
        for a in agencies:
            if isinstance(a, dict):
                # First try to get the name field
                name = a.get("name", "")
                if name:
                    agency_names.append(name)
                # If name is missing, try raw_name (which is often present for sub-agencies)
                elif "raw_name" in a:
                    agency_names.append(a["raw_name"])
                else:
                    agency_names.append("Unnamed Agency")
        
        standard_agency_names = ", ".join(agency_names) if agency_names else "N/A"
        
        # 2. Enhanced agency extraction - collect all available agency information
        detailed_agency_info = []
        
        # Extract from agencies array
        if agencies:
            for agency in agencies:
                if isinstance(agency, dict):
                    # Get all potentially useful agency fields
                    agency_info = []
                    
                    # First check for raw_name which is often present for sub-agencies
                    raw_name = agency.get("raw_name", "")
                    if raw_name:
                        agency_info.append(raw_name)
                    
                    # Main agency name (often missing for sub-agencies)
                    name = agency.get("name", "")
                    if name and name not in str(agency_info):
                        agency_info.append(name)
                    
                    # Look for other identifying fields
                    for field in ["slug", "acronym", "short_name", "id"]:
                        if field in agency and agency[field]:
                            field_value = str(agency[field])  # Convert to string to avoid type errors
                            # Only add if it provides new information
                            if field_value not in str(agency_info):
                                agency_info.append(f"{field_value}")
                    
                    # Add any other "name" fields
                    for field in agency.keys():
                        if "name" in field and field != "name" and field != "raw_name" and agency[field]:
                            field_value = str(agency[field])  # Convert to string
                            if field_value not in str(agency_info):
                                agency_info.append(f"{field_value}")
                    
                    # Check for sub-agency fields
                    for field in ["sub_agency", "subagency", "parent_id", "parent"]:
                        if field in agency and agency[field]:
                            field_value = str(agency[field])  # Convert to string
                            if field_value not in str(agency_info):
                                agency_info.append(f"Sub: {field_value}")
                    
                    detailed_agency_info.append(" - ".join(agency_info))
        
        # 3. Try to extract AGENCY section from text fields
        extracted_agency_text = ""
        for field in ["abstract", "raw_text", "full_text", "body"]:
            if field in item and isinstance(item[field], str):
                match = re.search(r"AGENCY:\s*(.*?)(?:\n\n|\n[A-Z]+:|$)", item[field], re.DOTALL)
                if match:
                    extracted_agency_text = match.group(1).strip()
                    break
        
        if extracted_agency_text:
            detailed_agency_info.append(f"From text: {extracted_agency_text}")
        
        # Compile all agency information
        detailed_agency_str = " | ".join(detailed_agency_info) if detailed_agency_info else "No detailed info available"
        
        # Store complete agency data for debugging
        raw_agency_data = str(agencies)
        
        entry_key = doc_url
        if entry_key in existing_entries:
            existing_entries[entry_key]["Keyword Matched"].append(keyword)
        else:
            existing_entries[entry_key] = {
                "Document Number": doc_id,
                "Title": item.get("title", "N/A"),
                "Publication Date": item.get("publication_date", "N/A"),
                "Month": datetime.strptime(item.get("publication_date", "N/A"), "%Y-%m-%d").strftime("%Y-%m") if item.get("publication_date") else "N/A",
                "Agencies": standard_agency_names,  # Keep original for compatibility
                "Detailed Agency Info": detailed_agency_str,  # Add enhanced info
                "Agency Data": raw_agency_data,  # Add raw data for debugging
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

            # Use detailed agency info if available
            agency_field = row.get('Detailed Agency Info', row['Agencies'])
            if "From text:" in agency_field:
                # Extract only the portion after "From text:"
                agency_field = agency_field.split("From text:")[1].strip()

            ris_entry = f"""TY  - GOVDOC
TI  - {row['Title']}
AU  - {agency_field}
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
    parser.add_argument("--debug", action="store_true", help="Enable detailed debugging of API responses")

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