#!/usr/bin/env bash
set -e

# Ensure uv is in PATH (for cron environment)
export PATH="$HOME/.local/bin:$PATH"

# Usage message
print_usage() { echo "Usage: $0 [--db <DB_PATH>] [--api] [--hours <hours>] [--end-hour <end_hour>]"; exit 1; }

# Default parameters
DB_PATH="${DB_PATH:-$(grep -E '^DB_PATH=' .env 2>/dev/null | cut -d '=' -f2)}"
HOURS=168
END_HOUR=17
API_MODE=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --db) DB_PATH="$2"; shift 2;;
        --api) API_MODE="--api"; shift;;
        --hours) HOURS="$2"; shift 2;;
        --end-hour) END_HOUR="$2"; shift 2;;
        -h|--help) print_usage;;
        *) echo "Unknown option: $1"; print_usage;;
    esac
done

# Change to script directory
cd "$(dirname "$0")"

# =============================================================================
# Cleanup: Keep only the last 12 runs
# =============================================================================
echo "Cleaning up old files (keeping last 12 runs)..."

# Clean articles/ directories
if [[ -d "articles" ]]; then
    ls -td articles/articles_* 2>/dev/null | tail -n +13 | xargs -r rm -rf
    echo "  Cleaned articles/"
fi

# Clean abstract_md/ files
if [[ -d "abstract_md" ]]; then
    ls -t abstract_md/abstract_md_*.md 2>/dev/null | tail -n +13 | xargs -r rm -f
    echo "  Cleaned abstract_md/"
fi

# Clean deliverable/ files (keep last 12 pairs of .md and .pdf)
# Use xargs -I {} to handle filenames with spaces
if [[ -d "deliverable" ]]; then
    ls -1t deliverable/*.md 2>/dev/null | tail -n +13 | xargs -I {} rm -f "{}"
    ls -1t deliverable/*.pdf 2>/dev/null | tail -n +13 | xargs -I {} rm -f "{}"
    echo "  Cleaned deliverable/"
fi

echo "Cleanup complete."
# =============================================================================

echo "Syncing dependencies with uv..."
uv sync

echo "Step 1: Extracting articles..."
if [[ -n "$API_MODE" ]]; then
    uv run python 0_sqlite_to_articles.py $API_MODE --hours "$HOURS" --end-hour "$END_HOUR"
elif [[ -n "$DB_PATH" ]]; then
    uv run python 0_sqlite_to_articles.py --db "$DB_PATH" --hours "$HOURS" --end-hour "$END_HOUR"
else
    # Let Python script decide based on .env (API if FRESHRSS_API_URL set, else error)
    uv run python 0_sqlite_to_articles.py --hours "$HOURS" --end-hour "$END_HOUR"
fi
# Determine the output directory created by the Python script based on timestamp
OUTPUT_DIR=$(ls -td articles/articles_* | head -n 1)
ARTICLES_LIST="$OUTPUT_DIR/successful_articles.txt"
if [[ ! -f "$ARTICLES_LIST" ]]; then
    echo "Error: Article list file not found at $ARTICLES_LIST"
    exit 1
fi
echo "Articles list: $ARTICLES_LIST"

echo "Step 2: Generating abstracts..."
uv run python 1_article_to_abstract_md.py "$ARTICLES_LIST"
ABSTRACT_MD_FILE=$(ls -t abstract_md/abstract_md_*.md | head -n 1)
if [[ ! -f "$ABSTRACT_MD_FILE" ]]; then
    echo "Error: Abstract markdown file not found."
    exit 1
fi
echo "Abstract markdown: $ABSTRACT_MD_FILE"

echo "Step 3: Generating final summary..."
uv run python 2_abstract_to_summary.py --input-md "$ABSTRACT_MD_FILE"
SUMMARY_MD=$(ls -t deliverable/"AI News Update "*.md 2>/dev/null | head -n 1)
if [[ -z "$SUMMARY_MD" ]]; then
    echo "Error: Summary markdown file not found."
    exit 1
fi
echo "Summary markdown: $SUMMARY_MD"

echo "Step 4: Converting summary to PDF..."
uv run python 3_md_to_pdf.py "$SUMMARY_MD"
PDF_FILE="${SUMMARY_MD%.md}.pdf"
if [[ ! -f "$PDF_FILE" ]]; then
    echo "Error: PDF file not created."
    exit 1
fi
echo "PDF file: $PDF_FILE"

echo "Step 5: Uploading to Dropbox..."
uv run python 4_save_to_dropbox.py "$SUMMARY_MD" "$PDF_FILE"

echo "Pipeline completed successfully!"