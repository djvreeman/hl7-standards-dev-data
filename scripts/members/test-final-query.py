"""
Test the final updated trademark member matcher
"""

import importlib.util
import sys

def main():
    print("Testing Final Updated Trademark Member Matcher")
    print("=" * 50)
    
    # Import the trademark matcher module
    spec = importlib.util.spec_from_file_location("tm", "trademark-member-matcher.py")
    tm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tm)
    
    try:
        # Load config
        print("Loading configuration...")
        config = tm.load_config('../../data/config/sf-config.yaml')
        print("✅ Configuration loaded")
        
        # Get access token
        print("Getting access token...")
        token = tm.get_access_token(config)
        print("✅ Access token obtained")
        
        # Fetch accounts
        print("Fetching member organizations...")
        accounts = tm.fetch_accounts(config, token)
        print(f"✅ Successfully retrieved {len(accounts)} member organizations")
        
        if accounts:
            print("\nSample member organizations:")
            for i, account in enumerate(accounts[:10], 1):
                print(f"{i}. {account.get('Name', 'N/A')}")
                print(f"   ID: {account.get('Id', 'N/A')[:10]}...")
                if account.get('BillingCity') and account.get('BillingState'):
                    print(f"   Location: {account['BillingCity']}, {account['BillingState']}")
                if account.get('Website'):
                    print(f"   Website: {account['Website']}")
                print()
            
            if len(accounts) > 10:
                print(f"... and {len(accounts) - 10} more organizations")
        else:
            print("❌ No member organizations found")
            
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    print(f"\n{'=' * 50}")
    print("Test complete!")


if __name__ == '__main__':
    main() 