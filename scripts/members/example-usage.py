"""
Example usage of the Trademark Member Matcher with actual data

This script shows how to use the matcher with your trademark applications spreadsheet.
You'll need to set up your Salesforce credentials first.
"""

import os
import sys
import pandas as pd

def main():
    print("Trademark Member Matcher - Example Usage")
    print("=" * 50)
    
    # Path to your trademark applications file
    input_file = "../../data/working/members/2025 07 18 - FHIR Trademark Applications Record.xlsx"
    output_file = "trademark-matching-results.xlsx"
    
    # Check if input file exists
    if not os.path.exists(input_file):
        print(f"Error: Input file not found: {input_file}")
        print("Please update the input_file path in this script.")
        return
    
    print(f"Input file: {input_file}")
    print(f"Output file: {output_file}")
    
    # Check if default config file exists
    default_config_file = "../../data/config/sf-config.yaml"
    if os.path.exists(default_config_file):
        config_file = default_config_file
        print(f"Using default config file: {config_file}")
    else:
        # Fallback to local config
        config_file = "config.yaml"
        if not os.path.exists(config_file):
            print(f"\nError: No configuration file found.")
            print(f"Default config not found: {default_config_file}")
            print(f"Local config not found: {config_file}")
            print("Please either:")
            print("1. Use the existing sf-config.yaml file, or")
            print("2. Copy config-template.yaml to config.yaml and fill in credentials")
            return
        print(f"Using local config file: {config_file}")
    
    print(f"Config file: {config_file}")
    
    # Show the available sheets
    try:
        xl = pd.ExcelFile(input_file)
        print(f"\nAvailable sheets: {xl.sheet_names}")
        
        # Show sample data from each sheet
        for sheet_name in xl.sheet_names:
            df = pd.read_excel(xl, sheet_name)
            print(f"\n{sheet_name}:")
            print(f"  Rows: {len(df)}")
            print(f"  Columns: {list(df.columns)}")
            
            # Show sample organizations
            if 'Organization' in df.columns:
                orgs = df['Organization'].dropna().head(3).tolist()
                print(f"  Sample organizations: {orgs}")
            
            # Show status distribution
            if 'Status' in df.columns:
                status_counts = df['Status'].value_counts()
                print(f"  Status distribution: {dict(status_counts)}")
    
    except Exception as e:
        print(f"Error reading Excel file: {e}")
        return
    
    print(f"\n{'=' * 50}")
    print("To run the matcher, use one of these commands:")
    print(f"{'=' * 50}")
    
    print("\n1. Process both sheets with human review (using default config):")
    print(f"   python trademark-member-matcher.py -i {input_file} -o {output_file}")
    
    print("\n2. Process both sheets with human review (specify config):")
    print(f"   python trademark-member-matcher.py -c {config_file} -i {input_file} -o {output_file}")
    
    print("\n3. Process only Community License Applications:")
    print(f"   python trademark-member-matcher.py -i {input_file} -o {output_file} -s 'Community License Applications'")
    
    print("\n4. Process only Product License Applications:")
    print(f"   python trademark-member-matcher.py -i {input_file} -o {output_file} -s 'Product License Applications'")
    
    print("\n5. Auto-match high confidence matches (90%+):")
    print(f"   python trademark-member-matcher.py -i {input_file} -o {output_file} --auto-match")
    
    print("\n6. Adjust fuzzy matching threshold:")
    print(f"   python trademark-member-matcher.py -i {input_file} -o {output_file} --fuzzy-threshold 80")
    
    print("\n7. Filter by different status:")
    print(f"   python trademark-member-matcher.py -i {input_file} -o {output_file} --status-filter 'pending'")
    
    print(f"\n{'=' * 50}")
    print("Tips:")
    print(f"{'=' * 50}")
    print("- Start with one sheet to test the process")
    print("- Use --auto-match for high-confidence matches to speed up processing")
    print("- Adjust --fuzzy-threshold if you're getting too many or too few matches")
    print("- The output file will contain the original data plus new columns:")
    print("  * Member_Y_N: Whether the organization is a member (Y/N)")
    print("  * SF_Member_ID: Salesforce Account ID if matched")
    print("  * Confidence_Score: Fuzzy matching confidence score (0-100)")
    print("  * Review_Status: How the match was determined")
    print("  * Matched_Organization: The matched organization name from Salesforce")


if __name__ == '__main__':
    main() 