import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import os

# Set up paths to the CSV files in the "data" folder relative to this script's location
script_dir = os.path.dirname(os.path.abspath(__file__))
data_dir = os.path.join(script_dir, "data")
os.makedirs(data_dir, exist_ok=True)  # Create the "data" folder if it doesn't exist

affiliate_registry_file = os.path.join(data_dir, 'affiliate_registry.csv')
membership_data_file = os.path.join(data_dir, 'membership_data.csv')

# Initialize CSV files if they don't exist
def initialize_files():
    try:
        if not os.path.exists(affiliate_registry_file):
            print(f"Creating {affiliate_registry_file}")
            pd.DataFrame(columns=['Affiliate_ID', 'Affiliate_Name', 'Country', 'Year_Active']).to_csv(affiliate_registry_file, index=False)
        if not os.path.exists(membership_data_file):
            print(f"Creating {membership_data_file}")
            pd.DataFrame(columns=['Affiliate_ID', 'Year', 'Org_Member_Count', 'Ind_Member_Count']).to_csv(membership_data_file, index=False)
        print("Files initialized successfully.")
    except Exception as e:
        print(f"Error initializing files: {e}")

initialize_files()

# Function to add affiliate to the CSV
def add_affiliate():
    affiliate_id = affiliate_id_entry.get()
    affiliate_name = affiliate_name_entry.get()
    country = country_entry.get()
    year_active = year_active_entry.get()

    if not (affiliate_id and affiliate_name and country and year_active):
        messagebox.showwarning("Missing Data", "Please fill in all affiliate fields.")
        return

    try:
        # Append to CSV
        df = pd.read_csv(affiliate_registry_file)
        df = df.append({
            'Affiliate_ID': affiliate_id,
            'Affiliate_Name': affiliate_name,
            'Country': country,
            'Year_Active': year_active
        }, ignore_index=True)
        df.to_csv(affiliate_registry_file, index=False)
        messagebox.showinfo("Success", "Affiliate added successfully!")
        clear_affiliate_entries()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to add affiliate: {e}")

def clear_affiliate_entries():
    affiliate_id_entry.delete(0, tk.END)
    affiliate_name_entry.delete(0, tk.END)
    country_entry.delete(0, tk.END)
    year_active_entry.delete(0, tk.END)

# Function to add membership data to the CSV
def add_membership_data():
    affiliate_id = membership_affiliate_id_entry.get()
    year = membership_year_entry.get()
    org_member_count = org_member_count_entry.get()
    ind_member_count = ind_member_count_entry.get()

    if not (affiliate_id and year and org_member_count and ind_member_count):
        messagebox.showwarning("Missing Data", "Please fill in all membership fields.")
        return

    try:
        # Append to CSV
        df = pd.read_csv(membership_data_file)
        df = df.append({
            'Affiliate_ID': affiliate_id,
            'Year': year,
            'Org_Member_Count': int(org_member_count),
            'Ind_Member_Count': int(ind_member_count)
        }, ignore_index=True)
        df.to_csv(membership_data_file, index=False)
        messagebox.showinfo("Success", "Membership data added successfully!")
        clear_membership_entries()
    except Exception as e:
        messagebox.showerror("Error", f"Failed to add membership data: {e}")

def clear_membership_entries():
    membership_affiliate_id_entry.delete(0, tk.END)
    membership_year_entry.delete(0, tk.END)
    org_member_count_entry.delete(0, tk.END)
    ind_member_count_entry.delete(0, tk.END)

# Setup main window
root = tk.Tk()
root.title("Affiliate Membership Data Collection")
root.geometry("400x300")  # Set window size

# Create tabbed layout
tab_control = ttk.Notebook(root)
affiliate_tab = ttk.Frame(tab_control)
membership_tab = ttk.Frame(tab_control)
tab_control.add(affiliate_tab, text="Affiliate Registry")
tab_control.add(membership_tab, text="Membership Data")
tab_control.pack(expand=1, fill="both")

# Affiliate Registry Tab
ttk.Label(affiliate_tab, text="Affiliate ID:").grid(column=0, row=0, padx=10, pady=5, sticky="W")
affiliate_id_entry = ttk.Entry(affiliate_tab)
affiliate_id_entry.grid(column=1, row=0, padx=10, pady=5)

ttk.Label(affiliate_tab, text="Affiliate Name:").grid(column=0, row=1, padx=10, pady=5, sticky="W")
affiliate_name_entry = ttk.Entry(affiliate_tab)
affiliate_name_entry.grid(column=1, row=1, padx=10, pady=5)

ttk.Label(affiliate_tab, text="Country:").grid(column=0, row=2, padx=10, pady=5, sticky="W")
country_entry = ttk.Entry(affiliate_tab)
country_entry.grid(column=1, row=2, padx=10, pady=5)

ttk.Label(affiliate_tab, text="Year Active:").grid(column=0, row=3, padx=10, pady=5, sticky="W")
year_active_entry = ttk.Entry(affiliate_tab)
year_active_entry.grid(column=1, row=3, padx=10, pady=5)

add_affiliate_button = ttk.Button(affiliate_tab, text="Add Affiliate", command=add_affiliate)
add_affiliate_button.grid(column=0, row=4, columnspan=2, pady=10)

# Membership Data Tab
ttk.Label(membership_tab, text="Affiliate ID:").grid(column=0, row=0, padx=10, pady=5, sticky="W")
membership_affiliate_id_entry = ttk.Entry(membership_tab)
membership_affiliate_id_entry.grid(column=1, row=0, padx=10, pady=5)

ttk.Label(membership_tab, text="Year:").grid(column=0, row=1, padx=10, pady=5, sticky="W")
membership_year_entry = ttk.Entry(membership_tab)
membership_year_entry.grid(column=1, row=1, padx=10, pady=5)

ttk.Label(membership_tab, text="Org Member Count:").grid(column=0, row=2, padx=10, pady=5, sticky="W")
org_member_count_entry = ttk.Entry(membership_tab)
org_member_count_entry.grid(column=1, row=2, padx=10, pady=5)

ttk.Label(membership_tab, text="Ind Member Count:").grid(column=0, row=3, padx=10, pady=5, sticky="W")
ind_member_count_entry = ttk.Entry(membership_tab)
ind_member_count_entry.grid(column=1, row=3, padx=10, pady=5)

add_membership_data_button = ttk.Button(membership_tab, text="Add Membership Data", command=add_membership_data)
add_membership_data_button.grid(column=0, row=4, columnspan=2, pady=10)

# Force update for macOS
root.update_idletasks()
root.after(100, root.deiconify)
root.mainloop()