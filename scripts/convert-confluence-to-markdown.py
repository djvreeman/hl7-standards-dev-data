import os
import re
import json
import base64
import subprocess
import requests
from bs4 import BeautifulSoup
import markdownify

# Load configuration from config.json
with open("data/config/config.json", "r") as config_file:
    config = json.load(config_file)

BASE_URL = config["base_url"]
BEARER_TOKEN = config["confluence_bearer_token"]
PAGE_IDS = config["page_ids"]
OUTPUT_DIR = config["output_dir"]

# Ensure the output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

def get_page_content(page_id):
    """Fetch page content using Bearer token authentication."""
    url = f"{BASE_URL}/rest/api/content/{page_id}"
    params = {"expand": "body.storage"}
    headers = {
        "Authorization": f"Bearer {BEARER_TOKEN}"
    }

    response = requests.get(url, params=params, headers=headers)
    if response.status_code == 200:
        return response.json()
    else:
        print(f"Failed to fetch page {page_id}: {response.status_code} - {response.text}")
        return None

def extract_drawio_macros(html_content):
    """Extract draw.io macros from HTML content."""
    # Updated pattern to specifically target 'ac:name="drawio"'
    macro_pattern = r'<ac:structured-macro[^>]*ac:name="drawio"[^>]*>.*?</ac:structured-macro>'
    macros = re.findall(macro_pattern, html_content, re.DOTALL)
    return macros

def decode_drawio_macro(macro):
    """Extract and decode the diagram content from the macro."""
    diagram_pattern = r'<ac:plain-text-body><!\[CDATA\[([\s\S]*?)\]\]></ac:plain-text-body>'
    match = re.search(diagram_pattern, macro)
    if match:
        diagram_data = match.group(1)
        try:
            decoded_data = base64.b64decode(diagram_data).decode('utf-8')
            return decoded_data
        except Exception as e:
            print(f"Failed to decode diagram data: {e}")
            return diagram_data  # Return raw if not base64
    return None

def save_drawio_diagram_as_png(drawio_content, output_path):
    """Save Draw.io content as PNG using the full path to Draw.io CLI."""
    drawio_cli_path = "/Applications/draw.io.app/Contents/MacOS/draw.io"
    temp_drawio_file = output_path.replace(".png", ".drawio")
    
    with open(temp_drawio_file, "w", encoding="utf-8") as file:
        file.write(drawio_content)
    
    try:
        subprocess.run(
            [drawio_cli_path, "-x", "-f", "png", "-o", output_path, temp_drawio_file],
            check=True
        )
        print(f"Diagram saved as PNG: {output_path}")
    finally:
        os.remove(temp_drawio_file)

def html_to_markdown(html_content, diagrams, page_id):
    """Convert HTML to Markdown and embed diagrams."""
    markdown_content = markdownify.markdownify(html_content, heading_style="ATX")
    for i, diagram_path in enumerate(diagrams, start=1):
        markdown_content += f"\n\n![Diagram {i}](./{os.path.basename(diagram_path)})\n"
    markdown_file = os.path.join(OUTPUT_DIR, f"page_{page_id}.md")
    with open(markdown_file, "w", encoding="utf-8") as file:
        file.write(markdown_content)
    print(f"Markdown file created: {markdown_file}")

def main():
    for page_id in PAGE_IDS:
        page_data = get_page_content(page_id)
        if page_data:
            html_content = page_data["body"]["storage"]["value"]
            drawio_macros = extract_drawio_macros(html_content)
            diagrams = []

            print(f"Found {len(drawio_macros)} Draw.io macros in page {page_id}.")
            for i, macro in enumerate(drawio_macros, start=1):
                diagram_content = decode_drawio_macro(macro)
                if diagram_content:
                    png_file = os.path.join(OUTPUT_DIR, f"page_{page_id}_diagram_{i}.png")
                    save_drawio_diagram_as_png(diagram_content, png_file)
                    diagrams.append(png_file)

            html_to_markdown(html_content, diagrams, page_id)

if __name__ == "__main__":
    main()