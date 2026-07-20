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

def _col(df: pd.DataFrame, *names: str, default: Any = None) -> Any:
    """Safely get the first matching column value from a DataFrame's first row.

    Args:
        df: DataFrame with at least one row.
        names: Column names to try, in priority order.
        default: Value to return if no matching column found.

    Returns:
        First non-NaN value found, or default.
    """
    if df is None or df.empty:
        return default
    row = df.iloc[0]
    for name in names:
        if name in df.columns:
            val = row[name]
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val
    return default


def _fmt(value: Any, unit: str = "", decimals: int = 1) -> str:
    """Format a numeric value for display.

    Args:
        value: The value to format.
        unit: Suffix (e.g., 'B', 'M', '%', 'T').
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
        if unit == "%":
            # Values come as ratios (0.74 = 74%), multiply by 100
            display = num * 100 if abs(num) < 10 else num
            return f"{display:.{decimals}f}%"
        if unit == "T":
            # Auto-scale to T/B/M
            if abs(num) >= 1e12:
                return f"${num/1e12:.{decimals}f}T"
            elif abs(num) >= 1e9:
                return f"${num/1e9:.{decimals}f}B"
            elif abs(num) >= 1e6:
                return f"${num/1e6:.{decimals}f}M"
            return f"${num:,.{decimals}f}"
        if unit == "B":
            if abs(num) >= 1e12:
                return f"${num/1e12:.{decimals}f}T"
            return f"${num/1e9:.{decimals}f}B"
        if unit == "M":
            return f"${num/1e6:.{decimals}f}M"
        if unit == "$":
            if abs(num) >= 1e12:
                return f"${num/1e12:.{decimals}f}T"
            elif abs(num) >= 1e9:
                return f"${num/1e9:.{decimals}f}B"
            elif abs(num) >= 1e6:
                return f"${num/1e6:.{decimals}f}M"
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
    ratios = data.get("ratios", pd.DataFrame())
    income = data.get("income", pd.DataFrame())
    balance = data.get("balance", pd.DataFrame())
    cashflow = data.get("cashflow", pd.DataFrame())
    price_history = data.get("price_history", pd.DataFrame())
    quote = data.get("quote", pd.DataFrame())
    estimates = data.get("estimates", pd.DataFrame())
    news = data.get("news", pd.DataFrame())
    filings = data.get("filings", pd.DataFrame())
    peers = data.get("peers", [])

    # Merge metrics + ratios for complete data access
    combined = metrics.copy() if not metrics.empty else pd.DataFrame()
    if not ratios.empty:
        for col in ratios.columns:
            if col not in combined.columns:
                combined[col] = ratios[col].values[:len(combined)] if len(combined) > 0 else ratios[col]

    lines: list[str] = []

    # ── Header ──
    lines.append(f"# {ticker} — {_col(profile, 'name', 'company_name', default=ticker)}")
    lines.append("")
    lines.append(f"> *Auto-generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
    lines.append("")

    # ── Company Overview ──
    lines.append("## Company Overview")
    lines.append("")

    overview_rows: list[tuple[str, str]] = [
        ("Ticker", ticker),
        ("Name", str(_col(profile, "name", "company_name", default="—"))),
        ("Sector", str(_col(profile, "sector", default="—"))),
        ("Industry", str(_col(profile, "industry", default="—"))),
        ("Market Cap", _fmt(_col(combined, "market_cap"), unit="T")),
        ("Enterprise Value", _fmt(_col(combined, "enterprise_value"), unit="T")),
        ("Employees", _fmt(_col(profile, "full_time_employees"), decimals=0)),
        ("Country", str(_col(profile, "country", default="—"))),
        ("Website", str(_col(profile, "website", default="—"))),
    ]
    lines.append(_kv_section("Profile", overview_rows))

    # ── Key Metrics ──
    if not combined.empty:
        lines.append("## Key Metrics (TTM)")
        lines.append("")
        metric_rows: list[tuple[str, str]] = [
            ("P/E Ratio", _fmt(_col(combined, "pe_ratio", "price_to_earnings"))),
            ("P/B Ratio", _fmt(_col(combined, "pb_ratio", "price_to_book"))),
            ("P/S Ratio", _fmt(_col(combined, "ps_ratio", "price_to_sales"))),
            ("P/FCF Ratio", _fmt(_col(combined, "price_to_fcf", "price_to_free_cash_flow"))),
            ("PEG Ratio", _fmt(_col(combined, "peg_ratio", "price_to_earnings_growth"))),
            ("EV/EBITDA", _fmt(_col(combined, "ev_to_ebitda"))),
            ("EV/Sales", _fmt(_col(combined, "ev_to_sales"))),
            ("ROE", _fmt(_col(combined, "roe", "return_on_equity"), unit="%")),
            ("ROA", _fmt(_col(combined, "roa", "return_on_assets"), unit="%")),
            ("ROIC", _fmt(_col(combined, "roic", "return_on_invested_capital"), unit="%")),
            ("Gross Margin", _fmt(_col(combined, "gross_margin", "gross_profit_margin"), unit="%")),
            ("Operating Margin", _fmt(_col(combined, "operating_margin", "operating_profit_margin"), unit="%")),
            ("Net Margin", _fmt(_col(combined, "net_margin", "net_profit_margin"), unit="%")),
            ("EBITDA Margin", _fmt(_col(combined, "ebitda_margin"), unit="%")),
            ("Debt/Equity", _fmt(_col(combined, "debt_to_equity"))),
            ("Current Ratio", _fmt(_col(combined, "current_ratio"))),
            ("Dividend Yield", _fmt(_col(combined, "dividend_yield"), unit="%")),
            ("Earnings Yield", _fmt(_col(combined, "earnings_yield"), unit="%")),
            ("FCF Yield", _fmt(_col(combined, "fcf_yield", "free_cash_flow_yield"), unit="%")),
        ]
        lines.append(_kv_section("Valuation & Profitability", metric_rows))
    else:
        lines.append("## Key Metrics")
        lines.append("")
        lines.append("*Metrics data not available.*")
        lines.append("")

    # ── Financial Statements ──
    lines.append("## Financial Statements")
    lines.append("")

    if not income.empty:
        lines.append("### Income Statement (Annual)")
        lines.append("")
        income_cols = ["period_ending", "total_revenue", "gross_profit",
                       "operating_income", "net_income", "eps_diluted",
                       "ebitda", "cost_of_revenue", "r_and_d"]
        lines.append(_df_to_md_table(income, income_cols))

    if not balance.empty:
        lines.append("### Balance Sheet (Annual)")
        lines.append("")
        balance_cols = ["period_ending", "total_assets", "total_liabilities",
                        "total_equity", "total_debt", "net_debt",
                        "cash_and_equivalents", "goodwill_intangibles"]
        lines.append(_df_to_md_table(balance, balance_cols))

    if not cashflow.empty:
        lines.append("### Cash Flow (Annual)")
        lines.append("")
        cf_cols = ["period_ending", "operating_cash_flow",
                    "capital_expenditure", "free_cash_flow",
                    "depreciation_amortization"]
        lines.append(_df_to_md_table(cashflow, cf_cols))

    # ── Price & K-line Data ──
    if not quote.empty:
        lines.append("## Current Price")
        lines.append("")
        price_rows: list[tuple[str, str]] = []
        for field, label in [
            ("last_price", "Last Price"), ("open", "Open"), ("high", "High"),
            ("low", "Low"), ("prev_close", "Previous Close"),
            ("change_percent", "Change %"), ("volume", "Volume"),
            ("year_high", "52-Week High"), ("year_low", "52-Week Low"),
            ("ma50", "50-Day MA"), ("ma200", "200-Day MA"),
            ("market_cap", "Market Cap"),
        ]:
            val = _col(quote, field)
            if val is not None:
                if field == "volume":
                    price_rows.append((label, f"{val:,.0f}"))
                elif field == "change_percent":
                    price_rows.append((label, _fmt(val, unit="%")))
                elif field in ("market_cap",):
                    price_rows.append((label, _fmt(val, unit="T")))
                elif val > 1e9:
                    price_rows.append((label, _fmt(val, unit="T")))
                else:
                    price_rows.append((label, _fmt(val, unit="$")))
        lines.append(_kv_section("Quote", price_rows))

    if not price_history.empty and len(price_history) >= 5:
        lines.append("## Price History (K-Line)")
        lines.append("")
        ph = price_history
        # Find date column
        date_col = None
        for c in ["date", "index"]:
            if c in ph.columns:
                date_col = c
                break
        # Show recent 10 rows
        display_cols = [date_col] if date_col else []
        for c in ["open", "high", "low", "close", "volume"]:
            if c in ph.columns:
                display_cols.append(c)
        available_cols = [c for c in display_cols if c in ph.columns]
        lines.append(_df_to_md_table(ph.tail(10), available_cols))
        lines.append("")

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
            peer_names = []
            for p in peers:
                if hasattr(p, 'name'):
                    peer_names.append(f"{getattr(p, 'symbol', '')} ({getattr(p, 'name', '')})")
                elif hasattr(p, 'symbol'):
                    peer_names.append(str(p.symbol))
                else:
                    peer_names.append(str(p))
            lines.append(", ".join(peer_names))
            lines.append("")

    # ── Research Framework (Obsidian Callouts) ──
    lines.append("## Research Framework")
    lines.append("")

    lines.append("> [!abstract] Moat Assessment")
    lines.append("> *What protects this company from competitors?*")
    lines.append("> 1. **Switching Costs** — how hard is it for customers to leave?")
    lines.append("> 2. **Network Effects** — does each user make it more valuable?")
    lines.append("> 3. **Intangible Assets** — patents, brand, regulatory moats?")
    lines.append("> 4. **Cost Advantage** — structural cost position vs peers?")
    lines.append("> 5. **Efficient Scale** — is the market naturally limited?")
    lines.append("")

    lines.append("> [!warning] Risks")
    lines.append("> | # | Risk | Severity | Probability |")
    lines.append("> |---|------|----------|-------------|")
    lines.append("> | 1 | *Describe risk...* | `#critical` | High / Med / Low |")
    lines.append("> | 2 | *Describe risk...* | `#medium` | High / Med / Low |")
    lines.append("> | 3 | *Describe risk...* | `#low` | High / Med / Low |")
    lines.append("")

    lines.append("> [!tip] Catalysts")
    lines.append("> | # | Catalyst | Timeline | Impact |")
    lines.append("> |---|----------|----------|--------|")
    lines.append("> | 1 | *Describe catalyst...* | `#near-term` | High / Med / Low |")
    lines.append("> | 2 | *Describe catalyst...* | `#medium-term` | High / Med / Low |")
    lines.append("")

    lines.append("> [!question] Investment Thesis")
    lines.append("> - **Position:** [Long / Neutral / Avoiding]")
    lines.append("> - **Fair Value Estimate:** $___ (margin of safety: ___%)")
    lines.append("> - **Key Assumption Being Priced In:** ___")
    lines.append("> - **What Would Change My Mind:** ___")
    lines.append("")

    lines.append(f"*Last data refresh: {datetime.now().strftime('%Y-%m-%d %H:%M')}*")
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
    """Generate an Obsidian-native investment research report.

    Outputs a report designed for Obsidian reading with:
    - YAML frontmatter (tags, ticker, date)
    - Callout blocks (> [!abstract], > [!warning], > [!tip], > [!quote])
    - Collapsible financial data appendix
    - [[wikilinks]] to related notes

    Args:
        ticker: Stock ticker.
        data: Full data dict from fetch_all_for_ticker.
        analysis: LLM-generated analysis text.

    Returns:
        Full Obsidian-formatted markdown report.
    """
    today = datetime.now().strftime("%Y-%m-%d")
    profile = data.get("profile", pd.DataFrame())
    name = _col(profile, "name", "company_name", default=ticker)
    sector = str(_col(profile, "sector", default="Unknown"))

    lines: list[str] = []

    # ── YAML Frontmatter ──
    lines.append("---")
    lines.append(f"title: \"{ticker} — Investment Research Report\"")
    lines.append(f"ticker: {ticker}")
    lines.append(f"company: \"{name}\"")
    lines.append(f"sector: \"{sector}\"")
    lines.append(f"date: {today}")
    lines.append("tags:")
    lines.append("  - investment-report")
    lines.append(f"  - {ticker.lower()}")
    lines.append(f"  - {sector.lower().replace(' ', '-')}")
    lines.append("type: report")
    lines.append("---")
    lines.append("")

    # ── Header ──
    lines.append(f"# 📊 {ticker} — {name}")
    lines.append(f"> *Investment Research Report · {datetime.now().strftime('%B %d, %Y')}*")
    lines.append("")
    lines.append(f"**Ticker:** [[{ticker}]] | **Sector:** [[Sector — {sector}]] | **Market Cap:** {_fmt(_col(data.get('metrics', pd.DataFrame()), 'market_cap'), unit='T')}")
    lines.append("")

    # ── Quick Links ──
    lines.append("> [!tip]- Quick Navigation")
    lines.append("> - [[Investment Dashboard]] | [[Peer Comparison]] | [[{ticker} Valuation]]".replace("{ticker}", ticker))
    lines.append("> - [[Sector — {sector}]] | [[Economic Indicators]]".replace("{sector}", sector))
    lines.append("")
    # ── Analysis Section (LLM output) ──
    if analysis:
        lines.append(analysis)
    else:
        lines.append("> [!warning] Analysis Pending")
        lines.append("> Run `python scripts/generate_report.py --ticker " + ticker + "` to generate.")
        lines.append("")

    # ── Separator ──
    lines.append("---")
    lines.append("")

    # ── Collapsible Financial Appendix ──
    lines.append("> [!note]- 📋 Financial Data Appendix *(click to expand)*")
    lines.append(">")
    # Embed the company data with '>' prefix for callout nesting
    company_md = generate_company_md(ticker, data)
    for line in company_md.split("\n"):
        if line.strip():
            lines.append(f"> {line}")
        else:
            lines.append(">")
    lines.append("")

    # ── Footer ──
    lines.append(f"---")
    lines.append(f"*Report generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · AI Investment System*")
    lines.append(f"*Related: [[{ticker}]] · [[Peer Comparison]] · [[Investment Dashboard]]*")

    return "\n".join(lines)
