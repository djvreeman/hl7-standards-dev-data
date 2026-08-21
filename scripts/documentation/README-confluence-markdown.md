# Confluence Markdown Uploader

This script allows you to create or update Confluence pages from markdown files.

## Features

- ✅ Create new Confluence pages from markdown files
- ✅ Update existing Confluence pages with new content
- ✅ Support for YAML configuration files
- ✅ Parent page hierarchy support
- ✅ Enhanced markdown support (tables, code blocks, TOC)
- ✅ Comprehensive error handling and validation

## Requirements

Install the required Python packages:

```bash
pip install requests pyyaml markdown
```

## Configuration

Create a YAML configuration file (default: `data/config/confluence.yaml`):

```yaml
# Confluence API Configuration
base_url: https://confluence.hl7.org
bearer_token: your_personal_access_token_here

# Optional rate limiting settings
rate_limit_delay: 1.5  # seconds to wait between requests
max_retries: 3         # number of retries for failed requests
retry_delay: 10.0      # seconds to wait on rate limit/errors before retry
```

### Getting a Bearer Token

1. Go to your Confluence instance
2. Click on your profile picture → Settings
3. Go to Personal Access Tokens
4. Create a new token with appropriate permissions

## Usage

### Basic Syntax

```bash
python3 scripts/update-confluence-page-w-markdown.py -t "Page Title" -i "path/to/markdown.md"
```

### Command Line Options

| Option | Short | Default | Description |
|--------|-------|---------|-------------|
| `--config` | `-c` | `data/config/confluence.yaml` | Path to YAML config file |
| `--space` | `-s` | `~dvreeman` | Confluence space key |
| `--title` | `-t` | *required* | Title of the page |
| `--input` | `-i` | *required* | Path to input markdown file |
| `--parent` | `-p` | `345541283` | Parent page ID for new pages |
| `--replace` | `-r` | *none* | Page ID to update (if not provided, creates new page) |

### Examples

#### Create a New Page

```bash
# Using defaults
python3 scripts/update-confluence-page-w-markdown.py \
    -t "2025T2 Issue Resolution Summary Report" \
    -i "data/tmp/2025T2-enhanced.md"

# With custom space and parent
python3 scripts/update-confluence-page-w-markdown.py \
    -t "2025T2 Issue Resolution Summary Report" \
    -i "data/tmp/2025T2-enhanced.md" \
    -s "FHIR" \
    -p "123456789"
```

#### Update an Existing Page

```bash
python3 scripts/update-confluence-page-w-markdown.py \
    -t "2025T2 Issue Resolution Summary Report (Updated)" \
    -i "data/tmp/2025T2-enhanced.md" \
    -r "987654321"
```

#### Using a Custom Config File

```bash
python3 scripts/update-confluence-page-w-markdown.py \
    -c "data/config/custom-confluence.yaml" \
    -t "2025T2 Issue Resolution Summary Report" \
    -i "data/tmp/2025T2-enhanced.md"
```

## Markdown Support

The script supports enhanced markdown features:

- **Tables**: Standard markdown tables
- **Code blocks**: Fenced code blocks with syntax highlighting
- **Table of Contents**: Automatic TOC generation
- **Standard markdown**: Headers, lists, links, images, etc.

## Error Handling

The script includes comprehensive error handling:

- ✅ Config file validation
- ✅ Input file existence checks
- ✅ API response validation
- ✅ Clear error messages with emojis
- ✅ Proper exit codes for scripting

## Output

The script provides clear feedback:

- 🔄 Processing status
- ✅ Success messages with page URLs
- ❌ Error messages with details
- 🎉 Final success confirmation

## Testing

Run the test script to see examples:

```bash
./scripts/test-confluence-script.sh
```

## Troubleshooting

### Common Issues

1. **Authentication errors**: Check your bearer token
2. **File not found**: Verify the markdown file path
3. **Permission errors**: Ensure you have write access to the Confluence space
4. **Rate limiting**: The script includes built-in delays, but you may need to adjust them

### Debug Mode

For debugging, you can modify the script to add more verbose output or check the Confluence API documentation for specific error codes.
