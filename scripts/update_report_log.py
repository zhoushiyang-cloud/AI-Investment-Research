"""
update_report_log.py — Append REAL short-term updates to existing reports.

For each tracked company: fetches recent price action + K-line trend + uses
DeepSeek to write a concise analysis based on actual data. Appends as an
Update Log entry to the latest report.

Usage:
    python scripts/update_report_log.py --ticker SMCI       # single company
    python scripts/update_report_log.py --count 5            # update 5 oldest
    python scripts/update_report_log.py --all                # all tracked
    python scripts/update_report_log.py --consolidate        # keep only latest per ticker
"""

import re
import sys
import time
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
COMPANIES_DIR = PROJECT_ROOT / "companies"

TRACKED = sorted([f.stem for f in COMPANIES_DIR.glob("*.md")])


# ── Data Gathering ──────────────────────────────────────────────────────────

def get_price_context(ticker: str) -> dict:
    """Get recent price data from K-line history."""
    try:
        from src.config import setup_openbb_credentials
        setup_openbb_credentials()
        from src.data_engine import get_price_history
    except Exception:
        return {}
    warnings.filterwarnings("ignore")
    try:
        hist = get_price_history(ticker, start="2026-07-01")
        if hist.empty or "close" not in hist.columns:
            return {}
        closes = hist["close"].values
        latest = float(closes[-1])
        # 1-week, 2-week, 1-month changes
        wk1 = float(closes[-6]) if len(closes) >= 6 else float(closes[0])
        wk2 = float(closes[-11]) if len(closes) >= 11 else float(closes[0])
        mo1 = float(closes[0])
        high = float(hist["high"].max())
        low = float(hist["low"].min())
        return {
            "price": round(latest, 2),
            "chg_1w": round(((latest - wk1) / wk1) * 100, 1),
            "chg_2w": round(((latest - wk2) / wk2) * 100, 1),
            "chg_1m": round(((latest - mo1) / mo1) * 100, 1),
            "high": round(high, 2),
            "low": round(low, 2),
        }
    except Exception:
        return {}


def fetch_company_news(ticker: str) -> str:
    """Fetch recent news headlines from yfinance (free)."""
    try:
        from src.data_engine import get_news
        news = get_news(ticker, limit=10)
        if news is not None and not news.empty:
            headlines = []
            for _, row in news.head(8).iterrows():
                title = str(row.get("title", ""))[:120]
                if title:
                    headlines.append(f"- {title}")
            return "\n".join(headlines) if headlines else "No recent news found."
        return "No recent news found."
    except Exception:
        return "News unavailable."


def get_report_rating(ticker: str) -> str:
    """Extract current rating from latest report."""
    report = find_latest_report(ticker)
    if not report:
        return "N/A"
    text = report.read_text(encoding="utf-8")
    m = re.search(r'\*\*(BUY|SELL|HOLD|Buy|Hold|Sell)\*\*', text)
    if m:
        return m.group(1).upper()
    m = re.search(r'Rating:\s*\*?\*?(BUY|SELL|HOLD)', text, re.IGNORECASE)
    return m.group(1).upper() if m else "N/A"


# ── Report Management ──────────────────────────────────────────────────────

def find_latest_report(ticker: str) -> Path | None:
    """Find the latest English report for a ticker."""
    candidates = sorted(
        REPORTS_DIR.glob(f"{ticker}_report_*.md"), reverse=True)
    for c in candidates:
        if "_cn" not in c.stem and "_prompt" not in c.stem:
            return c
    return None


def consolidate_reports(ticker: str) -> int:
    """Keep only the latest EN + CN report per ticker, delete older versions."""
    en_reports = sorted([
        f for f in REPORTS_DIR.glob(f"{ticker}_report_*.md")
        if "_cn" not in f.stem and "_prompt" not in f.stem
    ], reverse=True)
    cn_reports = sorted([
        f for f in REPORTS_DIR.glob(f"{ticker}_report_*_cn.md")
    ], reverse=True)

    deleted = 0
    for f in en_reports[1:]:
        f.unlink()
        deleted += 1
    for f in cn_reports[1:]:
        f.unlink()
        deleted += 1
    return deleted


# ── DeepSeek Analysis ──────────────────────────────────────────────────────

def generate_analysis(ticker: str, price: dict, news_text: str) -> str:
    """Use DeepSeek to write a concise update analysis."""
    from src.config import load_config
    from openai import OpenAI

    config = load_config()
    api_key = config.get("deepseek", {}).get("api_key", "")
    if not api_key:
        return _fallback_analysis(ticker, price, news_text)

    model = config.get("deepseek", {}).get("model", "deepseek-chat")
    base_url = config.get("deepseek", {}).get("base_url", "https://api.deepseek.com/v1")

    rating = get_report_rating(ticker)
    prompt = f"""Write a SHORT investment update for {ticker} (current rating: {rating}).

Price data:
- Current: ${price.get('price', '?')}
- 1-week change: {price.get('chg_1w', '?')}%
- 2-week change: {price.get('chg_2w', '?')}%
- July range: ${price.get('low', '?')} - ${price.get('high', '?')}

Recent news:
{news_text[:800]}

Write in this EXACT format (keep it brief, factual, no fluff):

> [!tip] Recent Developments
> - **Price Action:** 1-2 sentences on recent price movement and what's driving it
> - **Key News:** 1-2 most important recent developments affecting the stock
> - **Peer/Sector Context:** 1 sentence on how peers or the sector are performing
> - **Short-Term Outlook:** 1-2 sentences on what to watch in the coming 1-2 weeks

> [!quote] Rating Status
> **{rating} Maintained** — [1 sentence on whether the thesis is intact and what would change it].
> Next catalyst: [earnings date or major event if known, otherwise 'Monitor macro and sector trends'].

Output ONLY the callout blocks above. No preamble."""

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        resp = client.chat.completions.create(
            model=model, messages=[{"role": "user", "content": prompt}],
            max_tokens=600, temperature=0.4,
        )
        return resp.choices[0].message.content.strip()
    except Exception:
        return _fallback_analysis(ticker, price, news_text)


def _fallback_analysis(ticker: str, price: dict, news_text: str) -> str:
    """Generate a basic analysis without LLM."""
    p = price.get("price", "?")
    chg = price.get("chg_1w", 0)
    direction = "up" if chg > 0 else "down"
    return f"""> [!tip] Recent Developments
> - **Price Action:** {ticker} at ${p} ({chg:+.1f}% over the past week), trading within a July range of ${price.get('low', '?')}-${price.get('high', '?')}.
> - **Key News:** See headlines above for recent developments.
> - **Peer/Sector Context:** Monitor peer movements and sector ETF flows for context.
> - **Short-Term Outlook:** Watch for upcoming earnings, macro data, and sector rotation signals.
>
> > [!quote] Rating Status
> **Rating Maintained** — thesis unchanged pending material news.
> Next catalyst: Monitor for upcoming events."""


# ── Append Logic ───────────────────────────────────────────────────────────

def build_update_entry(ticker: str, price: dict, analysis: str) -> str:
    """Build the full update log entry."""
    today = datetime.now().strftime("%Y-%m-%d")
    p = price.get("price", "?")
    chg_1w = price.get("chg_1w", 0)
    chg_1m = price.get("chg_1m", 0)

    entry = f"""
---

## 📝 Update Log

### {today}

| Metric | Value |
|---|---|
| **Price** | ${p} |
| **1-Week** | {chg_1w:+.1f}% |
| **1-Month** | {chg_1m:+.1f}% |

{analysis}

"""
    return entry


def append_to_report(report_path: Path, entry: str) -> bool:
    """Append or insert update log entry."""
    content = report_path.read_text(encoding="utf-8")

    # Clean any existing blank/placeholder update logs
    content = re.sub(
        r'\n---\n\n## 📝 Update Log\n\n### \d{4}-\d{2}-\d{2}\n.*?(?=\n> \[!note\]|$)',
        '', content, flags=re.DOTALL
    )

    if "## 📝 Update Log" in content:
        # Append after existing entries (before appendix)
        marker = "## 📝 Update Log\n"
        idx = content.index(marker) + len(marker)
        next_section = content.find("\n> [!note]", idx)
        if next_section == -1:
            next_section = content.rfind("\n---\n")
        if next_section == -1:
            next_section = len(content)
        entry_body = entry.replace("## 📝 Update Log\n\n", "")
        new_content = content[:idx] + "\n" + entry_body + content[next_section:]
    else:
        # First time
        appendix = content.rfind("📋 Financial Data Appendix")
        if appendix >= 0:
            note_start = content.rfind("> [!note]", 0, appendix)
            idx = note_start if note_start >= 0 else appendix
        else:
            idx = content.rfind("\n---\n")
        if idx == -1:
            idx = len(content)
        new_content = content[:idx].rstrip() + "\n" + entry + content[idx:]

    report_path.write_text(new_content, encoding="utf-8")
    return True


# ── Main ───────────────────────────────────────────────────────────────────

def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Append real update logs to reports")
    parser.add_argument("--ticker", type=str, help="Single ticker")
    parser.add_argument("--count", type=int, default=0, help="Update N oldest")
    parser.add_argument("--all", action="store_true", help="Update all tracked")
    parser.add_argument("--consolidate", action="store_true", help="Delete old report versions, keep latest only")
    args = parser.parse_args()

    # Consolidation
    if args.consolidate:
        total = 0
        for t in TRACKED:
            d = consolidate_reports(t)
            if d:
                print(f"  {t}: removed {d} old versions")
                total += d
        print(f"\n  Total removed: {total} old report files")
        return

    # Determine tickers
    tickers: list[str] = []
    if args.ticker:
        tickers = [args.ticker.upper()]
    elif args.all:
        tickers = TRACKED
    elif args.count > 0:
        # Sort by oldest update
        from scripts.batch_update_reports import load_state
        state = load_state()
        def sort_key(t):
            last = state.get(t, {}).get("last_updated", "2000-01-01")
            return (last, t)
        tickers = sorted(TRACKED, key=sort_key)[:args.count]
    else:
        print("Usage: update_report_log.py [--ticker NVDA] [--count 5] [--all] [--consolidate]")
        sys.exit(1)

    for ticker in tickers:
        report = find_latest_report(ticker)
        if not report:
            print(f"  [{ticker}] No report — skipping")
            continue

        print(f"  [{ticker}] Fetching data...", end=" ", flush=True)
        price = get_price_context(ticker)
        news = fetch_company_news(ticker)
        print(f"${price.get('price', '?')}", end=" ", flush=True)

        print("DeepSeek...", end=" ", flush=True)
        analysis = generate_analysis(ticker, price, news)
        entry = build_update_entry(ticker, price, analysis)
        if append_to_report(report, entry):
            print("✅")
        else:
            print("❌")
        time.sleep(1)


if __name__ == "__main__":
    main()
