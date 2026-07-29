"""
Fetch latest price + news for tickers needing Update Log, output JSON for analysis.
Uses yfinance only (free, no rate limits).
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.data_engine import get_quote, get_price_history, get_news
from datetime import date, timedelta

# Tickers that need updates (reports dated <= 07-24, excluding today's updates)
TICKERS = [
    "ALGM", "AMZN", "AVGO", "CGNX", "CRCL", "DELL",
    "GOOGL", "KO", "MRVL", "MSFT", "NVDA", "ONDS",
    "ORCL", "PLTR", "RKLB", "SKHYV", "SMCI", "SPCX"
]

today = date.today()
one_week_ago = today - timedelta(days=7)
one_month_ago = today - timedelta(days=30)

results = {}

for ticker in TICKERS:
    print(f"Fetching {ticker}...")
    info = {"ticker": ticker}

    # Quote
    try:
        q = get_quote(ticker)
        info["price"] = q.get("price") if q else None
        info["change_pct"] = q.get("change_percent") if q else None
    except Exception as e:
        print(f"  Quote error: {e}")
        info["price"] = None
        info["change_pct"] = None

    # Price history for 1-week and 1-month
    try:
        hist = get_price_history(ticker, start=one_month_ago.isoformat(), end=today.isoformat())
        if hist is not None and not hist.empty:
            closes = hist["close"]
            if len(closes) >= 2:
                latest_close = closes.iloc[-1]
                # 1-week change
                week_ago_idx = max(0, len(closes) - 6)
                week_close = closes.iloc[week_ago_idx]
                info["week_change"] = round((latest_close - week_close) / week_close * 100, 1)
                # 1-month change
                month_close = closes.iloc[0]
                info["month_change"] = round((latest_close - month_close) / month_close * 100, 1)
                # 52-week high
                info["high_52w"] = round(float(hist["high"].max()), 2)
                info["low_52w"] = round(float(hist["low"].min()), 2)
                # Recent range
                info["week_high"] = round(float(hist["high"].iloc[-6:].max()), 2)
                info["week_low"] = round(float(hist["low"].iloc[-6:].min()), 2)
            else:
                info["week_change"] = None
                info["month_change"] = None
        else:
            info["week_change"] = None
            info["month_change"] = None
    except Exception as e:
        print(f"  History error: {e}")
        info["week_change"] = None
        info["month_change"] = None

    # News
    try:
        news = get_news(ticker, limit=5)
        if news is not None and not news.empty:
            headlines = []
            for _, row in news.head(5).iterrows():
                headlines.append(str(row.get("title", ""))[:120])
            info["news"] = headlines
        else:
            info["news"] = []
    except Exception as e:
        print(f"  News error: {e}")
        info["news"] = []

    results[ticker] = info
    print(f"  Price: ${info['price']}, 1W: {info['week_change']}%, 1M: {info['month_change']}%")

# Output as JSON
output_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "processed", "update_log_data.json")
os.makedirs(os.path.dirname(output_path), exist_ok=True)
with open(output_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2, default=str)

print(f"\nSaved to {output_path}")
print(f"Total: {len(results)} tickers")
