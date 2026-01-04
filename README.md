# AI News Summary Tool

This tool automatically extracts AI-related articles from FreshRSS, generates article abstracts, compiles a weekly summary, and outputs Markdown and PDF documents.

## Features

- Extract AI news articles from FreshRSS (via API or SQLite database)
- Generate individual article abstracts in Markdown
- Merge abstracts to produce a weekly summary Markdown file
- Convert Markdown documents to PDF
- Support parallel processing for improved performance
- Automatically upload summary Markdown and PDF files via rclone or Dropbox API
- **Auto-cleanup**: Keeps only the last 12 runs to save disk space

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) - Fast Python package manager
- Operating Systems: Windows, macOS, or Linux

## Installation

1. Install uv (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Clone the repository:
   ```bash
   git clone <repository_url>
   cd ai_news_summary
   ```

3. Install dependencies:
   ```bash
   uv sync
   ```

## Configuration

Create a `.env` file in the project root. The `run.sh` script and individual Python scripts will load configurations from this file.

### Data Source (choose one)

The tool supports two modes for fetching articles:

#### Option A: FreshRSS API Mode (Recommended for remote FreshRSS)

Use this when FreshRSS is running on a different machine.

```dotenv
# --- FreshRSS API Configuration ---
FRESHRSS_API_URL="https://your-freshrss-domain.com/api/greader.php"
FRESHRSS_API_USER="your_username"
FRESHRSS_API_PASSWORD="your_api_password"
FRESHRSS_API_CATEGORY="AI-News"  # Supports multiple: "AI-News,Tech,Research"
# Optional: exclude specific feeds within categories
FRESHRSS_API_EXCLUDE_FEEDS="Feed Name To Skip,Another Feed"
```

**Setup steps:**
1. In FreshRSS, go to Settings → Authentication → Enable API access
2. Set an API password (different from your login password)
3. Create a category (e.g., "AI-News") and add your desired feeds to it
4. Set the above environment variables

#### Option B: SQLite Mode (Local database)

Use this when you have direct access to the FreshRSS SQLite database.

```dotenv
# --- SQLite Configuration ---
# Path to the FreshRSS SQLite database file.
DB_PATH=/path/to/freshrss.db

# Comma-separated list of exact feed names to include.
# This is **MANDATORY** for SQLite mode.
ALLOWED_FEED_NAMES="TechCrunch AI News,Reuters AI News,The Verge - AI"

# Optional: Category ID for WeChat articles (or similar).
WECHAT_CATEGORY_ID="where_you_put_your_wechat_rss"

# Optional: URL pattern for WeChat articles.
WECHAT_URL_PATTERN_CONTAINS="wechat2rss_or_other_service_provider"
```

**Mode selection priority:**
- If `--api` flag is used → API mode
- If only `FRESHRSS_API_URL` is set → API mode
- If `DB_PATH` or `--db` is set → SQLite mode

### Gemini AI Configuration

```dotenv
# Gemini service configuration (used for abstracts and summary)
Gemini_API_KEY="YOUR_GEMINI_API_KEY"
Gemini_BASE_URL="https://generativelanguage.googleapis.com/v1beta/openai/"
# Models per step (supports Gemini 2.5 and 3 series)
Gemini_ABSTRACT_MODEL_ID="gemini-3-flash-preview"
Gemini_SUMMARY_MODEL_ID="gemini-3-pro-preview"
```

### Upload Configuration

```dotenv
# Option 1: rclone (recommended if already configured)
RCLONE_MD_DEST="dropbox:/path/to/markdown"
RCLONE_PDF_DEST="dropbox:/path/to/pdf"

# Option 2: Dropbox API (used if rclone not configured)
DROPBOX_APP_KEY="YOUR_DROPBOX_APP_KEY"
DROPBOX_APP_SECRET="YOUR_DROPBOX_APP_SECRET"
DROPBOX_REFRESH_TOKEN="YOUR_DROPBOX_REFRESH_TOKEN"
```

Ensure the environment variables are correctly set before running any script.

### Upload Setup

You can choose between two upload methods:

#### Option 1: rclone (Recommended)

If you have rclone configured, this is the simpler option as it doesn't require Dropbox API credentials.

1. Install and configure rclone:
   ```bash
   rclone config
   ```
2. Add the destination paths to your `.env` file:
   ```dotenv
   RCLONE_MD_DEST="dropbox:/path/to/markdown"
   RCLONE_PDF_DEST="dropbox:/path/to/pdf"
   ```

When `RCLONE_MD_DEST` or `RCLONE_PDF_DEST` is set, the script will use rclone instead of the Dropbox API.

#### Option 2: Dropbox API

To enable Dropbox uploads, follow these steps to obtain your API credentials:

1.  **Create a Dropbox App**:
    *   Go to the [Dropbox App Console](https://www.dropbox.com/developers/apps) and click **Create app**.
    *   **Choose an API**: Select "Scoped access".
    *   **Choose the type of access**: Select either "App Folder" or "Full Dropbox".
    *   **Name your app**: Give it a unique name (e.g., `ai-news-uploader`).

2.  **Configure App Permissions**:
    *   In your app's settings, go to the **Permissions** tab.
    *   Under `Files and Folders`, check `files.content.read` and `files.content.write`.
    *   Click **Submit** to save changes.

3.  **Generate Refresh Token**:
    *   Navigate back to the **Settings** tab to find your **App key** and **App secret**.
    *   Run the helper script. Make sure you are in the project's root directory:
        ```bash
        python3 get_refresh_token.py
        ```
    *   When prompted, enter your **App key** and **App secret**.
    *   The script will provide a URL. Open it in your browser, authorize the app, and copy the **authorization code** that Dropbox provides.
    *   Paste the code back into your terminal.

4.  **Update `.env` file**:
    *   The script will output the `DROPBOX_APP_KEY`, `DROPBOX_APP_SECRET`, and a long-lived `DROPBOX_REFRESH_TOKEN`.
    *   Copy these three lines into your `.env` file.

After this setup, the script will be able to upload files to Dropbox without your token expiring.

## Project Structure

```
.
├── 0_sqlite_to_articles.py         # Extract articles from FreshRSS database
├── 1_article_to_abstract_md.py     # Generate article abstracts in Markdown
├── 2_abstract_to_summary.py        # Compile abstracts into a weekly summary
├── 3_md_to_pdf.py                  # Convert Markdown to PDF
├── 4_save_to_dropbox.py            # Upload files to Dropbox
├── get_refresh_token.py            # Helper script to get Dropbox refresh token
├── run.sh                          # Run the entire pipeline with one command
├── pyproject.toml                  # Project dependencies (uv/pip)
├── articles/                       # Stores extracted article text files
├── abstract_md/                    # Stores generated abstract Markdown files
├── deliverable/                    # Stores summary Markdown and PDF files
├── system_prompt/                  # Stores AI prompt templates
└── README.md                       # Project documentation
```

## Usage

### Run Individual Steps

1. Extract articles (creates `articles/articles_YYYYMMDD_HHMM` directory):
   ```bash
   # SQLite mode
   uv run python 0_sqlite_to_articles.py --db <DB_PATH> [--hours <hours>] [--end-hour <end_hour>]

   # API mode (uses FRESHRSS_API_* env vars)
   uv run python 0_sqlite_to_articles.py --api [--hours <hours>] [--end-hour <end_hour>]
   ```
2. Generate article abstracts (creates `abstract_md/abstract_md_YYYYMMDD_HHMMSS.md`):
   ```bash
   uv run python 1_article_to_abstract_md.py <articles_list.txt> [--output-md <OUTPUT_MD>]
   ```
3. Generate weekly summary (creates `deliverable/AI News Update YYYY MM DD.md`):
   ```bash
   uv run python 2_abstract_to_summary.py --input-md <ABSTRACT_MD> [--output-md <OUTPUT_MD>]
   ```
4. Convert summary Markdown to PDF:
   ```bash
   uv run python 3_md_to_pdf.py <SUMMARY_MD>
   ```

### Run Full Pipeline

Make the pipeline script executable and run:

```bash
chmod +x run.sh

# API mode (recommended for remote FreshRSS)
./run.sh --api [--hours <hours>] [--end-hour <end_hour>]

# SQLite mode
./run.sh --db <DB_PATH> [--hours <hours>] [--end-hour <end_hour>]

# Auto-detect mode (uses .env configuration)
./run.sh
```

**What happens on each run:**
1. **Cleanup**: Removes old files, keeping only the last 12 runs
2. **Extract**: Fetches articles from FreshRSS (API or SQLite)
3. **Abstract**: Generates per-article abstracts using Gemini
4. **Summarize**: Compiles weekly summary
5. **Convert**: Creates PDF from Markdown
6. **Upload**: Sends files to cloud storage

## Notes

- Ensure all required environment variables are set in the `.env` file.
- Processing a large number of articles may take some time.
- Comply with website terms of service when crawling or extracting content.
- The `--api` flag forces API mode even if `DB_PATH` is set.
