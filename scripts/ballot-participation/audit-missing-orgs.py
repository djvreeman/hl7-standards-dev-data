#!/usr/bin/env python3
"""
Audit Missing-Org Rows in Ballot Participation Data

Surfaces every BALLOT row whose Organization (or Organization_Canonical) is
missing, alongside the rest of that balloter's chronological ballot history,
so the data can be efficiently curated into ``balloter-overrides.csv``.

The output CSV's first 8 columns mirror ``ballot_participation-*-normalized.csv``
(and ``balloter-overrides.csv``), so curated rows can be copy/pasted directly
into the overrides file.

USAGE:
    python3 audit-missing-orgs.py \\
        --ballot-csv data/working/ballot-participation/ballot_participation-YYYYMMDD-HHMMSS-normalized.csv \\
        --baldef-csv data/working/ballot-participation/baldef_data-YYYYMMDD-HHMMSS.csv \\
        -o data/working/ballot-participation/missing-orgs-audit-YYYYMMDD-HHMMSS.csv

OPTIONS:
    --balloter KEY        Restrict to a single Balloter Key
    --include-curated PATH Path to balloter-overrides.csv. Marks rows whose
                          BALLOT ID is already present there with Already_Overridden=Y.
    --missing-only        Emit only rows where Missing_Org=Y (default: emit
                          full chronological history of each affected balloter).
"""

import argparse
import csv
import os
import sys

import pandas as pd


PARTICIPATION_FIRST_COLS = [
    "BALDEF ID",
    "BALLOT ID",
    "Balloter Key",
    "Balloter Name",
    "Organization",
    "Org Category",
    "Vote",
    "Organization_Canonical",
]

BALDEF_JOIN_COLS = ["Ballot Period", "Ballot Close Date", "Specification", "Product Family"]

OUTPUT_COLUMNS = (
    PARTICIPATION_FIRST_COLS
    + BALDEF_JOIN_COLS
    + ["Missing_Org", "Already_Overridden", "Suggested_Org", "Source", "Notes"]
)


def _is_blank(value) -> bool:
    if value is None:
        return True
    if isinstance(value, float) and pd.isna(value):
        return True
    s = str(value).strip()
    return s == "" or s.lower() == "nan" or s == "0"


def is_missing_org(row: pd.Series) -> bool:
    org = row.get("Organization", "")
    canon = row.get("Organization_Canonical", "")
    return _is_blank(org) or _is_blank(canon)


def compute_suggested_org(history: pd.DataFrame) -> str:
    """
    If the balloter has exactly one distinct non-missing canonical org across
    their history, return it. Otherwise return ''.
    """
    if "Organization_Canonical" not in history.columns:
        return ""
    canon = history["Organization_Canonical"].astype(str).str.strip()
    canon = canon[~canon.apply(_is_blank)]
    distinct = canon.unique()
    if len(distinct) == 1:
        return distinct[0]
    return ""


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Audit missing-org rows alongside each balloter's ballot history"
    )
    parser.add_argument("--ballot-csv", required=True, help="ballot_participation-*-normalized.csv")
    parser.add_argument("--baldef-csv", required=True, help="baldef_data-*.csv")
    parser.add_argument("-o", "--output", required=True, help="Path to output audit CSV")
    parser.add_argument("--balloter", default=None, help="Restrict to one Balloter Key")
    parser.add_argument(
        "--include-curated",
        default=None,
        help="Path to balloter-overrides.csv (flags rows already overridden)",
    )
    parser.add_argument(
        "--missing-only",
        action="store_true",
        help="Emit only Missing_Org=Y rows (default: full history of affected balloters)",
    )
    args = parser.parse_args()

    print(f"📂 Loading participation data from {args.ballot_csv}...")
    try:
        df = pd.read_csv(
            args.ballot_csv,
            dtype=str,
            keep_default_na=False,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True,
        )
        df.columns = df.columns.str.strip()
        print(f"✅ Loaded {len(df)} participation records")
    except Exception as e:
        print(f"❌ Error loading participation CSV: {e}")
        return 1

    if "Organization_Canonical" not in df.columns:
        df["Organization_Canonical"] = ""

    print(f"\n📂 Loading BALDEF data from {args.baldef_csv}...")
    try:
        df_baldef = pd.read_csv(
            args.baldef_csv,
            dtype=str,
            keep_default_na=False,
            quoting=csv.QUOTE_MINIMAL,
            doublequote=True,
        )
        df_baldef.columns = df_baldef.columns.str.strip()
        print(f"✅ Loaded {len(df_baldef)} BALDEF records")
    except Exception as e:
        print(f"❌ Error loading BALDEF CSV: {e}")
        return 1

    keep_baldef = ["BALDEF ID"] + [c for c in BALDEF_JOIN_COLS if c in df_baldef.columns]
    df_baldef_small = df_baldef[keep_baldef].drop_duplicates(subset=["BALDEF ID"])

    curated_ballot_ids: set[str] = set()
    if args.include_curated:
        if not os.path.exists(args.include_curated):
            print(f"⚠️  --include-curated path not found: {args.include_curated}")
        else:
            try:
                df_curated = pd.read_csv(
                    args.include_curated,
                    dtype=str,
                    keep_default_na=False,
                    quoting=csv.QUOTE_MINIMAL,
                    doublequote=True,
                )
                df_curated.columns = df_curated.columns.str.strip()
                if "BALLOT ID" in df_curated.columns:
                    curated_ballot_ids = set(df_curated["BALLOT ID"].astype(str).str.strip())
                    print(f"✅ Loaded {len(curated_ballot_ids)} curated BALLOT ID(s)")
                else:
                    print(f"⚠️  Curated file missing 'BALLOT ID' column")
            except Exception as e:
                print(f"⚠️  Could not read curated overrides file: {e}")

    print("\n🔍 Detecting missing-org rows...")
    missing_mask = df.apply(is_missing_org, axis=1)
    n_missing = int(missing_mask.sum())
    print(f"  Missing-org rows: {n_missing}")

    if args.balloter:
        affected_keys = {args.balloter}
        print(f"  Restricting to balloter: {args.balloter}")
    else:
        affected_keys = set(df.loc[missing_mask, "Balloter Key"].astype(str).str.strip())
        print(f"  Affected balloters: {len(affected_keys)}")

    if not affected_keys:
        print("ℹ️  Nothing to audit. Writing empty audit file.")
        pd.DataFrame(columns=OUTPUT_COLUMNS).to_csv(args.output, index=False, quoting=csv.QUOTE_MINIMAL)
        return 0

    df_focus = df[df["Balloter Key"].astype(str).str.strip().isin(affected_keys)].copy()

    df_focus = df_focus.merge(df_baldef_small, on="BALDEF ID", how="left")

    for col in BALDEF_JOIN_COLS:
        if col not in df_focus.columns:
            df_focus[col] = ""

    df_focus["Missing_Org"] = df_focus.apply(lambda r: "Y" if is_missing_org(r) else "N", axis=1)

    if curated_ballot_ids:
        df_focus["Already_Overridden"] = df_focus["BALLOT ID"].astype(str).str.strip().apply(
            lambda b: "Y" if b in curated_ballot_ids else "N"
        )
    else:
        df_focus["Already_Overridden"] = "N"

    suggested_by_key: dict[str, str] = {}
    for key, group in df_focus.groupby("Balloter Key"):
        suggested_by_key[str(key).strip()] = compute_suggested_org(group)
    df_focus["Suggested_Org"] = df_focus["Balloter Key"].astype(str).str.strip().map(suggested_by_key).fillna("")

    df_focus["Source"] = ""
    df_focus["Notes"] = ""

    if args.missing_only:
        df_focus = df_focus[df_focus["Missing_Org"] == "Y"]

    sort_close = pd.to_datetime(df_focus["Ballot Close Date"], errors="coerce", utc=True)
    df_focus = df_focus.assign(_sort_close=sort_close)
    df_focus = df_focus.sort_values(
        by=["Balloter Key", "_sort_close", "BALLOT ID"], kind="stable", na_position="last"
    ).drop(columns=["_sort_close"])

    for col in OUTPUT_COLUMNS:
        if col not in df_focus.columns:
            df_focus[col] = ""
    df_out = df_focus[OUTPUT_COLUMNS]

    print(f"\n💾 Writing audit CSV to {args.output}...")
    try:
        df_out.to_csv(args.output, index=False, quoting=csv.QUOTE_MINIMAL, doublequote=True)
    except Exception as e:
        print(f"❌ Error writing audit CSV: {e}")
        return 1

    print(f"✅ Wrote {len(df_out)} row(s)")
    print("\n📊 Summary:")
    print(f"  Affected balloters:                  {len(affected_keys)}")
    print(f"  Total missing-org rows:              {n_missing}")
    if curated_ballot_ids:
        already = int((df_out["Already_Overridden"] == "Y").sum())
        print(f"  Rows already overridden in curated:  {already}")
    suggested_count = sum(1 for v in suggested_by_key.values() if v)
    print(f"  Balloters with single-org suggestion: {suggested_count} / {len(affected_keys)}")
    print("\n✅ Done!")
    return 0


if __name__ == "__main__":
    sys.exit(main())
