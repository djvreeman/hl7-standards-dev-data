from flask import Flask, render_template, request, redirect, url_for, flash
import pandas as pd
import os

app = Flask(__name__)
app.secret_key = 'supersecretkey'

# Set up paths to CSV files
script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(script_dir, "data")
os.makedirs(data_dir, exist_ok=True)

affiliate_registry_file = os.path.join(data_dir, 'affiliate_registry.csv')
membership_data_file = os.path.join(data_dir, 'membership_data.csv')

# Initialize CSV files if they don't exist
def initialize_files():
    if not os.path.exists(affiliate_registry_file):
        pd.DataFrame(columns=['Affiliate_ID', 'Affiliate_Name', 'Country', 'Year_Active']).to_csv(affiliate_registry_file, index=False)
    if not os.path.exists(membership_data_file):
        pd.DataFrame(columns=['Affiliate_ID', 'Year', 'Org_Member_Count', 'Ind_Member_Count']).to_csv(membership_data_file, index=False)

initialize_files()

# Home route
@app.route('/')
def index():
    # Load membership data and calculate totals by year
    df = pd.read_csv(membership_data_file)
    
    # Calculate yearly totals for organizational and individual members
    yearly_totals = df.groupby('Year').agg({
        'Org_Member_Count': 'sum',
        'Ind_Member_Count': 'sum',
        'Affiliate_ID': 'nunique'  # Count unique affiliates per year
    }).rename(columns={'Affiliate_ID': 'Affiliate_Count'}).reset_index()
    
    # Convert yearly totals to a dictionary for easier handling in the template
    yearly_totals = yearly_totals.to_dict(orient='records')
    return render_template('index.html', yearly_totals=yearly_totals)

# Route to add an affiliate
@app.route('/add_affiliate', methods=['GET', 'POST'])
def add_affiliate():
    # Load affiliate data
    affiliates_df = pd.read_csv(affiliate_registry_file)
    affiliates = affiliates_df.to_dict(orient='records')

    if request.method == 'POST':
        # Retrieve form data
        affiliate_id = request.form.get('affiliate_id')
        affiliate_name = request.form.get('affiliate_name')
        country = request.form.get('country')
        year_active = request.form.get('year_active')

        # Save the affiliate data
        new_row = pd.DataFrame([{
            'Affiliate_ID': affiliate_id,
            'Affiliate_Name': affiliate_name,
            'Country': country,
            'Year_Active': year_active
        }])
        
        # Append and save to CSV
        affiliates_df = pd.concat([affiliates_df, new_row], ignore_index=True)
        affiliates_df.to_csv(affiliate_registry_file, index=False)
        
        flash("Affiliate added successfully!", "success")
        return redirect(url_for('index'))
    
    return render_template('add_affiliate.html', affiliates=affiliates)

# Route to edit an affiliate
@app.route('/edit_affiliate/<affiliate_id>', methods=['GET', 'POST'])
def edit_affiliate(affiliate_id):
    print(f"Accessed edit_affiliate with ID: {affiliate_id}")  # Debugging statement

    # Read the CSV file and ensure affiliate_id is treated as a string
    df = pd.read_csv(affiliate_registry_file, dtype={'Affiliate_ID': str})
    print(f"Current DataFrame:\n{df}")  # Debugging statement to print the entire DataFrame

    # Filter DataFrame to find the specified affiliate
    affiliate = df[df['Affiliate_ID'] == str(affiliate_id)]
    print(f"Filtered DataFrame for affiliate_id {affiliate_id}:\n{affiliate}")  # Debugging statement
    
    # Check if the affiliate exists
    if affiliate.empty:
        print("Affiliate ID not found!")  # Debugging statement
        flash("Affiliate ID not found!", "error")
        return redirect(url_for('view_affiliates'))

    affiliate = affiliate.iloc[0].to_dict()
    print(f"Affiliate data for editing: {affiliate}")  # Debugging statement
    
    if request.method == 'POST':
        # Update the DataFrame with the new values
        df.loc[df['Affiliate_ID'] == str(affiliate_id), 'Affiliate_Name'] = request.form['affiliate_name']
        df.loc[df['Affiliate_ID'] == str(affiliate_id), 'Country'] = request.form['country']
        df.loc[df['Affiliate_ID'] == str(affiliate_id), 'Year_Active'] = request.form['year_active']
        df.to_csv(affiliate_registry_file, index=False)
        flash("Affiliate updated successfully!", "success")
        return redirect(url_for('view_affiliates'))
    
    return render_template('edit_affiliate.html', affiliate=affiliate)

# Route to add membership data
@app.route('/add_membership', methods=['GET', 'POST'])
def add_membership():
    # Load affiliate data
    affiliates_df = pd.read_csv(affiliate_registry_file)
    affiliates = affiliates_df.to_dict(orient='records')

    if request.method == 'POST':
        # Retrieve form data
        affiliate_id = request.form.get('affiliate_id')
        year = request.form.get('year')
        org_member_count = int(request.form.get('org_member_count'))
        ind_member_count = int(request.form.get('ind_member_count'))
        
        # Calculate total member count
        total_member_count = org_member_count + ind_member_count
        print(f"Total Member Count calculated: {total_member_count}")  # Debugging

        # Save the membership data with total count
        df = pd.read_csv(membership_data_file)
        new_row = pd.DataFrame([{
            'Affiliate_ID': affiliate_id,
            'Year': year,
            'Org_Member_Count': org_member_count,
            'Ind_Member_Count': ind_member_count,
            'Total_Member_Count': total_member_count  # Save total count
        }])
        
        # Concatenate the new row and save back to CSV
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(membership_data_file, index=False)
        
        flash("Membership data added successfully!", "success")
        return redirect(url_for('index'))

    return render_template('add_membership.html', affiliates=affiliates)

# Route to edit membership data
@app.route('/edit_membership/<affiliate_id>/<year>', methods=['GET', 'POST'])
def edit_membership(affiliate_id, year):
    # Load data and ensure columns are treated as strings
    affiliates_df = pd.read_csv(affiliate_registry_file, dtype={'Affiliate_ID': str})
    membership_df = pd.read_csv(membership_data_file, dtype={'Affiliate_ID': str, 'Year': str})

    # Merge to include affiliate names
    merged_df = membership_df.merge(affiliates_df[['Affiliate_ID', 'Affiliate_Name']], on='Affiliate_ID', how='left')
    
    # Find the specific record for editing
    record = merged_df[(merged_df['Affiliate_ID'] == affiliate_id) & (merged_df['Year'] == year)]
    
    if record.empty:
        flash("Membership record not found!", "error")
        return redirect(url_for('view_membership'))

    # Extract the record and calculate Total Member Count for initial display
    record = record.iloc[0].to_dict()
    record['Total_Member_Count'] = record['Org_Member_Count'] + record['Ind_Member_Count']

    if request.method == 'POST':
        # Retrieve updated counts from the form
        org_member_count = int(request.form.get('org_member_count'))
        ind_member_count = int(request.form.get('ind_member_count'))
        total_member_count = org_member_count + ind_member_count

        # Update values in the original membership DataFrame
        membership_df.loc[(membership_df['Affiliate_ID'] == affiliate_id) & (membership_df['Year'] == year), 'Org_Member_Count'] = org_member_count
        membership_df.loc[(membership_df['Affiliate_ID'] == affiliate_id) & (membership_df['Year'] == year), 'Ind_Member_Count'] = ind_member_count
        membership_df.loc[(membership_df['Affiliate_ID'] == affiliate_id) & (membership_df['Year'] == year), 'Total_Member_Count'] = total_member_count
        membership_df.to_csv(membership_data_file, index=False)
        
        flash("Membership data updated successfully!", "success")
        return redirect(url_for('view_membership'))
    
    return render_template('edit_membership.html', record=record)

# Route to view affiliates
@app.route('/view_affiliates')
def view_affiliates():
    affiliates = pd.read_csv(affiliate_registry_file)
    print(f"Viewing Affiliates: {affiliates.to_dict(orient='records')}")  # Debugging statement
    return render_template('view_affiliates.html', affiliates=affiliates.to_dict(orient='records'))

# Route to view membership data
@app.route('/view_membership')
def view_membership():
    # Load and merge data
    affiliates_df = pd.read_csv(affiliate_registry_file)
    membership_df = pd.read_csv(membership_data_file)
    
    # Merge to include affiliate names and calculate Total_Member_Count
    membership_df['Total_Member_Count'] = membership_df['Org_Member_Count'] + membership_df['Ind_Member_Count']
    merged_df = membership_df.merge(affiliates_df[['Affiliate_ID', 'Affiliate_Name']], on='Affiliate_ID', how='left')

    # Convert merged DataFrame to a list of dictionaries
    membership = merged_df.to_dict(orient='records')
    
    return render_template('view_membership.html', membership=membership)
if __name__ == '__main__':
    app.run(debug=True, port=5001)