#!/usr/bin/env python3
"""
Test script to check PDF conversion capabilities.
"""

import os
import tempfile

def test_weasyprint():
    """Test WeasyPrint functionality"""
    print("=== Testing WeasyPrint ===")
    try:
        from weasyprint import HTML
        print("✅ WeasyPrint library imported successfully")
        
        # Test basic conversion
        test_html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Test Page</h1>
            <p>This is a test of WeasyPrint conversion.</p>
        </body>
        </html>
        """
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            html_obj = HTML(string=test_html)
            html_obj.write_pdf(tmp_file.name)
            print(f"✅ WeasyPrint PDF created: {tmp_file.name}")
            os.unlink(tmp_file.name)
            
        return True
        
    except ImportError as e:
        print(f"❌ WeasyPrint not available: {e}")
        return False
    except Exception as e:
        print(f"❌ WeasyPrint failed: {e}")
        return False

def test_pdfkit():
    """Test pdfkit functionality"""
    print("\n=== Testing pdfkit ===")
    try:
        import pdfkit
        print("✅ pdfkit library imported successfully")
        
        # Test basic conversion
        test_html = """
        <html>
        <head><title>Test</title></head>
        <body>
            <h1>Test Page</h1>
            <p>This is a test of pdfkit conversion.</p>
        </body>
        </html>
        """
        
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp_file:
            options = {
                'page-size': 'A4',
                'margin-top': '0.75in',
                'margin-right': '0.75in',
                'margin-bottom': '0.75in',
                'margin-left': '0.75in',
                'encoding': "UTF-8",
            }
            pdfkit.from_string(test_html, tmp_file.name, options=options)
            print(f"✅ pdfkit PDF created: {tmp_file.name}")
            os.unlink(tmp_file.name)
            
        return True
        
    except ImportError as e:
        print(f"❌ pdfkit not available: {e}")
        return False
    except Exception as e:
        print(f"❌ pdfkit failed: {e}")
        if "wkhtmltopdf" in str(e).lower():
            print("💡 Install wkhtmltopdf: brew install wkhtmltopdf (macOS)")
        return False

def main():
    """Run all tests"""
    print("🔧 Testing PDF Conversion Capabilities")
    print("=" * 50)
    
    weasyprint_works = test_weasyprint()
    pdfkit_works = test_pdfkit()
    
    print("\n" + "=" * 50)
    print("📋 Summary:")
    
    if weasyprint_works:
        print("✅ WeasyPrint: Working")
    else:
        print("❌ WeasyPrint: Not working")
        
    if pdfkit_works:
        print("✅ pdfkit: Working")
    else:
        print("❌ pdfkit: Not working")
    
    if not weasyprint_works and not pdfkit_works:
        print("\n🚨 No PDF conversion method is working!")
        print("💡 Install dependencies: ./install_pdf_dependencies.sh")
    elif not weasyprint_works:
        print("\n⚠️ WeasyPrint not working, but pdfkit is available")
        print("💡 Use --use-pdfkit-only flag when running the script")
    elif not pdfkit_works:
        print("\n⚠️ pdfkit not working, but WeasyPrint is available")
        print("💡 The script should work with WeasyPrint fallback")
    else:
        print("\n✅ Both PDF conversion methods are working!")
        print("💡 The script will use WeasyPrint with pdfkit fallback")

if __name__ == "__main__":
    main()

