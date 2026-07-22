---
name: update-all-reports
description: Update all existing company reports with latest data and news
metadata:
  type: project
---

When the user says "更新所有研报" or "update all reports", run the full 3-step pipeline for every company that has an existing file in `companies/`:

1. For each `companies/{TICKER}.md` file, run:
   - `python scripts/update_company.py --ticker {TICKER}` — refresh financials
   - `python scripts/valuation.py --ticker {TICKER} --all-models --sensitivity` — re-run valuation
   - `python scripts/generate_report.py --ticker {TICKER} --provider deepseek` — regenerate AI report

2. Process in order of importance: NVDA, AVGO, ORCL (core tracked), then others alphabetically

3. If orchestrate.py works (no GBK error), use `python scripts/orchestrate.py --all --with-reports --sensitivity` as a shortcut

4. Each report overwrites the existing one with today's date

**Current tracked companies:** NVDA, AVGO, ORCL, ALGM, AMZN, CGNX, GOOGL, MSFT, TSLA, RKLB, SPCX, MRVL

**Why:** USAGE.md defines `orchestrate.py --all` as the daily/weekly routine. Reports degrade over time as prices move and new data arrives. A full refresh ensures all reports reflect current financials and market conditions.

**How to apply:** Use `PYTHONIOENCODING=utf-8` prefix on Windows. Process companies sequentially (API rate limits). If DeepSeek API fails for a ticker, note it and continue with the next. Related: [[default-report-generation]]
