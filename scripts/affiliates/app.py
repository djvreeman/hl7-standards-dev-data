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
    if request.method == 'POST':
        affiliate_id = request.form['affiliate_id']
        affiliate_name = request.form['affiliate_name']
        country = request.form['country']
        year_active = request.form['year_active']
        df = pd.read_csv(affiliate_registry_file)

        if affiliate_id in df['Affiliate_ID'].values:
            flash("Affiliate ID already exists!", "error")
            return redirect(url_for('add_affiliate'))

        new_row = pd.DataFrame([{
            'Affiliate_ID': affiliate_id,
            'Affiliate_Name': affiliate_name,
            'Country': country,
            'Year_Active': year_active
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(affiliate_registry_file, index=False)
        flash("Affiliate added successfully!", "success")
        return redirect(url_for('index'))
    return render_template('add_affiliate.html')

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
    affiliates = pd.read_csv(affiliate_registry_file)['Affiliate_ID'].tolist()

    if request.method == 'POST':
        affiliate_id = request.form['affiliate_id']
        year = request.form['year']
        org_member_count = request.form['org_member_count']
        ind_member_count = request.form['ind_member_count']

        if affiliate_id not in affiliates:
            flash("Affiliate ID does not exist!", "error")
            return redirect(url_for('add_membership'))

        df = pd.read_csv(membership_data_file)
        new_row = pd.DataFrame([{
            'Affiliate_ID': affiliate_id,
            'Year': year,
            'Org_Member_Count': int(org_member_count),
            'Ind_Member_Count': int(ind_member_count)
        }])
        df = pd.concat([df, new_row], ignore_index=True)
        df.to_csv(membership_data_file, index=False)
        flash("Membership data added successfully!", "success")
        return redirect(url_for('index'))
    return render_template('add_membership.html', affiliates=affiliates)

# Route to edit membership data
@app.route('/edit_membership/<affiliate_id>/<year>', methods=['GET', 'POST'])
def edit_membership(affiliate_id, year):
    print(f"Accessed edit_membership with Affiliate ID: {affiliate_id} and Year: {year}")  # Debugging statement

    # Read the CSV file and ensure both affiliate_id and year are treated as strings
    df = pd.read_csv(membership_data_file, dtype={'Affiliate_ID': str, 'Year': str})
    print(f"Current DataFrame:\n{df}")  # Debugging statement to print the entire DataFrame

    # Filter DataFrame to find the specified membership record
    record = df[(df['Affiliate_ID'] == str(affiliate_id)) & (df['Year'] == str(year))]
    print(f"Filtered DataFrame for affiliate_id {affiliate_id} and year {year}:\n{record}")  # Debugging statement

    # Check if the membership record exists
    if record.empty:
        print("Membership record not found!")  # Debugging statement
        flash("Membership record not found!", "error")
        return redirect(url_for('view_membership'))

    record = record.iloc[0].to_dict()
    print(f"Membership data for editing: {record}")  # Debugging statement

    if request.method == 'POST':
        # Update the DataFrame with the new values
        df.loc[(df['Affiliate_ID'] == str(affiliate_id)) & (df['Year'] == str(year)), 'Org_Member_Count'] = request.form['org_member_count']
        df.loc[(df['Affiliate_ID'] == str(affiliate_id)) & (df['Year'] == str(year)), 'Ind_Member_Count'] = request.form['ind_member_count']
        df.to_csv(membership_data_file, index=False)
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
    membership = pd.read_csv(membership_data_file)
    print(f"Viewing Membership Data: {membership.to_dict(orient='records')}")  # Debugging statement
    return render_template('view_membership.html', membership=membership.to_dict(orient='records'))

if __name__ == '__main__':
    app.run(debug=True, port=5001)