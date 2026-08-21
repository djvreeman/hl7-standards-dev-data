"""
Salesforce Diagnostic Script

This script helps diagnose the Salesforce data structure to find the correct way
to query for member organizations.
"""

import requests
import yaml
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


def main():
    print("Salesforce Diagnostic Script")
    print("=" * 50)
    
    # Load config
    config = load_config('../../data/config/sf-config.yaml')
    print(f"✅ Config loaded from ../../data/config/sf-config.yaml")
    
    # Get access token
    print("🔑 Getting access token...")
    token = get_access_token(config)
    print(f"✅ Access token obtained")
    
    # Test 1: Describe Account object
    print("\n📋 Describing Account object...")
    try:
        account_desc = describe_object(config, token, 'Account')
        print(f"✅ Account object described successfully")
        
        # Show available fields
        print(f"\nAccount fields ({len(account_desc['fields'])} total):")
        for field in account_desc['fields']:
            if field['name'] in ['Name', 'Type', 'Industry', 'BillingCity', 'BillingState', 'BillingCountry', 'Website', 'Phone']:
                print(f"  - {field['name']}: {field['type']} (required: {field['nillable'] == False})")
        
        # Show picklist values for Type field
        type_field = next((f for f in account_desc['fields'] if f['name'] == 'Type'), None)
        if type_field and 'picklistValues' in type_field:
            print(f"\nAccount Type picklist values:")
            for value in type_field['picklistValues']:
                print(f"  - {value['value']} (active: {value['active']})")
    
    except Exception as e:
        print(f"❌ Error describing Account: {e}")
    
    # Test 2: Query for different Account types
    print(f"\n🔍 Testing Account queries...")
    
    queries_to_test = [
        "SELECT Id, Name, Type, Industry, BillingCity, BillingState FROM Account WHERE Type = 'Member' LIMIT 5",
        "SELECT Id, Name, Type, Industry, BillingCity, BillingState FROM Account WHERE Type = 'Corporate Member' LIMIT 5",
        "SELECT Id, Name, Type, Industry, BillingCity, BillingState FROM Account WHERE Type = 'Affiliate' LIMIT 5",
        "SELECT Id, Name, Type, Industry, BillingCity, BillingState FROM Account WHERE Type LIKE '%Member%' LIMIT 10",
        "SELECT Id, Name, Type, Industry, BillingCity, BillingState FROM Account WHERE Type != null LIMIT 10",
        "SELECT Id, Name, Type, Industry, BillingCity, BillingState FROM Account LIMIT 10"
    ]
    
    for i, query in enumerate(queries_to_test, 1):
        print(f"\nQuery {i}: {query}")
        try:
            results = query_salesforce(config, token, query)
            print(f"  ✅ Found {len(results)} records")
            for record in results[:3]:  # Show first 3
                print(f"    - {record.get('Name', 'N/A')} (Type: {record.get('Type', 'N/A')})")
            if len(results) > 3:
                print(f"    ... and {len(results) - 3} more")
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Test 3: Look for other potential member-related objects
    print(f"\n🔍 Checking for other potential member objects...")
    
    # Try to describe some common objects that might contain member data
    potential_objects = ['Contact', 'OrderApi__Badge__c', 'OrderApi__Badge_Type__c', 'Membership__c', 'Member__c']
    
    for obj_name in potential_objects:
        try:
            obj_desc = describe_object(config, token, obj_name)
            print(f"✅ {obj_name} object exists with {len(obj_desc['fields'])} fields")
            
            # Show key fields
            key_fields = [f['name'] for f in obj_desc['fields'] if f['name'] in ['Name', 'Type', 'Status', 'Email', 'Account__c', 'Contact__c']]
            if key_fields:
                print(f"  Key fields: {', '.join(key_fields)}")
        except Exception as e:
            print(f"❌ {obj_name} object not found or not accessible: {e}")
    
    # Test 4: Query for organizations with badges (from the co-chairs script)
    print(f"\n🔍 Testing badge-based organization queries...")
    
    badge_queries = [
        """
        SELECT DISTINCT Account.Id, Account.Name, Account.BillingCity, Account.BillingState, Account.Website
        FROM OrderApi__Badge__c 
        WHERE OrderApi__Is_Active__c = true 
        AND OrderApi__Contact__r.AccountId != null
        LIMIT 10
        """,
        """
        SELECT Id, Name, BillingCity, BillingState, Website,
               (SELECT Id, Name FROM Contacts LIMIT 5)
        FROM Account 
        WHERE Id IN (
            SELECT DISTINCT OrderApi__Contact__r.AccountId 
            FROM OrderApi__Badge__c 
            WHERE OrderApi__Is_Active__c = true
        )
        LIMIT 10
        """
    ]
    
    for i, query in enumerate(badge_queries, 1):
        print(f"\nBadge Query {i}:")
        try:
            results = query_salesforce(config, token, query.strip())
            print(f"  ✅ Found {len(results)} records")
            for record in results[:3]:
                print(f"    - {record.get('Name', 'N/A')} (ID: {record.get('Id', 'N/A')[:10]}...)")
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print(f"\n{'=' * 50}")
    print("Diagnostic complete! Check the results above to understand your Salesforce structure.")


if __name__ == '__main__':
    main() 