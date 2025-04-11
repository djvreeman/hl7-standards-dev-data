#!/usr/bin/env python3
import argparse
import os
import pandas as pd
import numpy as np
from datetime import datetime
import matplotlib.pyplot as plt
import seaborn as sns

# Global utility function for timestamp formatting
def format_iso_timestamp(timestamp):
    """Format ISO timestamps for proper parsing."""
    if not timestamp or not isinstance(timestamp, str):
        return None
        
    # Handle +0000 format (convert to +00:00 for fromisoformat)
    if "+0000" in timestamp:
        timestamp = timestamp.replace("+0000", "+00:00")
    
    # Handle Z format
    if timestamp.endswith("Z"):
        timestamp = timestamp.replace("Z", "+00:00")
        
    return timestamp

def analyze_backlog_age(df, reference_date=None):
    """
    Analyze the age of unresolved issues in a backlog.
    
    Args:
        df (pd.DataFrame): DataFrame containing issue data
        reference_date (str, optional): Date to calculate age against. 
                                       If None, uses the latest resolution date.
    
    Returns:
        dict: Dictionary of backlog metrics
    """
    # Identify unresolved issues (those without a Resolution Date)
    unresolved_df = df[df['Resolution Date'].isna()].copy()
    
    if len(unresolved_df) == 0:
        return {
            "backlog_count": 0,
            "message": "No unresolved issues found in the dataset."
        }
    
    # Determine reference date for age calculation
    if reference_date is None:
        # Use the latest date in the dataset as reference
        all_dates = []
        for date_col in ['Created Date', 'Resolution Date']:
            valid_dates = df[date_col].dropna()
            parsed_dates = [datetime.fromisoformat(format_iso_timestamp(d)) for d in valid_dates if isinstance(d, str)]
            all_dates.extend(parsed_dates)
        
        if all_dates:
            reference_date = max(all_dates)
        else:
            # If no valid dates, use current date
            reference_date = datetime.now()
    elif isinstance(reference_date, str):
        reference_date = datetime.fromisoformat(format_iso_timestamp(reference_date))
    
    # Calculate age for each unresolved issue
    def calculate_age(created_date_str):
        try:
            created_date_str = format_iso_timestamp(created_date_str)
            if not created_date_str:
                return None
            created_date = datetime.fromisoformat(created_date_str)
            age_days = (reference_date - created_date).total_seconds() / (24 * 60 * 60)
            return float(f"{age_days:.3g}")
        except (ValueError, TypeError):
            return None
    
    unresolved_df['Age (days)'] = unresolved_df['Created Date'].apply(calculate_age)
    
    # Calculate age distribution metrics
    age_metrics = {
        "backlog_count": len(unresolved_df),
        "mean_age": unresolved_df['Age (days)'].mean(),
        "median_age": unresolved_df['Age (days)'].median(),
        "p90_age": unresolved_df['Age (days)'].quantile(0.9),
        "max_age": unresolved_df['Age (days)'].max(),
        "age_distribution": {
            "0-7_days": len(unresolved_df[unresolved_df['Age (days)'] <= 7]),
            "8-30_days": len(unresolved_df[(unresolved_df['Age (days)'] > 7) & (unresolved_df['Age (days)'] <= 30)]),
            "31-90_days": len(unresolved_df[(unresolved_df['Age (days)'] > 30) & (unresolved_df['Age (days)'] <= 90)]),
            "91-180_days": len(unresolved_df[(unresolved_df['Age (days)'] > 90) & (unresolved_df['Age (days)'] <= 180)]),
            "181-365_days": len(unresolved_df[(unresolved_df['Age (days)'] > 180) & (unresolved_df['Age (days)'] <= 365)]),
            "over_365_days": len(unresolved_df[unresolved_df['Age (days)'] > 365])
        }
    }
    
    # Calculate staleness index
    # This is a custom metric that weights tickets based on their age
    # The formula gives more weight to older tickets
    def calculate_staleness_score(age):
        if pd.isna(age):
            return 0
        elif age <= 7:
            return 0.1 * age  # 0.1 points per day for first week
        elif age <= 30:
            return 0.7 + 0.2 * (age - 7)  # 0.2 points per day for remainder of first month
        elif age <= 90:
            return 5.3 + 0.5 * (age - 30)  # 0.5 points per day for months 2-3
        elif age <= 180:
            return 35.3 + 1.0 * (age - 90)  # 1.0 points per day for months 4-6
        else:
            return 125.3 + 2.0 * (age - 180)  # 2.0 points per day beyond 6 months
    
    unresolved_df['Staleness Score'] = unresolved_df['Age (days)'].apply(calculate_staleness_score)
    
    # Calculate overall staleness index (average staleness score)
    age_metrics["staleness_index"] = unresolved_df['Staleness Score'].mean()
    
    # Classify based on staleness index
    if age_metrics["staleness_index"] < 10:
        age_metrics["staleness_category"] = "Healthy"
    elif age_metrics["staleness_index"] < 50:
        age_metrics["staleness_category"] = "Moderate"
    elif age_metrics["staleness_index"] < 100:
        age_metrics["staleness_category"] = "Stale"
    else:
        age_metrics["staleness_category"] = "Critical"
    
    # Calculate product family breakdown
    product_backlog = unresolved_df.groupby('Product Family').agg({
        'Issue': 'count',
        'Age (days)': ['mean', 'median', lambda x: x.quantile(0.9)],
        'Staleness Score': 'mean'
    })
    
    # Rename columns for clarity
    product_backlog.columns = ['Count', 'Mean Age', 'Median Age', 'P90 Age', 'Staleness Index']
    
    # Sort by count descending
    product_backlog = product_backlog.sort_values('Count', ascending=False)
    
    age_metrics["product_family_backlog"] = product_backlog.reset_index().to_dict('records')
    
    return age_metrics

def plot_backlog_age_distribution(df, output_file, reference_date=None):
    """
    Create a visualization of the backlog age distribution
    
    Args:
        df (pd.DataFrame): DataFrame containing issue data
        output_file (str): Path to save the visualization
        reference_date (str, optional): Date to calculate age against
    """
    # Identify unresolved issues
    unresolved_df = df[df['Resolution Date'].isna()].copy()
    
    if len(unresolved_df) == 0:
        # Create empty plot with message
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, "No unresolved issues found in the dataset.", 
                horizontalalignment='center', verticalalignment='center',
                transform=plt.gca().transAxes, fontsize=14)
        plt.savefig(output_file)
        plt.close()
        return
    
    # Determine reference date for age calculation
    if reference_date is None:
        # Use latest date in dataset
        all_dates = []
        for date_col in ['Created Date', 'Resolution Date']:
            valid_dates = df[date_col].dropna()
            parsed_dates = [datetime.fromisoformat(format_iso_timestamp(d)) for d in valid_dates if isinstance(d, str)]
            all_dates.extend(parsed_dates)
        
        if all_dates:
            reference_date = max(all_dates)
        else:
            reference_date = datetime.now()
    elif isinstance(reference_date, str):
        reference_date = datetime.fromisoformat(format_iso_timestamp(reference_date))
    
    # Calculate age for each unresolved issue
    def calculate_age(created_date_str):
        try:
            created_date_str = format_iso_timestamp(created_date_str)
            if not created_date_str:
                return None
            created_date = datetime.fromisoformat(created_date_str)
            age_days = (reference_date - created_date).total_seconds() / (24 * 60 * 60)
            return float(f"{age_days:.3g}")
        except (ValueError, TypeError):
            return None
    
    unresolved_df['Age (days)'] = unresolved_df['Created Date'].apply(calculate_age)
    
    # Create age buckets for visualization
    def age_category(age):
        if pd.isna(age):
            return "Unknown"
        elif age <= 7:
            return "0-7 days"
        elif age <= 30:
            return "8-30 days"
        elif age <= 90:
            return "31-90 days"
        elif age <= 180:
            return "91-180 days"
        elif age <= 365:
            return "181-365 days"
        else:
            return "Over 365 days"
    
    unresolved_df['Age Category'] = unresolved_df['Age (days)'].apply(age_category)
    
    # Create ordered category to ensure proper order in plots
    age_order = ["0-7 days", "8-30 days", "31-90 days", "91-180 days", "181-365 days", "Over 365 days", "Unknown"]
    unresolved_df['Age Category'] = pd.Categorical(unresolved_df['Age Category'], categories=age_order, ordered=True)
    
    # Create subplot grid
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))
    
    # Plot 1: Age distribution histogram
    sns.histplot(data=unresolved_df, x='Age (days)', bins=30, kde=True, ax=ax1)
    ax1.set_title('Backlog Age Distribution (Days)')
    ax1.set_xlabel('Age (days)')
    ax1.set_ylabel('Number of Issues')
    
    # Add vertical lines for key percentiles
    median_age = unresolved_df['Age (days)'].median()
    p90_age = unresolved_df['Age (days)'].quantile(0.9)
    
    ax1.axvline(median_age, color='red', linestyle='--', label=f'Median: {median_age:.1f} days')
    ax1.axvline(p90_age, color='orange', linestyle='--', label=f'P90: {p90_age:.1f} days')
    ax1.legend()
    
    # Plot 2: Age category counts
    age_counts = unresolved_df['Age Category'].value_counts().sort_index()
    colors = ['green', 'yellowgreen', 'yellow', 'orange', 'orangered', 'red', 'gray']
    
    # Create bar plot with custom colors - updated for seaborn v0.13+
    bars = sns.barplot(x=age_counts.index, y=age_counts.values, hue=age_counts.index, 
                     palette=colors, legend=False, ax=ax2)
    ax2.set_title('Backlog Age Categories')
    ax2.set_xlabel('Age Category')
    ax2.set_ylabel('Number of Issues')
    # Fix the tick labels
    plt.setp(ax2.get_xticklabels(), rotation=45, ha='right')
    
    # Add count labels
    for i, p in enumerate(bars.patches):
        ax2.annotate(f'{int(p.get_height())}', 
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha = 'center', va = 'bottom',
                    xytext = (0, 5), textcoords = 'offset points')
    
    # Add figure title and adjust layout
    plt.suptitle(f'Backlog Age Analysis (Total Unresolved Issues: {len(unresolved_df)})', fontsize=16)
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    
    # Save figure
    plt.savefig(output_file)
    plt.close()

def generate_backlog_report(backlog_metrics, output_file):
    """
    Generate a readable report of backlog age metrics
    
    Args:
        backlog_metrics (dict): Dictionary of backlog metrics from analyze_backlog_age
        output_file (str): Path to save the report
    """
    with open(output_file, 'w') as f:
        f.write("===== BACKLOG AGE ANALYSIS REPORT =====\n\n")
        
        if backlog_metrics.get("backlog_count", 0) == 0:
            f.write(backlog_metrics.get("message", "No unresolved issues to analyze."))
            return
        
        # Overall backlog statistics
        f.write("===== OVERALL BACKLOG STATISTICS =====\n")
        f.write(f"Total unresolved issues: {backlog_metrics['backlog_count']}\n")
        f.write(f"Mean age: {backlog_metrics['mean_age']:.1f} days\n")
        f.write(f"Median age: {backlog_metrics['median_age']:.1f} days\n")
        f.write(f"P90 age: {backlog_metrics['p90_age']:.1f} days\n")
        f.write(f"Maximum age: {backlog_metrics['max_age']:.1f} days\n")
        f.write(f"Staleness Index: {backlog_metrics['staleness_index']:.1f} (Category: {backlog_metrics['staleness_category']})\n\n")
        
        # Age distribution
        f.write("===== AGE DISTRIBUTION =====\n")
        for age_range, count in backlog_metrics['age_distribution'].items():
            percentage = (count / backlog_metrics['backlog_count']) * 100
            f.write(f"{age_range}: {count} issues ({percentage:.1f}%)\n")
        f.write("\n")
        
        # Product Family breakdown
        f.write("===== PRODUCT FAMILY BREAKDOWN =====\n")
        f.write("Top 10 product families by backlog count:\n\n")
        
        # Header
        f.write(f"{'Product Family':<20} {'Count':<8} {'Mean Age':<10} {'Median Age':<12} {'P90 Age':<10} {'Staleness':<10}\n")
        f.write(f"{'-'*20} {'-'*8} {'-'*10} {'-'*12} {'-'*10} {'-'*10}\n")
        
        # Data rows (top 10)
        for product in backlog_metrics['product_family_backlog'][:10]:
            f.write(f"{product['Product Family'][:20]:<20} {product['Count']:<8} "
                   f"{product['Mean Age']:.1f}{' '*5} {product['Median Age']:.1f}{' '*7} "
                   f"{product['P90 Age']:.1f}{' '*5} {product['Staleness Index']:.1f}\n")
        
        # Risk assessment
        f.write("\n===== RISK ASSESSMENT =====\n")
        
        # P90 age assessment
        if backlog_metrics['p90_age'] > 180:
            f.write("⚠️ HIGH RISK: 10% of backlog issues are older than 6 months\n")
        elif backlog_metrics['p90_age'] > 90:
            f.write("⚠️ MEDIUM RISK: 10% of backlog issues are older than 3 months\n")
        
        # Age distribution assessment
        old_issues_count = backlog_metrics['age_distribution']['over_365_days']
        if old_issues_count > 0:
            old_issues_pct = (old_issues_count / backlog_metrics['backlog_count']) * 100
            f.write(f"⚠️ {old_issues_count} issues ({old_issues_pct:.1f}%) have been open for more than a year\n")
        
        # Staleness assessment
        if backlog_metrics['staleness_category'] in ['Stale', 'Critical']:
            f.write(f"⚠️ Backlog Staleness Index ({backlog_metrics['staleness_index']:.1f}) indicates significant aging issues\n")

def preprocess_data(df):
    """
    Preprocess the dataframe to ensure all required columns are present.
    
    Args:
        df (pd.DataFrame): DataFrame to preprocess
        
    Returns:
        pd.DataFrame: Preprocessed DataFrame
    """
    # Check if the DataFrame already has the necessary columns
    required_columns = ['Product Family', 'Creation Month']
    missing_columns = [col for col in required_columns if col not in df.columns]
    
    # If columns are missing, add them
    if missing_columns:
        print(f"Adding missing columns: {missing_columns}")
        
        # Extract the Product Family from the Issue field if needed
        if 'Product Family' not in df.columns and 'Issue' in df.columns:
            df['Product Family'] = df['Issue'].str.split('-').str[0]
        
        # Extract month-year from dates for trend analysis if needed
        if 'Creation Month' not in df.columns and 'Created Date' in df.columns:
            def extract_month_year(date_str):
                try:
                    date_str = format_iso_timestamp(date_str)
                    if not date_str:
                        return None
                    date_obj = datetime.fromisoformat(date_str)
                    return f"{date_obj.year}-{date_obj.month:02d}"
                except (ValueError, TypeError):
                    return None
            
            df['Creation Month'] = df['Created Date'].apply(extract_month_year)
            
    return df

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Analyze backlog age metrics and generate reports.')
    parser.add_argument('-i', '--input', required=True, help='Input CSV file path')
    parser.add_argument('-o', '--output-dir', default='./reports', help='Directory to save reports and visualizations')
    parser.add_argument('-r', '--reference-date', help='Reference date for backlog age calculation (ISO format)')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Read the CSV file
    df = pd.read_csv(args.input)
    
    # Preprocess the data
    df = preprocess_data(df)
    
    # Analyze backlog age
    backlog_metrics = analyze_backlog_age(df, args.reference_date)
    backlog_report_file = os.path.join(args.output_dir, "backlog_report.txt")
    generate_backlog_report(backlog_metrics, backlog_report_file)
    
    # Generate backlog age distribution plot
    backlog_plot_file = os.path.join(args.output_dir, "backlog_age_distribution.png")
    plot_backlog_age_distribution(df, backlog_plot_file, args.reference_date)
    
    print(f"Backlog report generated at: {backlog_report_file}")
    print(f"Visualization saved to: {backlog_plot_file}")

if __name__ == '__main__':
    main()
    