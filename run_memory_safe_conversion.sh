#!/bin/bash

# Script to run the memory-safe PDF conversion with appropriate flags

echo "🚀 Running Memory-Safe PDF Conversion"
echo "======================================"

# Check if the script exists
if [ ! -f "scripts/hl7-process-documents/convert-confluence-to-pdf-via-markdown.py" ]; then
    echo "❌ Error: convert-confluence-to-pdf-via-markdown.py not found"
    exit 1
fi

# Set default values
SKIP_ON_ERROR=""
MAX_MEMORY="150"
SPACES=""

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-on-error)
            SKIP_ON_ERROR="--skip-on-error"
            shift
            ;;
        --max-memory)
            MAX_MEMORY="$2"
            shift 2
            ;;
        --spaces)
            SPACES="--spaces $2"
            shift 2
            ;;
        --dry-run)
            DRY_RUN="--dry-run"
            shift
            ;;
        *)
            echo "Unknown option: $1"
            echo "Usage: $0 [--skip-on-error] [--max-memory MB] [--spaces SPACE1,SPACE2] [--dry-run]"
            exit 1
            ;;
    esac
done

echo "📋 Configuration:"
echo "  Skip on error: ${SKIP_ON_ERROR:-No}"
echo "  Max memory: ${MAX_MEMORY}MB"
echo "  Spaces: ${SPACES:-All}"
echo "  Dry run: ${DRY_RUN:-No}"
echo ""

# Create logs directory
mkdir -p logs

# Run the conversion
echo "🔄 Starting conversion..."
python scripts/hl7-process-documents/convert-confluence-to-pdf-via-markdown.py \
    --main-config data/config/main.yaml \
    --spaces-dir data/config/spaces \
    --log-file logs/conversion-$(date +%Y%m%d-%H%M%S).log \
    --max-memory-mb $MAX_MEMORY \
    $SKIP_ON_ERROR \
    $SPACES \
    $DRY_RUN

echo ""
echo "✅ Conversion completed!"
echo "📁 Check the logs directory for detailed output"
echo "📁 Check the output directory for generated files"

