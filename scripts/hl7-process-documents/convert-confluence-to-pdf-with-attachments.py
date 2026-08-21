# convert-confluence-to-pdf-with-attachments.py
#
# Usage:
#   python convert-confluence-to-pdf-with-attachments.py \
#       --main-config config/main.yaml \
#       --spaces-dir data/config/spaces \
#       [--spaces FHIR,HE] \
#       [--dry-run] \
#       [--dry-run-output reports/summary.txt] \
#       [--log-file logs/export.log] \
#       [--explicit]
#
# Description:
#   This script processes Confluence spaces based on YAML config files and converts
#   pages to PDF format with intelligent attachment handling. Each space has a config
#   in data/config/spaces/<space_key>.yaml that defines which pages or parent pages
#   to include or exclude. Includes override excludes.
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
#   ATTACHMENT HANDLING:
#   - Each page gets its own folder with the PDF and its attachments
#   - Directory structure mirrors Confluence page hierarchy (parent/child relationships)
#   - An "Attachments" section is added to each page with relative links
#   - Attachments are categorized by type (images, documents, etc.)
#   - Includes metadata like file size and download date
#   - Uses relative paths for portability and sharing
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
from urllib.parse import urljoin, unquote
from collections import defaultdict
import datetime
import mimetypes
from pathlib import Path

# PDF conversion libraries
try:
    from weasyprint import HTML, CSS
    WEASYPRINT_AVAILABLE = True
except ImportError:
    WEASYPRINT_AVAILABLE = False
    print("Warning: weasyprint not available, falling back to pdfkit")

try:
    import pdfkit
    # Test if wkhtmltopdf is available
    try:
        pdfkit.from_string('<html><body>test</body></html>', '/dev/null')
        PDFKIT_AVAILABLE = True
    except Exception as e:
        PDFKIT_AVAILABLE = False
        print("Warning: pdfkit available but wkhtmltopdf not found")
        print("Note: wkhtmltopdf is discontinued. WeasyPrint is recommended for PDF conversion.")
except ImportError:
    PDFKIT_AVAILABLE = False
    print("Warning: pdfkit not available")

if not WEASYPRINT_AVAILABLE and not PDFKIT_AVAILABLE:
    print("Error: Neither weasyprint nor pdfkit is available. Please install dependencies:")
    print("  Run: ./install_pdf_dependencies.sh")
    print("  Or install manually:")
    print("    pip install weasyprint pdfkit")
    print("    brew install cairo pango gdk-pixbuf libffi wkhtmltopdf (macOS)")
    print("    apt-get install libcairo2 libpango-1.0-0 libgdk-pixbuf2.0-0 libffi-dev wkhtmltopdf (Ubuntu)")
    exit(1)

INVALID_FILENAME_CHARS = re.compile(r'[^a-zA-Z0-9+_.-]')
logger = None

def create_relative_path(from_dir, to_file):
    """Create a relative path from one directory to a file"""
    return os.path.relpath(to_file, from_dir)

def check_memory_usage():
    """Check current memory usage and log it"""
    try:
        import psutil
        process = psutil.Process()
        memory_info = process.memory_info()
        memory_mb = memory_info.rss / 1024 / 1024
        log_message(f"📊 Memory usage: {memory_mb:.1f} MB")
        return memory_mb
    except ImportError:
        return None

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

def get_file_size(file_path):
    """Get file size in human readable format"""
    size = os.path.getsize(file_path)
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

def get_file_type(filename):
    """Categorize file by type"""
    ext = Path(filename).suffix.lower()
    if ext in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg', '.webp']:
        return 'Image'
    elif ext in ['.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
        return 'Document'
    elif ext in ['.zip', '.rar', '.7z', '.tar', '.gz']:
        return 'Archive'
    elif ext in ['.mp4', '.avi', '.mov', '.wmv', '.flv']:
        return 'Video'
    elif ext in ['.mp3', '.wav', '.flac', '.aac']:
        return 'Audio'
    else:
        return 'Other'

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

def download_all_attachments(base_url, token, page_id, shared_attachments_dir):
    """Download all attachments for a page and return metadata"""
    attachments = get_attachments(base_url, token, page_id)
    if not attachments:
        return []
    
    downloaded_attachments = []
    for att in attachments.get("results", []):
        filename = att['title']
        full_url = f"{base_url}{att['_links']['download']}"
        output_path = os.path.join(shared_attachments_dir, filename)
        
        # Check if file already exists to avoid re-downloading
        if not os.path.exists(output_path):
            if download_attachment(full_url, token, output_path):
                log_message(f"📎 Downloaded attachment: {filename}")
            else:
                log_message(f"❌ Failed to download attachment: {filename}")
                continue
        else:
            log_message(f"📎 Attachment already exists: {filename}")
        
        # Get file metadata
        file_size = get_file_size(output_path)
        file_type = get_file_type(filename)
        download_date = datetime.datetime.fromtimestamp(os.path.getmtime(output_path)).strftime('%Y-%m-%d %H:%M:%S')
        
        downloaded_attachments.append({
            'filename': filename,
            'file_path': output_path,
            'file_size': file_size,
            'file_type': file_type,
            'download_date': download_date,
            'original_id': att.get('id'),
            'original_created': att.get('created'),
            'original_author': att.get('author', {}).get('displayName', 'Unknown')
        })
    
    return downloaded_attachments

def create_attachments_section_html(attachments, page_dir, page_attachments_dir):
    """Create HTML section for attachments with relative links"""
    if not attachments:
        return ""
    
    # Group attachments by type
    attachments_by_type = defaultdict(list)
    for att in attachments:
        attachments_by_type[att['file_type']].append(att)
    
    html_content = """
    <div class="attachments-section">
        <h2>📎 Attachments</h2>
        <p>This page contains the following attachments:</p>
    """
    
    for file_type, type_attachments in sorted(attachments_by_type.items()):
        html_content += f'<h3>{file_type}s</h3><ul>'
        
        for att in sorted(type_attachments, key=lambda x: x['filename']):
            # Create relative path from page directory to attachment
            rel_path = create_relative_path(page_dir, att['file_path'])
            
            html_content += f"""
            <li>
                <a href="{rel_path}" target="_blank">{att['filename']}</a>
                <br>
                <small>
                    📏 Size: {att['file_size']} | 
                    📅 Downloaded: {att['download_date']} | 
                    👤 Author: {att['original_author']}
                </small>
            </li>
            """
        
        html_content += '</ul>'
    
    html_content += '</div>'
    return html_content

def extract_diagrams_and_media(content_html, base_url, token, page_id, page_dir, page_attachments_dir):
    """Extract and replace diagrams and media with local file references"""
    soup = BeautifulSoup(content_html, "html.parser")
    diagrams = soup.find_all("ac:structured-macro", {"ac:name": "drawio"})
    media_links = soup.find_all("ac:image")

    attachments = get_attachments(base_url, token, page_id)
    if not attachments:
        return str(soup)

    fallback_images = []
    for diagram in diagrams:
        param = diagram.find("ac:parameter", {"ac:name": "diagramName"})
        if not param:
            continue
        diagram_name = param.text.strip()
        for att in attachments.get("results", []):
            if att["title"].startswith(diagram_name):
                full_url = f"{base_url}{att['_links']['download']}"
                # Download to shared directory first
                shared_output_path = os.path.join(os.path.dirname(page_attachments_dir), "..", "shared_attachments", att['title'])
                if download_attachment(full_url, token, shared_output_path):
                    # Copy to page-specific directory for relative linking
                    page_attachment_path = os.path.join(page_attachments_dir, att['title'])
                    if not os.path.exists(page_attachment_path):
                        import shutil
                        shutil.copy2(shared_output_path, page_attachment_path)
                    
                    rel_path = create_relative_path(page_dir, page_attachment_path)
                    if diagram.parent:
                        # Create img tag for diagram
                        img_tag = soup.new_tag("img", src=rel_path, alt=att['title'])
                        img_tag['style'] = "max-width: 100%; height: auto;"
                        diagram.replace_with(img_tag)
                    else:
                        log_message(f"⚠️ Warning: Diagram {att['title']} not attached to tree, adding to fallback.")
                        fallback_images.append((att['title'], rel_path))

    for media in media_links:
        attachment_ref = media.find("ri:attachment")
        if not attachment_ref:
            continue
        filename = attachment_ref.get("ri:filename", "").strip()
        for att in attachments.get("results", []):
            if att['title'] == filename:
                full_url = f"{base_url}{att['_links']['download']}"
                # Download to shared directory first
                shared_output_path = os.path.join(os.path.dirname(page_attachments_dir), "..", "shared_attachments", filename)
                if download_attachment(full_url, token, shared_output_path):
                    # Copy to page-specific directory for relative linking
                    page_attachment_path = os.path.join(page_attachments_dir, filename)
                    if not os.path.exists(page_attachment_path):
                        import shutil
                        shutil.copy2(shared_output_path, page_attachment_path)
                    
                    rel_path = create_relative_path(page_dir, page_attachment_path)
                    if filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg')):
                        img_tag = soup.new_tag("img", src=rel_path, alt=filename)
                        img_tag['style'] = "max-width: 100%; height: auto;"
                        media.replace_with(img_tag)
                    else:
                        link_tag = soup.new_tag("a", href=rel_path)
                        link_tag.string = filename
                        media.replace_with(link_tag)

    if fallback_images:
        fallback_section = soup.new_tag("div", **{"class": "fallback-images"})
        fallback_section.append(soup.new_tag("hr"))
        header = soup.new_tag("h3")
        header.string = "📊 Diagrams and Media"
        fallback_section.append(header)
        for title, rel_path in fallback_images:
            if title.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.svg')):
                img_tag = soup.new_tag("img", src=rel_path, alt=title)
                img_tag['style'] = "max-width: 100%; height: auto;"
                fallback_section.append(img_tag)
            else:
                link_tag = soup.new_tag("a", href=rel_path)
                link_tag.string = title
                fallback_section.append(link_tag)
        soup.append(fallback_section)

    return str(soup)

def create_pdf_from_html(html_content, output_path, title, use_pdfkit_only=False):
    """Convert HTML content to PDF with robust memory management and fallbacks"""
    # Check content size and truncate if too large
    content_size = len(html_content.encode('utf-8'))
    max_content_size = 10 * 1024 * 1024  # 10MB limit
    
    if content_size > max_content_size:
        log_message(f"⚠️ HTML content too large ({content_size / 1024 / 1024:.1f}MB), truncating...")
        # Truncate content to prevent memory issues
        html_content = html_content[:max_content_size // 2] + "\n\n[Content truncated due to size]"
    
    # Add basic CSS styling
    css_content = """
    body { font-family: Arial, sans-serif; margin: 20px; line-height: 1.6; }
    h1, h2, h3, h4, h5, h6 { color: #333; }
    .attachments-section { margin-top: 30px; border-top: 2px solid #ccc; padding-top: 20px; }
    .attachments-section h2 { color: #666; }
    .attachments-section ul { list-style-type: none; padding-left: 0; }
    .attachments-section li { margin-bottom: 10px; padding: 5px; background-color: #f9f9f9; }
    .attachments-section a { color: #0066cc; text-decoration: none; }
    .attachments-section small { color: #666; }
    img { max-width: 100%; height: auto; }
    table { border-collapse: collapse; width: 100%; }
    th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
    th { background-color: #f2f2f2; }
    code { background-color: #f4f4f4; padding: 2px 4px; border-radius: 3px; }
    pre { background-color: #f4f4f4; padding: 10px; border-radius: 5px; overflow-x: auto; }
    """
    
    # Create complete HTML document
    full_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>{title}</title>
        <style>{css_content}</style>
    </head>
    <body>
        {html_content}
    </body>
    </html>
    """
    
    # Try WeasyPrint first with enhanced memory management (unless pdfkit-only is specified)
    if WEASYPRINT_AVAILABLE and not use_pdfkit_only:
        try:
            # Create a temporary HTML file to reduce memory usage
            import tempfile
            with tempfile.NamedTemporaryFile(mode='w', suffix='.html', delete=False, encoding='utf-8') as temp_html:
                temp_html.write(full_html)
                temp_html_path = temp_html.name
            
            # Use file-based approach instead of string-based
            html_obj = HTML(filename=temp_html_path)
            html_obj.write_pdf(output_path)
            
            # Clean up
            del html_obj
            os.unlink(temp_html_path)
            
            # Force garbage collection
            import gc
            gc.collect()
            
            return True
            
        except Exception as weasyprint_error:
            log_message(f"⚠️ WeasyPrint failed: {weasyprint_error}, trying pdfkit...")
            # Force garbage collection after WeasyPrint failure
            import gc
            gc.collect()
    
    # Fallback to pdfkit
    if PDFKIT_AVAILABLE:
        try:
            options = {
                'page-size': 'A4',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
                'encoding': "UTF-8",
                'no-outline': None,
                'quiet': ''
            }
            pdfkit.from_string(full_html, output_path, options=options)
            
            # Force garbage collection
            import gc
            gc.collect()
            
            return True
            
        except Exception as pdfkit_error:
            log_message(f"❌ pdfkit failed: {pdfkit_error}")
            if "wkhtmltopdf" in str(pdfkit_error).lower():
                log_message("💡 wkhtmltopdf is discontinued. WeasyPrint is recommended for PDF conversion.")
            import gc
            gc.collect()
            return False
    
    # Last resort: create a simple HTML file
    try:
        html_output_path = output_path.replace('.pdf', '.html')
        with open(html_output_path, 'w', encoding='utf-8') as f:
            f.write(full_html)
        log_message(f"⚠️ PDF conversion failed, saved as HTML: {html_output_path}")
        log_message(f"💡 You can open this HTML file in a browser and print to PDF manually")
        return False
    except Exception as html_error:
        log_message(f"❌ Failed to save even HTML: {html_error}")
        return False

def fetch_page(base_url, token, page_id):
    url = f"{base_url}/rest/api/content/{page_id}?expand=body.storage,title"
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        return response.json()
    return None

def process_page(page_id, base_url, token, output_dir, shared_attachments_dir, tree=None, page_lookup=None, parent_lookup=None, use_pdfkit_only=False):
    page = fetch_page(base_url, token, page_id)
    if not page:
        log_message(f"❌ Failed to fetch page {page_id}")
        return

    title = page['title']
    html_content = page['body']['storage']['value']
    log_message(f"📄 Processing page: {title} ({page_id})")

    # Create hierarchical directory structure
    if tree and page_lookup and parent_lookup:
        # Build the full path from root to this page
        path_components = []
        current_id = page_id
        
        # Walk up the tree to build the path
        while current_id in parent_lookup and parent_lookup[current_id] is not None:
            parent_id = parent_lookup[current_id]
            if parent_id in page_lookup:
                parent_title = page_lookup[parent_id]
                path_components.insert(0, sanitize_filename(parent_title) + f"_{parent_id}")
            current_id = parent_id
        
        # Add the current page
        path_components.append(sanitize_filename(title) + f"_{page_id}")
        
        # Create the full directory path
        page_dir = os.path.join(output_dir, *path_components)
    else:
        # Fallback to flat structure if tree info not available
        page_dir_name = sanitize_filename(title) + f"_{page_id}"
        page_dir = os.path.join(output_dir, page_dir_name)
    
    os.makedirs(page_dir, exist_ok=True)
    
    # Create attachments subdirectory for this page
    page_attachments_dir = os.path.join(page_dir, "attachments")
    os.makedirs(page_attachments_dir, exist_ok=True)

    # Download all attachments for this page to the shared directory first
    shared_attachments = download_all_attachments(base_url, token, page_id, shared_attachments_dir)
    
    # Copy attachments to page-specific directory for relative linking
    page_attachments = []
    for att in shared_attachments:
        # Copy from shared to page-specific directory
        page_attachment_path = os.path.join(page_attachments_dir, att['filename'])
        if not os.path.exists(page_attachment_path):
            import shutil
            shutil.copy2(att['file_path'], page_attachment_path)
            log_message(f"📋 Copied attachment to page directory: {att['filename']}")
        
        # Update the file path to point to the page-specific copy
        att['file_path'] = page_attachment_path
        page_attachments.append(att)
    
    # Process content and replace diagrams/media with page-specific paths
    content_with_links = extract_diagrams_and_media(html_content, base_url, token, page_id, page_dir, page_attachments_dir)
    
    # Add attachments section with relative paths from page directory
    attachments_section = create_attachments_section_html(page_attachments, page_dir, page_attachments_dir)
    content_with_links += attachments_section
    
    # Convert to PDF
    filename = sanitize_filename(title) + f"_{page_id}.pdf"
    filepath = os.path.join(page_dir, filename)
    
    try:
        # Check memory before PDF creation
        check_memory_usage()
        
        if create_pdf_from_html(content_with_links, filepath, title, use_pdfkit_only):
            log_message(f"✅ Saved PDF: {filepath}")
            if page_attachments:
                log_message(f"📎 Included {len(page_attachments)} attachments in page directory")
        else:
            log_message(f"❌ Failed to create PDF: {filepath}")
    except Exception as e:
        log_message(f"❌ Error processing page {page_id}: {e}")
    finally:
        # Force garbage collection after processing each page
        import gc
        gc.collect()
        
        # Check memory after cleanup
        check_memory_usage()

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
    parser = argparse.ArgumentParser(description="Export Confluence pages to PDF with intelligent attachment handling")
    parser.add_argument('--main-config', default='config/main.yaml', help='Path to main YAML config file')
    parser.add_argument('--spaces-dir', default='data/config/spaces', help='Path to directory containing space configs')
    parser.add_argument('--spaces', help='Optional comma-separated list of space keys to process')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be processed')
    parser.add_argument('--dry-run-output', help='Write dry-run output to this file')
    parser.add_argument('--log-file', help='Optional log file to capture results and warnings')
    parser.add_argument('--explicit', action='store_true', help='Force explicit mode for all spaces')
    parser.add_argument('--use-pdfkit-only', action='store_true', help='Force use of pdfkit instead of WeasyPrint')
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
            log_message("🚀 Exporting PDFs for included pages...")
            space_output_dir = os.path.join(output_dir, space_key)
            os.makedirs(space_output_dir, exist_ok=True)

            # Create a shared attachments directory for all spaces
            shared_attachments_dir = os.path.join(output_dir, "shared_attachments")
            os.makedirs(shared_attachments_dir, exist_ok=True)

            for pid in sorted(final_ids):
                title = page_lookup.get(pid)
                if title:
                    try:
                        process_page(pid, base_url, token, space_output_dir, shared_attachments_dir, tree, page_lookup, parent_lookup, args.use_pdfkit_only)
                    except Exception as e:
                        log_message(f"❌ Failed to process page {pid} ({title}): {e}")
                        # Continue with next page instead of crashing
                        continue

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