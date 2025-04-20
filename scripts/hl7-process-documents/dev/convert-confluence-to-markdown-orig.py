import os
import json
import re
import requests
from bs4 import BeautifulSoup
import markdownify

# Load configuration
with open("data/config/config.json", "r") as config_file:
    config = json.load(config_file)

BASE_URL = config["confluence_base_url"]
BEARER_TOKEN = config["confluence_bearer_token"]
PAGE_IDS = config["confluence_page_ids"]
OUTPUT_DIR = config["output_dir"]

def sanitize_filename(title):
    """Sanitize the title to create a filesystem-safe filename."""
    # Replace invalid characters with an underscore
    safe_title = re.sub(r'[\\/*?:"<>|]', '_', title)
    return safe_title

def get_page_content(page_id):
    """Fetch page content using Bearer token authentication."""
    url = f"{BASE_URL}/rest/api/content/{page_id}"
    params = {"expand": "body.storage"}
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}"
    }

    response = requests.get(url, params=params, headers=headers)
    
    if response.status_code == 200:
        if "Human Verification" in response.text or "captcha-container" in response.text:
            print(f"CAPTCHA detected for page {page_id}. Manual intervention required.")
            return None
        return response.json()
    else:
        print(f"Failed to fetch page {page_id}: {response.status_code} - {response.text}")
        return None

def get_page_attachments(page_id):
    """Fetch attachments for a Confluence page."""
    url = f"{BASE_URL}/rest/api/content/{page_id}/child/attachment"
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}"
    }

    response = requests.get(url, headers=headers)
    
    if response.status_code == 200:
        if "Human Verification" in response.text or "captcha-container" in response.text:
            print(f"CAPTCHA detected while fetching attachments for page {page_id}. Manual intervention required.")
            return None
        return response.json()
    else:
        print(f"Failed to fetch attachments for page {page_id}: {response.status_code} - {response.text}")
        return None

def download_attachment(attachment_url, output_path):
    """Download an attachment to the specified path."""
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}"
    }
    response = requests.get(attachment_url, headers=headers, stream=True)
    
    if response.status_code == 200:
        if "Human Verification" in response.text or "captcha-container" in response.text:
            print(f"CAPTCHA detected during download from {attachment_url}. Manual intervention required.")
            return False

        with open(output_path, 'wb') as file:
            for chunk in response.iter_content(chunk_size=8192):
                file.write(chunk)
        if os.path.exists(output_path):
            print(f"File successfully downloaded: {output_path}")
            return True
        else:
            print(f"File download failed: {output_path}")
            return False
    else:
        print(f"Failed to download attachment: {response.status_code} - {response.text}")
        return False

def extract_and_export_diagrams(page_content, page_id, markdown_file_path):
    """Extract Draw.io diagrams or exported images and replace them inline in the Markdown content."""
    soup = BeautifulSoup(page_content, "html.parser")
    diagrams = soup.find_all("ac:structured-macro", {"ac:name": "drawio"})

    if not diagrams:
        print(f"No Draw.io diagrams found in page {page_id}.")
        return page_content, []

    print(f"Found {len(diagrams)} Draw.io diagrams in page {page_id}.")
    attachments = get_page_attachments(page_id)

    if not attachments:
        print(f"Skipping diagram extraction for page {page_id} due to attachment fetch failure.")
        return page_content, []

    markdown_dir = os.path.dirname(markdown_file_path)
    images_dir = os.path.join(markdown_dir, "images")
    os.makedirs(images_dir, exist_ok=True)

    for diagram in diagrams:
        diagram_name_param = diagram.find("ac:parameter", {"ac:name": "diagramName"})
        if not diagram_name_param:
            continue

        diagram_name = diagram_name_param.text.strip()
        print(f"Processing diagram: {diagram_name}")

        # Find the matching attachment
        matching_attachment = None
        for attachment in attachments.get("results", []):
            attachment_title = attachment["title"]
            if attachment_title.startswith(diagram_name):  # Match based on `diagramName`
                matching_attachment = attachment
                break

        if matching_attachment:
            attachment_url = matching_attachment["_links"]["download"]
            full_url = f"{BASE_URL}{attachment_url}"
            output_path = os.path.join(images_dir, matching_attachment["title"])

            if download_attachment(full_url, output_path):
                print(f"Downloaded: {output_path}")
                relative_path = os.path.relpath(output_path, os.path.dirname(markdown_file_path))
                markdown_link = f"![{matching_attachment['title']}]({relative_path})"

                # Replace the macro in the tree with the Markdown image link
                diagram.replace_with(markdown_link)
        else:
            print(f"No matching attachment found for diagram: {diagram_name}")

    return str(soup), []

def process_pages():
    """Process all pages specified in the configuration."""
    for page_id in PAGE_IDS:
        page = get_page_content(page_id)
        if page:
            title = page["title"]
            sanitized_title = sanitize_filename(title)  # Sanitize the title
            content = page["body"]["storage"]["value"]
            
            # Process Draw.io diagrams and update the content inline
            updated_content, _ = extract_and_export_diagrams(content, page_id, os.path.join(OUTPUT_DIR, f"{sanitized_title}.md"))
            
            # Convert updated HTML content to Markdown
            markdown_content = markdownify.markdownify(updated_content, heading_style="ATX")
            output_path = os.path.join(OUTPUT_DIR, f"{sanitized_title}.md")

            # Save Markdown file
            with open(output_path, "w") as md_file:
                md_file.write(markdown_content)
            print(f"Converted page {title} to Markdown.")

if __name__ == "__main__":
    process_pages()