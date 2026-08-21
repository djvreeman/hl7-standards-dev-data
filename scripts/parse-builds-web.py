#!/usr/local/bin/python3
# -*- coding: utf-8 -*-

# Overview:
#
# Reads the FHIR IG CI-build registry (build.fhir.org) and exports:
#   1. A CSV of every unique org/repo hooked up to the pipeline (builds.json)
#   2. Optionally, a recent-activity summary of specifications built inside a
#      configurable time window, plus a subset for one or more GitHub orgs.
#
# Dates come from https://build.fhir.org/ig/qas.json — the same feed the
# auto-ig-builder "What's building right now?" dashboard uses.
# See: https://fhir.github.io/auto-ig-builder/
#
# Organization matching is exact on the GitHub org name (case-insensitive).
# --orgs HL7 matches HL7/… only, not HL7-cz, hl7-eu, HL7Austria, etc.
#
# Usage:
#   python3 scripts/parse-builds-web.py
#   python3 scripts/parse-builds-web.py -o data/working/builds/build-repos.csv
#   python3 scripts/parse-builds-web.py --recent
#   python3 scripts/parse-builds-web.py --recent --days 365 --orgs HL7
#   python3 scripts/parse-builds-web.py --recent --days 90 --orgs HL7 FHIR HL7-cz

import argparse
import csv
import datetime
import os
import re
from collections import defaultdict

import requests

BUILDS_JSON_URL = "https://build.fhir.org/ig/builds.json"
QAS_JSON_URL = "https://build.fhir.org/ig/qas.json"
CI_BUILD_BASE = "https://build.fhir.org/ig"
GITHUB_BASE = "https://github.com"
REQUEST_HEADERS = {
    "User-Agent": "hl7-standards-dev-data/parse-builds-web.py",
    "Accept": "application/json",
}
REQUEST_TIMEOUT = 120

# Format current date and time as YYYYMMDD-HHMMSS
current_time = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")

RECENT_CSV_COLUMNS = [
    "org",
    "repo",
    "org_repo",
    "title",
    "name",
    "package_id",
    "ig_ver",
    "fhir_version",
    "status",
    "last_built",
    "last_built_branch",
    "failing",
    "errs",
    "warnings",
    "branches_in_window",
    "ci_url",
    "github_url",
]


def fetch_json(url):
    """GET a JSON document from the CI-build server."""
    response = requests.get(url, headers=REQUEST_HEADERS, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.json()


def unique_org_repos(builds):
    """Return a sorted unique list of org/repo from builds.json path entries."""
    parsed_entries = [
        "/".join(entry.split("/")[:2]) for entry in builds if isinstance(entry, str)
    ]
    return sorted(set(parsed_entries))


def parse_json_and_write_csv(output_file, builds=None):
    """Fetch (or reuse) builds.json and write unique org/repo rows to CSV."""
    if builds is None:
        builds = fetch_json(BUILDS_JSON_URL)
    unique_parsed_entries = unique_org_repos(builds)
    write_unique_repos_csv(output_file, unique_parsed_entries)
    return unique_parsed_entries


def write_unique_repos_csv(output_file, unique_parsed_entries):
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        for entry in unique_parsed_entries:
            writer.writerow([entry])


def parse_orgs_arg(values):
    """Split --orgs values that may be space- and/or comma-separated."""
    orgs = []
    for value in values or []:
        for part in value.split(","):
            part = part.strip()
            if part:
                orgs.append(part)
    return orgs


def org_matches(org, selected_orgs):
    """Exact org-name match, case-insensitive. HL7 does not match HL7-cz."""
    org_lower = org.lower()
    return any(org_lower == selected.lower() for selected in selected_orgs)


def parse_repo_path(repo_path):
    """Parse a qas.json/builds.json path like Org/repo/branches/branch[/failure]/qa.json."""
    parts = [p for p in (repo_path or "").split("/") if p]
    org = parts[0] if len(parts) > 0 else ""
    repo = parts[1] if len(parts) > 1 else ""
    branch = parts[3] if len(parts) > 3 else "master"
    failing = "failure" in parts
    return org, repo, branch, failing


def parse_qa_date(entry):
    """Parse a QA record's timestamp, preferring dateISO8601."""
    iso = entry.get("dateISO8601") or ""
    if iso:
        try:
            return datetime.datetime.fromisoformat(iso.replace("Z", "+00:00"))
        except ValueError:
            pass
    raw = entry.get("date") or ""
    if raw:
        try:
            return datetime.datetime.strptime(raw, "%a, %d %b, %Y %H:%M:%S %z")
        except ValueError:
            pass
    return None


def ensure_aware(dt):
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=datetime.timezone.utc)
    return dt


def aggregate_specs(qa_entries):
    """
    Collapse per-branch QA records into one specification per org/repo,
    keeping the most recently built branch as the representative record.
    """
    branches_by_repo = defaultdict(list)
    for entry in qa_entries:
        if not isinstance(entry, dict):
            continue
        org, repo, branch, failing = parse_repo_path(entry.get("repo", ""))
        if not org or not repo:
            continue
        built_at = ensure_aware(parse_qa_date(entry))
        if built_at is None:
            continue
        branches_by_repo[f"{org}/{repo}"].append(
            {
                "org": org,
                "repo": repo,
                "branch": branch,
                "failing": failing or bool(entry.get("exception")),
                "built_at": built_at,
                "title": (entry.get("title") or "").strip(),
                "name": (entry.get("name") or "").strip(),
                "package_id": (entry.get("package-id") or "").strip(),
                "ig_ver": str(entry.get("ig-ver") or "").strip(),
                "fhir_version": str(entry.get("version") or "").strip(),
                "status": str(entry.get("status") or "").strip(),
                "errs": entry.get("errs", ""),
                "warnings": entry.get("warnings", ""),
            }
        )

    specs = []
    for org_repo, branches in branches_by_repo.items():
        branches.sort(key=lambda b: b["built_at"], reverse=True)
        latest = branches[0]
        org = latest["org"]
        repo = latest["repo"]
        specs.append(
            {
                "org": org,
                "repo": repo,
                "org_repo": org_repo,
                "title": latest["title"],
                "name": latest["name"],
                "package_id": latest["package_id"],
                "ig_ver": latest["ig_ver"],
                "fhir_version": latest["fhir_version"],
                "status": latest["status"],
                "last_built": latest["built_at"],
                "last_built_branch": latest["branch"],
                "failing": latest["failing"],
                "errs": latest["errs"],
                "warnings": latest["warnings"],
                "branches": branches,
                "ci_url": f"{CI_BUILD_BASE}/{org}/{repo}",
                "github_url": f"{GITHUB_BASE}/{org}/{repo}",
            }
        )
    specs.sort(key=lambda s: s["last_built"], reverse=True)
    return specs


def filter_specs_in_window(specs, cutoff):
    return [s for s in specs if s["last_built"] >= cutoff]


def branches_in_window(spec, cutoff):
    return [b for b in spec["branches"] if b["built_at"] >= cutoff]


def counts_by_org(specs):
    counts = defaultdict(int)
    for spec in specs:
        counts[spec["org"]] += 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0].lower()))


def registry_count_for_org(registry_org_counts, org):
    """Look up a registry org count with case-insensitive fallback."""
    if org in registry_org_counts:
        return registry_org_counts[org]
    org_lower = org.lower()
    for registry_org, count in registry_org_counts.items():
        if registry_org.lower() == org_lower:
            return count
    return 0


def md_escape(value):
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def format_dt(dt):
    if dt is None:
        return ""
    return ensure_aware(dt).astimezone(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def format_iso(dt):
    if dt is None:
        return ""
    return ensure_aware(dt).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def write_recent_csv(output_file, specs, cutoff):
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
    with open(output_file, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=RECENT_CSV_COLUMNS)
        writer.writeheader()
        for spec in specs:
            writer.writerow(
                {
                    "org": spec["org"],
                    "repo": spec["repo"],
                    "org_repo": spec["org_repo"],
                    "title": spec["title"],
                    "name": spec["name"],
                    "package_id": spec["package_id"],
                    "ig_ver": spec["ig_ver"],
                    "fhir_version": spec["fhir_version"],
                    "status": spec["status"],
                    "last_built": format_iso(spec["last_built"]),
                    "last_built_branch": spec["last_built_branch"],
                    "failing": "Y" if spec["failing"] else "N",
                    "errs": spec["errs"],
                    "warnings": spec["warnings"],
                    "branches_in_window": len(branches_in_window(spec, cutoff)),
                    "ci_url": spec["ci_url"],
                    "github_url": spec["github_url"],
                }
            )


def write_spec_table(lines, specs):
    lines.append(
        "| Org/Repo | Title | Package | Last built | Branch | Failing | CI |"
    )
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for spec in specs:
        org_repo = f"[{md_escape(spec['org_repo'])}]({spec['github_url']})"
        title = md_escape(spec["title"] or spec["name"])
        package = md_escape(spec["package_id"])
        last_built = format_dt(spec["last_built"])
        branch = md_escape(spec["last_built_branch"])
        failing = "Y" if spec["failing"] else "N"
        ci = f"[build]({spec['ci_url']})"
        lines.append(
            f"| {org_repo} | {title} | {package} | {last_built} | {branch} | {failing} | {ci} |"
        )


def write_markdown_summary(
    output_file,
    unique_repos,
    recent_specs,
    subset_specs_by_org,
    selected_orgs,
    days,
    cutoff,
    now,
):
    output_dir = os.path.dirname(output_file)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    registry_count = len(unique_repos)
    recent_count = len(recent_specs)
    pct = (100.0 * recent_count / registry_count) if registry_count else 0.0
    org_counts = counts_by_org(recent_specs)
    registry_org_counts = defaultdict(int)
    for entry in unique_repos:
        org = entry.split("/", 1)[0]
        registry_org_counts[org] += 1

    lines = [
        "# CI-Build Registry — Recent Activity",
        "",
        f"- **Window:** last {days} day{'s' if days != 1 else ''} "
        f"({format_dt(cutoff)} through {format_dt(now)})",
        f"- **Registry (unique org/repo):** {registry_count}",
        f"- **Built in window:** {recent_count} ({pct:.1f}% of registry)",
        f"- **Sources:** [{BUILDS_JSON_URL}]({BUILDS_JSON_URL}), [{QAS_JSON_URL}]({QAS_JSON_URL})",
        "- **Dashboard:** [auto-ig-builder recent activity](https://fhir.github.io/auto-ig-builder/)",
        "- A specification is counted if **any** branch produced a QA build in the window. "
        "The row shows the most recently built branch.",
        "- Organization filters match the GitHub org name exactly (case-insensitive). "
        "`HL7` does not include `HL7-cz`, `hl7-eu`, etc.",
        "",
        "## Summary of all specifications built in the window",
        "",
        f"**{recent_count}** unique specifications had CI-build activity in the last {days} days.",
        "",
        "### Counts by organization",
        "",
        "| Organization | Specs in window | Specs in registry |",
        "| --- | ---: | ---: |",
    ]
    for org, count in org_counts:
        lines.append(
            f"| {md_escape(org)} | {count} | {registry_count_for_org(registry_org_counts, org)} |"
        )

    for org in selected_orgs:
        subset = subset_specs_by_org.get(org, [])
        in_registry = registry_count_for_org(registry_org_counts, org)
        lines.extend(
            [
                "",
                f"## Subset: `{org}/`",
                "",
                f"**{len(subset)}** of **{in_registry}** `{org}/` specifications in the registry "
                f"were built in the last {days} days.",
                "",
            ]
        )
        if subset:
            write_spec_table(lines, subset)
        else:
            lines.append("_No matching specifications in this window._")

    lines.extend(
        [
            "",
            "## All specifications built in the window",
            "",
            f"**{recent_count}** unique specifications had CI-build activity in the last {days} days.",
            "",
        ]
    )
    write_spec_table(lines, recent_specs)

    with open(output_file, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines) + "\n")


def print_console_summary(
    unique_repos,
    recent_specs,
    subset_specs_by_org,
    selected_orgs,
    days,
    cutoff,
):
    registry_count = len(unique_repos)
    recent_count = len(recent_specs)
    print(
        f"Built in last {days} days (since {format_dt(cutoff)}): "
        f"{recent_count} of {registry_count} registry specs"
    )
    registry_org_counts = defaultdict(int)
    for entry in unique_repos:
        registry_org_counts[entry.split("/", 1)[0].lower()] += 1
    for org in selected_orgs:
        subset = subset_specs_by_org.get(org, [])
        in_registry = registry_org_counts.get(org.lower(), 0)
        print(
            f"  {org}/: {len(subset)} of {in_registry} registry specs built in window"
        )


def recent_output_stem(unique_repos_output):
    """Derive sibling output paths from the unique-repos CSV path."""
    directory = os.path.dirname(unique_repos_output) or "data/working/builds"
    basename = os.path.basename(unique_repos_output)
    stem, _ext = os.path.splitext(basename)
    stem = re.sub(r"-build-repos$", "", stem) or current_time
    return os.path.join(directory, stem)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Export the FHIR CI-build registry (unique org/repos) and optionally "
            "summarize specifications built in a time window, with an org subset."
        )
    )
    parser.add_argument(
        "-o",
        "--output",
        default=f"data/working/builds/{current_time}-build-repos.csv",
        help="Path to the unique org/repo CSV file.",
    )
    parser.add_argument(
        "--recent",
        action="store_true",
        help=(
            "Also summarize specifications built in the time window "
            "(from qas.json) and write CSV + Markdown reports."
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=365,
        help="Time window in days for --recent (default: 365).",
    )
    parser.add_argument(
        "--orgs",
        nargs="+",
        default=["HL7"],
        help=(
            "GitHub org(s) for the subset section. Exact name match, not a prefix: "
            "HL7 does not include HL7-cz. Space- or comma-separated. Default: HL7"
        ),
    )
    parser.add_argument(
        "--recent-csv",
        default=None,
        help="Path for the recent-activity CSV (default: alongside -o).",
    )
    parser.add_argument(
        "--summary",
        default=None,
        help="Path for the Markdown summary (default: alongside -o).",
    )

    args = parser.parse_args()
    if args.days < 1:
        parser.error("--days must be >= 1")

    selected_orgs = parse_orgs_arg(args.orgs)
    builds = fetch_json(BUILDS_JSON_URL)
    unique_parsed_entries = unique_org_repos(builds)
    write_unique_repos_csv(args.output, unique_parsed_entries)
    # Keep this first "written to" line unchanged so manage-affiliate-roster.py
    # still discovers the unique-repos CSV from stdout.
    print(
        f"Data has been written to: {args.output}\n"
        f"Number of entries: {len(unique_parsed_entries)}"
    )

    if not args.recent:
        raise SystemExit(0)

    qas = fetch_json(QAS_JSON_URL)
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=args.days)
    all_specs = aggregate_specs(qas)
    recent_specs = filter_specs_in_window(all_specs, cutoff)
    subset_specs_by_org = {
        org: [s for s in recent_specs if org_matches(s["org"], [org])]
        for org in selected_orgs
    }

    stem = recent_output_stem(args.output)
    recent_csv_path = args.recent_csv or f"{stem}-recent-builds.csv"
    summary_path = args.summary or f"{stem}-recent-builds.md"

    write_recent_csv(recent_csv_path, recent_specs, cutoff)
    write_markdown_summary(
        summary_path,
        unique_parsed_entries,
        recent_specs,
        subset_specs_by_org,
        selected_orgs,
        args.days,
        cutoff,
        now,
    )
    print_console_summary(
        unique_parsed_entries,
        recent_specs,
        subset_specs_by_org,
        selected_orgs,
        args.days,
        cutoff,
    )
    print(f"Recent-activity CSV: {recent_csv_path}")
    print(f"Markdown summary: {summary_path}")
