#!/usr/bin/env python3
"""
Apply Per-BALLOT-ID Balloter Overrides to Ballot Participation Data

This module exposes shared override-merge logic used by both this CLI and by
``apply-org-mapping.py`` (so the org-mapping step and the override step happen
in a single command). It can also be invoked directly to re-apply overrides to
an already-normalized CSV without re-running the org-mapping pass.

The overrides file is keyed by ``BALLOT ID`` (unique within the participation
CSV). For each override row, any non-empty cell replaces the corresponding cell
in the participation row; empty cells leave the participation row unchanged.

USAGE:
    # Re-apply overrides to an existing normalized CSV
    python3 apply-balloter-overrides.py \\
        -i ballot_participation-YYYYMMDD-HHMMSS-normalized.csv \\
        -v balloter-overrides.csv \\
        -o ballot_participation-YYYYMMDD-HHMMSS-curated.csv

    # Treat conflicts (override differs from non-empty existing value) as errors
    python3 apply-balloter-overrides.py -i ... -v ... -o ... --strict
"""

import argparse
import csv
import os
import re
import sys

import pandas as pd


OVERRIDE_COLUMNS = [
    "Balloter Name",
    "Organization",
    "Org Category",
    "Vote",
    "Organization_Canonical",
]

DEFAULT_OVERRIDES_FILENAME = "balloter-overrides.csv"


def normalize_ballot_id(raw) -> str:
    """
    Normalize BALLOT ID for matching participation rows.

    Spreadsheets often coerce ``BALLOT-18632`` to the number ``18632`` or float
    ``18632.0``, which would otherwise fail to match the participation CSV.
    """
    if raw is None:
        return ""
    if isinstance(raw, float) and pd.isna(raw):
        return ""
    s = str(raw).strip()
    if not s or s.lower() == "nan":
        return ""
    # Excel-style float rendered as string
    if re.fullmatch(r"\d+\.0", s):
        s = s[:-2]
    if s.isdigit():
        return f"BALLOT-{s}"
    return s


def _is_blank(value) -> bool:
    """Empty string / NaN / literal '0' are all treated as missing."""
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    s = str(value).strip()
    return s == "" or s.lower() == "nan" or s == "0"


def load_overrides(overrides_file: str) -> pd.DataFrame:
    """Load overrides CSV. Returns empty DataFrame (with expected columns) on miss."""
    if not os.path.exists(overrides_file):
        print(f"⚠️  Overrides file not found: {overrides_file}")
        return pd.DataFrame(
            columns=["BALDEF ID", "BALLOT ID", "Balloter Key"] + OVERRIDE_COLUMNS + ["Source", "Notes"]
        )

    df = pd.read_csv(
        overrides_file,
        dtype=str,
        keep_default_na=False,
        quoting=csv.QUOTE_MINIMAL,
        doublequote=True,
        encoding="utf-8-sig",
    )
    df.columns = df.columns.str.strip()

    if "BALLOT ID" not in df.columns:
        raise ValueError(f"Overrides file missing required column 'BALLOT ID': {overrides_file}")

    return df


def count_override_rows(df: pd.DataFrame) -> tuple[int, int]:
    """
    Return (total_rows, rows_with_a_normalizable_BALLOT_ID).

    Used for clearer console reporting (distinguish header-only files from
    populated overrides).
    """
    if df is None or df.empty:
        return 0, 0
    if "BALLOT ID" not in df.columns:
        return len(df), 0
    bids = df["BALLOT ID"].map(normalize_ballot_id)
    return len(df), int(bids.astype(bool).sum())


def apply_overrides(
    df_participation: pd.DataFrame,
    df_overrides: pd.DataFrame,
    strict: bool = False,
) -> tuple[pd.DataFrame, dict]:
    """
    Merge overrides into participation DataFrame, keyed by BALLOT ID.

    Returns:
        (merged_df, summary_dict). summary_dict has keys:
            'override_rows', 'rows_touched', 'fields_replaced' (per-column counts),
            'conflicts' (list of dicts), 'unknown_ballot_ids' (list of strings).

    Raises:
        ValueError when strict=True and at least one conflict is found.
    """
    # Reset index so positional indices from enumerate match df.iloc / df.at
    # (avoids KeyError when callers pass a slice whose index labels are not 0..n-1).
    df = df_participation.copy().reset_index(drop=True)
    if "BALLOT ID" not in df.columns:
        raise ValueError("Participation DataFrame missing required column 'BALLOT ID'")

    summary = {
        "override_rows": int(len(df_overrides)),
        "rows_touched": 0,
        "fields_replaced": {col: 0 for col in OVERRIDE_COLUMNS},
        "conflicts": [],
        "unknown_ballot_ids": [],
    }

    if df_overrides.empty:
        return df, summary

    for col in OVERRIDE_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df["__row_idx"] = range(len(df))
    ballot_index: dict[str, int] = {}
    for ballot_id_raw, idx in zip(df["BALLOT ID"], df["__row_idx"]):
        bid = normalize_ballot_id(ballot_id_raw)
        if bid:
            ballot_index.setdefault(bid, int(idx))
    df = df.drop(columns=["__row_idx"])

    rows_touched_idx: set[int] = set()

    for _, ov_row in df_overrides.iterrows():
        ballot_id = normalize_ballot_id(ov_row.get("BALLOT ID"))
        if not ballot_id:
            continue

        idx = ballot_index.get(ballot_id)
        if idx is None:
            summary["unknown_ballot_ids"].append(ballot_id)
            continue

        for col in OVERRIDE_COLUMNS:
            if col not in df_overrides.columns:
                continue
            new_val = ov_row.get(col, "")
            if _is_blank(new_val):
                continue

            existing_val = df.at[idx, col]
            new_val_str = str(new_val).strip()
            existing_str = "" if _is_blank(existing_val) else str(existing_val).strip()

            if existing_str and existing_str != new_val_str:
                summary["conflicts"].append(
                    {
                        "BALLOT ID": ballot_id,
                        "column": col,
                        "existing": existing_str,
                        "override": new_val_str,
                    }
                )

            df.at[idx, col] = new_val_str
            summary["fields_replaced"][col] += 1
            rows_touched_idx.add(idx)

    summary["rows_touched"] = len(rows_touched_idx)

    if strict and summary["conflicts"]:
        raise ValueError(
            f"--strict: {len(summary['conflicts'])} override conflict(s) found; aborting."
        )

    return df, summary


def print_summary(summary: dict, *, verbose: bool = True, skip_file_row_count: bool = False) -> None:
    """Pretty-print the summary returned by ``apply_overrides``."""
    if not skip_file_row_count:
        print(f"  Override rows read:        {summary['override_rows']}")
    print(f"  Participation rows touched: {summary['rows_touched']}")
    if summary["fields_replaced"]:
        for col, count in summary["fields_replaced"].items():
            if count:
                print(f"    - {col}: {count} replaced")
    if summary["unknown_ballot_ids"]:
        n = len(summary["unknown_ballot_ids"])
        print(f"  ⚠️  {n} override BALLOT ID(s) not found in participation data")
        if verbose:
            for bid in summary["unknown_ballot_ids"][:10]:
                print(f"       - {bid}")
            if n > 10:
                print(f"       ... and {n - 10} more")
    if summary["conflicts"]:
        n = len(summary["conflicts"])
        print(f"  ⚠️  {n} conflict(s) where override differs from existing non-empty value")
        if verbose:
            for c in summary["conflicts"][:10]:
                print(
                    f"       - {c['BALLOT ID']} {c['column']!r}: "
                    f"existing={c['existing']!r} override={c['override']!r}"
                )
            if n > 10:
                print(f"       ... and {n - 10} more")


def resolve_default_overrides_path(reference_path: str | None) -> str | None:
    """
    Resolve the default overrides path.

    Looks for ``balloter-overrides.csv`` in the same directory as ``reference_path``
    (typically the org-mapping CSV). Returns the path if it exists, else None.
    """
    if not reference_path:
        return None
    directory = os.path.dirname(os.path.abspath(reference_path)) or "."
    candidate = os.path.join(directory, DEFAULT_OVERRIDES_FILENAME)
    return candidate if os.path.exists(candidate) else None


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Apply per-BALLOT-ID balloter overrides to ballot participation data"
    )
    parser.add_argument("-i", "--input", required=True, help="Path to input ballot participation CSV")
    parser.add_argument("-v", "--overrides", required=True, help="Path to balloter-overrides CSV")
    parser.add_argument("-o", "--output", required=True, help="Path to output CSV")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Treat any conflict (override differs from existing non-empty value) as an error",
    )
    args = parser.parse_args()

    print(f"📂 Loading participation data from {args.input}...")
    try:
        df = pd.read_csv(args.input, dtype=str, keep_default_na=False, quoting=csv.QUOTE_MINIMAL, doublequote=True)
        df.columns = df.columns.str.strip()
        print(f"✅ Loaded {len(df)} records")
    except Exception as e:
        print(f"❌ Error loading participation CSV: {e}")
        return 1

    print(f"\n📋 Loading overrides from {args.overrides}...")
    try:
        df_overrides = load_overrides(args.overrides)
    except Exception as e:
        print(f"❌ Error loading overrides CSV: {e}")
        return 1
    total_rows, with_id = count_override_rows(df_overrides)
    print(f"✅ Loaded {total_rows} data row(s) from overrides ({with_id} with a BALLOT ID).")

    print(f"\n🔄 Applying balloter overrides...")
    try:
        df_merged, summary = apply_overrides(df, df_overrides, strict=args.strict)
    except ValueError as e:
        print(f"❌ {e}")
        return 2

    print_summary(summary)

    print(f"\n💾 Saving curated data to {args.output}...")
    try:
        df_merged.to_csv(args.output, index=False, quoting=csv.QUOTE_MINIMAL, doublequote=True)
        print("✅ Curated CSV saved")
    except Exception as e:
        print(f"❌ Error saving CSV: {e}")
        return 1

    print("\n✅ Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
