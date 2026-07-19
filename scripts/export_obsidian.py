"""
export_obsidian.py — Export company data to Obsidian-compatible markdown vault.

Generates [[wikilinks]] between company notes, sector pages, and topic pages
for an interconnected Obsidian knowledge graph.

Usage:
    python scripts/export_obsidian.py [--output ../obsidian_export/] [--all]

Output:
    obsidian_export/
    ├── NVDA.md                     # Company note with frontmatter + backlinks
    ├── AVGO.md
    ├── ORCL.md
    ├── Investment Dashboard.md     # Master index
    ├── Peer Comparison.md          # Comparative valuations
    └── Sector — Technology.md      # Sector-level aggregation
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_engine import get_profile, get_peer_metrics
from src.config import load_config

# ── Templates ────────────────────────────────────────────────────────────────

OBSIDIAN_FRONTMATTER = """---
ticker: {ticker}
sector: {sector}
industry: {industry}
updated: {date}
tags:
  - investment
  - {ticker_lower}
  - {sector_tag}
---

"""

DASHBOARD_FRONTMATTER = """---
title: Investment Dashboard
date: {date}
tags:
  - dashboard
  - investment
  - portfolio
---

"""

TOPIC_FRONTMATTER = """---
title: {title}
date: {date}
tags:
  - topic
  - {tag}
---

"""


# ── Converters ───────────────────────────────────────────────────────────────

def convert_md_to_obsidian(source_path: Path, ticker: str) -> str:
    """Convert a company markdown file to Obsidian format.

    Adds YAML frontmatter with live sector/industry data, appends wikilink
    backlinks for graph navigation.

    Args:
        source_path: Path to the source company .md file.
        ticker: Stock ticker symbol.

    Returns:
        Obsidian-formatted markdown string.
    """
    # Get live sector info
    sector = "Unknown"
    industry = "Unknown"
    try:
        profile = get_profile(ticker)
        if profile is not None and not profile.empty:
            sector = str(profile.iloc[0].get("sector", "Unknown"))
            industry = str(profile.iloc[0].get("industry", "Unknown"))
    except Exception:
        pass

    ticker_lower = ticker.lower()
    sector_tag = sector.lower().replace(" ", "-")

    frontmatter = OBSIDIAN_FRONTMATTER.format(
        ticker=ticker,
        sector=sector,
        industry=industry,
        date=datetime.now().strftime("%Y-%m-%d"),
        ticker_lower=ticker_lower,
        sector_tag=sector_tag,
    )

    # Read original company file
    if not source_path.exists():
        body = f"# {ticker}\n\n> File not found.\n"
    else:
        original = source_path.read_text(encoding="utf-8")
        lines = original.split("\n")
        # Remove existing H1 (frontmatter replaces it)
        if lines and lines[0].startswith("# "):
            lines = lines[1:]
        body = "\n".join(lines).strip()

    # Build backlinks section
    backlinks = "\n\n## 🔗 Related Notes\n\n"
    backlinks += f"- [[Investment Dashboard]]\n"
    backlinks += f"- [[{ticker} Valuation]]\n"
    backlinks += f"- [[Peer Comparison]]\n"
    if sector != "Unknown":
        backlinks += f"- [[Sector — {sector}]]\n"
    backlinks += f"- [[News Feed]]\n"

    return frontmatter + "\n" + body + backlinks


def generate_dashboard(tickers_data: dict[str, dict[str, Any]]) -> str:
    """Generate the master Investment Dashboard with live metrics.

    Args:
        tickers_data: Dict of ticker → data from data_engine.

    Returns:
        Dashboard markdown content.
    """
    content = DASHBOARD_FRONTMATTER.format(date=datetime.now().strftime("%Y-%m-%d"))
    content += "# 📊 Investment Dashboard\n\n"

    # Summary table
    content += "## Tracked Companies\n\n"
    content += "| Ticker | Company | Sector | Market Cap | P/E | Rev Growth |\n"
    content += "|---|---|---|---|---|---|\n"

    for ticker, data in tickers_data.items():
        profile = data.get("profile")
        metrics = data.get("metrics")

        name = ticker
        sector = "—"
        mcap = "—"
        pe = "—"
        growth = "—"

        if profile is not None and not profile.empty:
            p = profile.iloc[0]
            name = str(p.get("name", ticker))
            sector = str(p.get("sector", "—"))
            mcap_val = p.get("market_cap")
            if mcap_val and not (hasattr(mcap_val, 'isna') and mcap_val.isna()):
                mcap = f"${mcap_val / 1e12:.1f}T" if mcap_val > 1e12 else f"${mcap_val / 1e9:.0f}B"

        if metrics is not None and not metrics.empty:
            m = metrics.iloc[0]
            pe_val = m.get("pe_ratio")
            if pe_val and not (hasattr(pe_val, 'isna') and pe_val.isna()):
                pe = f"{pe_val:.1f}x"
            growth_val = m.get("revenue_growth")
            if growth_val and not (hasattr(growth_val, 'isna') and growth_val.isna()):
                growth = f"{growth_val:.1%}"

        content += f"| [[{ticker}]] | {name} | {sector} | {mcap} | {pe} | {growth} |\n"

    content += "\n## Quick Links\n\n"
    content += "- [[Peer Comparison]]\n"
    content += "- [[Sector — Technology]]\n"
    content += "- [[Economic Indicators]]\n"
    content += "- [[News Feed]]\n"
    content += "- [[Watchlist]]\n"

    return content


def generate_peer_comparison(tickers: list[str]) -> str:
    """Generate a Peer Comparison topic page with valuation tables.

    Args:
        tickers: List of ticker symbols.

    Returns:
        Peer Comparison markdown content.
    """
    content = TOPIC_FRONTMATTER.format(
        title="Peer Comparison",
        date=datetime.now().strftime("%Y-%m-%d"),
        tag="valuation",
    )
    content += "# 📈 Peer Comparison\n\n"
    content += "Valuation multiples across tracked companies and peers.\n\n"

    try:
        df = get_peer_metrics(tickers)
        if not df.empty:
            cols = ["ticker", "pe_ratio", "ev_to_ebitda", "pb_ratio", "revenue_growth", "gross_margin", "roe"]
            available = [c for c in cols if c in df.columns]
            content += _df_to_obsidian_table(df, available)
    except Exception as e:
        content += f"> ⚠️ Data unavailable: {e}\n"

    content += "\n## Related\n\n"
    for t in tickers:
        content += f"- [[{t}]]\n"
    content += "- [[Investment Dashboard]]\n"

    return content


def generate_sector_page(sector: str, tickers: list[str]) -> str:
    """Generate a sector aggregation page.

    Args:
        sector: Sector name (e.g., 'Technology').
        tickers: Tickers in this sector.

    Returns:
        Sector page markdown content.
    """
    tag = sector.lower().replace(" ", "-")
    content = TOPIC_FRONTMATTER.format(
        title=f"Sector — {sector}",
        date=datetime.now().strftime("%Y-%m-%d"),
        tag=tag,
    )
    content += f"# 🏭 Sector — {sector}\n\n"
    content += "## Holdings\n\n"

    for t in tickers:
        content += f"- [[{t}]]\n"

    content += "\n## Sector Context\n\n"
    content += f"<!-- Add sector-level macro analysis here -->\n"
    content += f"- [[Investment Dashboard]]\n"
    content += f"- [[Economic Indicators]]\n"

    return content


def _df_to_obsidian_table(df, columns: list[str]) -> str:
    """Convert a DataFrame to Obsidian markdown table."""
    available = [c for c in columns if c in df.columns]
    if not available:
        return "*No data.*\n"

    lines = ["| " + " | ".join(available) + " |"]
    lines.append("|" + "|".join("---" for _ in available) + "|")

    for _, row in df.iterrows():
        cells = []
        for col in available:
            val = row[col]
            if col == "ticker":
                cells.append(f"[[{val}]]")
            elif isinstance(val, float):
                if "growth" in col or "margin" in col or col == "roe" or col == "roa":
                    cells.append(f"{val:.1%}" if not (hasattr(val, 'isna') and val.isna()) else "—")
                else:
                    cells.append(f"{val:.1f}" if not (hasattr(val, 'isna') and val.isna()) else "—")
            else:
                cells.append(str(val) if val is not None else "—")
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines) + "\n"


# ── Export Engine ────────────────────────────────────────────────────────────

def export_all(output_dir: Path) -> dict[str, int]:
    """Export all company files + topic pages to Obsidian vault.

    Args:
        output_dir: Destination directory for the Obsidian vault.

    Returns:
        Dict with counts of files generated by type.
    """
    companies_dir = Path(__file__).resolve().parent.parent / "companies"
    output_dir.mkdir(parents=True, exist_ok=True)

    config = load_config()
    tracked = config.get("tracked", {}).get("tickers", ["NVDA", "AVGO", "ORCL"])
    if isinstance(tracked, str):
        import json
        tracked = json.loads(tracked)

    stats = {"company": 0, "topic": 0}

    # Export company notes
    tickers_data: dict[str, dict[str, Any]] = {}
    for md_file in sorted(companies_dir.glob("*.md")):
        ticker = md_file.stem.upper()
        tickers_data[ticker] = {}

        obsidian_content = convert_md_to_obsidian(md_file, ticker)
        output_path = output_dir / md_file.name

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(obsidian_content)

        print(f"  ✅ {md_file.name} → {output_path}")
        stats["company"] += 1

    # Generate dashboard
    dashboard = generate_dashboard(tickers_data)
    dash_path = output_dir / "Investment Dashboard.md"
    dash_path.write_text(dashboard, encoding="utf-8")
    print(f"  📊 Created: Investment Dashboard.md")
    stats["topic"] += 1

    # Generate peer comparison
    peers_content = generate_peer_comparison(list(tickers_data.keys()))
    peers_path = output_dir / "Peer Comparison.md"
    peers_path.write_text(peers_content, encoding="utf-8")
    print(f"  📈 Created: Peer Comparison.md")
    stats["topic"] += 1

    # Generate sector pages
    sectors: dict[str, list[str]] = {}
    for ticker in tickers_data:
        try:
            profile = get_profile(ticker)
            if profile is not None and not profile.empty:
                sector = str(profile.iloc[0].get("sector", "Technology"))
            else:
                sector = "Technology"
        except Exception:
            sector = "Technology"
        sectors.setdefault(sector, []).append(ticker)

    for sector, sector_tickers in sectors.items():
        sector_content = generate_sector_page(sector, sector_tickers)
        sector_path = output_dir / f"Sector — {sector}.md"
        sector_path.write_text(sector_content, encoding="utf-8")
        print(f"  🏭 Created: Sector — {sector}.md")
        stats["topic"] += 1

    return stats


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Export data to Obsidian vault")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: ./obsidian_export/)")
    args = parser.parse_args()

    output_dir = Path(args.output).resolve() if args.output else \
        Path(__file__).resolve().parent.parent / "obsidian_export"

    print(f"\n{'='*60}")
    print(f"  Exporting to Obsidian Vault")
    print(f"  Output: {output_dir}")
    print(f"{'='*60}\n")

    stats = export_all(output_dir)

    print(f"\n{'='*60}")
    print(f"  ✅ Done!")
    print(f"  {stats['company']} company note(s)")
    print(f"  {stats['topic']} topic page(s)")
    print(f"  → {output_dir}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
