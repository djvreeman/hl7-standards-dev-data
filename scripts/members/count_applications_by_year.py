import pandas as pd

# Path to the Excel file
file_path = 'data/working/members/2025 07 18 - FHIR Trademark Applications Record.xlsx'

# Community License Applications
community_df = pd.read_excel(file_path, sheet_name='Community License Applications')
community_df['Year'] = pd.to_datetime(community_df['Date'], errors='coerce').dt.year
community_counts = community_df['Year'].value_counts().sort_index()

print('Community License Applications by Year:')
print(community_counts)

# Product License Applications
product_df = pd.read_excel(file_path, sheet_name='Product License Applications')

# Use the correct column name with leading space
submitted_col = ' submitted'

def parse_submitted(val):
    try:
        # Try as datetime string first
        dt = pd.to_datetime(val, errors='coerce')
        if pd.notnull(dt):
            return dt
        # Try as Unix timestamp (seconds)
        return pd.to_datetime(int(val), unit='s', errors='coerce')
    except Exception:
        return pd.NaT

product_df['Year'] = product_df[submitted_col].apply(parse_submitted).dt.year
product_counts = product_df['Year'].value_counts().sort_index()

print('\nProduct License Applications by Year:')
print(product_counts)

# Export to CSV
community_export = pd.DataFrame({
    'Type': 'Community',
    'Year': community_counts.index,
    'Count': community_counts.values
})
product_export = pd.DataFrame({
    'Type': 'Product',
    'Year': product_counts.index,
    'Count': product_counts.values
})

export_df = pd.concat([community_export, product_export], ignore_index=True)
export_df.to_csv('scripts/members/application_counts_by_year.csv', index=False)
print("\nResults exported to 'scripts/members/application_counts_by_year.csv'") 