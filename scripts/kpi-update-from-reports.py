#!/usr/bin/env python3
# =============================================================================
# KPI Update from Reports
#
# This script extracts metrics from various HL7 reports (Issue Reports, PSS Reports,
# Ballot Participation Reports) and updates a KPI tracking CSV file.
#
# === Usage ===
# python scripts/kpi-update-from-reports.py \
#     --issue-report data/working/issue-analysis/2025/2025-AllYear/finals/2022to2025-issue-report.md \
#     -i data/working/issue-analysis/2025/2025-AllYear/finals/new_kpis.csv \
#     -o data/working/issue-analysis/2025/2025-AllYear/finals/new_kpis_updated.csv
#
# # In-place update (default when -o/--output is omitted) with backup
# python scripts/kpi-update-from-reports.py \
#     --issue-report data/working/issue-analysis/2025/2025-AllYear/finals/2022to2025-issue-report.md \
#     -i data/working/issue-analysis/2025/2025-AllYear/finals/new_kpis.csv \
#     --backup
#
# === Future Extensions ===
# --pss-report: For PSS approval metrics
# --ballot-report: For ballot participation metrics
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import csv
import re
import sys
import shutil
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple


def parse_markdown_table(content: str, section_title: str, table_index: int = 0) -> Optional[List[Dict[str, str]]]:
    """
    Extract data from a markdown table in the report.
    
    Args:
        content: Full markdown content
        section_title: Title of the section containing the table (e.g., "Reporter Breakdown")
                      Can be a partial match and will handle emojis/special characters
        table_index: Which table in the section (0-based)
    
    Returns:
        List of dictionaries with column names as keys, or None if not found
    """
    # Find the section - escape special regex characters but allow flexible matching
    # Handle emojis and special characters by using a more flexible pattern
    escaped_title = re.escape(section_title)
    # Try exact match first - match from ### through the section until next ### or ##
    # Match the title line, then capture everything until the next section header
    pattern = rf"### [^\n]*{escaped_title}[^\n]*\n((?:[^\n]|\n(?!### |## ))*)"
    section_match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
    
    if not section_match:
        # Try partial match (section title contains the search string)
        # Replace non-word/space characters for flexible matching
        flexible_title = re.sub(r'[^\w\s]', '[^\n]*', section_title)
        pattern = rf"### [^\n]*{flexible_title}[^\n]*\n((?:[^\n]|\n(?!### |## ))*)"
        section_match = re.search(pattern, content, re.MULTILINE | re.IGNORECASE)
    
    if not section_match:
        return None
    
    # Get the section content (group 1 is the content after the title)
    section_text = section_match.group(1) if section_match.lastindex >= 1 else section_match.group(0)
    
    # Find all tables in the section
    # Look for table pattern: header row, separator row (with dashes), then data rows
    # First, find the separator row pattern to locate tables
    lines = section_text.split('\n')
    table_start_indices = []
    
    for i, line in enumerate(lines):
        # Check if this looks like a separator row (starts with |, contains dashes or colons)
        if line.strip().startswith('|') and ('-' in line or ':' in line):
            # Check if previous line is a header (starts with |)
            if i > 0 and lines[i-1].strip().startswith('|'):
                table_start_indices.append(i-1)
    
    if table_index >= len(table_start_indices):
        return None
    
    start_idx = table_start_indices[table_index]
    
    # Extract table: header (start_idx), separator (start_idx+1), then data rows
    table_lines = []
    table_lines.append(lines[start_idx])  # Header
    table_lines.append(lines[start_idx + 1])  # Separator
    
    # Collect data rows until we hit a non-table line or end
    for i in range(start_idx + 2, len(lines)):
        line = lines[i]
        if line.strip().startswith('|') and line.strip() != '':
            table_lines.append(line)
        elif line.strip() == '':
            # Empty line might be part of table, continue
            continue
        else:
            # Non-table line, stop
            break
    
    if len(table_lines) < 3:  # Need at least header, separator, and one data row
        return None
    
    # Parse header
    header_line = table_lines[0]
    headers = [h.strip() for h in header_line.split('|')[1:-1]]
    
    if len(headers) == 0:
        return None
    
    # Parse data rows (skip header and separator)
    rows = []
    for line in table_lines[2:]:
        if line.strip() and '|' in line:
            cells = [c.strip() for c in line.split('|')[1:-1]]
            if len(cells) == len(headers):
                row_dict = {}
                for i, header in enumerate(headers):
                    row_dict[header] = cells[i]
                rows.append(row_dict)
    
    return rows if rows else None


def convert_period_format(period: str) -> str:
    """
    Convert period format from report (e.g., '2022T1') to CSV format (e.g., '2022-T1').
    
    Args:
        period: Period string in format YYYYT[1-3] or YYYY-T[1-3]
    
    Returns:
        Period string in format YYYY-T[1-3]
    """
    # Handle both formats
    if '-' in period:
        return period
    # Convert 2022T1 to 2022-T1
    match = re.match(r'(\d{4})T([1-3])', period)
    if match:
        return f"{match.group(1)}-T{match.group(2)}"
    return period


def clean_numeric_value(value: str) -> Optional[float]:
    """
    Clean and convert numeric values from markdown tables.
    Removes commas, percentage signs, and converts to float.
    
    Args:
        value: String value from table
    
    Returns:
        Float value or None if conversion fails
    """
    if not value or value.strip() == '':
        return None
    
    # Remove commas and percentage signs
    cleaned = value.replace(',', '').replace('%', '').strip()
    
    try:
        return float(cleaned)
    except ValueError:
        return None


def extract_issue_report_metrics(report_content: str) -> Dict[str, Dict[str, float]]:
    """
    Extract metrics from an issue report markdown file.
    
    Args:
        report_content: Full content of the markdown report
    
    Returns:
        Dictionary mapping indicator IDs to dictionaries of period -> value
        Format: {indicator_id: {period: value}}
    """
    metrics = {}
    
    # Indicator 19: Issue submitters (Total Reporters)
    reporter_data = parse_markdown_table(report_content, "Reporter Breakdown")
    if reporter_data and len(reporter_data) > 0:
        metrics['19'] = {}
        for row in reporter_data:
            period_raw = row.get('Period', '')
            period = convert_period_format(period_raw)
            total_reporters = clean_numeric_value(row.get('Total Reporters', ''))
            if period and total_reporters is not None:
                metrics['19'][period] = int(total_reporters)
    
    # Indicator 20: Issue submitters: New (% New Reporters)
    if reporter_data:
        metrics['20'] = {}
        for row in reporter_data:
            period = convert_period_format(row.get('Period', ''))
            pct_new = clean_numeric_value(row.get('% New Reporters', ''))
            if period and pct_new is not None:
                metrics['20'][period] = pct_new
    
    # Indicator 21: Issues resolved (Count from Resolution Time table)
    # Find the breakdown section by finding the start and end markers
    breakdown_start = report_content.find("## Breakdown by Period within")
    breakdown_end = report_content.find("\n## Issue Reporters", breakdown_start)
    
    resolution_data = None
    if breakdown_start >= 0:
        if breakdown_end < 0:
            breakdown_end = len(report_content)
        breakdown_content = report_content[breakdown_start:breakdown_end]
        
        # Find the resolution time subsection within breakdown
        subsection_start = breakdown_content.find("###")
        while subsection_start >= 0:
            # Check if this is the resolution time subsection
            subsection_header = breakdown_content[subsection_start:breakdown_content.find('\n', subsection_start)]
            # Reports evolved over time (e.g. "...in 2026T1" vs "...in 2022-2025");
            # match the subsection by its semantic title rather than a hard-coded date range.
            if 'Time to Issue Resolution' in subsection_header:
                # Found it! Extract the table
                subsection_content = breakdown_content[subsection_start:]
                # Find the table
                lines = subsection_content.split('\n')
                table_start_indices = []
                for i, line in enumerate(lines):
                    if line.strip().startswith('|') and ('-' in line or ':' in line):
                        if i > 0 and lines[i-1].strip().startswith('|') and 'Period' in lines[i-1]:
                            table_start_indices.append(i-1)
                if table_start_indices:
                    start_idx = table_start_indices[0]
                    table_lines = [lines[start_idx], lines[start_idx + 1]]
                    for i in range(start_idx + 2, len(lines)):
                        line = lines[i]
                        if line.strip().startswith('|') and line.strip() != '':
                            table_lines.append(line)
                        elif line.strip() == '':
                            continue
                        elif line.strip().startswith('###') or line.strip().startswith('##'):
                            break
                        else:
                            continue
                    if len(table_lines) >= 3:
                        header_line = table_lines[0]
                        headers = [h.strip() for h in header_line.split('|')[1:-1]]
                        if len(headers) > 0:
                            rows = []
                            for line in table_lines[2:]:
                                if line.strip() and '|' in line:
                                    cells = [c.strip() for c in line.split('|')[1:-1]]
                                    if len(cells) == len(headers):
                                        row_dict = {headers[i]: cells[i] for i in range(len(headers))}
                                        rows.append(row_dict)
                            if rows:
                                resolution_data = rows
                                break
            # Move to next subsection
            subsection_start = breakdown_content.find("###", subsection_start + 1)
    
    # Keep only period rows (e.g., 2026T1); ignore any rollup rows if present.
    if resolution_data:
        original_count = len(resolution_data)
        resolution_data = [row for row in resolution_data if 'T' in row.get('Period', '')]
        if len(resolution_data) == 0 and original_count > 0:
            # If filtering removed everything, maybe the format is different - try without filter
            resolution_data = parse_markdown_table(report_content, "Time to Issue Resolution in 2022-2025", 0)
            if resolution_data:
                resolution_data = [row for row in resolution_data if 'T' in row.get('Period', '')]
    if resolution_data:
        metrics['21'] = {}
        for row in resolution_data:
            period = convert_period_format(row.get('Period', ''))
            count = clean_numeric_value(row.get('Count', ''))
            if period and count is not None:
                metrics['21'][period] = int(count)
    
    # Indicator 35: Resolution Time Average
    # Use the breakdown table (same as indicator 21)
    if resolution_data:
        metrics['35'] = {}
        for row in resolution_data:
            period = convert_period_format(row.get('Period', ''))
            ave = clean_numeric_value(row.get('Ave (days)', ''))
            if period and ave is not None:
                metrics['35'][period] = ave
    
    # Indicator 36: Resolution Time Median
    if resolution_data:
        metrics['36'] = {}
        for row in resolution_data:
            period = convert_period_format(row.get('Period', ''))
            median = clean_numeric_value(row.get('Median (days)', ''))
            if period and median is not None:
                metrics['36'][period] = median
    
    # Indicator 37: Resolution Time P80
    if resolution_data:
        metrics['37'] = {}
        for row in resolution_data:
            period = convert_period_format(row.get('Period', ''))
            p80 = clean_numeric_value(row.get('P80 (days)', ''))
            if period and p80 is not None:
                metrics['37'][period] = p80
    
    # Indicator 38: Application Time Average  
    # Extract it directly from the breakdown section (reuse the same breakdown content)
    breakdown_start = report_content.find("## Breakdown by Period within")
    breakdown_end = report_content.find("\n## Issue Reporters", breakdown_start)
    
    application_data = None
    if breakdown_start >= 0:
        if breakdown_end < 0:
            breakdown_end = len(report_content)
        breakdown_content = report_content[breakdown_start:breakdown_end]
        
        # Find the application time subsection within breakdown
        subsection_start = breakdown_content.find("###")
        while subsection_start >= 0:
            # Check if this is the application time subsection
            subsection_header = breakdown_content[subsection_start:breakdown_content.find('\n', subsection_start)]
            if 'Time to' in subsection_header and 'Issue Being Applied' in subsection_header:
                # Found it! Extract the table
                subsection_content = breakdown_content[subsection_start:]
                # Find the table
                lines = subsection_content.split('\n')
                table_start_indices = []
                for i, line in enumerate(lines):
                    if line.strip().startswith('|') and ('-' in line or ':' in line):
                        if i > 0 and lines[i-1].strip().startswith('|') and 'Period' in lines[i-1]:
                            table_start_indices.append(i-1)
                if table_start_indices:
                    start_idx = table_start_indices[0]
                    table_lines = [lines[start_idx], lines[start_idx + 1]]
                    for i in range(start_idx + 2, len(lines)):
                        line = lines[i]
                        if line.strip().startswith('|') and line.strip() != '':
                            table_lines.append(line)
                        elif line.strip() == '':
                            continue
                        elif line.strip().startswith('###') or line.strip().startswith('##'):
                            break
                        else:
                            continue
                    if len(table_lines) >= 3:
                        header_line = table_lines[0]
                        headers = [h.strip() for h in header_line.split('|')[1:-1]]
                        if len(headers) > 0:
                            rows = []
                            for line in table_lines[2:]:
                                if line.strip() and '|' in line:
                                    cells = [c.strip() for c in line.split('|')[1:-1]]
                                    if len(cells) == len(headers):
                                        row_dict = {headers[i]: cells[i] for i in range(len(headers))}
                                        rows.append(row_dict)
                            if rows:
                                application_data = rows
                                break
            # Move to next subsection
            subsection_start = breakdown_content.find("###", subsection_start + 1)
    
    # Keep only period rows (e.g., 2026T1); ignore any rollup rows if present.
    if application_data:
        original_count = len(application_data)
        application_data = [row for row in application_data if 'T' in row.get('Period', '')]
        if len(application_data) == 0 and original_count > 0:
            # If filtering removed everything, maybe the format is different - try without filter
            application_data = parse_markdown_table(report_content, "Time to (Resolved) Issue Being Applied in Specification in 2022-2025", 0)
            if application_data:
                application_data = [row for row in application_data if 'T' in row.get('Period', '')]
    
    if application_data:
        metrics['38'] = {}
        for row in application_data:
            period = convert_period_format(row.get('Period', ''))
            ave = clean_numeric_value(row.get('Ave (days)', ''))
            if period and ave is not None:
                metrics['38'][period] = ave
    
    return metrics


def read_kpi_csv(csv_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Read the KPI CSV file.
    
    Args:
        csv_path: Path to the CSV file
    
    Returns:
        Tuple of (list of row dictionaries, list of column names)
    """
    rows = []
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        for row in reader:
            rows.append(row)
    
    return rows, fieldnames


def convert_ballot_cycle_to_period(cycle: str) -> Optional[str]:
    """
    Convert ballot cycle format (YYYYMM) to period format (YYYY-T#).
    
    Ballot cycles:
    - YYYY01 (January) -> YYYY-T1
    - YYYY05 (May) -> YYYY-T2
    - YYYY09 (September) -> YYYY-T3
    
    Args:
        cycle: Ballot cycle string (e.g., "202501", "202205")
    
    Returns:
        Period string in format YYYY-T# or None if invalid
    """
    match = re.match(r'(\d{4})(\d{2})', cycle)
    if not match:
        return None
    
    year = match.group(1)
    month = match.group(2)
    
    if month == '01':
        return f"{year}-T1"
    elif month == '05':
        return f"{year}-T2"
    elif month == '09':
        return f"{year}-T3"
    
    return None


def extract_ballot_participation_metrics(report_content: str) -> Dict[str, Dict[str, float]]:
    """
    Extract metrics from a ballot participation report markdown file.
    
    Args:
        report_content: Full content of the markdown report
    
    Returns:
        Dictionary mapping indicator IDs to dictionaries of period -> value
        Format: {indicator_id: {period: value}}
    """
    metrics = {}

    # Period label as written by the analyzer's parse_time_period():
    #   - "YYYY"            (full year, e.g. 2024)
    #   - "YYYYTn"          (triannual, e.g. 2026T1)
    #   - "YYYY[Tn]-YYYY[Tn]" (range, e.g. 2022-2026 or 2022-2026T1)
    period_label_re = r'\d{4}(?:T[1-3])?(?:-\d{4}(?:T[1-3])?)?'

    # Find the "Summary for <label>" section
    summary_section_match = re.search(rf'### Summary for {period_label_re}', report_content)
    if not summary_section_match:
        return metrics
    
    # Extract the summary table
    summary_start = summary_section_match.start()
    summary_end = report_content.find('\n####', summary_start)
    if summary_end < 0:
        summary_end = report_content.find('\n##', summary_start)
    if summary_end < 0:
        summary_end = len(report_content)
    
    summary_section = report_content[summary_start:summary_end]
    
    # Parse the summary table: Cycle | Consensus Groups (N) | Total Voter Enrollment (N) | Ave per CG
    summary_table = parse_markdown_table(summary_section, "Summary for", 0)
    
    # Find the Active Voters table
    active_voters_match = re.search(rf'#### Active Voters for {period_label_re}', report_content)
    active_voters_table = None
    if active_voters_match:
        active_voters_start = active_voters_match.start()
        active_voters_end = report_content.find('\n####', active_voters_start + 1)
        if active_voters_end < 0:
            active_voters_end = report_content.find('\n##', active_voters_start)
        if active_voters_end < 0:
            active_voters_end = len(report_content)
        
        active_voters_section = report_content[active_voters_start:active_voters_end]
        active_voters_table = parse_markdown_table(active_voters_section, "Active Voters for", 0)
    
    if not summary_table:
        return metrics
    
    # Group cycles by period and aggregate metrics
    period_data = {}  # period -> {cycles: [], enrollment: set(), active_voters: set(), ave_per_cg: [], active_pct_per_cg: []}
    
    for row in summary_table:
        cycle = row.get('Cycle', '').strip()
        if not cycle:
            continue
        
        period = convert_ballot_cycle_to_period(cycle)
        if not period:
            continue
        
        if period not in period_data:
            period_data[period] = {
                'cycles': [],
                'enrollment_set': set(),  # Will track unique voters from breakdown
                'active_voters_set': set(),  # Will track unique active voters from breakdown
                'ave_per_cg': [],
                'active_pct_per_cg': []
            }
        
        period_data[period]['cycles'].append(cycle)
        ave_per_cg = clean_numeric_value(row.get('Ave per CG', ''))
        if ave_per_cg is not None:
            period_data[period]['ave_per_cg'].append(ave_per_cg)
    
    # Process Active Voters table if available
    if active_voters_table:
        for row in active_voters_table:
            cycle = row.get('Cycle', '').strip()
            if not cycle:
                continue
            
            period = convert_ballot_cycle_to_period(cycle)
            if not period or period not in period_data:
                continue
            
            active_pct_per_cg = clean_numeric_value(row.get('Active Voter % per CG (Ave)', ''))
            if active_pct_per_cg is not None:
                period_data[period]['active_pct_per_cg'].append(active_pct_per_cg)
    
    # Now we need to get unique voter counts from the breakdown table
    # Find the breakdown table
    breakdown_match = re.search(rf'#### Breakdown by Consensus Group for {period_label_re}', report_content)
    if breakdown_match:
        breakdown_start = breakdown_match.start()
        breakdown_end = report_content.find('\n####', breakdown_start + 1)
        if breakdown_end < 0:
            breakdown_end = report_content.find('\n##', breakdown_start)
        if breakdown_end < 0:
            breakdown_end = len(report_content)
        
        breakdown_section = report_content[breakdown_start:breakdown_end]
        breakdown_table = parse_markdown_table(breakdown_section, "Breakdown by Consensus Group for", 0)
        
        if breakdown_table:
            # Group by period and collect unique voters
            for row in breakdown_table:
                cycle = row.get('Cycle', '').strip()
                if not cycle:
                    continue
                
                period = convert_ballot_cycle_to_period(cycle)
                if not period or period not in period_data:
                    continue
                
                # For unique voter enrollment, we'd need the actual voter list
                # But we can approximate by using the enrollment count per CG
                # Actually, we need to sum enrollment across all CGs in the period
                # But that won't give us unique voters across CGs
                # For now, let's use the "Total Voter Enrollment (N)" from summary table
                # which should be the sum across all CGs (but may have duplicates)
                pass
    
    # Calculate metrics per period
    # Indicator 4: Balloters per Consensus Group (average) - average of "Ave per CG" across cycles
    metrics['4'] = {}
    for period, data in period_data.items():
        if data['ave_per_cg']:
            avg = sum(data['ave_per_cg']) / len(data['ave_per_cg'])
            metrics['4'][period] = avg
    
    # Indicator 39: Balloters enrolled - need unique voters across all cycles in period
    # We'll use the sum of "Total Voter Enrollment (N)" from summary table per cycle
    # Note: This may double-count voters enrolled in multiple CGs, but it's the best we can do
    # without access to individual voter lists
    metrics['39'] = {}
    for period, data in period_data.items():
        total_enrollment = 0
        for row in summary_table:
            cycle = row.get('Cycle', '').strip()
            if convert_ballot_cycle_to_period(cycle) == period:
                enrollment = clean_numeric_value(row.get('Total Voter Enrollment (N)', ''))
                if enrollment is not None:
                    total_enrollment += enrollment
        if total_enrollment > 0:
            metrics['39'][period] = int(total_enrollment)
    
    # Indicator 40: Active voters - sum of "Active Voters (N)" from active voters table
    metrics['40'] = {}
    if active_voters_table:
        for period, data in period_data.items():
            total_active = 0
            for row in active_voters_table:
                cycle = row.get('Cycle', '').strip()
                if convert_ballot_cycle_to_period(cycle) == period:
                    active = clean_numeric_value(row.get('Active Voters (N)', ''))
                    if active is not None:
                        total_active += active
            if total_active > 0:
                metrics['40'][period] = int(total_active)
    
    # Indicator 41: Active voters percent - calculate from enrollment and active voters
    metrics['41'] = {}
    for period in period_data.keys():
        if period in metrics['39'] and period in metrics['40']:
            enrollment = metrics['39'][period]
            active = metrics['40'][period]
            if enrollment > 0:
                pct = (active / enrollment) * 100
                metrics['41'][period] = pct
    
    # Indicator 42: Active voters % per CG average - average of "Active Voter % per CG (Ave)" across cycles
    metrics['42'] = {}
    for period, data in period_data.items():
        if data['active_pct_per_cg']:
            avg = sum(data['active_pct_per_cg']) / len(data['active_pct_per_cg'])
            metrics['42'][period] = avg
    
    return metrics


def get_indicator_template(indicator_id: str) -> Dict[str, str]:
    """
    Get default field values for an indicator ID.
    This defines the structure for each indicator type.
    
    Args:
        indicator_id: The indicator ID
    
    Returns:
        Dictionary with default field values for this indicator
    """
    templates = {
        '19': {
            'ID': '19',
            'Domain': 'Global Engagement',
            'Indicator': 'Issue submitters',
            'Type': 'N',
            'Unit': 'count',
            'Notes': '',
            'Steward': 'Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'KPI;ISSUES',
            'Direction': 'higher',
            'Image': ''
        },
        '20': {
            'ID': '20',
            'Domain': 'Global Engagement',
            'Indicator': 'Issue submitters: New',
            'Type': '%',
            'Unit': '%',
            'Notes': '',
            'Steward': 'Standards Development',
            'Target': '20',
            'Target Type': 'period',
            'Target Operation': '',
            'Tags': 'KPI;ISSUES',
            'Direction': 'higher',
            'Image': ''
        },
        '21': {
            'ID': '21',
            'Domain': 'Standards Development',
            'Indicator': 'Issues resolved',
            'Type': 'N',
            'Unit': 'issues',
            'Notes': '',
            'Steward': 'HL7; Standards Development',
            'Target': '1500',
            'Target Type': 'period',
            'Target Operation': '',
            'Tags': 'KPI;ISSUES',
            'Direction': 'higher',
            'Image': ''
        },
        '35': {
            'ID': '35',
            'Domain': 'Standards Development',
            'Indicator': 'Resolution Time: Average',
            'Type': 'days',
            'Unit': 'average',
            'Notes': '',
            'Steward': 'HL7; Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'ISSUES',
            'Direction': 'lower',
            'Image': ''
        },
        '36': {
            'ID': '36',
            'Domain': 'Standards Development',
            'Indicator': 'Resolution Time: Median',
            'Type': 'days',
            'Unit': 'median',
            'Notes': '',
            'Steward': 'HL7; Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'ISSUES',
            'Direction': 'lower',
            'Image': ''
        },
        '37': {
            'ID': '37',
            'Domain': 'Standards Development',
            'Indicator': 'Resolution Time: P80',
            'Type': 'days',
            'Unit': 'P80',
            'Notes': '',
            'Steward': 'HL7; Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'ISSUES',
            'Direction': 'lower',
            'Image': ''
        },
        '38': {
            'ID': '38',
            'Domain': 'Standards Development',
            'Indicator': 'Resolution to Application Time: Average',
            'Type': 'days',
            'Unit': 'average',
            'Notes': '',
            'Steward': 'HL7; Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'ISSUES',
            'Direction': 'lower',
            'Image': ''
        },
        '4': {
            'ID': '4',
            'Domain': 'Global Engagement',
            'Indicator': 'Balloters',
            'Type': 'per Consensus Group',
            'Unit': 'average',
            'Notes': '',
            'Steward': 'Standards Development',
            'Target': '100',
            'Target Type': 'period',
            'Target Operation': '',
            'Tags': 'KPI;BALLOTS',
            'Direction': 'higher',
            'Image': ''
        },
        '39': {
            'ID': '39',
            'Domain': 'Standards Development',
            'Indicator': 'Balloters enrolled',
            'Type': 'N',
            'Unit': 'count',
            'Notes': '',
            'Steward': 'Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'BALLOTS',
            'Direction': 'higher',
            'Image': ''
        },
        '40': {
            'ID': '40',
            'Domain': 'Standards Development',
            'Indicator': 'Active voters',
            'Type': 'N',
            'Unit': 'count',
            'Notes': '',
            'Steward': 'Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'BALLOTS',
            'Direction': 'higher',
            'Image': ''
        },
        '41': {
            'ID': '41',
            'Domain': 'Standards Development',
            'Indicator': 'Active voters',
            'Type': '%',
            'Unit': '%',
            'Notes': '',
            'Steward': 'Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'BALLOTS',
            'Direction': 'higher',
            'Image': ''
        },
        '42': {
            'ID': '42',
            'Domain': 'Standards Development',
            'Indicator': 'Active voters % per CG',
            'Type': '%',
            'Unit': 'average',
            'Notes': '',
            'Steward': 'Standards Development',
            'Target': '',
            'Target Type': '',
            'Target Operation': '',
            'Tags': 'BALLOTS',
            'Direction': 'higher',
            'Image': ''
        }
    }
    
    return templates.get(indicator_id, {})


def update_kpi_csv(rows: List[Dict[str, str]], metrics: Dict[str, Dict[str, float]], 
                   indicator_ids: List[str], fieldnames: List[str]) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    """
    Update KPI CSV rows with extracted metrics. Adds new rows for periods that don't exist.
    
    Args:
        rows: List of row dictionaries from the CSV
        metrics: Dictionary mapping indicator IDs to period -> value dictionaries
        indicator_ids: List of indicator IDs to update
        fieldnames: List of column names from the CSV
    
    Returns:
        Tuple of (updated list of row dictionaries, dictionary of update counts by indicator)
    """
    updated_rows = []
    update_counts = {indicator_id: 0 for indicator_id in indicator_ids}
    
    # Track which indicator+period combinations we've updated
    updated_keys = set()
    
    # First pass: update existing rows
    for row in rows:
        indicator_id = row.get('ID', '').strip()
        period_raw = row.get('Time Period', '').strip()
        # Normalize period format for comparison
        period = convert_period_format(period_raw)
        key = (indicator_id, period)
        
        # Check if this row should be updated
        if indicator_id in indicator_ids and indicator_id in metrics:
            period_metrics = metrics[indicator_id]
            
            # Update value if period matches
            if period in period_metrics:
                # Create a copy of the row and update the value
                updated_row = row.copy()
                new_value = str(period_metrics[period])
                old_value = updated_row.get('Value', '')
                updated_row['Value'] = new_value
                updated_rows.append(updated_row)
                updated_keys.add(key)
                update_counts[indicator_id] += 1
            else:
                # Keep existing row if period doesn't match
                updated_rows.append(row)
        else:
            # Keep existing row if indicator ID doesn't match
            updated_rows.append(row)
    
    # Second pass: add new rows for periods that don't exist
    for indicator_id in indicator_ids:
        if indicator_id not in metrics:
            continue
        
        # Always get the correct template from get_indicator_template to ensure correct indicator name
        template_dict = get_indicator_template(indicator_id)
        if not template_dict:
            print(f"  Warning: No template found for indicator {indicator_id}, skipping")
            continue
        
        # Try to find an existing row to copy other fields (but we'll override key fields with template)
        existing_row = None
        for row in rows:
            if row.get('ID', '').strip() == indicator_id:
                existing_row = row.copy()
                break
        
        # Create template row: use existing row if found, but always override with correct template values
        if existing_row:
            # Start with existing row, but override key fields from template to ensure correctness
            template_row = existing_row.copy()
            # Override key fields that should always come from the template
            for key_field in ['Indicator', 'Domain', 'Type', 'Unit', 'Steward', 'Tags', 'Direction']:
                if key_field in template_dict:
                    template_row[key_field] = template_dict[key_field]
        else:
            # No existing row, create template from dictionary
            template_row = {field: template_dict.get(field, '') for field in fieldnames}
        
        # Add rows for periods that don't exist
        for period, value in metrics[indicator_id].items():
            key = (indicator_id, period)
            if key not in updated_keys:
                # Create new row based on template
                new_row = template_row.copy()
                new_row['Time Period'] = period
                new_row['Value'] = str(value)
                # Ensure all fields are present
                for field in fieldnames:
                    if field not in new_row:
                        new_row[field] = ''
                updated_rows.append(new_row)
                update_counts[indicator_id] += 1
    
    return updated_rows, update_counts


def write_kpi_csv(rows: List[Dict[str, str]], fieldnames: List[str], output_path: Path):
    """
    Write updated KPI CSV file.
    
    Args:
        rows: List of row dictionaries
        fieldnames: List of column names
        output_path: Path to write the CSV file
    """
    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

def maybe_create_backup(input_path: Path, backup_arg: Optional[str]) -> Optional[Path]:
    """
    Optionally create a timestamped backup of the input KPI CSV before modifications.

    backup_arg behavior:
      - None: no backup
      - "" or ".": backup alongside input file
      - any other string: treat as directory to place backup
    """
    if backup_arg is None:
        return None

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_dir = input_path.parent if backup_arg in ("", ".") else Path(backup_arg)
    backup_dir.mkdir(parents=True, exist_ok=True)

    backup_name = f"{ts}-{input_path.stem}-bak.csv"
    backup_path = backup_dir / backup_name
    shutil.copy2(input_path, backup_path)
    return backup_path


def main():
    parser = argparse.ArgumentParser(
        description='Extract metrics from HL7 reports and update KPI tracking CSV',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update KPIs from issue report
  python scripts/kpi-update-from-reports.py \\
      --issue-report data/working/issue-analysis/2025/2025-AllYear/finals/2022to2025-issue-report.md \\
      --kpi-csv data/working/issue-analysis/2025/2025-AllYear/finals/new_kpis.csv \\
      --output data/working/issue-analysis/2025/2025-AllYear/finals/new_kpis_updated.csv

  # Update KPIs in-place (and create a backup alongside input)
  python scripts/kpi-update-from-reports.py \\
      --issue-report data/working/issue-analysis/2025/2025-AllYear/finals/2022to2025-issue-report.md \\
      -i data/working/issue-analysis/2025/2025-AllYear/finals/new_kpis.csv \\
      --backup
        """
    )
    
    parser.add_argument(
        '--issue-report',
        type=str,
        help='Path to issue report markdown file'
    )
    
    parser.add_argument(
        '--pss-report',
        type=str,
        help='Path to PSS report markdown file (future extension)'
    )
    
    parser.add_argument(
        '--ballot-report',
        type=str,
        help='Path to ballot participation report markdown file (future extension)'
    )
    
    parser.add_argument(
        '--kpi-csv',
        '-i',
        type=str,
        required=True,
        help='Path to input KPI CSV file'
    )
    
    parser.add_argument(
        '--output',
        '-o',
        type=str,
        required=False,
        default=None,
        help='Path to output updated KPI CSV file (default: overwrite input file)'
    )

    parser.add_argument(
        '--backup',
        nargs='?',
        const='.',
        default=None,
        help='Create a timestamped backup of the input KPI CSV before processing. '
             'Optionally provide a directory (default: alongside input).'
    )
    
    parser.add_argument(
        '--indicators',
        type=str,
        nargs='+',
        help='Specific indicator IDs to update (default: all from reports)'
    )
    
    args = parser.parse_args()
    
    # Read the KPI CSV
    kpi_csv_path = Path(args.kpi_csv)
    if not kpi_csv_path.exists():
        print(f"Error: KPI CSV file not found: {kpi_csv_path}", file=sys.stderr)
        sys.exit(1)

    backup_path = maybe_create_backup(kpi_csv_path, args.backup)
    if backup_path:
        print(f"Backup created: {backup_path}")
    
    print(f"Reading KPI CSV from {kpi_csv_path}")
    rows, fieldnames = read_kpi_csv(kpi_csv_path)
    
    # Collect metrics from all report types
    all_metrics = {}
    indicator_ids_to_update = set()
    
    # Extract from issue report
    if args.issue_report:
        issue_report_path = Path(args.issue_report)
        if not issue_report_path.exists():
            print(f"Warning: Issue report not found: {issue_report_path}", file=sys.stderr)
        else:
            print(f"Extracting metrics from issue report: {issue_report_path}")
            with open(issue_report_path, 'r', encoding='utf-8') as f:
                report_content = f.read()
            
            issue_metrics = extract_issue_report_metrics(report_content)
            all_metrics.update(issue_metrics)
            indicator_ids_to_update.update(issue_metrics.keys())
            
            print(f"  Found metrics for indicators: {sorted(issue_metrics.keys())}")
    
    # Future: Extract from PSS report
    if args.pss_report:
        print("PSS report extraction not yet implemented", file=sys.stderr)
    
    # Extract from ballot participation report
    if args.ballot_report:
        ballot_report_path = Path(args.ballot_report)
        if not ballot_report_path.exists():
            print(f"Warning: Ballot report not found: {ballot_report_path}", file=sys.stderr)
        else:
            print(f"Extracting metrics from ballot participation report: {ballot_report_path}")
            with open(ballot_report_path, 'r', encoding='utf-8') as f:
                report_content = f.read()
            
            ballot_metrics = extract_ballot_participation_metrics(report_content)
            all_metrics.update(ballot_metrics)
            indicator_ids_to_update.update(ballot_metrics.keys())
            
            print(f"  Found metrics for indicators: {sorted(ballot_metrics.keys())}")
    
    # Filter indicators if specified
    if args.indicators:
        indicator_ids_to_update = indicator_ids_to_update.intersection(set(args.indicators))
        # Also filter metrics dictionary
        all_metrics = {k: v for k, v in all_metrics.items() if k in indicator_ids_to_update}
    
    if not all_metrics:
        print("Warning: No metrics found to update", file=sys.stderr)
        # Still write the output file (copy of input), defaulting to input path
        output_path = Path(args.output) if args.output else kpi_csv_path
        write_kpi_csv(rows, fieldnames, output_path)
        sys.exit(0)
    
    print(f"Updating indicators: {sorted(indicator_ids_to_update)}")
    
    
    # Update the CSV
    updated_rows, update_counts = update_kpi_csv(rows, all_metrics, list(indicator_ids_to_update), fieldnames)
    
    # Write the output
    output_path = Path(args.output) if args.output else kpi_csv_path
    print(f"Writing updated KPI CSV to {output_path}")
    write_kpi_csv(updated_rows, fieldnames, output_path)
    
    # Print summary
    print("\nUpdate summary:")
    for indicator_id in sorted(indicator_ids_to_update):
        total_periods = len(all_metrics.get(indicator_id, {}))
        updated_count = update_counts.get(indicator_id, 0)
        print(f"  Indicator {indicator_id}: Updated {updated_count} of {total_periods} period(s)")
    
    print(f"\nDone! Updated CSV written to {output_path}")


if __name__ == '__main__':
    main()
