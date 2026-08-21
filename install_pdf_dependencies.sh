#!/bin/bash

# Script to install PDF conversion dependencies for the Confluence to PDF converter

echo "🔧 Installing PDF conversion dependencies..."

# Check if we're on macOS
if [[ "$OSTYPE" == "darwin"* ]]; then
    echo "📱 Detected macOS"
    
    # Check if Homebrew is installed
    if ! command -v brew &> /dev/null; then
        echo "❌ Homebrew not found. Please install Homebrew first:"
        echo "   /bin/bash -c \"\$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)\""
        exit 1
    fi
    
    echo "🍺 Installing WeasyPrint dependencies..."
    brew install cairo pango gdk-pixbuf libffi
    
    echo "🍺 Installing wkhtmltopdf for pdfkit fallback..."
    # Try to install wkhtmltopdf, but it may be discontinued
    if brew install wkhtmltopdf 2>/dev/null; then
        echo "✅ wkhtmltopdf installed via Homebrew"
    else
        echo "⚠️ wkhtmltopdf not available via Homebrew (discontinued)"
        echo "💡 Alternative: Install manually from https://wkhtmltopdf.org/downloads.html"
        echo "   Or use WeasyPrint only (recommended)"
    fi
    
    echo "✅ macOS dependencies installed!"
    
elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
    echo "🐧 Detected Linux"
    
    # Check if apt is available (Ubuntu/Debian)
    if command -v apt-get &> /dev/null; then
        echo "📦 Installing WeasyPrint dependencies..."
        sudo apt-get update
        sudo apt-get install -y libcairo2 libpango-1.0-0 libgdk-pixbuf2.0-0 libffi-dev
        
        echo "📦 Installing wkhtmltopdf for pdfkit fallback..."
        sudo apt-get install -y wkhtmltopdf
        
        echo "✅ Ubuntu/Debian dependencies installed!"
        
    # Check if yum is available (CentOS/RHEL)
    elif command -v yum &> /dev/null; then
        echo "📦 Installing WeasyPrint dependencies..."
        sudo yum install -y cairo pango gdk-pixbuf2 libffi-devel
        
        echo "📦 Installing wkhtmltopdf for pdfkit fallback..."
        sudo yum install -y wkhtmltopdf
        
        echo "✅ CentOS/RHEL dependencies installed!"
        
    else
        echo "❌ Unsupported Linux distribution. Please install manually:"
        echo "   - cairo, pango, gdk-pixbuf2, libffi-dev"
        echo "   - wkhtmltopdf"
        exit 1
    fi
    
else
    echo "❌ Unsupported operating system: $OSTYPE"
    echo "Please install dependencies manually:"
    echo "   - cairo, pango, gdk-pixbuf2, libffi"
    echo "   - wkhtmltopdf"
    exit 1
fi

echo ""
echo "🐍 Installing Python dependencies..."
pip install weasyprint pdfkit psutil markdownify

echo ""
echo "✅ All dependencies installed!"
echo ""
echo "📋 Next steps:"
echo "1. Test the script: python convert-confluence-to-pdf-with-attachments.py --dry-run"
echo "2. WeasyPrint should work well with the memory management improvements"
echo "3. If PDF conversion fails, HTML files will be created that you can manually convert to PDF"
echo ""
echo "💡 Note: wkhtmltopdf is discontinued. WeasyPrint is recommended for PDF conversion."
