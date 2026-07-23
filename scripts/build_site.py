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
from datetime import datetime
from pathlib import Path

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
        title = m.group(2) or ctype.capitalize()
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
        # Recursively process inner content
        inner = _convert_body(content)
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
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 720px; margin: 0 auto; padding: 16px;
    line-height: 1.6;
  }}
  h1 {{ font-size:1.4em; color:#fff; margin:16px 0 8px; }}
  h2 {{ font-size:1.15em; color:#e0e0e0; margin:20px 0 8px; border-bottom:1px solid var(--border); padding-bottom:4px; }}
  h3 {{ font-size:1em; color:#d0d0d0; margin:14px 0 4px; }}
  h4, h5, h6 {{ font-size:0.9em; color:var(--muted); margin:10px 0 4px; }}
  p {{ margin:6px 0; }}
  a {{ color: var(--accent); text-decoration: none; }}
  a:hover {{ text-decoration: underline; }}
  strong {{ color: #fff; }}
  em {{ color: #d0d0d0; }}
  code {{ background:#1c2333; padding:1px 5px; border-radius:3px; font-size:0.85em; }}
  pre {{ background:#1c2333; padding:12px; border-radius:6px; overflow-x:auto; margin:8px 0; }}
  pre code {{ background:none; padding:0; }}
  blockquote {{ border-left:3px solid var(--border); padding:4px 12px; margin:8px 0; color:var(--muted); }}
  hr {{ border:none; border-top:1px solid var(--border); margin:16px 0; }}
  ul, ol {{ padding-left:24px; margin:8px 0; }}
  li {{ margin:3px 0; }}

  /* Tables */
  .md-table {{ width:100%; border-collapse:collapse; margin:10px 0; font-size:0.85em; }}
  .md-table th {{ background:var(--card); color:#fff; padding:8px 10px; text-align:left;
    border:1px solid var(--border); font-weight:600; }}
  .md-table td {{ padding:6px 10px; border:1px solid var(--border); }}
  .md-table tr:nth-child(even) {{ background:#0d1117; }}

  /* Callouts */
  .callout {{
    border-radius: 6px; margin: 12px 0; padding: 12px 14px;
    background: var(--card);
  }}
  .callout-title {{ font-weight:700; margin-bottom:6px; font-size:0.9em; }}
  .callout-body {{ font-size:0.88em; }}
  .callout-body p {{ margin:4px 0; }}
  .callout-body ul, .callout-body ol {{ margin:4px 0; padding-left:20px; }}
  .callout-warning {{ background:#2a1a0a; }}
  .callout-tip, .callout-success {{ background:#1a2a1a; }}
  .callout-quote {{ background:#1a1a2a; font-style:italic; }}

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
<a class="back-link" href="../index.html">← Back to Portal</a>
<div class="meta-header">
  <span><strong>{ticker}</strong></span>
  <span>{meta.get('company', '')}</span>
  <span>{meta.get('sector', '')}</span>
  <span>{date_str}</span>
</div>
{html_body}
<a class="back-link" href="../index.html" style="margin-top:24px;display:block;">← Back to Portal</a>
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
        result["predictions_md"] = predictions[0].relative_to(PROJECT_ROOT).as_posix()
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


# ── HTML Generation ────────────────────────────────────────────────────────────

def build_index_html(
    reports: list[dict],
    calendar: dict | None,
    tracked: list[dict],
) -> str:
    """Generate the mobile-first portal index.html."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    # Group reports: only latest EN version per ticker
    ticker_latest: dict[str, dict] = {}
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
        cn_path = r["path"].replace(".md", "_cn.html")
        report_cards += f"""
        <a href="{r['path']}" class="report-card">
          <div class="rc-ticker">{r['ticker']}</div>
          <div class="rc-name">{r['company'][:30]}</div>
          <div class="rc-meta">
            <span class="rating {rating_class}">{r['rating']}</span>
            <span class="target">🎯 ${r['target']}</span>
          </div>
          <div class="rc-date">{r['date']}</div>
        </a>"""

    # Build economic events HTML
    econ_html = ""
    if calendar:
        econ_html = f"""
        <a href="{calendar.get('calendar_html', '#')}" class="card-link">
          <div class="quick-card">
            <div class="qc-icon">📅</div>
            <div class="qc-text">
              <div class="qc-title">Earnings Calendar</div>
              <div class="qc-sub">{calendar.get('calendar_month', 'Current')}</div>
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
              <div class="qc-title">AI Predictions</div>
              <div class="qc-sub">DeepSeek-generated forecasts</div>
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
  }}
  * {{ margin:0; padding:0; box-sizing:border-box; }}
  body {{
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
    background: var(--bg); color: var(--text);
    max-width: 600px; margin: 0 auto; padding: 16px;
    -webkit-font-smoothing: antialiased;
  }}
  header {{ text-align: center; padding: 24px 0 12px; }}
  header h1 {{ font-size: 1.3em; color: #fff; }}
  header .sub {{ font-size: 0.8em; color: var(--muted); margin-top: 4px; }}

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
  .qc-title {{ font-size: 0.95em; color: #fff; font-weight: 600; }}
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

  /* Report Cards */
  .report-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }}
  .report-card {{
    background: var(--card); border: 1px solid var(--border);
    border-radius: 10px; padding: 12px; text-decoration: none; color: inherit;
    transition: all 0.15s;
  }}
  .report-card:active {{ background: #1c2333; }}
  .rc-ticker {{ font-weight: 800; color: var(--accent); font-size: 0.85em; }}
  .rc-name {{ font-size: 0.72em; color: var(--muted); margin: 2px 0 4px;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }}
  .rc-meta {{ display: flex; gap: 6px; align-items: center; }}
  .rating {{ font-size: 0.68em; font-weight: 700; padding: 1px 6px; border-radius: 3px; }}
  .rating.buy {{ background: #1a3a1a; color: var(--buy); }}
  .rating.sell {{ background: #3a1a1a; color: var(--sell); }}
  .rating.hold {{ background: #3a2a0a; color: var(--hold); }}
  .target {{ font-size: 0.68em; color: var(--muted); }}
  .rc-date {{ font-size: 0.65em; color: var(--muted); margin-top: 4px; }}

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

<header>
  <h1>📊 {SITE_TITLE}</h1>
  <div class="sub">Updated: {now} · {len(latest_reports)} reports · {len(tracked)} companies tracked</div>
</header>

<!-- Mega-Cap Earnings Alert -->
<section>
  <div class="section-title">🔥 Mega-Cap Earnings This Week</div>
  <div class="alert">
    <div class="alert-title">⚠️ High-Impact Events</div>
    <div class="alert-items">
      <a href="companies/INTC.html" class="alert-chip">INTC Jul 23</a>
      <a href="companies/GOOGL.html" class="alert-chip">GOOGL Jul 22 ✅</a>
      <a href="companies/TSLA.html" class="alert-chip">TSLA Jul 22 ✅</a>
      <a href="companies/MSFT.html" class="alert-chip">MSFT Jul 29</a>
      <a href="companies/AAPL.html" class="alert-chip" style="display:none">AAPL Jul 30</a>
    </div>
    <div style="margin-top:4px;font-size:0.7em;color:var(--muted)">
      🏛 FOMC Jul 29 · GDP Jul 30 · PCE Jul 31
    </div>
  </div>
</section>

<!-- Calendar + Predictions -->
<section>
  <div class="section-title">📅 Calendar & Predictions</div>
  {econ_html}
</section>

<!-- Latest Reports -->
<section>
  <div class="section-title">📑 Latest Research Reports</div>
  <div class="report-grid">
    {report_cards}
  </div>
</section>

<!-- Tracked Companies -->
<section>
  <div class="section-title">🏢 Tracked Companies ({len(tracked)})</div>
  <div class="chip-row">
    {tracked_html}
  </div>
</section>

<div class="footer">
  AI Investment Research System · Generated {now}<br>
  <a href="https://github.com" style="color:var(--accent)">View on GitHub</a>
</div>

<script>
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

SW_JS = """// Simple service worker for offline caching
const CACHE_NAME = 'ai-invest-v1';
const ASSETS = ['./', 'index.html', 'manifest.json'];

self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(ASSETS))
  );
});

self.addEventListener('fetch', event => {
  event.respondWith(
    caches.match(event.request).then(response => response || fetch(event.request))
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
    print("  [4/6] Generating docs/index.html...")
    index_html = build_index_html(reports, calendar, tracked)
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

    # 6. Verify and update index links to .html
    print("  [6/6] Updating link extensions...")
    index_path = DOCS_DIR / "index.html"
    index_content = index_path.read_text(encoding="utf-8")
    # Replace .md links with .html links
    index_content = index_content.replace('.md"', '.html"')
    index_path.write_text(index_content, encoding="utf-8")

    print(f"\n[Done] Site built in docs/\n")
    print("  Next: git add docs/ && git commit && git push")
    print("  Then: Enable GitHub Pages from docs/ folder in repo settings")


if __name__ == "__main__":
    main()
