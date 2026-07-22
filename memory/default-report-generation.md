---
name: default-report-generation
description: Standard 3-step pipeline for generating any company investment report
metadata:
  type: project
---

When the user says "generate a report for XXX" or "give me XXX report" (where XXX is a stock ticker), run the full 3-step pipeline automatically without asking for confirmation:

**Step 1:** `python scripts/update_company.py --ticker {TICKER}` — fetch fundamentals (financials, K-line, SEC filings, profile) via FMP→Tiingo→yfinance→SEC
**Step 2:** `python scripts/valuation.py --ticker {TICKER} --all-models --sensitivity` — run DCF + Comps + Graham Number
**Step 3:** `python scripts/generate_report.py --ticker {TICKER} --provider deepseek` — DeepSeek LLM synthesizes all data into a formatted investment memo

The enhanced `generate_report.py` now uses ALL available APIs: profile, metrics, ratios, income/balance/cashflow statements, analyst estimates, price targets (Benzinga/FMP), 30-day news, SEC filings, insider trades, K-line price history, and current quote.

**Why:** USAGE.md defines this as the standard 3-step workflow. The user has configured FMP (free), Tiingo (free), Benzinga, FRED, and DeepSeek API keys. The enhanced prompt builder includes every available data source to produce the richest possible report.

**How to apply:** When user mentions a ticker + "report"/"generate", immediately run all 3 steps. Use `PYTHONIOENCODING=utf-8 .venv/Scripts/python` prefix on Windows. If the ticker doesn't exist, warn the user first. If DeepSeek API fails, try OpenAI fallback; if both fail, generate the report manually using available data.
