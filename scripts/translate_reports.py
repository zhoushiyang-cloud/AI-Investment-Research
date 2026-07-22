"""
translate_reports.py — Batch translate English investment reports to Chinese via DeepSeek API.

Usage:
    python scripts/translate_reports.py --all              # translate all reports
    python scripts/translate_reports.py --ticker SMCI      # translate single report
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from openai import OpenAI
from src.config import load_config


def translate_text(client: OpenAI, model: str, text: str) -> str:
    """Translate English report text to Chinese, preserving markdown structure."""
    prompt = f"""Translate the following investment research report from English to Chinese (Simplified).

CRITICAL RULES:
1. Preserve ALL markdown formatting (callouts, tables, wikilinks, frontmatter) EXACTLY as-is
2. DO NOT translate: ticker symbols, numbers, dates, financial figures, percentages
3. DO NOT translate: [[wikilinks]] like [[NVDA]], [[DELL]]
4. DO NOT translate: markdown syntax like `#critical`, `#near-term`
5. Translate analysis/prose naturally in professional financial Chinese
6. Keep the exact same structure — same headers, same bullet points, same callout blocks

Output the translated report directly with no preamble or commentary.

--- REPORT TO TRANSLATE ---
{text}"""

    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=8192,
            temperature=0.1,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  [Error] DeepSeek API: {e}")
        return ""


def main() -> None:
    parser = argparse.ArgumentParser(description="Translate investment reports to Chinese")
    parser.add_argument("--ticker", type=str, help="Single ticker to translate")
    parser.add_argument("--all", action="store_true", help="Translate all reports")
    args = parser.parse_args()

    config = load_config()
    api_key = config.get("deepseek", {}).get("api_key", "")
    base_url = config.get("deepseek", {}).get("base_url", "https://api.deepseek.com/v1")
    model = config.get("deepseek", {}).get("model", "deepseek-chat")

    if not api_key:
        print("[Error] No DeepSeek API key configured.")
        sys.exit(1)

    client = OpenAI(api_key=api_key, base_url=base_url)

    reports_dir = Path(__file__).resolve().parent.parent / "reports"

    # Find reports to process
    report_files: list[Path] = []
    if args.ticker:
        ticker = args.ticker.upper()
        matches = list(reports_dir.glob(f"{ticker}_report_*.md"))
        # Exclude already-translated Chinese versions
        matches = [m for m in matches if "_cn" not in m.stem]
        report_files = matches
    elif args.all:
        all_reports = sorted(reports_dir.glob("*_report_*.md"))
        report_files = [f for f in all_reports if "_cn" not in f.stem]
    else:
        print("Usage: python translate_reports.py [--ticker NVDA] [--all]")
        sys.exit(1)

    if not report_files:
        print("No reports found to translate.")
        sys.exit(1)

    print(f"Translating {len(report_files)} report(s)...")
    print(f"Model: {model} via {base_url}\n")

    for i, report_path in enumerate(report_files, 1):
        ticker = report_path.stem.split("_")[0]
        cn_path = report_path.parent / report_path.name.replace(".md", "_cn.md")

        # Skip if Chinese version already exists and is newer than the English version
        if cn_path.exists() and cn_path.stat().st_mtime >= report_path.stat().st_mtime:
            print(f"  [{i}/{len(report_files)}] {ticker} — CN already up-to-date, skipping")
            continue

        print(f"  [{i}/{len(report_files)}] {ticker} — translating...")

        text = report_path.read_text(encoding="utf-8")

        # Split: keep frontmatter + appendix intact, translate only analysis sections
        # Strategy: translate the whole thing — the prompt rules ensure fidelity

        translated = translate_text(client, model, text)

        if translated:
            cn_path.write_text(translated, encoding="utf-8")
            print(f"  [{i}/{len(report_files)}] {ticker} — saved to {cn_path.name}")
        else:
            print(f"  [{i}/{len(report_files)}] {ticker} — FAILED")

    print(f"\n[Done] Translation complete.")


if __name__ == "__main__":
    main()
