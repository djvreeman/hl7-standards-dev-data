#!/usr/bin/env python3
# =============================================================================
# Calculate Package Indicators
#
# This script fetches package data from packages2.fhir.org and calculates
# four ecosystem indicators:
# - ID 43: Packages (total unique packages)
# - ID 44: Packages: New (new packages in period)
# - ID 45: Package versions (total package versions)
# - ID 46: Package versions: New (new package versions in period)
# - ID 49: Package versions: New R4
# - ID 50: Package versions: New R4B
# - ID 51: Package versions: New R5
# - ID 52: Package versions: Total R4 (cumulative)
# - ID 53: Package versions: Total R4B (cumulative)
# - ID 54: Package versions: Total R5 (cumulative)
#
# FHIR version mapping: 4.0.1→R4, 4.3.0→R4B, 5.0.0→R5
#
# === Usage ===
# python scripts/packages/calculate-package-indicators.py \
#     --kpi-csv data/working/indicators/all_kpis.csv \
#     --output data/working/indicators/all_kpis_updated.csv \
#     [--packages-json data/working/packages/20260117-packages.fhir.org-packages.json]
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
from urllib.request import urlopen
from urllib.error import URLError

# Major FHIR version mapping: fhirVersion string -> indicator label (R4, R4B, R5)
FHIR_VERSION_TO_LABEL: Dict[str, str] = {
    "4.0.1": "R4",
    "4.3.0": "R4B",
    "5.0.0": "R5",
}
# Exact fhirVersion values we track for indicators 49-54
FHIR_VERSIONS_FOR_INDICATORS: Set[str] = set(FHIR_VERSION_TO_LABEL.keys())


def parse_time_period(period_str: str) -> Tuple[datetime, datetime]:
    """
    Parse a time period string like '2025-T3', '2025T3', '2024', or '2022-2025' into start and end dates.
    
    Time periods:
    - T1: Jan 1 to Apr 30
    - T2: May 1 to Aug 31
    - T3: Sep 1 to Dec 31
    
    Args:
        period_str: Period string in format:
            - YYYY-T[1-3] or YYYYT[1-3] (e.g., '2025-T3' or '2025T3')
            - YYYY (full year)
            - YYYY[-T[1-3]]-YYYY[-T[1-3]] (range, e.g., '2022-2025' or '2022T1-2025T3')
    
    Returns:
        Tuple of (start_date, end_date) as timezone-aware datetime objects (UTC)
    """
    from datetime import timezone
    import re
    
    # Range format: '2022-2025' or '2022T1-2025T3'
    range_match = re.match(r'^(\d{4}(?:T[1-3])?)-(\d{4}(?:T[1-3])?)$', period_str)
    if range_match:
        start_period = range_match.group(1)
        end_period = range_match.group(2)
        
        # Parse start and end dates
        start_date, _ = parse_time_period(start_period)
        _, end_date = parse_time_period(end_period)
        
        return start_date, end_date
    
    # Full year format: '2024'
    full_year_match = re.match(r'^(\d{4})$', period_str)
    if full_year_match:
        year = int(full_year_match.group(1))
        start_date = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
        end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        return start_date, end_date
    
    # Period format: '2025-T3' or '2025T3'
    tri_match = re.match(r'^(\d{4})[-T]T?([1-3])$', period_str)
    if tri_match:
        year = int(tri_match.group(1))
        tri = tri_match.group(2)
        
        if tri == '1':
            # T1: Jan 1 00:00:00 to Apr 30 23:59:59
            start_date = datetime(year, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 4, 30, 23, 59, 59, tzinfo=timezone.utc)
        elif tri == '2':
            # T2: May 1 00:00:00 to Aug 31 23:59:59
            start_date = datetime(year, 5, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 8, 31, 23, 59, 59, tzinfo=timezone.utc)
        elif tri == '3':
            # T3: Sep 1 00:00:00 to Dec 31 23:59:59
            start_date = datetime(year, 9, 1, 0, 0, 0, tzinfo=timezone.utc)
            end_date = datetime(year, 12, 31, 23, 59, 59, tzinfo=timezone.utc)
        
        return start_date, end_date
    
    raise ValueError(f"Invalid time period format: {period_str}. Use 'YYYY', 'YYYYT[1-3]', 'YYYY-T[1-3]', or 'YYYY[-T[1-3]]-YYYY[-T[1-3]]'")


def expand_periods(period_str: str) -> List[str]:
    """
    Expand a period string into a list of individual periods.
    
    Examples:
    - '2022-2025' -> ['2022-T1', '2022-T2', '2022-T3', '2023-T1', ..., '2025-T3']
    - '2024T3' -> ['2024-T3']
    - '2024' -> ['2024-T1', '2024-T2', '2024-T3']
    
    Args:
        period_str: Period string (range, single period, or full year)
    
    Returns:
        List of period strings in format 'YYYY-T[1-3]'
    """
    import re
    
    # Range format: '2022-2025' or '2022T1-2025T3'
    range_match = re.match(r'^(\d{4})(T[1-3])?-(\d{4})(T[1-3])?$', period_str)
    if range_match:
        start_year = int(range_match.group(1))
        start_tri = range_match.group(2)
        end_year = int(range_match.group(3))
        end_tri = range_match.group(4)
        
        periods = []
        
        # Determine start tri
        if start_tri:
            start_tri_num = int(start_tri[1])
        else:
            start_tri_num = 1
        
        # Determine end tri
        if end_tri:
            end_tri_num = int(end_tri[1])
        else:
            end_tri_num = 3
        
        # Generate all periods in range
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


def fetch_ig_registry_data() -> Tuple[Set[str], Dict[str, str]]:
    """
    Fetch the FHIR IG registry and extract package names and canonical URLs.
    
    Sources package names from:
    - 'npm-name' field in each guide
    - 'package' field in each edition (format: "package-name#version")
    
    Returns:
        Tuple of (set of unique package names, dict mapping package_name -> canonical_url)
    """
    from urllib.request import Request
    
    registry_url = "https://raw.githubusercontent.com/FHIR/ig-registry/master/fhir-ig-list.json"
    
    print(f"Fetching IG registry from {registry_url}...")
    
    try:
        req = Request(registry_url)
        req.add_header('Accept', 'application/json')
        
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read())
            
            package_names = set()
            package_to_canonical = {}  # Map package name -> canonical URL
            
            guides = data.get('guides', [])
            
            for guide in guides:
                canonical_url = guide.get('canonical', '').strip()
                
                # Get npm-name if available
                npm_name = guide.get('npm-name', '').strip()
                if npm_name:
                    package_names.add(npm_name)
                    if canonical_url:
                        package_to_canonical[npm_name] = canonical_url
                
                # Get package names from editions
                editions = guide.get('editions', [])
                for edition in editions:
                    package_str = edition.get('package', '').strip()
                    if package_str:
                        # Format is "package-name#version", extract just the name
                        if '#' in package_str:
                            pkg_name = package_str.split('#')[0].strip()
                            if pkg_name:
                                package_names.add(pkg_name)
                                if canonical_url:
                                    package_to_canonical[pkg_name] = canonical_url
            
            print(f"  Found {len(package_names)} unique package names")
            print(f"  Found {len(package_to_canonical)} package-to-canonical mappings")
            return package_names, package_to_canonical
            
    except Exception as e:
        print(f"Error fetching IG registry: {e}", file=sys.stderr)
        sys.exit(1)


def fetch_ig_registry_package_names() -> Set[str]:
    """
    Fetch the FHIR IG registry and extract all unique package names.
    
    Returns:
        Set of unique package names
    """
    package_names, _ = fetch_ig_registry_data()
    return package_names


def fetch_package_versions_from_package_list(canonical_url: str, package_name: str) -> Tuple[List[Dict], Optional[str]]:
    """
    Fetch package versions from package-list.json at the canonical URL.
    
    Args:
        canonical_url: Canonical URL of the IG (e.g., "http://hl7.org/fhir/us/core")
        package_name: Name of the package
    
    Returns:
        Tuple of (list of package version dictionaries, error_message)
    """
    from urllib.request import Request
    from urllib.error import HTTPError
    
    # Try package-list.json at canonical URL
    package_list_url = canonical_url.rstrip('/') + '/package-list.json'
    
    try:
        req = Request(package_list_url)
        req.add_header('Accept', 'application/json')
        
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read())
            
            versions = []
            package_list = data.get('list', [])
            
            for entry in package_list:
                version = entry.get('version', '').strip()
                date_str = entry.get('date', '').strip()
                fhir_version = entry.get('fhir-version') or entry.get('fhirVersion') or entry.get('fhirversion') or ''
                if isinstance(fhir_version, list):
                    fhir_version = fhir_version[0] if fhir_version else ''
                fhir_version = str(fhir_version).strip() if fhir_version else ''
                
                if version and date_str:
                    versions.append({
                        'name': package_name,
                        'version': version,
                        'date': date_str,
                        'fhirVersion': fhir_version,
                    })
            
            if versions:
                return versions, None
            else:
                return [], f"No versions found in package-list.json"
                
    except HTTPError as e:
        error_msg = f"HTTP {e.code}: {e.reason}"
        return [], error_msg
    except URLError as e:
        error_msg = f"URL Error: {str(e)}"
        return [], error_msg
    except json.JSONDecodeError as e:
        error_msg = f"JSON decode error: {str(e)}"
        return [], error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        return [], error_msg


def fetch_package_versions(
    package_name: str,
    cache_dir: Optional[Path] = None,
    canonical_url: Optional[str] = None,
    refresh_cache: bool = False,
) -> Tuple[List[Dict], Optional[str]]:
    """
    Fetch all versions for a specific package from packages2.fhir.org.
    
    Uses NPM-compatible endpoint: GET /packages/{package-name}
    Response format: { "name": "...", "versions": { "version": {...}, ... } }
    
    If the package returns 404 and canonical_url is provided, falls back to fetching
    package-list.json from the canonical URL.
    
    Args:
        package_name: Name of the package (e.g., "hl7.fhir.us.core")
        cache_dir: Optional directory to cache package version data
        canonical_url: Optional canonical URL for fallback fetching (e.g., "http://hl7.org/fhir/us/core")
        refresh_cache: If True, ignore any existing cached package data and fetch fresh from API
    
    Returns:
        Tuple of (list of package version dictionaries, error_message)
        - versions: List with 'name', 'version', and 'date' fields
        - error_message: None if successful, error description if failed
    """
    from urllib.request import Request
    from urllib.error import HTTPError
    
    api_url = f"https://packages2.fhir.org/packages/{package_name}"
    
    # Check cache first (unless refresh requested)
    if cache_dir and not refresh_cache:
        cache_file = cache_dir / f"{package_name.replace('/', '_')}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cached_data = json.load(f)
                    if isinstance(cached_data, dict) and 'versions' in cached_data:
                        versions = []
                        for version, version_data in cached_data['versions'].items():
                            if isinstance(version_data, dict) and version_data.get('date'):
                                versions.append({
                                    'name': version_data.get('name', package_name),
                                    'version': version,
                                    'date': version_data.get('date'),
                                    'fhirVersion': version_data.get('fhirVersion') or version_data.get('fhirversion') or '',
                                })
                        return versions, None
            except Exception as e:
                # If cache read fails, fetch fresh
                pass
    
    try:
        req = Request(api_url)
        req.add_header('Accept', 'application/json')
        req.add_header('User-Agent', 'Mozilla/5.0')
        
        with urlopen(req, timeout=30) as response:
            status_code = response.getcode()
            data = json.loads(response.read())
            
            # Extract versions from response
            versions = []
            if isinstance(data, dict):
                if 'versions' in data:
                    for version, version_data in data['versions'].items():
                        if isinstance(version_data, dict) and version_data.get('date'):
                            versions.append({
                                'name': version_data.get('name', package_name),
                                'version': version,
                                'date': version_data.get('date'),
                                'fhirVersion': version_data.get('fhirVersion') or version_data.get('fhirversion') or '',
                            })
                    
    # Cache the response (also overwrites when refresh_cache=True)
                    if cache_dir:
                        cache_dir.mkdir(parents=True, exist_ok=True)
                        cache_file = cache_dir / f"{package_name.replace('/', '_')}.json"
                        with open(cache_file, 'w', encoding='utf-8') as f:
                            json.dump(data, f, indent=2, ensure_ascii=False)
                else:
                    # Response doesn't have 'versions' key
                    return [], f"Response missing 'versions' key. Keys: {list(data.keys())}"
            
            if not versions:
                return [], f"No versions found in response (status {status_code})"
            
            return versions, None
            
    except HTTPError as e:
        # If 404 and we have a canonical URL, try package-list.json as fallback
        if e.code == 404 and canonical_url:
            versions, fallback_error = fetch_package_versions_from_package_list(canonical_url, package_name)
            if versions:
                return versions, None  # Success via fallback
            else:
                # Fallback also failed, return the original 404 error
                error_msg = f"HTTP {e.code}: {e.reason} (fallback to package-list.json also failed: {fallback_error})"
                return [], error_msg
        error_msg = f"HTTP {e.code}: {e.reason}"
        return [], error_msg
    except URLError as e:
        error_msg = f"URL Error: {str(e)}"
        return [], error_msg
    except json.JSONDecodeError as e:
        error_msg = f"JSON decode error: {str(e)}"
        return [], error_msg
    except Exception as e:
        error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        return [], error_msg


def fetch_all_package_names_from_api() -> Set[str]:
    """
    Fetch all package names from the /packages/ endpoint.
    
    This endpoint returns a list of all packages (not just IGs), but may be limited.
    We'll use this to get the complete list of package names.
    
    Returns:
        Set of unique package names
    """
    from urllib.request import Request
    
    api_url = "https://packages2.fhir.org/packages/"
    
    print(f"Fetching all package names from {api_url}...")
    
    try:
        req = Request(api_url)
        req.add_header('Accept', 'application/json')
        req.add_header('User-Agent', 'Mozilla/5.0')
        
        with urlopen(req, timeout=30) as response:
            data = json.loads(response.read())
            
            package_names = set()
            
            # Handle response format
            packages = []
            if isinstance(data, list):
                packages = data
            elif isinstance(data, dict):
                if 'packages' in data:
                    packages = data['packages']
                elif 'items' in data:
                    packages = data['items']
                elif 'results' in data:
                    packages = data['results']
                elif 'data' in data:
                    packages = data['data']
                elif 'list' in data:
                    packages = data['list']
            
            # Extract unique package names
            sample_keys = None
            for pkg in packages:
                if isinstance(pkg, dict):
                    if sample_keys is None:
                        sample_keys = list(pkg.keys())
                    name = pkg.get('name', '').strip()
                    if name:
                        package_names.add(name)
                    else:
                        # Debug: show what fields are available if 'name' is missing
                        if sample_keys is None or 'name' not in pkg:
                            print(f"  Warning: Package missing 'name' field. Available keys: {list(pkg.keys())}", file=sys.stderr)
            
            if sample_keys:
                print(f"  Sample package keys: {sample_keys}")
            print(f"  Found {len(package_names)} unique package names")
            return package_names
            
    except Exception as e:
        print(f"Error fetching package names from API: {e}", file=sys.stderr)
        return set()


def fetch_packages_api(cache_dir: Optional[Path] = None, verify_ig_registry: bool = True, refresh_cache: bool = False) -> List[Dict]:
    """
    Fetch all package data by:
    1. Getting package names from /packages/ endpoint (complete list)
    2. Optionally verifying IG registry packages are all present
    3. Fetching all versions for each package from packages2.fhir.org
    4. Caching individual package responses locally
    
    Args:
        cache_dir: Optional directory to cache package version data (default: data/working/packages/cache)
        verify_ig_registry: If True, verify that all IG registry packages are in /packages/
        refresh_cache: If True, ignore existing cached package files and fetch fresh from API
    
    Returns:
        List of package dictionaries with 'name', 'version', and 'date' fields
    """
    import time
    
    if cache_dir is None:
        cache_dir = Path('data/working/packages/cache')
    
    # Step 1: Get package names from /packages/ endpoint (complete list)
    package_names = fetch_all_package_names_from_api()
    
    if not package_names:
        print(f"Error: No package names found from /packages/ endpoint", file=sys.stderr)
        sys.exit(1)
    
    # Step 2: Verify IG registry packages are all in /packages/ and get canonical URLs
    package_to_canonical = {}  # Map package_name -> canonical_url for fallback fetching
    if verify_ig_registry:
        print(f"\nVerifying IG registry packages are in /packages/...")
        ig_package_names, ig_package_to_canonical = fetch_ig_registry_data()
        package_to_canonical.update(ig_package_to_canonical)
        
        # Find packages in IG registry that are NOT in /packages/
        missing_from_packages = ig_package_names - package_names
        
        if missing_from_packages:
            print(f"  ⚠️  WARNING: Found {len(missing_from_packages)} packages in IG registry NOT in /packages/:")
            for pkg in sorted(missing_from_packages):
                canonical = package_to_canonical.get(pkg, 'N/A')
                print(f"    - {pkg} (canonical: {canonical})")
            
            # Save to file for review
            missing_file = cache_dir.parent / f"ig-registry-missing-from-packages-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
            with open(missing_file, 'w', encoding='utf-8') as f:
                f.write(f"Packages in IG registry but NOT in /packages/ endpoint\n")
                f.write(f"Generated: {datetime.now().isoformat()}\n")
                f.write(f"Total missing: {len(missing_from_packages)}\n")
                f.write("=" * 80 + "\n\n")
                for pkg in sorted(missing_from_packages):
                    canonical = package_to_canonical.get(pkg, 'N/A')
                    f.write(f"{pkg}\n")
                    f.write(f"  Canonical URL: {canonical}\n")
                    f.write(f"  package-list.json URL: {canonical.rstrip('/') + '/package-list.json' if canonical != 'N/A' else 'N/A'}\n\n")
            print(f"  Missing packages list saved to: {missing_file}")
            
            # Add missing packages to our list
            package_names.update(missing_from_packages)
            print(f"  Added {len(missing_from_packages)} missing packages to fetch list")
        else:
            print(f"  ✓ All {len(ig_package_names)} IG registry packages are present in /packages/")
        
        # Also check for packages in /packages/ that are NOT in IG registry (for info)
        extra_in_packages = package_names - ig_package_names
        print(f"  Info: {len(extra_in_packages)} packages in /packages/ are not in IG registry (expected - /packages/ includes non-IG packages)")
    
    print(f"\nTotal unique package names to fetch: {len(package_names)}")
    
    # Step 3: Fetch versions for each package
    print(f"\nFetching versions for {len(package_names)} packages...")
    all_packages = []
    successful = 0
    failed_packages = []  # List of (package_name, error_message) tuples
    fallback_successful = 0  # Count of packages successfully fetched via package-list.json fallback
    
    for i, package_name in enumerate(sorted(package_names), 1):
        try:
            canonical_url = package_to_canonical.get(package_name)
            versions, error_msg = fetch_package_versions(
                package_name,
                cache_dir,
                canonical_url=canonical_url,
                refresh_cache=refresh_cache,
            )
            
            if error_msg:
                failed_packages.append((package_name, error_msg))
            elif versions:
                all_packages.extend(versions)
                successful += 1
                # Track if this was fetched via fallback (if canonical_url was provided and package wasn't in cache)
                if canonical_url and not (cache_dir and (cache_dir / f"{package_name.replace('/', '_')}.json").exists()):
                    # Likely fetched via fallback (we can't be 100% sure without modifying fetch_package_versions)
                    # But if it had a canonical_url and wasn't cached, it probably used fallback
                    fallback_successful += 1
            else:
                failed_packages.append((package_name, "No versions returned (empty list)"))
            
            if i % 50 == 0:
                print(f"  Progress: {i}/{len(package_names)} packages, {len(all_packages)} versions fetched, {len(failed_packages)} failed")
        
        except Exception as e:
            failed_packages.append((package_name, f"Exception: {type(e).__name__}: {str(e)}"))
        
        # Rate limiting: small delay to avoid overwhelming the API
        if i % 10 == 0:
            time.sleep(0.5)
    
    # Report results
    print(f"\n✓ Fetched versions for {successful} packages ({len(failed_packages)} failed)")
    if fallback_successful > 0:
        print(f"  ({fallback_successful} packages fetched via package-list.json fallback)")
    print(f"  Total package versions: {len(all_packages)}")
    
    # Report failed packages with details
    if failed_packages:
        print(f"\nFailed package fetches ({len(failed_packages)}):")
        # Group by error type for summary
        error_counts = {}
        for pkg_name, error_msg in failed_packages:
            # Extract error type (first part before colon)
            error_type = error_msg.split(':')[0] if ':' in error_msg else error_msg
            error_counts[error_type] = error_counts.get(error_type, 0) + 1
        
        print(f"  Error summary:")
        for error_type, count in sorted(error_counts.items(), key=lambda x: -x[1]):
            print(f"    {error_type}: {count}")
        
        # Save detailed failure log
        failed_log_file = cache_dir.parent / f"failed-packages-{datetime.now().strftime('%Y%m%d-%H%M%S')}.txt"
        with open(failed_log_file, 'w', encoding='utf-8') as f:
            f.write(f"Failed Package Fetches - {datetime.now().isoformat()}\n")
            f.write(f"Total failed: {len(failed_packages)}\n")
            f.write("=" * 80 + "\n\n")
            for pkg_name, error_msg in sorted(failed_packages):
                f.write(f"{pkg_name}\n")
                f.write(f"  Error: {error_msg}\n")
                f.write(f"  URL: https://packages2.fhir.org/packages/{pkg_name}\n\n")
        print(f"  Detailed failure log saved to: {failed_log_file}")
    
    if not all_packages:
        print(f"Error: No package versions fetched", file=sys.stderr)
        sys.exit(1)
    
    return all_packages, len(failed_packages)


def save_packages_json(packages: List[Dict], output_dir: Path) -> Path:
    """
    Save packages JSON to a timestamped file.
    
    Args:
        packages: List of package dictionaries
        output_dir: Directory to save the JSON file
    
    Returns:
        Path to the saved file
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    filename = f"{timestamp}-packages.fhir.org-packages.json"
    filepath = output_dir / filename
    
    print(f"Saving packages JSON to {filepath}...")
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(packages, f, indent=2, ensure_ascii=False)
    
    print(f"  Saved {len(packages)} package versions")
    return filepath


def parse_package_date(date_str: str) -> Optional[datetime]:
    """
    Parse a package date string (ISO format) to datetime.
    
    Args:
        date_str: Date string in ISO format (e.g., "2015-10-24T12:00:00.000Z")
    
    Returns:
        timezone-aware datetime object (UTC) or None if parsing fails
    """
    from datetime import timezone
    try:
        # Handle ISO format with Z timezone
        if date_str.endswith('Z'):
            date_str = date_str[:-1] + '+00:00'
        dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        # Ensure timezone-aware (UTC)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _get_fhir_version(pkg: Dict) -> str:
    """Extract fhirVersion from package dict (case-insensitive)."""
    fv = (pkg.get('fhirVersion') or pkg.get('fhirversion') or '').strip()
    return fv


def calculate_package_metrics(packages: List[Dict], periods: List[str]) -> Dict[str, Dict[str, int]]:
    """
    Calculate package metrics for each time period.
    
    Requirements:
    - Total packages: Count of unique "name" values that exist as of end of period
    - New packages: Count of unique "name" values that appeared during the period
      (based on the earliest version date of that package)
    - Total versions: Count of (name, version) pairs that exist as of end of period
    - New versions: Count of (name, version) pairs that appeared during the period
    - New R4/R4B/R5: New package versions in period for fhirversion 4.0.1/4.3.0/5.0.0
    - Total R4/R4B/R5: Cumulative package versions as of period end for each FHIR version
    
    Args:
        packages: List of package dictionaries with 'name', 'version', 'date', and optionally 'fhirVersion'
        periods: List of period strings (e.g., ['2025-T3', '2025-T2', ...])
    
    Returns:
        Dictionary mapping indicator IDs to period -> value dictionaries
        Format: {
            '43': {...}, '44': {...}, '45': {...}, '46': {...},
            '49': {...}, '50': {...}, '51': {...},  # New R4, R4B, R5
            '52': {...}, '53': {...}, '54': {...}  # Total R4, R4B, R5
        }
    """
    # Aggregate all entries by package name and version
    # Each entry in the JSON represents a specific package version with a date
    package_versions = {}  # (name, version) -> (date, fhir_version)
    package_earliest_date = {}  # name -> earliest date across all versions
    
    for pkg in packages:
        name = pkg.get('name', '').strip()
        version = pkg.get('version', '').strip()
        date_str = pkg.get('date', '')
        fhir_version = _get_fhir_version(pkg)
        
        if not name or not version or not date_str:
            continue
        
        pkg_date = parse_package_date(date_str)
        if not pkg_date:
            continue
        
        # Track each (name, version) pair with its date and fhirversion
        key = (name, version)
        if key not in package_versions or pkg_date < package_versions[key][0]:
            package_versions[key] = (pkg_date, fhir_version)
        
        # Track the earliest date for each package name (across all versions)
        if name not in package_earliest_date or pkg_date < package_earliest_date[name]:
            package_earliest_date[name] = pkg_date
    
    # Sort periods chronologically (oldest first) for cumulative calculations
    def period_sort_key(p: str) -> Tuple[int, int]:
        match = p.split('-T')
        year = int(match[0])
        tri = int(match[1])
        return (year, tri)
    
    sorted_periods = sorted(periods, key=period_sort_key)
    
    # Indicator IDs: 49=New R4, 50=New R4B, 51=New R5, 52=Total R4, 53=Total R4B, 54=Total R5
    fhir_version_to_new_id = {"4.0.1": "49", "4.3.0": "50", "5.0.0": "51"}
    fhir_version_to_total_id = {"4.0.1": "52", "4.3.0": "53", "5.0.0": "54"}
    
    metrics = {
        '43': {}, '44': {}, '45': {}, '46': {},
        '49': {}, '50': {}, '51': {},
        '52': {}, '53': {}, '54': {},
    }
    
    # Calculate metrics for each period
    for period in sorted_periods:
        try:
            period_start, period_end = parse_time_period(period)
        except ValueError as e:
            print(f"Warning: Skipping invalid period {period}: {e}", file=sys.stderr)
            continue
        
        total_packages = set()
        total_versions = set()
        new_packages = set()
        new_versions = set()
        
        # Per-FHIR-version counts: new and total
        new_by_fv: Dict[str, Set[Tuple[str, str]]] = {fv: set() for fv in FHIR_VERSIONS_FOR_INDICATORS}
        total_by_fv: Dict[str, Set[Tuple[str, str]]] = {fv: set() for fv in FHIR_VERSIONS_FOR_INDICATORS}
        
        for (name, version), (version_date, fhir_version) in package_versions.items():
            # Total versions: include if this version exists as of period end
            if version_date <= period_end:
                total_versions.add((name, version))
                total_packages.add(name)
                if fhir_version in FHIR_VERSIONS_FOR_INDICATORS:
                    total_by_fv[fhir_version].add((name, version))
            
            # New versions: include if this version appeared during the period
            if period_start <= version_date <= period_end:
                new_versions.add((name, version))
                if fhir_version in FHIR_VERSIONS_FOR_INDICATORS:
                    new_by_fv[fhir_version].add((name, version))
        
        for name, earliest_date in package_earliest_date.items():
            if period_start <= earliest_date <= period_end:
                new_packages.add(name)
        
        metrics['43'][period] = len(total_packages)
        metrics['44'][period] = len(new_packages)
        metrics['45'][period] = len(total_versions)
        metrics['46'][period] = len(new_versions)
        
        for fv in FHIR_VERSIONS_FOR_INDICATORS:
            new_id = fhir_version_to_new_id.get(fv)
            total_id = fhir_version_to_total_id.get(fv)
            if new_id:
                metrics[new_id][period] = len(new_by_fv[fv])
            if total_id:
                metrics[total_id][period] = len(total_by_fv[fv])
    
    return metrics


def read_kpi_csv(csv_path: Path) -> Tuple[List[Dict[str, str]], List[str]]:
    """
    Read KPI CSV file.
    
    Args:
        csv_path: Path to CSV file
    
    Returns:
        Tuple of (list of row dictionaries, list of fieldnames)
    """
    with open(csv_path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        fieldnames = reader.fieldnames
        rows = list(reader)
    
    return rows, fieldnames


def get_periods_from_csv(rows: List[Dict[str, str]], indicator_ids: List[str]) -> List[str]:
    """
    Extract unique time periods for specified indicators from CSV rows.
    
    Args:
        rows: List of row dictionaries
        indicator_ids: List of indicator IDs to look for
    
    Returns:
        List of unique period strings
    """
    periods = set()
    indicator_ids_set = set(indicator_ids)
    
    for row in rows:
        if row.get('ID', '').strip() in indicator_ids_set:
            period = row.get('Time Period', '').strip()
            if period:
                periods.add(period)
    
    return sorted(list(periods))


def update_kpi_csv(rows: List[Dict[str, str]], metrics: Dict[str, Dict[str, int]], 
                   indicator_ids: List[str], fieldnames: List[str], 
                   failed_packages_count: int = 0) -> Tuple[List[Dict[str, str]], Dict[str, int]]:
    """
    Update KPI CSV rows with calculated metrics. Adds new rows for periods that don't exist.
    
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
        period = row.get('Time Period', '').strip()
        key = (indicator_id, period)
        
        # Check if this row should be updated
        if indicator_id in indicator_ids and indicator_id in metrics:
            period_metrics = metrics[indicator_id]
            
            # Update value if period matches
            if period in period_metrics:
                # Create a copy of the row and update the value
                updated_row = row.copy()
                new_value = str(period_metrics[period])
                updated_row['Value'] = new_value
                # Ensure Tags=ECOSYSTEM for package version indicators 49-54
                if indicator_id in ('49', '50', '51', '52', '53', '54'):
                    updated_row['Tags'] = 'ECOSYSTEM'
                
                # Add failure count to Notes field for package indicators
                if failed_packages_count > 0:
                    if indicator_id in ['43', '44']:
                        # For package indicators, report failed packages
                        existing_notes = updated_row.get('Notes', '').strip()
                        failure_note = f"Failed to fetch {failed_packages_count} package(s) from API"
                        if existing_notes:
                            updated_row['Notes'] = f"{existing_notes}. {failure_note}"
                        else:
                            updated_row['Notes'] = failure_note
                    elif indicator_id in ['45', '46', '49', '50', '51', '52', '53', '54']:
                        # For version indicators, report failed packages (which means failed versions)
                        existing_notes = updated_row.get('Notes', '').strip()
                        failure_note = f"Failed to fetch versions for {failed_packages_count} package(s) from API"
                        if existing_notes:
                            updated_row['Notes'] = f"{existing_notes}. {failure_note}"
                        else:
                            updated_row['Notes'] = failure_note
                
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
        
        # Get a template row for this indicator (to copy other fields)
        template_row = None
        for row in rows:
            if row.get('ID', '').strip() == indicator_id:
                template_row = row.copy()
                break
        
        # If no existing row found, create a basic template
        if not template_row:
            # Default template based on indicator ID
            template_row = {
                'ID': indicator_id,
                'Domain': 'Standards Development',
                'Type': 'N',
                'Unit': 'count',
                'Steward': 'Standards Development',
                'Tags': 'ECOSYSTEM',
                'Direction': 'higher',
                'Image': ''
            }
            indicator_templates = {
                '43': 'Packages',
                '44': 'Packages: New',
                '45': 'Package versions',
                '46': 'Packages versions: New',
                '49': 'Package versions: New R4',
                '50': 'Package versions: New R4B',
                '51': 'Package versions: New R5',
                '52': 'Package versions: Total R4',
                '53': 'Package versions: Total R4B',
                '54': 'Package versions: Total R5',
            }
            if indicator_id in indicator_templates:
                template_row['Indicator'] = indicator_templates[indicator_id]
            if indicator_id in ('49', '50', '51', '52', '53', '54'):
                template_row['Unit'] = 'count'
        
        # Ensure Tags=ECOSYSTEM for package version indicators 49-54 (including when template from existing row)
        if indicator_id in ('49', '50', '51', '52', '53', '54'):
            template_row['Tags'] = 'ECOSYSTEM'
        
        # Add rows for periods that don't exist
        for period, value in metrics[indicator_id].items():
            key = (indicator_id, period)
            if key not in updated_keys:
                # Create new row based on template
                new_row = template_row.copy()
                new_row['Time Period'] = period
                new_row['Value'] = str(value)
                
                # Add failure count to Notes field for package indicators
                if failed_packages_count > 0:
                    if indicator_id in ['43', '44']:
                        # For package indicators, report failed packages
                        failure_note = f"Failed to fetch {failed_packages_count} package(s) from API"
                        new_row['Notes'] = failure_note
                    elif indicator_id in ['45', '46', '49', '50', '51', '52', '53', '54']:
                        # For version indicators, report failed packages (which means failed versions)
                        failure_note = f"Failed to fetch versions for {failed_packages_count} package(s) from API"
                        new_row['Notes'] = failure_note
                
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


def main():
    parser = argparse.ArgumentParser(
        description='Calculate package indicators from FHIR packages API',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Fetch fresh data and update KPIs for specific periods
  python scripts/packages/calculate-package-indicators.py \\
      --kpi-csv data/working/indicators/all_kpis.csv \\
      --output data/working/indicators/all_kpis_updated.csv \\
      -p 2022-2025
  
  # Use existing JSON file with specific period
  python scripts/packages/calculate-package-indicators.py \\
      --kpi-csv data/working/indicators/all_kpis.csv \\
      --output data/working/indicators/all_kpis_updated.csv \\
      --packages-json data/working/packages/20260117-packages.fhir.org-packages.json \\
      -p 2024T3
  
  # Use periods from CSV (default behavior)
  python scripts/packages/calculate-package-indicators.py \\
      --kpi-csv data/working/indicators/all_kpis.csv \\
      --output data/working/indicators/all_kpis_updated.csv \\
      --packages-json data/working/packages/20260117-packages.fhir.org-packages.json
        """
    )
    
    parser.add_argument(
        '--kpi-csv',
        type=str,
        required=True,
        help='Path to input KPI CSV file'
    )
    
    parser.add_argument(
        '--output',
        type=str,
        required=True,
        help='Path to output updated KPI CSV file'
    )
    
    parser.add_argument(
        '--packages-json',
        type=str,
        help='Path to existing packages JSON file (if not provided, will fetch from API)'
    )
    
    parser.add_argument(
        '--packages-dir',
        type=str,
        default='data/working/packages',
        help='Directory to save fetched packages JSON (default: data/working/packages)'
    )
    
    parser.add_argument(
        '--cache-dir',
        type=str,
        default='data/working/packages/cache',
        help='Directory to cache individual package version responses (default: data/working/packages/cache)'
    )
    
    parser.add_argument(
        '--use-cache-only',
        action='store_true',
        help='Only use cached package data, do not fetch from API'
    )

    parser.add_argument(
        '--refresh-cache',
        action='store_true',
        help='Fetch fresh per-package data from API and overwrite cache (ignores existing cached package files)'
    )
    
    parser.add_argument(
        '-p', '--periods',
        type=str,
        nargs='+',
        help='Time periods to calculate indicators for (e.g., "2022-2025", "2024T3", "2024"). '
             'If not specified, will use periods found in CSV for indicators 43-46.'
    )
    
    args = parser.parse_args()
    
    # Read the KPI CSV
    kpi_csv_path = Path(args.kpi_csv)
    if not kpi_csv_path.exists():
        print(f"Error: KPI CSV file not found: {kpi_csv_path}", file=sys.stderr)
        sys.exit(1)
    
    print(f"Reading KPI CSV from {kpi_csv_path}")
    rows, fieldnames = read_kpi_csv(kpi_csv_path)
    
    # Get periods - either from command line or from CSV
    indicator_ids = ['43', '44', '45', '46', '49', '50', '51', '52', '53', '54']
    if args.periods:
        # Expand periods from command line arguments
        periods = []
        for period_arg in args.periods:
            try:
                expanded = expand_periods(period_arg)
                periods.extend(expanded)
            except ValueError as e:
                print(f"Error: Invalid period format '{period_arg}': {e}", file=sys.stderr)
                sys.exit(1)
        periods = sorted(list(set(periods)))  # Remove duplicates and sort
        print(f"Using periods from command line: {', '.join(periods)}")
    else:
        # Get periods from CSV for package indicators (43-46, 49-54)
        periods = get_periods_from_csv(rows, indicator_ids)
        if not periods:
            print("Warning: No periods found for package indicators in CSV", file=sys.stderr)
            periods = ['2025-T3', '2025-T2', '2025-T1']  # Default periods
        print(f"Found periods from CSV: {', '.join(periods)}")
    
    # Load or fetch packages data
    failed_packages_count = 0  # Track failed packages count
    if args.packages_json:
        packages_json_path = Path(args.packages_json)
        if not packages_json_path.exists():
            print(f"Error: Packages JSON file not found: {packages_json_path}", file=sys.stderr)
            sys.exit(1)
        print(f"Loading packages from {packages_json_path}...")
        with open(packages_json_path, 'r', encoding='utf-8') as f:
            packages = json.load(f)
        print(f"  Loaded {len(packages)} package versions")
        # No failure count available when loading from JSON
        failed_packages_count = 0
    elif args.use_cache_only:
        # Load from cache directory
        cache_dir = Path(args.cache_dir)
        print(f"Loading packages from cache directory: {cache_dir}...")
        packages = []
        if cache_dir.exists():
            cache_files = list(cache_dir.glob("*.json"))
            print(f"  Found {len(cache_files)} cached package files")
            for cache_file in cache_files:
                try:
                    with open(cache_file, 'r', encoding='utf-8') as f:
                        cached_data = json.load(f)
                        if isinstance(cached_data, dict) and 'versions' in cached_data:
                            package_name = cached_data.get('name', cache_file.stem)
                            for version, version_data in cached_data['versions'].items():
                                if isinstance(version_data, dict) and version_data.get('date'):
                                    packages.append({
                                        'name': version_data.get('name', package_name),
                                        'version': version,
                                        'date': version_data.get('date'),
                                        'fhirVersion': version_data.get('fhirVersion') or version_data.get('fhirversion') or '',
                                    })
                except Exception as e:
                    print(f"  Warning: Error reading {cache_file}: {e}", file=sys.stderr)
        print(f"  Loaded {len(packages)} package versions from cache")
        if not packages:
            print(f"Error: No packages found in cache. Run without --use-cache-only first.", file=sys.stderr)
            sys.exit(1)
        # No failure count available when loading from cache
        failed_packages_count = 0
    else:
        # Fetch from API using IG registry approach
        cache_dir = Path(args.cache_dir)
        packages, failed_packages_count = fetch_packages_api(cache_dir=cache_dir, refresh_cache=args.refresh_cache)
        packages_dir = Path(args.packages_dir)
        save_packages_json(packages, packages_dir)
    
    # Calculate metrics
    print("\nCalculating package metrics...")
    metrics = calculate_package_metrics(packages, periods)
    
    # Print calculated metrics
    print("\nCalculated metrics:")
    for indicator_id in indicator_ids:
        if indicator_id in metrics:
            print(f"  Indicator {indicator_id}:")
            for period, value in sorted(metrics[indicator_id].items()):
                print(f"    {period}: {value}")
    
    # Update the CSV
    print(f"\nUpdating KPI CSV...")
    updated_rows, update_counts = update_kpi_csv(rows, metrics, indicator_ids, fieldnames, failed_packages_count=failed_packages_count)
    
    # Write the output
    output_path = Path(args.output)
    print(f"Writing updated KPI CSV to {output_path}")
    write_kpi_csv(updated_rows, fieldnames, output_path)
    
    # Print summary
    print("\nUpdate summary:")
    for indicator_id in indicator_ids:
        if indicator_id in metrics:
            total_periods = len(metrics[indicator_id])
            updated_count = update_counts.get(indicator_id, 0)
            print(f"  Indicator {indicator_id}: Updated {updated_count} of {total_periods} period(s)")
    
    print(f"\nDone! Updated CSV written to {output_path}")


if __name__ == '__main__':
    main()
