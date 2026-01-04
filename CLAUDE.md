# CLAUDE.md

This file provides guidance for Claude Code when working with this repository.

## Project Overview

AI News Summary Tool - A pipeline that extracts AI news from FreshRSS, generates abstracts and summaries using Gemini, and uploads results to cloud storage.

## Pipeline Steps

```
0_sqlite_to_articles.py  → Extract articles from FreshRSS (API or SQLite)
1_article_to_abstract_md.py  → Generate per-article abstracts (Gemini Flash)
2_abstract_to_summary.py  → Compile weekly summary (Gemini Pro)
3_md_to_pdf.py  → Convert Markdown to PDF
4_save_to_dropbox.py  → Upload via rclone or Dropbox API
```

Run full pipeline: `./run.sh [--db <path>] [--api] [--hours N] [--end-hour HH]`

Package management: `uv` (see pyproject.toml)

**Auto-cleanup**: Each run automatically removes old files, keeping only the last 12 runs.

## Key Configuration (.env)

### Data Source (choose one mode)

**API Mode** (for remote FreshRSS):
| Variable | Purpose |
|----------|---------|
| `FRESHRSS_API_URL` | FreshRSS API endpoint (e.g., `https://rss.example.com/api/greader.php`) |
| `FRESHRSS_API_USER` | FreshRSS username |
| `FRESHRSS_API_PASSWORD` | FreshRSS API password |
| `FRESHRSS_API_CATEGORY` | Category names, comma-separated (e.g., `AI-News,Tech`) |
| `FRESHRSS_API_EXCLUDE_FEEDS` | (Optional) Feed names to exclude, comma-separated |

**SQLite Mode** (for local database):
| Variable | Purpose |
|----------|---------|
| `DB_PATH` | FreshRSS SQLite database path |
| `ALLOWED_FEED_NAMES` | Comma-separated feed names to include |

### Other Configuration
| Variable | Purpose |
|----------|---------|
| `Gemini_API_KEY` | Google Gemini API key |
| `Gemini_ABSTRACT_MODEL_ID` | Model for abstracts (default: `gemini-3-flash-preview`) |
| `Gemini_SUMMARY_MODEL_ID` | Model for summary (default: `gemini-3-pro-preview`) |
| `RCLONE_MD_DEST` | rclone destination for .md files (optional) |
| `RCLONE_PDF_DEST` | rclone destination for .pdf files (optional) |
| `DROPBOX_*` | Dropbox API credentials (fallback if rclone not configured) |

## Upload Logic

Priority: rclone > Dropbox API
- If `RCLONE_MD_DEST` or `RCLONE_PDF_DEST` is set → uses rclone
- Otherwise → uses Dropbox SDK with app key/secret/refresh token

## Code Patterns

- Uses OpenAI SDK with Gemini's OpenAI-compatible endpoint
- Parallel processing with `ThreadPoolExecutor` (configurable via `ABSTRACT_MAX_WORKERS`)
- Rate limiting built into abstract generation
- Output normalization handles various Gemini response formats (markdown fences, etc.)

## Common Tasks

### Test Gemini API connection
```bash
uv run python -c "from openai import OpenAI; from dotenv import load_dotenv; import os; load_dotenv(); c=OpenAI(api_key=os.getenv('Gemini_API_KEY'),base_url=os.getenv('Gemini_BASE_URL')); print(c.chat.completions.create(model='gemini-3-flash-preview',messages=[{'role':'user','content':'hi'}]).choices[0].message.content)"
```

### Test FreshRSS API connection
```bash
uv run python 0_sqlite_to_articles.py --api --hours 24
```

### Test rclone upload
```bash
uv run python 4_save_to_dropbox.py /path/to/test.md
```

## Directory Structure

- `articles/` - Extracted raw articles (timestamped subdirs)
- `abstract_md/` - Generated abstracts
- `deliverable/` - Final MD and PDF output
- `system_prompt/` - AI prompt templates

## Style Guidelines

- Python 3.7+, 4-space indentation, UTF-8
- `snake_case` for functions/variables
- Scripts follow `N_description.py` naming
- Keep prints concise, never log secrets
