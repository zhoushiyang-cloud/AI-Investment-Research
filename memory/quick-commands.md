---
name: quick-commands
description: Master reference — all trigger phrases, commands, and workflows for the AI Investment System
metadata:
  type: project
---

# Quick Commands & Workflows

## Report Generation (any ticker)

| User says | Action |
|---|---|
| "生成 XX 报告" / "generate XX report" | 3-step pipeline: update_company → valuation → generate_report (DeepSeek) → translate (CN) → sync portal |
| "更新一批" / "update next batch" | `batch_update_reports.py --count 5` → updates 5 oldest companies → sync portal |
| "更新所有研报" / "update all reports" | `batch_update_reports.py --count 18` — refreshes everything |

**After generating a report, portal auto-syncs to GitHub Pages.** No manual push needed.

## Calendar & Predictions

| User says | Action |
|---|---|
| "日历" / "calendar" | `financial_calendar.py --month YYYY-MM --generate-predictions` |
| "这个月财报" | same as above for current month |
| "XX 为什么涨/跌" | fetch latest news + quote + analyze catalyst |

## Portal Site

- **EN**: `https://zhoushiyang-cloud.github.io/AI-Investment-Research/`
- **CN**: `https://zhoushiyang-cloud.github.io/AI-Investment-Research/index_cn.html`
- Rebuild: `python scripts/build_site.py`
- Sync: `python scripts/sync_portal.py` (with 5 retries)

## Key Scripts

```
scripts/generate_report.py     — AI report via DeepSeek (--ticker, --provider deepseek)
scripts/translate_reports.py   — EN→CN via DeepSeek (--ticker, --all)
scripts/financial_calendar.py  — Nasdaq earnings + predictions + HTML calendar
scripts/build_site.py          — MD→HTML renderer → docs/ portal
scripts/sync_portal.py         — rebuild + git push (5 retries)
scripts/batch_update_reports.py — rotation: 5 oldest/day (--count N, --list)
```

## Architecture

- **Data**: FMP (free) → Tiingo (K-line) → yfinance → SEC
- **AI**: DeepSeek API (openai-compatible, model: deepseek-chat)
- **Reports**: Obsidian callout syntax (en → convert to styled HTML for web)
- **Output**: 18 tracked companies, bilingual (EN + _cn), GitHub Pages, PWA
- **Scheduler**: Windows Task Scheduler daily 8AM via `schedule_daily.cmd`

## Bilingual Reports

Every English report auto-gets a Chinese translation. CN portal links to `_cn.html` files.
DeepSeek translates with rules: preserve wikilinks, numbers, tags; translate only analysis text.

## Theme

Portal + reports have ☀️/🌙 toggle (localStorage persisted), light/dark CSS variables.

[[default-report-generation]] [[bilingual-reports]] [[financial-calendar]] [[auto-sync-portal]]
