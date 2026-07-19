"""
markdown.py — Markdown generation utilities for company files and reports.

Converts structured financial data into human-readable markdown tables
and sections for company .md files, dashboards, and investment reports.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd


# ── Helpers ──────────────────────────────────────────────────────────────────

def _fmt(value: Any, unit: str = "", decimals: int = 1) -> str:
    """Format a numeric value for display.

    Args:
        value: The value to format.
        unit: Suffix (e.g., 'B', 'M', '%').
        decimals: Number of decimal places.

    Returns:
        Formatted string, or '—' if value is None/NaN.
    """
    if value is None:
        return "—"
    try:
        num = float(value)
        if pd.isna(num):
            return "—"
        if unit == "%" and decimals == 0:
            return f"{num:.0f}%"
        if unit == "B":
            return f"${num:.{decimals}f}B"
        if unit == "M":
            return f"${num:.{decimals}f}M"
        if unit == "$":
            return f"${num:,.{decimals}f}"
        if decimals == 0:
            return f"{num:,.0f}"
        return f"{num:.{decimals}f}"
    except (ValueError, TypeError):
        return str(value) if value is not None else "—"


def _df_to_md_table(df: pd.DataFrame, columns: list[str] | None = None) -> str:
    """Convert a DataFrame to a markdown table string.

    Args:
        df: Input DataFrame.
        columns: Subset of columns to include. None = all.

    Returns:
        Markdown table as a string.
    """
    if df is None or df.empty:
        return "*No data available.*\n"

    if columns:
        df = df[[c for c in columns if c in df.columns]]

    lines = []
    lines.append("| " + " | ".join(str(c) for c in df.columns) + " |")
    lines.append("|" + "|".join("---" for _ in df.columns) + "|")

    for _, row in df.iterrows():
        cells = []
        for col in df.columns:
            val = row[col]
            if isinstance(val, float):
                cells.append(_fmt(val))
            elif isinstance(val, (int,)):
                cells.append(f"{val:,}")
            else:
                cells.append(str(val) if pd.notna(val) else "—")
        lines.append("| " + " | ".join(cells) + " |")

    return "\n".join(lines) + "\n"


def _kv_row(label: str, value: str) -> str:
    """Single key-value row for a metrics table."""
    return f"| {label} | {value} |"


def _kv_section(title: str, rows: list[tuple[str, str]]) -> str:
    """Build a key-value metrics section.

    Args:
        title: Section heading.
        rows: List of (label, value) tuples.

    Returns:
        Markdown section.
    """
    lines = [f"### {title}", "", "| Metric | Value |", "|---|---|"]
    for label, value in rows:
        lines.append(_kv_row(label, value))
    lines.append("")
    return "\n".join(lines)


# ── Company Markdown Generator ───────────────────────────────────────────────

def generate_company_md(
    ticker: str,
    data: dict[str, Any],
) -> str:
    """Generate a complete company analysis markdown file from live data.

    Args:
        ticker: Stock ticker symbol.
        data: Dict from data_engine.fetch_all_for_ticker().

    Returns:
        Full markdown string for the company .md file.
    """
    ticker = ticker.upper()
    profile = data.get("profile", pd.DataFrame())
    metrics = data.get("metrics", pd.DataFrame())
    income = data.get("income", pd.DataFrame())
    balance = data.get("balance", pd.DataFrame())
    cashflow = data.get("cashflow", pd.DataFrame())
    estimates = data.get("estimates", pd.DataFrame())
    news = data.get("news", pd.DataFrame())
    filings = data.get("filings", pd.DataFrame())
    peers = data.get("peers", [])

    lines: list[str] = []

    # ── Header ──
    lines.append(f"# {ticker} — {_extract(profile, 'name', ticker)}")
    lines.append("")
    lines.append(f"> *Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    # ── Company Overview ──
    lines.append("## Company Overview")
    lines.append("")

    overview_rows: list[tuple[str, str]] = [
        ("Ticker", ticker),
        ("Name", str(_extract(profile, "name", "—"))),
        ("Sector", str(_extract(profile, "sector", "—"))),
        ("Industry", str(_extract(profile, "industry", "—"))),
        ("Market Cap", _fmt(_extract(profile, "market_cap"), unit="B")),
        ("Employees", _fmt(_extract(profile, "full_time_employees"), decimals=0)),
        ("Country", str(_extract(profile, "country", "—"))),
        ("Website", str(_extract(profile, "website", "—"))),
    ]
    lines.append(_kv_section("Profile", overview_rows))

    # ── Key Metrics ──
    if not metrics.empty:
        lines.append("## Key Metrics (TTM)")
        lines.append("")
        m = metrics.iloc[0]
        metric_rows: list[tuple[str, str]] = [
            ("P/E Ratio", _fmt(m.get("pe_ratio"))),
            ("P/B Ratio", _fmt(m.get("pb_ratio"))),
            ("P/S Ratio", _fmt(m.get("ps_ratio"))),
            ("EV/EBITDA", _fmt(m.get("ev_to_ebitda"))),
            ("ROE", _fmt(m.get("roe"), unit="%")),
            ("ROA", _fmt(m.get("roa"), unit="%")),
            ("Gross Margin", _fmt(m.get("gross_margin"), unit="%")),
            ("Operating Margin", _fmt(m.get("operating_margin"), unit="%")),
            ("Net Margin", _fmt(m.get("net_margin"), unit="%")),
            ("Revenue Growth (YoY)", _fmt(m.get("revenue_growth"), unit="%")),
            ("Debt/Equity", _fmt(m.get("debt_to_equity"))),
            ("Current Ratio", _fmt(m.get("current_ratio"))),
        ]
        lines.append(_kv_section("Valuation & Profitability", metric_rows))
    else:
        lines.append("## Key Metrics")
        lines.append("")
        lines.append("*Metrics data not available — check provider configuration.*")
        lines.append("")

    # ── Financial Statements ──
    lines.append("## Financial Statements")
    lines.append("")

    if not income.empty:
        lines.append("### Income Statement (Annual)")
        lines.append("")
        income_cols = ["period_ending", "total_revenue", "gross_profit",
                       "operating_income", "net_income", "eps_diluted"]
        lines.append(_df_to_md_table(income, income_cols))

    if not balance.empty:
        lines.append("### Balance Sheet (Annual)")
        lines.append("")
        balance_cols = ["period_ending", "total_assets", "total_liabilities",
                        "total_equity", "total_debt", "cash_and_equivalents"]
        lines.append(_df_to_md_table(balance, balance_cols))

    if not cashflow.empty:
        lines.append("### Cash Flow (Annual)")
        lines.append("")
        cf_cols = ["period_ending", "operating_cash_flow",
                    "capital_expenditure", "free_cash_flow"]
        lines.append(_df_to_md_table(cashflow, cf_cols))

    # ── Analyst Estimates ──
    if not estimates.empty:
        lines.append("## Analyst Estimates")
        lines.append("")
        lines.append(_df_to_md_table(estimates))

    # ── Recent News ──
    if not news.empty:
        lines.append("## Recent News")
        lines.append("")
        for _, article in news.head(15).iterrows():
            title = article.get("title", "N/A")
            url = article.get("url", "#")
            source = article.get("source", "N/A")
            date = article.get("date", "")
            lines.append(f"- [{title}]({url}) — *{source}* ({date})")
        lines.append("")

    # ── SEC Filings ──
    if not filings.empty:
        lines.append("## Recent SEC Filings")
        lines.append("")
        filing_cols = ["filing_date", "form_type", "description"]
        lines.append(_df_to_md_table(filings, filing_cols))

    # ── Peers ──
    if peers:
        lines.append("## Peers")
        lines.append("")
        if isinstance(peers, list):
            lines.append(", ".join(str(p) for p in peers))
            lines.append("")

    # ── Manual Sections (preserved placeholders) ──
    lines.append("## Moat Assessment")
    lines.append("")
    lines.append("<!-- Add your moat analysis here -->")
    lines.append("")

    lines.append("## Risks")
    lines.append("")
    lines.append("<!-- Add risk analysis here -->")
    lines.append("")

    lines.append("## Catalysts")
    lines.append("")
    lines.append("<!-- Add catalysts here -->")
    lines.append("")

    lines.append("## Recent Updates")
    lines.append("")
    lines.append(f"<!-- Last updated: {datetime.now().strftime('%Y-%m-%d')} -->")
    lines.append("")

    return "\n".join(lines)


def _extract(df: pd.DataFrame, column: str, default: Any = "—") -> Any:
    """Safely extract a single value from a DataFrame.

    Args:
        df: DataFrame with at least one row.
        column: Column name to extract.
        default: Value to return if column doesn't exist or value is NaN.

    Returns:
        The cell value or default.
    """
    if df is None or df.empty:
        return default
    if column not in df.columns:
        return default
    val = df.iloc[0][column]
    if pd.isna(val):
        return default
    return val


# ── Dashboard Generator ──────────────────────────────────────────────────────

def generate_dashboard_md(tickers_data: dict[str, dict]) -> str:
    """Generate a portfolio dashboard markdown file.

    Args:
        tickers_data: Dict of ticker → data dict (from fetch_all_for_ticker).

    Returns:
        Full markdown for the dashboard.
    """
    lines: list[str] = []
    lines.append("# Investment Dashboard")
    lines.append("")
    lines.append(f"> Updated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append("")

    # Summary table
    lines.append("## Portfolio Summary")
    lines.append("")
    lines.append("| Ticker | Name | Price | Market Cap | P/E | Revenue Growth | Gross Margin |")
    lines.append("|---|---|---|---|---|---|---|")

    for ticker, data in tickers_data.items():
        profile = data.get("profile", pd.DataFrame())
        metrics_df = data.get("metrics", pd.DataFrame())
        quote = data.get("quote", pd.DataFrame())

        name = str(_extract(profile, "name", ticker))
        mcap = _fmt(_extract(profile, "market_cap"), unit="B")

        price = "—"
        if not quote.empty and "close" in quote.columns:
            price = _fmt(quote.iloc[0]["close"], unit="$")

        pe = "—"
        rev_growth = "—"
        gross_margin = "—"
        if not metrics_df.empty:
            m = metrics_df.iloc[0]
            pe = _fmt(m.get("pe_ratio"))
            rev_growth = _fmt(m.get("revenue_growth"), unit="%")
            gross_margin = _fmt(m.get("gross_margin"), unit="%")

        lines.append(f"| {ticker} | {name} | {price} | {mcap} | {pe} | {rev_growth} | {gross_margin} |")

    lines.append("")

    # Individual company sections
    for ticker, data in tickers_data.items():
        profile = data.get("profile", pd.DataFrame())
        news = data.get("news", pd.DataFrame())
        name = _extract(profile, "name", ticker)

        lines.append(f"## {ticker} — {name}")
        lines.append("")

        if not news.empty:
            lines.append("### Latest News")
            lines.append("")
            for _, a in news.head(5).iterrows():
                title = a.get("title", "N/A")
                url = a.get("url", "#")
                date = a.get("date", "")
                lines.append(f"- [{title}]({url}) ({date})")
            lines.append("")

    return "\n".join(lines)


# ── Report Generator ─────────────────────────────────────────────────────────

def generate_report_md(
    ticker: str,
    data: dict[str, Any],
    analysis: str = "",
) -> str:
    """Generate an investment research report markdown.

    Args:
        ticker: Stock ticker.
        data: Full data dict from fetch_all_for_ticker.
        analysis: Pre-written analysis text (e.g., from Claude).

    Returns:
        Full markdown report string.
    """
    lines: list[str] = []
    lines.append(f"# {ticker} — Investment Research Report")
    lines.append(f"*{datetime.now().strftime('%B %d, %Y')}*")
    lines.append("")

    # TOC
    lines.append("## Table of Contents")
    lines.append("1. [Executive Summary](#executive-summary)")
    lines.append("2. [Financial Overview](#financial-overview)")
    lines.append("3. [Valuation](#valuation)")
    lines.append("4. [Risks & Catalysts](#risks--catalysts)")
    lines.append("5. [Recommendation](#recommendation)")
    lines.append("")

    if analysis:
        lines.append(analysis)
    else:
        lines.append("## Executive Summary")
        lines.append("")
        lines.append("*Analysis pending — run generate_report.py with Claude API key.*")
        lines.append("")

    # Append financial data appendix
    lines.append("---")
    lines.append("## Appendix: Financial Data")
    lines.append("")
    lines.append(generate_company_md(ticker, data))

    return "\n".join(lines)
