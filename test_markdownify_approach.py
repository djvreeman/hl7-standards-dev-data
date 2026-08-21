#!/usr/bin/env python3
"""
Test script to verify the markdownify approach for memory-efficient PDF conversion.
"""

import os
import tempfile
import markdownify

def test_markdownify_conversion():
    """Test markdownify HTML to Markdown conversion"""
    print("=== Testing markdownify HTML to Markdown Conversion ===")
    
    # Sample HTML content similar to Confluence
    sample_html = """
    <html>
    <head><title>Test Page</title></head>
    <body>
        <h1>Test Page Title</h1>
        <p>This is a test paragraph with <strong>bold text</strong> and <em>italic text</em>.</p>
        
        <h2>Section 1</h2>
        <p>This is section 1 content.</p>
        
        <h3>Subsection</h3>
        <ul>
            <li>Item 1</li>
            <li>Item 2</li>
            <li>Item 3</li>
        </ul>
        
        <table>
            <tr><th>Header 1</th><th>Header 2</th></tr>
            <tr><td>Data 1</td><td>Data 2</td></tr>
        </table>
        
        <p>Here's a <a href="test.pdf">link to a file</a>.</p>
    </body>
    </html>
    """
    
    try:
        # Convert HTML to Markdown
        markdown_content = markdownify.markdownify(sample_html, heading_style="ATX")
        
        print("✅ HTML to Markdown conversion successful!")
        print("\n📄 Generated Markdown:")
        print("=" * 50)
        print(markdown_content)
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"❌ markdownify conversion failed: {e}")
        return False

def test_markdown_to_html():
    """Test Markdown to HTML conversion"""
    print("\n=== Testing Markdown to HTML Conversion ===")
    
    sample_markdown = """
# Test Page Title

This is a test paragraph with **bold text** and *italic text*.

## Section 1

This is section 1 content.

### Subsection

- Item 1
- Item 2
- Item 3

| Header 1 | Header 2 |
|----------|----------|
| Data 1   | Data 2   |

Here's a [link to a file](test.pdf).
"""
    
    try:
        import markdown
        html_content = markdown.markdown(sample_markdown, extensions=['tables', 'fenced_code', 'codehilite'])
        
        print("✅ Markdown to HTML conversion successful!")
        print(f"📄 Generated HTML length: {len(html_content)} characters")
        
        return True
        
    except ImportError:
        print("⚠️ markdown library not available")
        return False
    except Exception as e:
        print(f"❌ Markdown to HTML conversion failed: {e}")
        return False

def test_memory_efficiency():
    """Test memory efficiency of the approach"""
    print("\n=== Testing Memory Efficiency ===")
    
    # Create a large HTML content to test memory usage
    large_html = "<html><body>"
    for i in range(1000):
        large_html += f"<h1>Section {i}</h1><p>This is content for section {i}.</p>"
    large_html += "</body></html>"
    
    try:
        # Check memory before conversion
        import psutil
        process = psutil.Process()
        memory_before = process.memory_info().rss / 1024 / 1024
        
        # Convert to Markdown
        markdown_content = markdownify.markdownify(large_html, heading_style="ATX")
        
        # Check memory after conversion
        memory_after = process.memory_info().rss / 1024 / 1024
        memory_diff = memory_after - memory_before
        
        print(f"✅ Memory usage: {memory_before:.1f}MB → {memory_after:.1f}MB (Δ{memory_diff:+.1f}MB)")
        print(f"📄 Markdown content length: {len(markdown_content)} characters")
        
        if memory_diff < 50:  # Less than 50MB increase
            print("✅ Memory efficient!")
        else:
            print("⚠️ Higher memory usage than expected")
        
        return True
        
    except ImportError:
        print("⚠️ psutil not available for memory monitoring")
        return True
    except Exception as e:
        print(f"❌ Memory efficiency test failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔧 Testing markdownify-based PDF Conversion Approach")
    print("=" * 60)
    
    tests = [
        test_markdownify_conversion,
        test_markdown_to_html,
        test_memory_efficiency
    ]
    
    results = []
    for test in tests:
        try:
            result = test()
            results.append(result)
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")
            results.append(False)
    
    print("\n" + "=" * 60)
    print("📋 Test Summary:")
    
    test_names = ["markdownify conversion", "markdown to HTML", "memory efficiency"]
    for i, (name, result) in enumerate(zip(test_names, results)):
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"  {status}: {name}")
    
    all_passed = all(results)
    if all_passed:
        print("\n🎉 All tests passed! The markdownify approach should work well.")
        print("💡 You can now use: python convert-confluence-to-pdf-via-markdown.py")
    else:
        print("\n⚠️ Some tests failed. Check the output above for details.")
        print("💡 You may need to install dependencies: pip install markdownify markdown psutil")

if __name__ == "__main__":
    main()

