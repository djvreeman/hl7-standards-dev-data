import argparse
import csv
from pathlib import Path
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def get_dependent_packages_selenium(package_name, version):
    base_url = f"https://registry.fhir.org/package/{package_name}%7C{version}"
    
    # Setup Selenium WebDriver
    chrome_options = Options()
    chrome_options.add_argument("--headless")  # Run in headless mode
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    service = Service(ChromeDriverManager().install())  # Automatically manage ChromeDriver
    driver = webdriver.Chrome(service=service, options=chrome_options)

    try:
        # Open the package page
        driver.get(base_url)

        # Wait for the "Dependents" tab to load and click it
        wait = WebDriverWait(driver, 10)
        dependents_tab = wait.until(EC.element_to_be_clickable((By.ID, "rc-tabs-0-tab-dependents")))
        dependents_tab.click()

        # Wait for the dependents list to load
        dependents_section = wait.until(EC.presence_of_element_located((By.ID, "rc-tabs-0-panel-dependents")))

        # Parse the list of dependent packages
        dependents_list = []
        dependents_items = dependents_section.find_elements(By.XPATH, './/ul/li/span')  # Adjust XPath based on structure
        for item in dependents_items:
            dependents_list.append(item.text.strip())

        return dependents_list

    except Exception as e:
        print(f"Error: {e}")
        return []

    finally:
        driver.quit()

def write_to_csv(package, version, dependents, output_path):
    # Construct the file name
    file_name = f"{package}-{version}-dependents.csv"
    output_file = Path(output_path) / file_name

    # Write to CSV
    with open(output_file, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Write the header
        writer.writerow(['package', 'version', 'dependent-package'])
        # Write the dependent packages
        for dependent in dependents:
            writer.writerow([package, version, dependent])

    # Print output message with count
    print(f"({len(dependents)}) dependent packages written to {output_file}")

if __name__ == "__main__":
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Extract dependent packages from the FHIR registry and write to CSV.")
    parser.add_argument("-p", "--package", required=True, help="FHIR package name (e.g., hl7.fhir.uv.ipa)")
    parser.add_argument("-v", "--version", required=True, help="FHIR package version (e.g., 1.0.0)")
    parser.add_argument("-o", "--output", required=True, help="Output directory for the CSV file")
    args = parser.parse_args()

    # Get package and version from arguments
    package = args.package
    version = args.version
    output_path = args.output

    # Extract dependent packages
    dependents = get_dependent_packages_selenium(package, version)
    if dependents:
        write_to_csv(package, version, dependents, output_path)
    else:
        print("No dependent packages found or an error occurred.")