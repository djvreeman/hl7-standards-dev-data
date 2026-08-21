# Confluence to PDF Converter with Intelligent Attachment Handling

This script converts Confluence pages to PDF format with intelligent attachment management.

## Key Features

### 1. PDF Conversion
- Converts Confluence pages to high-quality PDFs
- Preserves formatting, tables, and styling
- Uses WeasyPrint (preferred) or pdfkit as fallback
- Includes proper CSS styling for professional appearance

### 2. Intelligent Attachment Strategy
- **Shared Attachment Directory**: All attachments are stored in a shared `shared_attachments/` directory
- **Deduplication**: Avoids re-downloading existing files
- **Categorized Display**: Attachments are grouped by type (Images, Documents, Archives, etc.)
- **Rich Metadata**: Shows file size, download date, and original author
- **Relative Links**: Uses relative paths for portability

### 3. Attachment Organization
Each page includes an "Attachments" section at the bottom with:
- **Categorized listing** by file type
- **Clickable links** to download/view files
- **File metadata** (size, date, author)
- **Visual organization** with proper styling

## Installation

1. Install Python dependencies:
```bash
pip install -r requirements-pdf.txt
```

2. For WeasyPrint (recommended), install system dependencies:
   - **macOS**: `brew install cairo pango gdk-pixbuf libffi`
   - **Ubuntu**: `sudo apt-get install libcairo2 libpango-1.0-0 libgdk-pixbuf2.0-0 libffi-dev`

## Usage

```bash
python convert-confluence-to-pdf-with-attachments.py \
    --main-config config/main.yaml \
    --spaces-dir data/config/spaces \
    [--spaces FHIR,HE] \
    [--dry-run] \
    [--dry-run-output reports/summary.txt] \
    [--log-file logs/export.log] \
    [--explicit]
```

## Output Structure

```
output_dir/
├── space_key/
│   ├── page_title_pageid.pdf
│   ├── another_page_pageid.pdf
│   └── ...
└── shared_attachments/
    ├── document1.pdf
    ├── image1.png
    ├── archive1.zip
    └── ...
```

## Attachment Handling Strategy

### 1. Download Strategy
- All attachments are downloaded to `shared_attachments/` directory
- Files are deduplicated across pages (same file = single download)
- Original filenames are preserved
- Download progress is logged

### 2. Linking Strategy
- **In-page references**: Diagrams and images are embedded directly in the PDF
- **Attachment section**: All attachments are listed at the bottom of each page
- **Relative paths**: Links use relative paths for portability
- **Categorized display**: Files grouped by type for easy navigation

### 3. Metadata Display
Each attachment shows:
- 📏 File size (human-readable)
- 📅 Download date
- 👤 Original author
- 🔗 Clickable filename

## Configuration

The script uses the same YAML configuration as the original markdown converter:

```yaml
# config/main.yaml
confluence_base_url: "https://your-confluence-instance.com"
confluence_bearer_token: "your-token"
output_dir: "output"
page_limit: 50

# data/config/spaces/space_key.yaml
space_key: "SPACE"
explicit-mode: false
includes:
  parent_pages:
    - id: 12345
  pages:
    - id: 67890
excludes:
  attachments:
    - id: 35717349
      title: "Outdated Document.zip"
```

## Benefits of This Approach

1. **Efficient Storage**: Shared attachments prevent duplication
2. **Professional PDFs**: High-quality output with proper styling
3. **Easy Navigation**: Categorized attachment listings
4. **Portable**: Relative links work when moving the output directory
5. **Comprehensive**: All attachments are preserved and accessible
6. **Metadata Rich**: Shows file information for better organization

## Troubleshooting

### PDF Generation Issues
- Ensure WeasyPrint or pdfkit is properly installed
- Check system dependencies for WeasyPrint
- Verify HTML content is valid

### Attachment Issues
- Check network connectivity for downloads
- Verify Confluence API permissions
- Ensure sufficient disk space for attachments

### Performance
- Large attachments may slow down processing
- Consider excluding large files in YAML config
- Monitor disk usage during processing
