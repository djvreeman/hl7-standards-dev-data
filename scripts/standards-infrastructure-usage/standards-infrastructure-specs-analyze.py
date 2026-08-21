#!/usr/bin/env python3
# =============================================================================
# Standards Infrastructure Specification Analysis
#
# Universe (denominator): every unique specification that was **built** on the
# FHIR IG CI-build pipeline in the lookback (HL7 International, partners, AND
# community/other orgs) PLUS any specification that had a Jira specification-
# feedback **issue created** in the window and is not on that CI pipeline
# (V2, older CDA, DAM/functional models, FHIR Core, and similar).
#
# Primary marker (T): unique Jira Specification key with at least one issue
# created in the lookback. This is services consumed (Jira feedback vs
# build-only), not a closed BALDEF cycle.
#
# This is a companion to the CI-build and issue-analysis pipelines, not a
# replacement. It does not modify participation, org-mapping, or KPI reports.
#
# === How the two sources are linked ===
#
# Build side (parse-builds-web.py --recent): one row per GitHub org/repo, with
# package_id, title, last_built, ci_url, github_url.
#
# Issue side (parse-jira-filter-export-csv-md.py): specification-feedback
# issues with Specification + Created Date. Operating model: keep the JQL
# inline and limit with created >= -400d (~7–8k rows vs 50k+). Do NOT use
# filter 24407 (date-capped, excludes AU/EU; that filter is for T1 issue
# reports). SOP: scripts/documentation/README-standards-infrastructure-specs.md
#
# Join, in order (first hit wins):
#   1. --link-mapping CSV (org_repo, Specification)
#   2. SPECS.json gitUrl  → github.com/{org}/{repo}  (case-insensitive)
#   3. SPECS.json ciUrl   → build.fhir.org/ig/{org}/{repo}
#   4. package_id vs a package id reconstructed from the SPECS canonical URL
#
# Identity after the join:
#   - Specs on the CI builder: unique org/repo. If one repo maps to several
#     Jira keys, they stay one specification; it counts as T if any key had
#     an issue created in the window.
#   - Issue-only specs (V2, older CDA zips, Arden, FHIR Core, …): unique Jira
#     Specification key, added because they used Jira feedback but are not on
#     the IG publisher.
#
# CI-build coverage: all org/repos with a QA build in the window except
# publisher templates (`ig-template-*` / `*.template`). Community IGs are in
# the denominator. `--exclude-community` drops them if you want the old
# International+Partners-only universe.
#
# === Inputs ===
#
#   --issues-csv              Jira issue CSV (Specification + Created Date)
#   --recent-builds-csv       recent-builds CSV from parse-builds-web.py --recent
#     OR --fetch-builds       pull qas.json live (no VPN needed)
#
# === Example ===
#
#   python3 scripts/parse-jira-filter-export-csv-md.py \
#       -f '{"jql": "project in (FHIR, CDA, V2, OTHER) AND Specification is not EMPTY AND created >= -400d ORDER BY created DESC"}' \
#       -d 'key,fields.created,fields.customfield_11302,fields.spec_display_name,fields.issuetype.name,fields.status.name' \
#       -o "data/working/issue-analysis/YYYY/YYYY-lookback/all-spec-feedback-issues" \
#       -e csv --cache --cache-dir data/working/cache
#
#   python3 scripts/parse-builds-web.py --recent --days 365
#
#   python3 scripts/standards-infrastructure-usage/standards-infrastructure-specs-analyze.py \
#       --issues-csv data/working/issue-analysis/YYYY/YYYY-lookback/all-spec-feedback-issues.csv \
#       --recent-builds-csv data/working/builds/<timestamp>-recent-builds.csv \
#       -o data/working/standards-infrastructure-usage/reports/YYYY-MM-DD-standards-infrastructure-specs.md \
#       --lookback-days 365 \
#       --data-gathering-date YYYY-MM-DD \
#       --csv data/working/standards-infrastructure-usage/reports/YYYY-MM-DD-standards-infrastructure-specs.csv
#
# === Source ===
#   https://github.com/djvreeman/hl7-standards-dev-data
#   SOP: scripts/documentation/README-standards-infrastructure-specs.md
#
# === Author ===
#   Daniel J. Vreeman, PT, DPT, MS, FACMI, FIAHSI
#   HL7 International
# =============================================================================

import argparse
import csv
import importlib.util
import os
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import datetime, timezone
from urllib.parse import urlparse

import pandas as pd

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SCRIPTS_DIR = os.path.dirname(SCRIPT_DIR)
PROJECT_ROOT = os.path.dirname(SCRIPTS_DIR)

SPECS_JSON_URL = "https://raw.githubusercontent.com/HL7/JIRA-Spec-Artifacts/gh-pages/SPECS.json"
DEFAULT_AFFILIATE_ROSTER = os.path.join(PROJECT_ROOT, "data/working/affiliates/main-affiliate-roster.csv")

INTERNATIONAL_KEY_TOKENS = frozenset({"us", "uv"})

PARTNER_KEY_TOKENS = {
    "au": "HL7 Australia",
    "eu": "HL7 Europe",
    "uk": "HL7 UK",
    "ca": "HL7 Canada",
    "nz": "HL7 New Zealand",
    "ch": "HL7 Switzerland",
    "de": "HL7 Germany",
    "nl": "HL7 Netherlands",
    "fr": "HL7 France",
    "be": "HL7 Belgium",
    "it": "HL7 Italy",
    "es": "HL7 Spain",
    "br": "HL7 Brazil",
    "jp": "HL7 Japan",
    "kr": "HL7 Korea",
    "tw": "HL7 Taiwan",
    "in": "HL7 India",
    "ar": "HL7 Argentina",
    "at": "HL7 Austria",
    "cz": "HL7 Czech Republic",
    "dk": "HL7 Denmark",
    "cl": "HL7 Chile",
    "pt": "HL7 Portugal",
    "se": "HL7 Sweden",
    "ee": "HL7 Estonia",
}

PARTNER_HOSTS = {
    "hl7.org.au": "HL7 Australia",
    "fhir.hl7.org.au": "HL7 Australia",
    "hl7.eu": "HL7 Europe",
    "fhir.hl7.eu": "HL7 Europe",
    "hl7.org.uk": "HL7 UK",
    "fhir.hl7.org.uk": "HL7 UK",
    "hl7.org.ca": "HL7 Canada",
    "fhir.hl7.org.ca": "HL7 Canada",
    "hl7.org.nz": "HL7 New Zealand",
    "hl7.ch": "HL7 Switzerland",
    "hl7.de": "HL7 Germany",
    "hl7.nl": "HL7 Netherlands",
    "hl7.fr": "HL7 France",
    "hl7.be": "HL7 Belgium",
    "hl7.it": "HL7 Italy",
    "hl7.es": "HL7 Spain",
    "hl7.org.br": "HL7 Brazil",
    "hl7.jp": "HL7 Japan",
    "hl7.at": "HL7 Austria",
    "fhir.hl7.at": "HL7 Austria",
    "hl7chile.cl": "HL7 Chile",
}

PARTNER_SUMMARY_PATTERNS = [
    (re.compile(r"\bHL7\s+Australia\b", re.IGNORECASE), "HL7 Australia"),
    (re.compile(r"\bHL7\s+AU\b", re.IGNORECASE), "HL7 Australia"),
    (re.compile(r"\bHL7\s+Europe\b", re.IGNORECASE), "HL7 Europe"),
    (re.compile(r"\bHL7\s+EU\b", re.IGNORECASE), "HL7 Europe"),
    (re.compile(r"\bHL7\s+UK\b", re.IGNORECASE), "HL7 UK"),
    (re.compile(r"\bHL7\s+Canada\b", re.IGNORECASE), "HL7 Canada"),
    (re.compile(r"\bHL7\s+New Zealand\b", re.IGNORECASE), "HL7 New Zealand"),
    (re.compile(r"\bHL7\s+Austria\b", re.IGNORECASE), "HL7 Austria"),
    (re.compile(r"\bHL7\s+Belgium\b", re.IGNORECASE), "HL7 Belgium"),
    (re.compile(r"\bHL7\s+Switzerland\b", re.IGNORECASE), "HL7 Switzerland"),
    (re.compile(r"\bHL7\s+Czech", re.IGNORECASE), "HL7 Czech Republic"),
]

SPONSOR_INTERNATIONAL = "HL7 International"
SPONSOR_PARTNER = "HL7 Partner"
SPONSOR_OTHER = "Other"

SOURCE_BUILD = "CI-build"
SOURCE_ISSUE = "Jira-issue"
SOURCE_BOTH = "CI-build + Jira-issue"


def extract_timestamp_from_filename(filename):
    match = re.search(r"(\d{8})-(\d{6})", filename or "")
    if not match:
        return None
    date_str, time_str = match.group(1), match.group(2)
    try:
        return pd.Timestamp(
            year=int(date_str[:4]),
            month=int(date_str[4:6]),
            day=int(date_str[6:8]),
            hour=int(time_str[:2]),
            minute=int(time_str[2:4]),
            second=int(time_str[4:6]),
            tz="UTC",
        )
    except (ValueError, IndexError):
        return None


def format_count(value):
    try:
        if value is None or pd.isna(value):
            return "N/A"
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return "N/A"


def format_date(ts):
    if ts is None or pd.isna(ts):
        return "N/A"
    return pd.Timestamp(ts).strftime("%B %d, %Y")


def format_pct(numerator, denominator):
    if not denominator:
        return "N/A"
    return f"{100.0 * numerator / denominator:.1f}%"


def md_escape(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def split_specification_keys(value):
    if pd.isna(value) or value is None:
        return []
    text = str(value).strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


def normalize_host(url):
    if not url or pd.isna(url):
        return ""
    text = str(url).strip()
    if not text:
        return ""
    if "://" not in text:
        text = "https://" + text
    try:
        host = (urlparse(text).hostname or "").lower()
    except ValueError:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def strip_git_suffix(repo):
    repo = (repo or "").strip().rstrip("/")
    if repo.lower().endswith(".git"):
        repo = repo[:-4]
    return repo


def parse_github_org_repo(url):
    if not url or pd.isna(url):
        return None
    match = re.search(r"github\.com/([^/]+)/([^/#?]+)", str(url), re.IGNORECASE)
    if not match:
        return None
    org = match.group(1).strip()
    repo = strip_git_suffix(match.group(2))
    if not org or not repo:
        return None
    return f"{org}/{repo}".lower()


def parse_ci_org_repo(url):
    if not url or pd.isna(url):
        return None
    match = re.search(r"build\.fhir\.org/ig/([^/]+)/([^/#?]+)", str(url), re.IGNORECASE)
    if not match:
        return None
    org = match.group(1).strip()
    repo = strip_git_suffix(match.group(2))
    if not org or not repo:
        return None
    return f"{org}/{repo}".lower()


def package_id_from_canonical_url(url):
    """
    Reconstruct a conventional FHIR package id from a canonical / publication URL.
    http://hl7.org/fhir/us/core → hl7.fhir.us.core
    http://hl7.org.au/fhir/core → hl7.fhir.au.core (AU host special case)
    http://hl7.org/cda/us/ccda → hl7.cda.us.ccda
    http://hl7.org/xprod/ig/uv/piqi → hl7.xprod.uv.piqi
    """
    if not url or pd.isna(url):
        return None
    text = str(url).strip()
    if not text:
        return None
    if "://" not in text:
        text = "https://" + text
    parsed = urlparse(text)
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path_parts = [p for p in parsed.path.split("/") if p]

    if host in {"hl7.org.au", "fhir.hl7.org.au"}:
        rest = path_parts[1:] if path_parts and path_parts[0].lower() == "fhir" else path_parts
        return "hl7.fhir.au" + (("." + ".".join(rest)) if rest else "")

    if host in {"hl7.eu", "fhir.hl7.eu"}:
        rest = path_parts[1:] if path_parts and path_parts[0].lower() == "fhir" else path_parts
        return "hl7.fhir.eu" + (("." + ".".join(rest)) if rest else "")

    if host not in {"hl7.org", "www.hl7.org"}:
        return None
    if len(path_parts) >= 2 and path_parts[0].lower() in {"fhir", "cda", "xprod"}:
        family = path_parts[0].lower()
        rest = path_parts[1:]
        if family == "xprod" and rest and rest[0].lower() == "ig":
            rest = rest[1:]
        return "hl7." + family + (("." + ".".join(rest)) if rest else "")
    return None


def spec_key_partner_name(spec_key):
    if not spec_key:
        return None
    parts = str(spec_key).split("-")
    if len(parts) < 2:
        return None
    token = parts[1].lower()
    if token in INTERNATIONAL_KEY_TOKENS:
        return None
    return PARTNER_KEY_TOKENS.get(token)


def load_partner_overrides(mapping_file):
    overrides = {}
    if not mapping_file:
        return overrides
    if not os.path.exists(mapping_file):
        print(f"Warning: partner mapping file not found: {mapping_file}")
        return overrides

    df = pd.read_csv(mapping_file)
    required = {"Specification", "Sponsor"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Partner mapping CSV is missing required columns: {', '.join(sorted(missing))}"
        )

    skipped = 0
    for _, row in df.iterrows():
        status = str(row.get("Status", "") or "").strip()
        if status.lower() == "no match":
            skipped += 1
            continue
        key = str(row.get("Specification", "") or "").strip()
        sponsor_raw = str(row.get("Sponsor", "") or "").strip()
        partner = str(row.get("Partner", "") or "").strip()
        if not key or not sponsor_raw:
            continue
        sponsor_norm = sponsor_raw.lower()
        if sponsor_norm in {"international", "hl7 international"}:
            sponsor = SPONSOR_INTERNATIONAL
            partner = ""
        elif sponsor_norm in {"partner", "hl7 partner", "affiliate"}:
            sponsor = SPONSOR_PARTNER
            if not partner:
                print(f"Warning: partner mapping for {key} has Sponsor=Partner but empty Partner name")
        else:
            print(f"Warning: unknown Sponsor '{sponsor_raw}' for {key}; skipping row")
            continue
        overrides[key] = {
            "sponsor": sponsor,
            "partner": partner if sponsor == SPONSOR_PARTNER else "",
            "source": "mapping",
        }

    print(f"Loaded {len(overrides)} partner-mapping override(s) from {mapping_file}")
    if skipped:
        print(f"  Skipped {skipped} mapping row(s) with Status='No Match'")
    return overrides


def classify_specification(spec_key, specification_url, summary, overrides):
    if spec_key and spec_key in overrides:
        return dict(overrides[spec_key])

    host = normalize_host(specification_url)
    if host in PARTNER_HOSTS:
        return {
            "sponsor": SPONSOR_PARTNER,
            "partner": PARTNER_HOSTS[host],
            "source": "url-host",
        }

    partner_from_key = spec_key_partner_name(spec_key)
    if partner_from_key:
        return {
            "sponsor": SPONSOR_PARTNER,
            "partner": partner_from_key,
            "source": "spec-key",
        }

    summary_text = "" if summary is None or pd.isna(summary) else str(summary)
    for pattern, partner_name in PARTNER_SUMMARY_PATTERNS:
        if pattern.search(summary_text):
            return {
                "sponsor": SPONSOR_PARTNER,
                "partner": partner_name,
                "source": "summary",
            }

    return {
        "sponsor": SPONSOR_INTERNATIONAL,
        "partner": "",
        "source": "default",
    }


def classify_github_org(org, prefix_to_affiliate):
    """Classify a GitHub org using the affiliate roster build prefixes."""
    org_l = (org or "").strip().lower()
    if not org_l:
        return None
    if org_l == "hl7":
        return {
            "sponsor": SPONSOR_INTERNATIONAL,
            "partner": "",
            "source": "github-org",
        }
    if org_l in prefix_to_affiliate:
        return {
            "sponsor": SPONSOR_PARTNER,
            "partner": prefix_to_affiliate[org_l],
            "source": "github-org",
        }
    return None


def guess_partner_name_from_org(org):
    org_l = (org or "").strip()
    compact = re.sub(r"^hl7[-_]?", "", org_l, flags=re.IGNORECASE)
    token = compact.lower().strip("-_")
    if token in PARTNER_KEY_TOKENS:
        return PARTNER_KEY_TOKENS[token]
    pretty = re.sub(r"[-_]+", " ", compact).strip()
    if pretty:
        return f"HL7 {pretty.title()}"
    return org_l


def load_affiliate_prefixes(roster_path):
    prefix_to_affiliate = {}
    if not roster_path:
        return prefix_to_affiliate
    if not os.path.exists(roster_path):
        print(f"Warning: affiliate roster not found: {roster_path}")
        return prefix_to_affiliate
    df = pd.read_csv(roster_path)
    if "Build Prefix" not in df.columns or "Affiliate" not in df.columns:
        print(f"Warning: affiliate roster missing Build Prefix / Affiliate columns: {roster_path}")
        return prefix_to_affiliate
    for _, row in df.iterrows():
        prefix = str(row.get("Build Prefix") or "").strip()
        affiliate = str(row.get("Affiliate") or "").strip()
        if prefix and affiliate:
            prefix_to_affiliate[prefix.lower()] = affiliate
    print(f"Loaded {len(prefix_to_affiliate)} affiliate build prefix(es) from {roster_path}")
    return prefix_to_affiliate


def load_link_overrides(path):
    """org_repo, Specification → forced Jira key for that repo."""
    mapping = {}
    if not path:
        return mapping
    if not os.path.exists(path):
        print(f"Warning: link mapping file not found: {path}")
        return mapping
    df = pd.read_csv(path)
    if "org_repo" not in df.columns or "Specification" not in df.columns:
        raise ValueError("Link mapping CSV needs columns org_repo, Specification")
    for _, row in df.iterrows():
        org_repo = str(row.get("org_repo") or "").strip().lower()
        spec_key = str(row.get("Specification") or "").strip()
        if org_repo and spec_key:
            mapping.setdefault(org_repo, []).append(spec_key)
    print(f"Loaded link overrides for {len(mapping)} org/repo(s) from {path}")
    return mapping


def load_specs_index():
    """Load SPECS.json and index by key, git org/repo, ci org/repo, and package id."""
    empty = {"by_key": {}, "by_git": {}, "by_ci": {}, "by_package": {}, "display_names": {}}
    if not REQUESTS_AVAILABLE:
        print("Warning: requests not available; SPECS.json join will be skipped")
        return empty
    try:
        response = requests.get(SPECS_JSON_URL, timeout=30)
        response.raise_for_status()
        data = response.json()
    except Exception as exc:
        print(f"Warning: could not load SPECS.json: {exc}")
        return empty

    by_key = {}
    by_git = defaultdict(list)
    by_ci = defaultdict(list)
    by_package = defaultdict(list)
    display_names = {}
    n_git = n_ci = 0
    for item in data if isinstance(data, list) else []:
        key = str(item.get("key") or "").strip()
        if not key:
            continue
        by_key[key] = item
        name = str(item.get("name") or "").strip()
        if name:
            display_names[key] = name
        git_repo = parse_github_org_repo(item.get("gitUrl") or "")
        ci_repo = parse_ci_org_repo(item.get("ciUrl") or "")
        if git_repo:
            n_git += 1
            if key not in by_git[git_repo]:
                by_git[git_repo].append(key)
        if ci_repo:
            n_ci += 1
            if key not in by_ci[ci_repo]:
                by_ci[ci_repo].append(key)
        pkg = package_id_from_canonical_url(item.get("url") or "")
        if pkg:
            by_package[pkg.lower()].append(key)

    print(
        f"Loaded {len(by_key)} SPECS.json entries "
        f"(gitUrl={n_git}, ciUrl={n_ci}, package-from-url={len(by_package)})"
    )
    return {
        "by_key": by_key,
        "by_git": dict(by_git),
        "by_ci": dict(by_ci),
        "by_package": dict(by_package),
        "display_names": display_names,
    }


def is_publisher_template(repo, package_id):
    repo_l = (repo or "").lower()
    pkg_l = (package_id or "").lower()
    if repo_l.startswith("ig-template"):
        return True
    if pkg_l.endswith(".template") or pkg_l.endswith("-template"):
        return True
    if ".template." in pkg_l:
        return True
    return False


def is_in_scope_build(org, has_specs_link, prefix_to_affiliate, include_other):
    org_l = (org or "").strip().lower()
    if org_l == "hl7":
        return True
    if org_l in prefix_to_affiliate:
        return True
    if has_specs_link:
        return True
    return bool(include_other)


def load_parse_builds_module():
    path = os.path.join(SCRIPTS_DIR, "parse-builds-web.py")
    spec = importlib.util.spec_from_file_location("parse_builds_web", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Could not load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_recent_builds_csv(path, window_start, as_of):
    df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    if "org_repo" not in df.columns:
        if df.shape[1] == 1:
            raise ValueError(
                f"{path} looks like the unique org/repo list from parse-builds-web.py, "
                "which has no build dates. Use the *-recent-builds.csv from --recent, "
                "or pass --fetch-builds."
            )
        raise ValueError(f"Recent-builds CSV is missing org_repo column: {path}")
    if "last_built" in df.columns:
        df["last_built"] = pd.to_datetime(df["last_built"], utc=True, errors="coerce")
        before = len(df)
        df = df[df["last_built"].notna() & (df["last_built"] >= window_start) & (df["last_built"] <= as_of)].copy()
        print(f"Loaded {before} recent-build rows; {len(df)} fall in the lookback window")
    else:
        print(f"Warning: {path} has no last_built column; using all {len(df)} rows as in-window")
    return df


def fetch_recent_builds(window_start, as_of):
    module = load_parse_builds_module()
    print("Fetching qas.json from the CI-build server...")
    qas = module.fetch_json(module.QAS_JSON_URL)
    specs = module.aggregate_specs(qas)
    rows = []
    for spec in specs:
        last_built = pd.Timestamp(spec["last_built"])
        if last_built.tzinfo is None:
            last_built = last_built.tz_localize("UTC")
        else:
            last_built = last_built.tz_convert("UTC")
        if last_built < window_start or last_built > as_of:
            continue
        rows.append(
            {
                "org": spec["org"],
                "repo": spec["repo"],
                "org_repo": spec["org_repo"],
                "title": spec.get("title") or "",
                "name": spec.get("name") or "",
                "package_id": spec.get("package_id") or "",
                "last_built": last_built,
                "ci_url": spec.get("ci_url") or "",
                "github_url": spec.get("github_url") or "",
            }
        )
    df = pd.DataFrame(rows)
    print(f"Fetched {len(df)} CI-build specifications in the lookback window")
    return df


def load_issues_csv(path):
    try:
        df = pd.read_csv(path, quoting=csv.QUOTE_MINIMAL, doublequote=True)
    except Exception as exc:
        print(f"Warning: could not read issues CSV with explicit quoting: {exc}")
        print("Falling back to default CSV reading...")
        df = pd.read_csv(path)
    df.columns = df.columns.str.strip()
    rename = {}
    if "Created Date" not in df.columns and "created" in df.columns:
        rename["created"] = "Created Date"
    if "Specification" not in df.columns and "customfield_11302" in df.columns:
        rename["customfield_11302"] = "Specification"
    if "Issue" not in df.columns and "key" in df.columns:
        rename["key"] = "Issue"
    if rename:
        df = df.rename(columns=rename)
    required = ["Specification", "Created Date"]
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f"Issues CSV is missing required columns: {', '.join(missing)}")
    return df


def explode_spec_rows(issues_df):
    rows = []
    empty_spec = 0
    for _, row in issues_df.iterrows():
        keys = split_specification_keys(row.get("Specification"))
        if not keys:
            empty_spec += 1
            continue
        for key in keys:
            item = row.to_dict()
            item["Specification"] = key
            rows.append(item)
    exploded = pd.DataFrame(rows)
    if empty_spec:
        print(f"Warning: {empty_spec} issue row(s) had an empty Specification and were skipped")
    return exploded


def resolve_as_of_date(explicit_date, *paths):
    if explicit_date:
        try:
            as_of = pd.Timestamp(explicit_date, tz="UTC")
            # A date-only as-of includes that whole UTC day so same-day builds and closes count.
            if re.match(r"^\d{4}-\d{2}-\d{2}$", str(explicit_date).strip()):
                as_of = as_of + pd.Timedelta(days=1) - pd.Timedelta(microseconds=1)
            print(f"Using provided data gathering date: {as_of.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return as_of
        except Exception as exc:
            print(f"Warning: could not parse data gathering date '{explicit_date}': {exc}")

    for path in paths:
        if not path:
            continue
        inferred = extract_timestamp_from_filename(os.path.basename(path))
        if inferred is not None:
            print(f"Extracted data gathering date from {os.path.basename(path)}: {inferred.strftime('%Y-%m-%d %H:%M:%S %Z')}")
            return inferred

    as_of = pd.Timestamp(datetime.now(timezone.utc))
    print(f"Warning: could not determine data gathering date; using now UTC: {as_of.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    return as_of


def prepare_issues(issues_df, as_of, lookback_days, overrides):
    df = explode_spec_rows(issues_df).copy()
    df["Created Date"] = pd.to_datetime(df["Created Date"], errors="coerce", utc=True)
    window_start = as_of - pd.Timedelta(days=lookback_days)
    df["In Lookback"] = (
        df["Created Date"].notna()
        & (df["Created Date"] >= window_start)
        & (df["Created Date"] <= as_of)
    )
    coverage = {
        "rows": len(df),
        "created_min": df["Created Date"].min() if not df.empty else pd.NaT,
        "created_max": df["Created Date"].max() if not df.empty else pd.NaT,
        "in_lookback": int(df["In Lookback"].sum()) if not df.empty else 0,
        "stale": False,
    }
    in_window = df[df["In Lookback"]].copy()
    if not in_window.empty:
        classifications = in_window.apply(
            lambda row: classify_specification(
                row.get("Specification"),
                row.get("Specification URL"),
                row.get("Specification Display Name") or row.get("Summary"),
                overrides,
            ),
            axis=1,
        )
        in_window["Sponsor"] = classifications.apply(lambda c: c["sponsor"])
        in_window["Partner"] = classifications.apply(lambda c: c["partner"])
        in_window["Classification Source"] = classifications.apply(lambda c: c["source"])
    else:
        in_window["Sponsor"] = ""
        in_window["Partner"] = ""
        in_window["Classification Source"] = ""
    if pd.notna(coverage["created_max"]) and coverage["created_max"] < (as_of - pd.Timedelta(days=7)):
        coverage["stale"] = True
        print(
            f"Warning: issues extract Created Date only goes to "
            f"{coverage['created_max'].strftime('%Y-%m-%d')}, but lookback ends "
            f"{as_of.strftime('%Y-%m-%d')}. T will undercount until you refresh the Jira pull.",
            file=sys.stderr,
        )
    return in_window, window_start, coverage


def jira_keys_for_build(org_repo, package_id, specs_index, link_overrides):
    org_repo_l = (org_repo or "").lower()
    keys = []
    sources = []
    if org_repo_l in link_overrides:
        keys.extend(link_overrides[org_repo_l])
        sources.append("link-mapping")
    git_keys = specs_index["by_git"].get(org_repo_l, [])
    if git_keys:
        keys.extend(git_keys)
        sources.append("gitUrl")
    ci_keys = specs_index["by_ci"].get(org_repo_l, [])
    if ci_keys:
        keys.extend(ci_keys)
        sources.append("ciUrl")
    pkg = str(package_id or "").strip().lower()
    if pkg and pkg in specs_index["by_package"]:
        keys.extend(specs_index["by_package"][pkg])
        sources.append("package-id")
    # Preserve order, unique
    unique_keys = list(OrderedDict.fromkeys(k for k in keys if k))
    unique_sources = list(OrderedDict.fromkeys(sources))
    return unique_keys, unique_sources


def org_repos_for_jira_key(spec_key, specs_index, reverse_link):
    repos = []
    sources = []
    if spec_key in reverse_link:
        repos.extend(reverse_link[spec_key])
        sources.append("link-mapping")
    spec_obj = specs_index["by_key"].get(spec_key) or {}
    git_repo = parse_github_org_repo(spec_obj.get("gitUrl") or "")
    ci_repo = parse_ci_org_repo(spec_obj.get("ciUrl") or "")
    if git_repo:
        repos.append(git_repo)
        sources.append("gitUrl")
    if ci_repo:
        repos.append(ci_repo)
        sources.append("ciUrl")
    unique_repos = list(OrderedDict.fromkeys(repos))
    unique_sources = list(OrderedDict.fromkeys(sources))
    return unique_repos, unique_sources


def pick_classification(jira_keys, issue_class_by_key, org, prefix_to_affiliate, overrides, specs_index):
    """Prefer issue/SPECS classification; fall back to GitHub org."""
    for key in jira_keys:
        if key in overrides:
            return dict(overrides[key])
        if key in issue_class_by_key:
            return dict(issue_class_by_key[key])
        spec_obj = specs_index["by_key"].get(key) or {}
        guessed = classify_specification(key, spec_obj.get("url"), spec_obj.get("name"), overrides)
        if guessed["sponsor"] == SPONSOR_PARTNER:
            return guessed
    org_class = classify_github_org(org, prefix_to_affiliate)
    if org_class:
        return org_class
    if jira_keys:
        key = jira_keys[0]
        spec_obj = specs_index["by_key"].get(key) or {}
        return classify_specification(key, spec_obj.get("url"), spec_obj.get("name"), overrides)
    return {
        "sponsor": SPONSOR_OTHER,
        "partner": "",
        "source": "unclassified",
    }


def unique_join(values):
    return ", ".join(str(v) for v in OrderedDict.fromkeys(v for v in values if v not in (None, "", float("nan")) and not (isinstance(v, float) and pd.isna(v))))


def build_universe(
    builds_df,
    issues_in_window,
    specs_index,
    link_overrides,
    prefix_to_affiliate,
    overrides,
    include_other,
):
    reverse_link = defaultdict(list)
    for org_repo, keys in link_overrides.items():
        for key in keys:
            reverse_link[key].append(org_repo)

    issue_by_key = {}
    issue_class_by_key = {}
    if not issues_in_window.empty:
        for spec_key, group in issues_in_window.groupby("Specification"):
            group = group.sort_values("Created Date")
            latest = group.iloc[-1]
            issue_col = "Issue" if "Issue" in group.columns else None
            type_col = "Issue Type" if "Issue Type" in group.columns else None
            display_col = "Specification Display Name" if "Specification Display Name" in group.columns else None
            n_issues = int(group[issue_col].nunique()) if issue_col else len(group)
            issue_by_key[spec_key] = {
                "issues": n_issues,
                "issue_types": unique_join(group[type_col].dropna().astype(str).tolist()) if type_col else "",
                "first_created": group["Created Date"].min(),
                "latest_created": group["Created Date"].max(),
                "display": (
                    unique_join(group[display_col].dropna().astype(str).tolist()) if display_col else ""
                ),
                "sponsor": latest.get("Sponsor"),
                "partner": latest.get("Partner") or "",
                "class_source": latest.get("Classification Source") or "",
            }
            issue_class_by_key[spec_key] = {
                "sponsor": latest.get("Sponsor"),
                "partner": latest.get("Partner") or "",
                "source": latest.get("Classification Source") or "",
            }

    universe = {}
    excluded_other = 0
    excluded_template = 0

    def new_row(identity, org_repo=""):
        return {
            "Identity": identity,
            "Org/Repo": org_repo,
            "Jira Keys": "",
            "Display Name": "",
            "Title": "",
            "Package ID": "",
            "Sponsor": "",
            "Partner": "",
            "Classification Source": "",
            "Source": "",
            "Built in Window": False,
            "Had Issue in Window": False,
            "Issues in Period": 0,
            "Issue Types": "",
            "First Issue Created": pd.NaT,
            "Latest Issue Created": pd.NaT,
            "Last Built": pd.NaT,
            "Product Family": "",
            "Specification URL": "",
            "GitHub URL": "",
            "CI URL": "",
            "Link Method": "",
        }

    def apply_issue(row, spec_key, issue):
        keys = [k for k in (row["Jira Keys"].split(", ") if row["Jira Keys"] else []) if k]
        if spec_key not in keys:
            keys.append(spec_key)
        row["Jira Keys"] = unique_join(keys)
        row["Had Issue in Window"] = True
        row["Issues in Period"] = int(row.get("Issues in Period") or 0) + int(issue["issues"])
        row["Issue Types"] = unique_join(
            [p for p in (row.get("Issue Types") or "").split(", ") if p] + [issue["issue_types"]]
        )
        first_created = row.get("First Issue Created")
        latest_created = row.get("Latest Issue Created")
        if pd.isna(first_created) or issue["first_created"] < first_created:
            row["First Issue Created"] = issue["first_created"]
        if pd.isna(latest_created) or issue["latest_created"] > latest_created:
            row["Latest Issue Created"] = issue["latest_created"]
        if not row["Display Name"]:
            row["Display Name"] = issue["display"] or specs_index["display_names"].get(spec_key, "")
        if row["Built in Window"]:
            row["Source"] = SOURCE_BOTH
        else:
            row["Source"] = SOURCE_ISSUE

    for _, build in builds_df.iterrows():
        org = str(build.get("org") or "").strip()
        repo = str(build.get("repo") or "").strip()
        org_repo = str(build.get("org_repo") or f"{org}/{repo}").strip()
        package_id = str(build.get("package_id") or "").strip()
        if is_publisher_template(repo, package_id):
            excluded_template += 1
            continue
        jira_keys, link_sources = jira_keys_for_build(org_repo, package_id, specs_index, link_overrides)
        if not include_other:
            has_link = bool(jira_keys)
            if not is_in_scope_build(org, has_link, prefix_to_affiliate, include_other):
                excluded_other += 1
                continue

        identity = f"repo:{org_repo.lower()}"
        classification = pick_classification(
            jira_keys, issue_class_by_key, org, prefix_to_affiliate, overrides, specs_index
        )
        if classification["sponsor"] == SPONSOR_OTHER and not include_other:
            excluded_other += 1
            continue

        display = ""
        for key in jira_keys:
            display = specs_index["display_names"].get(key) or display
        raw_title = build.get("title") if pd.notna(build.get("title")) else ""
        raw_name = build.get("name") if pd.notna(build.get("name")) else ""
        title = str(raw_title or raw_name or display or "")

        row = new_row(identity, org_repo)
        row["Jira Keys"] = unique_join(jira_keys)
        row["Display Name"] = display
        row["Title"] = title
        row["Package ID"] = package_id
        row["Sponsor"] = classification["sponsor"]
        row["Partner"] = classification["partner"]
        row["Classification Source"] = classification["source"]
        row["Source"] = SOURCE_BUILD
        row["Built in Window"] = True
        row["Last Built"] = build.get("last_built")
        row["GitHub URL"] = str(build.get("github_url") or "")
        row["CI URL"] = str(build.get("ci_url") or "")
        row["Link Method"] = unique_join(link_sources)
        if jira_keys:
            spec_obj = specs_index["by_key"].get(jira_keys[0]) or {}
            row["Specification URL"] = spec_obj.get("url") or ""
            row["Product Family"] = jira_keys[0].split("-")[0] if "-" in jira_keys[0] else ""
        universe[identity] = row

    matched_issues = 0
    issue_only = 0
    for spec_key, issue in issue_by_key.items():
        candidate_repos, repo_sources = org_repos_for_jira_key(spec_key, specs_index, reverse_link)
        matched_identity = None
        for org_repo in candidate_repos:
            identity = f"repo:{org_repo.lower()}"
            if identity in universe:
                matched_identity = identity
                break
        if not matched_identity:
            # CI row may already list this Jira key even if SPECS reverse lookup missed it.
            for identity, row in universe.items():
                keys = [k for k in (row.get("Jira Keys") or "").split(", ") if k]
                if spec_key in keys:
                    matched_identity = identity
                    break
        if matched_identity:
            row = universe[matched_identity]
            apply_issue(row, spec_key, issue)
            if issue["sponsor"] == SPONSOR_PARTNER:
                row["Sponsor"] = SPONSOR_PARTNER
                row["Partner"] = issue["partner"]
                row["Classification Source"] = issue["class_source"]
            if repo_sources and not row["Link Method"]:
                row["Link Method"] = unique_join(repo_sources)
            matched_issues += 1
        else:
            identity = f"jira:{spec_key}"
            spec_obj = specs_index["by_key"].get(spec_key) or {}
            row = new_row(identity, candidate_repos[0] if candidate_repos else "")
            row["Jira Keys"] = spec_key
            row["Display Name"] = issue["display"] or specs_index["display_names"].get(spec_key, "")
            row["Title"] = row["Display Name"]
            row["Sponsor"] = issue["sponsor"]
            row["Partner"] = issue["partner"]
            row["Classification Source"] = issue["class_source"]
            row["Source"] = SOURCE_ISSUE
            row["Built in Window"] = False
            apply_issue(row, spec_key, issue)
            row["Product Family"] = spec_key.split("-")[0] if "-" in spec_key else ""
            row["Specification URL"] = spec_obj.get("url") or ""
            row["GitHub URL"] = spec_obj.get("gitUrl") or ""
            row["CI URL"] = spec_obj.get("ciUrl") or ""
            row["Link Method"] = unique_join(repo_sources) if repo_sources else "issue-only"
            universe[identity] = row
            issue_only += 1

    before_collapse = len(universe)
    universe = collapse_forks_by_jira_key(universe, specs_index, prefix_to_affiliate)
    collapsed = before_collapse - len(universe)
    if collapsed:
        print(f"Collapsed {collapsed} fork/duplicate repo(s) that share a Jira Specification key")

    print(f"Excluded {excluded_template} publisher-template repo(s)")
    if excluded_other:
        print(f"Excluded {excluded_other} out-of-scope community CI-build repo(s)")
    print(
        f"Universe: {len(universe)} specs "
        f"({sum(1 for r in universe.values() if r['Built in Window'])} built, "
        f"{sum(1 for r in universe.values() if r['Had Issue in Window'])} with a Jira issue, "
        f"{sum(1 for r in universe.values() if r['Source'] == SOURCE_ISSUE)} issue-only, "
        f"{sum(1 for r in universe.values() if r['Source'] == SOURCE_BOTH)} joined build+issue)"
    )

    result = pd.DataFrame(list(universe.values()))
    if result.empty:
        return result
    result = result.sort_values(
        ["Sponsor", "Partner", "Org/Repo", "Jira Keys"],
        kind="mergesort",
    ).reset_index(drop=True)
    return result


def canonical_repo_score(org_repo, jira_keys, specs_index, prefix_to_affiliate):
    """Higher score wins when several GitHub repos map to the same Jira spec."""
    org_repo_l = (org_repo or "").lower()
    org = org_repo_l.split("/", 1)[0] if org_repo_l else ""
    score = 0
    for key in jira_keys:
        spec_obj = specs_index["by_key"].get(key) or {}
        if parse_github_org_repo(spec_obj.get("gitUrl") or "") == org_repo_l:
            score += 100
        if parse_ci_org_repo(spec_obj.get("ciUrl") or "") == org_repo_l:
            score += 50
    if org == "hl7":
        score += 20
    if org in prefix_to_affiliate:
        score += 15
    return score


def collapse_forks_by_jira_key(universe, specs_index, prefix_to_affiliate):
    """
    One Jira Specification key = one specification, even if forks (AuDigitalHealth,
    personal clones) also built in the window.
    Only collapse rows whose Jira Keys set is a single key. Multi-key repo rows stay.
    """
    by_single_key = defaultdict(list)
    for identity, row in universe.items():
        keys = [k for k in (row.get("Jira Keys") or "").split(", ") if k]
        if len(keys) == 1:
            by_single_key[keys[0]].append(identity)

    drop = set()
    for spec_key, identities in by_single_key.items():
        if len(identities) < 2:
            continue
        ranked = sorted(
            identities,
            key=lambda ident: (
                canonical_repo_score(
                    universe[ident].get("Org/Repo") or "",
                    [spec_key],
                    specs_index,
                    prefix_to_affiliate,
                ),
                1 if universe[ident].get("Had Issue in Window") else 0,
                1 if universe[ident].get("Built in Window") else 0,
            ),
            reverse=True,
        )
        keeper = ranked[0]
        for ident in ranked[1:]:
            src = universe[ident]
            dst = universe[keeper]
            dst["Built in Window"] = bool(dst["Built in Window"] or src["Built in Window"])
            dst["Had Issue in Window"] = bool(dst["Had Issue in Window"] or src["Had Issue in Window"])
            if src["Had Issue in Window"]:
                dst["Issues in Period"] = int(dst.get("Issues in Period") or 0) + int(src.get("Issues in Period") or 0)
                dst["Issue Types"] = unique_join(
                    [p for p in (dst.get("Issue Types") or "").split(", ") if p]
                    + [p for p in (src.get("Issue Types") or "").split(", ") if p]
                )
                src_first = src.get("First Issue Created")
                dst_first = dst.get("First Issue Created")
                if pd.notna(src_first) and (pd.isna(dst_first) or src_first < dst_first):
                    dst["First Issue Created"] = src_first
                src_latest = src.get("Latest Issue Created")
                dst_latest = dst.get("Latest Issue Created")
                if pd.notna(src_latest) and (pd.isna(dst_latest) or src_latest > dst_latest):
                    dst["Latest Issue Created"] = src_latest
            if dst["Built in Window"] and src["Built in Window"]:
                dst_built = dst.get("Last Built")
                src_built = src.get("Last Built")
                if pd.notna(src_built) and (pd.isna(dst_built) or src_built > dst_built):
                    dst["Last Built"] = src_built
            if dst["Built in Window"] and dst["Had Issue in Window"]:
                dst["Source"] = SOURCE_BOTH
            drop.add(ident)
        extra = [universe[i].get("Org/Repo") for i in ranked[1:] if universe[i].get("Org/Repo")]
        if extra:
            existing = universe[keeper].get("Link Method") or ""
            note = "collapsed-forks: " + ", ".join(extra)
            universe[keeper]["Link Method"] = unique_join([existing, note])

    return {ident: row for ident, row in universe.items() if ident not in drop}


def md_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        cells = [md_escape(c) for c in row]
        lines.append("| " + " | ".join(cells) + " |")
    return lines


def sponsor_slice(df, sponsor):
    if df.empty:
        return df.iloc[0:0]
    return df[df["Sponsor"] == sponsor]


def summary_counts(df):
    universe = len(df)
    with_issue = int(df["Had Issue in Window"].sum()) if universe else 0
    built = int(df["Built in Window"].sum()) if universe else 0
    both = int((df["Built in Window"] & df["Had Issue in Window"]).sum()) if universe else 0
    build_only = int((df["Built in Window"] & ~df["Had Issue in Window"]).sum()) if universe else 0
    issue_only = int((~df["Built in Window"] & df["Had Issue in Window"]).sum()) if universe else 0
    return {
        "universe": universe,
        "with_issue": with_issue,
        "built": built,
        "both": both,
        "build_only": build_only,
        "issue_only": issue_only,
        "pct": format_pct(with_issue, universe),
    }


def sisc_rate_model_counts(full):
    """
    Translate the Full universe (denominator) row into SISC N, T, N-T cells.

    Fails the process if the four identity checks on that row do not hold.
    """
    u = int(full["universe"])
    b = int(full["with_issue"])
    c = int(full["built"])
    both = int(full["both"])
    build_only = int(full["build_only"])
    issue_only = int(full["issue_only"])

    checks = [
        ("U == C + IssueOnly", u == c + issue_only, f"{u} == {c} + {issue_only}"),
        ("B == Both + IssueOnly", b == both + issue_only, f"{b} == {both} + {issue_only}"),
        ("BuildOnly == C - Both", build_only == c - both, f"{build_only} == {c} - {both}"),
        ("U == BuildOnly + B", u == build_only + b, f"{u} == {build_only} + {b}"),
    ]
    failures = [f"{name} ({expr})" for name, ok, expr in checks if not ok]
    if failures:
        print("SISC sanity checks failed on the Full universe (denominator) row:", file=sys.stderr)
        for item in failures:
            print(f"  {item}", file=sys.stderr)
        sys.exit(1)

    n_minus_t = u - b
    if n_minus_t != build_only:
        print(
            f"SISC sanity checks failed: U - B ({n_minus_t}) != BuildOnly ({build_only})",
            file=sys.stderr,
        )
        sys.exit(1)

    return {
        "U": u,
        "B": b,
        "C": c,
        "Both": both,
        "BuildOnly": build_only,
        "IssueOnly": issue_only,
        "N": u,
        "T": b,
        "N_minus_T": n_minus_t,
    }


def inventory_rows(df, include_partner=False):
    rows = []
    sort_cols = ["Partner", "Jira Keys", "Org/Repo"] if include_partner else ["Jira Keys", "Org/Repo"]
    for _, row in df.sort_values(sort_cols, kind="mergesort").iterrows():
        cells = []
        if include_partner:
            cells.append(row.get("Partner") or "")
        cells.extend(
            [
                row.get("Jira Keys") or "",
                row.get("Org/Repo") or "",
                row.get("Display Name") or row.get("Title") or "",
                "Y" if row.get("Built in Window") else "N",
                "Y" if row.get("Had Issue in Window") else "N",
                format_count(row.get("Issues in Period") or 0) if row.get("Had Issue in Window") else "",
                row.get("Issue Types") or "",
                format_date(row.get("Latest Issue Created")) if row.get("Had Issue in Window") else "",
            ]
        )
        rows.append(cells)
    return rows


def other_org_counts(other_df):
    if other_df.empty:
        return []
    orgs = (
        other_df["Org/Repo"]
        .fillna("")
        .astype(str)
        .str.split("/", n=1)
        .str[0]
        .replace("", "(unknown org)")
    )
    counts = orgs.value_counts()
    return [(org, int(n)) for org, n in counts.items()]


def generate_report(universe, as_of, window_start, lookback_days, issues_csv, builds_label, include_other, issues_coverage):
    md = []
    intl = sponsor_slice(universe, SPONSOR_INTERNATIONAL)
    partners = sponsor_slice(universe, SPONSOR_PARTNER)
    other = sponsor_slice(universe, SPONSOR_OTHER)
    hl7_scope = pd.concat([intl, partners], ignore_index=True) if not universe.empty else universe
    full = summary_counts(universe)
    intl_c = summary_counts(intl)
    partner_c = summary_counts(partners)
    other_c = summary_counts(other)
    hl7_c = summary_counts(hl7_scope)

    created_min = format_date(issues_coverage.get("created_min")) if issues_coverage else "N/A"
    created_max = format_date(issues_coverage.get("created_max")) if issues_coverage else "N/A"

    md.append("# Specifications on HL7 Build and Jira Feedback Infrastructure\n")
    md.append(
        f"> **Lookback:** {lookback_days} days ending {format_date(as_of)} "
        f"({format_date(window_start)} – {format_date(as_of)})\n"
    )
    md.append(
        f"> **Jira issues source:** `{os.path.basename(issues_csv)}` "
        f"(Created Date {created_min} – {created_max}; "
        f"{format_count(issues_coverage.get('in_lookback', 0))} issues in lookback)\n"
    )
    if issues_coverage.get("stale"):
        md.append(
            "> **Coverage warning:** the issues extract ends before the lookback end date. "
            "T is incomplete until you refresh filter 24407 (or equivalent) and rerun.\n"
        )
    md.append(f"> **CI-build source:** {builds_label}\n")
    md.append(
        "> **Denominator (universe):** all specifications with FHIR IG CI-build activity in the "
        "lookback (HL7 International, partners, **and** community/other orgs), plus any "
        "specification that had a Jira issue created in the lookback and is not on that CI pipeline "
        "(V2, older CDA, DAM/functional models, FHIR Core, and similar published specs).\n"
    )
    md.append(
        "> **Primary rates:** of the HL7 International specifications in that universe, "
        "what share had at least one Jira issue created; same question for HL7 partners.\n"
    )
    md.append("")
    md.append("## Table of Contents\n")
    md.append("- [Summary](#summary)")
    md.append("- [SISC Rate Calculation cells](#sisc-rate-calculation-cells)")
    md.append("- [Partner Breakdown](#partner-breakdown)")
    md.append("- [Other (community) CI-builds](#other-community-ci-builds)")
    md.append("- [Built but no Jira issue (HL7 International and partners)](#built-but-no-jira-issue-hl7-international-and-partners)")
    md.append("- [Jira issue but not on the CI builder](#jira-issue-but-not-on-the-ci-builder)")
    md.append("- [Inventory — HL7 International](#inventory--hl7-international)")
    md.append("- [Inventory — HL7 Partners](#inventory--hl7-partners)")
    md.append("- [How the sources are linked](#how-the-sources-are-linked)")
    md.append("- [Methodology](#methodology)")
    md.append("")

    md.append("## Summary\n")
    md.append(
        f"The universe is **{format_count(full['universe'])}** unique specifications in the "
        f"{lookback_days}-day lookback: CI-build activity on the FHIR IG pipeline "
        f"({format_count(full['built'])}, including community orgs) plus "
        f"{format_count(full['issue_only'])} specification(s) with a Jira issue created that are not on that pipeline.\n"
    )
    md.append(
        f"Of **HL7 International** specifications in that universe, "
        f"**{format_count(intl_c['with_issue'])}** of **{format_count(intl_c['universe'])}** "
        f"({intl_c['pct']}) had at least one Jira issue created.\n"
    )
    md.append(
        f"Of **HL7 Partner** specifications, "
        f"**{format_count(partner_c['with_issue'])}** of **{format_count(partner_c['universe'])}** "
        f"({partner_c['pct']}) had at least one Jira issue created.\n"
    )
    headers = [
        "Segment",
        "Specs in universe",
        "Had Jira issue created",
        "Proportion with an issue",
        "Built in window",
        "Both",
        "Build only",
        "Issue only (not on CI)",
    ]

    def metric_row(label, counts, bold=False):
        values = [
            label,
            format_count(counts["universe"]),
            format_count(counts["with_issue"]),
            counts["pct"],
            format_count(counts["built"]),
            format_count(counts["both"]),
            format_count(counts["build_only"]),
            format_count(counts["issue_only"]),
        ]
        if bold:
            values = [f"**{v}**" for v in values]
        return values

    rows = [
        metric_row("Full universe (denominator)", full, bold=True),
        metric_row(SPONSOR_INTERNATIONAL, intl_c),
        metric_row("HL7 Partners (all)", partner_c),
        metric_row("HL7 International + Partners", hl7_c),
        metric_row("Other (community CI-builds)", other_c),
    ]
    md.extend(md_table(headers, rows))
    md.append("")

    sisc = sisc_rate_model_counts(full)
    md.append("## SISC Rate Calculation cells\n")
    md.append(
        f"SISC Rate Calculation cells: N = {format_count(sisc['N'])} specifications in the universe. "
        f"T = {format_count(sisc['T'])} specifications with at least one Jira issue created in the lookback. "
        f"N − T = {format_count(sisc['N_minus_T'])} specifications that used the build pipeline only.\n"
    )
    md.extend(
        md_table(
            ["SISC cell", "Symbol", "Formula", "Value"],
            [
                [
                    "Shared denominator (everyone who pays the shared pool)",
                    "N",
                    "U",
                    format_count(sisc["N"]),
                ],
                [
                    "Full-process count (only those who pay the full-process pool)",
                    "T",
                    "B",
                    format_count(sisc["T"]),
                ],
                [
                    "Tier 1 count (build and publication only)",
                    "N − T",
                    "U - B which equals BuildOnly",
                    format_count(sisc["N_minus_T"]),
                ],
            ],
        )
    )
    md.append("")
    md.append(
        "N includes CI-build specs and issue-only specs not on the FHIR IG CI builder. "
        "T is unique Specification keys with an issue created in the lookback, including those issue-only specs. "
        "This is services consumed (Jira feedback vs build-only), not HL7 vs partner vs community.\n"
    )

    md.append("## Partner Breakdown\n")
    if partners.empty:
        md.append("No partner specifications were in the universe for this lookback.\n")
    else:
        md.append(
            "HL7 partner / affiliate specifications in the universe, and the share of each "
            "that had at least one Jira issue created.\n"
        )
        partner_rows = []
        grouped = partners.groupby(partners["Partner"].replace("", "(unnamed partner)"))
        breakdown = []
        for name, group in grouped:
            breakdown.append((name, summary_counts(group)))
        breakdown.sort(key=lambda item: (-item[1]["universe"], item[0]))
        for name, counts in breakdown:
            partner_rows.append(metric_row(name, counts))
        md.extend(md_table(headers, partner_rows))
        md.append("")

    md.append("## Other (community) CI-builds\n")
    md.append(
        "GitHub orgs on the FHIR IG CI pipeline that are not HL7 International and not an "
        "affiliate-roster partner. They are in the **denominator** so the universe is all "
        "FHIR specs being built, not only HL7's. They rarely have issues on jira.hl7.org.\n"
    )
    if other.empty:
        md.append("None.\n")
    else:
        md.append(
            f"{format_count(other_c['universe'])} specification(s) "
            f"({format_count(other_c['with_issue'])} had a Jira issue created, {other_c['pct']}). "
            "Counts by GitHub organization:\n"
        )
        org_rows = [[org, format_count(n)] for org, n in other_org_counts(other)]
        md.extend(md_table(["GitHub org", "Specs in window"], org_rows))
        md.append("")

    build_only = (
        hl7_scope[hl7_scope["Built in Window"] & ~hl7_scope["Had Issue in Window"]].copy()
        if not hl7_scope.empty
        else hl7_scope
    )
    issue_only_df = (
        universe[~universe["Built in Window"] & universe["Had Issue in Window"]].copy()
        if not universe.empty
        else universe
    )

    md.append("## Built but no Jira issue (HL7 International and partners)\n")
    md.append(
        "HL7 International and partner specifications with CI-build activity in the lookback "
        "that did **not** have a Jira issue created in the same window. Community CI-builds are "
        "counted in the denominator above but omitted from this list.\n"
    )
    if build_only.empty:
        md.append("None.\n")
    else:
        md.append(f"{format_count(len(build_only))} specification(s).\n")
        md.extend(
            md_table(
                ["Sponsor", "Partner", "Jira Key(s)", "Org/Repo", "Title", "Package ID", "Last built"],
                [
                    [
                        row["Sponsor"],
                        row.get("Partner") or "",
                        row.get("Jira Keys") or "",
                        row.get("Org/Repo") or "",
                        row.get("Display Name") or row.get("Title") or "",
                        row.get("Package ID") or "",
                        format_date(row.get("Last Built")),
                    ]
                    for _, row in build_only.sort_values(["Sponsor", "Partner", "Org/Repo"]).iterrows()
                ],
            )
        )
        md.append("")

    md.append("## Jira issue but not on the CI builder\n")
    md.append(
        "Specifications with at least one Jira issue created in the lookback that did **not** have "
        "CI-build activity in the same window. Typical for V2, older CDA zips, DAM/functional-model "
        "documents, and FHIR Core (which uses a different build path than `build.fhir.org/ig/{org}/{repo}`).\n"
    )
    if issue_only_df.empty:
        md.append("None.\n")
    else:
        md.append(f"{format_count(len(issue_only_df))} specification(s).\n")
        md.extend(
            md_table(
                ["Sponsor", "Partner", "Jira Key", "Display Name", "Product Family", "Issues", "Latest Issue Created"],
                [
                    [
                        row["Sponsor"],
                        row.get("Partner") or "",
                        row.get("Jira Keys") or "",
                        row.get("Display Name") or row.get("Title") or "",
                        row.get("Product Family") or "",
                        format_count(row.get("Issues in Period") or 0),
                        format_date(row.get("Latest Issue Created")),
                    ]
                    for _, row in issue_only_df.sort_values(["Sponsor", "Partner", "Jira Keys"]).iterrows()
                ],
            )
        )
        md.append("")

    inv_headers = [
        "Jira Key(s)",
        "Org/Repo",
        "Display Name",
        "Built",
        "Had issue",
        "Issues",
        "Issue Types",
        "Latest Issue Created",
    ]
    md.append("## Inventory — HL7 International\n")
    if intl.empty:
        md.append("None.\n")
    else:
        md.append(f"{format_count(len(intl))} specification(s); {format_count(intl_c['with_issue'])} had a Jira issue created ({intl_c['pct']}).\n")
        md.extend(md_table(inv_headers, inventory_rows(intl)))
        md.append("")

    md.append("## Inventory — HL7 Partners\n")
    if partners.empty:
        md.append("None.\n")
    else:
        partner_inv_headers = ["Partner"] + inv_headers
        md.append(f"{format_count(len(partners))} specification(s); {format_count(partner_c['with_issue'])} had a Jira issue created ({partner_c['pct']}).\n")
        md.extend(md_table(partner_inv_headers, inventory_rows(partners, include_partner=True)))
        md.append("")

    md.append("## How the sources are linked\n")
    md.append("A CI-build `org/repo` is joined to a Jira Specification key using, in order:")
    md.append("")
    md.append("1. Optional `--link-mapping` CSV (`org_repo`, `Specification`) for manual exceptions.")
    md.append("2. `SPECS.json` `gitUrl` (`https://github.com/{org}/{repo}`), compared case-insensitively.")
    md.append("3. `SPECS.json` `ciUrl` (`http://build.fhir.org/ig/{org}/{repo}`).")
    md.append("4. CI-build `package_id` vs a package id reconstructed from the SPECS canonical `url`.")
    md.append("")
    md.append(
        "SPECS.json is the Jira spec registry ([HL7/JIRA-Spec-Artifacts](https://github.com/HL7/JIRA-Spec-Artifacts)). "
        "That is why `HL7/US-Core` matches `FHIR-us-core`, `hl7au/au-fhir-core` matches `FHIR-au-core`, "
        "and `HL7/piqi` matches `OTHER-piqi-framework`."
    )
    md.append("")
    md.append(
        "After the join, identity is **org/repo** for anything on the CI builder (so many issues on the "
        "same IG stay one specification). Specification keys with an in-window issue and no matching "
        "in-window build are appended as issue-only rows keyed by the Jira Specification."
    )
    md.append("")

    md.append("## Methodology\n")
    md.append(
        f"- **Lookback:** issue Created Date and CI `last_built` in "
        f"[{window_start.strftime('%Y-%m-%d')}, {as_of.strftime('%Y-%m-%d %H:%M:%S %Z')}], inclusive."
    )
    md.append("- **T / numerator:** unique Specification key with at least one Jira specification-feedback issue created in the lookback (any issue type: Change Request, Technical Correction, Question, Comment). Not a closed BALDEF.")
    md.append("- **Universe / denominator:** every non-template CI-build `org/repo` in the lookback (including community GitHub orgs) plus Specification keys with an in-window issue that did not match a CI-build row (HL7-tracked specs published outside the IG pipeline).")
    md.append("- **Primary rates:** (HL7 International specs that had an issue created) / (HL7 International specs in the universe), and the same for partners. Community specs are in the denominator of the full universe, not of those two rates.")
    md.append("- **Excluded from the universe:** IG publisher templates (`ig-template-*` / `*.template`). `--exclude-community` also drops community CI-builds.")
    md.append("- **International vs partner (issue side):** partner-mapping CSV, then URL host, then Jira key token (`FHIR-au-*`, `FHIR-eu-*`), then display name / summary text.")
    md.append("- **International vs partner (build side, no Jira key):** GitHub org vs affiliate roster `Build Prefix` (`hl7au` → HL7 Australia, `hl7-eu` → HL7 Europe, `HL7` → International).")
    md.append("- **Not partners:** `FHIR-us-*` / `FHIR-uv-*` and GitHub org `HL7` even when the realm is US or Universal.")
    md.append("- **This script does not use** ballot-participation CSVs, BALDEF close dates, org mapping, or balloter overrides.")
    md.append("")
    return "\n".join(md)


def write_csv(universe, path):
    out = universe.copy()
    for col in ("First Issue Created", "Latest Issue Created", "Last Built"):
        if col in out.columns:
            out[col] = pd.to_datetime(out[col], utc=True, errors="coerce").dt.strftime("%Y-%m-%d")
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    out.to_csv(path, index=False)
    print(f"Wrote specification inventory CSV: {path}")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Proportion of specifications (CI-build and/or Jira issue, unique spec) "
            "that had a specification-feedback issue created in a lookback window, "
            "by International vs partners."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 scripts/parse-jira-filter-export-csv-md.py \\
      -f '{"jql": "project in (FHIR, CDA, V2, OTHER) AND Specification is not EMPTY AND created >= -400d ORDER BY created DESC"}' \\
      -d 'key,fields.created,fields.customfield_11302,fields.spec_display_name,fields.issuetype.name,fields.status.name' \\
      -o data/working/issue-analysis/2026/lookback/all-spec-feedback-issues \\
      -e csv --cache --cache-dir data/working/cache

  python3 scripts/parse-builds-web.py --recent --days 365

  python3 scripts/standards-infrastructure-usage/standards-infrastructure-specs-analyze.py \\
      --issues-csv data/working/issue-analysis/2026/lookback/all-spec-feedback-issues.csv \\
      --recent-builds-csv data/working/builds/20260821-060233-recent-builds.csv \\
      -o data/working/standards-infrastructure-usage/reports/2026-08-21-standards-infrastructure-specs.md \\
      --lookback-days 365 \\
      --data-gathering-date 2026-08-21 \\
      --csv data/working/standards-infrastructure-usage/reports/2026-08-21-standards-infrastructure-specs.csv
        """,
    )
    parser.add_argument(
        "--issues-csv",
        required=True,
        help="Jira specification-feedback issue CSV (must include Specification and Created Date)",
    )
    parser.add_argument(
        "--recent-builds-csv",
        help="Recent-activity CSV from parse-builds-web.py --recent (not the unique org/repo list)",
    )
    parser.add_argument(
        "--fetch-builds",
        action="store_true",
        help="Fetch qas.json live instead of reading --recent-builds-csv (no Jira/VPN needed)",
    )
    parser.add_argument("-o", "--output", required=True, help="Output Markdown file path")
    parser.add_argument("--lookback-days", type=int, default=365, help="Lookback length in days (default: 365)")
    parser.add_argument(
        "--data-gathering-date",
        metavar="YYYY-MM-DD",
        help="As-of date for the window. Inferred from filenames if omitted.",
    )
    parser.add_argument("--csv", dest="csv_path", help="Optional universe inventory CSV path")
    parser.add_argument("--partner-mapping", help="Optional Specification/Sponsor/Partner overrides")
    parser.add_argument(
        "--link-mapping",
        help="Optional org_repo,Specification CSV to force a CI-build ↔ Jira-key join",
    )
    parser.add_argument(
        "--affiliate-roster",
        default=DEFAULT_AFFILIATE_ROSTER,
        help=f"Affiliate roster with Build Prefix column (default: {DEFAULT_AFFILIATE_ROSTER})",
    )
    parser.add_argument(
        "--exclude-community",
        action="store_true",
        help="Drop community/other CI-build orgs from the universe (default: they are included in the denominator)",
    )
    args = parser.parse_args()

    if args.lookback_days < 1:
        parser.error("--lookback-days must be at least 1")
    if not args.recent_builds_csv and not args.fetch_builds:
        parser.error("Provide --recent-builds-csv (from parse-builds-web.py --recent) or --fetch-builds")
    if args.recent_builds_csv and args.fetch_builds:
        parser.error("Use either --recent-builds-csv or --fetch-builds, not both")

    os.chdir(PROJECT_ROOT)
    as_of = resolve_as_of_date(args.data_gathering_date, args.issues_csv, args.recent_builds_csv)
    window_start = as_of - pd.Timedelta(days=args.lookback_days)
    print(f"Lookback window: {window_start.strftime('%Y-%m-%d')} to {as_of.strftime('%Y-%m-%d %H:%M:%S %Z')} ({args.lookback_days} days)")

    overrides = load_partner_overrides(args.partner_mapping)
    link_overrides = load_link_overrides(args.link_mapping)
    prefix_to_affiliate = load_affiliate_prefixes(args.affiliate_roster)
    specs_index = load_specs_index()

    print(f"Loading Jira issue data from {args.issues_csv}")
    issues_df = load_issues_csv(args.issues_csv)
    print(f"Loaded {len(issues_df)} issue rows")
    issues_in_window, _window_start, issues_coverage = prepare_issues(
        issues_df, as_of, args.lookback_days, overrides
    )
    issue_id_col = "Issue" if "Issue" in issues_in_window.columns else None
    n_issues = issues_in_window[issue_id_col].nunique() if issue_id_col and not issues_in_window.empty else len(issues_in_window)
    n_keys = issues_in_window["Specification"].nunique() if not issues_in_window.empty else 0
    print(f"In-window issues created: {n_issues} ({n_keys} unique Jira Specification keys)")

    if args.fetch_builds:
        builds_df = fetch_recent_builds(window_start, as_of)
        builds_label = "qas.json (live fetch)"
    else:
        print(f"Loading recent CI-build data from {args.recent_builds_csv}")
        builds_df = load_recent_builds_csv(args.recent_builds_csv, window_start, as_of)
        builds_label = f"`{os.path.basename(args.recent_builds_csv)}`"

    include_other = not args.exclude_community
    universe = build_universe(
        builds_df,
        issues_in_window,
        specs_index,
        link_overrides,
        prefix_to_affiliate,
        overrides,
        include_other,
    )

    intl_c = summary_counts(sponsor_slice(universe, SPONSOR_INTERNATIONAL))
    partner_c = summary_counts(sponsor_slice(universe, SPONSOR_PARTNER))
    other_n = len(sponsor_slice(universe, SPONSOR_OTHER))
    print(
        f"Full universe: {len(universe)} "
        f"(International={intl_c['universe']}, Partners={partner_c['universe']}, Other={other_n})"
    )
    print(
        f"  HL7 International with a Jira issue created: "
        f"{intl_c['with_issue']} / {intl_c['universe']} ({intl_c['pct']})"
    )
    print(
        f"  HL7 Partners with a Jira issue created: "
        f"{partner_c['with_issue']} / {partner_c['universe']} ({partner_c['pct']})"
    )

    report = generate_report(
        universe,
        as_of,
        window_start,
        args.lookback_days,
        args.issues_csv,
        builds_label,
        include_other,
        issues_coverage,
    )
    output_dir = os.path.dirname(args.output)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write(report)
    print(f"Wrote report: {args.output}")

    if args.csv_path:
        write_csv(universe, args.csv_path)

    print("Done!")


if __name__ == "__main__":
    main()
