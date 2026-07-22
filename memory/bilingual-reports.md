---
name: bilingual-reports
description: All investment reports must be generated in both English and Chinese
metadata:
  type: project
---

Every investment research report must have both an English version and a Chinese version.

**Naming convention:**
- English: `reports/{TICKER}_report_{date}.md`
- Chinese: `reports/{TICKER}_report_{date}_cn.md`

**Generation workflow:**
1. Run the standard 3-step pipeline to generate the English report (update_company → valuation → generate_report)
2. Immediately translate to Chinese using DeepSeek API via `python scripts/translate_reports.py --ticker {TICKER}`

**Translation rules (enforced in prompt):**
- Preserve ALL markdown formatting exactly
- Do NOT translate: tickers ([[NVDA]], [[DELL]]), numbers, dates, financial figures, percentages
- Do NOT translate: severity tags (`#critical`, `#near-term`)
- Translate analysis prose naturally in professional financial Chinese

**Why:** The user reads reports in both languages. English for accuracy (financial terminology), Chinese for reading speed and comprehension of narrative analysis.

**How to apply:** After `generate_report.py` completes, immediately run `translate_reports.py --ticker {TICKER}`. The translate script already handles caching — it skips if CN version is up-to-date.

Related: [[default-report-generation]]
