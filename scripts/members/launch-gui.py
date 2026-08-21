#!/usr/bin/env python3
"""
Simple launcher for the Trademark Matcher GUI
"""

import sys
import os

# Add current directory to Python path
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, current_dir)

try:
    # Try to import tkinter
    import tkinter as tk
    print("✅ Tkinter available")
    
    # Try to import other required modules
    import pandas as pd
    print("✅ Pandas available")
    
    import requests
    print("✅ Requests available")
    
    import yaml
    print("✅ PyYAML available")
    
    from fuzzywuzzy import fuzz
    print("✅ FuzzyWuzzy available")
    
    # Launch the GUI
    print("Launching GUI...")
    from trademark_matcher_gui_standalone import TrademarkMatcherGUI
    
    root = tk.Tk()
    app = TrademarkMatcherGUI(root)
    root.mainloop()
    
except ImportError as e:
    print(f"❌ Missing required module: {e}")
    print("\nPlease install required packages:")
    print("pip install -r requirements-gui.txt")
    
except Exception as e:
    print(f"❌ Error launching GUI: {e}")
    import traceback
    traceback.print_exc() 