#!/usr/bin/env python3
"""
Test script for uptime visualization time period parsing
"""

import re
from datetime import date
from typing import List, Tuple


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


def test_time_period_parsing():
    """Test various time period formats."""
    
    test_cases = [
        # Full year
        ("2024", TimePeriod(2024, 1, 2024, 12)),
        ("2025", TimePeriod(2025, 1, 2025, 12)),
        
        # Trimester
        ("2025T1", TimePeriod(2025, 1, 2025, 4)),
        ("2025T2", TimePeriod(2025, 5, 2025, 8)),
        ("2025T3", TimePeriod(2025, 9, 2025, 12)),
        
        # Ranges
        ("2023-2025T2", TimePeriod(2023, 1, 2025, 8)),
        ("2024T2-2025T1", TimePeriod(2024, 5, 2025, 4)),
        ("2024T1-2024T3", TimePeriod(2024, 1, 2024, 12)),
    ]
    
    print("Testing time period parsing...")
    
    for period_str, expected in test_cases:
        try:
            result = parse_time_period(period_str)
            if (result.start_year == expected.start_year and 
                result.start_month == expected.start_month and
                result.end_year == expected.end_year and
                result.end_month == expected.end_month):
                print(f"✓ {period_str} -> {result.start_year}-{result.start_month:02d} to {result.end_year}-{result.end_month:02d}")
            else:
                print(f"✗ {period_str} -> Expected {expected.start_year}-{expected.start_month:02d} to {expected.end_year}-{expected.end_month:02d}, got {result.start_year}-{result.start_month:02d} to {result.end_year}-{result.end_month:02d}")
        except Exception as e:
            print(f"✗ {period_str} -> Error: {e}")
    
    print("\nTesting month generation...")
    
    # Test month generation for a few cases
    test_periods = [
        ("2025T1", [(2025, 1), (2025, 2), (2025, 3), (2025, 4)]),
        ("2025T2", [(2025, 5), (2025, 6), (2025, 7), (2025, 8)]),
        ("2024T3-2025T1", [(2024, 9), (2024, 10), (2024, 11), (2024, 12), (2025, 1), (2025, 2), (2025, 3), (2025, 4)]),
    ]
    
    for period_str, expected_months in test_periods:
        try:
            period = parse_time_period(period_str)
            months = period.get_months()
            if months == expected_months:
                print(f"✓ {period_str} -> {len(months)} months: {months}")
            else:
                print(f"✗ {period_str} -> Expected {expected_months}, got {months}")
        except Exception as e:
            print(f"✗ {period_str} -> Error: {e}")


if __name__ == "__main__":
    test_time_period_parsing() 