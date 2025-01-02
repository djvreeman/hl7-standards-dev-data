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
        raise RuntimeError(f"Error processing {package_name}|{version}: {str(e)}") from e

    finally:
        driver.quit()

def process_packages(input_file, output_file, error_file):
    # Read input CSV
    with open(input_file, mode='r', encoding='utf-8') as file:
        reader = csv.reader(file)
        # Filter out empty rows and rows with missing fields
        packages = [row for row in reader if len(row) == 2 and row[0].strip() and row[1].strip()]

    # Skip header row if present
    if packages and packages[0] == ['package', 'version']:
        packages = packages[1:]

    # Prepare consolidated output and error data
    consolidated_data = []
    error_data = []
    total_dependents = 0

    for package, version in packages:
        print(f"Processing {package}|{version}...")
        try:
            dependents = get_dependent_packages_selenium(package, version)
            total_dependents += len(dependents)

            for dependent in dependents:
                consolidated_data.append([package, version, dependent])
        except Exception as e:
            # Log errors to the error data list
            error_data.append([package, version, str(e)])

    # Write consolidated output CSV
    with open(output_file, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Write the header
        writer.writerow(['package', 'version', 'dependent-package'])
        # Write the consolidated data
        writer.writerows(consolidated_data)

    # Write error CSV
    with open(error_file, mode='w', newline='', encoding='utf-8') as file:
        writer = csv.writer(file)
        # Write the header
        writer.writerow(['package', 'version', 'error-message'])
        # Write the error data
        writer.writerows(error_data)

    print(f"Processed {len(packages)} packages. ({total_dependents}) dependent packages written to {output_file}")
    print(f"({len(error_data)}) errors logged to {error_file}")

if __name__ == "__main__":
    # Setup argument parser
    parser = argparse.ArgumentParser(description="Extract dependent packages for multiple FHIR package versions and log errors.")
    parser.add_argument("-i", "--input", required=True, help="Input CSV file with package and version columns")
    parser.add_argument("-o", "--output", required=True, help="Output CSV file for consolidated results")
    parser.add_argument("-e", "--error", required=True, help="Error CSV file to log errors")
    args = parser.parse_args()

    # Get input, output, and error paths from arguments
    input_file = args.input
    output_file = args.output
    error_file = args.error

    # Process packages from input CSV and write results and errors to output files
    process_packages(input_file, output_file, error_file)