# AI Investment Research System

AI-powered investment research operating system — **OpenBB** for data, **Claude** for AI analysis, **Jupyter** for research, **Python** for automation, **Obsidian** for knowledge management.

## Architecture

```
Claude Code (orchestrator) → OpenBB (data) → Jupyter (research) → Scripts (automation) → Obsidian (knowledge base) → GitHub (version control)
```

## Quick Start

```bash
# Activate virtual environment
.venv\Scripts\activate  # Windows

# Bootstrap pip (if missing)
python -m ensurepip --upgrade

# Install dependencies
pip install -e ".[dev]"
pip install matplotlib seaborn openai anthropic jinja2 pytest mypy jupyter ipywidgets

# Configure API keys (optional — yfinance works for free)
cp config/api_keys.toml.example config/api_keys.toml
```

## Usage

### Daily Briefing (full pipeline)
```bash
python scripts/orchestrate.py --all
```

### Single Company Analysis
```bash
python scripts/orchestrate.py --ticker NVDA --with-reports --sensitivity
```

### Research Environment
```bash
jupyter lab notebooks/
```

### Individual Scripts
| Command | Purpose |
|---|---|
| `python scripts/update_company.py --ticker NVDA` | Fetch fundamentals → update company .md |
| `python scripts/update_news.py --ticker NVDA --days 7` | Fetch news → JSON + append to .md |
| `python scripts/valuation.py --ticker NVDA --all-models` | Run DCF + Comps + Graham |
| `python scripts/export_obsidian.py` | Export to Obsidian vault with [[wikilinks]] |
| `python scripts/generate_report.py --ticker NVDA` | LLM investment memo (needs API key) |
| `python scripts/orchestrate.py --all` | Run entire pipeline |

## Tracked Companies

| Ticker | Company | File |
|---|---|---|
| NVDA | NVIDIA Corporation | [NVDA.md](companies/NVDA.md) |
| AVGO | Broadcom Inc. | [AVGO.md](companies/AVGO.md) |
| ORCL | Oracle Corporation | [ORCL.md](companies/ORCL.md) |

## Data Providers

| Provider | Key Required? | What It Provides |
|---|---|---|
| **yfinance** | No | Price, profile, financials, metrics, news |
| **SEC** | No | EDGAR filings, insider trades, MD&A |
| **FMP** | Yes | Rich financials, ratios, transcripts, calendar |
| **Intrinio** | Yes | Forward estimates, reported financials |
| **Benzinga** | Yes | Rich news, analyst ratings |

The system works with **zero API keys** using yfinance + SEC. Add premium keys for richer data.

## Project Structure

```
AI_Investment_System/
├── src/                    # Shared library
│   ├── data_engine.py      # OpenBB wrapper (15+ data functions)
│   ├── config.py           # Unified config + credential management
│   └── markdown.py         # Markdown generators
├── scripts/                # Automation scripts
│   ├── orchestrate.py      # Master pipeline runner
│   ├── update_company.py   # Fetch fundamentals → .md files
│   ├── update_news.py      # Fetch news → JSON + .md append
│   ├── valuation.py        # DCF / Comps / Graham models
│   ├── export_obsidian.py  # Obsidian vault export
│   └── generate_report.py  # LLM investment memo generator
├── notebooks/              # Jupyter research environment
├── companies/              # Per-company markdown files
├── data/                   # raw/ and processed/ data
├── reports/                # Generated investment reports
├── prompts/                # LLM prompt templates
└── obsidian_export/        # Obsidian vault output
```

## License

Private — for personal use only.
