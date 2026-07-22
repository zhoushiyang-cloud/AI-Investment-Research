---
name: financial-calendar
description: Generate monthly financial calendar with earnings + economic events + AI predictions
metadata:
  type: project
---

When the user asks for "日历", "calendar", "财报日历", or "earnings calendar", run:

```
python scripts/financial_calendar.py --month YYYY-MM --generate-predictions --output all
```

This generates three outputs in `reports/calendar/`:
1. `YYYY-MM_calendar.md` — Obsidian markdown monthly calendar with callouts, calendar grid, weekly detail tables
2. `YYYY-MM_predictions.md` — DeepSeek AI predictions for mega-cap earnings + macro event impact analysis
3. `YYYY-MM_calendar.html` — Interactive HTML calendar with dark mode, filter buttons, tooltips

**Data sources:**
- Nasdaq Earnings API (free, no key): real-time earnings dates, EPS forecasts, surprise history
- FMP API: company profiles and sector enrichment
- DeepSeek API: AI-generated earnings predictions
- Curated economic calendar: FOMC, CPI, GDP, PCE, PPI, Retail Sales, Fed Beige Book

**Features:**
- Filters to ~100 important companies per month (market cap > $10B + all tracked tickers)
- 3-tier classification: 🔥 Mega-Cap ($200B+), ⭐ Large-Cap ($10B+), • Notable
- Color-coded interactive HTML with tooltips
- Tracked company alerts (flags any of our 18 tracked tickers reporting)

**Why:** Manual calendar checking is time-consuming. This automates earnings tracking and provides AI-powered predictions for high-impact events.

**How to apply:** Default month is current month. The script takes ~30-60 seconds to fetch all 30+ days of earnings data from Nasdaq.

Related: [[default-report-generation]]
