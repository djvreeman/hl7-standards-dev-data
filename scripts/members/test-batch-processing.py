#!/usr/bin/env python3
"""
Test script to verify batch processing works correctly
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

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


def test_batch_processing():
    """Test the batch processing approach."""
    print("Testing Batch Processing")
    print("=" * 50)
    
    try:
        # Load config
        config = load_config('../../data/config/sf-config.yaml')
        print("✅ Config loaded")
        
        # Get access token
        token = get_access_token(config)
        print("✅ Access token obtained")
        
        headers = {"Authorization": f"Bearer {token}"}
        
        # Step 1: Get a small sample of Contact IDs from badges
        print("\nStep 1: Getting sample Contact IDs from badges...")
        badge_query = "SELECT OrderApi__Contact__c FROM OrderApi__Badge__c WHERE OrderApi__Contact__c != null LIMIT 10"
        encoded_badge_query = urllib.parse.quote(badge_query, safe='')
        badge_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_badge_query}"
        
        response = requests.get(badge_url, headers=headers)
        response.raise_for_status()
        result = response.json()
        badge_records = result.get('records', [])
        
        print(f"✅ Found {len(badge_records)} badge records")
        
        # Extract Contact IDs
        contact_ids = set()
        for record in badge_records:
            if record.get('OrderApi__Contact__c'):
                contact_ids.add(record['OrderApi__Contact__c'])
        
        print(f"✅ Extracted {len(contact_ids)} unique Contact IDs")
        
        if not contact_ids:
            print("❌ No Contact IDs found")
            return
        
        # Step 2: Test batch processing for Contacts
        print("\nStep 2: Testing batch processing for Contacts...")
        contact_ids_list = list(contact_ids)
        batch_size = 5  # Small batch for testing
        contact_records = []
        
        for i in range(0, len(contact_ids_list), batch_size):
            batch = contact_ids_list[i:i + batch_size]
            contact_ids_str = "', '".join(batch)
            contact_query = f"SELECT AccountId FROM Contact WHERE Id IN ('{contact_ids_str}') AND AccountId != null"
            encoded_contact_query = urllib.parse.quote(contact_query, safe='')
            contact_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_contact_query}"
            
            response = requests.get(contact_url, headers=headers)
            response.raise_for_status()
            result = response.json()
            contact_records.extend(result.get('records', []))
            
            print(f"  ✅ Processed batch {i//batch_size + 1}/{(len(contact_ids_list) + batch_size - 1)//batch_size}")
        
        print(f"✅ Found {len(contact_records)} Contact records")
        
        # Extract Account IDs
        account_ids = set()
        for record in contact_records:
            if record.get('AccountId'):
                account_ids.add(record['AccountId'])
        
        print(f"✅ Found {len(account_ids)} unique Account IDs")
        
        if not account_ids:
            print("❌ No Account IDs found")
            return
        
        # Step 3: Test batch processing for Accounts
        print("\nStep 3: Testing batch processing for Accounts...")
        account_ids_list = list(account_ids)
        account_records = []
        
        for i in range(0, len(account_ids_list), batch_size):
            batch = account_ids_list[i:i + batch_size]
            account_ids_str = "', '".join(batch)
            account_query = f"""
                SELECT Id, Name, BillingCity, BillingState, Website
                FROM Account 
                WHERE Id IN ('{account_ids_str}')
                ORDER BY Name
            """
            encoded_account_query = urllib.parse.quote(account_query.strip(), safe='')
            account_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_account_query}"
            
            response = requests.get(account_url, headers=headers)
            response.raise_for_status()
            result = response.json()
            account_records.extend(result.get('records', []))
            
            print(f"  ✅ Processed batch {i//batch_size + 1}/{(len(account_ids_list) + batch_size - 1)//batch_size}")
        
        print(f"✅ Retrieved {len(account_records)} Account records")
        
        if account_records:
            print("\nSample member organizations:")
            for i, account in enumerate(account_records[:5], 1):
                print(f"{i}. {account.get('Name', 'N/A')}")
                print(f"   ID: {account.get('Id', 'N/A')[:10]}...")
                if account.get('BillingCity') and account.get('BillingState'):
                    print(f"   Location: {account['BillingCity']}, {account['BillingState']}")
                print()
        
        print("✅ Batch processing test completed successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == '__main__':
    test_batch_processing() 