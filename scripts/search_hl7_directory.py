from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import urllib.parse

# Base URL for the Global Membership Directory search results
BASE_SEARCH_URL = "https://www.hl7.org/about/GlobalMembershipDirectory/global_directory_result.cfm"

def create_query_url(first_name=None, last_name=None):
    """Generates the query URL with the given search parameters."""
    params = {}
    if first_name:
        params['first_name'] = first_name
    if last_name:
        params['last_name'] = last_name

    query_url = f"{BASE_SEARCH_URL}?{urllib.parse.urlencode(params)}"
    print(f"Generated Query URL: {query_url}")
    return query_url

def parse_results(browser):
    """Parses the search results from the webpage."""
    # Wait for the search results table to load
    WebDriverWait(browser, 10).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, "table tbody tr"))
    )

    results = []
    rows = browser.find_elements(By.CSS_SELECTOR, "table tbody tr")

    for row in rows:
        cols = row.find_elements(By.TAG_NAME, "td")

        if len(cols) >= 9:
            # The expected field order: Type, Affiliate, Last Name, First Name, Organization, Phone, Email, Aff Code, vCard
            first_name = cols[3].text.strip()
            last_name = cols[2].text.strip()

            # Extract the unique ID from the hyperlink in the "vCard" column
            try:
                link = cols[8].find_element(By.TAG_NAME, "a").get_attribute("href")
                query_params = urllib.parse.parse_qs(urllib.parse.urlparse(link).query)
                unique_id = query_params.get('unique_id', ['N/A'])[0]
            except Exception:
                unique_id = 'N/A'

            results.append((first_name, last_name, unique_id))

    return results

def display_results(results):
    """Displays the search results in a tabular format."""
    print(f"{'First Name':<15} {'Last Name':<20} {'Unique ID'}")
    print("-" * 55)
    for first_name, last_name, unique_id in results:
        print(f"{first_name:<15} {last_name:<20} {unique_id}")

def parse_name_input(name_input):
    """Splits the input into first and last name based on the first space."""
    parts = name_input.strip().split(" ", 1)
    first_name = parts[0]
    last_name = parts[1] if len(parts) > 1 else None
    return first_name, last_name

def main():
    # Initialize the Selenium WebDriver (Chrome)
    browser = webdriver.Chrome()

    try:
        # Open the Global Membership Directory (triggers login if needed)
        browser.get(BASE_SEARCH_URL)
        input("Log in and press Enter once you are on the search page...")

        while True:
            # Collect search input from the user
            name_input = input("Enter First and Last Name (or 'q' to quit): ").strip()
            if name_input.lower() == 'q':
                print("Exiting the search.")
                break

            first_name, last_name = parse_name_input(name_input)

            # Generate the search query URL and open it
            search_url = create_query_url(first_name, last_name)
            browser.get(search_url)

            # Parse and display the search results
            results = parse_results(browser)
            display_results(results)

    finally:
        print("Closing browser...")
        browser.quit()

if __name__ == "__main__":
    main()