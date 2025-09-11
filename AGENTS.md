# Repository Guidelines

## Project Structure & Module Organization
- Root scripts implement a linear pipeline:
  - `0_sqlite_to_articles.py` → extract from FreshRSS DB
  - `1_article_to_abstract_md.py` → per-article abstracts
  - `2_abstract_to_summary.py` → weekly summary
  - `3_md_to_pdf.py` → Markdown → PDF
  - `4_save_to_dropbox.py` → upload to Dropbox
- Helper: `get_refresh_token.py` (Dropbox auth).
- Data/outputs: `articles/`, `abstract_md/`, `deliverable/`.
- Prompts: `system_prompt/`. Config: `.env` (see `.env.example`).

## Build, Test, and Development Commands
- Setup environment (Python 3.7+):
  - `python3 -m venv .venv && source .venv/bin/activate`
  - `pip install -r requirements.txt`
- Run full pipeline:
  - `chmod +x run.sh && ./run.sh [--db <DB_PATH>] [--hours N] [--end-hour HH]`
- Run individual steps (examples):
  - `python 0_sqlite_to_articles.py --db <DB_PATH> --hours 24`
  - `python 1_article_to_abstract_md.py <articles_list.txt> --output-md abstract_md/out.md`
  - `python 2_abstract_to_summary.py --input-md abstract_md/out.md`
  - `python 3_md_to_pdf.py "deliverable/AI News Update YYYY MM DD.md"`

## Coding Style & Naming Conventions
- Python only; use 4-space indentation, UTF-8, Unix newlines.
- Naming: `snake_case` for functions/variables, `UPPER_SNAKE_CASE` for constants.
- Scripts follow `N_description.py` ordering; prefer adding reusable functions over inline script code.
- Keep prints concise; do not log secrets. If adding logging, use `logging` with INFO default.

## Testing Guidelines
- No formal suite yet. Prefer extracting logic into functions so it’s testable.
- Add tests under `tests/` with `pytest`; name files `test_*.py`.
- Examples: `pytest -q` for quick run; aim to cover parsing, filtering, and file emit paths.

## Commit & Pull Request Guidelines
- Commit messages: brief imperative subject (≤72 chars), optional body with rationale.
  - Example: `extract: filter by allowed feed names`.
- PRs should include:
- Summary of changes and motivation, sample commands or outputs.
- Any `.env` additions/changes (document in `.env.example`).
- Screenshots for PDF/Dropbox changes when useful.
- Checklist: passes `python -m compileall .`, basic run of changed step(s).

## Security & Configuration Tips
- Never commit secrets; keep `.env` local. Update `.env.example` for new keys.
- Required envs: FreshRSS `DB_PATH`, `ALLOWED_FEED_NAMES`, Gemini keys (`Gemini_API_KEY`, `Gemini_BASE_URL`), and per-step models (`Gemini_ABSTRACT_MODEL_ID`, `Gemini_SUMMARY_MODEL_ID`), plus Dropbox creds.
- AI provider: Gemini via OpenAI-compatible endpoint (`chat.completions`), abstracts use `gemini-2.5-flash`, summary uses `gemini-2.5-pro`.
- Concurrency: abstract generation defaults to 20 threads; optionally tune with `ABSTRACT_MAX_WORKERS` if rate-limited.
- Review outputs in `deliverable/` before upload; rotate tokens if leaked; redact tokens in logs (`cron_log.txt`).
