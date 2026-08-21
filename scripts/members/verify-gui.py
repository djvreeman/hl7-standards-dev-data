#!/usr/bin/env python3
"""
Verification script to test GUI functionality
"""

import sys
import os

print("🔍 Verifying GUI components...")

try:
    # Test tkinter
    import tkinter as tk
    from tkinter import ttk, filedialog, messagebox, scrolledtext
    print("✅ Tkinter and all GUI components available")
    
    # Test other required modules
    import pandas as pd
    print("✅ Pandas available")
    
    import requests
    print("✅ Requests available")
    
    import yaml
    print("✅ PyYAML available")
    
    from fuzzywuzzy import fuzz
    print("✅ FuzzyWuzzy available")
    
    print("\n🎉 All components verified! GUI should work properly.")
    print("\nTo launch the GUI, run:")
    print("python3 trademark-matcher-simple-gui.py")
    
except ImportError as e:
    print(f"❌ Missing component: {e}")
    print("\nPlease install missing packages:")
    print("pip install -r requirements-gui.txt")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc() 