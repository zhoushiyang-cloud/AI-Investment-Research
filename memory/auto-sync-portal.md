---
name: auto-sync-portal
description: Auto-sync reports to GitHub Pages after generation; daily batch rotation keeps all reports fresh
metadata:
  type: project
---

After generating any report, the system auto-builds the portal and pushes to GitHub Pages.

**Auto-sync:** `generate_report.py` now has `--sync` enabled by default. After saving a report, it automatically runs `sync_portal.py` which rebuilds the portal site and pushes to GitHub.

**Daily batch rotation:** `batch_update_reports.py` updates 5 companies per run (oldest first), rotating through all 18 tracked tickers. At 5/day, a full cycle takes ~4 days — staying well within free API rate limits.

**Scheduling:** Windows Task Scheduler runs `schedule_daily.cmd` at 8:00 AM daily.
Setup: `PowerShell (Admin) → Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass → .\scripts\setup_scheduler.ps1`

**Key commands:**
- `python scripts/batch_update_reports.py --count 5` — update 5 oldest companies
- `python scripts/batch_update_reports.py --list` — show update status
- `python scripts/sync_portal.py` — rebuild + push portal
- `python scripts/generate_report.py --ticker NVDA` — auto-syncs after generation

**Why:** Manual git push is tedious and prone to forgetting. Daily rotation ensures all reports stay current without exceeding free API limits (FMP 250 req/day, DeepSeek rate limits).

Related: [[default-report-generation]], [[bilingual-reports]]
