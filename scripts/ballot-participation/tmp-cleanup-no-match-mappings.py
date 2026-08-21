#!/usr/bin/env python3
"""
TEMP cleanup tool: surface (and optionally fix) org-mapping rows where
Status='No Match' but the Canonical_Organization actually differs from
Jira_Organization. ``apply-org-mapping.py`` silently skips any row whose
Status='No Match', so these rows look like real mappings on disk but are
ignored at runtime — which produces the override-vs-mapping conflict warnings
during the override merge.

This script does not invent mappings. It only flips Status for rows where
Canonical_Organization is non-empty AND already differs from Jira_Organization
(i.e. rows that were curated as a mapping but flagged 'No Match').

USAGE:
    # Dry run (default): list candidate rows
    python3 tmp-cleanup-no-match-mappings.py \\
        -m data/working/ballot-participation/org-mapping.csv

    # Limit to mappings whose Jira_Organization actually appears in the
    # current ballot data (recommended)
    python3 tmp-cleanup-no-match-mappings.py \\
        -m data/working/ballot-participation/org-mapping.csv \\
        --ballot-csv data/working/ballot-participation/ballot_participation-20260507-105431.csv

    # Apply the changes (writes to -m). Default new Status is 'Manual Override'
    # and Match_Score is left as-is (or set to 100 with --set-score).
    python3 tmp-cleanup-no-match-mappings.py \\
        -m data/working/ballot-participation/org-mapping.csv \\
        --ballot-csv data/working/ballot-participation/ballot_participation-20260507-105431.csv \\
        --apply

    # Print the equivalent update-org-mapping.py invocations instead of
    # editing the file (useful for review/git log).
    python3 tmp-cleanup-no-match-mappings.py \\
        -m data/working/ballot-participation/org-mapping.csv \\
        --print-commands

DELETE this file once the curated set is healthy and conflicts no longer fire.
"""

import argparse
import csv
import os
import shlex
import sys

import pandas as pd


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    s = str(value).strip()
    return s == "" or s.lower() == "nan"


def find_candidates(df_mapping: pd.DataFrame) -> pd.DataFrame:
    """Rows where Status='No Match' and Canonical != Jira and Canonical is non-empty."""
    df = df_mapping.copy()
    if "Status" not in df.columns:
        return df.iloc[0:0]
    status = df["Status"].astype(str).str.strip()
    jira = df["Jira_Organization"].astype(str).str.strip()
    canon = df["Canonical_Organization"].astype(str).str.strip()
    mask = (status == "No Match") & (~canon.apply(_is_blank)) & (canon != jira)
    return df[mask].copy()


def filter_to_used_in_ballots(candidates: pd.DataFrame, ballot_csv: str) -> pd.DataFrame:
    if not os.path.exists(ballot_csv):
        print(f"⚠️  --ballot-csv not found: {ballot_csv}; not filtering")
        return candidates
    print(f"📂 Loading ballot data to filter candidates: {ballot_csv}")
    df_ballots = pd.read_csv(ballot_csv, dtype=str, keep_default_na=False)
    used = set(df_ballots.get("Organization", pd.Series([], dtype=str)).astype(str).str.strip())
    keep = candidates["Jira_Organization"].astype(str).str.strip().isin(used)
    return candidates[keep].copy()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Find/fix org-mapping rows whose Status='No Match' but Canonical actually differs from Jira."
    )
    parser.add_argument("-m", "--mapping", required=True, help="Path to org-mapping CSV")
    parser.add_argument(
        "--ballot-csv",
        default=None,
        help="Optional ballot_participation CSV to limit candidates to mappings actually used in ballots.",
    )
    parser.add_argument(
        "--new-status",
        default="Manual Override",
        help="Status value to set when --apply (default: 'Manual Override').",
    )
    parser.add_argument(
        "--set-score",
        type=float,
        default=None,
        help="Optionally set Match_Score for affected rows (e.g. 100). Leaves it untouched otherwise.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes back to -m. Default is dry-run (just prints).",
    )
    parser.add_argument(
        "--print-commands",
        action="store_true",
        help="Print equivalent update-org-mapping.py CLI invocations and exit (no file write).",
    )
    args = parser.parse_args()

    if not os.path.exists(args.mapping):
        print(f"❌ Mapping file not found: {args.mapping}")
        return 1

    print(f"📂 Loading mapping: {args.mapping}")
    df_mapping = pd.read_csv(args.mapping, dtype=str, keep_default_na=False)

    candidates = find_candidates(df_mapping)
    if args.ballot_csv:
        candidates = filter_to_used_in_ballots(candidates, args.ballot_csv)

    n = len(candidates)
    print(f"\n🔍 Candidate rows (Status='No Match' AND Canonical is a real mapping): {n}")
    if n == 0:
        print("✅ Nothing to do.")
        return 0

    show_cols = [c for c in ["Jira_Organization", "Canonical_Organization", "Match_Score", "SF_Account_ID", "Status"] if c in candidates.columns]
    with pd.option_context("display.max_rows", None, "display.max_colwidth", 80):
        print(candidates[show_cols].to_string(index=False))

    if args.print_commands:
        print("\n# Equivalent update-org-mapping.py commands:")
        for _, row in candidates.iterrows():
            jira = shlex.quote(str(row["Jira_Organization"]))
            cmd = (
                f"python3 scripts/ballot-participation/update-org-mapping.py "
                f"--mapping {shlex.quote(args.mapping)} "
                f"--jira-org {jira} "
                f"--status {shlex.quote(args.new_status)}"
            )
            if args.set_score is not None:
                cmd += f" --score {int(args.set_score) if float(args.set_score).is_integer() else args.set_score}"
            print(cmd)
        return 0

    if not args.apply:
        print(
            f"\nℹ️  Dry run. Re-run with --apply to flip Status to {args.new_status!r}"
            + (f" and Match_Score to {args.set_score}" if args.set_score is not None else "")
            + "."
        )
        return 0

    candidate_idx = candidates.index
    df_mapping.loc[candidate_idx, "Status"] = args.new_status
    if args.set_score is not None:
        df_mapping.loc[candidate_idx, "Match_Score"] = args.set_score

    backup = args.mapping + ".bak-cleanup"
    print(f"\n💾 Writing backup: {backup}")
    pd.read_csv(args.mapping, dtype=str, keep_default_na=False).to_csv(
        backup, index=False, quoting=csv.QUOTE_MINIMAL, doublequote=True
    )

    print(f"💾 Writing updated mapping: {args.mapping}")
    df_mapping_sorted = df_mapping.sort_values("Jira_Organization", kind="stable")
    df_mapping_sorted.to_csv(args.mapping, index=False, quoting=csv.QUOTE_MINIMAL, doublequote=True)

    print(f"\n✅ Updated {n} row(s) (Status → {args.new_status!r})."
          + (f" Match_Score → {args.set_score}" if args.set_score is not None else ""))
    print("Re-run scripts/ballot-participation/apply-org-mapping.py to see conflict count drop.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
