# AI Investment System — Operations Manual

## Quick Reference

| Goal | Command |
|---|---|
| **Analyze a NEW stock** | 3 commands (see below) |
| **Analyze existing stock** | `python scripts/orchestrate.py --ticker NVDA --with-reports` |
| **Update ALL tracked stocks** | `python scripts/orchestrate.py --all` |
| **Interactive research** | `jupyter lab notebooks/` |
| **Export to Obsidian** | `python scripts/export_obsidian.py` |

---

## 1. Analyzing a NEW Stock

```
Step 1: Fetch data + generate company file
python scripts/update_company.py --ticker TSLA

Step 2: Run valuation models
python scripts/valuation.py --ticker TSLA --all-models --sensitivity

Step 3: Generate AI investment report
python scripts/generate_report.py --ticker TSLA --provider deepseek
```

**Output files:**
- `companies/TSLA.md` — company profile, financials, K-line, framework
- `reports/TSLA_report_2026-07-19.md` — AI-written investment memo

> **Tip:** Run Step 3 with `--dry-run` first to preview the prompt without spending API credits.

---

## 2. Daily / Weekly Routine

```bash
# One-command full pipeline for all tracked stocks
python scripts/orchestrate.py --all

# With AI reports (costs API credits)
python scripts/orchestrate.py --all --with-reports

# Full pipeline + DCF sensitivity analysis
python scripts/orchestrate.py --all --sensitivity
```

The pipeline runs: company data → news → valuation → Obsidian export → (optional) AI reports.

---

## 3. Adding a Stock to Permanent Tracking

Edit the `tracked` list in these files and add the ticker:

| File | Line |
|---|---|
| `scripts/update_company.py` | `tracked = ["NVDA", "AVGO", "ORCL"]` |
| `scripts/update_news.py` | `tracked = ["NVDA", "AVGO", "ORCL"]` |
| `scripts/orchestrate.py` | `tickers = ["NVDA", "AVGO", "ORCL"]` |

After adding, `--all` will include it automatically.

---

## 4. Individual Commands

### Data Fetching

```bash
# Company fundamentals → companies/{TICKER}.md
python scripts/update_company.py --ticker AAPL
python scripts/update_company.py --all

# News → data/processed/{TICKER}_news_{date}.json + append to .md
python scripts/update_news.py --ticker AAPL --days 30
python scripts/update_news.py --all --days 7
```

### Valuation

```bash
# All models (DCF + Comps + Graham)
python scripts/valuation.py --ticker NVDA --all-models

# DCF only with custom WACC + sensitivity table
python scripts/valuation.py --ticker NVDA --model dcf --wacc 0.12 --sensitivity

# Comps only
python scripts/valuation.py --ticker NVDA --model comps

# Override auto-detected growth rate
python scripts/valuation.py --ticker NVDA --model dcf --growth 0.25
```

### AI Report Generation

```bash
# DeepSeek (default) — OpenAI-compatible
python scripts/generate_report.py --ticker NVDA --provider deepseek

# Preview prompt first (no API cost)
python scripts/generate_report.py --ticker NVDA --provider deepseek --dry-run

# Using OpenAI
python scripts/generate_report.py --ticker NVDA --provider openai

# Using Anthropic Claude
python scripts/generate_report.py --ticker NVDA --provider anthropic

# All tracked stocks
python scripts/generate_report.py --all --provider deepseek
```

### Obsidian Export

```bash
# Export to obsidian_export/ vault
python scripts/export_obsidian.py

# Custom output path
python scripts/export_obsidian.py --output ~/Obsidian/InvestmentVault/
```

### Research Environment

```bash
# Launch Jupyter
jupyter lab notebooks/

# Notebooks:
#   01_company_deep_dive.ipynb   — Interactive single-company analysis
#   02_sector_comparison.ipynb   — Peer group valuation comparison
#   03_macro_dashboard.ipynb     — Economic indicators & market overview
#   04_valuation_sandbox.ipynb   — DCF Monte Carlo, scenario modeling
```

---

## 5. Python Quick Access

```python
from src.data_engine import *

# Quick price check
get_quote("NVDA")

# All data at once
data = fetch_all_for_ticker("TSLA", days_of_news=30)

# K-line / OHLCV
hist = get_price_history("NVDA", start="2025-01-01")

# Peer comparison table
peers = get_peer_metrics(["NVDA", "AMD", "INTC", "AVGO"])

# SEC filings
filings = get_sec_filings("NVDA", form_type="10-K", limit=5)
```

---

## 6. Configuration

### API Keys (`config/api_keys.toml`)

```toml
[fmp]          # Financial Modeling Prep — core data provider (FREE tier: 250 req/day)
api_key = "..."

[tiingo]       # Historical K-line prices (FREE tier: 1000 tickers/month)
api_key = "..."

[benzinga]     # News & analyst ratings (limited free tier)
api_key = "..."

[fred]         # Federal Reserve economic data (FREE)
api_key = "..."

[deepseek]     # AI report generation — OpenAI-compatible
api_key = "..."
base_url = "https://api.deepseek.com/v1"
model = "deepseek-chat"
```

**Minimum setup:** Just `[fmp]` is enough for 80% of features. Get a free key at https://financialmodelingprep.com/developer/docs/

### Data Provider Hierarchy

| Function | Primary | Fallback | Needs Key? |
|---|---|---|---|
| Price quote | FMP | yfinance | FMP key recommended |
| OHLCV / K-line | FMP | Tiingo | Either works |
| Income/Balance/Cash Flow | FMP | yfinance | FMP key recommended |
| Valuation multiples (P/E, etc.) | FMP | — | FMP required |
| Financial ratios | FMP | — | FMP required |
| Analyst estimates | FMP | — | FMP required |
| News | Tiingo | yfinance | News often needs paid tier |
| SEC filings | FMP | SEC | Either works |
| Macro data (GDP, CPI) | FRED | — | FRED required |
| AI report generation | DeepSeek | OpenAI / Anthropic | At least one needed |

---

## 7. Obsidian Integration

### Reading Reports in Obsidian

1. Point Obsidian vault to `D:\AI_Investment_System\`
2. Reports use **callouts** for visual hierarchy:
   - `> [!abstract]` — Executive Summary
   - `> [!warning]` — Risks
   - `> [!tip]` — Catalysts
   - `> [!quote]` — Recommendation
   - `> [!note]-` — Collapsible financial data appendix
3. `[[wikilinks]]` connect company notes, sector pages, comparisons
4. YAML frontmatter enables Dataview queries

### Exporting to a Separate Obsidian Vault

```bash
python scripts/export_obsidian.py --output ~/Obsidian/MyVault/
```

This generates a complete vault with:
- Company notes with frontmatter
- `Investment Dashboard.md` — portfolio overview
- `Peer Comparison.md` — valuation comparison
- `Sector — Technology.md` — sector aggregation
- All interconnected with `[[wikilinks]]`

---

## 8. Troubleshooting

| Problem | Fix |
|---|---|
| "Timeout" errors | yfinance blocked in China → FMP is the alternative. Make sure `[fmp]` key is set. |
| "401/402 Unauthorized" | FMP free tier restricted endpoint. Some peers may not have metrics. |
| News always empty | Free tier news APIs are limited. Upgrade Tiingo (~$10/mo) or FMP for news. |
| "gbk codec error" | Fixed. If new emoji appear, replace with plain text in the script. |
| DeepSeek returns nothing | Check `api_key` and `base_url` in `[deepseek]` config section. |
| pip missing in venv | `python -m ensurepip --upgrade` |
| Jupyter won't launch | `pip install jupyter ipywidgets` |

---

## 9. File Map

```
AI_Investment_System/
├── USAGE.md                    ← THIS FILE
├── config/api_keys.toml        ← YOUR API KEYS (git-ignored)
├── companies/                  ← Auto-generated company files
│   ├── NVDA.md
│   └── ...
├── reports/                    ← AI-generated investment reports
│   ├── NVDA_report_2026-xx-xx.md
│   └── NVDA_prompt_2026-xx-xx.md  (dry-run output)
├── obsidian_export/            ← Obsidian vault export
├── data/processed/             ← News JSON, pipeline logs
├── notebooks/                  ← Jupyter research notebooks
├── src/                        ← Core library
│   ├── data_engine.py          ← All OpenBB API calls
│   ├── config.py               ← Config loading + credentials
│   └── markdown.py             ← Report/company file generators
└── scripts/                    ← Automation scripts
    ├── orchestrate.py           ← Master pipeline
    ├── update_company.py        ← Fetch financials → .md
    ├── update_news.py           ← Fetch news → JSON + .md
    ├── valuation.py             ← DCF / Comps / Graham
    ├── export_obsidian.py       ← Obsidian vault export
    └── generate_report.py       ← LLM investment reports
```
