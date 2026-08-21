#!/usr/bin/env python3
"""
Test script to check GUI import functionality
"""

import os
import sys
import importlib.util

print("Testing GUI import...")

try:
    # Test importing the main matcher module
    current_dir = os.path.dirname(os.path.abspath(__file__))
    matcher_path = os.path.join(current_dir, "trademark-member-matcher.py")
    
    print(f"Current directory: {current_dir}")
    print(f"Matcher path: {matcher_path}")
    print(f"File exists: {os.path.exists(matcher_path)}")
    
    if os.path.exists(matcher_path):
        spec = importlib.util.spec_from_file_location("tm", matcher_path)
        tm = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(tm)
        print("✅ Successfully imported trademark-member-matcher module")
        
        # Test basic functionality
        print("Testing config loading...")
        config_path = os.path.join(current_dir, "../../data/config/sf-config.yaml")
        print(f"Config path: {config_path}")
        print(f"Config exists: {os.path.exists(config_path)}")
        
        if os.path.exists(config_path):
            config = tm.load_config(config_path)
            print("✅ Successfully loaded config")
        else:
            print("❌ Config file not found")
            
    else:
        print("❌ Matcher file not found")
        
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()

print("Import test complete!") 