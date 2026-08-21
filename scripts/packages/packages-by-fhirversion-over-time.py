#!/usr/bin/env python3
# =============================================================================
# Packages by FHIR Version Over Time
#
# Reads package data (e.g. from packages.fhir.org JSON export) and outputs:
# 1. A CSV showing number of FHIR packages by fhirversion over time (e.g. 2025-T1, 2025-T2)
# 2. Command-line summary of total packages by fhirversion
# 3. Optional KPI CSV with cumulative total and newly published packages by period,
#    filtered by major FHIR versions (R4=4.0.1, R4B=4.3.0, R5=5.0.0)
#
# === Usage ===
# python scripts/packages/packages-by-fhirversion-over-time.py \
#     --input data/working/packages/20260117-packages.fhir.org-packages.json \
#     --output data/working/packages/packages-by-fhirversion-over-time.csv \
#     [--kpi-csv data/working/packages/package-kpis.csv] \
#     [-p 2020-2026]
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import csv
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# Major FHIR version mapping: fhirVersion string -> display label
FHIR_VERSION_LABELS: Dict[str, str] = {
    "4.0.1": "R4",
    "4.3.0": "R4B",
    "5.0.0": "R5",
}


def parse_package_date(date_str: str) -> Optional[datetime]:
    """
    Parse a package date string (ISO format) to datetime.
    """
    if not date_str:
        return None
    try:
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def date_to_period(dt: datetime) -> str:
    """
    Convert a datetime to a period string (YYYY-T1, YYYY-T2, YYYY-T3).
    T1: Jan 1 - Apr 30
    T2: May 1 - Aug 31
    T3: Sep 1 - Dec 31
    """
    month = dt.month
    year = dt.year
    if month <= 4:
        return f"{year}-T1"
    elif month <= 8:
        return f"{year}-T2"
    else:
        return f"{year}-T3"


def parse_time_period(period_str: str) -> Tuple[datetime, datetime]:
    """
    Parse a period string (YYYY-T1, YYYY-T2, YYYY-T3) into start and end datetimes.
    T1: Jan 1 - Apr 30, T2: May 1 - Aug 31, T3: Sep 1 - Dec 31
    """
    tri_match = re.match(r"^(\d{4})-T([1-3])$", period_str)
    if not tri_match:
        raise ValueError(f"Invalid period format: {period_str}")
    year = int(tri_match.group(1))
    tri = tri_match.group(2)
    if tri == "1":
        start = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(year, 4, 30, 23, 59, 59, tzinfo=timezone.utc)
    elif tri == "2":
        start = datetime(year, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(year, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
    else:  # T3
        start = datetime(year, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
        end = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
    return start, end


def expand_periods(period_str: str) -> List[str]:
    """
    Expand a period string into a list of individual periods.
    Examples: '2022-2025' -> ['2022-T1', '2022-T2', ..., '2025-T3']
    """
    # Range format: '2022-2025' or '2022T1-2025T3'
    range_match = re.match(r'^(\d{4})(T[1-3])?-(\d{4})(T[1-3])?$', period_str)
    if range_match:
        start_year = int(range_match.group(1))
        start_tri = range_match.group(2)
        end_year = int(range_match.group(3))
        end_tri = range_match.group(4)

        start_tri_num = int(start_tri[1]) if start_tri else 1
        end_tri_num = int(end_tri[1]) if end_tri else 3

        periods = []
        for year in range(start_year, end_year + 1):
            tri_start = start_tri_num if year == start_year else 1
            tri_end = end_tri_num if year == end_year else 3
            for tri in range(tri_start, tri_end + 1):
                periods.append(f"{year}-T{tri}")
        return periods

    # Full year format: '2024'
    full_year_match = re.match(r'^(\d{4})$', period_str)
    if full_year_match:
        year = int(full_year_match.group(1))
        return [f"{year}-T1", f"{year}-T2", f"{year}-T3"]

    # Single period format: '2025-T3' or '2025T3'
    tri_match = re.match(r'^(\d{4})[-T]T?([1-3])$', period_str)
    if tri_match:
        year = int(tri_match.group(1))
        tri = tri_match.group(2)
        return [f"{year}-T{tri}"]

    raise ValueError(f"Invalid period format: {period_str}")


def load_packages(path: Path) -> List[Dict]:
    """Load package data from JSON file."""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data)}")
    return data


def _filter_packages_by_fhirversion(
    packages: List[Dict],
    fhirversions: Optional[Set[str]] = None,
) -> List[Dict]:
    """Filter packages to those whose fhirVersion is in fhirversions (if provided)."""
    if not fhirversions:
        return packages
    result = []
    for pkg in packages:
        fv = (pkg.get("fhirVersion") or pkg.get("fhirversion") or "").strip()
        if fv in fhirversions:
            result.append(pkg)
    return result


def calculate_kpi_metrics(
    packages: List[Dict],
    periods: List[str],
    fhirversions: Optional[Set[str]] = None,
) -> Tuple[Dict[str, int], Dict[str, int]]:
    """
    Calculate KPI metrics: total package versions (cumulative) and new package versions (within period).
    If fhirversions is provided, filter to only those FHIR versions (e.g. {"4.0.1", "4.3.0", "5.0.0"}).
    Returns: (total_by_period, new_by_period)
    """
    filtered = _filter_packages_by_fhirversion(packages, fhirversions)

    package_versions: Dict[Tuple[str, str], datetime] = {}  # (name, version) -> date

    for pkg in filtered:
        name = (pkg.get("name") or "").strip()
        version = (pkg.get("version") or "").strip()
        date_str = pkg.get("date", "")

        if not name or not version or not date_str:
            continue

        dt = parse_package_date(date_str)
        if not dt:
            continue

        key = (name, version)
        if key not in package_versions or dt < package_versions[key]:
            package_versions[key] = dt

    def period_sort_key(p: str) -> Tuple[int, int]:
        y, t = p.split("-T")
        return (int(y), int(t))

    sorted_periods = sorted(periods, key=period_sort_key)
    total_by_period: Dict[str, int] = {}
    new_by_period: Dict[str, int] = {}

    for period in sorted_periods:
        try:
            period_start, period_end = parse_time_period(period)
        except ValueError:
            continue

        total_versions = set()
        new_versions = set()

        for (name, version), version_date in package_versions.items():
            if version_date <= period_end:
                total_versions.add((name, version))
            if period_start <= version_date <= period_end:
                new_versions.add((name, version))

        total_by_period[period] = len(total_versions)
        new_by_period[period] = len(new_versions)

    return total_by_period, new_by_period


def compute_metrics(
    packages: List[Dict],
    periods: List[str],
) -> Tuple[Dict[str, Dict[str, int]], Dict[str, int]]:
    """
    Compute package counts by fhirversion and period.
    Returns: (period_matrix, total_by_fhirversion)
    - period_matrix: fhirversion -> period -> count
    - total_by_fhirversion: fhirversion -> total count
    """
    # (fhirversion, period) -> count
    matrix: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    total_by_fhirversion: Dict[str, int] = defaultdict(int)

    periods_set = set(periods)

    for pkg in packages:
        fhir_version = (pkg.get('fhirVersion') or pkg.get('fhirversion') or '').strip()
        date_str = pkg.get('date', '')

        if not fhir_version:
            continue

        dt = parse_package_date(date_str)
        if not dt:
            continue

        period = date_to_period(dt)
        if period in periods_set:
            matrix[fhir_version][period] += 1

        total_by_fhirversion[fhir_version] += 1

    return dict(matrix), dict(total_by_fhirversion)


# all_kpis.csv fieldnames (definitive format - do not add fields)
KPI_FIELDNAMES = [
    "ID", "Time Period", "Domain", "Indicator", "Type", "Unit", "Value",
    "Notes", "Steward", "Target", "Target Type", "Target Operation", "Tags",
    "Direction", "Image",
]


def write_kpi_csv(
    kpi_rows: List[Dict[str, str]],
    output_path: Path,
) -> None:
    """Write KPI CSV in all_kpis.csv format."""
    with open(output_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=KPI_FIELDNAMES, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(kpi_rows)


def write_csv(
    period_matrix: Dict[str, Dict[str, int]],
    periods: List[str],
    output_path: Path,
) -> None:
    """Write CSV with fhirversion as rows, periods as columns."""
    fieldnames = ['fhirversion'] + periods

    with open(output_path, 'w', encoding='utf-8', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        # Sort fhirversions - normalize for sorting (e.g. 4.0.1 before 4.3.0)
        def sort_key(fv: str) -> Tuple[int, ...]:
            parts = []
            for part in re.split(r'[.-]', fv):
                if part.isdigit():
                    parts.append(int(part))
                else:
                    parts.append(0 if 'ballot' in part.lower() else -1)
            return tuple(parts)

        for fv in sorted(period_matrix.keys(), key=sort_key):
            row = {'fhirversion': fv}
            for period in periods:
                row[period] = period_matrix[fv].get(period, 0)
            writer.writerow(row)


def main() -> None:
    parser = argparse.ArgumentParser(
        description='Summarize FHIR packages by fhirversion over time',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/packages/packages-by-fhirversion-over-time.py \\
      --input data/working/packages/20260117-packages.fhir.org-packages.json \\
      --output data/working/packages/packages-by-fhirversion-over-time.csv

  python scripts/packages/packages-by-fhirversion-over-time.py \\
      --input data/working/packages/20260117-packages.fhir.org-packages.json \\
      --output packages-by-fhirversion.csv -p 2020-2026
        """,
    )
    parser.add_argument(
        '--input',
        type=str,
        required=True,
        help='Path to packages JSON file',
    )
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Path to output CSV file',
    )
    parser.add_argument(
        "-p",
        "--periods",
        type=str,
        default="2015-2030",
        help="Time periods to include (e.g. 2020-2026, 2024T3). Default: 2015-2030",
    )
    parser.add_argument(
        "--kpi-csv",
        type=str,
        help="Path to output KPI CSV in all_kpis.csv format. Outputs Package versions R4/R4B/R5 and Package versions: New R4/R4B/R5.",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    if not input_path.exists():
        print(f"Error: Input file not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    print(f"Loading packages from {input_path}...")
    packages = load_packages(input_path)
    print(f"  Loaded {len(packages)} package versions")

    try:
        periods = expand_periods(args.periods)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    periods = sorted(periods)
    print(f"  Periods: {', '.join(periods)}")

    print("\nComputing metrics...")
    period_matrix, total_by_fhirversion = compute_metrics(packages, periods)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_csv(period_matrix, periods, output_path)
    print(f"\nWrote CSV to {output_path}")

    # KPI CSV output in all_kpis.csv format (Package versions R4/R4B/R5, Package versions: New R4/R4B/R5)
    if args.kpi_csv:
        kpi_rows: List[Dict[str, str]] = []
        # ID allocation: 47-48 R4, 49-50 R4B, 51-52 R5
        def kpi_row(indicator_id: str, period: str, indicator: str, value: str) -> Dict[str, str]:
            return {
                "ID": indicator_id,
                "Time Period": period,
                "Domain": "Standards Development",
                "Indicator": indicator,
                "Type": "N",
                "Unit": "count",
                "Value": value,
                "Notes": "",
                "Steward": "Standards Development",
                "Target": "",
                "Target Type": "",
                "Target Operation": "",
                "Tags": "ECOSYSTEM",
                "Direction": "higher",
                "Image": "",
            }
        id_base = 47
        for i, (fv, ver_label) in enumerate(FHIR_VERSION_LABELS.items()):
            tot, new = calculate_kpi_metrics(packages, periods, fhirversions={fv})
            total_id = str(id_base + i * 2)
            new_id = str(id_base + i * 2 + 1)
            for period in periods:
                kpi_rows.append(kpi_row(total_id, period, f"Package versions {ver_label}", str(tot.get(period, 0))))
                kpi_rows.append(kpi_row(new_id, period, f"Package versions: New {ver_label}", str(new.get(period, 0))))

        kpi_path = Path(args.kpi_csv)
        kpi_path.parent.mkdir(parents=True, exist_ok=True)
        write_kpi_csv(kpi_rows, kpi_path)
        print(f"Wrote KPI CSV to {kpi_path}")

    # Command-line summary: total packages by fhirversion
    print("\n" + "=" * 50)
    print("Total packages by fhirversion")
    print("=" * 50)

    def sort_key(fv: str) -> Tuple[int, ...]:
        parts = []
        for part in re.split(r'[.-]', fv):
            if part.isdigit():
                parts.append(int(part))
            else:
                parts.append(0 if 'ballot' in part.lower() else -1)
        return tuple(parts)

    for fv in sorted(total_by_fhirversion.keys(), key=sort_key):
        count = total_by_fhirversion[fv]
        print(f"  {fv}: {count}")

    print("=" * 50)
    print(f"  TOTAL: {sum(total_by_fhirversion.values())} package versions")
    print("=" * 50)
    print("\nDone.")


if __name__ == '__main__':
    main()
