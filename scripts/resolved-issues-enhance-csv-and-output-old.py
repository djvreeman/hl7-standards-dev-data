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

def enhance_csv(input_file):
    """
    Enhance a CSV file by adding metrics that help track issue resolution health.
    
    Args:
        input_file (str): Path to the input CSV file
    
    Returns:
        str: Path to the enhanced output file
        pd.DataFrame: The enhanced dataframe for further analysis
    """
    # Get the directory and filename without extension
    directory = os.path.dirname(input_file)
    filename = os.path.basename(input_file)
    base_name, extension = os.path.splitext(filename)
    
    # Create the output file path
    output_file = os.path.join(directory, f"{base_name}-enhanced{extension}")
    
    # Read the CSV file
    df = pd.read_csv(input_file)
    
    # Extract the Product Family from the Issue field
    df['Product Family'] = df['Issue'].str.split('-').str[0]
    
    # Calculate Days to Resolution (in days)
    def calculate_time_to_resolution(row):
        try:
            # Get and format the timestamps
            created_date_str = format_iso_timestamp(row['Created Date'])
            resolution_date_str = format_iso_timestamp(row['Resolution Date'])
            
            if not created_date_str or not resolution_date_str:
                return None
                
            # Parse the ISO 8601 formatted timestamps into datetime objects
            created_date = datetime.fromisoformat(created_date_str)
            resolution_date = datetime.fromisoformat(resolution_date_str)
            
            # Calculate the difference in days (can include fractional days)
            delta = resolution_date - created_date
            
            # Convert to days (including fractional part)
            days = delta.total_seconds() / (24 * 60 * 60)
            # Round to 3 significant digits
            return float(f"{days:.3g}")
        except (ValueError, TypeError, AttributeError) as e:
            # Print error for debugging (can be removed in production)
            print(f"Error processing dates: {row['Created Date']} - {row['Resolution Date']}: {e}")
            # Return NaN if there's an issue with the date format or missing dates
            return None
    
    # Apply the function to calculate Days to Resolution
    df['Days to Resolution'] = df.apply(calculate_time_to_resolution, axis=1)
    
    # Calculate additional fields for analysis
    # Extract month-year from dates for trend analysis
    def extract_month_year(date_str):
        try:
            date_str = format_iso_timestamp(date_str)
            if not date_str:
                return None
            date_obj = datetime.fromisoformat(date_str)
            return f"{date_obj.year}-{date_obj.month:02d}"
        except:
            return None
    
    df['Creation Month'] = df['Created Date'].apply(extract_month_year)
    df['Resolution Month'] = df['Resolution Date'].apply(extract_month_year)
    
    # Save the enhanced data to a new CSV file
    df.to_csv(output_file, index=False)
    
    return output_file, df

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

def calculate_resolution_metrics(df):
    """
    Calculate resolution metrics overall and by product family.
    
    Args:
        df (pd.DataFrame): DataFrame containing issue data
    
    Returns:
        dict: Dictionary of resolution metrics
    """
    # Get only resolved issues (those with Days to Resolution)
    resolved_df = df.dropna(subset=['Days to Resolution']).copy()
    
    if len(resolved_df) == 0:
        return {
            "resolved_count": 0,
            "message": "No resolved issues found in the dataset."
        }
    
    # Overall resolution metrics
    overall_metrics = {
        "resolved_count": len(resolved_df),
        "mean_days": resolved_df['Days to Resolution'].mean(),
        "median_days": resolved_df['Days to Resolution'].median(),
        "p90_days": resolved_df['Days to Resolution'].quantile(0.9),
        "min_days": resolved_df['Days to Resolution'].min(),
        "max_days": resolved_df['Days to Resolution'].max()
    }
    
    # Resolution metrics by product family
    product_resolution = resolved_df.groupby('Product Family').agg({
        'Issue': 'count',
        'Days to Resolution': ['mean', 'median', 'min', 'max', lambda x: x.quantile(0.9)]
    })
    
    # Rename columns for clarity
    product_resolution.columns = ['Count', 'Mean Days', 'Median Days', 'Min Days', 'Max Days', 'P90 Days']
    
    # Sort by count descending
    product_resolution = product_resolution.sort_values('Count', ascending=False)
    
    # Add to overall metrics
    overall_metrics["product_family_resolution"] = product_resolution.reset_index().to_dict('records')
    
    return overall_metrics

def generate_resolution_report(resolution_metrics, output_file):
    """
    Generate a readable report of resolution metrics
    
    Args:
        resolution_metrics (dict): Dictionary of resolution metrics from calculate_resolution_metrics
        output_file (str): Path to save the report
    """
    with open(output_file, 'w') as f:
        f.write("===== ISSUE RESOLUTION METRICS REPORT =====\n\n")
        
        if resolution_metrics.get("resolved_count", 0) == 0:
            f.write(resolution_metrics.get("message", "No resolved issues to analyze."))
            return
        
        # Overall statistics
        f.write("===== OVERALL RESOLUTION STATISTICS =====\n")
        f.write(f"Total resolved issues: {resolution_metrics['resolved_count']}\n")
        f.write(f"Mean days to resolution: {resolution_metrics['mean_days']:.2f} days\n")
        f.write(f"Median days to resolution: {resolution_metrics['median_days']:.2f} days\n")
        f.write(f"P90 days to resolution: {resolution_metrics['p90_days']:.2f} days\n")
        f.write(f"Fastest resolution: {resolution_metrics['min_days']:.2f} days\n")
        f.write(f"Slowest resolution: {resolution_metrics['max_days']:.2f} days\n\n")
        
        # Product Family breakdown
        f.write("===== PRODUCT FAMILY RESOLUTION TIMES =====\n")
        f.write("Top 10 product families by issue count:\n\n")
        
        # Header
        f.write(f"{'Product Family':<20} {'Count':<8} {'Mean':<10} {'Median':<10} {'Min':<10} {'Max':<10} {'P90':<10}\n")
        f.write(f"{'-'*20} {'-'*8} {'-'*10} {'-'*10} {'-'*10} {'-'*10} {'-'*10}\n")
        
        # Data rows (top 10)
        for product in resolution_metrics['product_family_resolution'][:10]:
            f.write(f"{product['Product Family'][:20]:<20} {product['Count']:<8} "
                   f"{product['Mean Days']:.2f}{' '*5} {product['Median Days']:.2f}{' '*5} "
                   f"{product['Min Days']:.2f}{' '*5} {product['Max Days']:.2f}{' '*5} "
                   f"{product['P90 Days']:.2f}\n")
        
        # Analysis
        f.write("\n===== PERFORMANCE ANALYSIS =====\n")
        
        # Find product families with significantly faster or slower resolution times
        products = resolution_metrics['product_family_resolution']
        overall_mean = resolution_metrics['mean_days']
        
        # Only consider product families with at least 10 issues
        significant_products = [p for p in products if p['Count'] >= 10]
        
        if significant_products:
            fast_products = [p for p in significant_products if p['Mean Days'] < 0.7 * overall_mean]
            slow_products = [p for p in significant_products if p['Mean Days'] > 1.3 * overall_mean]
            
            if fast_products:
                f.write("Product families with significantly faster resolution times:\n")
                for p in fast_products:
                    f.write(f"- {p['Product Family']}: {p['Mean Days']:.2f} days ({p['Count']} issues) - " 
                          f"{(1 - p['Mean Days']/overall_mean):.1%} faster than average\n")
                f.write("\n")
            
            if slow_products:
                f.write("Product families with significantly slower resolution times:\n")
                for p in slow_products:
                    f.write(f"- {p['Product Family']}: {p['Mean Days']:.2f} days ({p['Count']} issues) - "
                          f"{(p['Mean Days']/overall_mean - 1):.1%} slower than average\n")
                f.write("\n")

def plot_resolution_distribution(df, output_file):
    """
    Create a visualization of the resolution time distribution
    
    Args:
        df (pd.DataFrame): DataFrame containing issue data
        output_file (str): Path to save the visualization
    """
    # Get only resolved issues
    resolved_df = df.dropna(subset=['Days to Resolution']).copy()
    
    if len(resolved_df) == 0:
        # Create empty plot with message
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, "No resolved issues found in the dataset.", 
                horizontalalignment='center', verticalalignment='center',
                transform=plt.gca().transAxes, fontsize=14)
        plt.savefig(output_file)
        plt.close()
        return
    
    # Create resolution time categories
    def resolution_category(days):
        if pd.isna(days):
            return "Unknown"
        elif days <= 1:
            return "Same day"
        elif days <= 7:
            return "1-7 days"
        elif days <= 30:
            return "8-30 days"
        elif days <= 90:
            return "31-90 days"
        elif days <= 180:
            return "91-180 days"
        else:
            return "Over 180 days"
    
    resolved_df['Resolution Category'] = resolved_df['Days to Resolution'].apply(resolution_category)
    
    # Create ordered category
    resolution_order = ["Same day", "1-7 days", "8-30 days", "31-90 days", "91-180 days", "Over 180 days", "Unknown"]
    resolved_df['Resolution Category'] = pd.Categorical(resolved_df['Resolution Category'], 
                                                      categories=resolution_order, ordered=True)
    
    # Set up plot
    plt.figure(figsize=(15, 7))
    
    # Create subplot grid
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(15, 7))
    
    # Plot 1: Resolution time histogram
    sns.histplot(data=resolved_df, x='Days to Resolution', bins=30, kde=True, ax=ax1)
    ax1.set_title('Resolution Time Distribution (Days)')
    ax1.set_xlabel('Days to Resolution')
    ax1.set_ylabel('Number of Issues')
    
    # Add vertical lines for key percentiles
    median_days = resolved_df['Days to Resolution'].median()
    p90_days = resolved_df['Days to Resolution'].quantile(0.9)
    
    ax1.axvline(median_days, color='green', linestyle='--', label=f'Median: {median_days:.2f} days')
    ax1.axvline(p90_days, color='red', linestyle='--', label=f'P90: {p90_days:.2f} days')
    ax1.legend()
    
    # Plot 2: Resolution category counts
    cat_counts = resolved_df['Resolution Category'].value_counts().sort_index()
    colors = ['green', 'yellowgreen', 'yellow', 'orange', 'orangered', 'red', 'gray']
    
    # Create bar plot with custom colors
    bars = sns.barplot(x=cat_counts.index, y=cat_counts.values, palette=colors, ax=ax2)
    ax2.set_title('Resolution Time Categories')
    ax2.set_xlabel('Resolution Category')
    ax2.set_ylabel('Number of Issues')
    ax2.set_xticklabels(ax2.get_xticklabels(), rotation=45, ha='right')
    
    # Add count labels
    for i, p in enumerate(bars.patches):
        ax2.annotate(f'{int(p.get_height())}', 
                    (p.get_x() + p.get_width() / 2., p.get_height()),
                    ha = 'center', va = 'bottom',
                    xytext = (0, 5), textcoords = 'offset points')
    
    # Add figure title and adjust layout
    plt.suptitle(f'Resolution Time Analysis (Total Resolved Issues: {len(resolved_df)})', fontsize=16)
    plt.tight_layout()
    plt.subplots_adjust(top=0.9)
    
    # Save figure
    plt.savefig(output_file)
    plt.close()

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
    
    # Set up plot
    plt.figure(figsize=(12, 8))
    
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
    
    # Create bar plot with custom colors
    bars = sns.barplot(x=age_counts.index, y=age_counts.values, palette=colors, ax=ax2)
    ax2.set_title('Backlog Age Categories')
    ax2.set_xlabel('Age Category')
    ax2.set_ylabel('Number of Issues')
    ax2.set_xticklabels(ax2.get_xticklabels(), rotation=45, ha='right')
    
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

def main():
    # Set up argument parser
    parser = argparse.ArgumentParser(description='Enhance CSV file and generate issue health metrics.')
    parser.add_argument('-i', '--input', required=True, help='Input CSV file path')
    parser.add_argument('-o', '--output-dir', default='./reports', help='Directory to save reports and visualizations')
    
    # Parse arguments
    args = parser.parse_args()
    
    # Enhance the CSV file
    output_file, enhanced_df = enhance_csv(args.input)
    
    print(f"Enhanced CSV saved to: {output_file}")
    
    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)
    
    # Calculate resolution metrics
    resolution_metrics = calculate_resolution_metrics(enhanced_df)
    resolution_report_file = os.path.join(args.output_dir, "resolution_report.txt")
    generate_resolution_report(resolution_metrics, resolution_report_file)
    
    # Generate resolution time distribution plot
    resolution_plot_file = os.path.join(args.output_dir, "resolution_distribution.png")
    plot_resolution_distribution(enhanced_df, resolution_plot_file)
    
    # Analyze backlog age
    backlog_metrics = analyze_backlog_age(enhanced_df)
    backlog_report_file = os.path.join(args.output_dir, "backlog_report.txt")
    generate_backlog_report(backlog_metrics, backlog_report_file)
    
    # Generate backlog age distribution plot
    backlog_plot_file = os.path.join(args.output_dir, "backlog_age_distribution.png")
    plot_backlog_age_distribution(enhanced_df, backlog_plot_file)
    
    print(f"Resolution report generated at: {resolution_report_file}")
    print(f"Backlog report generated at: {backlog_report_file}")
    print(f"Visualizations saved to: {args.output_dir}")

if __name__ == '__main__':
    main()