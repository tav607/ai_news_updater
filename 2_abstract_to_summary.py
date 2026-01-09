#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate final summary from abstract Markdown file using Google Gemini API.
Usage:
    python 2_abstract_to_summary.py --input-md <ABSTRACT_MD> [--output-md <DELIVERABLE_MD>]
"""
import os
import sys
import re
import argparse
import time
from datetime import datetime
from dotenv import load_dotenv

try:
    from openai import OpenAI
except ImportError:
    print("Please install openai sdk: pip install openai")
    sys.exit(1)

def parse_args():
    parser = argparse.ArgumentParser(description="Generate final summary from abstract MD")
    parser.add_argument("--input-md", "-i", required=True, help="Path to abstract markdown file")
    parser.add_argument("--output-md", "-o", help="Path to output deliverable markdown file")
    return parser.parse_args()

def generate_summary(client, model_id, markdown_content):
    MAX_RETRIES = 5
    retry_count = 0
    prompt_path = os.path.join(os.path.dirname(__file__), "system_prompt/summary_prompt.md")
    with open(prompt_path, "r", encoding="utf-8") as f:
        prompt = f.read()
    while retry_count < MAX_RETRIES:
        try:
            completion = client.chat.completions.create(
                model=model_id,
                messages=[
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": markdown_content},
                ],
                temperature=0.5
            )
            return completion.choices[0].message.content
        except Exception as e:
            retry_count += 1
            print(f"Error calling API: {e}, retry {retry_count}/{MAX_RETRIES}")
            time.sleep(1)
    print("Max retries reached, exiting.")
    sys.exit(1)

def clean_abstract_md(content):
    """Clean abstract markdown: remove skip markers and deduplicate articles."""
    lines = content.split('\n')
    cleaned_lines = []
    seen_keys = set()  # Track both titles and URLs
    current_article = []
    current_key = None

    for line in lines:
        # Skip lines containing skip markers
        if '[跳过：' in line or '[跳过:' in line:
            continue

        # Detect article title with URL: ### [...](url)
        url_match = re.match(r'^### \[(.+?)\]\((.+?)\)\s*$', line)
        # Detect article title without URL: ### title
        title_only_match = re.match(r'^### (.+?)\s*$', line) if not url_match else None

        if url_match or title_only_match:
            # Save previous article if exists and not duplicate
            if current_key and current_key not in seen_keys:
                cleaned_lines.extend(current_article)
                seen_keys.add(current_key)

            # Start new article - use URL as key if available, otherwise title
            if url_match:
                url = url_match.group(2).strip()
                current_key = url  # Dedupe by URL
            else:
                current_key = title_only_match.group(1).strip()  # Dedupe by title
            current_article = [line]
        else:
            if current_key is not None:
                current_article.append(line)
            else:
                # Lines before first article header
                cleaned_lines.append(line)

    # Don't forget the last article
    if current_key and current_key not in seen_keys:
        cleaned_lines.extend(current_article)

    # Remove consecutive empty lines (keep at most 2)
    result = '\n'.join(cleaned_lines)
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result.strip()


def main():
    args = parse_args()
    if not os.path.exists(args.input_md):
        print(f"Error: input file '{args.input_md}' does not exist.")
        sys.exit(1)
    with open(args.input_md, "r", encoding="utf-8") as f:
        abstract_md = f.read()

    # Clean abstract: remove skip markers and deduplicate
    abstract_md = clean_abstract_md(abstract_md)
    print(f"Cleaned abstract markdown")
    load_dotenv()
    api_key = os.getenv("Gemini_API_KEY")
    # 模型：优先从 Gemini_SUMMARY_MODEL_ID 读取；未设置则回退到 Gemini_MODEL_ID；仍未设置则默认 gemini-3-pro-preview。
    model_id = os.getenv("Gemini_SUMMARY_MODEL_ID") or os.getenv("Gemini_MODEL_ID") or "gemini-3-pro-preview"
    base_url = os.getenv("Gemini_BASE_URL")
    if not api_key:
        print("Missing Gemini_API_KEY in environment.")
        sys.exit(1)
    if not base_url:
        print("Missing Gemini_BASE_URL in environment.")
        sys.exit(1)
    client = OpenAI(api_key=api_key, base_url=base_url)
    print("Generating summary...")
    summary_text = generate_summary(client, model_id, abstract_md)
    # Prepare deliverable
    deliverable_dir = os.path.join(os.getcwd(), "deliverable")
    os.makedirs(deliverable_dir, exist_ok=True)
    today = datetime.now().strftime("%Y %m %d")
    display_date = datetime.now().strftime("%Y/%m/%d")
    filename = f"AI News Update {today}.md"
    output_path = args.output_md if args.output_md else os.path.join(deliverable_dir, filename)
    deliverable_content = (
        f"# AI News Update - {display_date}\n\n"
        f"## Weekly Summary\n\n{summary_text}\n\n---\n\n"
        f"## News Abstracts\n\n{abstract_md}"
    )
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(deliverable_content)
    print(f"Deliverable saved to {output_path}")
    return output_path

if __name__ == "__main__":
    main() 
