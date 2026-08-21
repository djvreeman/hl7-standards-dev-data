#!/usr/bin/env python3
"""
Check if Salesforce tracks Contact Account (Organization) history

This script investigates whether Salesforce maintains a history of Account changes
for Contacts, which would be important for historical ballot participation data.

USAGE:
    python3 check-contact-account-history.py -c path/to/config.yaml -u bgradl
"""

import requests
import yaml
import argparse
import urllib.parse
import json


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


def describe_object(config, access_token, object_name):
    """Describe a Salesforce object to understand its structure."""
    url = f"{config['prod_server']}/services/data/v{config['version']}/sobjects/{object_name}/describe"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    return response.json()


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


def check_field_history(config, access_token, object_name):
    """Check if field history tracking is enabled for an object."""
    url = f"{config['prod_server']}/services/data/v{config['version']}/sobjects/{object_name}/describe"
    headers = {"Authorization": f"Bearer {access_token}"}
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    obj_desc = response.json()
    
    # Check if object has field history tracking
    return {
        'has_field_history': obj_desc.get('recordTypeInfo', {}).get('available', False),
        'fields': obj_desc.get('fields', [])
    }


def main():
    parser = argparse.ArgumentParser(
        description="Check if Salesforce tracks Contact Account history"
    )
    parser.add_argument(
        '-c', '--config',
        required=True,
        help='Path to YAML config file'
    )
    parser.add_argument(
        '-u', '--userid',
        help='Jira user ID to check (e.g., bgradl)'
    )
    
    args = parser.parse_args()
    
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
    
    # Check Contact object for history tracking
    print("\n📋 Checking Contact object for field history tracking...")
    try:
        contact_desc = describe_object(config, access_token, 'Contact')
        print(f"✅ Contact object described ({len(contact_desc['fields'])} fields)")
        
        # Look for AccountId field
        account_field = next((f for f in contact_desc['fields'] if f['name'] == 'AccountId'), None)
        if account_field:
            print(f"\n📌 AccountId field found:")
            print(f"  - Type: {account_field['type']}")
            print(f"  - Updateable: {account_field.get('updateable', False)}")
            print(f"  - Createable: {account_field.get('createable', False)}")
    except Exception as e:
        print(f"❌ Error describing Contact: {e}")
        return
    
    # Check for FieldHistoryTracked objects
    print("\n🔍 Checking for Field History objects...")
    
    # Standard Salesforce field history objects
    history_objects = [
        'ContactHistory',
        'AccountHistory',  # In case Account changes are tracked
    ]
    
    for obj_name in history_objects:
        try:
            obj_desc = describe_object(config, access_token, obj_name)
            print(f"✅ {obj_name} object exists!")
            print(f"  Fields: {len(obj_desc['fields'])}")
            
            # Show key fields
            key_fields = [f['name'] for f in obj_desc['fields'] 
                         if f['name'] in ['Field', 'OldValue', 'NewValue', 'CreatedDate', 'CreatedBy', 'ContactId', 'AccountId']]
            if key_fields:
                print(f"  Key fields: {', '.join(key_fields)}")
            
            # Show sample of available fields
            print(f"  Sample fields:")
            for field in obj_desc['fields'][:10]:
                print(f"    - {field['name']}: {field['type']}")
            if len(obj_desc['fields']) > 10:
                print(f"    ... and {len(obj_desc['fields']) - 10} more")
                
        except Exception as e:
            print(f"❌ {obj_name} not accessible: {e}")
    
    # Check if we can query ContactHistory for AccountId changes
    print("\n🔍 Checking ContactHistory for AccountId field tracking...")
    try:
        # Try to query ContactHistory to see what fields are tracked
        query = "SELECT Field, OldValue, NewValue, CreatedDate, ContactId FROM ContactHistory WHERE Field = 'AccountId' LIMIT 5"
        history_records = query_salesforce(config, access_token, query)
        
        if history_records:
            print(f"✅ Found {len(history_records)} AccountId change records in ContactHistory!")
            print("\nSample records:")
            for i, record in enumerate(history_records[:3], 1):
                print(f"\n  Record {i}:")
                print(f"    Contact ID: {record.get('ContactId', 'N/A')}")
                print(f"    Field: {record.get('Field', 'N/A')}")
                print(f"    Old Value: {record.get('OldValue', 'N/A')}")
                print(f"    New Value: {record.get('NewValue', 'N/A')}")
                print(f"    Date: {record.get('CreatedDate', 'N/A')}")
        else:
            print("⚠️  No AccountId change records found in ContactHistory")
            print("   This could mean:")
            print("   1. Field history tracking is not enabled for AccountId")
            print("   2. No Account changes have occurred")
            print("   3. History is stored elsewhere")
            
    except Exception as e:
        print(f"⚠️  Could not query ContactHistory: {e}")
        print("   This might mean field history tracking is not enabled")
    
    # If userid provided, check that specific contact
    if args.userid:
        print(f"\n🔍 Checking Contact for userid '{args.userid}'...")
        try:
            # First find the contact
            query = f"SELECT Id, FirstName, LastName, AccountId, Account.Name, atlassian_username_contact__c FROM Contact WHERE atlassian_username_contact__c = '{args.userid}'"
            contacts = query_salesforce(config, access_token, query)
            
            if contacts:
                contact = contacts[0]
                contact_id = contact.get('Id')
                account_name = contact.get('Account', {}).get('Name', 'N/A') if contact.get('Account') else 'N/A'
                
                print(f"✅ Found Contact: {contact.get('FirstName', '')} {contact.get('LastName', '')}")
                print(f"   Current Organization: {account_name}")
                print(f"   Contact ID: {contact_id}")
                
                # Check history for this specific contact
                print(f"\n📜 Checking history for this Contact...")
                history_query = f"SELECT Field, OldValue, NewValue, CreatedDate FROM ContactHistory WHERE ContactId = '{contact_id}' AND Field = 'AccountId' ORDER BY CreatedDate DESC"
                try:
                    contact_history = query_salesforce(config, access_token, history_query)
                    if contact_history:
                        print(f"✅ Found {len(contact_history)} AccountId change(s) for this Contact:")
                        for i, hist in enumerate(contact_history, 1):
                            print(f"\n  Change {i}:")
                            print(f"    Date: {hist.get('CreatedDate', 'N/A')}")
                            print(f"    Old Value: {hist.get('OldValue', 'N/A')}")
                            print(f"    New Value: {hist.get('NewValue', 'N/A')}")
                    else:
                        print("⚠️  No AccountId change history found for this Contact")
                        print("   This could mean:")
                        print("   - The Contact has never changed Accounts")
                        print("   - Field history tracking is not enabled")
                except Exception as e:
                    print(f"⚠️  Could not query history for this Contact: {e}")
            else:
                print(f"❌ No Contact found with userid '{args.userid}'")
        except Exception as e:
            print(f"❌ Error checking Contact: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("Summary:")
    print("="*60)
    print("Field history tracking in Salesforce:")
    print("  - ContactHistory object exists if field history is enabled")
    print("  - AccountId field changes can be tracked if enabled")
    print("  - Historical Account associations may be available")
    print("\nIf ContactHistory shows AccountId changes, you can:")
    print("  - Query historical Account associations by date")
    print("  - Match ballot dates with Account at that time")
    print("\nIf ContactHistory does NOT show AccountId changes:")
    print("  - Only current Account association is available")
    print("  - Historical ballot data may have different orgs")


if __name__ == '__main__':
    main()
