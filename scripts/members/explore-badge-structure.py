"""
Explore the OrderApi__Badge__c object structure
"""

import requests
import yaml
import urllib.parse


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
    print("Exploring OrderApi__Badge__c Structure")
    print("=" * 50)
    
    # Load config
    config = load_config('../../data/config/sf-config.yaml')
    print(f"✅ Config loaded")
    
    # Get access token
    print("🔑 Getting access token...")
    token = get_access_token(config)
    print(f"✅ Access token obtained")
    
    # Describe OrderApi__Badge__c object
    print(f"\n📋 Describing OrderApi__Badge__c object...")
    try:
        badge_desc = describe_object(config, token, 'OrderApi__Badge__c')
        print(f"✅ OrderApi__Badge__c object described successfully")
        
        # Show all fields
        print(f"\nOrderApi__Badge__c fields ({len(badge_desc['fields'])} total):")
        for field in badge_desc['fields']:
            print(f"  - {field['name']}: {field['type']} (required: {field['nillable'] == False})")
            if field['name'] in ['OrderApi__Contact__c', 'OrderApi__Is_Active__c', 'OrderApi__Badge_Type__c']:
                print(f"    * This is a key field for our query")
    
    except Exception as e:
        print(f"❌ Error describing OrderApi__Badge__c: {e}")
    
    # Test simple badge queries
    print(f"\n🔍 Testing simple badge queries...")
    
    simple_queries = [
        "SELECT Id, Name FROM OrderApi__Badge__c LIMIT 5",
        "SELECT Id, Name, OrderApi__Is_Active__c FROM OrderApi__Badge__c LIMIT 5",
        "SELECT Id, Name, OrderApi__Contact__c FROM OrderApi__Badge__c LIMIT 5",
        "SELECT Id, Name, OrderApi__Contact__c, OrderApi__Is_Active__c FROM OrderApi__Badge__c WHERE OrderApi__Is_Active__c = true LIMIT 5"
    ]
    
    for i, query in enumerate(simple_queries, 1):
        print(f"\nQuery {i}: {query}")
        try:
            results = query_salesforce(config, token, query)
            print(f"  ✅ Found {len(results)} records")
            for record in results[:3]:
                print(f"    - {record}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    # Test contact relationship
    print(f"\n🔍 Testing contact relationship...")
    
    contact_queries = [
        "SELECT Id, Name, OrderApi__Contact__c, OrderApi__Contact__r.Name FROM OrderApi__Badge__c WHERE OrderApi__Contact__c != null LIMIT 5",
        "SELECT Id, Name, OrderApi__Contact__c, OrderApi__Contact__r.AccountId FROM OrderApi__Badge__c WHERE OrderApi__Contact__c != null LIMIT 5"
    ]
    
    for i, query in enumerate(contact_queries, 1):
        print(f"\nContact Query {i}: {query}")
        try:
            results = query_salesforce(config, token, query)
            print(f"  ✅ Found {len(results)} records")
            for record in results[:3]:
                print(f"    - {record}")
        except Exception as e:
            print(f"  ❌ Error: {e}")
    
    print(f"\n{'=' * 50}")
    print("Exploration complete!")


if __name__ == '__main__':
    main() 