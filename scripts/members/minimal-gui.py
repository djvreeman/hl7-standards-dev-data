#!/usr/bin/env python3
"""
Minimal working GUI for trademark matcher
"""

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

def main():
    root = tk.Tk()
    root.title("Trademark Matcher - Minimal GUI")
    root.geometry("500x400")
    
    # Main frame
    frame = ttk.Frame(root, padding="20")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    # Title
    ttk.Label(frame, text="Trademark Member Matcher", font=('Arial', 16, 'bold')).grid(row=0, column=0, columnspan=3, pady=(0, 20))
    
    # File selection
    ttk.Label(frame, text="Input Excel File:").grid(row=1, column=0, sticky=tk.W, pady=5)
    input_var = tk.StringVar()
    ttk.Entry(frame, textvariable=input_var, width=40).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=(5, 0))
    
    def browse_input():
        filename = filedialog.askopenfilename(
            title="Select Input Excel File",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if filename:
            input_var.set(filename)
    
    ttk.Button(frame, text="Browse", command=browse_input).grid(row=1, column=2, padx=(5, 0))
    
    # Output file
    ttk.Label(frame, text="Output Excel File:").grid(row=2, column=0, sticky=tk.W, pady=5)
    output_var = tk.StringVar()
    ttk.Entry(frame, textvariable=output_var, width=40).grid(row=2, column=1, sticky=(tk.W, tk.E), padx=(5, 0))
    
    def browse_output():
        filename = filedialog.asksaveasfilename(
            title="Select Output Excel File",
            defaultextension=".xlsx",
            filetypes=[("Excel files", "*.xlsx"), ("All files", "*.*")]
        )
        if filename:
            output_var.set(filename)
    
    ttk.Button(frame, text="Browse", command=browse_output).grid(row=2, column=2, padx=(5, 0))
    
    # Status
    status_var = tk.StringVar(value="Ready")
    ttk.Label(frame, textvariable=status_var).grid(row=3, column=0, columnspan=3, sticky=tk.W, pady=20)
    
    # Buttons
    def test_connection():
        status_var.set("Testing connection...")
        messagebox.showinfo("Test", "This would test the Salesforce connection")
        status_var.set("Connection test complete")
    
    def process_data():
        if not input_var.get() or not output_var.get():
            messagebox.showerror("Error", "Please select both input and output files")
            return
        status_var.set("Processing data...")
        messagebox.showinfo("Process", "This would process the trademark applications")
        status_var.set("Processing complete")
    
    button_frame = ttk.Frame(frame)
    button_frame.grid(row=4, column=0, columnspan=3, pady=20)
    
    ttk.Button(button_frame, text="Test Connection", command=test_connection).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(button_frame, text="Process Data", command=process_data).pack(side=tk.LEFT, padx=(0, 10))
    ttk.Button(button_frame, text="Quit", command=root.quit).pack(side=tk.LEFT)
    
    # Configure grid weights
    root.columnconfigure(0, weight=1)
    root.rowconfigure(0, weight=1)
    frame.columnconfigure(1, weight=1)
    
    root.mainloop()

if __name__ == '__main__':
    main() 