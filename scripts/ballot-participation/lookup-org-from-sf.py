#!/usr/bin/env python3
"""
Lookup Organization from Salesforce by Jira/Atlassian User ID or Email

This script queries Salesforce to find the Organization (Account) associated with
a Contact based on their Atlassian/Jira user ID or email address. It first discovers 
the custom field name used to store the Jira ID, then performs lookups.

USAGE:
    # Lookup by user ID
    python3 lookup-org-from-sf.py -c path/to/config.yaml -u bgradl
    
    # Lookup by email
    python3 lookup-org-from-sf.py -c path/to/config.yaml -e user@example.com
    
    # Lookup by both (tries user ID first, then email if no match)
    python3 lookup-org-from-sf.py -c path/to/config.yaml -u bgradl -e user@example.com

ARGUMENTS:
    -c / --config    Path to the YAML configuration file (required).
    -u / --userid    Jira/Atlassian user ID to lookup (e.g., bgradl)
    -e / --email     Email address to lookup
    --discover-fields  First discover available fields on Contact object
"""

import requests
import yaml
import argparse
import urllib.parse
import json
import re


def load_config(path):
    """Load configuration from YAML file."""
    with open(path, 'r') as f:
        return yaml.safe_load(f)


def get_access_token(config):
    """Get Salesforce access token."""
    url = f"{config['prod_server']}/services/oauth2/token"
    params = {
        'grant_type': 'password',
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'username': config['username'],
        'password': config['password']
    }
    response = requests.post(url, data=params)
    response.raise_for_status()
    return response.json()['access_token']


def describe_contact_object(config, access_token):
    """Describe the Contact object to find fields related to Jira/Atlassian."""
    url = f"{config['prod_server']}/services/data/v{config['version']}/sobjects/Contact/describe"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


def find_jira_id_field(contact_desc):
    """
    Find the custom field that stores Atlassian/Jira ID.
    Looks for fields with names containing 'jira', 'atlassian', or similar terms.
    """
    potential_fields = []
    
    # Keywords to search for in field names
    keywords = ['jira', 'atlassian', 'atlassian_id', 'jira_id', 'jira_user', 'atlassian_user']
    
    for field in contact_desc['fields']:
        field_name = field['name'].lower()
        field_label = field.get('label', '').lower()
        
        # Check if field name or label contains any of our keywords
        for keyword in keywords:
            if keyword in field_name or keyword in field_label:
                potential_fields.append({
                    'name': field['name'],
                    'label': field.get('label', ''),
                    'type': field['type'],
                    'nillable': field.get('nillable', True)
                })
                break
    
    return potential_fields


def query_salesforce(config, access_token, query):
    """Execute a SOQL query."""
    encoded_query = urllib.parse.quote(query, safe='')
    url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_query}"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    all_records = []
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        all_records.extend(result.get('records', []))
        url = result.get('nextRecordsUrl')
        if url:
            url = f"{config['prod_server']}{url}"
    
    return all_records


def lookup_contact_by_jira_id(config, access_token, jira_userid, jira_field_name):
    """
    Lookup a Contact by Jira user ID and return their Organization (Account).
    
    Args:
        config: Salesforce configuration
        access_token: Salesforce access token
        jira_userid: The Jira/Atlassian user ID (e.g., 'bgradl')
        jira_field_name: The Salesforce field name that stores the Jira ID
    
    Returns:
        List of Contact records with Account information
    """
    # Query Contact with Account relationship
    query = (
        f"SELECT Id, FirstName, LastName, Email, AccountId, Account.Name, Account.Id, {jira_field_name} "
        f"FROM Contact "
        f"WHERE {jira_field_name} = '{jira_userid}'"
    )
    
    return query_salesforce(config, access_token, query)


def lookup_contact_by_email(config, access_token, email):
    """
    Lookup a Contact by email address and return their Organization (Account).
    
    Args:
        config: Salesforce configuration
        access_token: Salesforce access token
        email: The email address to lookup
    
    Returns:
        List of Contact records with Account information
    """
    # Query Contact with Account relationship by email
    # Use LIKE to handle case-insensitive matching
    query = (
        f"SELECT Id, FirstName, LastName, Email, AccountId, Account.Name, Account.Id "
        f"FROM Contact "
        f"WHERE Email = '{email}'"
    )
    
    return query_salesforce(config, access_token, query)


def main():
    parser = argparse.ArgumentParser(
        description="Lookup Organization from Salesforce by Jira/Atlassian User ID or Email"
    )
    parser.add_argument(
        '-c', '--config',
        required=True,
        help='Path to YAML config file (e.g., ../../data/config/sf-config.yaml or scripts/members/config.yaml)'
    )
    parser.add_argument(
        '-u', '--userid',
        help='Jira/Atlassian user ID to lookup (e.g., bgradl)'
    )
    parser.add_argument(
        '-e', '--email',
        help='Email address to lookup'
    )
    parser.add_argument(
        '--discover-fields',
        action='store_true',
        help='First discover available fields on Contact object'
    )
    parser.add_argument(
        '--field-name',
        help='Manually specify the Salesforce field name for Jira ID (skips discovery)'
    )
    
    args = parser.parse_args()
    
    # Validate that at least one lookup method is provided
    if not args.userid and not args.email:
        parser.error("Must specify either --userid (-u) or --email (-e) for lookup")
    
    # Load config
    print(f"Loading configuration from {args.config}...")
    try:
        config = load_config(args.config)
        print("✅ Config loaded")
    except Exception as e:
        print(f"❌ Error loading config: {e}")
        return
    
    # Get access token
    print("🔑 Getting access token...")
    try:
        access_token = get_access_token(config)
        print("✅ Access token obtained")
    except Exception as e:
        print(f"❌ Error getting access token: {e}")
        return
    
    contacts = []
    lookup_method = None
    
    # Try user ID lookup first if provided
    if args.userid:
        # If field name is manually specified, use it
        if args.field_name:
            jira_field_name = args.field_name
            print(f"Using manually specified field: {jira_field_name}")
        else:
            # Discover the field name
            print("\n📋 Describing Contact object to find Jira ID field...")
            try:
                contact_desc = describe_contact_object(config, access_token)
                print(f"✅ Contact object described ({len(contact_desc['fields'])} fields)")
            except Exception as e:
                print(f"❌ Error describing Contact object: {e}")
                return
            
            # Find potential Jira ID fields
            potential_fields = find_jira_id_field(contact_desc)
            
            if not potential_fields:
                print("\n⚠️  No fields found matching Jira/Atlassian keywords.")
                print("Available custom fields on Contact:")
                custom_fields = [f for f in contact_desc['fields'] if f['name'].endswith('__c')]
                for field in custom_fields[:20]:  # Show first 20 custom fields
                    print(f"  - {field['name']}: {field.get('label', '')} ({field['type']})")
                if len(custom_fields) > 20:
                    print(f"  ... and {len(custom_fields) - 20} more custom fields")
                
                if args.discover_fields:
                    print("\nAll Contact fields (first 50):")
                    for field in contact_desc['fields'][:50]:
                        print(f"  - {field['name']}: {field.get('label', '')} ({field['type']})")
                
                print("\nPlease use --field-name to specify the field name manually.")
                # If email is also provided, fall through to email lookup
                if not args.email:
                    return
            else:
                print(f"\n🔍 Found {len(potential_fields)} potential Jira ID field(s):")
                for field in potential_fields:
                    print(f"  - {field['name']}: {field['label']} ({field['type']})")
                
                # Use the first matching field (or let user choose)
                jira_field_name = potential_fields[0]['name']
                print(f"\n✅ Using field: {jira_field_name}")
                
                if len(potential_fields) > 1:
                    print(f"⚠️  Multiple fields found. Using first match. Use --field-name to specify a different field.")
        
        # Perform user ID lookup
        if 'jira_field_name' in locals():
            print(f"\n🔍 Looking up Contact with Jira ID '{args.userid}'...")
            try:
                contacts = lookup_contact_by_jira_id(config, access_token, args.userid, jira_field_name)
                if contacts:
                    lookup_method = f"Jira ID '{args.userid}'"
            except Exception as e:
                print(f"⚠️  Error looking up by Jira ID: {e}")
                if args.email:
                    print("  Falling back to email lookup...")
    
    # Try email lookup if no user ID match found (or if email was provided and user ID wasn't)
    if not contacts and args.email:
        print(f"\n🔍 Looking up Contact with email '{args.email}'...")
        try:
            contacts = lookup_contact_by_email(config, access_token, args.email)
            if contacts:
                lookup_method = f"email '{args.email}'"
        except Exception as e:
            print(f"❌ Error looking up by email: {e}")
            import traceback
            traceback.print_exc()
            return
    
    # Display results
    if not contacts:
        print(f"❌ No Contact found")
        if args.userid:
            print(f"   Tried Jira ID: '{args.userid}'")
        if args.email:
            print(f"   Tried email: '{args.email}'")
        return
    
    print(f"✅ Found {len(contacts)} Contact record(s) using {lookup_method}:\n")
    
    for i, contact in enumerate(contacts, 1):
        first_name = contact.get('FirstName', '')
        last_name = contact.get('LastName', '')
        name = f"{first_name} {last_name}".strip() or "N/A"
        email = contact.get('Email', 'N/A')
        contact_id = contact.get('Id', 'N/A')
        
        # Get Jira ID if available
        jira_id = 'N/A'
        if args.field_name and args.field_name in contact:
            jira_id = contact.get(args.field_name, 'N/A')
        elif 'atlassian_username_contact__c' in contact:
            jira_id = contact.get('atlassian_username_contact__c', 'N/A')
        
        account = contact.get('Account', {})
        account_name = account.get('Name', 'N/A') if account else 'N/A'
        account_id = account.get('Id', 'N/A') if account else 'N/A'
        
        print(f"Contact {i}:")
        print(f"  Name: {name}")
        print(f"  Email: {email}")
        if jira_id != 'N/A':
            print(f"  Jira ID: {jira_id}")
        print(f"  Contact ID: {contact_id}")
        print(f"  Organization: {account_name}")
        print(f"  Account ID: {account_id}")
        print()
    
    # Summary
    if len(contacts) == 1:
        account = contacts[0].get('Account', {})
        account_name = account.get('Name', '') if account else None
        lookup_value = args.userid if args.userid else args.email
        if account_name:
            print(f"✅ Organization for '{lookup_value}': {account_name}")
        else:
            print(f"⚠️  Contact '{lookup_value}' found but has no associated Organization")


if __name__ == '__main__':
    main()
