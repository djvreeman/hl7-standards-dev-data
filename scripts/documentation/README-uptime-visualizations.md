# Uptime Robot Calendar Visualization Script

This script captures screenshots of uptime calendars from Uptime Robot and combines them into a horizontal display for specified time periods.

## Features

- Captures screenshots of uptime calendars for specified time periods
- Supports multiple time period formats (full year, trimester, ranges)
- Automatically navigates through different months on the uptime site
- Combines multiple monthly screenshots into a single horizontal image
- Extracts system names from the uptime page for filename generation
- Handles various uptime site layouts and navigation patterns

## Requirements

### Python Dependencies
Install the required Python packages:

```bash
pip install -r requirements-uptime.txt
```

Or install manually:
```bash
pip install selenium>=4.0.0 Pillow>=9.0.0 requests>=2.25.0
```

### System Requirements
- Chrome browser installed
- ChromeDriver (usually auto-downloaded by Selenium)

## Usage

### Basic Usage

```bash
python get-uptime-visualizations.py -i <url> -p <time_period> -o <output_dir>
```

### Examples

1. **Capture a full year (2024):**
   ```bash
   python get-uptime-visualizations.py -i https://stats.hl7.org/784435470/calendar -p 2024
   ```

2. **Capture first trimester of 2025:**
   ```bash
   python get-uptime-visualizations.py -i https://stats.hl7.org/784435470/calendar -p 2025T1
   ```

3. **Capture a range from 2024T2 to 2025T1:**
   ```bash
   python get-uptime-visualizations.py -i https://stats.hl7.org/784435470/calendar -p 2024T2-2025T1
   ```

4. **Specify custom output directory:**
   ```bash
   python get-uptime-visualizations.py -i https://stats.hl7.org/784435470/calendar -p 2025T1 -o data/custom-output
   ```

## Time Period Formats

### Full Year
- Format: `YYYY`
- Example: `2024`, `2025`
- Captures all 12 months of the specified year

### Trimester
- Format: `YYYYT[1-3]`
- Examples: `2025T1`, `2025T2`, `2025T3`

**Trimester Definitions:**
- **T1**: January, February, March, April
- **T2**: May, June, July, August  
- **T3**: September, October, November, December

### Ranges
- Format: `YYYY[TX]-YYYY[TX]`
- Examples: `2023-2025T2`, `2024T2-2025T1`

## Output

The script generates:
1. Individual monthly screenshots (temporarily stored)
2. A combined horizontal image with filename format: `{period}-uptime-{system-name}.png`

### Example Output Filenames
- `2025T1-uptime-ballot-desktop.png`
- `2024-uptime-hl7-website.png`
- `2024T2-2025T1-uptime-fhir-server.png`

## How It Works

1. **Navigation**: The script uses multiple strategies to navigate to different months:
   - Date picker elements
   - Previous/Next arrow buttons
   - URL parameter manipulation

2. **Screenshot Capture**: For each month in the specified period:
   - Navigates to the month
   - Waits for the calendar to load
   - Captures screenshot of the calendar element or entire page

3. **Image Combination**: Combines all monthly screenshots into a single horizontal image

4. **System Name Extraction**: Attempts to extract the system name from the page for use in the output filename

## Troubleshooting

### Common Issues

1. **ChromeDriver not found**: Install ChromeDriver or ensure it's in your PATH
2. **Navigation fails**: The script tries multiple navigation strategies, but some uptime sites may have unique layouts
3. **Screenshots are empty**: Check if the uptime site requires authentication or has anti-bot measures

### Debug Mode

The script provides detailed logging to help troubleshoot issues:
- Navigation attempts and results
- Screenshot capture status
- System name extraction

### Manual Testing

Test the time period parsing logic:
```bash
python test-uptime-parsing.py
```

## Limitations

- Requires the uptime site to be publicly accessible
- May not work with sites that require authentication
- Navigation strategies may need adjustment for custom uptime site layouts
- Chrome browser must be installed on the system

## Contributing

To improve the script:
1. Add new navigation strategies for different uptime site layouts
2. Enhance system name extraction patterns
3. Add support for additional time period formats
4. Improve error handling and recovery 