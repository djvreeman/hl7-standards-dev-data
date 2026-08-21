#!/usr/bin/env python3
"""
Interactive Trademark Member Matcher GUI with State Management and Navigation
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import os
import sys
import threading
import pandas as pd
import requests
import yaml
import urllib.parse
import json
import pickle
from datetime import datetime
from fuzzywuzzy import fuzz, process

# Add the scripts/members directory to the path so we can import other modules
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

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

def search_salesforce_directly(config, access_token, search_term, limit=20, log_callback=None, restrict_by_badges=True):
    """Search Salesforce directly for accounts."""
    headers = {"Authorization": f"Bearer {access_token}"}
    
    if restrict_by_badges:
        # Badge types to include (same as fetch_accounts)
        badge_types = [
            "HL7 Affiliate",
            "HL7 Benefactor Member",
            "Comped Membership",
            "Affiliate Voting Member",
            "HL7 Organizational Member",
            "HL7 Gold Member",  # Re-added - badge type is active, instances may be inactive
            "HL7 Retiree Member",
            "HL7 Student Member",
            "HL7 Individual Member",
            "Voting Member"
        ]
        badge_type_filter = ", ".join([f"'{b}'" for b in badge_types])
        
        if log_callback:
            log_callback(f"Searching with badge restriction for: {search_term}")
        
        # Step 1: Get Contact IDs from badges (same as fetch_accounts)
        badge_query = (
            f"SELECT OrderApi__Contact__c FROM OrderApi__Badge__c "
            f"WHERE OrderApi__Badge_Type__r.Name IN ({badge_type_filter}) "
            f"AND OrderApi__Is_Active__c = true "
            f"AND OrderApi__Contact__c != null"
        )
        encoded_badge_query = urllib.parse.quote(badge_query, safe='')
        badge_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_badge_query}"
        
        try:
            response = requests.get(badge_url, headers=headers)
            response.raise_for_status()
            result = response.json()
            badge_records = result.get('records', [])
            
            if log_callback:
                log_callback(f"Found {len(badge_records)} badge records")
            
            # Extract unique Contact IDs
            contact_ids = set()
            for record in badge_records:
                if record.get('OrderApi__Contact__c'):
                    contact_ids.add(record['OrderApi__Contact__c'])
            
            if not contact_ids:
                if log_callback:
                    log_callback("No Contact IDs found from badges")
                return []
            
            # Step 2: Get Account IDs from Contacts
            contact_ids_list = list(contact_ids)
            batch_size = 200
            all_account_ids = set()
            
            for i in range(0, len(contact_ids_list), batch_size):
                batch = contact_ids_list[i:i + batch_size]
                contact_ids_str = "', '".join(batch)
                contact_query = f"SELECT AccountId FROM Contact WHERE Id IN ('{contact_ids_str}') AND AccountId != null"
                encoded_contact_query = urllib.parse.quote(contact_query, safe='')
                contact_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_contact_query}"
                
                response = requests.get(contact_url, headers=headers)
                response.raise_for_status()
                result = response.json()
                contact_records = result.get('records', [])
                
                for record in contact_records:
                    if record.get('AccountId'):
                        all_account_ids.add(record['AccountId'])
            
            if not all_account_ids:
                if log_callback:
                    log_callback("No Account IDs found from Contacts")
                return []
            
            # Step 3: Search Accounts with name filter
            account_ids_list = list(all_account_ids)
            all_results = []
            
            if log_callback:
                log_callback(f"Searching {len(account_ids_list)} member accounts for name containing '{search_term}'")
            
            for i in range(0, len(account_ids_list), batch_size):
                batch = account_ids_list[i:i + batch_size]
                account_ids_str = "', '".join(batch)
                account_query = f"""
                    SELECT Id, Name, BillingStreet, BillingCity, BillingState, 
                           BillingPostalCode, BillingCountry, Phone, Website
                    FROM Account 
                    WHERE Id IN ('{account_ids_str}')
                    AND Name LIKE '%{search_term}%'
                    ORDER BY Name
                    LIMIT {limit}
                """
                encoded_account_query = urllib.parse.quote(account_query.strip(), safe='')
                account_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_account_query}"
                
                response = requests.get(account_url, headers=headers)
                response.raise_for_status()
                result = response.json()
                batch_results = result.get('records', [])
                all_results.extend(batch_results)
                
                if log_callback:
                    log_callback(f"  Batch {i//batch_size + 1}: Found {len(batch_results)} matches")
                
                if len(all_results) >= limit:
                    break
            
            if log_callback:
                log_callback(f"Found {len(all_results)} matching accounts with badge restriction")
            
            return all_results[:limit]
            
        except Exception as e:
            if log_callback:
                log_callback(f"Error in restricted search: {e}")
            return []
    else:
        # Build SOQL query without badge restriction (original behavior)
        query = f"""
            SELECT Id, Name, BillingStreet, BillingCity, BillingState, 
                   BillingPostalCode, BillingCountry, Phone, Website
            FROM Account 
            WHERE Name LIKE '%{search_term}%'
            ORDER BY Name
            LIMIT {limit}
        """
        
        if log_callback:
            log_callback(f"Searching without badge restriction for: {search_term}")
        
        encoded_query = urllib.parse.quote(query.strip(), safe='')
        url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_query}"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()
            records = result.get('records', [])
            
            if log_callback:
                log_callback(f"Found {len(records)} accounts without badge restriction")
            
            return records
        except Exception as e:
            if log_callback:
                log_callback(f"Error searching Salesforce: {e}")
            return []

def fetch_accounts(config, access_token, log_callback=None):
    """Fetch Account records from Salesforce using a badge type filter."""
    headers = {"Authorization": f"Bearer {access_token}"}
    all_records = []

    # Badge types to include
    badge_types = [
        "HL7 Affiliate",
        "HL7 Benefactor Member",
        "Comped Membership",
        "Affiliate Voting Member",
        "HL7 Organizational Member",
        "HL7 Gold Member",  # Re-added - badge type is active, instances may be inactive
        "HL7 Retiree Member",
        "HL7 Student Member",
        "HL7 Individual Member",
        "Voting Member"
    ]
    badge_type_filter = ", ".join([f"'{b}'" for b in badge_types])

    if log_callback:
        log_callback("Step 1: Getting Contact IDs from badges with specific badge types...")

    badge_query = (
        f"SELECT OrderApi__Contact__c FROM OrderApi__Badge__c "
        f"WHERE OrderApi__Badge_Type__r.Name IN ({badge_type_filter}) "
        f"AND OrderApi__Is_Active__c = true "
        f"AND OrderApi__Contact__c != null"
    )
    encoded_badge_query = urllib.parse.quote(badge_query, safe='')
    badge_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_badge_query}"

    badge_records = []
    url = badge_url
    while url:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        result = response.json()
        badge_records.extend(result.get('records', []))
        url = result.get('nextRecordsUrl')
        if url:
            url = f"{config['prod_server']}{url}"

    if log_callback:
        log_callback(f"Found {len(badge_records)} badge records with specified types")

    # Extract unique Contact IDs
    contact_ids = set()
    for record in badge_records:
        if record.get('OrderApi__Contact__c'):
            contact_ids.add(record['OrderApi__Contact__c'])

    if log_callback:
        log_callback(f"Found {len(contact_ids)} unique Contact IDs")

    if not contact_ids:
        if log_callback:
            log_callback("No Contact IDs found from badges")
        return []

    # Step 2: Get Account IDs from Contacts (process in batches)
    if log_callback:
        log_callback("Step 2: Getting Account IDs from Contacts...")

    contact_ids_list = list(contact_ids)
    batch_size = 200
    contact_records = []

    for i in range(0, len(contact_ids_list), batch_size):
        batch = contact_ids_list[i:i + batch_size]
        contact_ids_str = "', '".join(batch)
        contact_query = f"SELECT AccountId FROM Contact WHERE Id IN ('{contact_ids_str}') AND AccountId != null"
        encoded_contact_query = urllib.parse.quote(contact_query, safe='')
        contact_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_contact_query}"

        url = contact_url
        while url:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()
            contact_records.extend(result.get('records', []))
            url = result.get('nextRecordsUrl')
            if url:
                url = f"{config['prod_server']}{url}"

        if log_callback:
            log_callback(f"  Processed batch {i//batch_size + 1}/{(len(contact_ids_list) + batch_size - 1)//batch_size}")

    if log_callback:
        log_callback(f"Found {len(contact_records)} Contact records")

    # Extract unique Account IDs
    account_ids = set()
    for record in contact_records:
        if record.get('AccountId'):
            account_ids.add(record['AccountId'])

    if log_callback:
        log_callback(f"Found {len(account_ids)} unique Account IDs")

    if not account_ids:
        if log_callback:
            log_callback("No Account IDs found from Contacts")
        return []

    # Step 3: Get Account details (process in batches)
    if log_callback:
        log_callback("Step 3: Getting Account details...")

    account_ids_list = list(account_ids)

    for i in range(0, len(account_ids_list), batch_size):
        batch = account_ids_list[i:i + batch_size]
        account_ids_str = "', '".join(batch)
        account_query = f"""
            SELECT Id, Name, BillingStreet, BillingCity, BillingState, 
                   BillingPostalCode, BillingCountry, Phone, Website
            FROM Account 
            WHERE Id IN ('{account_ids_str}')
            ORDER BY Name
        """
        encoded_account_query = urllib.parse.quote(account_query.strip(), safe='')
        account_url = f"{config['prod_server']}/services/data/v{config['version']}/query/?q={encoded_account_query}"

        url = account_url
        while url:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()
            all_records.extend(result.get('records', []))
            url = result.get('nextRecordsUrl')
            if url:
                url = f"{config['prod_server']}{url}"

        if log_callback:
            log_callback(f"  Processed batch {i//batch_size + 1}/{(len(account_ids_list) + batch_size - 1)//batch_size}")

    if log_callback:
        log_callback(f"Retrieved {len(all_records)} Account records")
    return all_records

def normalize_organization_name(name):
    """Normalize organization name for better matching."""
    if pd.isna(name):
        return ""
    
    name = str(name).strip()
    
    # Remove common suffixes
    suffixes = [' Inc', ' LLC', ' Ltd', ' Corp', ' Corporation', ' Company', ' Co', ' & Co']
    for suffix in suffixes:
        if name.endswith(suffix):
            name = name[:-len(suffix)]
    
    # Remove common prefixes
    prefixes = ['The ']
    for prefix in prefixes:
        if name.startswith(prefix):
            name = name[len(prefix):]
    
    return name.strip()

def find_matches(org_name, accounts, threshold=70, top_n=5):
    """Find fuzzy matches for organization name."""
    if not org_name or pd.isna(org_name):
        return []
    
    normalized_org = normalize_organization_name(org_name)
    account_names = [account['Name'] for account in accounts]
    
    # Try multiple fuzzy matching strategies
    all_matches = []
    
    # Strategy 1: Token sort ratio (handles word order differences)
    token_sort_matches = process.extract(normalized_org, account_names, 
                                       scorer=fuzz.token_sort_ratio, 
                                       limit=top_n)
    
    # Strategy 2: Token set ratio (handles partial matches)
    token_set_matches = process.extract(normalized_org, account_names, 
                                      scorer=fuzz.token_set_ratio, 
                                      limit=top_n)
    
    # Strategy 3: Partial ratio (handles substring matches)
    partial_matches = process.extract(normalized_org, account_names, 
                                    scorer=fuzz.partial_ratio, 
                                    limit=top_n)
    
    # Strategy 4: Simple ratio (exact character matching)
    simple_matches = process.extract(normalized_org, account_names, 
                                   scorer=fuzz.ratio, 
                                   limit=top_n)
    
    # Combine all matches and take the best score for each account
    match_scores = {}
    for match_name, score in token_sort_matches + token_set_matches + partial_matches + simple_matches:
        if match_name not in match_scores or score > match_scores[match_name]:
            match_scores[match_name] = score
    
    # Convert to list and sort by score
    all_matches = [(name, score) for name, score in match_scores.items()]
    all_matches.sort(key=lambda x: x[1], reverse=True)
    
    # Filter by threshold and create detailed results
    results = []
    for match_name, score in all_matches[:top_n]:
        if score >= threshold:
            # Find the account record
            account = next((acc for acc in accounts if acc['Name'] == match_name), None)
            if account:
                results.append({
                    'account': account,
                    'name': match_name,
                    'score': score,
                    'id': account['Id']
                })
    
    return results

def write_results(df, results, output_file, sheet_name):
    """Write results back to Excel file, updating the correct rows by row_index."""
    # Create a copy of the original dataframe
    result_df = df.copy()
    
    # Add new columns if not already present
    for col in ['Member_Y_N', 'SF_Member_ID', 'Confidence_Score', 'Review_Status', 'Matched_Organization']:
        if col not in result_df.columns:
            result_df[col] = ''
    
    # Fill in the results at the correct row_index
    for result in results:
        row_index = result['row_index']
        if 0 <= row_index < len(result_df):
            result_df.at[row_index, 'Member_Y_N'] = result['member_status']
            result_df.at[row_index, 'SF_Member_ID'] = result['sf_member_id']
            result_df.at[row_index, 'Confidence_Score'] = result['confidence_score']
            result_df.at[row_index, 'Review_Status'] = result['review_status']
            if result['selected_match']:
                result_df.at[row_index, 'Matched_Organization'] = result['selected_match']['name']
            else:
                result_df.at[row_index, 'Matched_Organization'] = ''
    
    # Write to Excel with proper error handling
    try:
        # Ensure sheet name doesn't exceed 31 characters (Excel limit)
        max_sheet_name_length = 31
        suffix = "_Results"
        max_base_length = max_sheet_name_length - len(suffix)
        
        if len(sheet_name) > max_base_length:
            truncated_sheet_name = sheet_name[:max_base_length]
            final_sheet_name = f"{truncated_sheet_name}{suffix}"
        else:
            final_sheet_name = f"{sheet_name}{suffix}"
        
        with pd.ExcelWriter(output_file, engine='openpyxl', mode='a' if os.path.exists(output_file) else 'w') as writer:
            result_df.to_excel(writer, sheet_name=final_sheet_name, index=False)
        return True, f"Results written to {output_file}, sheet: {final_sheet_name}"
    except Exception as e:
        # Try to write to a backup file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_file = output_file.replace('.xlsx', f'_backup_{timestamp}.xlsx')
        try:
            result_df.to_excel(backup_file, index=False)
            return True, f"Backup written to {backup_file}"
        except Exception as e2:
            # Write as CSV as last resort
            csv_file = output_file.replace('.xlsx', f'_backup_{timestamp}.csv')
            result_df.to_csv(csv_file, index=False)
            return True, f"CSV backup written to {csv_file}"

class ProcessingState:
    """Manages the state of processing for saving/loading progress."""
    
    def __init__(self, input_file, output_file, sheet_name, status_filter, threshold):
        self.input_file = input_file
        self.output_file = output_file
        self.sheet_name = sheet_name
        self.status_filter = status_filter
        self.threshold = threshold
        self.results = []
        self.current_index = 0
        self.total_records = 0
        self.accounts = []
        self.last_save_time = None
        
    def save_state(self, state_file):
        """Save current state to file."""
        state_data = {
            'input_file': self.input_file,
            'output_file': self.output_file,
            'sheet_name': self.sheet_name,
            'status_filter': self.status_filter,
            'threshold': self.threshold,
            'results': self.results,
            'current_index': self.current_index,
            'total_records': self.total_records,
            'last_save_time': datetime.now().isoformat()
        }
        
        try:
            with open(state_file, 'wb') as f:
                pickle.dump(state_data, f)
            self.last_save_time = datetime.now()
            return True
        except Exception as e:
            print(f"Error saving state: {e}")
            return False
    
    @classmethod
    def load_state(cls, state_file):
        """Load state from file."""
        try:
            with open(state_file, 'rb') as f:
                state_data = pickle.load(f)
            
            state = cls(
                state_data['input_file'],
                state_data['output_file'],
                state_data['sheet_name'],
                state_data['status_filter'],
                state_data['threshold']
            )
            state.results = state_data['results']
            state.current_index = state_data['current_index']
            state.total_records = state_data['total_records']
            state.last_save_time = datetime.fromisoformat(state_data['last_save_time'])
            return state
        except Exception as e:
            print(f"Error loading state: {e}")
            return None

class InteractiveReviewWindow:
    def __init__(self, parent, org_name, matches, config, token, log_callback, previous_result=None, cached_accounts=None):
        self.parent = parent
        self.org_name = org_name
        self.matches = matches
        self.config = config
        self.token = token
        self.log_callback = log_callback
        self.selected_match = None
        self.result = None
        self.previous_result = previous_result
        self.membership_history_cache = None  # Cache for membership history
        self.cached_accounts = cached_accounts  # All cached member accounts
        # Create review window with larger size
        self.window = tk.Toplevel(parent)
        self.window.title(f"Review Match: {org_name}")
        self.window.geometry("900x700")  # Increased size
        self.window.transient(parent)
        self.window.grab_set()
        self.setup_ui()
        
    def setup_ui(self):
        # Main frame
        main_frame = ttk.Frame(self.window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Organization info
        ttk.Label(main_frame, text=f"Organization: {self.org_name}", 
                 font=('Arial', 14, 'bold')).pack(anchor=tk.W, pady=(0, 20))
        
        # Create notebook for tabs
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
        
        # Tab 1: Fuzzy Matches
        matches_frame = ttk.Frame(notebook)
        notebook.add(matches_frame, text="Fuzzy Matches")
        self.setup_matches_tab(matches_frame)
        
        # Tab 2: Salesforce Search
        search_frame = ttk.Frame(notebook)
        notebook.add(search_frame, text="Salesforce Search")
        self.setup_search_tab(search_frame)
        
        # Tab 3: Membership History
        history_frame = ttk.Frame(notebook)
        notebook.add(history_frame, text="Membership History")
        self.setup_membership_history_tab(history_frame)
        
        # Buttons with more space
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(20, 0))
        
        ttk.Button(button_frame, text="No Match (Ctrl+N)", command=self.no_match).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Skip (Ctrl+S)", command=self.skip).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Quit Processing (Ctrl+Q)", command=self.quit_processing).pack(side=tk.RIGHT)
        
        # Add keyboard shortcuts for main window with Ctrl modifier
        def on_main_key_press(event):
            if event.state & 0x4:  # Ctrl key is pressed
                if event.keysym == 'n':
                    self.no_match()
                elif event.keysym == 's':
                    self.skip()
                elif event.keysym == 'q':
                    self.quit_processing()
        
        self.window.bind('<KeyPress>', on_main_key_press)
        
    def setup_matches_tab(self, parent):
        """Setup the fuzzy matches tab."""
        # Matches listbox
        ttk.Label(parent, text="Top Fuzzy Matches:", font=('Arial', 12, 'bold')).pack(anchor=tk.W, pady=(0, 10))
        
        # Create frame for listbox and scrollbar
        list_frame = ttk.Frame(parent)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.matches_listbox = tk.Listbox(list_frame, height=15)
        self.matches_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.matches_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.matches_listbox.configure(yscrollcommand=scrollbar.set)
        
        # Populate matches
        for i, match in enumerate(self.matches, 1):
            account = match['account']
            sf_id = account['Id']
            sf_url = f"https://hl7.lightning.force.com/lightning/r/Account/{sf_id}/view"
            display_text = f"{i}. {match['name']} (Score: {match['score']}%) - ID: {sf_id}"
            if account.get('BillingCity') and account.get('BillingState'):
                display_text += f" - {account['BillingCity']}, {account['BillingState']}"
            if account.get('Website'):
                display_text += f" - {account['Website']}"
            self.matches_listbox.insert(tk.END, display_text)
            
            # Store the URL for this item
            if not hasattr(self, 'match_urls'):
                self.match_urls = {}
            self.match_urls[i-1] = sf_url
        
        # Highlight previous selection if exists
        if self.previous_result and self.previous_result.get('selected_match'):
            prev_match = self.previous_result['selected_match']
            for i, match in enumerate(self.matches):
                if match['id'] == prev_match['id']:
                    self.matches_listbox.selection_set(i)
                    self.matches_listbox.see(i)
                    break
        
        # Add keyboard navigation
        def on_key_press(event):
            if event.keysym == 'Return':
                self.select_fuzzy_match()
            elif event.state & 0x4 and event.keysym == 'n':  # Ctrl+N for no match
                self.no_match()
        
        self.matches_listbox.bind('<KeyPress>', on_key_press)
        
        # Add double-click to open Salesforce URL
        def on_double_click(event):
            selection = self.matches_listbox.curselection()
            if selection and hasattr(self, 'match_urls'):
                index = selection[0]
                if index in self.match_urls:
                    import webbrowser
                    webbrowser.open(self.match_urls[index])
        
        self.matches_listbox.bind('<Double-Button-1>', on_double_click)
        self.matches_listbox.focus_set()  # Set focus to listbox
        
        # Instructions
        ttk.Label(parent, text="Keyboard: ↑/↓ to navigate, Enter to select, Ctrl+N for no match. Double-click to open Salesforce record.", 
                 font=('Arial', 9)).pack(pady=(5, 0))
        
        # Select match button
        ttk.Button(parent, text="Select Highlighted Match (Enter)", command=self.select_fuzzy_match).pack(pady=10)
        
    def setup_search_tab(self, parent):
        """Setup the Salesforce search tab."""
        # Search frame
        search_frame = ttk.Frame(parent)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        
        ttk.Label(search_frame, text="Search Term:").pack(side=tk.LEFT)
        self.search_var = tk.StringVar(value=self.org_name)
        search_entry = ttk.Entry(search_frame, textvariable=self.search_var, width=40)
        search_entry.pack(side=tk.LEFT, padx=(5, 10))
        
        ttk.Button(search_frame, text="Search", command=self.search_salesforce).pack(side=tk.LEFT)
        
        # Badge restriction option
        self.restrict_badges_var = tk.BooleanVar(value=True)  # Default enabled
        ttk.Checkbutton(search_frame, text="Restrict to HL7 Members", 
                       variable=self.restrict_badges_var).pack(side=tk.LEFT, padx=(10, 0))
        
        # Prefer direct search option
        self.prefer_direct_var = tk.BooleanVar(value=False)  # Default disabled
        ttk.Checkbutton(search_frame, text="Prefer Direct Search", 
                       variable=self.prefer_direct_var).pack(side=tk.LEFT, padx=(10, 0))
        
        # Cache refresh button
        ttk.Button(search_frame, text="Refresh Cache", command=self.refresh_cache).pack(side=tk.LEFT, padx=(10, 0))
        
        # Direct search button (bypass cache)
        ttk.Button(search_frame, text="Direct Search", command=self.direct_search).pack(side=tk.LEFT, padx=(10, 0))
        
        # Debug button to check organization badges
        ttk.Button(search_frame, text="Check Badges", command=self.check_organization_badges).pack(side=tk.LEFT, padx=(10, 0))
        
        # Search results label (will be updated dynamically)
        self.search_results_label = ttk.Label(parent, text="Search Results:", font=('Arial', 12, 'bold'))
        self.search_results_label.pack(anchor=tk.W, pady=(10, 5))
        
        # Create frame for results listbox
        results_frame = ttk.Frame(parent)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.search_results_listbox = tk.Listbox(results_frame, height=15)
        self.search_results_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        results_scrollbar = ttk.Scrollbar(results_frame, orient=tk.VERTICAL, command=self.search_results_listbox.yview)
        results_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.search_results_listbox.configure(yscrollcommand=results_scrollbar.set)
        
        # Add keyboard navigation for search results
        def on_search_key_press(event):
            if event.keysym == 'Return':
                self.select_search_result()
            elif event.state & 0x4 and event.keysym == 'n':  # Ctrl+N for no match
                self.no_match()
        
        self.search_results_listbox.bind('<KeyPress>', on_search_key_press)
        
        # Add double-click to open Salesforce URL for search results
        def on_search_double_click(event):
            selection = self.search_results_listbox.curselection()
            if selection and hasattr(self, 'search_urls'):
                index = selection[0]
                if index in self.search_urls:
                    import webbrowser
                    webbrowser.open(self.search_urls[index])
        
        self.search_results_listbox.bind('<Double-Button-1>', on_search_double_click)
        
        # Add keyboard navigation for search entry
        def on_search_entry_key_press(event):
            if event.keysym == 'Return':
                self.search_salesforce()
        
        search_entry.bind('<KeyPress>', on_search_entry_key_press)
        
        # Instructions
        ttk.Label(parent, text="Search: Enter to search, ↑/↓ to navigate results, Enter to select, Ctrl+N for no match. Double-click to open Salesforce record. Check 'Prefer Direct Search' to always bypass cache.", 
                 font=('Arial', 9)).pack(pady=(5, 0))
        
        # Select search result button
        ttk.Button(parent, text="Select Highlighted Search Result (Enter)", command=self.select_search_result).pack(pady=10)
        
    def setup_membership_history_tab(self, parent):
        """Setup the Membership History tab."""
        # Instructions
        ttk.Label(parent, text="This tab attempts to fetch and display all membership history records for the selected organization from Salesforce.", font=('Arial', 10)).pack(anchor=tk.W, pady=(0, 10))
        # Add a frame for controls
        controls_frame = ttk.Frame(parent)
        controls_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(controls_frame, text="Object Name:").pack(side=tk.LEFT)
        self.membership_object_var = tk.StringVar(value="Membership__c")
        object_entry = ttk.Entry(controls_frame, textvariable=self.membership_object_var, width=20)
        object_entry.pack(side=tk.LEFT, padx=(5, 10))
        ttk.Button(controls_frame, text="Fetch History", command=self.fetch_and_display_membership_history).pack(side=tk.LEFT)
        # Add a frame for the table
        self.history_table_frame = ttk.Frame(parent)
        self.history_table_frame.pack(fill=tk.BOTH, expand=True)
        # Fetch and display on tab open
        self.fetch_and_display_membership_history()
    def fetch_and_display_membership_history(self):
        # Clear previous table
        for widget in self.history_table_frame.winfo_children():
            widget.destroy()
        object_name = self.membership_object_var.get().strip()
        # Try to get Account ID from the selected match or top match
        account_id = None
        if self.selected_match and 'account' in self.selected_match:
            account_id = self.selected_match['account'].get('Id')
        elif self.matches and 'account' in self.matches[0]:
            account_id = self.matches[0]['account'].get('Id')
        if not account_id:
            ttk.Label(self.history_table_frame, text="No Account ID available for this organization.", foreground="red").pack()
            return
        # Query Salesforce for membership history
        try:
            records = self.query_membership_history(object_name, account_id)
            if not records:
                ttk.Label(self.history_table_frame, text=f"No records found in {object_name} for this Account.").pack()
                return
            # Display all fields in a table
            columns = sorted({k for rec in records for k in rec.keys()})
            tree = ttk.Treeview(self.history_table_frame, columns=columns, show='headings', height=10)
            for col in columns:
                tree.heading(col, text=col)
                tree.column(col, width=120, anchor=tk.W)
            for rec in records:
                values = [str(rec.get(col, '')) for col in columns]
                tree.insert('', tk.END, values=values)
            tree.pack(fill=tk.BOTH, expand=True)
            # Add vertical scrollbar
            vsb = ttk.Scrollbar(self.history_table_frame, orient="vertical", command=tree.yview)
            tree.configure(yscrollcommand=vsb.set)
            vsb.pack(side='right', fill='y')
        except Exception as e:
            ttk.Label(self.history_table_frame, text=f"Error fetching membership history: {e}", foreground="red").pack()
    def query_membership_history(self, object_name, account_id):
        """Query Salesforce for membership history records for the given Account ID and object name."""
        headers = {"Authorization": f"Bearer {self.token}"}
        # Try common field names for Account lookup
        possible_account_fields = ["Account__c", "AccountId", "account__c"]
        for account_field in possible_account_fields:
            soql = f"SELECT * FROM {object_name} WHERE {account_field} = '{account_id}' ORDER BY CreatedDate DESC LIMIT 100"
            url = f"{self.config['prod_server']}/services/data/v{self.config['version']}/query/?q=" + urllib.parse.quote(soql, safe='')
            try:
                response = requests.get(url, headers=headers)
                if response.status_code == 200:
                    result = response.json()
                    return result.get('records', [])
            except Exception:
                continue
        return []
    
    def search_salesforce(self):
        """Search Salesforce with the current search term."""
        search_term = self.search_var.get().strip()
        if not search_term:
            messagebox.showwarning("Warning", "Please enter a search term")
            return
        
        # Clear previous results
        self.search_results_listbox.delete(0, tk.END)
        
        try:
            # Get badge restriction setting
            restrict_by_badges = self.restrict_badges_var.get()
            
            # Log the search type being performed
            restriction_text = " (HL7 members only)" if restrict_by_badges else " (all accounts)"
            self.log_callback(f"Searching Salesforce for '{search_term}'{restriction_text}")
            
            if restrict_by_badges:
                # Check if user prefers direct search
                if self.prefer_direct_var.get():
                    self.log_callback("User prefers direct search, bypassing cache")
                    results = search_salesforce_directly(
                        self.config, self.token, search_term, 
                        limit=20, log_callback=self.log_callback,
                        restrict_by_badges=restrict_by_badges
                    )
                # For badge-restricted search, try using cached accounts first (more reliable)
                elif self.cached_accounts:
                    self.log_callback(f"Using {len(self.cached_accounts)} cached member accounts for search")
                    
                    # Enhanced search logic with multiple strategies
                    results = []
                    search_terms = search_term.lower().split()
                    
                    for account in self.cached_accounts:
                        account_name = account['Name'].lower()
                        matched = False
                        
                        # Strategy 1: Exact substring match
                        if search_term.lower() in account_name:
                            matched = True
                            self.log_callback(f"Found exact match: '{account['Name']}'")
                        
                        # Strategy 2: All search terms present (word-based search)
                        elif all(term in account_name for term in search_terms):
                            matched = True
                            self.log_callback(f"Found word match: '{account['Name']}'")
                        
                        # Strategy 3: Fuzzy matching for close matches
                        else:
                            from fuzzywuzzy import fuzz
                            ratio = fuzz.partial_ratio(search_term.lower(), account_name)
                            if ratio > 70:  # 70% similarity threshold
                                matched = True
                                self.log_callback(f"Found fuzzy match ({ratio}%): '{account['Name']}'")
                        
                        if matched:
                            results.append(account)
                    
                    self.log_callback(f"Found {len(results)} matches in cached accounts using enhanced search")
                    
                    # If no results in cache, try direct Salesforce search as fallback
                    if not results:
                        self.log_callback("No matches in cache, trying direct Salesforce search as fallback")
                        direct_results = search_salesforce_directly(
                            self.config, self.token, search_term, 
                            limit=20, log_callback=self.log_callback,
                            restrict_by_badges=restrict_by_badges
                        )
                        if direct_results:
                            self.log_callback(f"Found {len(direct_results)} matches via direct Salesforce search")
                            results = direct_results
                        else:
                            self.log_callback("No matches found via direct Salesforce search either")
                    else:
                        # Even if we found results in cache, check if direct search finds better matches
                        self.log_callback("Cache found results, but checking direct search for better matches...")
                        direct_results = search_salesforce_directly(
                            self.config, self.token, search_term, 
                            limit=20, log_callback=self.log_callback,
                            restrict_by_badges=restrict_by_badges
                        )
                        if direct_results:
                            # Compare results - if direct search has higher scores, use those
                            cache_scores = [match['score'] for match in find_matches(search_term, results, threshold=0, top_n=20)]
                            direct_scores = [match['score'] for match in find_matches(search_term, direct_results, threshold=0, top_n=20)]
                            
                            if direct_scores and (not cache_scores or max(direct_scores) > max(cache_scores)):
                                self.log_callback(f"Direct search found better matches (scores: {direct_scores} vs cache: {cache_scores})")
                                results = direct_results
                            else:
                                self.log_callback(f"Cache results are better (scores: {cache_scores} vs direct: {direct_scores})")
                else:
                    # Fallback to direct Salesforce search
                    self.log_callback("No cached accounts available, using direct Salesforce search")
                    results = search_salesforce_directly(
                        self.config, self.token, search_term, 
                        limit=20, log_callback=self.log_callback,
                        restrict_by_badges=restrict_by_badges
                    )
            else:
                # Search all accounts (no badge restriction)
                results = search_salesforce_directly(
                    self.config, self.token, search_term, 
                    limit=20, log_callback=self.log_callback,
                    restrict_by_badges=restrict_by_badges
                )
            
            if not results:
                restriction_text = " (HL7 members only)" if restrict_by_badges else " (all accounts)"
                self.search_results_listbox.insert(tk.END, f"No results found{restriction_text}")
                
                # Debug: Show some sample organizations from cached accounts
                if restrict_by_badges and self.cached_accounts:
                    self.search_results_listbox.insert(tk.END, "")
                    self.search_results_listbox.insert(tk.END, "Debug: Sample organizations in cache:")
                    sample_count = min(10, len(self.cached_accounts))
                    for i in range(sample_count):
                        org_name = self.cached_accounts[i]['Name']
                        self.search_results_listbox.insert(tk.END, f"  {org_name}")
                    if len(self.cached_accounts) > sample_count:
                        self.search_results_listbox.insert(tk.END, f"  ... and {len(self.cached_accounts) - sample_count} more")
                    
                    # Special debug for "national marrow" search
                    if "national" in search_term.lower() and "marrow" in search_term.lower():
                        self.search_results_listbox.insert(tk.END, "")
                        self.search_results_listbox.insert(tk.END, "Debug: Searching for 'National Marrow' specifically:")
                        found_any = False
                        for account in self.cached_accounts:
                            if "national" in account['Name'].lower() or "marrow" in account['Name'].lower():
                                self.search_results_listbox.insert(tk.END, f"  Found: '{account['Name']}'")
                                found_any = True
                        
                        if not found_any:
                            self.search_results_listbox.insert(tk.END, "  No organizations with 'national' or 'marrow' found in cache!")
                            self.search_results_listbox.insert(tk.END, "  This suggests the organization is not in the cached accounts.")
                        
                        # Also check for exact "National Marrow Donor Program"
                        exact_found = False
                        for account in self.cached_accounts:
                            if "national marrow donor program" in account['Name'].lower():
                                self.search_results_listbox.insert(tk.END, f"  EXACT MATCH: '{account['Name']}'")
                                exact_found = True
                        
                        if not exact_found:
                            self.search_results_listbox.insert(tk.END, "  'National Marrow Donor Program' NOT found in cache!")
                            
                            # Show organizations around "National" alphabetically
                            self.search_results_listbox.insert(tk.END, "")
                            self.search_results_listbox.insert(tk.END, "Debug: Organizations around 'National' in cache:")
                            national_orgs = [acc for acc in self.cached_accounts if "national" in acc['Name'].lower()]
                            national_orgs.sort(key=lambda x: x['Name'].lower())
                            for org in national_orgs[:10]:  # Show first 10
                                self.search_results_listbox.insert(tk.END, f"    '{org['Name']}'")
                            if len(national_orgs) > 10:
                                self.search_results_listbox.insert(tk.END, f"    ... and {len(national_orgs) - 10} more")
                
                return
            
            # Apply fuzzy matching to search results
            search_matches = find_matches(search_term, results, threshold=0, top_n=20)  # Lower threshold for search
            
            # Store search results for selection
            self.search_results = search_matches
            
            # Update results label with restriction info
            restriction_text = " (HL7 members only)" if restrict_by_badges else " (all accounts)"
            self.search_results_label.config(text=f"Search Results{restriction_text}:")
            
            # Store URLs for search results
            self.search_urls = {}
            
            for i, match in enumerate(search_matches, 1):
                account = match['account']
                sf_id = account['Id']
                sf_url = f"https://hl7.lightning.force.com/lightning/r/Account/{sf_id}/view"
                display_text = f"{i}. {match['name']} (Score: {match['score']}%) - ID: {sf_id}"
                if account.get('BillingCity') and account.get('BillingState'):
                    display_text += f" - {account['BillingCity']}, {account['BillingState']}"
                if account.get('Website'):
                    display_text += f" - {account['Website']}"
                self.search_results_listbox.insert(tk.END, display_text)
                self.search_urls[i-1] = sf_url
                
        except Exception as e:
            self.search_results_listbox.insert(tk.END, f"Error: {e}")
    
    def select_fuzzy_match(self):
        """Select a fuzzy match."""
        selection = self.matches_listbox.curselection()
        if selection:
            index = selection[0]
            if index < len(self.matches):
                self.selected_match = self.matches[index]
                self.result = 'selected'
                self.window.destroy()
        else:
            messagebox.showwarning("Warning", "Please select a match first")
    
    def select_search_result(self):
        """Select a search result."""
        selection = self.search_results_listbox.curselection()
        if selection:
            index = selection[0]
            if hasattr(self, 'search_results') and index < len(self.search_results):
                self.selected_match = self.search_results[index]
                self.result = 'selected'
                self.window.destroy()
        else:
            messagebox.showwarning("Warning", "Please select a search result first")
    
    def no_match(self):
        """Mark as no match."""
        self.selected_match = None
        self.result = 'no_match'
        self.window.destroy()
    
    def skip(self):
        """Skip this record."""
        self.selected_match = None
        self.result = 'skip'
        self.window.destroy()
    
    def quit_processing(self):
        """Quit processing."""
        self.selected_match = None
        self.result = 'quit'
        self.window.destroy()
    
    def refresh_cache(self):
        """Refresh the cached accounts from Salesforce."""
        try:
            self.log_callback("Refreshing cached accounts from Salesforce...")
            
            # Fetch fresh accounts using the function from this module
            fresh_accounts = fetch_accounts(self.config, self.token, self.log_callback)
            if fresh_accounts:
                self.cached_accounts = fresh_accounts
                self.log_callback(f"Cache refreshed: {len(fresh_accounts)} accounts loaded")
                
                # Debug: Check if specific organizations are in the cache
                org_names = [acc['Name'] for acc in fresh_accounts]
                if "National Marrow Donor Program" in org_names:
                    self.log_callback("✓ 'National Marrow Donor Program' found in refreshed cache")
                else:
                    self.log_callback("✗ 'National Marrow Donor Program' NOT found in refreshed cache")
                    
                # Check for other "National" organizations
                national_orgs = [name for name in org_names if "national" in name.lower()]
                self.log_callback(f"Found {len(national_orgs)} organizations with 'national' in name")
                for org in national_orgs[:5]:  # Show first 5
                    self.log_callback(f"  - {org}")
                
                messagebox.showinfo("Cache Refreshed", f"Loaded {len(fresh_accounts)} fresh accounts from Salesforce")
            else:
                self.log_callback("Failed to refresh cache - no accounts returned")
                messagebox.showerror("Cache Refresh Failed", "No accounts returned from Salesforce")
        except Exception as e:
            self.log_callback(f"Error refreshing cache: {e}")
            messagebox.showerror("Cache Refresh Error", f"Error: {e}")
    
    def check_organization_badges(self):
        """Check if a specific organization has the expected badges."""
        try:
            org_name = "National Marrow Donor Program"
            self.log_callback(f"Checking badges for '{org_name}'...")
            
            # First, find the Account ID for this organization
            account_query = f"SELECT Id FROM Account WHERE Name = '{org_name}'"
            encoded_query = urllib.parse.quote(account_query, safe='')
            url = f"{self.config['prod_server']}/services/data/v{self.config['version']}/query/?q={encoded_query}"
            
            headers = {"Authorization": f"Bearer {self.token}"}
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            result = response.json()
            accounts = result.get('records', [])
            
            if not accounts:
                self.log_callback(f"✗ Account '{org_name}' not found in Salesforce")
                return
            
            account_id = accounts[0]['Id']
            self.log_callback(f"✓ Found Account ID: {account_id}")
            
            # Now check for badges associated with this account
            badge_query = f"""
                SELECT OrderApi__Badge_Type__r.Name, OrderApi__Is_Active__c, OrderApi__Contact__c
                FROM OrderApi__Badge__c 
                WHERE OrderApi__Contact__c IN (
                    SELECT Id FROM Contact WHERE AccountId = '{account_id}'
                )
            """
            encoded_badge_query = urllib.parse.quote(badge_query, safe='')
            badge_url = f"{self.config['prod_server']}/services/data/v{self.config['version']}/query/?q={encoded_badge_query}"
            
            response = requests.get(badge_url, headers=headers)
            response.raise_for_status()
            result = response.json()
            badges = result.get('records', [])
            
            self.log_callback(f"Found {len(badges)} badges for '{org_name}':")
            for badge in badges:
                badge_type = badge.get('OrderApi__Badge_Type__r', {}).get('Name', 'Unknown')
                is_active = badge.get('OrderApi__Is_Active__c', False)
                contact_id = badge.get('OrderApi__Contact__c', 'Unknown')
                self.log_callback(f"  - {badge_type} (Active: {is_active}, Contact: {contact_id})")
            
            # Check if any of these badges are in our target list
            target_badges = [
                "HL7 Affiliate", "HL7 Benefactor Member", "Comped Membership",
                "Affiliate Voting Member", "HL7 Organizational Member", 
                "HL7 Gold Member",  # Re-added - badge type is active, instances may be inactive
                "HL7 Retiree Member", "HL7 Student Member", 
                "HL7 Individual Member", "Voting Member"
            ]
            
            matching_badges = [b for b in badges if b.get('OrderApi__Badge_Type__r', {}).get('Name') in target_badges]
            self.log_callback(f"Found {len(matching_badges)} matching target badges")
            
            if matching_badges:
                self.log_callback("✓ Organization should be in cache")
            else:
                self.log_callback("✗ Organization has no matching target badges")
                
        except Exception as e:
            self.log_callback(f"Error checking organization badges: {e}")
    
    def direct_search(self):
        """Perform a direct Salesforce search, bypassing the cache."""
        search_term = self.search_var.get().strip()
        if not search_term:
            messagebox.showwarning("Warning", "Please enter a search term")
            return
        
        # Clear previous results
        self.search_results_listbox.delete(0, tk.END)
        
        try:
            restrict_by_badges = self.restrict_badges_var.get()
            restriction_text = " (HL7 members only)" if restrict_by_badges else " (all accounts)"
            
            self.log_callback(f"Direct Salesforce search for '{search_term}'{restriction_text}")
            
            # Perform direct Salesforce search
            results = search_salesforce_directly(
                self.config, self.token, search_term, 
                limit=20, log_callback=self.log_callback,
                restrict_by_badges=restrict_by_badges
            )
            
            if not results:
                self.search_results_listbox.insert(tk.END, f"No results found via direct search{restriction_text}")
                return
            
            # Apply fuzzy matching to search results
            search_matches = find_matches(search_term, results, threshold=0, top_n=20)
            
            # Store search results for selection
            self.search_results = search_matches
            
            # Update results label
            self.search_results_label.config(text=f"Direct Search Results{restriction_text}:")
            
            # Store URLs for search results
            self.search_urls = {}
            
            for i, match in enumerate(search_matches, 1):
                account = match['account']
                sf_id = account['Id']
                sf_url = f"https://hl7.lightning.force.com/lightning/r/Account/{sf_id}/view"
                display_text = f"{i}. {match['name']} (Score: {match['score']}%) - ID: {sf_id}"
                if account.get('BillingCity') and account.get('BillingState'):
                    display_text += f" - {account['BillingCity']}, {account['BillingState']}"
                if account.get('Website'):
                    display_text += f" - {account['Website']}"
                self.search_results_listbox.insert(tk.END, display_text)
                self.search_urls[i-1] = sf_url
                
        except Exception as e:
            self.search_results_listbox.insert(tk.END, f"Error: {e}")
    
    def wait_for_result(self):
        """Wait for user to make a selection."""
        self.window.wait_window()
        return self.result, self.selected_match

def main():
    root = tk.Tk()
    root.title("Interactive Trademark Matcher with State Management")
    root.geometry("800x700")
    
    # Main frame
    frame = ttk.Frame(root, padding="20")
    frame.pack(fill=tk.BOTH, expand=True)
    
    # Title
    ttk.Label(frame, text="Interactive Trademark Member Matcher", 
             font=('Arial', 16, 'bold')).pack(pady=(0, 20))
    
    # File selection section
    ttk.Label(frame, text="File Configuration", font=('Arial', 12, 'bold')).pack(anchor=tk.W, pady=(0, 10))
    
    # Config file
    config_frame = ttk.Frame(frame)
    config_frame.pack(fill=tk.X, pady=5)
    ttk.Label(config_frame, text="Config File:").pack(side=tk.LEFT)
    config_var = tk.StringVar(value="data/config/sf-config.yaml")
    ttk.Entry(config_frame, textvariable=config_var, width=50).pack(side=tk.LEFT, padx=(5, 5))
    
    def browse_config():
        filename = filedialog.askopenfilename(
            title="Select Config File",
            filetypes=[("YAML files", "*.yaml"), ("All files", "*.*")]
        )
        if filename:
            config_var.set(filename)
    
    ttk.Button(config_frame, text="Browse", command=browse_config).pack(side=tk.LEFT)
    
    # Input file
    input_frame = ttk.Frame(frame)
    input_frame.pack(fill=tk.X, pady=5)
    ttk.Label(input_frame, text="Input File:").pack(side=tk.LEFT)
    input_var = tk.StringVar()
    ttk.Entry(input_frame, textvariable=input_var, width=50).pack(side=tk.LEFT, padx=(5, 5))
    
    def browse_input():
        filename = filedialog.askopenfilename(
            title="Select Input Excel File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if filename:
            input_var.set(filename)
    
    ttk.Button(input_frame, text="Browse", command=browse_input).pack(side=tk.LEFT)
    
    # Output file
    output_frame = ttk.Frame(frame)
    output_frame.pack(fill=tk.X, pady=5)
    ttk.Label(output_frame, text="Output File:").pack(side=tk.LEFT)
    output_var = tk.StringVar()
    ttk.Entry(output_frame, textvariable=output_var, width=50).pack(side=tk.LEFT, padx=(5, 5))
    
    def browse_output():
        filename = filedialog.asksaveasfilename(
            title="Select Output Excel File",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if filename:
            output_var.set(filename)
    
    ttk.Button(output_frame, text="Browse", command=browse_output).pack(side=tk.LEFT)
    
    # Options section
    ttk.Label(frame, text="Processing Options", font=('Arial', 12, 'bold')).pack(anchor=tk.W, pady=(20, 10))
    
    options_frame = ttk.Frame(frame)
    options_frame.pack(fill=tk.X, pady=5)
    
    ttk.Label(options_frame, text="Status Filter:").pack(side=tk.LEFT)
    status_var = tk.StringVar(value="approved")
    ttk.Entry(options_frame, textvariable=status_var, width=20).pack(side=tk.LEFT, padx=(5, 20))
    
    ttk.Label(options_frame, text="Fuzzy Threshold:").pack(side=tk.LEFT)
    threshold_var = tk.IntVar(value=70)
    ttk.Spinbox(options_frame, from_=0, to=100, textvariable=threshold_var, width=10).pack(side=tk.LEFT, padx=(5, 0))
    
    # Status log area
    ttk.Label(frame, text="Status Log:", font=('Arial', 10, 'bold')).pack(anchor=tk.W, pady=(20, 5))
    
    log_frame = ttk.Frame(frame)
    log_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
    
    status_text = scrolledtext.ScrolledText(log_frame, height=8, width=70)
    status_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
    
    def log_message(message):
        """Add message to status log."""
        status_text.insert(tk.END, f"{message}\n")
        status_text.see(tk.END)
        root.update()
    
    # Status label
    status_label_var = tk.StringVar(value="Ready")
    ttk.Label(frame, textvariable=status_label_var).pack(anchor=tk.W, pady=10)
    
    # State management variables
    current_state = None
    state_file_var = tk.StringVar()
    
    def load_saved_state():
        """Load a saved processing state."""
        nonlocal current_state
        
        filename = filedialog.askopenfilename(
            title="Select State File",
            filetypes=[("State files", "*.state"), ("All files", "*.*")]
        )
        if filename:
            state = ProcessingState.load_state(filename)
            if state:
                current_state = state
                input_var.set(state.input_file)
                output_var.set(state.output_file)
                status_var.set(state.status_filter)
                threshold_var.set(state.threshold)
                state_file_var.set(filename)
                log_message(f"Loaded state from {filename}")
                log_message(f"Progress: {len(state.results)}/{state.total_records} records processed")
                status_label_var.set(f"State loaded: {len(state.results)}/{state.total_records} processed")
            else:
                messagebox.showerror("Error", "Failed to load state file")
    
    def save_current_state():
        """Save current processing state."""
        if current_state:
            filename = filedialog.asksaveasfilename(
                title="Save State File",
                defaultextension=".state",
                filetypes=[("State files", "*.state"), ("All files", "*.*")]
            )
            if filename:
                if current_state.save_state(filename):
                    log_message(f"State saved to {filename}")
                    messagebox.showinfo("Success", f"State saved to {filename}")
                else:
                    messagebox.showerror("Error", "Failed to save state")
        else:
            messagebox.showwarning("Warning", "No processing state to save")
    
    def start_interactive_processing():
        """Start interactive processing with state management."""
        if not input_var.get() or not output_var.get():
            messagebox.showerror("Error", "Please select both input and output files")
            return
        
        if not config_var.get():
            messagebox.showerror("Error", "Please select a config file")
            return
        
        status_label_var.set("Processing data...")
        log_message("Starting interactive trademark application processing...")
        
        def process_thread():
            nonlocal current_state
            
            try:
                # Load config and get token
                log_message("Loading configuration...")
                config = load_config(config_var.get())
                token = get_access_token(config)
                log_message("Salesforce connection established")
                
                # Load Excel file
                log_message("Loading Excel file...")
                xl = pd.ExcelFile(input_var.get())
                
                # Show worksheet selection dialog if multiple sheets exist
                if len(xl.sheet_names) > 1:
                    # Create a simple dialog to select worksheet
                    sheet_dialog = tk.Toplevel(root)
                    sheet_dialog.title("Select Worksheet")
                    sheet_dialog.geometry("400x300")
                    sheet_dialog.transient(root)
                    sheet_dialog.grab_set()
                    
                    # Center the dialog
                    sheet_dialog.geometry("+%d+%d" % (root.winfo_rootx() + 50, root.winfo_rooty() + 50))
                    
                    # Main frame
                    dialog_frame = ttk.Frame(sheet_dialog, padding="20")
                    dialog_frame.pack(fill=tk.BOTH, expand=True)
                    
                    ttk.Label(dialog_frame, text="Select a worksheet to process:", 
                             font=('Arial', 12, 'bold')).pack(pady=(0, 20))
                    
                    # Create listbox for sheets
                    list_frame = ttk.Frame(dialog_frame)
                    list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 20))
                    
                    sheet_listbox = tk.Listbox(list_frame, height=10)
                    sheet_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
                    
                    scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=sheet_listbox.yview)
                    scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
                    sheet_listbox.configure(yscrollcommand=scrollbar.set)
                    
                    # Populate sheets
                    for i, sheet in enumerate(xl.sheet_names):
                        # Try to get row count for each sheet
                        try:
                            temp_df = pd.read_excel(xl, sheet)
                            row_count = len(temp_df)
                            display_text = f"{sheet} ({row_count} records)"
                        except:
                            display_text = f"{sheet} (error reading)"
                        sheet_listbox.insert(tk.END, display_text)
                    
                    # Select first sheet by default
                    sheet_listbox.selection_set(0)
                    sheet_listbox.see(0)
                    
                    selected_sheet = [None]  # Use list to store selection
                    
                    def on_sheet_select():
                        selection = sheet_listbox.curselection()
                        if selection:
                            selected_sheet[0] = xl.sheet_names[selection[0]]
                            sheet_dialog.destroy()
                    
                    def on_cancel():
                        selected_sheet[0] = None
                        sheet_dialog.destroy()
                    
                    # Buttons
                    button_frame = ttk.Frame(dialog_frame)
                    button_frame.pack(fill=tk.X, pady=(20, 0))
                    
                    ttk.Button(button_frame, text="Select", command=on_sheet_select).pack(side=tk.LEFT, padx=(0, 10))
                    ttk.Button(button_frame, text="Cancel", command=on_cancel).pack(side=tk.LEFT)
                    
                    # Add keyboard shortcuts
                    def on_dialog_key_press(event):
                        if event.keysym == 'Return':
                            on_sheet_select()
                        elif event.keysym == 'Escape':
                            on_cancel()
                    
                    sheet_dialog.bind('<KeyPress>', on_dialog_key_press)
                    sheet_listbox.bind('<Double-Button-1>', lambda e: on_sheet_select())
                    
                    # Wait for user selection
                    sheet_dialog.wait_window()
                    
                    if selected_sheet[0] is None:
                        log_message("Worksheet selection cancelled")
                        return
                    
                    sheet_name = selected_sheet[0]
                    log_message(f"User selected sheet: '{sheet_name}'")
                else:
                    sheet_name = xl.sheet_names[0]  # Use first sheet if only one exists
                    log_message(f"Only one sheet found: '{sheet_name}'")
                
                df = pd.read_excel(xl, sheet_name)
                log_message(f"Loaded sheet '{sheet_name}' with {len(df)} records")
                
                # Filter by status if specified
                if status_var.get() and 'Status' in df.columns:
                    df = df[df['Status'].str.lower() == status_var.get().lower()]
                    log_message(f"Filtered to {len(df)} records with status '{status_var.get()}'")
                
                # Initialize or load state
                if current_state is None:
                    current_state = ProcessingState(
                        input_var.get(), output_var.get(), sheet_name, 
                        status_var.get(), threshold_var.get()
                    )
                    current_state.total_records = len(df)
                    current_state.current_index = 0
                else:
                    # Use existing state
                    log_message(f"Resuming from state: {len(current_state.results)} records already processed")
                
                # Fetch accounts from Salesforce (only if not already loaded)
                if not current_state.accounts:
                    log_message("Fetching member accounts from Salesforce...")
                    accounts = fetch_accounts(config, token, log_message)
                    current_state.accounts = accounts
                    log_message(f"Retrieved {len(accounts)} member accounts")
                else:
                    accounts = current_state.accounts
                    log_message(f"Using {len(accounts)} cached member accounts")
                
                if not accounts:
                    log_message("No member accounts found. Processing stopped.")
                    return
                
                # Start navigation interface
                show_navigation_interface(df, current_state, config, token, log_message, accounts)
                
            except Exception as e:
                error_msg = f"Processing failed: {e}"
                log_message(f"ERROR: {error_msg}")
                root.after(0, lambda: messagebox.showerror("Error", error_msg))
                root.after(0, lambda: status_label_var.set("Processing failed"))
        
        # Start processing in a separate thread
        thread = threading.Thread(target=process_thread)
        thread.daemon = True
        thread.start()
    
    def show_navigation_interface(df, state, config, token, log_message, accounts):
        """Show the navigation interface for processing records."""
        nav_window = tk.Toplevel(root)
        nav_window.title("Record Navigation")
        nav_window.geometry("600x400")
        nav_window.transient(root)
        nav_window.grab_set()
        
        # Main frame
        main_frame = ttk.Frame(nav_window, padding="20")
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Progress info
        progress_var = tk.StringVar()
        ttk.Label(main_frame, textvariable=progress_var, font=('Arial', 12, 'bold')).pack(pady=(0, 20))
        
        # Current record info
        record_frame = ttk.LabelFrame(main_frame, text="Current Record", padding="10")
        record_frame.pack(fill=tk.X, pady=(0, 20))
        
        org_label = ttk.Label(record_frame, text="", font=('Arial', 10))
        org_label.pack(anchor=tk.W)
        
        email_label = ttk.Label(record_frame, text="", font=('Arial', 9))
        email_label.pack(anchor=tk.W)
        
        current_record_index = state.current_index
        
        def update_display():
            """Update the display with current record info."""
            if current_record_index < len(df):
                row = df.iloc[current_record_index]
                org_name = row.get('Organization', '')
                contact_email = row.get('Contact Email', '')
                
                org_label.config(text=f"Organization: {org_name}")
                email_label.config(text=f"Email: {contact_email}")
                
                # Check if already processed
                existing_result = next((r for r in state.results if r['row_index'] == current_record_index), None)
                if existing_result:
                    status = f"Status: {existing_result['review_status']}"
                    if existing_result['selected_match']:
                        status += f" - Matched: {existing_result['selected_match']['name']}"
                    else:
                        status += " - No match"
                else:
                    status = "Status: Not processed"
                
                progress_var.set(f"Record {current_record_index + 1} of {len(df)} - {status}")
            else:
                org_label.config(text="No more records")
                email_label.config(text="")
                progress_var.set(f"All {len(df)} records processed")
        
        def navigate_record(direction):
            """Navigate to previous or next record."""
            nonlocal current_record_index
            
            new_index = current_record_index + direction
            if 0 <= new_index < len(df):
                current_record_index = new_index
                update_display()
                nav_log_message(f"Navigated to record {current_record_index + 1}")
            else:
                nav_log_message(f"Cannot navigate {'backward' if direction < 0 else 'forward'} - at {'first' if direction < 0 else 'last'} record")
        
        def review_current():
            """Review the current record."""
            if current_record_index >= len(df):
                nav_log_message("No current record to review")
                return
            
            row = df.iloc[current_record_index]
            org_name = row.get('Organization', '')
            contact_email = row.get('Contact Email', '')
            
            if pd.isna(org_name) or not org_name.strip():
                nav_log_message(f"Skipping record {current_record_index + 1}: No organization name")
                return
            
            # Find existing result
            existing_result = next((r for r in state.results if r['row_index'] == current_record_index), None)
            
            # Find fuzzy matches
            matches = find_matches(org_name, accounts, threshold_var.get())
            
            nav_log_message(f"Opening review window for: {org_name}")
            
            # Show review window
            review_window = InteractiveReviewWindow(
                nav_window, org_name, matches, config, token, nav_log_message, existing_result, accounts
            )
            
            result, selected_match = review_window.wait_for_result()
            
            if result == 'quit':
                nav_log_message("Review cancelled")
                return
            elif result == 'skip':
                review_status = 'skipped'
                selected_match = None
            elif result == 'no_match':
                review_status = 'no_match'
                selected_match = None
            else:  # selected
                review_status = 'manual_review'
            
            # Determine member status
            member_status = 'Y' if selected_match else 'N'
            sf_member_id = selected_match['id'] if selected_match else ''
            confidence_score = selected_match['score'] if selected_match else 0
            
            # Update or add result
            if existing_result:
                # Update existing result
                existing_result.update({
                    'selected_match': selected_match,
                    'member_status': member_status,
                    'sf_member_id': sf_member_id,
                    'confidence_score': confidence_score,
                    'review_status': review_status
                })
                nav_log_message(f"Updated record {current_record_index + 1}")
            else:
                # Add new result
                result_data = {
                    'row_index': current_record_index,
                    'organization': org_name,
                    'contact_email': contact_email,
                    'matches': matches,
                    'selected_match': selected_match,
                    'member_status': member_status,
                    'sf_member_id': sf_member_id,
                    'confidence_score': confidence_score,
                    'review_status': review_status
                }
                state.results.append(result_data)
                nav_log_message(f"Processed record {current_record_index + 1}")
            
            # Update current index if this was the next unprocessed record
            if current_record_index == state.current_index:
                state.current_index = current_record_index + 1
            
            update_display()
        
        # Navigation buttons
        nav_frame = ttk.Frame(main_frame)
        nav_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Button(nav_frame, text="← Previous (Left Arrow)", command=lambda: navigate_record(-1)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(nav_frame, text="Next → (Right Arrow)", command=lambda: navigate_record(1)).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(nav_frame, text="Review Current (Enter)", command=review_current).pack(side=tk.LEFT, padx=(0, 10))
        
        # Action buttons
        action_frame = ttk.Frame(main_frame)
        action_frame.pack(fill=tk.X, pady=(0, 20))
        
        ttk.Button(action_frame, text="Save State", command=lambda: save_state_from_nav()).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(action_frame, text="Save Results", command=lambda: save_results_from_nav()).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(action_frame, text="Close", command=nav_window.destroy).pack(side=tk.RIGHT)
        
        # Status log
        log_label = ttk.Label(main_frame, text="Navigation Log:", font=('Arial', 10, 'bold')).pack(anchor=tk.W)
        nav_log = scrolledtext.ScrolledText(main_frame, height=8, width=60)
        nav_log.pack(fill=tk.BOTH, expand=True)
        
        def nav_log_message(message):
            """Add message to navigation log."""
            nav_log.insert(tk.END, f"{message}\n")
            nav_log.see(tk.END)
            nav_window.update()
        
        def save_state_from_nav():
            """Save state from navigation window."""
            filename = filedialog.asksaveasfilename(
                title="Save State File",
                defaultextension=".state",
                filetypes=[("State files", "*.state"), ("All files", "*.*")]
            )
            if filename:
                if state.save_state(filename):
                    nav_log_message(f"State saved to {filename}")
                    messagebox.showinfo("Success", f"State saved to {filename}")
                else:
                    messagebox.showerror("Error", "Failed to save state")
        
        def save_results_from_nav():
            """Save results from navigation window."""
            if not state.results:
                messagebox.showwarning("Warning", "No results to save")
                return
            
            success, message = write_results(df, state.results, output_var.get(), state.sheet_name)
            nav_log_message(message)
            if success:
                messagebox.showinfo("Success", f"Results saved!\n{message}")
            else:
                messagebox.showerror("Error", f"Failed to save results: {message}")
        
        # Add keyboard shortcuts
        def on_nav_key_press(event):
            if event.keysym == 'Left':
                navigate_record(-1)
            elif event.keysym == 'Right':
                navigate_record(1)
            elif event.keysym == 'Return':
                review_current()
        
        nav_window.bind('<KeyPress>', on_nav_key_press)
        
        # Initialize display
        update_display()
        nav_log_message("Navigation interface ready. Use Left/Right arrow keys to navigate, Enter to review current record.")
        
        # Wait for window to close
        nav_window.wait_window()

    # Buttons
    button_frame = ttk.Frame(frame)
    button_frame.pack(pady=20)
    
    ttk.Button(button_frame, text="Load State", command=load_saved_state).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(button_frame, text="Save State", command=save_current_state).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(button_frame, text="Start Interactive Processing", 
               command=start_interactive_processing).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(button_frame, text="Quit", command=root.quit).pack(side=tk.LEFT)
    
    root.mainloop()

if __name__ == '__main__':
    main() 