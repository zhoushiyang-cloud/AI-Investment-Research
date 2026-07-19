"""
update_news.py — Aggregate latest news for tracked companies via OpenBB.

Usage:
    python scripts/update_news.py --ticker NVDA [--days 7]
    python scripts/update_news.py --all [--days 30]
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_engine import get_news


def save_news_json(ticker: str, news_df) -> Path | None:
    """Save news articles as JSON to data/processed/.

    Args:
        ticker: Stock ticker symbol.
        news_df: DataFrame from get_news().

    Returns:
        Path to saved file, or None if no articles.
    """
    if news_df is None or news_df.empty:
        return None

    data_dir = Path(__file__).resolve().parent.parent / "data" / "processed"
    data_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    output_path = data_dir / f"{ticker}_news_{today}.json"

    # Convert DataFrame to list of dicts, handling non-serializable types
    records = []
    for _, row in news_df.iterrows():
        rec = {}
        for col in news_df.columns:
            val = row[col]
            if hasattr(val, 'isoformat'):
                val = val.isoformat()
            elif hasattr(val, 'strftime'):
                val = val.strftime("%Y-%m-%d %H:%M")
            elif hasattr(val, 'item'):
                val = val.item()
            else:
                try:
                    json.dumps(val)
                except (TypeError, ValueError):
                    val = str(val)
            rec[col] = val
        records.append(rec)

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

    return output_path


def append_news_to_md(ticker: str, news_df) -> int:
    """Append recent news section to the company markdown file.

    Args:
        ticker: Stock ticker symbol.
        news_df: DataFrame from get_news().

    Returns:
        Number of articles appended.
    """
    if news_df is None or news_df.empty:
        return 0

    companies_dir = Path(__file__).resolve().parent.parent / "companies"
    md_path = companies_dir / f"{ticker.upper()}.md"

    if not md_path.exists():
        print(f"  ⚠️  {md_path} does not exist — run update_company.py first.")
        return 0

    today = datetime.now().strftime("%Y-%m-%d")
    lines = [f"\n\n## News Summary ({today})\n"]

    count = 0
    for _, article in news_df.head(15).iterrows():
        title = article.get("title", "N/A")
        url = article.get("url", "#")
        source = article.get("source", "N/A")
        date_val = article.get("date", "")
        lines.append(f"- [{title}]({url}) — *{source}* ({date_val})\n")
        count += 1

    with open(md_path, "a", encoding="utf-8") as f:
        f.writelines(lines)

    return count


def main() -> None:
    parser = argparse.ArgumentParser(description="Aggregate latest news for tracked companies")
    parser.add_argument("--ticker", type=str, help="Single ticker to fetch news for")
    parser.add_argument("--all", action="store_true", help="Fetch news for all tracked companies")
    parser.add_argument("--days", type=int, default=7, help="Days to look back (default: 7)")
    parser.add_argument("--limit", type=int, default=30, help="Max articles per ticker (default: 30)")
    args = parser.parse_args()

    tracked = ["NVDA", "AVGO", "ORCL"]

    tickers: list[str] = []
    if args.all:
        tickers = tracked
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        print("Usage: python update_news.py [--ticker NVDA] [--all] [--days 7]")
        sys.exit(1)

    end = datetime.now()
    start = end - timedelta(days=args.days)

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"  News for {ticker} ({args.days}d: {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')})")
        print(f"{'='*60}")

        news_df = get_news(
            ticker,
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            limit=args.limit,
        )

        if news_df is None or news_df.empty:
            print(f"  ℹ️  No news found for {ticker}.")
            continue

        print(f"  [News] Fetched {len(news_df)} articles")

        # Save JSON
        json_path = save_news_json(ticker, news_df)
        if json_path:
            print(f"  [Save] Saved to {json_path}")

        # Append to company .md
        appended = append_news_to_md(ticker, news_df)
        print(f"  [Append] Appended {appended} articles to companies/{ticker}.md")

    print(f"\n✅ Done.")


if __name__ == "__main__":
    main()
