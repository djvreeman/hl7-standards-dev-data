#!/bin/bash

# Example script for converting Confluence pages to PDF with attachments
# This demonstrates the usage of the convert-confluence-to-pdf-with-attachments.py script

echo "🚀 Starting Confluence to PDF conversion..."

# Set up directories
mkdir -p logs
mkdir -p reports
mkdir -p output

# Example 1: Convert all spaces (default behavior)
echo "📋 Example 1: Converting all spaces..."
python convert-confluence-to-pdf-with-attachments.py \
    --main-config ../../data/config/main.yaml \
    --spaces-dir ../../data/config/spaces \
    --log-file logs/export-all.log

# Example 2: Convert specific spaces only
echo "📋 Example 2: Converting specific spaces (FHIR, HE)..."
python convert-confluence-to-pdf-with-attachments.py \
    --main-config ../../data/config/main.yaml \
    --spaces-dir ../../data/config/spaces \
    --spaces FHIR,HE \
    --log-file logs/export-specific.log

# Example 3: Dry run to see what would be processed
echo "📋 Example 3: Dry run to preview processing..."
python convert-confluence-to-pdf-with-attachments.py \
    --main-config ../../data/config/main.yaml \
    --spaces-dir ../../data/config/spaces \
    --spaces FHIR \
    --dry-run \
    --dry-run-output reports/dry-run-summary.txt \
    --log-file logs/dry-run.log

# Example 4: Force explicit mode for all spaces
echo "📋 Example 4: Force explicit mode..."
python convert-confluence-to-pdf-with-attachments.py \
    --main-config ../../data/config/main.yaml \
    --spaces-dir ../../data/config/spaces \
    --explicit \
    --log-file logs/explicit-mode.log

echo "✅ Conversion examples completed!"
echo "📁 Check the 'output' directory for generated PDFs"
echo "📁 Check the 'logs' directory for detailed logs"
echo "📁 Check the 'reports' directory for dry-run summaries"
