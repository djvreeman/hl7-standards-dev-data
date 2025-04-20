# convert-confluence-to-markdown-v2.py
#
# Usage:
#   python convert-confluence-to-markdown-v2.py \
#       --main-config config/main.yaml \
#       --spaces-dir data/config/spaces \
#       [--spaces FHIR,HE] \
#       [--dry-run] \
#       [--dry-run-output reports/summary.txt] \
#       [--log-file logs/export.log] \
#       [--explicit]
#
# Description:
#   This script processes Confluence spaces based on YAML config files. Each space
#   has a config in data/config/spaces/<space_key>.yaml that defines which pages or
#   parent pages to include or exclude. Includes override excludes.
#
#   By default, ALL spaces in the directory are processed unless --spaces is specified.
#   When --dry-run is enabled, the script prints the list of included, excluded,
#   and re-included pages. Optionally, it writes this summary to a file if
#   --dry-run-output is provided.
#
#   Spaces can individually specify 'explicit-mode: true' in their YAML config.
#   When a space has 'explicit-mode: true', only explicitly listed content is processed.
#
#   If --explicit is passed on the command line, it overrides all space settings,
#   forcing explicit mode ON for every space, regardless of YAML.
#
# - The YAML config can specify excluded parent pages, pages, or attachments under the excludes section. For example, this excludes a particular outdated attachment:
#
#   excludes:
#     attachments:
#       - id: 35717349
#         title: HL7 Committee Best Practices v1.0.zip
#
# Attachments are excluded if either their ID or title matches.
# 
# The explicit mode behavior (either via --explicit or 'explicit-mode: true' in YAML)
# only parses content that is specifically included in the space's 'includes' section.
# Otherwise, the default is to process everything in the space (minus excludes).

import argparse
import os
import re
import html
import yaml
import requests
from bs4 import BeautifulSoup
import markdownify
from urllib.parse import urljoin, unquote
from collections import defaultdict

INVALID_FILENAME_CHARS = re.compile(r'[^a-zA-Z0-9+_.-]')
logger = None

def log_message(message):
    print(message)
    if logger:
        with open(logger, 'a') as f:
            f.write(message + '\n')

def sanitize_filename(title):
    title = unquote(title)
    title = html.unescape(title)
    title = title.replace(" ", "+")
    title = INVALID_FILENAME_CHARS.sub("", title)
    title = re.sub(r"^[.-]+|[.-]+$", "", title)
    title = re.sub(r"_+$", "", title)
    return title

def download_attachment(attachment_url, token, output_path):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(attachment_url, headers=headers, stream=True)
    if response.status_code == 200:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        return os.path.exists(output_path)
    return False

def get_attachments(base_url, token, page_id):
    url = f"{base_url}/rest/api/content/{page_id}/child/attachment"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def extract_diagrams_and_media(content_html, base_url, token, page_id, output_dir):
    soup = BeautifulSoup(content_html, "html.parser")
    diagrams = soup.find_all("ac:structured-macro", {"ac:name": "drawio"})
    media_links = soup.find_all("ac:image")

    attachments = get_attachments(base_url, token, page_id)
    if not attachments:
        return str(soup)

    attachments_dir = os.path.join(output_dir, "attachments")
    os.makedirs(attachments_dir, exist_ok=True)

    fallback_images = []
    for diagram in diagrams:
        param = diagram.find("ac:parameter", {"ac:name": "diagramName"})
        if not param:
            continue
        diagram_name = param.text.strip()
        for att in attachments.get("results", []):
            if att["title"].startswith(diagram_name):
                full_url = f"{base_url}{att['_links']['download']}"
                output_path = os.path.join(attachments_dir, att['title'])
                if download_attachment(full_url, token, output_path):
                    rel_path = os.path.relpath(output_path, output_dir)
                    if diagram.parent:
                        diagram.replace_with(f"![{att['title']}]({rel_path})")
                    else:
                        log_message(f"⚠️ Warning: Diagram {att['title']} not attached to tree, skipping replace.")
                        fallback_images.append((att['title'], rel_path))

    for media in media_links:
        attachment_ref = media.find("ri:attachment")
        if not attachment_ref:
            continue
        filename = attachment_ref.get("ri:filename", "").strip()
        for att in attachments.get("results", []):
            if att['title'] == filename:
                full_url = f"{base_url}{att['_links']['download']}"
                output_path = os.path.join(attachments_dir, filename)
                if download_attachment(full_url, token, output_path):
                    rel_path = os.path.relpath(output_path, output_dir)
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif')):
                        md_link = f"![{filename}]({rel_path})"
                    else:
                        md_link = f"[{filename}]({rel_path})"
                    media.insert_after(md_link)
                    media.decompose()

    if fallback_images:
        fallback_section = BeautifulSoup("", "html.parser")
        fallback_section.append(fallback_section.new_tag("hr"))
        header = fallback_section.new_tag("h3")
        header.string = "Unplaced Diagrams"
        fallback_section.append(header)
        for title, rel_path in fallback_images:
            tag = fallback_section.new_tag("p")
            tag.string = f"![{title}]({rel_path})"
            fallback_section.append(tag)
        soup.append(fallback_section)

    return str(soup)

def post_process_markdown(content):
    return content.replace(r"\\_", "_")

def fetch_page(base_url, token, page_id):
    url = f"{base_url}/rest/api/content/{page_id}?expand=body.storage,title"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def process_page(page_id, base_url, token, output_dir):
    page = fetch_page(base_url, token, page_id)
    if not page:
        log_message(f"❌ Failed to fetch page {page_id}")
        return

    title = page['title']
    html_content = page['body']['storage']['value']
    log_message(f"📄 Processing page: {title} ({page_id})")

    content_with_links = extract_diagrams_and_media(html_content, base_url, token, page_id, output_dir)
    markdown = markdownify.markdownify(content_with_links, heading_style="ATX")
    markdown = post_process_markdown(markdown)

    filename = sanitize_filename(title) + f"_{page_id}.md"
    filepath = os.path.join(output_dir, filename)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(markdown)
    log_message(f"✅ Saved: {filepath}")

def load_yaml(path):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def fetch_all_pages(base_url, token, space_key, limit=50):
    pages = []
    start = 0
    while True:
        url = urljoin(base_url, "/rest/api/content")
        params = {
            "spaceKey": space_key,
            "limit": limit,
            "start": start,
            "expand": "ancestors,title"
        }
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        pages.extend(data.get("results", []))
        if not data.get("_links", {}).get("next"):
            break
        start += limit
    return pages

def build_tree(pages):
    tree = defaultdict(list)
    page_lookup = {}
    parent_lookup = {}
    for page in pages:
        page_id = int(page['id'])
        title = page['title']
        parent_id = int(page['ancestors'][-1]['id']) if page.get('ancestors') else None
        tree[parent_id].append(page_id)
        parent_lookup[page_id] = parent_id
        page_lookup[page_id] = title
    return tree, page_lookup, parent_lookup

def collect_descendants(tree, root_id):
    result = set()
    stack = [root_id]
    while stack:
        node = stack.pop()
        result.add(node)
        stack.extend(tree.get(node, []))
    return result

def determine_final_pages(all_page_ids, includes, excludes, tree, explicit=False):
    included_ids = set()

    # First process parent_pages: parent and all descendants
    for entry in includes.get('parent_pages', []):
        included_ids.update(collect_descendants(tree, entry['id']))

    # Then process individual pages: only the page itself
    for entry in includes.get('pages', []):
        included_ids.add(entry['id'])

    excluded_ids = set()
    for entry in excludes.get('parent_pages', []) + excludes.get('pages', []):
        excluded_ids.update(collect_descendants(tree, entry['id']))

    if explicit:
        final_ids = included_ids
    else:
        final_ids = (all_page_ids - excluded_ids) | included_ids

    return final_ids, included_ids, excluded_ids

def write_dry_run_log(output_path, summary_lines):
    with open(output_path, 'w') as f:
        for line in summary_lines:
            f.write(line + '\n')

def print_hierarchy(tree, page_lookup, parent_lookup, current_id, final_ids, included_ids, excluded_ids, depth=0, lines=None):
    lines = lines if lines is not None else []
    prefix = "  " * depth
    title = page_lookup.get(current_id, '?')
    if current_id in included_ids & excluded_ids:
        status = "♻️"
    elif current_id in excluded_ids:
        status = "🚫"
    elif current_id in final_ids:
        status = "✅"
    else:
        status = "➖"
    lines.append(f"{prefix}{status} {current_id}: {title}")
    for child_id in sorted(tree.get(current_id, [])):
        print_hierarchy(tree, page_lookup, parent_lookup, child_id, final_ids, included_ids, excluded_ids, depth + 1, lines)
    return lines

def main():
    global logger
    parser = argparse.ArgumentParser(description="Export Confluence pages to Markdown")
    parser.add_argument('--main-config', default='config/main.yaml', help='Path to main YAML config file')
    parser.add_argument('--spaces-dir', default='data/config/spaces', help='Path to directory containing space configs')
    parser.add_argument('--spaces', help='Optional comma-separated list of space keys to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    parser.add_argument('--dry-run-output', help='Write dry-run output to this file')
    parser.add_argument('--log-file', help='Optional log file to capture results and warnings')
    parser.add_argument('--explicit', action='store_true', help='Force explicit mode for all spaces')
    args = parser.parse_args()

    if args.log_file:
        logger = args.log_file
        os.makedirs(os.path.dirname(logger), exist_ok=True)
        if os.path.exists(logger):
            os.remove(logger)

    main_config = load_yaml(args.main_config)
    base_url = main_config['confluence_base_url']
    token = main_config['confluence_bearer_token']
    page_limit = main_config.get('page_limit', 50)
    output_dir = main_config['output_dir']

    dry_run_summary = []

    space_filters = args.spaces.split(',') if args.spaces else None

    for filename in os.listdir(args.spaces_dir):
        if not filename.endswith('.yaml'):
            continue
        space_key_candidate = filename[:-5]
        if space_filters and space_key_candidate not in space_filters:
            continue

        path = os.path.join(args.spaces_dir, filename)
        log_message(f"📘 Reading space config from: {path}")

        config = load_yaml(path)
        space_key = config['space_key']
        includes = config.get('includes', {})
        excludes = config.get('excludes', {})

        # New: Determine if explicit mode should be on for this space
        config_explicit_mode = config.get('explicit-mode', False)
        if args.explicit:
            space_explicit_mode = True
        else:
            space_explicit_mode = config_explicit_mode

        log_message(f"🔍 Processing space: {space_key} (Explicit mode: {space_explicit_mode})")
        dry_run_summary.append(f"# Space: {space_key}")

        pages = fetch_all_pages(base_url, token, space_key, page_limit)
        log_message(f"📄 Found {len(pages)} pages in space '{space_key}'")

        tree, page_lookup, parent_lookup = build_tree(pages)
        all_page_ids = set(page_lookup.keys()) if not space_explicit_mode else set()

        final_ids, included_ids, excluded_ids = determine_final_pages(
            all_page_ids, includes, excludes, tree, explicit=space_explicit_mode
        )
        log_message(f"✅ Final page count to export: {len(final_ids)}")

        root_ids = [pid for pid in page_lookup if parent_lookup.get(pid) not in page_lookup]
        dry_run_summary.append("📂 Page Hierarchy:")
        for root_id in sorted(root_ids):
            print_hierarchy(tree, page_lookup, parent_lookup, root_id, final_ids, included_ids, excluded_ids, 0, dry_run_summary)

        if not args.dry_run:
            log_message("")
            log_message("🚀 Exporting Markdown for included pages...")
            space_output_dir = os.path.join(output_dir, space_key)
            os.makedirs(space_output_dir, exist_ok=True)
            for pid in sorted(final_ids):
                title = page_lookup.get(pid)
                if title:
                    process_page(pid, base_url, token, space_output_dir)

    if args.dry_run:
        log_message("")
        log_message("--- Dry Run Summary ---")
        for line in dry_run_summary:
            log_message(line)

    if args.dry_run_output:
        write_dry_run_log(args.dry_run_output, dry_run_summary)
        log_message("")
        log_message(f"📄 Dry-run summary written to {args.dry_run_output}")

if __name__ == '__main__':
    main()