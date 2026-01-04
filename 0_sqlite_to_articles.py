#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Extract and format articles from FreshRSS into individual text files.
Supports two modes:
  - API mode: Uses FreshRSS Google Reader API (set FRESHRSS_API_URL)
  - SQLite mode: Reads from local database file (set DB_PATH)

Usage:
    python 0_sqlite_to_articles.py [--db <DB_PATH>] [--hours 168] [--end-hour 18]
"""
import os
import sys
import argparse
import sqlite3
from datetime import datetime, timedelta
from urllib.parse import urljoin, quote
from bs4 import BeautifulSoup
from dotenv import load_dotenv

try:
    import requests
except ImportError:
    requests = None


# ============================================================================
# FreshRSS API Functions
# ============================================================================

def freshrss_api_login(api_url, user, password):
    """
    Authenticate with FreshRSS Google Reader API.
    Returns Auth token on success, None on failure.
    """
    # Ensure api_url ends without slash, then append path
    base_url = api_url.rstrip('/')
    login_url = f"{base_url}/accounts/ClientLogin"
    data = {
        "Email": user,
        "Passwd": password,
    }
    try:
        resp = requests.post(login_url, data=data, timeout=30)
        resp.raise_for_status()
        for line in resp.text.strip().split("\n"):
            if line.startswith("Auth="):
                return line[5:]
        print(f"API login failed: Auth token not found in response")
        return None
    except requests.RequestException as e:
        print(f"API login failed: {e}")
        return None


def freshrss_api_get_articles(api_url, auth_token, category, start_ts, end_ts):
    """
    Fetch articles from FreshRSS API for a specific category within time range.
    Handles pagination via continuation token.
    Returns list of (link, title, content, date, feed_name) tuples.
    """
    # URL encode the category name for the API path
    base_url = api_url.rstrip('/')
    stream_id = f"user/-/label/{quote(category, safe='')}"
    stream_url = f"{base_url}/reader/api/0/stream/contents/{stream_id}"

    headers = {"Authorization": f"GoogleLogin auth={auth_token}"}
    articles = []
    continuation = None

    # Extend ot range by 2 days to avoid missing articles where
    # crawl_time < start_ts but published_time >= start_ts
    ot_with_buffer = start_ts - (2 * 24 * 3600)

    while True:
        # Note: FreshRSS nt param doesn't work reliably, so we only use ot
        # and filter by start_ts/end_ts in code
        params = {
            "n": 1000,  # max items per request
            "ot": ot_with_buffer,  # fetch with buffer, filter precisely in code
            "output": "json",
        }
        if continuation:
            params["c"] = continuation

        try:
            resp = requests.get(stream_url, headers=headers, params=params, timeout=60)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as e:
            print(f"API request failed: {e}")
            break
        except ValueError as e:
            print(f"API response parse failed: {e}")
            break

        items = data.get("items", [])
        for item in items:
            date_val = item.get("published", 0)

            # Filter by time range (since FreshRSS time params are unreliable)
            if date_val < start_ts or date_val > end_ts:
                continue

            link = ""
            if item.get("canonical"):
                link = item["canonical"][0].get("href", "")
            elif item.get("alternate"):
                link = item["alternate"][0].get("href", "")

            title = item.get("title", "")
            content = item.get("summary", {}).get("content", "")

            # Extract feed name from origin
            feed_name = item.get("origin", {}).get("title", "Unknown")

            articles.append((link, title, content, date_val, feed_name))

        # Check for more pages - stop if no more items or all items are beyond end_ts
        continuation = data.get("continuation")
        if not continuation or not items:
            break
        # Also stop if all items in this batch are after end_ts (no point continuing)
        if all(item.get("published", 0) > end_ts for item in items):
            break

    return articles

def parse_args():
    parser = argparse.ArgumentParser(description="Extract and format articles from FreshRSS (API or SQLite)")
    parser.add_argument("--db", help="Path to FreshRSS SQLite database file (overrides DB_PATH in .env)")
    parser.add_argument("--hours", type=int, default=168, help="Time window in hours (default: 168)")
    parser.add_argument("--end-hour", type=int, default=17, help="End hour of day (0-23) for the window end (default: 17)")
    parser.add_argument("--api", action="store_true", help="Force API mode even if DB_PATH is set")
    return parser.parse_args()


def fetch_articles_from_sqlite(db_path, start_ts, end_ts):
    """Fetch articles from SQLite database."""
    if not os.path.exists(db_path):
        print(f"Error: database file '{db_path}' not found.")
        sys.exit(1)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Load query conditions from environment variables
    allowed_feed_names_str = os.getenv("ALLOWED_FEED_NAMES")
    wechat_category_id = os.getenv("WECHAT_CATEGORY_ID", "0")
    wechat_url_pattern = os.getenv("WECHAT_URL_PATTERN_CONTAINS", "wechat")

    if not allowed_feed_names_str:
        print("Error: ALLOWED_FEED_NAMES must be set for SQLite mode.")
        sys.exit(1)

    allowed_feed_names = [name.strip() for name in allowed_feed_names_str.split(',') if name.strip()]
    if not allowed_feed_names:
        print("Error: ALLOWED_FEED_NAMES resulted in empty list.")
        sys.exit(1)

    feed_name_conditions = " OR ".join(["f.name = ?"] * len(allowed_feed_names))
    query_template = f'''
    SELECT e.link, e.title, e.content, e.date, f.name
    FROM entry e
    JOIN feed f ON e.id_feed = f.id
    WHERE e.date BETWEEN ? AND ?
      AND (
        {feed_name_conditions}
        OR (f.category = ? AND f.url LIKE ?)
      )
    ORDER BY e.date DESC
    '''
    params = [start_ts, end_ts] + allowed_feed_names + [wechat_category_id, f'%{wechat_url_pattern}%']

    cursor.execute(query_template, tuple(params))
    rows = cursor.fetchall()
    conn.close()
    return rows


def fetch_articles_from_api(start_ts, end_ts):
    """Fetch articles from FreshRSS API."""
    if requests is None:
        print("Error: 'requests' library required for API mode. Install with: pip install requests")
        sys.exit(1)

    api_url = os.getenv("FRESHRSS_API_URL")
    api_user = os.getenv("FRESHRSS_API_USER")
    api_password = os.getenv("FRESHRSS_API_PASSWORD")
    api_categories_str = os.getenv("FRESHRSS_API_CATEGORY")

    missing = []
    if not api_url:
        missing.append("FRESHRSS_API_URL")
    if not api_user:
        missing.append("FRESHRSS_API_USER")
    if not api_password:
        missing.append("FRESHRSS_API_PASSWORD")
    if not api_categories_str:
        missing.append("FRESHRSS_API_CATEGORY")

    if missing:
        print(f"Error: Missing environment variables for API mode: {', '.join(missing)}")
        sys.exit(1)

    # Support multiple categories (comma-separated)
    categories = [c.strip() for c in api_categories_str.split(',') if c.strip()]
    if not categories:
        print("Error: FRESHRSS_API_CATEGORY resulted in empty list.")
        sys.exit(1)

    print(f"Authenticating with FreshRSS API at {api_url}...")
    auth_token = freshrss_api_login(api_url, api_user, api_password)
    if not auth_token:
        print("Error: Failed to authenticate with FreshRSS API.")
        sys.exit(1)

    # Fetch articles from all categories
    all_articles = []
    for category in categories:
        print(f"Fetching articles from category '{category}'...")
        articles = freshrss_api_get_articles(api_url, auth_token, category, start_ts, end_ts)
        all_articles.extend(articles)
        print(f"  Found {len(articles)} articles in '{category}'")

    # Filter out excluded feeds
    exclude_feeds_str = os.getenv("FRESHRSS_API_EXCLUDE_FEEDS", "")
    if exclude_feeds_str:
        exclude_feeds = set(f.strip() for f in exclude_feeds_str.split(',') if f.strip())
        before_count = len(all_articles)
        # feed_name is index 4 in tuple (link, title, content, date, feed_name)
        all_articles = [a for a in all_articles if a[4] not in exclude_feeds]
        excluded_count = before_count - len(all_articles)
        if excluded_count > 0:
            print(f"Excluded {excluded_count} articles from feeds: {', '.join(exclude_feeds)}")

    # Sort by date descending (index 3 is date_val)
    all_articles.sort(key=lambda x: x[3], reverse=True)
    return all_articles


def main():
    load_dotenv()
    args = parse_args()

    # Compute time window
    now = datetime.now()
    if now.hour >= args.end_hour:
        end_dt = now.replace(hour=args.end_hour, minute=0, second=0, microsecond=0)
    else:
        end_dt = (now - timedelta(days=1)).replace(hour=args.end_hour, minute=0, second=0, microsecond=0)
    start_dt = end_dt - timedelta(hours=args.hours)
    start_ts = int(start_dt.timestamp())
    end_ts = int(end_dt.timestamp())
    print(f"Extracting entries from {start_dt} to {end_dt} (timestamps {start_ts}-{end_ts})")

    # Determine mode: API or SQLite
    api_url = os.getenv("FRESHRSS_API_URL")
    db_path = args.db or os.getenv("DB_PATH")

    if args.api or (api_url and not db_path):
        # API mode
        print("Using API mode")
        rows = fetch_articles_from_api(start_ts, end_ts)
    elif db_path:
        # SQLite mode
        print("Using SQLite mode")
        rows = fetch_articles_from_sqlite(db_path, start_ts, end_ts)
    else:
        print("Error: No data source configured.")
        print("Set FRESHRSS_API_URL for API mode, or DB_PATH/--db for SQLite mode.")
        sys.exit(1)

    if not rows:
        print("No entries found in the specified time window.")
        sys.exit(0)

    # Prepare output directory based on current timestamp
    base_dir = "articles"
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    output_dir = os.path.join(base_dir, f"articles_{timestamp}")
    os.makedirs(output_dir, exist_ok=True)
    list_file = os.path.join(output_dir, "successful_articles.txt")

    # Write each article as a text file and record the path
    with open(list_file, "w", encoding="utf-8") as list_f:
        for idx, (link, title, content, date_val, feed_name) in enumerate(rows, start=1):
            file_name = f"article_{idx}.txt"
            file_path = os.path.join(output_dir, file_name)
            # Clean HTML content
            soup = BeautifulSoup(content or "", "html.parser")
            text = soup.get_text().strip()
            # Format date
            try:
                dt_str = datetime.fromtimestamp(date_val).strftime("%Y年%m月%d日")
            except Exception:
                dt_str = str(date_val)
            # Write file
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(link + "\n\n")
                f.write(title + "\n\n")
                f.write(f"{feed_name} {dt_str}" + "\n\n")
                f.write(text)
            list_f.write(file_path + "\n")

    print(f"Extracted {len(rows)} articles. List file: {list_file}")


if __name__ == "__main__":
    main() 