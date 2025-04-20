import os
import json
import re
import requests
from bs4 import BeautifulSoup
import markdownify

# Load configuration
with open("data/config/config.json", "r") as config_file:
    config = json.load(config_file)

PARENT_PAGE_IDS = config.get("confluence_parent_page_ids", [])
BASE_URL = config["confluence_base_url"]
BEARER_TOKEN = config["confluence_bearer_token"]
SPACE_KEYS = config.get("confluence_space_keys", [])
PAGE_IDS = config.get("confluence_page_ids", [])
OUTPUT_DIR = config["output_dir"]
PAGE_LIMIT = config.get("page_limit", 25)  # Default to 25 if not specified


def get_child_page_ids(parent_page_id):
    """
    Fetch child page IDs for a given parent page ID.
    """
    url = f"{BASE_URL}/rest/api/content/{parent_page_id}/child/page"
    headers = {"Authorization": f"Bearer {BEARER_TOKEN}"}
    params = {"limit": 100}  # Adjust as needed
    child_page_ids = []

    while url:
        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Error fetching child pages for parent {parent_page_id}: {response.text}")
            break

        data = response.json()
        child_page_ids.extend([page["id"] for page in data.get("results", [])])
        url = data.get("_links", {}).get("next")

    return child_page_ids


def sanitize_filename(filename):
    """
    Sanitize the filename by removing problematic characters
    and ensuring consistency with Markdown formatting.
    """
    # Replace spaces with underscores and remove backslashes
    filename = filename.replace(" ", "_").replace("\\", "")

    # Remove any characters that are not alphanumeric, underscores, periods, or hyphens
    filename = re.sub(r"[^a-zA-Z0-9_.-]", "", filename)

    # Ensure the filename does not start or end with a period or hyphen
    filename = re.sub(r"^[.-]+|[.-]+$", "", filename)

    # Remove any trailing underscores before appending extensions
    filename = re.sub(r"_+$", "", filename)

    return filename

def download_attachment(attachment_url, output_path):
    """Download an attachment to the specified path."""
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}"
    }
    response = requests.get(attachment_url, headers=headers, stream=True)

    if response.status_code == 200:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
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

def get_page_ids_from_space(space_key, limit=25):
    """Fetch all page IDs from a specific Confluence space with pagination."""
    url = f"{BASE_URL}/rest/api/content"
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}",
        "Accept": "application/json"
    }
    
    page_ids = []
    start = 0  # Starting index for pagination

    while True:
        params = {
            "spaceKey": space_key,
            "type": "page",
            "start": start,
            "limit": limit,
            "expand": "body.storage"
        }
        response = requests.get(url, headers=headers, params=params)
        
        if response.status_code == 200:
            data = response.json()
            for result in data.get("results", []):
                page_ids.append(result["id"])
            
            print(f"Fetched {len(data.get('results', []))} pages from space '{space_key}', start={start}.")
            if len(data.get("results", [])) < limit:
                break
            start += limit
        else:
            print(f"Error fetching pages from space '{space_key}': {response.status_code} - {response.text}")
            break
    
    return page_ids

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

def post_process_markdown(markdown_content):
    """
    Post-process Markdown content to remove escaped characters
    and ensure consistent formatting.
    """
    # Remove backslashes before underscores
    markdown_content = markdown_content.replace(r"\_", "_")

    return markdown_content

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
    
def extract_and_export_diagrams_and_attachments(page_content, page_id, markdown_file_path):
    """
    Extract Draw.io diagrams, media files (e.g., PNGs, JPGs), and other attachments (e.g., PDFs, Word docs),
    and replace them inline in the Markdown content.
    """
    soup = BeautifulSoup(page_content, "html.parser")
    diagrams = soup.find_all("ac:structured-macro", {"ac:name": "drawio"})
    media_links = soup.find_all("ac:image")  # Handles inline media files like PNGs and JPGs

    # Fetch all attachments for the page
    attachments = get_page_attachments(page_id)
    if not attachments:
        print(f"Skipping extraction for page {page_id} due to attachment fetch failure.")
        return page_content, []

    print(f"Found {len(diagrams)} Draw.io diagrams and {len(media_links)} media files in page {page_id}.")

    markdown_dir = os.path.dirname(markdown_file_path)
    attachments_dir = os.path.join(markdown_dir, "attachments")
    os.makedirs(attachments_dir, exist_ok=True)

    # Process Draw.io diagrams
    for diagram in diagrams:
        diagram_name_param = diagram.find("ac:parameter", {"ac:name": "diagramName"})
        if not diagram_name_param:
            continue

        diagram_name = diagram_name_param.text.strip()
        print(f"Processing diagram: {diagram_name}")

        # Find the matching attachment for the diagram
        matching_attachment = None
        for attachment in attachments.get("results", []):
            if attachment["title"].startswith(diagram_name):  # Match based on `diagramName`
                matching_attachment = attachment
                break

        if matching_attachment:
            attachment_url = matching_attachment["_links"]["download"]
            full_url = f"{BASE_URL}{attachment_url}"
            output_path = os.path.join(attachments_dir, matching_attachment["title"])

            if download_attachment(full_url, output_path):
                print(f"Downloaded diagram: {output_path}")
                relative_path = os.path.relpath(output_path, os.path.dirname(markdown_file_path))
                markdown_link = f"![{matching_attachment['title']}]({relative_path})"

                # Replace the macro in the tree with the Markdown image link
                diagram.replace_with(markdown_link)
        else:
            print(f"No matching attachment found for diagram: {diagram_name}")

    # Process other media files (e.g., PNGs, JPGs)
    for media in media_links:
        attachment_ref = media.find("ri:attachment")
        if not attachment_ref:
            print("No attachment reference found for media; skipping.")
            continue

        media_filename = attachment_ref.get("ri:filename", "").strip()
        print(f"Processing media file: {media_filename}")

        # Find the matching attachment for the media
        matching_attachment = None
        for attachment in attachments.get("results", []):
            if attachment["title"] == media_filename:
                matching_attachment = attachment
                break

        if matching_attachment:
            attachment_url = matching_attachment["_links"]["download"]
            full_url = f"{BASE_URL}{attachment_url}"
            output_path = os.path.join(attachments_dir, media_filename)

            if download_attachment(full_url, output_path):
                print(f"Downloaded media file: {output_path}")
                relative_path = os.path.relpath(output_path, os.path.dirname(markdown_file_path))
                # Check if the file is an image based on its extension
                if media_filename.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                    markdown_link = f"![{media_filename}]({relative_path})"
                else:
                    markdown_link = f"[{media_filename}]({relative_path})"

                # Replace the media element with the appropriate Markdown link
                media.insert_after(markdown_link)
                media.decompose()
        else:
            print(f"No matching attachment found for media file: {media_filename}")

    # Process other attachments (e.g., PDFs, Word documents)
    for attachment in attachments.get("results", []):
        file_title = attachment["title"]
        file_url = f"{BASE_URL}{attachment['_links']['download']}"
        output_path = os.path.join(attachments_dir, file_title)

        if download_attachment(file_url, output_path):
            print(f"Downloaded attachment: {output_path}")
            relative_path = os.path.relpath(output_path, os.path.dirname(markdown_file_path))
            # Check if the file is an image or a document
            if file_title.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.bmp')):
                markdown_link = f"![{file_title}]({relative_path})"
            else:
                markdown_link = f"[{file_title}]({relative_path})"

            # Add a link to the attachment at the end of the content
            new_link = soup.new_tag("p")
            new_link.string = markdown_link
            soup.append(new_link)

    return str(soup), []

def process_parent_pages():
    """Process parent pages and their child pages."""
    parent_output_dir = os.path.join(OUTPUT_DIR, "parent_pages")
    os.makedirs(parent_output_dir, exist_ok=True)

    for parent_id in PARENT_PAGE_IDS:
        print(f"Processing parent page ID: {parent_id}")
        parent_page_output_dir = os.path.join(parent_output_dir, f"parent_{sanitize_filename(parent_id)}")
        os.makedirs(parent_page_output_dir, exist_ok=True)

        # Process the parent page
        page = get_page_content(parent_id)
        if page:
            process_single_page(page, parent_page_output_dir)

        # Process child pages
        child_page_ids = get_child_page_ids(parent_id)
        print(f"Found {len(child_page_ids)} child pages for parent page ID: {parent_id}")

        for child_id in child_page_ids:
            child_page = get_page_content(child_id)
            if child_page:
                process_single_page(child_page, parent_page_output_dir)

def process_single_page(page, output_dir):
    """Process a single page and save as Markdown."""
    title = page["title"]
    sanitized_title = sanitize_filename(title)
    content = page["body"]["storage"]["value"]

    # Process Draw.io diagrams and update the content inline
    images_dir = os.path.join(output_dir, "images")
    updated_content, _ = extract_and_export_diagrams_and_attachments(content, page["id"], images_dir)

    # Convert updated HTML content to Markdown
    markdown_content = markdownify.markdownify(updated_content, heading_style="ATX")
    
    # Post-process Markdown content to remove escaped characters
    markdown_content = post_process_markdown(markdown_content)

    output_path = os.path.join(output_dir, f"{sanitized_title}.md")

    # Ensure no duplicate files
    if os.path.exists(output_path):
        os.remove(output_path)

    # Save Markdown file
    with open(output_path, "w") as md_file:
        md_file.write(markdown_content)
    print(f"Converted page {title} to Markdown in directory: {output_dir}")

def process_pages():
    """Process all pages specified in the configuration."""
    # Process space pages
    for space_key in SPACE_KEYS:
        print(f"Processing space: {space_key}")
        space_output_dir = os.path.join(OUTPUT_DIR, sanitize_filename(space_key))
        os.makedirs(space_output_dir, exist_ok=True)

        space_page_ids = get_page_ids_from_space(space_key, limit=PAGE_LIMIT)
        print(f"Found {len(space_page_ids)} pages in space '{space_key}'.")

        for page_id in space_page_ids:
            page = get_page_content(page_id)
            if page:
                process_single_page(page, space_output_dir)

    # Process individually specified pages
    if PAGE_IDS:
        misc_output_dir = os.path.join(OUTPUT_DIR, "miscellaneous")
        os.makedirs(misc_output_dir, exist_ok=True)

        for page_id in PAGE_IDS:
            page = get_page_content(page_id)
            if page:
                process_single_page(page, misc_output_dir)

    # Process parent pages and their children
    if PARENT_PAGE_IDS:
        process_parent_pages()

if __name__ == "__main__":
    process_pages()