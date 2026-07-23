"""
build_site.py — Generate the mobile-first GitHub Pages portal from all reports.

Scans reports/, companies/, and calendar data, then generates:
  - docs/index.html     — mobile dashboard (calendar + predictions + report cards)
  - docs/manifest.json  — PWA manifest
  - docs/sw.js          — service worker for offline caching

Usage:
    python scripts/build_site.py
"""

import json
import re
import sys
import warnings
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REPORTS_DIR = PROJECT_ROOT / "reports"
CALENDAR_DIR = REPORTS_DIR / "calendar"
COMPANIES_DIR = PROJECT_ROOT / "companies"
DOCS_DIR = PROJECT_ROOT / "docs"

SITE_TITLE = "AI Investment Research"
SITE_DESC = "AI-powered investment research portal — earnings calendar, predictions, and company reports."


# ── Markdown to HTML Renderer ────────────────────────────────────────────────

def _md_to_html(md_text: str, file_path: str = "") -> str:
    """Convert Obsidian-flavored markdown to styled HTML.

    Handles: YAML frontmatter, [[wikilinks]], > [!callout] blocks,
    markdown tables, headings, bold/italic, lists, code, hr, blockquotes.
    """
    # Split frontmatter from body
    meta: dict[str, str] = {}
    body = md_text
    if md_text.startswith("---"):
        parts = md_text.split("---", 2)
        if len(parts) >= 3:
            for line in parts[1].strip().split("\n"):
                if ":" in line:
                    k, _, v = line.partition(":")
                    meta[k.strip()] = v.strip().strip('"')
            body = "---" + parts[2]

    # ── Pre-processing: Obsidian-specific syntax ──

    # Convert [[wikilinks]] to links
    def _wikilink(m):
        target = m.group(1)
        # Split alias: [[Target|Alias]]
        if "|" in target:
            target, alias = target.split("|", 1)
            return f'<a href="../companies/{target.strip()}.html">{alias.strip()}</a>'
        return f'<a href="../companies/{target.strip()}.html">{target.strip()}</a>'

    body = re.sub(r"\[\[([^\]]+)\]\]", _wikilink, body)

    # ── Inner: inline formatting ──
    def _inline(text: str) -> str:
        """Convert inline markdown: bold, italic, code, links, images."""
        text = re.sub(r"!\[([^\]]*)\]\(([^)]+)\)", r'<img src="\2" alt="\1">', text)
        text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r'<a href="\2">\1</a>', text)
        text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
        text = re.sub(r"\*([^*]+)\*", r"<em>\1</em>", text)
        text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
        return text

    def _escape_html(text: str) -> str:
        return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

    # ── Inner: body converter (must be defined before _callout) ──
    def _convert_body(text: str) -> str:
        lines = text.split("\n")
        out: list[str] = []
        in_table = False
        in_code = False
        in_list: str | bool = False
        i = 0

        while i < len(lines):
            line = lines[i]
            stripped = line.strip()

            if stripped.startswith("```"):
                if in_code:
                    out.append("</code></pre>")
                    in_code = False
                else:
                    out.append('<pre><code>')
                    in_code = True
                i += 1
                continue
            if in_code:
                out.append(_escape_html(line))
                i += 1
                continue

            if stripped in ("---", "***", "___", "* * *"):
                out.append("<hr>")
                i += 1
                continue

            if "|" in stripped and not stripped.startswith(">"):
                if not in_table:
                    in_table = True
                    out.append('<table class="md-table">')
                if re.match(r'^[\|\s\-:]+$', stripped):
                    i += 1
                    continue
                cells = [c.strip() for c in stripped.strip("|").split("|")]
                # Check if next line is separator
                is_header = (i + 1 < len(lines) and
                             re.match(r'^[\|\s\-:]+$', lines[i+1].strip()))
                tag = "th" if is_header else "td"
                out.append("<tr>" + "".join(f"<{tag}>{_inline(c)}</{tag}>" for c in cells) + "</tr>")
                i += 1
                if i >= len(lines) or "|" not in lines[i]:
                    out.append("</table>")
                    in_table = False
                continue

            if in_table:
                out.append("</table>")
                in_table = False

            h_match = re.match(r"^(#{1,6})\s+(.+)", stripped)
            if h_match:
                level = len(h_match.group(1))
                out.append(f"<h{level}>{_inline(h_match.group(2))}</h{level}>")
                i += 1
                continue

            if stripped.startswith("> ") and "[!" not in stripped:
                content = stripped[2:]
                j = i + 1
                while j < len(lines) and lines[j].strip().startswith("> "):
                    content += "<br>" + lines[j].strip()[2:]
                    j += 1
                out.append(f"<blockquote>{_inline(content)}</blockquote>")
                i = j
                continue

            ul_match = re.match(r"^(\s*)[-*+]\s+(.+)", stripped)
            if ul_match:
                if in_list != "ul":
                    if in_list:
                        out.append(f"</{in_list}>")
                    out.append("<ul>")
                    in_list = "ul"
                out.append(f"<li>{_inline(ul_match.group(2))}</li>")
                i += 1
                continue

            ol_match = re.match(r"^(\s*)\d+\.\s+(.+)", stripped)
            if ol_match:
                if in_list != "ol":
                    if in_list:
                        out.append(f"</{in_list}>")
                    out.append("<ol>")
                    in_list = "ol"
                out.append(f"<li>{_inline(ol_match.group(2))}</li>")
                i += 1
                continue

            if in_list and not stripped:
                out.append(f"</{in_list}>")
                in_list = False

            if not stripped:
                out.append("")
                i += 1
                continue

            out.append(f"<p>{_inline(stripped)}</p>")
            i += 1

        if in_table:
            out.append("</table>")
        if in_list:
            out.append(f"</{in_list}>")
        if in_code:
            out.append("</code></pre>")
        return "\n".join(out)

    # Convert Obsidian callouts to styled divs
    def _callout(m):
        ctype = m.group(1).lower()
        title = (m.group(2) or ctype.capitalize()).strip()
        # Strip collapsible marker (+/-) from title
        if title and title[0] in "+-":
            title = title[1:].strip()
        content = m.group(3)
        # Map callout types to colors/emoji
        type_map = {
            "abstract": ("📋", "#58a6ff"), "info": ("ℹ️", "#58a6ff"),
            "example": ("📊", "#3fb950"), "warning": ("⚠️", "#d2991d"),
            "tip": ("💡", "#3fb950"), "quote": ("💬", "#8b949e"),
            "question": ("❓", "#d2a850"), "note": ("📝", "#58a6ff"),
            "success": ("✅", "#3fb950"), "danger": ("🚨", "#f85149"),
        }
        emoji, color = type_map.get(ctype, ("📌", "#8b949e"))
        # Strip '> ' prefix from each line, then convert inner markdown
        stripped_lines = []
        for line in content.split("\n"):
            s = line.strip()
            if s.startswith("> "):
                stripped_lines.append(s[2:])
            elif s == ">":
                stripped_lines.append("")
            else:
                stripped_lines.append(s)
        inner = _convert_body("\n".join(stripped_lines))
        return (
            f'<div class="callout callout-{ctype}" style="border-left:3px solid {color}">'
            f'<div class="callout-title">{emoji} {title}</div>'
            f'<div class="callout-body">{inner}</div></div>'
        )

    body = re.sub(
        r'>\s*\[!(\w+)\]\s*([+-]?\s*[^\n]*)?\n((?:>\s?[^\n]*\n?)+)',
        _callout, body,
    )

    # ── Build final HTML page ──
    html_body = _convert_body(body)

    title = meta.get("title", meta.get("ticker", "Report"))
    ticker = meta.get("ticker", "")
    date_str = meta.get("date", "")

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title}</title>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
    --buy: #3fb950; --sell: #f85149; --hold: #d2991d;
    --callout-abstract: #1a2a3a; --callout-info: #1a2a3a;
    --callout-warning: #2a1a0a; --callout-tip: #1a2a1a;
    --callout-quote: #1a1a2a;
    --h1: #fff; --h2: #e0e0e0; --strong: #fff;
  }}
  [data-theme="light"] {{
    --bg: #ffffff; --card: #f6f8fa; --border: #d0d7de;
    --text: #1f2328; --muted: #656d76; --accent: #0969da;
    --buy: #1a7f37; --sell: #cf222e; --hold: #9a6700;
    --callout-abstract: #f0f6fc; --callout-info: #f0f6fc;
    --callout-warning: #fff8e1; --callout-tip: #e6f6e6;
    --callout-quote: #f3f4f6;
    --h1: #1f2328; --h2: #2f3640; --strong: #1f2328;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 720px; margin: 0 auto; padding: 16px;
    line-height: 1.6;
  }}
  /* Theme toggle */
  .theme-toggle {{
    position: fixed; top: 12px; right: 12px; z-index: 999;
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--card); border: 1px solid var(--border);
    color: var(--text); font-size: 1.2em; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    transition: transform 0.2s;
  }}
  .theme-toggle:active {{ transform: scale(0.9); }}
  h1 {{ font-size:1.4em; color:var(--h1); margin:16px 0 8px; }}
  h2 {{ font-size:1.15em; color:var(--h2); margin:20px 0 8px; border-bottom:1px solid var(--border); padding-bottom:4px; }}
  h3 {{ font-size:1em; color:var(--h2); margin:14px 0 4px; }}
  h4, h5, h6 {{ font-size:0.9em; color:var(--muted); margin:10px 0 4px; }}
  p {{ margin:6px 0; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  strong {{ color: var(--strong); }}
  em {{ color: var(--muted); }}
  code {{ background:var(--card); padding:1px 5px; border-radius:3px; font-size:0.85em; }}
  pre {{ background:var(--card); padding:12px; border-radius:6px; overflow-x:auto; margin:8px 0; }}
  pre code {{ background:none; padding:0; }}
  blockquote {{ border-left:3px solid var(--border); padding:4px 12px; margin:8px 0; color:var(--muted); }}
  hr {{ border:none; border-top:1px solid var(--border); margin:16px 0; }}
  ul, ol {{ padding-left:24px; margin:8px 0; }}
  li {{ margin:3px 0; }}

  /* Tables */
  .md-table {{ width:100%; border-collapse:collapse; margin:10px 0; font-size:0.85em; }}
  .md-table th {{ background:var(--card); color:var(--strong); padding:8px 10px; text-align:left;
    border:1px solid var(--border); font-weight:600; }}
  .md-table td {{ padding:6px 10px; border:1px solid var(--border); }}
  .md-table tr:nth-child(even) {{ background:var(--bg); }}

  /* Callouts */
  .callout {{
    border-radius: 6px; margin: 12px 0; padding: 12px 14px;
    background: var(--card);
  }}
  .callout-title {{ font-weight:700; margin-bottom:6px; font-size:0.9em; }}
  .callout-body {{ font-size:0.88em; }}
  .callout-body p {{ margin:4px 0; }}
  .callout-body ul, .callout-body ol {{ margin:4px 0; padding-left:20px; }}
  .callout-warning {{ background:var(--callout-warning); }}
  .callout-tip, .callout-success {{ background:var(--callout-tip); }}
  .callout-quote {{ background:var(--callout-quote); font-style:italic; }}
  .callout-abstract {{ background:var(--callout-abstract); }}
  .callout-info {{ background:var(--callout-info); }}
  .callout-example {{ background:var(--callout-info); }}

  /* Metadata header */
  .meta-header {{
    background:var(--card); border-radius:8px; padding:12px 16px;
    margin-bottom:16px; font-size:0.82em; color:var(--muted);
  }}
  .meta-header span {{ margin-right:16px; }}

  /* Back link */
  .back-link {{
    display:inline-block; margin-bottom:16px; font-size:0.82em;
    color:var(--accent);
  }}

  /* Responsive */
  @media (max-width:500px) {{
    body {{ padding:10px; font-size:0.9em; }}
    h1 {{ font-size:1.2em; }}
    .md-table {{ font-size:0.7em; }}
  }}
</style>
</head>
<body>
<button class="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode" id="themeBtn">☀️</button>
<a class="back-link" href="javascript:history.back()">← Back</a>
<div class="meta-header">
  <span><strong>{ticker}</strong></span>
  <span>{meta.get('company', '')}</span>
  <span>{meta.get('sector', '')}</span>
  <span>{date_str}</span>
</div>
{html_body}
<a class="back-link" href="javascript:history.back()" style="margin-top:24px;display:block;">← Back</a>

<script>
  (function() {{
    var theme = localStorage.getItem('theme');
    if (theme === 'light') {{
      document.documentElement.setAttribute('data-theme', 'light');
      document.getElementById('themeBtn').textContent = '🌙';
    }}
  }})();
  function toggleTheme() {{
    var isLight = document.documentElement.getAttribute('data-theme') === 'light';
    if (isLight) {{
      document.documentElement.removeAttribute('data-theme');
      document.getElementById('themeBtn').textContent = '☀️';
      localStorage.setItem('theme', 'dark');
    }} else {{
      document.documentElement.setAttribute('data-theme', 'light');
      document.getElementById('themeBtn').textContent = '🌙';
      localStorage.setItem('theme', 'light');
    }}
  }}
</script>

</body>
</html>"""


# ── Data Extraction ────────────────────────────────────────────────────────────

def extract_report_meta(path: Path) -> dict | None:
    """Extract frontmatter + key sections from a report markdown file."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return None

    meta: dict[str, str] = {}
    lines = text.split("\n")

    # Parse YAML frontmatter
    in_frontmatter = False
    fm_lines = 0
    for line in lines:
        if line.strip() == "---" and fm_lines == 0:
            in_frontmatter = True
            continue
        if line.strip() == "---" and in_frontmatter:
            break
        if in_frontmatter and ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"')
            meta[key] = val

    if not meta.get("ticker"):
        return None

    # Extract rating from recommendation callout
    rating = "—"
    target = "—"
    in_rec = False
    for line in lines:
        if "> [!quote] Recommendation" in line:
            in_rec = True
            continue
        if in_rec:
            if "**BUY**" in line.upper() or "Buy" in line:
                rating = "BUY"
            elif "**SELL**" in line.upper() or "Sell" in line:
                rating = "SELL"
            elif "**HOLD**" in line.upper() or "Hold" in line:
                rating = "HOLD"
            if "Price Target" in line or "price target" in line.lower():
                target = line.split("$")[-1].split(")")[0].split("*")[0].strip()[:20]
            if rating != "—" and target != "—":
                break

    # Convert .md path to .html for web links
    web_path = path.relative_to(PROJECT_ROOT).as_posix().replace(".md", ".html")

    return {
        "ticker": meta.get("ticker", "?"),
        "company": meta.get("company", meta.get("ticker", "?")),
        "sector": meta.get("sector", "—"),
        "date": meta.get("date", "?"),
        "rating": rating,
        "target": target,
        "path": web_path,
        "is_cn": "_cn" in path.stem,
    }


def scan_reports() -> list[dict]:
    """Scan all report files and extract metadata."""
    reports = []
    for f in sorted(REPORTS_DIR.glob("*_report_*.md"), reverse=True):
        # Skip prompts, skip calendar dir
        if "_prompt_" in f.name:
            continue
        meta = extract_report_meta(f)
        if meta:
            reports.append(meta)
    return reports


def scan_calendar() -> dict | None:
    """Find the latest calendar HTML and prediction MD."""
    calendars = sorted(CALENDAR_DIR.glob("*_calendar.html"), reverse=True)
    predictions = sorted(CALENDAR_DIR.glob("*_predictions.md"), reverse=True)

    result = {}
    if calendars:
        result["calendar_html"] = calendars[0].relative_to(PROJECT_ROOT).as_posix()
        result["calendar_month"] = calendars[0].stem.replace("_calendar", "")
    if predictions:
        result["predictions_md"] = predictions[0].relative_to(PROJECT_ROOT).as_posix().replace(".md", ".html")
    return result if result else None


def scan_tracked_companies() -> list[dict]:
    """Get list of companies with research files."""
    companies = []
    for f in sorted(COMPANIES_DIR.glob("*.md")):
        ticker = f.stem
        # Quick read for company name from first heading
        try:
            first_line = f.read_text(encoding="utf-8").split("\n")[0].strip("# ")
        except Exception:
            first_line = ticker
        companies.append({
            "ticker": ticker,
            "name": first_line.replace(f"# {ticker} — ", "").strip() or ticker,
            "path": f.relative_to(PROJECT_ROOT).as_posix(),
        })
    return companies


# ── Live Prices ──────────────────────────────────────────────────────────────

def fetch_live_prices(tickers: list[str]) -> dict[str, dict]:
    """Get real-time quotes via data_engine (OpenBB FMP integration)."""
    import warnings
    warnings.filterwarnings("ignore")
    try:
        from src.data_engine import get_quote
    except Exception:
        return {}
    prices: dict[str, dict] = {}
    for t in tickers[:18]:
        try:
            q = get_quote(t)
            if not q.empty:
                row = q.iloc[0]
                chg_pct_raw = row.get("change_percent", 0) or 0
                prices[t] = {
                    "price": row.get("last_price", 0) or 0,
                    "change_pct": round(float(chg_pct_raw) * 100, 2),
                    "market_cap": row.get("market_cap", 0) or 0,
                }
        except Exception:
            pass
    return prices


def extract_mega_events(calendar: dict | None) -> list[dict]:
    """Extract mega-cap earnings events for this week from calendar data."""
    if not calendar:
        return []
    # Read the calendar HTML to extract mega events
    cal_html = calendar.get("calendar_html", "")
    if not cal_html:
        return []
    cal_path = PROJECT_ROOT / cal_html
    if not cal_path.exists():
        return []

    mega = []
    now = datetime.now()
    try:
        # Parse calendar HTML for mega-cap events (className 'mega')
        html = cal_path.read_text(encoding="utf-8")
        # Extract calendar data from the embedded JSON
        match = re.search(r"const CALENDAR_DATA\s*=\s*({.*?});", html, re.DOTALL)
        if match:
            data = json.loads(match.group(1))
            for date_str, events in data.items():
                try:
                    ev_date = datetime.strptime(date_str, "%Y-%m-%d")
                except ValueError:
                    continue
                if ev_date < now:
                    continue  # past
                for ev in events:
                    if ev.get("importance", 0) >= 3:
                        mega.append({
                            "date": date_str,
                            "symbol": ev["symbol"],
                            "eps": ev.get("eps", "?"),
                        })
        # Sort by date, take top 8
        mega.sort(key=lambda x: x["date"])
    except Exception:
        pass
    return mega[:8]


# ── HTML Generation Helpers ──────────────────────────────────────────────────

def _build_mega_alert(mega_events: list[dict], prices: dict, T) -> str:
    """Build dynamic mega-cap earnings alert HTML."""
    if not mega_events:
        return '<div class="alert"><div class="alert-title">⚠️ No mega-cap events in data</div></div>'
    chips = ""
    for ev in mega_events[:6]:
        sym = ev["symbol"]
        p = prices.get(sym, {})
        chg = p.get("change_pct", 0)
        chg_sign = "📈" if chg > 0 else "📉" if chg < 0 else ""
        chips += f'<a href="companies/{sym}.html" class="alert-chip">{sym} {ev["date"][5:]} {chg_sign}</a>\n'
    return f'<div class="alert"><div class="alert-title">⚠️ {T("High-Impact Events", "高影响力事件")}</div><div class="alert-items">{chips}</div></div>'


def _build_mini_calendar(calendar: dict | None, T) -> str:
    """Build a 'This Week' mini calendar from calendar data."""
    if not calendar:
        return "<p>No calendar data available.</p>"

    cal_html = calendar.get("calendar_html", "")
    cal_path = PROJECT_ROOT / cal_html
    if not cal_path.exists():
        return "<p>Calendar data not found.</p>"

    today = datetime.now()
    rows = ""
    for offset in range(7):
        d = today + timedelta(days=offset)
        date_str = d.strftime("%Y-%m-%d")
        day_name = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"][d.weekday()]
        rows += f"<div class='mini-day'><span class='mini-date'>{d.day} {day_name[:3]}</span></div>"

    return f'<div class="mini-cal">{rows}</div>'


# ── HTML Generation ────────────────────────────────────────────────────────────

def build_index_html(
    reports: list[dict],
    calendar: dict | None,
    tracked: list[dict],
    lang: str = "en",
    prices: dict[str, dict] | None = None,
    mega_events: list[dict] | None = None,
) -> str:
    """Generate the mobile-first portal index.html.

    Args:
        lang: 'en' for English, 'cn' for Chinese UI.
        prices: Optional live price data keyed by ticker.
        mega_events: Optional mega-cap earnings events.
    """
    if prices is None:
        prices = {}
    if mega_events is None:
        mega_events = []

    C = lang == "cn"  # Chinese mode
    T = lambda en, cn: cn if C else en

    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Group reports: use appropriate language versions
    ticker_latest: dict[str, dict] = {}
    for r in reports:
        if C:
            if not r["is_cn"]:
                continue
        else:
            if r["is_cn"]:
                continue
        t = r["ticker"]
        if t not in ticker_latest:
            ticker_latest[t] = r
    latest_reports = sorted(ticker_latest.values(), key=lambda x: x["date"], reverse=True)
    if not latest_reports and C:
        for r in reports:
            if r["is_cn"]:
                continue
            t = r["ticker"]
            if t not in ticker_latest:
                ticker_latest[t] = r
        latest_reports = sorted(ticker_latest.values(), key=lambda x: x["date"], reverse=True)

    # Build report cards HTML
    report_cards = ""
    for r in latest_reports[:20]:
        rating_class = {
            "BUY": "buy", "SELL": "sell", "HOLD": "hold",
        }.get(r["rating"], "")
        p = prices.get(r["ticker"], {})
        price_str = f"${p.get('price', 0):.2f}" if p.get("price") else "—"
        chg = p.get("change_pct", 0)
        chg_str = f"<span class='rc-chg {'up' if chg >= 0 else 'down'}'>{chg:+.1f}%</span>" if p else ""
        mcap = p.get("market_cap", 0)
        mcap_str = f"${mcap/1e9:.0f}B" if mcap > 0 else ""
        cn_href = r["path"].replace(".html", "_cn.html")
        report_cards += f"""
        <a href="{r['path']}" class="report-card" data-en-href="{r['path']}" data-cn-href="{cn_href}">
          <div class="rc-header">
            <span class="rc-ticker">{r['ticker']}</span>
            <span class="rc-price">{price_str}</span>
          </div>
          <div class="rc-name" data-en="{r['company'][:30]}" data-cn="">{r['company'][:30]}</div>
          <div class="rc-meta">
            <span class="rating {rating_class}">{r['rating']}</span>
            <span class="target">🎯 ${r['target']}</span>
            {chg_str}
          </div>
          <div class="rc-footer">
            <span class="rc-mcap">{mcap_str}</span>
            <span class="rc-date">{r['date']}</span>
          </div>
        </a>"""

    # Build economic events HTML
    econ_html = ""
    if calendar:
        econ_html = f"""
        <a href="{calendar.get('calendar_html', '#')}" class="card-link">
          <div class="quick-card">
            <div class="qc-icon">📅</div>
            <div class="qc-text">
              <div class="qc-title">{T('Earnings Calendar', '财报日历')}</div>
              <div class="qc-sub">{calendar.get('calendar_month', T('Current', '当前'))}</div>
            </div>
            <div class="qc-arrow">→</div>
          </div>
        </a>"""
        if calendar.get("predictions_md"):
            econ_html += f"""
        <a href="{calendar['predictions_md']}" class="card-link">
          <div class="quick-card">
            <div class="qc-icon">🔮</div>
            <div class="qc-text">
              <div class="qc-title">{T('AI Predictions', 'AI预测')}</div>
              <div class="qc-sub">{T('DeepSeek-generated forecasts', 'DeepSeek AI 生成预测')}</div>
            </div>
            <div class="qc-arrow">→</div>
          </div>
        </a>"""

    # Build tracked companies quick links
    tracked_html = ""
    for c in sorted(tracked, key=lambda x: x["ticker"]):
        cn_file = COMPANIES_DIR / f"{c['ticker']}.md"
        has_report = cn_file.exists()
        cls = "has-report" if has_report else ""
        tracked_html += f'<a href="companies/{c["ticker"]}.html" class="tracked-chip {cls}">{c["ticker"]}</a>\n'

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, viewport-fit=cover">
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
<title>{SITE_TITLE}</title>
<meta name="description" content="{SITE_DESC}">
<meta name="theme-color" content="#0d1117">
<meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
<meta name="apple-mobile-web-app-title" content="AI Invest">
<link rel="manifest" href="manifest.json">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>">
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --border: #30363d;
    --text: #c9d1d9; --muted: #8b949e; --accent: #58a6ff;
    --buy: #3fb950; --sell: #f85149; --hold: #d2991d;
    --mega: #f78166; --large: #d2a850;
    --h1: #fff; --h2: #e0e0e0;
  }}
  [data-theme="light"] {{
    --bg: #ffffff; --card: #f6f8fa; --border: #d0d7de;
    --text: #1f2328; --muted: #656d76; --accent: #0969da;
    --buy: #1a7f37; --sell: #cf222e; --hold: #9a6700;
    --mega: #cf222e; --large: #bf8700;
    --h1: #1f2328; --h2: #2f3640;
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 1200px; margin: 0 auto; padding: 16px;
    -webkit-font-smoothing: antialiased;
  }}
  @media (min-width: 900px) {{
    body {{ padding: 24px 32px; }}
    .report-grid {{ grid-template-columns: repeat(3, 1fr); }}
    .quick-card {{ max-width: 500px; }}
  }}
  @media (min-width: 600px) and (max-width: 899px) {{
    .report-grid {{ grid-template-columns: repeat(2, 1fr); }}
  }}
  header {{ text-align: center; padding: 24px 0 12px; position:relative; }}
  header h1 {{ font-size: 1.3em; color: var(--h1); }}
  header .sub {{ font-size: 0.8em; color: var(--muted); margin-top: 4px; }}
  /* Theme toggle */
  .theme-toggle {{
    position: fixed; top: 12px; right: 12px; z-index: 999;
    width: 40px; height: 40px; border-radius: 50%;
    background: var(--card); border: 1px solid var(--border);
    color: var(--text); font-size: 1.2em; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
    box-shadow: 0 2px 8px rgba(0,0,0,0.15);
    transition: transform 0.2s;
  }}
  .theme-toggle:active {{ transform: scale(0.9); }}

  /* Lang Toggle */
  .lang-toggle {{
    position: absolute; top: 8px; left: 8px;
    background: var(--card); border: 1px solid var(--border);
    color: var(--text); padding: 4px 10px; border-radius: 16px;
    font-size: 0.75em; cursor: pointer; z-index: 10;
    transition: background 0.2s;
  }}
  .lang-toggle:active {{ background: var(--border); }}
  @media (max-width: 400px) {{
    .lang-toggle {{ font-size: 0.7em; padding: 3px 8px; }}
  }}

  .section-title {{
    font-size: 0.85em; font-weight: 600; color: var(--muted);
    text-transform: uppercase; letter-spacing: 0.5px;
    margin: 20px 0 8px; padding-bottom: 6px; border-bottom: 1px solid var(--border);
  }}

  /* Quick Cards */
  .quick-card {{
    display: flex; align-items: center; background: var(--card);
    padding: 14px 16px; border-radius: 10px; margin-bottom: 8px;
    border: 1px solid var(--border); transition: all 0.15s;
  }}
  .card-link {{ text-decoration: none; color: inherit; }}
  .quick-card:active {{ background: #1c2333; transform: scale(0.99); }}
  .qc-icon {{ font-size: 1.6em; margin-right: 14px; }}
  .qc-text {{ flex:1; }}
  .qc-title {{ font-size: 0.95em; color: var(--h1); font-weight: 600; }}
  .qc-sub {{ font-size: 0.78em; color: var(--muted); margin-top: 2px; }}
  .qc-arrow {{ color: var(--muted); font-size: 1.2em; }}

  /* Alert Banner */
  .alert {{
    background: linear-gradient(135deg, #1a0a0a 0%, #2a1010 100%);
    border: 1px solid #5a2020; border-radius: 10px; padding: 14px 16px;
    margin-bottom: 10px;
  }}
  .alert-title {{ color: var(--mega); font-weight: 700; font-size: 0.85em; margin-bottom: 6px; }}
  .alert-items {{ display: flex; flex-wrap: wrap; gap: 6px; }}
  .alert-chip {{
    background: #2a1515; color: #f78166; padding: 4px 8px;
    border-radius: 5px; font-size: 0.75em; font-weight: 600;
    text-decoration: none;
  }}

  /* Search */
  .search-wrap {{ margin: 10px 0; }}
  .search-box {{
    width: 100%; padding: 10px 14px; border-radius: 10px;
    background: var(--card); color: var(--text); border: 1px solid var(--border);
    font-size: 0.9em; outline: none; transition: border 0.2s;
  }}
  .search-box:focus {{ border-color: var(--accent); }}
  .search-box::placeholder {{ color: var(--muted); }}

  /* Report Cards */
  .report-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .report-card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 10px; text-decoration: none; color: inherit;
    transition: all 0.15s;
  }}
  .report-card:active {{ background: #1c2333; }}
  .report-card.hidden {{ display: none; }}
  .rc-header {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 2px; }}
  .rc-ticker {{ font-weight: 800; color: var(--accent); font-size: 0.85em; }}
  .rc-price {{ font-size: 0.78em; color: var(--text); font-weight: 600; }}
  .rc-name {{ font-size: 0.7em; color: var(--muted); margin: 2px 0 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .rc-meta {{ display: flex; gap: 4px; align-items: center; flex-wrap: wrap; }}
  .rating {{ font-size: 0.65em; font-weight: 700; padding: 1px 5px; border-radius: 3px; }}
  .rating.buy {{ background: #1a3a1a; color: var(--buy); }}
  .rating.sell {{ background: #3a1a1a; color: var(--sell); }}
  .rating.hold {{ background: #3a2a0a; color: var(--hold); }}
  .target {{ font-size: 0.65em; color: var(--muted); }}
  .rc-chg {{ font-size: 0.65em; font-weight: 600; }}
  .rc-chg.up {{ color: var(--buy); }}
  .rc-chg.down {{ color: var(--sell); }}
  .rc-footer {{ display: flex; justify-content: space-between; margin-top: 4px; }}
  .rc-mcap {{ font-size: 0.62em; color: var(--muted); }}
  .rc-date {{ font-size: 0.6em; color: var(--muted); }}

  /* Mini Calendar */
  .mini-cal {{ display: flex; gap: 4px; overflow-x: auto; padding: 4px 0; }}
  .mini-day {{
    flex: 0 0 44px; text-align: center; background: var(--card);
    border-radius: 8px; padding: 6px 2px; font-size: 0.7em;
    border: 1px solid var(--border);
  }}
  .mini-date {{ font-weight: 700; color: var(--accent); }}

  /* Bottom Nav */
  .bottom-nav {{
    position: fixed; bottom: 0; left: 50%; transform: translateX(-50%);
    max-width: 600px; width: 100%;
    display: flex; justify-content: space-around;
    background: var(--card); border-top: 1px solid var(--border);
    padding: 6px 0 env(safe-area-inset-bottom, 6px);
    z-index: 998;
  }}
  .nav-item {{
    display: flex; flex-direction: column; align-items: center;
    text-decoration: none; color: var(--muted); font-size: 0.65em;
    padding: 4px 12px; border-radius: 8px; transition: all 0.15s;
  }}
  .nav-item.active {{ color: var(--accent); }}
  .nav-item:active {{ background: var(--bg); }}
  .nav-icon {{ font-size: 1.4em; }}
  .nav-label {{ margin-top: 1px; }}

  /* Tracked Chips */
  .chip-row {{ display: flex; flex-wrap: wrap; gap: 5px; }}
  .tracked-chip {{
    background: var(--card); border: 1px solid var(--border);
    padding: 5px 10px; border-radius: 16px; font-size: 0.72em;
    text-decoration: none; color: var(--text); font-weight: 600;
    transition: all 0.15s;
  }}
  .tracked-chip.has-report {{ border-color: var(--accent); }}
  .tracked-chip:active {{ background: #1c2333; }}

  /* Bottom */
  .footer {{ text-align: center; padding: 24px 0; font-size: 0.7em; color: var(--muted); }}
</style>
</head>
<body>

<button class="theme-toggle" onclick="toggleTheme()" title="Toggle light/dark mode" id="themeBtn">☀️</button>

<header>
  <h1 data-en="📊 {SITE_TITLE}" data-cn="📊 AI投资研究">📊 {SITE_TITLE}</h1>
  <div class="sub" data-en="{T('Updated:', '更新：')} {now} · {len(latest_reports)} {T('reports', '份报告')} · {len(tracked)} {T('companies tracked', '家公司追踪')}"
       data-cn="更新：{now} · {len(latest_reports)} 份报告 · {len(tracked)} 家公司追踪">
    {T('Updated:', '更新：')} {now} · {len(latest_reports)} {T('reports', '份报告')} · {len(tracked)} {T('companies tracked', '家公司追踪')}
  </div>
  <!-- Language Toggle -->
  <button class="lang-toggle" onclick="toggleLang()" id="langBtn" title="Switch language">
    <span class="lang-flag">🇨🇳</span> <span data-en="中文" data-cn="English">中文</span>
  </button>
</header>

<!-- Search Bar -->
<div class="search-wrap">
  <input type="text" class="search-box" id="searchBox"
    placeholder="{T('Search ticker or company...', '搜索股票代码或公司...')}"
    oninput="filterReports()" autocomplete="off">
</div>

<!-- Dynamic Mega-Cap Earnings Alert -->
<section>
  <div class="section-title" data-en="🔥 Mega-Cap Earnings This Week" data-cn="🔥 本周重磅财报">🔥 {T('Mega-Cap Earnings This Week', '本周重磅财报')}</div>
  {_build_mega_alert(mega_events, prices, T)}
</section>

<!-- Mini Calendar: This Week -->
<section>
  <div class="section-title" data-en="📅 This Week" data-cn="📅 本周">📅 {T('This Week', '本周')}</div>
  {_build_mini_calendar(calendar, T)}
</section>

<!-- Calendar + Predictions links -->
<section>
  {econ_html}
</section>

<!-- Latest Reports -->
<section>
  <div class="section-title" data-en="📑 Latest Research Reports" data-cn="📑 最新研究报告">📑 {T('Latest Research Reports', '最新研究报告')}</div>
  <div class="report-grid" id="reportGrid">
    {report_cards}
  </div>
</section>

<!-- Tracked Companies -->
<section>
  <div class="section-title" data-en="🏢 Tracked Companies ({len(tracked)})" data-cn="🏢 追踪公司 ({len(tracked)})">🏢 {T('Tracked Companies', '追踪公司')} ({len(tracked)})</div>
  <div class="chip-row" id="chipRow">
    {tracked_html}
  </div>
</section>

<div style="height:80px"></div><!-- spacer for bottom nav -->

<!-- Bottom Navigation Bar -->
<nav class="bottom-nav">
  <a href="index.html" class="nav-item active">
    <span class="nav-icon">🏠</span>
    <span class="nav-label">{T('Home', '首页')}</span>
  </a>
  <a href="reports/calendar/2026-07_calendar.html" class="nav-item">
    <span class="nav-icon">📅</span>
    <span class="nav-label">{T('Calendar', '日历')}</span>
  </a>
  <a href="reports/calendar/2026-07_predictions.html" class="nav-item">
    <span class="nav-icon">🔮</span>
    <span class="nav-label">{T('Predict', '预测')}</span>
  </a>
  <a href="javascript:toggleLang()" class="nav-item" id="navLang">
    <span class="nav-icon" id="langIcon">🇨🇳</span>
    <span class="nav-label" id="langLabel" data-en="中文" data-cn="English">中文</span>
  </a>
</nav>

<div class="footer">
  <span data-en="AI Investment Research System" data-cn="AI投资研究系统">AI Investment Research System</span> · Generated {now}<br>
  <a href="https://github.com" style="color:var(--accent)">{T('View on GitHub', '在 GitHub 上查看')}</a>
</div>

<script>
  // Search filter
  function filterReports() {{
    var q = (document.getElementById('searchBox').value || '').toUpperCase();
    document.querySelectorAll('.report-card').forEach(function(c) {{
      var t = (c.querySelector('.rc-ticker')?.textContent || '').toUpperCase();
      var n = (c.querySelector('.rc-name')?.textContent || '').toUpperCase();
      c.classList.toggle('hidden', q.length > 0 && !t.includes(q) && !n.includes(q));
    }});
    document.querySelectorAll('.tracked-chip').forEach(function(c) {{
      c.style.opacity = (q.length > 0 && !c.textContent.toUpperCase().includes(q)) ? '0.3' : '1';
    }});
  }}

  // Language toggle
  var currentLang = localStorage.getItem('lang') || 'en';
  function applyLang(lang) {{
    currentLang = lang;
    localStorage.setItem('lang', lang);
    // Toggle all [data-en][data-cn] elements
    document.querySelectorAll('[data-en][data-cn]').forEach(function(el) {{
      el.textContent = el.getAttribute('data-' + lang) || el.textContent;
    }});
    // Switch report card links
    document.querySelectorAll('.report-card').forEach(function(card) {{
      var href = card.getAttribute('data-' + lang + '-href');
      if (href) card.setAttribute('href', href);
    }});
    // Update lang button
    var btn = document.getElementById('langBtn');
    var icon = document.getElementById('langIcon');
    var label = document.getElementById('langLabel');
    if (lang === 'cn') {{
      if (btn) btn.innerHTML = '<span class=\"lang-flag\">🇺🇸</span> <span data-en=\"中文\" data-cn=\"English\">English</span>';
      if (icon) icon.textContent = '🇺🇸';
      if (label) label.textContent = 'English';
    }} else {{
      if (btn) btn.innerHTML = '<span class=\"lang-flag\">🇨🇳</span> <span data-en=\"中文\" data-cn=\"English\">中文</span>';
      if (icon) icon.textContent = '🇨🇳';
      if (label) label.textContent = '中文';
    }}
  }}
  function toggleLang() {{
    applyLang(currentLang === 'en' ? 'cn' : 'en');
  }}
  // Apply saved language on load
  if (currentLang === 'cn') applyLang('cn');

  // Theme
  (function() {{
    var theme = localStorage.getItem('theme');
    if (theme === 'light') {{
      document.documentElement.setAttribute('data-theme', 'light');
      document.getElementById('themeBtn').textContent = '🌙';
    }}
  }})();
  function toggleTheme() {{
    var isLight = document.documentElement.getAttribute('data-theme') === 'light';
    if (isLight) {{
      document.documentElement.removeAttribute('data-theme');
      document.getElementById('themeBtn').textContent = '☀️';
      localStorage.setItem('theme', 'dark');
    }} else {{
      document.documentElement.setAttribute('data-theme', 'light');
      document.getElementById('themeBtn').textContent = '🌙';
      localStorage.setItem('theme', 'light');
    }}
  }}

  // Push notification for mega-cap earnings
  if ('Notification' in window && Notification.permission === 'default') {{
    document.addEventListener('click', function once() {{
      Notification.requestPermission();
      document.removeEventListener('click', once);
    }}, {{ once: true }});
  }}

  if ('serviceWorker' in navigator) {{
    navigator.serviceWorker.register('sw.js');
  }}
</script>

</body>
</html>"""


# ── PWA Files ──────────────────────────────────────────────────────────────────

MANIFEST_JSON = """{
  "name": "AI Investment Research",
  "short_name": "AI Invest",
  "description": "AI-powered investment research — calendar, predictions, reports",
  "start_url": ".",
  "display": "standalone",
  "background_color": "#0d1117",
  "theme_color": "#0d1117",
  "icons": [
    {"src": "data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📊</text></svg>", "sizes": "any", "type": "image/svg+xml"}
  ]
}"""

SW_JS = """// Service worker — network-first with offline fallback, pre-caches recent pages
const CACHE = 'ai-invest-v3';
const PRE = ['./', 'index.html', 'index_cn.html', 'manifest.json'];

self.addEventListener('install', e => {
  e.waitUntil(caches.open(CACHE).then(c => c.addAll(PRE).catch(() => {})));
  self.skipWaiting();
});
self.addEventListener('activate', e => {
  e.waitUntil(caches.keys().then(keys =>
    Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k)))));
  self.clients.claim();
});
self.addEventListener('fetch', e => {
  if (e.request.method !== 'GET') return;
  e.respondWith(
    fetch(e.request).then(r => {
      if (r.ok && r.type === 'basic') {
        const clone = r.clone();
        caches.open(CACHE).then(c => c.put(e.request, clone));
      }
      return r;
    }).catch(() => caches.match(e.request))
  );
});
"""


# ── Main ────────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Building mobile portal...\n")

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    # 1. Scan data
    print("  [1/4] Scanning reports...")
    reports = scan_reports()
    print(f"    Found {len(reports)} report files")

    print("  [2/4] Scanning calendar...")
    calendar = scan_calendar()
    print(f"    Calendar: {'Yes' if calendar else 'No'}")

    print("  [3/4] Scanning tracked companies...")
    tracked = scan_tracked_companies()
    print(f"    Found {len(tracked)} companies")

    # 2. Generate files
    # 3.5 Fetch live prices and mega events
    print("  [3.5/6] Fetching live prices + mega events...")
    tickers_p = [c["ticker"] for c in tracked]
    prices = fetch_live_prices(tickers_p)
    print(f"    {len(prices)} live prices")
    mega_events = extract_mega_events(calendar)
    print(f"    {len(mega_events)} mega events")

    print("  [4/6] Generating docs/index.html...")
    index_html = build_index_html(reports, calendar, tracked, prices=prices, mega_events=mega_events)
    (DOCS_DIR / "index.html").write_text(index_html, encoding="utf-8")
    print(f"    docs/index.html ({len(index_html):,} bytes)")

    # manifest.json
    (DOCS_DIR / "manifest.json").write_text(MANIFEST_JSON, encoding="utf-8")
    print("    docs/manifest.json")

    # sw.js
    (DOCS_DIR / "sw.js").write_text(SW_JS, encoding="utf-8")
    print("    docs/sw.js")

    # .nojekyll — disable Jekyll processing so .md files are served as-is
    (DOCS_DIR / ".nojekyll").write_text("")
    print("    docs/.nojekyll")

    # 5. Convert all .md files to .html and copy into docs/
    print("  [5/6] Converting .md reports to .html and copying into docs/...")
    import shutil

    # Clean docs/ (keep index.html, manifest.json, sw.js, .nojekyll)
    for item in list(DOCS_DIR.glob("*")):
        if item.name not in ("index.html", "manifest.json", "sw.js", ".nojekyll"):
            if item.is_dir():
                shutil.rmtree(str(item))
            else:
                item.unlink()

    # Convert and copy reports
    docs_reports = DOCS_DIR / "reports"
    docs_reports.mkdir(exist_ok=True)
    for md_file in sorted(REPORTS_DIR.rglob("*.md")):
        rel = md_file.relative_to(REPORTS_DIR)
        dest = docs_reports / rel.with_suffix(".html")
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            raw = md_file.read_text(encoding="utf-8")
            html = _md_to_html(raw, str(rel))
            dest.write_text(html, encoding="utf-8")
        except Exception as e:
            # Fallback: copy raw .md
            import shutil as _shutil
            _shutil.copy2(str(md_file), str(dest.with_suffix(".md")))
            print(f"    ⚠️ {rel}: conversion failed ({e}), copied as .md")
    print(f"    docs/reports/ ({len(list(docs_reports.rglob('*.html')))} .html files)")

    # Copy calendar HTML directly
    cal_src = REPORTS_DIR / "calendar"
    cal_dest = docs_reports / "calendar"
    cal_dest.mkdir(parents=True, exist_ok=True)
    for cal_html in cal_src.glob("*.html"):
        content = cal_html.read_text(encoding="utf-8")
        with open(str(cal_dest / cal_html.name), "w", encoding="utf-8") as f:
            f.write(content)
        print(f"    calendar.html (copied)")

    # Convert and copy companies
    docs_companies = DOCS_DIR / "companies"
    docs_companies.mkdir(exist_ok=True)
    for md_file in sorted(COMPANIES_DIR.glob("*.md")):
        dest = docs_companies / md_file.with_suffix(".html").name
        try:
            raw = md_file.read_text(encoding="utf-8")
            html = _md_to_html(raw, md_file.name)
            dest.write_text(html, encoding="utf-8")
        except Exception:
            import shutil as _shutil
            _shutil.copy2(str(md_file), str(dest.with_suffix(".md")))
    print(f"    docs/companies/ ({len(list(docs_companies.glob('*.html')))} .html files)")

    # 6. Verify links and create CN redirect
    print("  [6/6] Updating links + CN redirect...")
    index_path = DOCS_DIR / "index.html"
    index_content = index_path.read_text(encoding="utf-8")
    index_content = index_content.replace('.md"', '.html"')
    index_path.write_text(index_content, encoding="utf-8")

    # index_cn.html redirects to index.html with CN language
    cn_redirect = '<!DOCTYPE html><html><head><meta charset="UTF-8"><meta http-equiv="refresh" content="0;url=index.html"><script>localStorage.setItem("lang","cn");location.href="index.html";</script></head><body>Redirecting to unified portal...</body></html>'
    (DOCS_DIR / "index_cn.html").write_text(cn_redirect, encoding="utf-8")
    print("    docs/index_cn.html (redirect to unified portal)")

    print(f"\n[Done] Site built in docs/\n")
    print("  Next: git add docs/ && git commit && git push")
    print("  Then: Enable GitHub Pages from docs/ folder in repo settings")


if __name__ == "__main__":
    main()
