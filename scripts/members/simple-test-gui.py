#!/usr/bin/env python3
"""
Simple test GUI to verify basic functionality
"""

import tkinter as tk
from tkinter import ttk, messagebox

def main():
    root = tk.Tk()
    root.title("Simple Test GUI")
    root.geometry("400x300")
    
    # Add some basic widgets
    frame = ttk.Frame(root, padding="20")
    frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
    
    ttk.Label(frame, text="Trademark Matcher GUI Test", font=('Arial', 14, 'bold')).grid(row=0, column=0, pady=(0, 20))
    
    ttk.Label(frame, text="This is a simple test to verify GUI functionality.").grid(row=1, column=0, pady=(0, 10))
    
    def test_click():
        messagebox.showinfo("Test", "GUI is working! ✅")
    
    ttk.Button(frame, text="Test Button", command=test_click).grid(row=2, column=0, pady=10)
    
    ttk.Label(frame, text="If you can see this window and click the button, the GUI is working.").grid(row=3, column=0, pady=10)
    
    root.mainloop()

if __name__ == '__main__':
    main() 