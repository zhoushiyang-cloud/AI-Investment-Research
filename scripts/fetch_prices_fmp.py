"""Fetch current prices via FMP API (different rate limit bucket than yfinance)."""
import json, urllib.request, time, os

API_KEY = "rzkzlStT5Kd8vg3PTKvrr2z8nSf0ahdj"
TICKERS = ['ALGM','AMZN','AVGO','CGNX','CRCL','DELL','GOOGL','KO','MRVL','MSFT','NVDA','ONDS','ORCL','PLTR','RKLB','SKHYV','SMCI','SPCX']

results = {}
for t in TICKERS:
    try:
        url = f"https://financialmodelingprep.com/api/v3/quote/{t}?apikey={API_KEY}"
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        data = json.loads(urllib.request.urlopen(req, timeout=15).read())
        if data:
            q = data[0]
            results[t] = {
                'price': q.get('price'),
                'change_pct': round(q.get('changesPercentage', 0), 2),
                'day_change': q.get('change'),
                'volume': q.get('volume'),
            }
            print(f"{t}: ${q.get('price')} ({q.get('changesPercentage'):+.1f}%)")
        else:
            results[t] = {'price': None}
            print(f"{t}: No data")
    except Exception as e:
        results[t] = {'price': None}
        print(f"{t}: ERROR - {str(e)[:80]}")
    time.sleep(0.4)

out_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "processed", "prices_fmp.json")
os.makedirs(os.path.dirname(out_path), exist_ok=True)
with open(out_path, "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)
print(f"Saved {len(results)} tickers to {out_path}")
