# Trademark Application Member Matcher

This script helps review trademark applications and determine whether the applicant organization is a member of HL7 via API calls to Salesforce database.

## Features

- Reads trademark applications from Excel spreadsheet
- Queries Salesforce for member organizations (using badge-based approach)
- Uses fuzzy matching to find potential matches
- Human-in-the-loop review with top 5 choices
- **NEW**: Direct Salesforce search capability during review
- **NEW**: GUI interface for easier interaction
- **NEW**: Graceful error handling and backup file creation
- Filters by status (e.g., "approved" only)
- Outputs results with Member Y/N field and SF member ID

## Installation

1. Install required dependencies:
```bash
pip install -r requirements.txt
```

2. For GUI version:
```bash
pip install -r requirements-gui.txt
```

3. Configuration:
   - **Default**: The script will automatically use `../../data/config/sf-config.yaml` if available
   - **Custom**: Copy the configuration template and specify it with `-c`:
   ```bash
   cp config-template.yaml config.yaml
   # Edit config.yaml with your Salesforce API credentials
   ```

## Usage

### Command Line Interface

#### Basic Usage
```bash
# Using default config file (../../data/config/sf-config.yaml)
python trademark-member-matcher.py -i input.xlsx -o output.xlsx

# Using custom config file
python trademark-member-matcher.py -c config.yaml -i input.xlsx -o output.xlsx
```

### GUI Interface

For a more user-friendly experience, use the GUI version:

```bash
# Run from main directory (recommended)
python3 scripts/members/trademark-matcher-gui-main.py

# Or navigate to scripts/members directory first
cd scripts/members

# Option 1: Minimal GUI (guaranteed to work)
python3 minimal-gui.py

# Option 2: Simplified GUI (full functionality)
python3 trademark-matcher-simple-gui.py

# Option 3: Standalone GUI
python3 trademark-matcher-gui-standalone.py

# Option 4: Launcher script (with error checking)
python3 launch-gui.py

# Option 5: Original GUI (requires proper import setup)
python3 trademark-matcher-gui.py
```

The GUI provides:
- File browser dialogs for easy file selection
- Real-time progress updates and status logging
- Simplified processing (auto-matches best results)
- Visual interface for configuration
- Error handling and backup file creation

### Advanced Options
```bash
# Process only one sheet
python trademark-member-matcher.py -i input.xlsx -o output.xlsx -s "Community License Applications"

# Filter by different status
python trademark-member-matcher.py -i input.xlsx -o output.xlsx --status-filter "pending"

# Adjust fuzzy matching threshold
python trademark-member-matcher.py -i input.xlsx -o output.xlsx --fuzzy-threshold 80

# Auto-match high confidence matches (90%+)
python trademark-member-matcher.py -i input.xlsx -o output.xlsx --auto-match

# Skip human review (for testing)
python trademark-member-matcher.py -i input.xlsx -o output.xlsx --skip-review

# Use custom config file
python trademark-member-matcher.py -c config.yaml -i input.xlsx -o output.xlsx
```

## Configuration

The `config.yaml` file should contain:

```yaml
# Salesforce API Configuration
prod_server: "https://hl7.my.salesforce.com"
version: "60.0"
client_id: "your_connected_app_client_id"
client_secret: "your_connected_app_client_secret"
username: "your_salesforce_username"
password: "your_salesforce_password_and_security_token"

# Matching Configuration
fuzzy_threshold: 70  # Minimum confidence score for fuzzy matching (0-100)
auto_match_threshold: 90  # Threshold for auto-matching without human review
```

## Input Format

The script expects an Excel file with the following columns:
- `Organization`: Organization name
- `Contact Email`: Contact email address
- `Status`: Application status (e.g., "approved", "pending")

## Output Format

The script creates a new Excel file with the original data plus these additional columns:
- `Member_Y_N`: Whether the organization is a member (Y/N)
- `SF_Member_ID`: Salesforce Account ID if matched
- `Confidence_Score`: Fuzzy matching confidence score (0-100)
- `Review_Status`: How the match was determined (manual_review, auto_matched, skipped, etc.)
- `Matched_Organization`: The matched organization name from Salesforce

## Workflow

1. **Load Data**: Reads the trademark applications from Excel
2. **Fetch Members**: Queries Salesforce for member organizations
3. **Fuzzy Matching**: Uses fuzzy string matching to find potential matches
4. **Human Review**: For each application, presents top 5 matches for review
5. **Output Results**: Saves results to a new Excel file

## Human Review Interface

For each organization, the script displays:
- Organization name from the application
- Top 5 potential matches from Salesforce with:
  - Organization name
  - Confidence score
  - Salesforce ID
  - Location (if available)
  - Website (if available)

### Review Options:
- `1-5`: Select the matching organization
- `0`: No match (not a member)
- `s`: Search Salesforce directly for other options
- `q`: Quit processing

### Direct Salesforce Search

When reviewing matches, you can search Salesforce directly:
- Enter custom search terms
- View up to 20 matching organizations
- Select from search results
- Perform new searches if needed

## Tips

1. **Start with a small subset**: Use the `-s` option to process just one sheet first
2. **Adjust thresholds**: Lower the fuzzy threshold if you're missing matches, raise it if you're getting too many false positives
3. **Use auto-match**: For high-confidence matches, use `--auto-match` to speed up processing
4. **Review results**: Always review the output file to ensure accuracy

## Error Handling

The tool now includes robust error handling:
- **Graceful shutdowns**: Results are saved even if you quit partway through
- **Backup files**: If the main output file is corrupted, backup files are created
- **CSV fallback**: If Excel writing fails, results are saved as CSV
- **Progress tracking**: Real-time progress updates during processing

## Troubleshooting

- **No matches found**: Try lowering the `--fuzzy-threshold`
- **Too many false positives**: Try raising the `--fuzzy-threshold`
- **Salesforce connection issues**: Check your credentials and network connection
- **Excel file issues**: Ensure the file is not open in another application
- **Corrupted output files**: Check for backup files with `_backup_` in the filename 