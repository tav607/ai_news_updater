# CLAUDE.md

This file provides guidance for Claude Code when working with this repository.

## Project Overview

AI News Summary Tool - A pipeline that extracts AI news from FreshRSS, generates abstracts and summaries using Gemini, and uploads results to cloud storage.

## Pipeline Steps

```
0_sqlite_to_articles.py  → Extract articles from FreshRSS SQLite DB
1_article_to_abstract_md.py  → Generate per-article abstracts (Gemini Flash)
2_abstract_to_summary.py  → Compile weekly summary (Gemini Pro)
3_md_to_pdf.py  → Convert Markdown to PDF
4_save_to_dropbox.py  → Upload via rclone or Dropbox API
```

Run full pipeline: `./run.sh [--db <path>] [--hours N] [--end-hour HH]`

## Key Configuration (.env)

| Variable | Purpose |
|----------|---------|
| `DB_PATH` | FreshRSS SQLite database path |
| `ALLOWED_FEED_NAMES` | Comma-separated feed names to include |
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

### Test API connection
```bash
source .venv/bin/activate
python -c "from openai import OpenAI; from dotenv import load_dotenv; import os; load_dotenv(); c=OpenAI(api_key=os.getenv('Gemini_API_KEY'),base_url=os.getenv('Gemini_BASE_URL')); print(c.chat.completions.create(model='gemini-3-flash-preview',messages=[{'role':'user','content':'hi'}]).choices[0].message.content)"
```

### Test rclone upload
```bash
source .venv/bin/activate
python 4_save_to_dropbox.py /path/to/test.md
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
