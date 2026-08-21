#!/usr/bin/env python3
"""
Test script to verify PDF conversion dependencies are properly installed.
Run this before using the main conversion script.
"""

import sys

def test_imports():
    """Test if all required modules can be imported"""
    print("🔍 Testing PDF conversion dependencies...")
    
    # Core dependencies
    try:
        import requests
        print("✅ requests - OK")
    except ImportError:
        print("❌ requests - MISSING")
        return False
    
    try:
        import yaml
        print("✅ pyyaml - OK")
    except ImportError:
        print("❌ pyyaml - MISSING")
        return False
    
    try:
        from bs4 import BeautifulSoup
        print("✅ beautifulsoup4 - OK")
    except ImportError:
        print("❌ beautifulsoup4 - MISSING")
        return False
    
    # PDF conversion libraries
    weasyprint_available = False
    pdfkit_available = False
    
    try:
        from weasyprint import HTML, CSS
        print("✅ weasyprint - OK (preferred)")
        weasyprint_available = True
    except ImportError:
        print("⚠️  weasyprint - NOT AVAILABLE")
    
    try:
        import pdfkit
        print("✅ pdfkit - OK (fallback)")
        pdfkit_available = True
    except ImportError:
        print("⚠️  pdfkit - NOT AVAILABLE")
    
    if not weasyprint_available and not pdfkit_available:
        print("❌ ERROR: Neither weasyprint nor pdfkit is available!")
        print("   Please install at least one of them:")
        print("   pip install weasyprint")
        print("   pip install pdfkit")
        return False
    
    return True

def test_weasyprint_functionality():
    """Test if WeasyPrint can actually generate PDFs"""
    try:
        from weasyprint import HTML
        print("\n🧪 Testing WeasyPrint functionality...")
        
        # Create a simple test HTML
        test_html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Test PDF Generation</h1>
            <p>If you can see this, WeasyPrint is working correctly!</p>
        </body>
        </html>
        """
        
        # Try to create a PDF (in memory)
        HTML(string=test_html).write_pdf(target=None)
        print("✅ WeasyPrint PDF generation - OK")
        return True
        
    except Exception as e:
        print(f"❌ WeasyPrint test failed: {e}")
        print("   This might be due to missing system dependencies.")
        print("   On macOS: brew install cairo pango gdk-pixbuf libffi")
        print("   On Ubuntu: sudo apt-get install libcairo2 libpango-1.0-0 libgdk-pixbuf2.0-0 libffi-dev")
        return False

def test_pdfkit_functionality():
    """Test if pdfkit can actually generate PDFs"""
    try:
        import pdfkit
        print("\n🧪 Testing pdfkit functionality...")
        
        # Check if wkhtmltopdf is available
        try:
            pdfkit.from_string("<h1>Test</h1>", "test.pdf")
            print("✅ pdfkit PDF generation - OK")
            # Clean up test file
            import os
            if os.path.exists("test.pdf"):
                os.remove("test.pdf")
            return True
        except Exception as e:
            print(f"❌ pdfkit test failed: {e}")
            print("   This might be due to missing wkhtmltopdf.")
            print("   On macOS: brew install wkhtmltopdf")
            print("   On Ubuntu: sudo apt-get install wkhtmltopdf")
            return False
            
    except ImportError:
        print("⚠️  pdfkit not available for testing")
        return False

def main():
    print("🚀 PDF Conversion Dependency Checker")
    print("=" * 40)
    
    # Test imports
    if not test_imports():
        print("\n❌ FAILED: Missing required dependencies")
        sys.exit(1)
    
    # Test functionality
    weasyprint_works = False
    pdfkit_works = False
    
    try:
        weasyprint_works = test_weasyprint_functionality()
    except:
        pass
    
    try:
        pdfkit_works = test_pdfkit_functionality()
    except:
        pass
    
    print("\n" + "=" * 40)
    if weasyprint_works or pdfkit_works:
        print("✅ SUCCESS: PDF conversion is ready!")
        if weasyprint_works:
            print("   Using WeasyPrint for PDF generation")
        elif pdfkit_works:
            print("   Using pdfkit for PDF generation")
        print("\n🎉 You can now run the conversion script!")
    else:
        print("❌ FAILED: No PDF conversion method is working")
        print("   Please check the error messages above and install missing dependencies")
        sys.exit(1)

if __name__ == "__main__":
    main()
