"""
Test script for the Trademark Member Matcher

This script demonstrates the functionality without requiring Salesforce credentials.
It uses mock data to show how the matching process works.
"""

import pandas as pd
from fuzzywuzzy import fuzz, process
import sys
import os

# Import functions directly from the main script
import importlib.util
spec = importlib.util.spec_from_file_location("trademark_member_matcher", "trademark-member-matcher.py")
trademark_matcher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(trademark_matcher)

# Get the functions we need
normalize_organization_name = trademark_matcher.normalize_organization_name
find_matches = trademark_matcher.find_matches
display_matches = trademark_matcher.display_matches


def create_mock_accounts():
    """Create mock Salesforce account data for testing."""
    return [
        {
            'Id': '001A0000001',
            'Name': 'Epic Systems Corporation',
            'BillingCity': 'Verona',
            'BillingState': 'WI',
            'Website': 'https://www.epic.com'
        },
        {
            'Id': '001A0000002',
            'Name': 'Cerner Corporation',
            'BillingCity': 'Kansas City',
            'BillingState': 'MO',
            'Website': 'https://www.cerner.com'
        },
        {
            'Id': '001A0000003',
            'Name': 'Allscripts Healthcare Solutions',
            'BillingCity': 'Chicago',
            'BillingState': 'IL',
            'Website': 'https://www.allscripts.com'
        },
        {
            'Id': '001A0000004',
            'Name': 'Athenahealth Inc',
            'BillingCity': 'Watertown',
            'BillingState': 'MA',
            'Website': 'https://www.athenahealth.com'
        },
        {
            'Id': '001A0000005',
            'Name': 'GE Healthcare',
            'BillingCity': 'Chicago',
            'BillingState': 'IL',
            'Website': 'https://www.gehealthcare.com'
        },
        {
            'Id': '001A0000006',
            'Name': 'Siemens Healthineers',
            'BillingCity': 'Erlangen',
            'BillingState': 'Bavaria',
            'Website': 'https://www.siemens-healthineers.com'
        },
        {
            'Id': '001A0000007',
            'Name': 'Philips Healthcare',
            'BillingCity': 'Amsterdam',
            'BillingState': 'North Holland',
            'Website': 'https://www.philips.com/healthcare'
        },
        {
            'Id': '001A0000008',
            'Name': 'Oracle Corporation',
            'BillingCity': 'Austin',
            'BillingState': 'TX',
            'Website': 'https://www.oracle.com'
        },
        {
            'Id': '001A0000009',
            'Name': 'Microsoft Corporation',
            'BillingCity': 'Redmond',
            'BillingState': 'WA',
            'Website': 'https://www.microsoft.com'
        },
        {
            'Id': '001A0000010',
            'Name': 'IBM Corporation',
            'BillingCity': 'Armonk',
            'BillingState': 'NY',
            'Website': 'https://www.ibm.com'
        }
    ]


def create_mock_applications():
    """Create mock trademark application data for testing."""
    return pd.DataFrame([
        {
            'Organization': 'Epic Systems Corp',
            'Contact Email': 'contact@epic.com',
            'Status': 'approved',
            'Description': 'FHIR integration platform'
        },
        {
            'Organization': 'Cerner Corp',
            'Contact Email': 'info@cerner.com',
            'Status': 'approved',
            'Description': 'Healthcare IT solutions'
        },
        {
            'Organization': 'Allscripts Healthcare',
            'Contact Email': 'support@allscripts.com',
            'Status': 'approved',
            'Description': 'Electronic health records'
        },
        {
            'Organization': 'Athenahealth',
            'Contact Email': 'help@athenahealth.com',
            'Status': 'approved',
            'Description': 'Cloud-based healthcare services'
        },
        {
            'Organization': 'GE Healthcare Systems',
            'Contact Email': 'contact@gehealthcare.com',
            'Status': 'approved',
            'Description': 'Medical imaging equipment'
        },
        {
            'Organization': 'Siemens Medical Solutions',
            'Contact Email': 'info@siemens-healthineers.com',
            'Status': 'approved',
            'Description': 'Diagnostic imaging systems'
        },
        {
            'Organization': 'Philips Medical Systems',
            'Contact Email': 'support@philips.com',
            'Status': 'approved',
            'Description': 'Patient monitoring systems'
        },
        {
            'Organization': 'Oracle Health',
            'Contact Email': 'health@oracle.com',
            'Status': 'approved',
            'Description': 'Healthcare data management'
        },
        {
            'Organization': 'Microsoft Healthcare',
            'Contact Email': 'healthcare@microsoft.com',
            'Status': 'approved',
            'Description': 'Cloud healthcare platform'
        },
        {
            'Organization': 'IBM Watson Health',
            'Contact Email': 'watson@ibm.com',
            'Status': 'approved',
            'Description': 'AI-powered healthcare analytics'
        },
        {
            'Organization': 'Random Non-Member Corp',
            'Contact Email': 'info@random.com',
            'Status': 'approved',
            'Description': 'Some random application'
        }
    ])


def test_normalization():
    """Test the organization name normalization function."""
    print("Testing organization name normalization:")
    test_names = [
        'Epic Systems Corporation',
        'Epic Systems Corp',
        'Epic Systems Inc',
        'The Epic Systems Company',
        'Epic Systems LLC',
        'Epic Systems & Co'
    ]
    
    for name in test_names:
        normalized = normalize_organization_name(name)
        print(f"  '{name}' -> '{normalized}'")
    print()


def test_fuzzy_matching():
    """Test the fuzzy matching functionality."""
    print("Testing fuzzy matching:")
    accounts = create_mock_accounts()
    
    test_orgs = [
        'Epic Systems Corp',
        'Cerner Corp',
        'Allscripts Healthcare',
        'Random Non-Member Corp'
    ]
    
    for org in test_orgs:
        print(f"\nMatching: '{org}'")
        matches = find_matches(org, accounts, threshold=70)
        
        if matches:
            for i, match in enumerate(matches[:3], 1):
                print(f"  {i}. {match['name']} (Score: {match['score']}%)")
        else:
            print("  No matches found")
    print()


def test_full_workflow():
    """Test the full workflow with mock data."""
    print("Testing full workflow with mock data:")
    print("=" * 60)
    
    # Load mock data
    accounts = create_mock_accounts()
    applications = create_mock_applications()
    
    # Filter to approved applications
    approved_apps = applications[applications['Status'].str.lower() == 'approved']
    print(f"Processing {len(approved_apps)} approved applications")
    
    results = []
    
    for index, row in approved_apps.iterrows():
        org_name = row['Organization']
        contact_email = row['Contact Email']
        
        print(f"\nProcessing: {org_name}")
        
        # Find matches
        matches = find_matches(org_name, accounts, threshold=70)
        
        # Simulate human review (auto-select first match if score > 85)
        selected_match = None
        if matches and matches[0]['score'] > 85:
            selected_match = matches[0]
            print(f"  Auto-matched: {selected_match['name']} (Score: {selected_match['score']}%)")
        elif matches:
            print(f"  Manual review needed. Top match: {matches[0]['name']} (Score: {matches[0]['score']}%)")
            # In real usage, this would call display_matches()
        else:
            print("  No matches found")
        
        # Record result
        member_status = 'Y' if selected_match else 'N'
        sf_member_id = selected_match['id'] if selected_match else ''
        confidence_score = selected_match['score'] if selected_match else 0
        
        results.append({
            'organization': org_name,
            'contact_email': contact_email,
            'member_status': member_status,
            'sf_member_id': sf_member_id,
            'confidence_score': confidence_score,
            'matched_organization': selected_match['name'] if selected_match else ''
        })
    
    # Display summary
    print(f"\n{'=' * 60}")
    print("SUMMARY:")
    print(f"{'=' * 60}")
    
    members = [r for r in results if r['member_status'] == 'Y']
    non_members = [r for r in results if r['member_status'] == 'N']
    
    print(f"Total applications processed: {len(results)}")
    print(f"Identified as members: {len(members)}")
    print(f"Not members: {len(non_members)}")
    
    print(f"\nMembers found:")
    for member in members:
        print(f"  - {member['organization']} -> {member['matched_organization']} (Score: {member['confidence_score']}%)")
    
    print(f"\nNon-members:")
    for non_member in non_members:
        print(f"  - {non_member['organization']}")


def main():
    """Run all tests."""
    print("Trademark Member Matcher - Test Suite")
    print("=" * 50)
    
    test_normalization()
    test_fuzzy_matching()
    test_full_workflow()
    
    print(f"\n{'=' * 50}")
    print("Test completed successfully!")
    print("\nTo use with real data:")
    print("1. Copy config-template.yaml to config.yaml")
    print("2. Fill in your Salesforce credentials")
    print("3. Run: python trademark-member-matcher.py -c config.yaml -i your-file.xlsx -o results.xlsx")


if __name__ == '__main__':
    main() 