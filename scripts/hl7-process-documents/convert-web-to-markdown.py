import os
import time
import yaml
import requests
import shutil
import re
import html
from urllib.parse import urljoin, urlparse, unquote
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup
from markdownify import markdownify as md

# --- CONFIGURE FILENAME SANITIZATION ---
INVALID_FILENAME_CHARS = re.compile(r'[^A-Za-z0-9_.+()-]+')

def sanitize_filename(title):
    title = unquote(title)
    title = html.unescape(title)
    title = title.replace(" ", "+")
    title = INVALID_FILENAME_CHARS.sub("", title)
    title = re.sub(r"^[.-]+|[.-]+$", "", title)
    title = re.sub(r"_+$", "", title)
    return title

# --- SELENIUM SETUP ---
def init_driver():
    chrome_options = Options()
    chrome_options.add_argument('--headless')
    chrome_options.add_argument('--no-sandbox')
    chrome_options.add_argument('--disable-dev-shm-usage')
    driver = webdriver.Chrome(options=chrome_options)
    return driver

# --- FETCH PAGE CONTENT ---
def fetch_page_content(url, driver):
    print(f"Fetching: {url}")
    driver.get(url)
    time.sleep(2)  # Wait for dynamic content to load
    return driver.page_source

# --- DOWNLOAD IMAGES ---
def download_image(img_url, base_url, attachments_dir):
    full_url = urljoin(base_url, img_url)
    print(f"Downloading image: {full_url}")
    try:
        response = requests.get(full_url, stream=True)
        response.raise_for_status()
        parsed = urlparse(full_url)
        filename = os.path.basename(parsed.path)
        local_path = os.path.join(attachments_dir, filename)
        with open(local_path, 'wb') as out_file:
            shutil.copyfileobj(response.raw, out_file)
        return os.path.relpath(local_path, attachments_dir)
    except Exception as e:
        print(f"Warning: Failed to download image {full_url} ({e})")
        return img_url  # fallback

# --- PROCESS HTML TO MARKDOWN ---
def process_html_to_markdown(html, base_url, attachments_dir):
    soup = BeautifulSoup(html, 'html.parser')

    # Download images and replace src
    for img in soup.find_all('img'):
        src = img.get('src')
        if src:
            local_img_path = download_image(src, base_url, attachments_dir)
            img['src'] = os.path.join('attachments', local_img_path)

    # Convert cleaned HTML to Markdown
    markdown = md(str(soup), heading_style="ATX")
    return markdown, soup

# --- EXTRACT TITLE FOR FILENAME ---
def extract_title(soup):
    title_tag = soup.find('title')
    if title_tag and title_tag.text.strip():
        return title_tag.text.strip()
    h1_tag = soup.find('h1')
    if h1_tag and h1_tag.text.strip():
        return h1_tag.text.strip()
    return "untitled"

# --- MAIN PROCESS ---
def main(config_file, output_dir):
    os.makedirs(output_dir, exist_ok=True)
    attachments_dir = os.path.join(output_dir, 'attachments')
    os.makedirs(attachments_dir, exist_ok=True)

    with open(config_file, 'r') as f:
        config = yaml.safe_load(f)

    driver = init_driver()

    for item in config.get('pages', []):
        url = item.get('url')

        if not url:
            print("Skipping entry with missing URL.")
            continue

        html = fetch_page_content(url, driver)
        markdown, soup = process_html_to_markdown(html, url, attachments_dir)

        title = extract_title(soup)
        filename = sanitize_filename(title) + '.md'

        output_path = os.path.join(output_dir, filename)
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(markdown)

        print(f"✅ Saved markdown to {output_path}")

    driver.quit()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Fetch URLs and convert to Markdown.")
    parser.add_argument('-c', '--config', required=True, help="Path to YAML config file.")
    parser.add_argument('-o', '--output', required=True, help="Path to output folder.")
    args = parser.parse_args()

    main(args.config, args.output)
