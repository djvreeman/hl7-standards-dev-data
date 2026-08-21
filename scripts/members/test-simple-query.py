"""
Test a simpler approach - get Account IDs first, then query Accounts
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
    print("Testing Simple Query Approach")
    print("=" * 50)
    
    # Load config
    config = load_config('../../data/config/sf-config.yaml')
    print(f"✅ Config loaded")
    
    # Get access token
    print("🔑 Getting access token...")
    token = get_access_token(config)
    print(f"✅ Access token obtained")
    
    # Step 1: Get Account IDs from badges
    print(f"\n🔍 Step 1: Getting Account IDs from active badges...")
    badge_query = """
        SELECT DISTINCT OrderApi__Contact__r.AccountId 
        FROM OrderApi__Badge__c 
        WHERE OrderApi__Is_Active__c = true
        AND OrderApi__Contact__c != null
        LIMIT 20
    """
    
    try:
        badge_results = query_salesforce(config, token, badge_query.strip())
        print(f"✅ Found {len(badge_results)} Account IDs from badges")
        
        if badge_results:
            # Extract Account IDs
            account_ids = []
            for record in badge_results:
                if record.get('OrderApi__Contact__r', {}).get('AccountId'):
                    account_ids.append(record['OrderApi__Contact__r']['AccountId'])
            
            print(f"✅ Extracted {len(account_ids)} unique Account IDs")
            print(f"Sample Account IDs: {account_ids[:5]}")
            
            # Step 2: Query Accounts using the IDs
            if account_ids:
                print(f"\n🔍 Step 2: Querying Accounts...")
                account_ids_str = "', '".join(account_ids[:10])  # Limit to first 10 for testing
                account_query = f"""
                    SELECT Id, Name, BillingStreet, BillingCity, BillingState, 
                           BillingPostalCode, BillingCountry, Phone, Website
                    FROM Account 
                    WHERE Id IN ('{account_ids_str}')
                    ORDER BY Name
                """
                
                try:
                    account_results = query_salesforce(config, token, account_query.strip())
                    print(f"✅ Found {len(account_results)} member organizations")
                    
                    if account_results:
                        print(f"\nSample member organizations:")
                        for i, record in enumerate(account_results[:5], 1):
                            print(f"{i}. {record.get('Name', 'N/A')}")
                            print(f"   ID: {record.get('Id', 'N/A')[:10]}...")
                            if record.get('BillingCity') and record.get('BillingState'):
                                print(f"   Location: {record['BillingCity']}, {record['BillingState']}")
                            if record.get('Website'):
                                print(f"   Website: {record['Website']}")
                            print()
                    else:
                        print("❌ No member organizations found")
                        
                except Exception as e:
                    print(f"❌ Error querying Accounts: {e}")
            else:
                print("❌ No Account IDs found")
        else:
            print("❌ No badge records found")
            
    except Exception as e:
        print(f"❌ Error querying badges: {e}")
    
    print(f"\n{'=' * 50}")
    print("Test complete!")


if __name__ == '__main__':
    main() 