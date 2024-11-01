import streamlit as st
import pandas as pd
import json

# Initialize session state to store data
if "data" not in st.session_state:
    st.session_state["data"] = []

# Function to load data from an input CSV
def load_csv(file):
    try:
        df = pd.read_csv(file)
        # Convert authors field from JSON string to list of dicts
        df["authors"] = df["authors"].apply(json.loads)
        st.session_state["data"] = df.to_dict(orient="records")
        st.success("CSV loaded successfully!")
    except Exception as e:
        st.error(f"Failed to load CSV: {e}")

# Function to save data to CSV
def save_to_csv(filename):
    if not filename.endswith(".csv"):
        st.error("Filename must end with .csv")
        return
    df = pd.DataFrame(st.session_state["data"])
    # Convert authors list back to JSON string for saving
    df["authors"] = df["authors"].apply(json.dumps)
    try:
        df.to_csv(filename, index=False)
        st.success(f"Data saved successfully to {filename}")
    except Exception as e:
        st.error(f"Failed to save CSV: {e}")

# Function to add a new package row
def add_package_row(package_id, version, url, authors):
    new_row = {
        "package-id": package_id,
        "version": version,
        "url": url,
        "authors": authors
    }
    st.session_state["data"].append(new_row)

# Function to delete a row by index
def delete_row(index):
    st.session_state["data"].pop(index)
    st.success("Row deleted successfully!")

# Streamlit UI
st.title("Package Editor Information")

# Load CSV input
uploaded_file = st.file_uploader("Upload a CSV file", type=["csv"])
if uploaded_file:
    load_csv(uploaded_file)

# Display current data in a table
if st.session_state["data"]:
    st.write("Current Data:")
    df = pd.DataFrame(st.session_state["data"])
    st.dataframe(df)

    # Select a row to edit or delete
    row_index = st.number_input("Select Row Index to Edit/Delete", min_value=0, max_value=len(st.session_state["data"]) - 1, step=1)
    selected_row = st.session_state["data"][row_index]

    # Display selected row for editing
    st.write(f"Editing Row {row_index}:")
    package_id = st.text_input("Package ID", value=selected_row["package-id"])
    version = st.text_input("Version", value=selected_row["version"])
    url = st.text_input("Canonical URL", value=selected_row["url"])

    # Display and edit authors
    authors = selected_row["authors"]
    st.write("Authors:")
    for i, author in enumerate(authors):
        st.text_input(f"First Name ({i})", value=author["first_name"], key=f"first_name_{i}")
        st.text_input(f"Last Name ({i})", value=author["last_name"], key=f"last_name_{i}")
        st.text_input(f"Role ({i})", value=author["role"], key=f"role_{i}")
        st.text_input(f"Email ({i})", value=author["email"], key=f"email_{i}")

    # Button to delete the selected row
    if st.button("Delete Row"):
        delete_row(row_index)

    # Button to update the selected row
    if st.button("Update Row"):
        # Collect updated author information
        updated_authors = []
        for i, author in enumerate(authors):
            updated_author = {
                "first_name": st.session_state[f"first_name_{i}"],
                "last_name": st.session_state[f"last_name_{i}"],
                "role": st.session_state[f"role_{i}"],
                "email": st.session_state[f"email_{i}"]
            }
            updated_authors.append(updated_author)

        # Update the selected row with new values
        st.session_state["data"][row_index] = {
            "package-id": package_id,
            "version": version,
            "url": url,
            "authors": updated_authors
        }
        st.success("Row updated successfully!")

# Input fields for new package row
st.write("Add New Package Row:")
new_package_id = st.text_input("New Package ID", "")
new_version = st.text_input("New Version", "")
new_url = st.text_input("New Canonical URL", "")
new_authors_json = st.text_area("New Authors (JSON Format)", "[]")

# Button to add a new row
if st.button("Add New Row"):
    try:
        new_authors = json.loads(new_authors_json)
        add_package_row(new_package_id, new_version, new_url, new_authors)
        st.success("New row added successfully!")
    except json.JSONDecodeError:
        st.error("Invalid JSON format for authors.")

# Input field to specify filename and path for saving
filename = st.text_input("Enter the filename and path to save CSV", "package_editors.csv")

# Button to save the data to the specified CSV file
if st.button("Save to CSV"):
    save_to_csv(filename)