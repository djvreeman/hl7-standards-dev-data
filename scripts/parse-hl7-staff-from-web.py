import os
import argparse
import csv
import time
from datetime import datetime

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from bs4 import BeautifulSoup

def parse_staff(html):
    soup = BeautifulSoup(html, "html.parser")
    directory_members = soup.find_all("div", class_="directory-member")

    staff_list = []
    for member in directory_members:
        anchor = member.find("a")
        if anchor:
            anchor_text = anchor.get_text(separator="|", strip=True)
            parts = anchor_text.split("|", maxsplit=1)
            if len(parts) == 2:
                title = parts[0].strip()
                name = parts[1].strip()
                staff_list.append({"name": name, "title": title})
    return staff_list

def main():
    parser = argparse.ArgumentParser(description="Extract HL7 staff names and titles from the website.")
    parser.add_argument(
        "url",
        nargs="?",
        default="https://www.hl7.org/about/hl7staff.cfm",
        help="URL of the HL7 staff page (default: https://www.hl7.org/about/hl7staff.cfm)"
    )
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="data/working/staff",
        help="Output directory (default: data/working/staff)"
    )
    args = parser.parse_args()
    
    # Configure Chrome in headless mode
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")

    # Create the WebDriver (assuming 'chromedriver' is on your PATH)
    driver = webdriver.Chrome(options=chrome_options)

    try:
        # Navigate to the staff page
        driver.get(args.url)

        # Wait a bit for the page to load fully, if needed
        time.sleep(5)  # or use Selenium's wait conditions if there's dynamic loading

        # Get the rendered HTML
        html = driver.page_source
    finally:
        # Close the browser
        driver.quit()

    # Ensure output directory exists
    os.makedirs(args.output_dir, exist_ok=True)

    # Save the raw HTML for debugging
    debug_html_path = os.path.join(args.output_dir, "debug_staff_page.html")
    with open(debug_html_path, "w", encoding="utf-8") as raw_file:
        raw_file.write(html)
    print(f"Saved rendered HTML to {debug_html_path} for inspection.")

    # Parse the staff data from the rendered HTML
    staff_data = parse_staff(html)

    # Generate a timestamped CSV filename without colons
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    output_file = os.path.join(args.output_dir, f"{timestamp}-hl7staff.csv")

    # Write staff info to CSV
    with open(output_file, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["Name", "Title"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in staff_data:
            writer.writerow({"Name": entry["name"], "Title": entry["title"]})

    print(f"Extracted {len(staff_data)} staff members. Data saved to {output_file}.")

if __name__ == "__main__":
    main()