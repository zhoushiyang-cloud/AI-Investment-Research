# CLAUDE.md — AI Investment Research System

## Project Overview

AI-powered investment research operating system. Integrates **OpenBB** (data), **Claude** (AI analysis), **Jupyter** (research), **Python scripts** (automation), and **Obsidian** (knowledge base) into a unified pipeline.

## Architecture

```
Claude Code (orchestrator)
    │
    ▼
OpenBB (data layer: equity, news, SEC, economics)
    │
    ▼
src/data_engine.py  ← unified data access (15+ functions)
    │
    ├── scripts/update_company.py   → regenerate company .md files
    ├── scripts/update_news.py      → fetch + save news
    ├── scripts/valuation.py        → DCF / comps / Graham models
    ├── scripts/export_obsidian.py  → Obsidian vault export
    └── scripts/generate_report.py  → LLM investment memos
    │
    ▼
notebooks/  ← interactive research (Jupyter)
    │
    ▼
companies/ + obsidian_export/  ← knowledge base (Obsidian)
    │
    ▼
GitHub  ← version control
```

## Quick Start

```bash
# Activate venv
.venv\Scripts\activate  # Windows

# Install dependencies (if not already done)
python -m ensurepip --upgrade
pip install -e ".[dev]"
pip install matplotlib seaborn openai anthropic jinja2 pytest mypy jupyter ipywidgets

# Configure API keys
cp config/api_keys.toml.example config/api_keys.toml
# Edit with your keys — yfinance works FREE without any keys
```

## Core Workflows

### Daily Briefing (full pipeline)
```bash
python scripts/orchestrate.py --all
```
Runs: company update → news → valuation → Obsidian export for all tracked tickers.

### Single Company Deep Dive
```bash
python scripts/orchestrate.py --ticker NVDA --with-reports --sensitivity
```

### Quick Price Check
```bash
python -c "from src.data_engine import get_quote; print(get_quote('NVDA'))"
```

### Launch Research Environment
```bash
jupyter lab notebooks/
```

## Project Structure

```
AI_Investment_System/
├── src/
│   ├── data_engine.py   # OpenBB wrapper (get_quote, get_profile, get_news, etc.)
│   ├── config.py        # Centralized config + OpenBB credential setup
│   └── markdown.py      # Markdown generators for company files, dashboards, reports
├── scripts/
│   ├── update_company.py # Fetch fundamentals → companies/{TICKER}.md
│   ├── update_news.py    # Fetch news → data/processed/ + append to .md
│   ├── valuation.py      # DCF (auto-param), Comps, Graham Number
│   ├── export_obsidian.py# Companies → Obsidian vault with [[wikilinks]]
│   ├── orchestrate.py    # Master pipeline (runs all above in order)
│   └── generate_report.py# Claude/OpenAI investment memo generator
├── companies/            # Per-company markdown analysis files
├── notebooks/            # Jupyter research notebooks
├── data/                 # raw/ and processed/ data
├── reports/              # Generated investment reports
├── prompts/              # LLM prompt templates
└── obsidian_export/      # Obsidian vault output
```

## Data Engine API (`src/data_engine.py`)

| Function | Description | Provider |
|---|---|---|
| `get_quote(ticker)` | Real-time price quote | yfinance (free) |
| `get_profile(ticker)` | Company profile (sector, mcap, employees) | yfinance (free) |
| `get_price_history(ticker, ...)` | OHLCV K-line data | yfinance (free) |
| `get_income_statement(ticker)` | Revenue, EPS, margins | yfinance→FMP |
| `get_balance_sheet(ticker)` | Assets, debt, equity | yfinance→FMP |
| `get_cash_flow(ticker)` | Operating CF, capex, FCF | yfinance→FMP |
| `get_key_metrics(ticker)` | P/E, P/B, ROE, margins | yfinance→FMP |
| `get_estimates_consensus(ticker)` | Analyst estimates | yfinance→FMP |
| `get_news(ticker, ...)` | Company news articles | yfinance (free) |
| `get_sec_filings(ticker)` | 10-K, 10-Q, 8-K filings | SEC (free) |
| `get_insider_trading(ticker)` | Form 4 insider trades | SEC (free) |
| `get_peer_metrics(tickers)` | Peer comparison table | yfinance→FMP |
| `fetch_all_for_ticker(ticker)` | ALL data in one call | mixed |

## Provider Strategy

**yfinance** → default (free, no API key required)
**SEC** → for filings (free)
**FMP** → premium upgrade (richer data, more reliable)
**Intrinio / Tiingo / Benzinga** → additional premium providers

The system works with zero API keys and gets better when you add them.
Configure keys in `config/api_keys.toml`.

## When Claude Code Should...

### Analyze a company
```bash
python scripts/orchestrate.py --ticker {TICKER} --with-reports
```
Then read `companies/{TICKER}.md` and `reports/{TICKER}_report_*.md`.

### Update everything
```bash
python scripts/orchestrate.py --all
```

### Research a new idea
```bash
jupyter lab notebooks/01_company_deep_dive.ipynb
```

### Generate a report
```bash
python scripts/generate_report.py --ticker {TICKER}
```

### Check valuation
```bash
python scripts/valuation.py --ticker {TICKER} --all-models --sensitivity
```

## Conventions

- Python 3.11+, type hints on all function signatures
- Line length: 100 (ruff)
- Lint: `ruff check src/ scripts/`
- All data access through `src/data_engine.py` — never call OpenBB directly from scripts
- Provider errors degrade gracefully (return empty DataFrame, log warning)
- Dataclasses for structured data; pandas DataFrames for tabular
