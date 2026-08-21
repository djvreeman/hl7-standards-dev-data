#!/bin/bash

# Test script for the enhanced Confluence markdown uploader
# This demonstrates how to use the script with different options

echo "Testing Confluence markdown uploader script..."

# Example 1: Create a new page with default settings
echo "Example 1: Creating a new page with default settings"
python3 scripts/update-confluence-page-w-markdown.py \
    -t "2025T2 Issue Resolution Summary Report" \
    -i "data/tmp/2025T2-enhanced.md"

echo ""

# Example 2: Create a new page with custom space and parent
echo "Example 2: Creating a new page with custom space and parent"
python3 scripts/update-confluence-page-w-markdown.py \
    -t "2025T2 Issue Resolution Summary Report" \
    -i "data/tmp/2025T2-enhanced.md" \
    -s "FHIR" \
    -p "123456789"

echo ""

# Example 3: Update an existing page
echo "Example 3: Updating an existing page"
python3 scripts/update-confluence-page-w-markdown.py \
    -t "2025T2 Issue Resolution Summary Report (Updated)" \
    -i "data/tmp/2025T2-enhanced.md" \
    -r "987654321"

echo ""

# Example 4: Using a custom config file
echo "Example 4: Using a custom config file"
python3 scripts/update-confluence-page-w-markdown.py \
    -c "data/config/custom-confluence.yaml" \
    -t "2025T2 Issue Resolution Summary Report" \
    -i "data/tmp/2025T2-enhanced.md"

echo "Test examples completed!"
