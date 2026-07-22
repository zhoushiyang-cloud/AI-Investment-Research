"""
financial_calendar.py — Monthly US Stock Earnings + Major Events Calendar & Prediction System.

Pulls real-time earnings data from Nasdaq's free API, filters for important companies,
generates DeepSeek-powered predictions for key earnings reports, and outputs:
  1. Obsidian markdown monthly calendar with callouts
  2. DeepSeek prediction report for mega-cap earnings + major macro events
  3. Interactive HTML calendar with tooltips and dark mode

Usage:
    python scripts/financial_calendar.py --month 2026-07
    python scripts/financial_calendar.py --month 2026-07 --generate-predictions
    python scripts/financial_calendar.py --month 2026-07 --output html
"""

import argparse
import calendar as cal_mod
import json
import math
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.config import load_config

# ── Config ──────────────────────────────────────────────────────────────────────
NASDAQ_API = "https://api.nasdaq.com/api/calendar/earnings"
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "reports" / "calendar"

# Mega-cap threshold: only generate predictions for companies above this market cap
MEGA_CAP_THRESHOLD = 200_000_000_000  # $200B
LARGE_CAP_THRESHOLD = 10_000_000_000   # $10B

# Core tracked tickers (always highlighted even if below threshold)
TRACKED_TICKERS = {
    "NVDA", "AVGO", "ORCL", "MRVL", "SMCI", "DELL", "PLTR", "CRCL",
    "RKLB", "SPCX", "SKHYV", "ALGM", "CGNX", "AMZN", "GOOGL", "MSFT",
    "TSLA", "ONDS",
}

# Major US economic events (curated — FRED release dates + scheduled events)
MAJOR_EVENTS_2026_07 = [
    {"date": "2026-07-14", "event": "June CPI Inflation Report", "importance": "critical",
     "affected": "All equities, bonds, rates. High CPI → tech selloff; low CPI → rally."},
    {"date": "2026-07-15", "event": "June PPI (Producer Prices)", "importance": "medium",
     "affected": "Industrials, materials, consumer goods."},
    {"date": "2026-07-16", "event": "Fed Beige Book Release", "importance": "medium",
     "affected": "Banks, regional economy exposure."},
    {"date": "2026-07-17", "event": "June Retail Sales Data", "importance": "medium",
     "affected": "Consumer discretionary, retail (AMZN, TSLA)."},
    {"date": "2026-07-28", "event": "FOMC July Meeting (Day 1)", "importance": "critical",
     "affected": "All equities. Rate decision on 7/29. Dovish → growth rally; hawkish → selloff."},
    {"date": "2026-07-29", "event": "FOMC Rate Decision (2:00 PM ET)", "importance": "critical",
     "affected": "All equities. Most important event of the month."},
    {"date": "2026-07-30", "event": "Q2 GDP Advance Estimate", "importance": "critical",
     "affected": "All equities. Growth trajectory signal."},
    {"date": "2026-07-31", "event": "June PCE Inflation (Fed's preferred gauge)", "importance": "critical",
     "affected": "All equities. Core PCE directly influences Fed policy."},
]


# ── Data Fetching ───────────────────────────────────────────────────────────────

def _parse_market_cap(raw: str) -> float:
    """Parse market cap string like '$293,607,298,848' into float."""
    if not raw or raw == "N/A":
        return 0.0
    return float(raw.replace("$", "").replace(",", ""))


def fetch_earnings_day(date_str: str) -> list[dict]:
    """Fetch earnings calendar for one day from Nasdaq API."""
    try:
        r = requests.get(
            NASDAQ_API,
            params={"date": date_str},
            headers=REQUEST_HEADERS,
            timeout=15,
        )
        if r.status_code != 200:
            return []
        data = r.json()
        rows = data.get("data", {}).get("rows")
        if rows is None:
            return []
        return rows
    except Exception:
        return []


def fetch_month_earnings(year: int, month: int) -> dict[str, list[dict]]:
    """Fetch all earnings events for a month.

    Returns:
        Dict mapping date_str -> list of earnings events.
    """
    _, days_in_month = cal_mod.monthrange(year, month)
    all_events: dict[str, list[dict]] = {}

    print(f"  Fetching earnings for {year}-{month:02d} ({days_in_month} days)...")

    for day in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day:02d}"
        events = fetch_earnings_day(date_str)
        if events:
            all_events[date_str] = events
        if day % 7 == 0 or day == days_in_month:
            total = sum(len(v) for v in all_events.values())
            print(f"    Day {day}/{days_in_month}: {total} events so far...")

    return all_events


# ── Filtering & Classification ─────────────────────────────────────────────────

def _to_importance(mcap: float, ticker: str) -> int:
    """Classify earning event importance: 3=mega, 2=large, 1=notable, 0=skip."""
    ticker_upper = ticker.upper().strip()
    if ticker_upper in TRACKED_TICKERS:
        return 3 if mcap >= MEGA_CAP_THRESHOLD else 2
    if mcap >= MEGA_CAP_THRESHOLD:
        return 3
    if mcap >= LARGE_CAP_THRESHOLD:
        return 2
    # Include small-caps if they're notable names (optional)
    return 0  # Skip micro/small caps by default


def classify_events(all_events: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """Filter and classify earnings events by importance.

    Returns:
        Dict with keys '⭐⭐⭐', '⭐⭐', '⭐' → list of annotated events.
    """
    classified: dict[str, list[dict]] = {"⭐⭐⭐": [], "⭐⭐": [], "⭐": []}

    for date_str, events in sorted(all_events.items()):
        for ev in events:
            symbol = (ev.get("symbol") or "").upper().strip()
            name = ev.get("name", "?")
            mcap_raw = ev.get("marketCap", "$0")
            mcap = _parse_market_cap(mcap_raw)

            importance = _to_importance(mcap, symbol)
            if importance == 0:
                continue

            annotated = {
                **ev,
                "symbol_clean": symbol,
                "name_clean": name,
                "market_cap_val": mcap,
                "importance": importance,
                "date": date_str,
                "eps_forecast": ev.get("epsForecast", "N/A"),
                "eps_actual": ev.get("eps", "N/A"),
                "surprise": ev.get("surprise", "N/A"),
                "quarter": ev.get("fiscalQuarterEnding", "?"),
                "report_time": ev.get("time", "time-not-supplied"),
                "no_of_ests": ev.get("noOfEsts", "?"),
            }

            label = {3: "⭐⭐⭐", 2: "⭐⭐", 1: "⭐"}[importance]
            classified[label].append(annotated)

    return classified


# ── DeepSeek Predictions ────────────────────────────────────────────────────────

def _build_prediction_prompt(event: dict) -> str:
    """Build a prediction prompt for a single company's upcoming earnings."""
    symbol = event["symbol_clean"]
    name = event["name_clean"]
    mcap_b = event["market_cap_val"] / 1e9
    eps_f = event["eps_forecast"]
    eps_a = event["eps_actual"]
    surprise = event["surprise"]
    quarter = event["quarter"]

    return f"""You are a senior equity research analyst specializing in earnings predictions.

Company: {name} ({symbol})
Market Cap: ${mcap_b:.0f}B
Fiscal Quarter: {quarter}
Consensus EPS Forecast: ${eps_f}
Last Reported EPS: ${eps_a}
Previous Surprise: {surprise}%

Based on the company's sector, recent market trends, and AI/tech cycle dynamics, predict:

1. **Earnings Outcome**: Beat / Miss / Inline (choose one)
2. **Stock Price Reaction**: +X% or -X% (estimate the post-earnings move)
3. **Key Driver** (1 sentence): What factor will most determine this result
4. **Confidence**: High / Medium / Low

Output as JSON:
{{"outcome": "Beat", "price_reaction": "+3.5%", "driver": "AI server demand acceleration drove upside", "confidence": "Medium"}}

Return ONLY the JSON object, no other text."""


def generate_predictions(
    classified: dict[str, list[dict]],
    config: dict,
) -> list[dict]:
    """Generate DeepSeek predictions for mega-cap earnings."""
    from openai import OpenAI

    api_key = config.get("deepseek", {}).get("api_key", "")
    model = config.get("deepseek", {}).get("model", "deepseek-chat")
    base_url = config.get("deepseek", {}).get("base_url", "https://api.deepseek.com/v1")

    if not api_key:
        print("  [WARN] No DeepSeek API key — skipping predictions.")
        return []

    client = OpenAI(api_key=api_key, base_url=base_url)

    # Only predict for ⭐⭐⭐ companies
    targets = classified.get("⭐⭐⭐", [])[:15]  # Cap at 15 to control API costs
    predictions: list[dict] = []

    print(f"\n  Generating predictions for {len(targets)} mega-cap companies...")

    for i, ev in enumerate(targets, 1):
        symbol = ev["symbol_clean"]
        prompt = _build_prediction_prompt(ev)
        print(f"    [{i}/{len(targets)}] {symbol}...", end=" ")

        try:
            response = client.chat.completions.create(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                max_tokens=256,
                temperature=0.4,
            )
            raw = response.choices[0].message.content.strip()

            # Parse JSON from response
            if raw.startswith("```"):
                raw = raw.split("\n", 1)[1].rsplit("\n", 1)[0]
            pred = json.loads(raw)
            pred["symbol"] = symbol
            pred["name"] = ev["name_clean"]
            pred["market_cap_b"] = ev["market_cap_val"] / 1e9
            pred["eps_forecast"] = ev["eps_forecast"]
            pred["date"] = ev["date"]
            predictions.append(pred)
            print(pred.get("outcome", "?"))
        except Exception as e:
            print(f"FAILED: {e}")

    return predictions


# ── Output: Obsidian Markdown Calendar ─────────────────────────────────────────

def _importance_badge(importance: int) -> str:
    return {3: "🔥", 2: "⭐", 1: "•"}[importance]


def _format_mcap(val: float) -> str:
    if val >= 1e12:
        return f"${val/1e12:.1f}T"
    if val >= 1e9:
        return f"${val/1e9:.0f}B"
    if val >= 1e6:
        return f"${val/1e6:.0f}M"
    return f"${val:,.0f}"


def generate_markdown_calendar(
    year: int,
    month: int,
    classified: dict[str, list[dict]],
    all_events: dict[str, list[dict]],
) -> str:
    """Generate Obsidian markdown monthly calendar with embedded events."""
    month_name = datetime(year, month, 1).strftime("%B")
    month_abbr = datetime(year, month, 1).strftime("%b")

    # Build event lookup by date
    event_map: dict[str, list[dict]] = {}
    for label, events in classified.items():
        for ev in events:
            d = ev["date"]
            event_map.setdefault(d, []).append(ev)

    # Build economic event lookup
    econ_map: dict[str, list[dict]] = {}
    for ev in MAJOR_EVENTS_2026_07:
        econ_map.setdefault(ev["date"], []).append(ev)

    total_events = sum(len(v) for v in classified.values())
    mega = len(classified.get("⭐⭐⭐", []))
    large = len(classified.get("⭐⭐", []))

    md = f"""---
title: "{month_name} {year} Earnings Calendar"
date: {datetime.now().strftime('%Y-%m-%d')}
tags:
  - earnings-calendar
  - monthly
  - {year}
type: calendar
month: "{year}-{month:02d}"
total_events: {total_events}
mega_cap: {mega}
large_cap: {large}
---

# 📅 {month_name} {year} — US Stock Earnings Calendar
> *Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} · {total_events} notable companies reporting*

---

## 🗓 Calendar Grid

| Mon | Tue | Wed | Thu | Fri | Sat | Sun |
|---|---|---|---|---|---|---|
"""

    # Build calendar grid (Mon-Sun)
    cal = cal_mod.Calendar(firstweekday=0)  # Monday first
    weeks = cal.monthdatescalendar(year, month)

    for week in weeks:
        row = "|"
        for date_obj in week:
            day = date_obj.day
            date_str = date_obj.strftime("%Y-%m-%d")

            if date_obj.month != month:
                row += " |"  # Gray days
                continue

            cell = f"**{day}**"

            # Add economic events
            econ_events = econ_map.get(date_str, [])
            for ee in econ_events:
                emoji = "🔴" if ee["importance"] == "critical" else "🟡"
                cell += f"<br>{emoji} {ee['event']}"

            # Add earnings events (top 3 per day)
            day_events = event_map.get(date_str, [])
            shown = 0
            for ev in sorted(day_events, key=lambda x: -x["market_cap_val"]):
                if shown >= 3:
                    break
                badge = _importance_badge(ev["importance"])
                cell += f"<br>{badge} [[{ev['symbol_clean']}]]"
                if ev["eps_forecast"] and ev["eps_forecast"] != "N/A":
                    cell += f" (${ev['eps_forecast']})"
                shown += 1

            remaining = len(day_events) - shown
            if remaining > 0:
                cell += f"<br>  *+{remaining} more*"

            row += cell + " |"

        row += "\n"
        md += row

    # ── Economic Events Section ──
    md += f"""
---

## 🏛 Major Economic Events — {month_name} {year}

| Date | Event | Importance | Affected Sectors |
|---|---|---|---|
"""
    for ev in sorted(MAJOR_EVENTS_2026_07, key=lambda x: x["date"]):
        imp = "🔴 Critical" if ev["importance"] == "critical" else "🟡 Medium"
        md += f"| {ev['date']} | {ev['event']} | {imp} | {ev['affected']} |\n"

    # ── Detailed Earnings by Week ──
    md += f"""

---

## 📊 Detailed Earnings by Week

"""

    # Group by week
    current_week_events: dict[str, list[dict]] = {}
    for label, events in classified.items():
        for ev in events:
            date_obj = datetime.strptime(ev["date"], "%Y-%m-%d")
            week_num = date_obj.isocalendar()[1]
            week_key = f"Week {week_num} ({date_obj.strftime('%b %d')} — ...)"
            current_week_events.setdefault(week_key, []).append(ev)

    for week_key in sorted(current_week_events.keys()):
        week_evs = current_week_events[week_key]
        md += f"\n### {week_key}\n\n"
        md += "| Ticker | Company | Market Cap | EPS Fcst | Quarter | Importance |\n"
        md += "|---|---|---|---|---|---|\n"
        for ev in sorted(week_evs, key=lambda x: -x["market_cap_val"]):
            badge = _importance_badge(ev["importance"])
            mcap_str = _format_mcap(ev["market_cap_val"])
            md += (
                f"| [[{ev['symbol_clean']}]] | {ev['name_clean']} | {mcap_str} | "
                f"${ev['eps_forecast']} | {ev['quarter']} | {badge} |\n"
            )

    md += f"""

---

## 📈 Statistics

| Metric | Value |
|---|---|
| Total Notable Companies | {total_events} |
| Mega-Cap ($200B+) | {mega} |
| Large-Cap ($10B+) | {large} |
| Tracked Companies Reporting | {sum(1 for v in classified.values() for ev in v if ev['symbol_clean'] in TRACKED_TICKERS)} |
| Most Active Day | *see grid above* |

> [!tip]- Quick Links
> - [[Investment Dashboard]] | [[{month_name} {year} Earnings Predictions]]
> - [[Economic Indicators]] | [[Portfolio Watchlist]]

---
*Calendar generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · AI Investment System*
*Data: Nasdaq Earnings Calendar API · Economic Events: Curated (FRED/FOMC schedule)*
"""
    return md


# ── Output: Predictions Markdown ───────────────────────────────────────────────

def generate_predictions_markdown(
    year: int,
    month: int,
    predictions: list[dict],
    classified: dict[str, list[dict]],
) -> str:
    """Generate Obsidian markdown for earnings + macro predictions."""
    month_name = datetime(year, month, 1).strftime("%B")

    md = f"""---
title: "{month_name} {year} Earnings Predictions"
date: {datetime.now().strftime('%Y-%m-%d')}
tags:
  - earnings-predictions
  - predictions
  - {year}
type: predictions
month: "{year}-{month:02d}"
---

# 🔮 {month_name} {year} — Earnings & Event Predictions
> *AI-Generated Predictions · {datetime.now().strftime('%Y-%m-%d %H:%M')}*

---

## 🤖 AI Earnings Predictions (Mega-Cap)

*Generated by DeepSeek AI. These are probabilistic estimates, not financial advice.*

"""

    for pred in predictions:
        symbol = pred["symbol"]
        outcome = pred.get("outcome", "?")
        reaction = pred.get("price_reaction", "?")
        driver = pred.get("driver", "?")
        confidence = pred.get("confidence", "Medium")
        mcap_b = pred.get("market_cap_b", 0)
        eps_f = pred.get("eps_forecast", "?")

        conf_emoji = {"High": "🟢", "Medium": "🟡", "Low": "🔴"}.get(confidence, "⚪")

        md += f"""### [{symbol}] — {pred.get('name', symbol)}

| Field | Value |
|---|---|
| **Prediction** | **{outcome}** |
| **Price Reaction** | {reaction} |
| **Confidence** | {conf_emoji} {confidence} |
| **Market Cap** | ${mcap_b:.0f}B |
| **Consensus EPS** | ${eps_f} |

> [!quote] Analysis
> **Key Driver:** {driver}
>
> *This prediction is AI-generated based on available data. Always do your own research.*

---
"""

    # ── Macro Event Impact ──
    md += f"""

---

## 🏛 Major Macro Event Impact Predictions

"""
    for ev in MAJOR_EVENTS_2026_07:
        imp = "CRITICAL" if ev["importance"] == "critical" else "Medium"
        md += f"""### {ev['date']} — {ev['event']} `#{imp}`

> [!info] Expected Impact
> {ev['affected']}

"""

    # ── Tracked Companies Alert ──
    md += f"""

---

## ⚠️ Tracked Companies Reporting This Month

| Ticker | Date | EPS Fcst | Status |
|---|---|---|---|
"""
    for label in ["⭐⭐⭐", "⭐⭐", "⭐"]:
        for ev in classified.get(label, []):
            if ev["symbol_clean"] in TRACKED_TICKERS:
                md += (
                    f"| [[{ev['symbol_clean']}]] | {ev['date']} | "
                    f"${ev['eps_forecast']} | ⚠️ Watch |\n"
                )

    md += f"""

> [!tip] Action Items
> - Review pre-earnings positions 3 days before report date
> - Consider hedging around FOMC (7/29) and GDP (7/30)
> - Check [[Investment Dashboard]] for current portfolio weights

---
*Predictions generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · AI Investment System*
"""
    return md


# ── Output: HTML Calendar ──────────────────────────────────────────────────────

def generate_html_calendar(
    year: int,
    month: int,
    classified: dict[str, list[dict]],
) -> str:
    """Generate self-contained interactive HTML calendar."""
    month_name = datetime(year, month, 1).strftime("%B")

    # Flatten classified into date lookup
    event_map: dict[str, list[dict]] = {}
    for label, events in classified.items():
        for ev in events:
            event_map.setdefault(ev["date"], []).append(ev)

    # Build JSON data for JS consumption
    calendar_data: dict[str, list[dict]] = {}
    for date_str, events in event_map.items():
        calendar_data[date_str] = [
            {
                "symbol": e["symbol_clean"],
                "name": e["name_clean"],
                "mcap": _format_mcap(e["market_cap_val"]),
                "mcap_val": e["market_cap_val"],
                "eps": str(e.get("eps_forecast", "?")),
                "importance": e["importance"],
                "quarter": str(e.get("quarter", "?")),
            }
            for e in sorted(events, key=lambda x: -x["market_cap_val"])[:10]
        ]

    # Economic events
    econ_data = [
        {"date": e["date"], "event": e["event"], "importance": e["importance"]}
        for e in MAJOR_EVENTS_2026_07
    ]

    calendar_json = json.dumps(calendar_data)
    econ_json = json.dumps(econ_data)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{month_name} {year} Earnings Calendar</title>
<style>
  :root {{
    --bg: #1a1a2e;
    --card: #16213e;
    --text: #e0e0e0;
    --accent: #e94560;
    --gold: #ffd700;
    --mega: #ff6b6b;
    --large: #ffd93d;
    --small: #6bcb77;
    --border: #2a2a4a;
    --hover: #1f3060;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{
    font-family: -apple-system, Segoe UI, sans-serif;
    background: var(--bg); color: var(--text);
    padding: 20px; max-width: 1200px; margin: auto;
  }}
  h1 {{ text-align: center; margin-bottom: 20px; color: var(--accent); }}
  .grid {{
    display: grid; grid-template-columns: repeat(7, 1fr);
    gap: 4px; margin-bottom: 20px;
  }}
  .day-header {{
    background: var(--card); padding: 10px; text-align: center;
    font-weight: bold; border-radius: 6px;
  }}
  .day {{
    background: var(--card); padding: 8px; min-height: 100px;
    border-radius: 6px; cursor: default; transition: all 0.2s;
    position: relative; font-size: 0.85em;
  }}
  .day:hover {{ background: var(--hover); transform: scale(1.02); z-index: 10; }}
  .day.empty {{ opacity: 0.3; }}
  .day-num {{ font-weight: bold; font-size: 1.1em; margin-bottom: 4px; }}
  .event {{ margin: 2px 0; padding: 2px 4px; border-radius: 3px; font-size: 0.75em; }}
  .event.mega {{ background: var(--mega); color: #000; font-weight: bold; }}
  .event.large {{ background: var(--large); color: #000; }}
  .event.small {{ background: var(--small); color: #000; }}
  .event.econ {{ background: #8b5cf6; color: #fff; font-weight: bold; }}
  .event.more {{ color: #888; font-style: italic; }}
  .legend {{ display: flex; gap: 20px; justify-content: center; margin: 15px 0; flex-wrap: wrap; }}
  .legend span {{ padding: 4px 10px; border-radius: 4px; font-size: 0.85em; }}
  .tooltip {{
    display: none; position: absolute; background: #000; color: #fff;
    padding: 8px 12px; border-radius: 6px; font-size: 0.8em; z-index: 100;
    white-space: nowrap; pointer-events: none; left: 50%; transform: translateX(-50%);
    bottom: 100%; margin-bottom: 5px; box-shadow: 0 4px 12px rgba(0,0,0,0.5);
  }}
  .day:hover .tooltip {{ display: block; }}
  .stats {{ text-align: center; margin: 20px 0; font-size: 0.9em; color: #888; }}
  .filter-row {{ text-align: center; margin: 10px 0; }}
  .filter-row button {{
    background: var(--card); color: var(--text); border: 1px solid var(--border);
    padding: 6px 14px; margin: 0 3px; border-radius: 4px; cursor: pointer;
  }}
  .filter-row button.active {{ background: var(--accent); }}
  @media (max-width: 768px) {{
    .day {{ min-height: 60px; font-size: 0.7em; }}
  }}
</style>
</head>
<body>

<h1>📅 {month_name} {year} — Earnings Calendar</h1>

<div class="filter-row">
  <button onclick="filter('all')" class="active" id="btn-all">All</button>
  <button onclick="filter('mega')" id="btn-mega">🔥 Mega-Cap</button>
  <button onclick="filter('tracked')" id="btn-tracked">⭐ Tracked</button>
  <button onclick="filter('econ')" id="btn-econ">🏛 Economic</button>
</div>

<div class="legend">
  <span style="background:var(--mega);color:#000">🔥 Mega-Cap ($200B+)</span>
  <span style="background:var(--large);color:#000">⭐ Large-Cap ($10B+)</span>
  <span style="background:var(--small);color:#000">• Notable</span>
  <span style="background:#8b5cf6;color:#fff">🏛 Economic Event</span>
</div>

<div class="grid" id="calendar-grid"></div>

<div class="stats" id="stats-bar"></div>

<script>
const CALENDAR_DATA = {calendar_json};
const ECON_DATA = {econ_json};
const TRACKED = {json.dumps(list(TRACKED_TICKERS))};
const YEAR = {year}, MONTH = {month};

function buildCalendar() {{
  const grid = document.getElementById('calendar-grid');
  grid.innerHTML = '';
  const headers = ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'];
  headers.forEach(h => {{
    const dh = document.createElement('div');
    dh.className = 'day-header'; dh.textContent = h;
    grid.appendChild(dh);
  }});

  const firstDay = new Date(YEAR, MONTH-1, 1).getDay();
  const daysInMonth = new Date(YEAR, MONTH, 0).getDate();
  const startOffset = firstDay === 0 ? 6 : firstDay - 1; // Monday=0

  for (let i = 0; i < startOffset; i++) {{
    const empty = document.createElement('div');
    empty.className = 'day empty';
    grid.appendChild(empty);
  }}

  for (let d = 1; d <= daysInMonth; d++) {{
    const dateStr = `${{YEAR}}-${{String(MONTH).padStart(2,'0')}}-${{String(d).padStart(2,'0')}}`;
    const cell = document.createElement('div');
    cell.className = 'day';
    cell.id = 'day-' + d;

    let html = `<div class="day-num">${{d}}</div>`;

    // Economic events
    const econEvts = ECON_DATA.filter(e => e.date === dateStr);
    econEvts.forEach(ee => {{
      html += `<div class="event econ" data-type="econ">🏛 ${{ee.event.substring(0,30)}}</div>`;
    }});

    // Earnings events
    const dayEvents = CALENDAR_DATA[dateStr] || [];
    dayEvents.forEach((ev, i) => {{
      if (i >= 4) return;
      const cls = ev.importance >= 3 ? 'mega' : ev.importance >= 2 ? 'large' : 'small';
      const tracked = TRACKED.includes(ev.symbol) ? '⭐' : '';
      html += `<div class="event ${{cls}}" data-type="earnings">${{tracked}} ${{ev.symbol}} ($${{ev.eps}})</div>`;
    }});

    if (dayEvents.length > 4) {{
      html += `<div class="event more">+${{dayEvents.length - 4}} more...</div>`;
    }}

    // Tooltip
    if (dayEvents.length > 0 || econEvts.length > 0) {{
      let tip = '<b>' + dateStr + '</b><br>';
      econEvts.forEach(ee => tip += '🏛 ' + ee.event + '<br>');
      dayEvents.slice(0,8).forEach(ev => {{
        tip += `${{ev.symbol}}: ${{ev.name}} (${{ev.mcap}}, EPS ${{ev.eps}})<br>`;
      }});
      if (dayEvents.length > 8) tip += '+ more...';
      html += `<div class="tooltip">${{tip}}</div>`;
    }}

    cell.innerHTML = html;
    grid.appendChild(cell);
  }}

  document.getElementById('stats-bar').innerHTML =
    `${{Object.values(CALENDAR_DATA).flat().length}} events · ${{ECON_DATA.length}} economic events · ${{Object.keys(CALENDAR_DATA).length}} trading days`;
}}

function filter(type) {{
  document.querySelectorAll('.filter-row button').forEach(b => b.classList.remove('active'));
  document.getElementById('btn-' + type).classList.add('active');

  document.querySelectorAll('.day').forEach(day => {{
    if (type === 'all') {{ day.style.opacity = '1'; return; }}
    const events = day.querySelectorAll('.event');
    const econEvts = day.querySelectorAll('.event[data-type="econ"]');
    const earningEvts = day.querySelectorAll('.event[data-type="earning"]:not([data-type="econ"])');
    if (type === 'econ') {{
      day.style.opacity = econEvts.length > 0 ? '1' : '0.25';
    }} else if (type === 'mega') {{
      const hasMega = Array.from(events).some(e => e.classList.contains('mega'));
      day.style.opacity = hasMega ? '1' : '0.25';
    }} else if (type === 'tracked') {{
      let hasTracked = false;
      events.forEach(e => {{
        if (e.textContent.includes('⭐')) hasTracked = true;
      }});
      day.style.opacity = hasTracked ? '1' : '0.25';
    }}
  }});
}}

buildCalendar();
</script>
</body>
</html>"""


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Financial Calendar & Prediction System"
    )
    parser.add_argument(
        "--month", type=str,
        default=datetime.now().strftime("%Y-%m"),
        help="Month in YYYY-MM format (default: current month)",
    )
    parser.add_argument(
        "--generate-predictions", action="store_true",
        help="Generate DeepSeek AI predictions for mega-cap earnings",
    )
    parser.add_argument(
        "--output", type=str, default="all",
        choices=["all", "md", "html", "predictions"],
        help="Output formats (default: all)",
    )
    args = parser.parse_args()

    # Parse month
    year, month = map(int, args.month.split("-"))

    print(f"\n{'='*60}")
    print(f"  Financial Calendar — {year}-{month:02d}")
    print(f"{'='*60}")

    # Ensure output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Fetch
    all_events = fetch_month_earnings(year, month)
    total_raw = sum(len(v) for v in all_events.values())
    print(f"\n  Total raw events fetched: {total_raw}")

    # 2. Classify
    classified = classify_events(all_events)
    for label in ["⭐⭐⭐", "⭐⭐", "⭐"]:
        print(f"  {label}: {len(classified[label])} companies")

    # 3. Predictions (optional)
    predictions: list[dict] = []
    if args.generate_predictions:
        config = load_config()
        predictions = generate_predictions(classified, config)
        print(f"  Generated {len(predictions)} predictions")

    # 4. Output
    month_str = f"{year}-{month:02d}"

    if args.output in ("all", "md"):
        md = generate_markdown_calendar(year, month, classified, all_events)
        md_path = OUTPUT_DIR / f"{month_str}_calendar.md"
        md_path.write_text(md, encoding="utf-8")
        print(f"\n  [OK] Calendar: {md_path}")

    if args.output in ("all", "predictions"):
        pred_md = generate_predictions_markdown(year, month, predictions, classified)
        pred_path = OUTPUT_DIR / f"{month_str}_predictions.md"
        pred_path.write_text(pred_md, encoding="utf-8")
        print(f"  [OK] Predictions: {pred_path}")

    if args.output in ("all", "html"):
        html = generate_html_calendar(year, month, classified)
        html_path = OUTPUT_DIR / f"{month_str}_calendar.html"
        html_path.write_text(html, encoding="utf-8")
        print(f"  [OK] HTML Calendar: {html_path}")

    print(f"\n[Done] Calendar generation complete.")


if __name__ == "__main__":
    main()
