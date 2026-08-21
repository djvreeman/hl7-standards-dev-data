#!/usr/bin/env python3
"""
Uptime Robot Calendar Screenshot Capture and Visualization Script

This script captures screenshots of uptime calendars from Uptime Robot and combines them
into a horizontal display for specified time periods.

Usage:
    python get-uptime-visualizations.py -i <url> -p <time_period> -o <output_dir>

Time Period Formats:
    - Full year: '2024'
    - Trimester: '2025T1', '2025T2', '2025T3'
    - Ranges: '2023-2025T2', '2024T2-2025T1'

Trimester Definitions:
    T1: January, February, March, April
    T2: May, June, July, August
    T3: September, October, November, December
"""

import os
import re
import argparse
import time
from datetime import datetime, date
from typing import List, Tuple, Optional
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
from PIL import Image
import requests


class TimePeriod:
    """Represents a time period with start and end dates."""
    
    def __init__(self, start_year: int, start_month: int, end_year: int, end_month: int):
        self.start_year = start_year
        self.start_month = start_month
        self.end_year = end_year
        self.end_month = end_month
    
    def get_months(self) -> List[Tuple[int, int]]:
        """Returns list of (year, month) tuples for all months in the period."""
        months = []
        current_year = self.start_year
        current_month = self.start_month
        
        while (current_year < self.end_year) or (current_year == self.end_year and current_month <= self.end_month):
            months.append((current_year, current_month))
            
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1
        
        return months


def parse_time_period(period_str: str) -> TimePeriod:
    """Parse time period string into TimePeriod object."""
    
    # Handle full year
    if re.match(r'^\d{4}$', period_str):
        year = int(period_str)
        return TimePeriod(year, 1, year, 12)
    
    # Handle trimester
    trimester_match = re.match(r'^(\d{4})T([1-3])$', period_str)
    if trimester_match:
        year = int(trimester_match.group(1))
        trimester = int(trimester_match.group(2))
        
        if trimester == 1:
            return TimePeriod(year, 1, year, 4)
        elif trimester == 2:
            return TimePeriod(year, 5, year, 8)
        elif trimester == 3:
            return TimePeriod(year, 9, year, 12)
    
    # Handle ranges
    range_match = re.match(r'^(\d{4})(?:T([1-3]))?-(\d{4})(?:T([1-3]))?$', period_str)
    if range_match:
        start_year = int(range_match.group(1))
        start_trimester = range_match.group(2)
        end_year = int(range_match.group(3))
        end_trimester = range_match.group(4)
        
        # Determine start month
        if start_trimester:
            if start_trimester == '1':
                start_month = 1
            elif start_trimester == '2':
                start_month = 5
            elif start_trimester == '3':
                start_month = 9
        else:
            start_month = 1
        
        # Determine end month
        if end_trimester:
            if end_trimester == '1':
                end_month = 4
            elif end_trimester == '2':
                end_month = 8
            elif end_trimester == '3':
                end_month = 12
        else:
            end_month = 12
        
        return TimePeriod(start_year, start_month, end_year, end_month)
    
    raise ValueError(f"Invalid time period format: {period_str}")


def extract_system_name(driver) -> str:
    """Extract system name from the uptime page."""
    try:
        # Look for the monitor name specifically
        monitor_selectors = [
            ".monitor-name", "h2.monitor-name", "h2", 
            "[data-testid='monitor-name']", ".title"
        ]
        
        for selector in monitor_selectors:
            try:
                elements = driver.find_elements(By.CSS_SELECTOR, selector)
                for element in elements:
                    if element.is_displayed() and element.text.strip():
                        text = element.text.strip()
                        # Look for patterns like "Ballot Desktop history logs"
                        if "history logs" in text.lower():
                            # Extract the service name before "history logs"
                            service_name = text.replace(" history logs", "").strip()
                            # Clean up the text and use as system name
                            system_name = re.sub(r'[^\w\s-]', '', service_name)
                            system_name = re.sub(r'\s+', '-', system_name).lower()
                            print(f"  Extracted system name from '{text}' -> '{system_name}'")
                            return system_name
            except NoSuchElementException:
                continue
        
        # Fallback: look for any h2 element that might contain the service name
        try:
            h2_elements = driver.find_elements(By.CSS_SELECTOR, "h2")
            for h2 in h2_elements:
                if h2.is_displayed() and h2.text.strip():
                    text = h2.text.strip()
                    # Clean up the text and use as system name
                    system_name = re.sub(r'[^\w\s-]', '', text)
                    system_name = re.sub(r'\s+', '-', system_name).lower()
                    print(f"  Extracted system name from h2 '{text}' -> '{system_name}'")
                    return system_name
        except Exception:
            pass
        
        # Fallback: extract from URL or use default
        url = driver.current_url
        if 'stats.uptimerobot.com' in url:
            return 'uptime-system'
        else:
            return 'unknown-system'
            
    except Exception as e:
        print(f"Warning: Could not extract system name: {e}")
        return 'unknown-system'


def navigate_to_month(driver, year: int, month: int) -> bool:
    """Navigate to a specific month on the uptime calendar."""
    try:
        # Wait for the page to load initially
        time.sleep(3)
        
        # First, try to get current displayed months to understand where we are
        current_months = _get_current_months(driver)
        print(f"  Current months on page: {current_months}")
        
        # Check if target month is already visible
        target_month_text = f"{_get_month_name(month)} {year}"
        if target_month_text in current_months:
            print(f"  Target month {target_month_text} is already visible")
            return True
        
        # Try different navigation strategies
        navigation_strategies = [
            # Strategy 1: Use calendar navigation buttons
            lambda: _navigate_with_calendar_buttons(driver, year, month),
            # Strategy 2: Use date picker
            lambda: _navigate_with_date_picker(driver, year, month),
            # Strategy 3: Use previous/next arrows
            lambda: _navigate_with_arrows(driver, year, month)
        ]
        
        for i, strategy in enumerate(navigation_strategies, 1):
            try:
                print(f"  Trying navigation strategy {i}...")
                if strategy():
                    print(f"  Strategy {i} succeeded")
                    time.sleep(3)  # Wait for page to load
                    
                    # Verify we reached the target month
                    new_months = _get_current_months(driver)
                    print(f"  Months after navigation: {new_months}")
                    if target_month_text in new_months:
                        print(f"  ✓ Successfully navigated to {target_month_text}")
                        return True
                    else:
                        print(f"  ✗ Navigation didn't reach {target_month_text}")
                        
            except Exception as e:
                print(f"  Strategy {i} failed: {str(e)[:100]}...")
                continue
        
        print(f"  All navigation strategies failed for {year}-{month:02d}")
        return False
        
    except Exception as e:
        print(f"Error navigating to {year}-{month:02d}: {e}")
        return False


def _navigate_with_picker(driver, year: int, month: int) -> bool:
    """Navigate using month/year picker if available."""
    try:
        # Look for date picker elements
        picker_selectors = [
            "input[type='date']", 
            ".date-picker", 
            ".month-picker",
            "[data-testid='date-picker']"
        ]
        
        for selector in picker_selectors:
            try:
                picker = driver.find_element(By.CSS_SELECTOR, selector)
                picker.clear()
                picker.send_keys(f"{year}-{month:02d}-01")
                picker.send_keys("\n")
                return True
            except NoSuchElementException:
                continue
        
        return False
    except Exception:
        return False


def _navigate_with_arrows(driver, year: int, month: int) -> bool:
    """Navigate using previous/next arrows."""
    try:
        # Get current displayed month/year
        current_month_elem = driver.find_element(By.CSS_SELECTOR, ".current-month, .month-display")
        current_text = current_month_elem.text.lower()
        
        # Parse current month/year
        current_match = re.search(r'(\w+)\s+(\d{4})', current_text)
        if not current_match:
            return False
        
        month_names = {
            'january': 1, 'february': 2, 'march': 3, 'april': 4,
            'may': 5, 'june': 6, 'july': 7, 'august': 8,
            'september': 9, 'october': 10, 'november': 11, 'december': 12
        }
        
        current_month_name = current_match.group(1)
        current_year = int(current_match.group(2))
        current_month = month_names.get(current_month_name, 1)
        
        # Calculate how many months to navigate
        target_date = date(year, month, 1)
        current_date = date(current_year, current_month, 1)
        
        months_diff = (target_date.year - current_date.year) * 12 + (target_date.month - current_date.month)
        
        if months_diff == 0:
            return True
        
        # Find navigation buttons
        if months_diff > 0:
            # Need to go forward
            next_buttons = driver.find_elements(By.CSS_SELECTOR, ".next, .arrow-right, [data-testid='next']")
            for _ in range(months_diff):
                if next_buttons:
                    next_buttons[0].click()
                    time.sleep(1)
        else:
            # Need to go backward
            prev_buttons = driver.find_elements(By.CSS_SELECTOR, ".prev, .arrow-left, [data-testid='prev']")
            for _ in range(abs(months_diff)):
                if prev_buttons:
                    prev_buttons[0].click()
                    time.sleep(1)
        
        return True
        
    except Exception:
        return False


def _navigate_with_url(driver, year: int, month: int) -> bool:
    """Navigate by manipulating URL parameters."""
    try:
        current_url = driver.current_url
        
        # Try to add date parameters to URL
        if '?' in current_url:
            new_url = f"{current_url}&year={year}&month={month}"
        else:
            new_url = f"{current_url}?year={year}&month={month}"
        
        driver.get(new_url)
        return True
        
    except Exception:
        return False


def _get_current_months(driver) -> List[str]:
    """Get list of currently displayed months on the page."""
    months = []
    try:
        calendar_divs = driver.find_elements(By.CSS_SELECTOR, ".jsCalendar")
        for div in calendar_divs:
            if div.is_displayed():
                title_elements = div.find_elements(By.CSS_SELECTOR, ".jsCalendar-title-name")
                for title_elem in title_elements:
                    month_text = title_elem.text.strip()
                    if month_text:
                        months.append(month_text)
    except Exception:
        pass
    return months


def _get_month_name(month: int) -> str:
    """Get month name from month number."""
    month_names = {
        1: "January", 2: "February", 3: "March", 4: "April",
        5: "May", 6: "June", 7: "July", 8: "August",
        9: "September", 10: "October", 11: "November", 12: "December"
    }
    return month_names.get(month, "Unknown")


def _navigate_with_calendar_buttons(driver, year: int, month: int) -> bool:
    """Navigate using the calendar prev/next buttons."""
    try:
        # Find the calendar navigation buttons
        prev_button = driver.find_element(By.CSS_SELECTOR, ".calendar-prev")
        next_button = driver.find_element(By.CSS_SELECTOR, ".calendar-next")
        
        if not prev_button.is_enabled() and not next_button.is_enabled():
            print("    Both navigation buttons are disabled")
            return False
        
        # Get current months to understand our position
        current_months = _get_current_months(driver)
        target_month_text = f"{_get_month_name(month)} {year}"
        
        # Calculate how many clicks we need
        # The page shows 3 months at a time, so we need to navigate in 3-month increments
        target_date = date(year, month, 1)
        
        # Find the earliest month currently displayed
        earliest_month = None
        earliest_date = None
        for month_text in current_months:
            try:
                month_name, year_str = month_text.rsplit(" ", 1)
                month_num = list(_get_month_name(i) for i in range(1, 13)).index(month_name) + 1
                month_date = date(int(year_str), month_num, 1)
                if earliest_date is None or month_date < earliest_date:
                    earliest_date = month_date
                    earliest_month = month_text
            except:
                continue
        
        if earliest_date is None:
            print("    Could not determine current position")
            return False
        
        # Calculate how many 3-month steps we need
        months_diff = (target_date.year - earliest_date.year) * 12 + (target_date.month - earliest_date.month)
        steps_needed = months_diff // 3
        
        print(f"    Current earliest month: {earliest_month}")
        print(f"    Target month: {target_month_text}")
        print(f"    Need to navigate {steps_needed} steps")
        
        # Navigate using the appropriate button
        if steps_needed > 0:
            # Need to go forward
            if next_button.is_enabled():
                for i in range(steps_needed):
                    print(f"    Clicking next button (step {i+1}/{steps_needed})")
                    next_button.click()
                    time.sleep(2)
                    # Check if we've reached the target
                    new_months = _get_current_months(driver)
                    if target_month_text in new_months:
                        print(f"    Reached target month after {i+1} steps")
                        return True
            else:
                print("    Next button is disabled")
                return False
        elif steps_needed < 0:
            # Need to go backward
            if prev_button.is_enabled():
                for i in range(abs(steps_needed)):
                    print(f"    Clicking prev button (step {i+1}/{abs(steps_needed)})")
                    prev_button.click()
                    time.sleep(2)
                    # Check if we've reached the target
                    new_months = _get_current_months(driver)
                    if target_month_text in new_months:
                        print(f"    Reached target month after {i+1} steps")
                        return True
            else:
                print("    Prev button is disabled")
                return False
        else:
            print("    Already at correct position")
            return True
        
        return False
        
    except Exception as e:
        print(f"    Calendar button navigation failed: {e}")
        return False


def _navigate_with_date_picker(driver, year: int, month: int) -> bool:
    """Navigate using the date picker if available."""
    try:
        # Look for the calendar timepicker
        timepicker = driver.find_element(By.CSS_SELECTOR, ".calendar-timepicker")
        if timepicker.is_displayed():
            print(f"    Found calendar timepicker: {timepicker.text}")
            timepicker.click()
            time.sleep(1)
            
            # Look for date input that might appear
            date_inputs = driver.find_elements(By.CSS_SELECTOR, "input[type='date'], input[type='month']")
            for date_input in date_inputs:
                if date_input.is_displayed():
                    print(f"    Found date input, setting to {year}-{month:02d}")
                    date_input.clear()
                    date_input.send_keys(f"{year}-{month:02d}")
                    date_input.send_keys("\n")
                    return True
            
            # If no date input, try to find any input field
            inputs = driver.find_elements(By.CSS_SELECTOR, "input")
            for input_elem in inputs:
                if input_elem.is_displayed() and input_elem.is_enabled():
                    try:
                        input_elem.clear()
                        input_elem.send_keys(f"{year}-{month:02d}")
                        input_elem.send_keys("\n")
                        return True
                    except:
                        continue
        
        return False
        
    except Exception as e:
        print(f"    Date picker navigation failed: {e}")
        return False


def extract_month_uptime(driver, year: int, month: int) -> Optional[float]:
    """Extract uptime percentage for a specific month."""
    try:
        month_name = _get_month_name(month)
        target_month_text = f"{month_name} {year}"
        
        # Find all jsCalendar divs and look for the one with the target month
        calendar_divs = driver.find_elements(By.CSS_SELECTOR, ".jsCalendar")
        
        for div in calendar_divs:
            try:
                if div.is_displayed():
                    # Look for the month title within this div
                    title_elements = div.find_elements(By.CSS_SELECTOR, ".jsCalendar-title-name")
                    for title_elem in title_elements:
                        if title_elem.text.strip() == target_month_text:
                            # Found the target month calendar, now get the uptime percentage
                            uptime_elements = div.find_elements(By.CSS_SELECTOR, ".jsCalendar-title-right")
                            for uptime_elem in uptime_elements:
                                uptime_text = uptime_elem.text.strip()
                                # Extract percentage value (e.g., "100%" -> 100.0)
                                match = re.search(r'([\d.]+)%', uptime_text)
                                if match:
                                    uptime_value = float(match.group(1))
                                    return uptime_value
            except Exception:
                continue
        
        return None
        
    except Exception as e:
        print(f"    Warning: Could not extract uptime for {year}-{month:02d}: {e}")
        return None


def capture_month_screenshot(driver, year: int, month: int, temp_dir: str) -> Optional[str]:
    """Capture screenshot for a specific month."""
    try:
        # Wait for page to load
        time.sleep(2)
        
        # Try to find the specific month table
        month_name = _get_month_name(month)
        
        # Look for the specific month calendar div
        target_month_text = f"{month_name} {year}"
        print(f"    Looking for month: {target_month_text}")
        
        # Find all jsCalendar divs and look for the one with the target month
        calendar_divs = driver.find_elements(By.CSS_SELECTOR, ".jsCalendar")
        target_div = None
        
        for div in calendar_divs:
            try:
                if div.is_displayed():
                    # Look for the month title within this div
                    title_elements = div.find_elements(By.CSS_SELECTOR, ".jsCalendar-title-name")
                    for title_elem in title_elements:
                        if title_elem.text.strip() == target_month_text:
                            target_div = div
                            print(f"    Found calendar div for {target_month_text}")
                            break
                    if target_div:
                        break
            except Exception:
                continue
        
        # Generate screenshot path
        screenshot_path = os.path.join(temp_dir, f"{year}-{month:02d}.png")
        
        if target_div:
            # Screenshot just the target month calendar div
            print(f"    Capturing calendar div for {year}-{month:02d}")
            try:
                target_div.screenshot(screenshot_path)
            except Exception as e:
                print(f"    Calendar div screenshot failed, falling back to full page: {e}")
                driver.save_screenshot(screenshot_path)
        else:
            # Fallback: screenshot the entire page
            print(f"    No specific calendar div found for {year}-{month:02d}, capturing full page")
            driver.save_screenshot(screenshot_path)
        
        # Verify the screenshot was created and has content
        if os.path.exists(screenshot_path) and os.path.getsize(screenshot_path) > 1000:
            print(f"    ✓ Captured screenshot for {year}-{month:02d}")
            return screenshot_path
        else:
            print(f"    ✗ Screenshot for {year}-{month:02d} appears to be empty or too small")
            return None
        
    except Exception as e:
        print(f"Error capturing screenshot for {year}-{month:02d}: {e}")
        return None


def combine_screenshots(screenshot_paths: List[str], output_path: str, system_name: str):
    """Combine multiple screenshots into a horizontal layout."""
    if not screenshot_paths:
        raise ValueError("No screenshots to combine")
    
    # Load all images
    images = []
    for path in screenshot_paths:
        if os.path.exists(path):
            img = Image.open(path)
            images.append(img)
    
    if not images:
        raise ValueError("No valid screenshots found")
    
    # Calculate dimensions for combined image
    max_height = max(img.height for img in images)
    total_width = sum(img.width for img in images)
    
    # Create combined image
    combined_img = Image.new('RGB', (total_width, max_height), 'white')
    
    # Paste images side by side
    x_offset = 0
    for img in images:
        # Center vertically if image is smaller than max height
        y_offset = (max_height - img.height) // 2
        combined_img.paste(img, (x_offset, y_offset))
        x_offset += img.width
    
    # Save combined image
    combined_img.save(output_path, 'PNG')
    print(f"Combined {len(images)} screenshots into {output_path}")


def generate_output_filename(time_period: TimePeriod, system_name: str) -> str:
    """Generate output filename based on time period and system name."""
    start_str = f"{time_period.start_year}"
    if time_period.start_month != 1:
        start_str += f"T{(time_period.start_month - 1) // 4 + 1}"
    
    end_str = f"{time_period.end_year}"
    if time_period.end_month != 12:
        end_str += f"T{(time_period.end_month - 1) // 4 + 1}"
    
    if start_str == end_str:
        period_str = start_str
    else:
        period_str = f"{start_str}-{end_str}"
    
    return f"{period_str}-uptime-{system_name}.png"


def main():
    parser = argparse.ArgumentParser(
        description="Capture uptime visualizations from Uptime Robot calendars",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Time Period Formats:
    - Full year: '2024'
    - Trimester: '2025T1', '2025T2', '2025T3'
    - Ranges: '2023-2025T2', '2024T2-2025T1'

Trimester Definitions:
    T1: January, February, March, April
    T2: May, June, July, August
    T3: September, October, November, December
        """
    )
    
    parser.add_argument(
        "-i", "--input-url",
        required=True,
        help="URL of the Uptime Robot calendar (e.g., https://stats.hl7.org/784435470/calendar)"
    )
    
    parser.add_argument(
        "-p", "--period",
        required=True,
        help="Time period to capture (e.g., '2025T1', '2024', '2023-2025T2')"
    )
    
    parser.add_argument(
        "-o", "--output-dir",
        default="data/working/uptime-visualizations",
        help="Output directory for the combined image (default: data/working/uptime-visualizations)"
    )
    
    args = parser.parse_args()
    
    # Parse time period
    try:
        time_period = parse_time_period(args.period)
    except ValueError as e:
        print(f"Error: {e}")
        return 1
    
    # Create output directory
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Create temporary directory for screenshots
    temp_dir = os.path.join(args.output_dir, "temp_screenshots")
    os.makedirs(temp_dir, exist_ok=True)
    
    # Configure Chrome with more stable options
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-web-security")
    chrome_options.add_argument("--disable-features=VizDisplayCompositor")
    chrome_options.add_argument("--window-size=1920,1080")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    driver = None
    try:
        # Initialize WebDriver
        driver = webdriver.Chrome(options=chrome_options)
        
        # Navigate to the uptime page
        print(f"Navigating to {args.input_url}")
        driver.get(args.input_url)
        
        # Wait for page to load
        time.sleep(5)
        
        # Extract system name
        system_name = extract_system_name(driver)
        print(f"Detected system name: {system_name}")
        
        # Get list of months to capture
        months = time_period.get_months()
        print(f"Capturing {len(months)} months: {months}")
        
        # First, get all available months on the current page
        print("  Analyzing available months on the page...")
        available_months = []
        calendar_divs = driver.find_elements(By.CSS_SELECTOR, ".jsCalendar")
        
        for div in calendar_divs:
            try:
                if div.is_displayed():
                    title_elements = div.find_elements(By.CSS_SELECTOR, ".jsCalendar-title-name")
                    for title_elem in title_elements:
                        month_text = title_elem.text.strip()
                        print(f"    Found month: {month_text}")
                        available_months.append(month_text)
            except Exception:
                continue
        
        # Filter requested months to only those available
        available_month_set = set(available_months)
        filtered_months = []
        
        for year, month in months:
            month_name = {
                1: "January", 2: "February", 3: "March", 4: "April",
                5: "May", 6: "June", 7: "July", 8: "August",
                9: "September", 10: "October", 11: "November", 12: "December"
            }[month]
            target_month_text = f"{month_name} {year}"
            
            if target_month_text in available_month_set:
                filtered_months.append((year, month))
                print(f"    ✓ {target_month_text} is available")
            else:
                print(f"    ✗ {target_month_text} is not available on current page")
        
        screenshot_paths = []
        uptime_values = {}  # Dictionary to store uptime values: {(year, month): uptime_percentage}
        
        # Always try to capture the requested months by navigating to them
        print("  Attempting to navigate to requested months...")
        for year, month in months:
            print(f"  Processing {year}-{month:02d}...")
            
            # Navigate to the month
            if navigate_to_month(driver, year, month):
                # Extract uptime percentage for this month
                uptime = extract_month_uptime(driver, year, month)
                if uptime is not None:
                    uptime_values[(year, month)] = uptime
                    print(f"    Extracted uptime for {year}-{month:02d}: {uptime}%")
                else:
                    print(f"    Could not extract uptime for {year}-{month:02d}")
                
                # Capture the screenshot
                screenshot_path = capture_month_screenshot(driver, year, month, temp_dir)
                if screenshot_path:
                    screenshot_paths.append(screenshot_path)
            else:
                print(f"  Failed to navigate to {year}-{month:02d}")
        
        # If we couldn't capture any requested months, fall back to available months
        if not screenshot_paths:
            print("  Could not capture any requested months. Capturing all available months as fallback...")
            for i, div in enumerate(calendar_divs):
                if div.is_displayed():
                    fallback_path = os.path.join(temp_dir, f"available-month-{i+1}.png")
                    try:
                        div.screenshot(fallback_path)
                        if os.path.exists(fallback_path) and os.path.getsize(fallback_path) > 1000:
                            screenshot_paths.append(fallback_path)
                            print(f"  ✓ Captured available month {i+1}")
                    except Exception as e:
                        print(f"  Failed to capture available month {i+1}: {e}")
        
        if not screenshot_paths:
            print("No screenshots were captured successfully")
            return 1
        
        # Generate output filename
        output_filename = generate_output_filename(time_period, system_name)
        output_path = os.path.join(args.output_dir, output_filename)
        
        # Combine screenshots
        combine_screenshots(screenshot_paths, output_path, system_name)
        
        print(f"Successfully created uptime visualization: {output_path}")
        
        # Display uptime statistics
        if uptime_values:
            print("\n" + "=" * 60)
            print("Uptime Statistics")
            print("=" * 60)
            
            # Sort months chronologically
            sorted_months = sorted(uptime_values.keys())
            
            # Display uptime for each month
            for year, month in sorted_months:
                uptime = uptime_values[(year, month)]
                print(f"  {year}-{month:02d}: {uptime}%")
            
            # Calculate and display average
            if len(uptime_values) > 0:
                average_uptime = sum(uptime_values.values()) / len(uptime_values)
                print("-" * 60)
                print(f"  Average: {average_uptime}%")
                print("=" * 60)
        else:
            print("\nWarning: Could not extract uptime values for any months")
        
        # Clean up temporary files
        for path in screenshot_paths:
            try:
                os.remove(path)
            except Exception as e:
                print(f"Warning: Could not remove temporary file {path}: {e}")
        
        try:
            os.rmdir(temp_dir)
        except Exception as e:
            print(f"Warning: Could not remove temporary directory {temp_dir}: {e}")
        
        return 0
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
        
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    exit(main()) 