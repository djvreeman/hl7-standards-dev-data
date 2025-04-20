# confluence-config-cli.py
#
# Usage:
#   python confluence-config-cli.py add \
#       --url https://confluence.hl7.org/spaces/FHIR/pages/90352022/Archived+Pages \
#       --section excludes \
#       --type parent_pages \
#       --main-config config/main.yaml
#
# Description:
#   Adds a Confluence page (or parent page) to a YAML config file under the specified
#   include or exclude section. The page title is fetched using the Confluence API.
#   Automatically detects or asks for the Confluence space key, and writes to
#   data/config/spaces/<space_key>.yaml, creating the file if needed.

import argparse
import os
import requests
from urllib.parse import urlparse
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedMap

def log_message(message):
    print(message)

def load_yaml(path):
    if not os.path.exists(path):
        return {}
    with open(path, 'r') as f:
        yaml = YAML()
        data = yaml.load(f)
        return data if data is not None else {}

def save_yaml(data, path):
    yaml = YAML()
    yaml.default_flow_style = False
    yaml.allow_unicode = True

    def recursively_add_comments(node):
        if isinstance(node, dict):
            for k, v in list(node.items()):
                if isinstance(v, dict):
                    if '_comment' in v:
                        comment = v.pop('_comment')
                        node.yaml_set_comment_before_after_key(k, before=comment)
                    recursively_add_comments(v)
                elif isinstance(v, list):
                    for item in v:
                        recursively_add_comments(item)

    commented_data = CommentedMap(data)
    recursively_add_comments(commented_data)

    with open(path, 'w', encoding='utf-8') as f:
        yaml.dump(commented_data, f)

def fetch_page_title(base_url, token, page_id):
    url = f"{base_url}/rest/api/content/{page_id}?expand=title"
    headers = {"Authorization": f"Bearer {token}"}

    response = requests.get(url, headers=headers)

    if response.status_code == 404:
        log_message(f"⚠️ Page {page_id} not found via token. Retrying unauthenticated...")
        response = requests.get(url)

        if response.status_code == 404:
            log_message(f"❌ Page {page_id} still not found even when unauthenticated.")
            print("")
            print(f"⚠️  The page ID {page_id} could not be retrieved automatically via the Confluence API.")
            choice = input("Would you like to manually enter the page title? (y/n): ").strip().lower()

            if choice == 'y':
                manual_title = input("Enter the page title exactly as you want it recorded: ").strip()
                if not manual_title:
                    raise SystemExit(f"Aborting: No title provided for page ID {page_id}.")

                manual_annotation = input("Optional: Enter a comment/annotation about why this page is excluded (or leave blank): ").strip()
                return manual_title, manual_annotation
            else:
                raise SystemExit(f"Aborting: Could not retrieve title for page ID {page_id} and manual entry declined.")

    response.raise_for_status()
    data = response.json()
    return data['title'], None

def parse_page_id_from_url(url):
    parsed = urlparse(url)
    if '/download/attachments/' in parsed.path:
        return parsed.path.split('/')[3]
    parts = parsed.path.split('/')
    try:
        idx = parts.index('pages')
        return parts[idx + 1]
    except (ValueError, IndexError):
        raise ValueError(f"Invalid Confluence URL format: {url}")

def determine_entry_type(base_url, token, url, page_id):
    if '/download/attachments/' in url:
        log_message(f"🔎 URL points to an attachment — treating as attachment.")
        return 'attachments'

    child_url = f"{base_url}/rest/api/content/{page_id}/child/page"
    headers = {"Authorization": f"Bearer {token}"}
    child_resp = requests.get(child_url, headers=headers)

    if child_resp.status_code == 200:
        data = child_resp.json()
        if data.get('size', 0) > 0:
            log_message(f"🔎 Page {page_id} has children — treating as parent_page.")
            return 'parent_pages'
        else:
            log_message(f"🔎 Page {page_id} has no children — treating as normal page.")
            return 'pages'
    else:
        log_message(f"⚠️ Could not determine if page {page_id} has children, defaulting to page.")
        return 'pages'

def ensure_space_config_structure(space_config, space_key):
    if 'space_key' not in space_config:
        space_config['space_key'] = space_key
    if 'includes' not in space_config:
        space_config['includes'] = {'parent_pages': [], 'pages': [], 'attachments': []}
    else:
        space_config['includes'].setdefault('parent_pages', [])
        space_config['includes'].setdefault('pages', [])
        space_config['includes'].setdefault('attachments', [])
    if 'excludes' not in space_config:
        space_config['excludes'] = {'parent_pages': [], 'pages': [], 'attachments': []}
    else:
        space_config['excludes'].setdefault('parent_pages', [])
        space_config['excludes'].setdefault('pages', [])
        space_config['excludes'].setdefault('attachments', [])
    return space_config

def add_entry(main_config, section, entry_type, url, token):
    base_url = main_config.get('confluence_base_url')
    spaces_dir = main_config.get('spaces_dir', 'data/config/spaces')

    page_id = parse_page_id_from_url(url)
    title, annotation = fetch_page_title(base_url, token, page_id)

    space_key = url.split('/spaces/')[1].split('/')[0]
    space_config_path = os.path.join(spaces_dir, f"{space_key}.yaml")

    space_config = load_yaml(space_config_path)
    space_config = ensure_space_config_structure(space_config, space_key)

    if entry_type == 'auto':
        entry_type = determine_entry_type(base_url, token, url, page_id)

    if section not in space_config:
        space_config[section] = {}
    if entry_type not in space_config[section]:
        space_config[section][entry_type] = []

    new_entry = {'id': int(page_id), 'title': title}
    if annotation:
        new_entry['_comment'] = annotation

    existing_ids = {str(entry.get('id')) for entry in space_config[section][entry_type] if isinstance(entry, dict)}
    if str(new_entry['id']) in existing_ids:
        log_message(f"⚠️ Page ID {new_entry['id']} already exists under {section}/{entry_type}, skipping.")
    else:
        space_config[section][entry_type].append(new_entry)
        log_message(f"✅ Added page ID {new_entry['id']} to {section}/{entry_type}.")

    save_yaml(space_config, space_config_path)
    log_message(f"✅ Successfully updated {space_config_path}.")

def main():
    parser = argparse.ArgumentParser(description="Modify Confluence config YAMLs.")
    parser.add_argument('action', choices=['add'], help='Action to perform (currently only supports add)')
    parser.add_argument('--main-config', required=True, help='Path to main YAML config file')
    parser.add_argument('--section', required=True, help='Top-level section (e.g., includes or excludes)')
    parser.add_argument('--type', required=True, help='Type within section (pages, parent_pages, attachments, or auto)')
    parser.add_argument('--url', required=True, help='Full URL to Confluence page or attachment')
    args = parser.parse_args()

    main_config = load_yaml(args.main_config)

    base_url = main_config.get('confluence_base_url')
    token = main_config.get('confluence_bearer_token')

    if not base_url or not token:
        log_message("❌ Main config must contain both 'confluence_base_url' and 'confluence_bearer_token'.")
        raise SystemExit(1)

    if args.action == 'add':
        add_entry(main_config, args.section, args.type, args.url, token)

if __name__ == '__main__':
    main()
