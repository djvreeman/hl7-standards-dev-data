#!/usr/bin/env python3
import argparse
import os
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns

def overall_analysis(df):
    total = len(df)
    resolved_count = df['Resolved'].sum()
    backlog_count = total - resolved_count
    overall_stats = {
        "Total Issues": total,
        "Resolved Issues": resolved_count,
        "Backlog Issues": backlog_count
    }
    if 'Days to Resolution' in df.columns and not df[df['Resolved']].empty:
        overall_stats["Days to Resolution Stats"] = df[df['Resolved']]['Days to Resolution'].describe().to_string()
    return overall_stats

def group_analysis(df, group_col):
    group_counts = df.groupby(group_col).size()
    resolved_stats = None
    if 'Days to Resolution' in df.columns:
        # Only consider resolved issues for resolution metrics
        resolved_group = df[df['Resolved']].groupby(group_col)['Days to Resolution']
        if not resolved_group.empty:
            resolved_stats = resolved_group.describe()
    return group_counts, resolved_stats

def generate_visualization_counts(df, group_col, output_dir):
    # Generate a bar chart for issue counts by group
    group_counts = df[group_col].value_counts()
    plt.figure(figsize=(10, 6))
    sns.barplot(x=group_counts.index, y=group_counts.values)
    plt.xticks(rotation=45, ha='right')
    plt.title(f"Issue Counts by {group_col}")
    plt.xlabel(group_col)
    plt.ylabel("Issue Count")
    output_path = os.path.join(output_dir, f"{group_col}_counts.png")
    plt.tight_layout()
    plt.savefig(output_path)
    plt.close()
    print(f"Visualization saved: {output_path}")

def generate_visualization_boxplot(df, group_col, output_dir):
    # Generate a boxplot for Days to Resolution (resolved issues) by group
    if 'Days to Resolution' in df.columns:
        resolved = df[df['Resolved']]
        if not resolved.empty:
            plt.figure(figsize=(10, 6))
            sns.boxplot(x=group_col, y='Days to Resolution', data=resolved)
            plt.xticks(rotation=45, ha='right')
            plt.title(f"Days to Resolution by {group_col}")
            output_path = os.path.join(output_dir, f"{group_col}_resolution_boxplot.png")
            plt.tight_layout()
            plt.savefig(output_path)
            plt.close()
            print(f"Boxplot saved: {output_path}")
    else:
        print("No 'Days to Resolution' column found for boxplot.")

def analyze_issues(input_file, output_dir):
    # Read the CSV file with tab delimiter
    df = pd.read_csv(input_file, sep='\t')
    print(f"Loaded data from: {input_file}")

    # Strip any extra whitespace from column headers
    df.columns = df.columns.str.strip()

    # Convert date fields to datetime objects if they exist
    if 'Created Date' in df.columns:
        df['Created Date'] = pd.to_datetime(df['Created Date'], errors='coerce')
    else:
        print("Warning: 'Created Date' column not found. Skipping conversion.")
    
    if 'Resolution Date' in df.columns:
        df['Resolution Date'] = pd.to_datetime(df['Resolution Date'], errors='coerce')
        df['Resolved'] = df['Resolution Date'].notna()
    else:
        print("Warning: 'Resolution Date' column not found. Assuming no issues are resolved.")
        df['Resolved'] = False

    # Create the output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)

    # --- Overall Analysis ---
    overall_stats = overall_analysis(df)
    overall_report_path = os.path.join(output_dir, "overall_analysis_report.txt")
    with open(overall_report_path, "w") as report:
        report.write("=== Overall Analysis Report ===\n")
        for key, value in overall_stats.items():
            report.write(f"{key}: {value}\n")
        report.write("\n")
        # Analysis by each grouping field
        group_fields = ['Product Family', 'Realm', 'Specification']
        for field in group_fields:
            if field in df.columns:
                report.write(f"=== Analysis by {field} ===\n")
                group_counts, resolved_stats = group_analysis(df, field)
                report.write("Issue Counts:\n")
                report.write(group_counts.to_string())
                report.write("\n\n")
                if resolved_stats is not None:
                    report.write("Days to Resolution statistics for resolved issues:\n")
                    report.write(resolved_stats.to_string())
                    report.write("\n\n")
            else:
                report.write(f"Column '{field}' not found in data.\n\n")
    print(f"Overall analysis report generated at: {overall_report_path}")

    # --- Generate Visualizations ---
    for field in ['Product Family', 'Realm', 'Specification']:
        if field in df.columns:
            generate_visualization_counts(df, field, output_dir)
            generate_visualization_boxplot(df, field, output_dir)
        else:
            print(f"Column '{field}' not found for visualization.")

def main():
    parser = argparse.ArgumentParser(
        description='Analyze issue resolution trends overall and by Product Family, Realm, and Specification.'
    )
    parser.add_argument('-i', '--input', required=True,
                        help='Path to the tab-separated CSV input file.')
    parser.add_argument('-o', '--output', default=".",
                        help='Output directory to save reports and visualizations.')
    args = parser.parse_args()
    analyze_issues(args.input, args.output)

if __name__ == "__main__":
    main()