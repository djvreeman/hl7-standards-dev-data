import os
import json
import requests

# Load configuration
with open("data/config/config.json", "r") as config_file:
    config = json.load(config_file)

BASE_URL = config["confluence_base_url"]
BEARER_TOKEN = config["confluence_bearer_token"]
SPACE_KEYS = config["confluence_space_key"]  # Now a list of space keys
OUTPUT_DIR = config["output_dir"]

def get_page_ids(space_key):
    """Fetch all page IDs from a specific Confluence space."""
    url = f"{BASE_URL}/rest/api/space/{space_key}/content"
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Accept": "application/json"
    }
    
    page_ids = []
    start = 0
    limit = 25  # Number of pages per request
    
    while True:
        params = {"start": start, "limit": limit}
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            # Extract page IDs
            for result in data.get("page", {}).get("results", []):
                page_ids.append(result["id"])
            # Handle pagination
            if data.get("_links", {}).get("next"):
                start += limit
            else:
                break
        else:
            print(f"Error fetching pages from space '{space_key}': {response.status_code} - {response.text}")
            break
    
    return page_ids

def save_page_ids_to_config(page_ids_dict, output_dir):
    """Save the page IDs in a config.json-compatible format."""
    os.makedirs(output_dir, exist_ok=True)
    output_file = os.path.join(output_dir, "page_ids_config.json")
    config_data = {"page_ids_by_space": page_ids_dict}
    
    with open(output_file, "w") as file:
        json.dump(config_data, file, indent=2)
    print(f"Page IDs saved to {output_file} in config.json format.")

if __name__ == "__main__":
    page_ids_by_space = {}
    for space_key in SPACE_KEYS:
        print(f"Fetching page IDs from space: {space_key}")
        page_ids = get_page_ids(space_key)
        print(f"Found {len(page_ids)} pages in space '{space_key}'.")
        page_ids_by_space[space_key] = page_ids
    
    if page_ids_by_space:
        save_page_ids_to_config(page_ids_by_space, OUTPUT_DIR)