#!/usr/bin/env python3
import argparse
import json
import requests
from markdown import markdown

def load_config(config_path):
    with open(config_path, 'r') as f:
        return json.load(f)

def create_page(config_path, space_key, title, markdown_file):
    # Load config
    config = load_config(config_path)
    base_url = config['confluence_base_url'].rstrip("/")
    bearer_token = config['confluence_bearer_token']
    headers = {
        "Authorization": f"Bearer {bearer_token}",
        "Content-Type": "application/json"
    }

    # Load and convert markdown
    with open(markdown_file, "r", encoding="utf-8") as f:
        md_text = f.read()
        html_content = markdown(md_text, extensions=["tables", "fenced_code"])

    # Build payload to create page
    payload = {
        "type": "page",
        "title": title,
        "space": {
            "key": space_key
        },
        "body": {
            "storage": {
                "value": html_content,
                "representation": "storage"
            }
        }
    }

    # POST to create content
    url = f"{base_url}/rest/api/content"
    response = requests.post(url, headers=headers, json=payload)
    if response.status_code == 200 or response.status_code == 201:
        data = response.json()
        print(f"✅ Page created: {base_url}/pages/viewpage.action?pageId={data['id']}")
    else:
        print(f"❌ Error creating page: {response.status_code}")
        print(response.text)
        response.raise_for_status()

def main():
    parser = argparse.ArgumentParser(description="Create a new Confluence page from markdown.")
    parser.add_argument("-c", "--config", required=True, help="Path to config.json with API info")
    parser.add_argument("-s", "--space", required=True, help="Confluence space key (e.g., 'FHIR')")
    parser.add_argument("-t", "--title", required=True, help="Title of the new page")
    parser.add_argument("-m", "--markdown", required=True, help="Path to the markdown file")
    args = parser.parse_args()

    create_page(args.config, args.space, args.title, args.markdown)

if __name__ == "__main__":
    main()