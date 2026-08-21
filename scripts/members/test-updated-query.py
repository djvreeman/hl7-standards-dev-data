"""
Test the updated query for member organizations
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
    print("Testing Updated Member Organization Query")
    print("=" * 50)
    
    # Load config
    config = load_config('../../data/config/sf-config.yaml')
    print(f"✅ Config loaded")
    
    # Get access token
    print("🔑 Getting access token...")
    token = get_access_token(config)
    print(f"✅ Access token obtained")
    
    # Test the updated query
    subquery = (
        "SELECT OrderApi__Contact__c FROM OrderApi__Badge__c "
        "WHERE OrderApi__Is_Active__c = true"
    )

    query = (
        "SELECT Id, Name, BillingStreet, BillingCity, BillingState, "
        "BillingPostalCode, BillingCountry, Phone, Website "
        f"FROM Account WHERE Id IN ("
        f"SELECT AccountId FROM Contact WHERE Id IN ({subquery})"
        f") ORDER BY Name LIMIT 20"
    )
    
    print(f"\n🔍 Testing updated query...")
    print(f"Query: {query.strip()}")
    
    try:
        results = query_salesforce(config, token, query.strip())
        print(f"✅ Found {len(results)} member organizations")
        
        if results:
            print(f"\nSample member organizations:")
            for i, record in enumerate(results[:10], 1):
                print(f"{i}. {record.get('Name', 'N/A')}")
                print(f"   ID: {record.get('Id', 'N/A')[:10]}...")
                if record.get('BillingCity') and record.get('BillingState'):
                    print(f"   Location: {record['BillingCity']}, {record['BillingState']}")
                if record.get('Website'):
                    print(f"   Website: {record['Website']}")
                print()
            
            if len(results) > 10:
                print(f"... and {len(results) - 10} more organizations")
        else:
            print("❌ No member organizations found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
    
    print(f"\n{'=' * 50}")
    print("Test complete!")


if __name__ == '__main__':
    main() 