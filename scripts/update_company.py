"""
update_company.py — Fetch live company fundamentals via OpenBB and regenerate .md files.

Usage:
    python scripts/update_company.py --ticker NVDA
    python scripts/update_company.py --all
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_engine import fetch_all_for_ticker
from src.markdown import generate_company_md


def main() -> None:
    parser = argparse.ArgumentParser(description="Update company fundamental data")
    parser.add_argument("--ticker", type=str, help="Single ticker to update")
    parser.add_argument("--all", action="store_true", help="Update all tracked companies")
    parser.add_argument("--days", type=int, default=7, help="Days of news to include")
    args = parser.parse_args()

    tracked = ["NVDA", "AVGO", "ORCL"]

    tickers: list[str] = []
    if args.all:
        tickers = tracked
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        print("Usage: python update_company.py [--ticker NVDA] [--all]")
        sys.exit(1)

    companies_dir = Path(__file__).resolve().parent.parent / "companies"
    companies_dir.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"  Updating {ticker}...")
        print(f"{'='*60}")

        # Fetch ALL data via the unified engine
        data = fetch_all_for_ticker(ticker, days_of_news=args.days)

        # Generate the complete company markdown
        md_content = generate_company_md(ticker, data)

        # Write to companies/{TICKER}.md
        md_path = companies_dir / f"{ticker}.md"
        md_path.write_text(md_content, encoding="utf-8")

        # Summary
        profile = data.get("profile")
        name = "Unknown"
        if profile is not None and not profile.empty:
            name = profile.iloc[0].get("name", ticker)

        income = data.get("income")
        rev_str = "—"
        if income is not None and not income.empty and "total_revenue" in income.columns:
            rev = income.iloc[0]["total_revenue"]
            if rev and not (hasattr(rev, 'isna') and rev.isna()):
                rev_str = f"${rev:,.0f}M"

        print(f"  ✅ {name} ({ticker}) — Revenue: {rev_str}")
        print(f"  📄 Saved to {md_path}")

    print(f"\n✅ Done. Updated {len(tickers)} company file(s).")


if __name__ == "__main__":
    main()
