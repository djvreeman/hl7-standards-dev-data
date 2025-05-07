#!/usr/bin/env python3
import argparse
import pandas as pd
import numpy as np

def get_tri_section(month_num):
    if month_num in [1, 2, 3, 4]:
        return "T1"
    elif month_num in [5, 6, 7, 8]:
        return "T2"
    elif month_num in [9, 10, 11, 12]:
        return "T3"
    else:
        return "Unknown"

def process_data(df):
    df['Created Date'] = pd.to_datetime(df['Created Date'], errors='coerce')
    df['Resolution Date'] = pd.to_datetime(df['Resolution Date'], errors='coerce')
    df['creation_month'] = df['Created Date'].dt.month
    df['creation_tri'] = df['creation_month'].apply(lambda m: get_tri_section(m) if pd.notnull(m) else "Unknown")
    df['resolution_month'] = df['Resolution Date'].dt.month
    df['resolution_tri'] = df['resolution_month'].apply(lambda m: get_tri_section(m) if pd.notnull(m) else "Unknown")
    df['is_resolved'] = df['Resolution Date'].notnull()
    df['days_to_resolution'] = (df['Resolution Date'] - df['Created Date']).dt.total_seconds() / 86400.0
    return df

def compute_time_period_metrics(df_subset, period):
    # Only count issues created in this period (not those resolved in this period)
    new_mask = df_subset['creation_tri'] == period
    new_issues = df_subset[new_mask].shape[0]
    
    resolved_mask = df_subset['is_resolved'] & (df_subset['resolution_tri'] == period)
    resolved = df_subset[resolved_mask].shape[0]
    
    backlog_mask = (~df_subset['is_resolved']) & (df_subset['creation_tri'] == period)
    backlog = df_subset[backlog_mask].shape[0]
    
    times = df_subset.loc[resolved_mask, 'days_to_resolution']
    if not times.empty:
        ave = times.mean()
        med = times.median()
        p90 = times.quantile(0.9)
    else:
        ave = med = p90 = None
    
    return new_issues, resolved, backlog, ave, med, p90

def generate_summary_markdown(df):
    md = []
    md.append("# Issue Resolution Summary Report\n")
    # Table of Contents
    md.append("## Table of Contents\n")
    md.extend([
        "- [Overall Summary](#overall-summary)",
        "- [Summary by Time Period](#summary-by-time-period)",
        "- [Breakdown by Realm and Time Period](#breakdown-by-realm-and-time-period)",
        "- [Breakdown by WG Name and Realm](#breakdown-by-wg-name-and-realm-total-issues--percent-within-wg)",
        "- [Breakdown by WG Name and Time Period](#breakdown-by-wg-name-and-time-period)",
        "- [Breakdown by Specification and Time Period](#breakdown-by-specification-and-time-period)",
        "- [Breakdown by Product Family and Time Period](#breakdown-by-product-family-and-time-period)",
        "- [Notes](#notes)",
        "  - [P90 Performance Bands (based on 2024 data)](#p90-performance-bands-based-on-2024-data)",
        ""
    ])

    # Overall summary
    total = len(df)
    resolved = df['is_resolved'].sum()
    backlog = total - resolved
    times_all = df.loc[df['is_resolved'], 'days_to_resolution']
    ave_all = times_all.mean() if not times_all.empty else None
    med_all = times_all.median() if not times_all.empty else None
    p90_all = times_all.quantile(0.9) if not times_all.empty else None

    md.append("## Overall Summary\n")
    md.append(f"- **Total Issues:** {total}")
    md.append(f"- **Resolved Issues:** {resolved}")
    md.append(f"- **Backlog (Unresolved):** {backlog}")
    md.append(f"- **Ave Resolution Time (days):** {ave_all:.2f}" if ave_all is not None else "- **Ave Resolution Time (days):** N/A")
    md.append(f"- **Median Resolution Time (days):** {med_all:.2f}" if med_all is not None else "- **Median Resolution Time (days):** N/A")
    md.append(f"- **P90 Resolution Time (days):** {p90_all:.2f}" if p90_all is not None else "- **P90 Resolution Time (days):** N/A")
    md.append("")

    # Summary by Time Period
    md.append("## Summary by Time Period\n")
    md.append("| Time Period | New | Resolved | Backlog | Ave (days) | Median (days) | P90 (days) |")
    md.append("|-------------|-----|----------|---------|------------|---------------|------------|")
    for period in ['T1','T2','T3']:
        n, r, b, ave, med, p90 = compute_time_period_metrics(df, period)
        ave_str = f"{ave:.2f}" if ave is not None else "N/A"
        med_str = f"{med:.2f}" if med is not None else "N/A"
        p90_str = f"{p90:.2f}" if p90 is not None else "N/A"
        md.append(f"| {period} | {n} | {r} | {b} | {ave_str} | {med_str} | {p90_str} |")
    md.append("")

    def render_breakdown(title, groups, key_cols):
        md.append(f"## {title}\n")
        header = key_cols + ["Time Period","New","Resolved","Backlog","Ave (days)","Median (days)","P90 (days)"]
        md.append("| " + " | ".join(header) + " |")
        md.append("|" + "|".join("-"*len(h) for h in header) + "|")
        for grp in groups:
            df_grp = df.copy()
            for col, val in grp.items():
                df_grp = df_grp[df_grp[col] == val]
            for period in ['T1','T2','T3']:
                n, r, b, ave, med, p90 = compute_time_period_metrics(df_grp, period)
                ave_str = f"{ave:.2f}" if ave is not None else "N/A"
                med_str = f"{med:.2f}" if med is not None else "N/A"
                p90_str = f"{p90:.2f}" if p90 is not None else "N/A"
                row = [str(grp.get(col, '')) for col in key_cols] + [period, str(n), str(r), str(b), ave_str, med_str, p90_str]
                md.append("| " + " | ".join(row) + " |")
        md.append("")

    realms = [{"Realm": r} for r in sorted(df['Realm'].unique())]
    render_breakdown("Breakdown by Realm and Time Period", realms, ["Realm"])

    wgs = [{"WG Name": w} for w in sorted(df['WG Name'].unique())]
    render_breakdown("Breakdown by WG Name and Time Period", wgs, ["WG Name"])

    # Breakdown by WG Name and Realm (% within WG Name)
    md.append("## Breakdown by WG Name and Realm (Total Issues + % within WG)\n")
    grouped = df.groupby(['WG Name', 'Realm']).size().reset_index(name='Total Issues')

    # Calculate total issues per WG
    wg_totals = grouped.groupby('WG Name')['Total Issues'].transform('sum')
    grouped['% within WG'] = (grouped['Total Issues'] / wg_totals * 100).round(1)
    grouped = grouped.sort_values(by=['WG Name', 'Total Issues'], ascending=[True, False])

    md.append("| WG Name | Realm | Total Issues | % within WG |")
    md.append("|---------|--------|---------------|--------------|")
    for _, row in grouped.iterrows():
        wg = row['WG Name'] if pd.notnull(row['WG Name']) else "Unknown"
        realm = row['Realm'] if pd.notnull(row['Realm']) else "Unknown"
        total = int(row['Total Issues'])
        pct = f"{row['% within WG']:.1f}"
        md.append(f"| {wg} | {realm} | {total} | {pct}% |")
    md.append("")

    specs = df[['WG Name','Specification Display Name']].drop_duplicates().sort_values(
        by=['WG Name','Specification Display Name']
    ).to_dict(orient='records')
    render_breakdown("Breakdown by Specification and Time Period", specs,
                     ["WG Name","Specification Display Name"])

    pfs = [{"Product Family": p} for p in sorted(df['Product Family'].unique())]
    render_breakdown("Breakdown by Product Family and Time Period", pfs, ["Product Family"])

    # Notes
    md.append("## Notes\n")
    md.append("- **Time Periods** are defined as:")
    md.append("  - **T1:** January, February, March, April")
    md.append("  - **T2:** May, June, July, August")
    md.append("  - **T3:** September, October, November, December\n")
    md.append("- **P90 (90th percentile)** indicates the number of days within which 90% of resolved issues were closed.\n")
    md.append("### P90 Performance Bands (based on 2024 data)\n")
    md.append("| Band                  | P90 Range (days) | Interpretation                                                                             |")
    md.append("|-----------------------|------------------|--------------------------------------------------------------------------------------------|")
    md.append("| **Excellent**         | ≤ 60             | 90% of tickets close within two months—very tight SLA.                                      |")
    md.append("| **Good**              | 61 – 180         | 90% close within six months—reasonable for complex standard‑development.                    |")
    md.append("| **Moderate**          | 181 – 365        | 90% close within a year—acceptable but opportunities exist to accelerate processes.         |")
    md.append("| **Needs Improvement** | > 365            | 10% of tickets take longer than a year—indicative of serious bottlenecks or resource gaps.  |\n")
    md.append("**Rationale:**")
    md.append("- Median (~35 days) shows half of tickets resolve in about a month.")
    md.append("- Average (~163 days) sits in the \"Good\" band (61–180 days).")
    md.append("- P90 (~446 days) exceeds one year, so anything > 365 days is flagged as \"Needs Improvement.\"\n")

    return "\n".join(md)

def main():
    parser = argparse.ArgumentParser(
        description="Analyze issue resolutions and generate a markdown summary report with TOC, median, and P90."
    )
    parser.add_argument("-i","--input", required=True, help="Input CSV file path")
    parser.add_argument("-o","--output", required=True, help="Output Markdown file path")
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    df.columns = df.columns.str.strip()
    if 'WG Name' not in df.columns and 'WG' in df.columns:
        df.rename(columns={'WG':'WG Name'}, inplace=True)
    if 'Specification Display Name' not in df.columns and 'Specification' in df.columns:
        df.rename(columns={'Specification':'Specification Display Name'}, inplace=True)

    df = process_data(df)
    report = generate_summary_markdown(df)

    with open(args.output,"w") as f:
        f.write(report)
    print(f"Report written to {args.output}")

if __name__=="__main__":
    main()