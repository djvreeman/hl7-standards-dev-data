import sys
import os
import pandas as pd
import json
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QPushButton, 
    QFileDialog, QTableWidget, QTableWidgetItem, QMessageBox, QDialog,
    QFormLayout, QLineEdit, QDialogButtonBox, QHBoxLayout, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QDesktopServices

class EditorsUI(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("CSV Editors Manager")
        self.setGeometry(100, 100, 1200, 600)

        self.data = None
        self.file_path = None
        self.last_directory = os.getcwd()
        self.unsaved_changes = False  # Track unsaved changes

        layout = QVBoxLayout()

        load_button = QPushButton("Load CSV")
        load_button.clicked.connect(self.check_unsaved_changes_before_loading)
        layout.addWidget(load_button)

        self.table = QTableWidget()
        self.table.cellClicked.connect(self.handle_table_click)  # Handle clicks for hyperlinks
        layout.addWidget(self.table)

        edit_button = QPushButton("Edit Selected Editors")
        edit_button.clicked.connect(self.edit_selected)
        layout.addWidget(edit_button)

        save_button = QPushButton("Save CSV")
        save_button.clicked.connect(self.save_csv)
        layout.addWidget(save_button)

        container = QWidget()
        container.setLayout(layout)
        self.setCentralWidget(container)

    def check_unsaved_changes_before_loading(self):
        """Check for unsaved changes before loading a new file."""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to discard them and load a new file?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                return  # Do not proceed if the user chooses not to discard changes
        self.load_csv()

    def closeEvent(self, event):
        """Handle the close event to warn about unsaved changes."""
        if self.unsaved_changes:
            reply = QMessageBox.question(
                self, "Unsaved Changes",
                "You have unsaved changes. Do you want to discard them and exit?",
                QMessageBox.Yes | QMessageBox.No, QMessageBox.No
            )
            if reply == QMessageBox.No:
                event.ignore()  # Cancel the close event
            else:
                event.accept()  # Allow the window to close

    def load_csv(self):
        """Load a CSV file."""
        self.file_path, _ = QFileDialog.getOpenFileName(self, "Open CSV", self.last_directory, "CSV Files (*.csv)")
        if self.file_path:
            try:
                self.last_directory = os.path.dirname(self.file_path)
                self.data = pd.read_csv(self.file_path)
                self.data['editors'] = self.data['editors'].fillna("{}").apply(lambda x: "{}" if x.strip() == "" else x)
                self.populate_table()
                self.unsaved_changes = False  # Reset unsaved changes flag
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to load CSV: {str(e)}")

    def populate_table(self):
        """Populate the table with CSV data."""
        columns = self.data.columns
        self.table.setRowCount(len(self.data))
        self.table.setColumnCount(len(columns))
        self.table.setHorizontalHeaderLabels(columns)

        for row_idx, row in self.data.iterrows():
            for col_idx, value in enumerate(row):
                item = QTableWidgetItem(str(value))
                if self.is_url(str(value)):
                    item.setData(Qt.UserRole, QUrl(value))
                    item.setForeground(Qt.blue)
                    item.setToolTip("Click to open URL")
                self.table.setItem(row_idx, col_idx, item)

    def is_url(self, text):
        """Check if a string is a URL."""
        return text.startswith("http://") or text.startswith("https://")

    def handle_table_click(self, row, column):
        """Handle clicks on table cells to open URLs."""
        item = self.table.item(row, column)
        if item:
            url = item.data(Qt.UserRole)
            if isinstance(url, QUrl):
                QDesktopServices.openUrl(url)

    def edit_selected(self):
        """Edit the editors field of the selected row."""
        selected_row = self.table.currentRow()
        if selected_row == -1:
            QMessageBox.warning(self, "Warning", "No row selected.")
            return

        editors_json = self.table.item(selected_row, self.data.columns.get_loc("editors")).text()
        editor_dialog = EditorsDialog(editors_json)
        if editor_dialog.exec_() == QDialog.Accepted:
            new_editors = editor_dialog.get_editors()
            self.data.at[selected_row, "editors"] = new_editors
            self.populate_table()
            self.unsaved_changes = True

    def save_csv(self):
        """Save the modified CSV."""
        if self.file_path:
            try:
                self.data.to_csv(self.file_path, index=False)
                QMessageBox.information(self, "Success", "CSV saved successfully!")
                self.unsaved_changes = False
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to save CSV: {str(e)}")

class EditorsDialog(QDialog):
    def __init__(self, editors_json):
        super().__init__()
        self.setWindowTitle("Edit Editors")

        # Parse the JSON or initialize with an empty structure
        try:
            self.editors = json.loads(editors_json)
        except json.JSONDecodeError:
            self.editors = {}  # Initialize with an empty dictionary

        # Ensure the "authors" key exists
        if "authors" not in self.editors:
            self.editors["authors"] = []

        layout = QVBoxLayout()

        # List of authors
        self.authors_list = QListWidget()
        self.populate_authors_list()
        self.authors_list.currentRowChanged.connect(self.load_author_details)
        layout.addWidget(self.authors_list)

        # Author input fields
        self.first_name_input = QLineEdit()
        self.last_name_input = QLineEdit()
        self.role_input = QLineEdit()
        self.email_input = QLineEdit()

        form_layout = QFormLayout()
        form_layout.addRow("First Name:", self.first_name_input)
        form_layout.addRow("Last Name:", self.last_name_input)
        form_layout.addRow("Role:", self.role_input)
        form_layout.addRow("Email:", self.email_input)
        layout.addLayout(form_layout)

        # Buttons for adding, saving, and removing authors
        buttons_layout = QHBoxLayout()
        save_button = QPushButton("Save Author")
        save_button.clicked.connect(self.save_author)
        buttons_layout.addWidget(save_button)

        add_button = QPushButton("Add Another Author")
        add_button.clicked.connect(self.add_new_author)
        buttons_layout.addWidget(add_button)

        remove_button = QPushButton("Remove Selected Author")
        remove_button.clicked.connect(self.remove_selected_author)
        buttons_layout.addWidget(remove_button)

        layout.addLayout(buttons_layout)

        # OK and Cancel buttons
        button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)

        self.setLayout(layout)

    def populate_authors_list(self):
        """Populate the list with existing authors."""
        self.authors_list.clear()
        for author in self.editors["authors"]:
            item_text = f"{author['first_name']} {author['last_name']} ({author['role']})"
            self.authors_list.addItem(QListWidgetItem(item_text))

    def load_author_details(self, index):
        """Load the selected author's details into the form."""
        if index != -1:
            author = self.editors["authors"][index]
            self.first_name_input.setText(author.get("first_name", ""))
            self.last_name_input.setText(author.get("last_name", ""))
            self.role_input.setText(author.get("role", ""))
            self.email_input.setText(author.get("email", ""))

    def save_author(self):
        """Save the current author details to the selected author."""
        current_index = self.authors_list.currentRow()
        if current_index != -1:
            self.editors["authors"][current_index] = {
                "first_name": self.first_name_input.text(),
                "last_name": self.last_name_input.text(),
                "role": self.role_input.text(),
                "email": self.email_input.text(),
            }
            self.populate_authors_list()

    def add_new_author(self):
        """Add a new author with the entered details."""
        new_author = {
            "first_name": self.first_name_input.text(),
            "last_name": self.last_name_input.text(),
            "role": self.role_input.text(),
            "email": self.email_input.text(),
        }
        self.editors["authors"].append(new_author)  # Safely append the new author
        self.populate_authors_list()
        self.clear_author_form()

    def remove_selected_author(self):
        """Remove the selected author from the list."""
        selected_index = self.authors_list.currentRow()
        if selected_index != -1:
            del self.editors["authors"][selected_index]
            self.populate_authors_list()

    def clear_author_form(self):
        """Clear the input fields for adding a new author."""
        self.first_name_input.clear()
        self.last_name_input.clear()
        self.role_input.clear()
        self.email_input.clear()

    def get_editors(self):
        """Return the updated editors JSON."""
        return json.dumps(self.editors, indent=4)
    
def main():
    app = QApplication(sys.argv)
    window = EditorsUI()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()