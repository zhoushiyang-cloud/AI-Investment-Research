"""
data_engine.py — Unified OpenBB data access layer.

All investment data flows through this module. Each function wraps an OpenBB
API call, normalizes the result, and degrades gracefully when a provider is
unavailable or returns no data.

Key design decisions:
- yfinance is the default provider (free, no API key required)
- SEC is used for filings (free, no API key required)
- fmp/intrinio/tiingo/benzinga are premium upgrade paths
- All functions return DataFrames or dicts, never raw OBBject
- Errors are logged as warnings, never crash the caller
"""

from __future__ import annotations

import warnings
from datetime import datetime, timedelta
from typing import Any

import pandas as pd
from openbb import obb

from src.config import load_config, pick_provider, setup_openbb_credentials

# ── Setup ────────────────────────────────────────────────────────────────────
# Configure OpenBB credentials once at import time
try:
    setup_openbb_credentials()
except Exception:
    pass  # Credentials are optional — yfinance works without keys


# ── Column Normalization ──────────────────────────────────────────────────────
# Different providers use different column names for the same data.
# This mapping ensures consumers (markdown.py, scripts) always find standard names.
# Format: { standard_name: [possible provider-specific names] }

_COLUMN_ALIASES: dict[str, list[str]] = {
    # ── Income Statement ──
    "total_revenue":       ["revenue", "total_revenue", "sales_revenue"],
    "operating_income":   ["total_operating_income", "operating_income", "ebit"],
    "net_income":          ["consolidated_net_income", "bottom_line_net_income",
                            "net_income", "net_income_from_continuing_operations"],
    "eps_diluted":         ["diluted_earnings_per_share", "eps_diluted", "diluted_eps"],
    "eps_basic":           ["basic_earnings_per_share", "eps_basic", "basic_eps"],
    "gross_profit":        ["gross_profit"],
    "ebitda":              ["ebitda"],
    "cost_of_revenue":     ["cost_of_revenue"],
    "r_and_d":             ["research_and_development_expense", "research_and_development"],
    "sga":                 ["selling_general_and_admin_expense", "general_and_admin_expense"],

    # ── Balance Sheet ──
    "total_assets":        ["total_assets"],
    "total_liabilities":   ["total_liabilities"],
    "total_equity":        ["total_common_equity", "total_equity",
                            "total_equity_non_controlling_interests", "total_shareholders_equity"],
    "total_debt":          ["total_debt"],
    "net_debt":            ["net_debt"],
    "cash_and_equivalents": ["cash_and_cash_equivalents", "cash_and_equivalents"],
    "goodwill_intangibles": ["goodwill_and_intangible_assets", "goodwill_intangibles"],
    "accounts_receivable": ["accounts_receivables", "accounts_receivable", "net_receivables"],
    "inventory":           ["inventory"],
    "total_current_assets": ["total_current_assets"],
    "total_current_liabilities": ["total_current_liabilities"],

    # ── Cash Flow ──
    "operating_cash_flow": ["net_cash_from_operating_activities", "operating_cash_flow"],
    "capital_expenditure": ["capital_expenditure", "purchase_of_property_plant_and_equipment"],
    "free_cash_flow":     ["free_cash_flow"],
    "depreciation_amortization": ["depreciation_and_amortization"],

    # ── Valuation Multiples (from metrics + ratios) ──
    "pe_ratio":           ["price_to_earnings", "pe_ratio", "pe_ttm"],
    "pb_ratio":           ["price_to_book", "pb_ratio", "pb_ttm"],
    "ps_ratio":           ["price_to_sales", "ps_ratio", "ps_ttm"],
    "price_to_fcf":       ["price_to_free_cash_flow", "price_to_fcf"],
    "peg_ratio":          ["price_to_earnings_growth", "peg_ratio"],
    "ev_to_ebitda":       ["ev_to_ebitda", "enterprise_value_over_ebitda"],
    "ev_to_sales":        ["ev_to_sales"],
    "ev_to_fcf":          ["ev_to_free_cash_flow", "ev_to_fcf"],

    # ── Profitability ──
    "gross_margin":       ["gross_profit_margin", "gross_margin"],
    "operating_margin":   ["operating_profit_margin", "operating_margin", "ebit_margin"],
    "net_margin":         ["net_profit_margin", "net_margin", "bottom_line_profit_margin"],
    "ebitda_margin":      ["ebitda_margin"],
    "roe":                ["return_on_equity", "roe"],
    "roa":                ["return_on_assets", "roa"],
    "roic":               ["return_on_invested_capital", "roic"],
    "earnings_yield":     ["earnings_yield"],
    "fcf_yield":          ["free_cash_flow_yield", "fcf_yield"],

    # ── Growth ──
    "revenue_growth":     ["revenue_growth", "revenue_growth_yoy"],

    # ── Financial Health ──
    "debt_to_equity":     ["debt_to_equity", "debt_to_equity_ratio"],
    "current_ratio":      ["current_ratio"],
    "dividend_yield":     ["dividend_yield", "dividend_yield_percent"],

    # ── Profile ──
    "market_cap":         ["market_cap", "market_capitalization"],
    "enterprise_value":   ["enterprise_value"],
    "shares_outstanding": ["weighted_average_diluted_shares_outstanding",
                           "shares_outstanding", "weighted_average_shares"],
    "full_time_employees": ["full_time_employees", "employees"],
    "sector":             ["sector"],
    "industry":           ["industry"],
    "name":               ["name", "company_name", "long_name"],
    "country":            ["country"],
    "website":            ["website", "website_url"],
}


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add standard column name aliases to a DataFrame.

    For each standard name, if any of its provider-specific aliases exists
    as a column, add a copy under the standard name. Original columns preserved.

    Args:
        df: DataFrame from any OpenBB provider.

    Returns:
        Same DataFrame with standard column aliases added.
    """
    if df is None or df.empty:
        return df

    df = df.copy()
    for standard_name, aliases in _COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in df.columns and standard_name not in df.columns:
                df[standard_name] = df[alias]
                break
    return df


def _col(df: pd.DataFrame, *names: str) -> Any:
    """Safely get the first matching column value from a DataFrame row.

    Args:
        df: DataFrame with one row.
        names: Column names to try, in priority order.

    Returns:
        First non-NaN value found, or None.
    """
    if df is None or df.empty:
        return None
    row = df.iloc[0]
    for name in names:
        if name in df.columns:
            val = row[name]
            if val is not None and not (isinstance(val, float) and pd.isna(val)):
                return val
    return None


# ── Internal helpers ─────────────────────────────────────────────────────────

def _safe_result(result, default: Any = None) -> Any:
    """Extract results from an OpenBB OBBject, returning default on failure.

    Args:
        result: An OBBject from any obb.* call.
        default: Value to return if results are empty/None.

    Returns:
        Results as-is (list of pydantic models), a DataFrame, or default.
    """
    if result is None:
        return default
    try:
        data = result.results  # type: ignore[union-attr]
        if data is None:
            return default
        return data
    except Exception:
        return default


def _to_df(result, **kwargs) -> pd.DataFrame:
    """Convert an OpenBB result to a pandas DataFrame, with fallback.

    Args:
        result: OBBject result.
        **kwargs: Passed to to_dataframe().

    Returns:
        DataFrame (empty if conversion fails).
    """
    if result is None:
        return pd.DataFrame()
    try:
        df = result.to_dataframe(**kwargs)  # type: ignore[union-attr]
        # Move date index to column if present
        if isinstance(df.index, pd.DatetimeIndex) or (
            hasattr(df.index, 'dtype') and 'date' in str(df.index.dtype).lower()
        ):
            df = df.reset_index()
        if df.index.name == 'date' or 'date' in str(df.index.dtype).lower():
            df = df.reset_index()
        return _normalize_columns(df)
    except Exception:
        # Fallback: try to build DataFrame from results list
        data = _safe_result(result)
        if isinstance(data, pd.DataFrame):
            df = data
            if isinstance(df.index, pd.DatetimeIndex):
                df = df.reset_index()
            return _normalize_columns(df)
        if isinstance(data, list) and len(data) > 0:
            try:
                df = pd.DataFrame([d.model_dump() if hasattr(d, "model_dump") else d for d in data])
                return _normalize_columns(df)
            except Exception:
                pass
        return pd.DataFrame()


def _resolve_provider(preferred: str | None, *fallbacks: str) -> str:
    """Resolve which provider to use.

    If the user specifies one, use it. Otherwise pick the best free
    or configured provider from the fallback chain.

    Args:
        preferred: Explicit provider override, or None.
        fallbacks: Provider names in preference order.

    Returns:
        Final provider name.
    """
    if preferred is not None:
        return preferred
    return pick_provider(*fallbacks)


def _try_with_fallback(fn, *fallback_providers: str, **kwargs) -> pd.DataFrame:
    """Try an OpenBB call, falling back through providers on failure.

    When the primary provider fails (402, timeout, etc.), this automatically
    retries with each fallback provider until one succeeds.

    Args:
        fn: A callable that takes (provider=...) and returns an OpenBB result.
        fallback_providers: Provider names to try in order.
        **kwargs: Additional kwargs passed to fn (excluding 'provider').

    Returns:
        DataFrame from the first successful provider, or empty DataFrame.
    """
    last_error = ""
    for provider in fallback_providers:
        try:
            result = fn(provider=provider, **kwargs)
            df = _to_df(result)
            if not df.empty:
                return df
            last_error = f"empty result from {provider}"
        except Exception as e:
            last_error = str(e)
            continue  # Try next provider

    warnings.warn(f"All providers failed: {', '.join(fallback_providers)}. Last: {last_error}")
    return pd.DataFrame()


# ── Price & Market Data ──────────────────────────────────────────────────────

def get_quote(ticker: str, provider: str | None = None) -> pd.DataFrame:
    """Get real-time quote for a ticker."""
    if provider:
        return _to_df(obb.equity.price.quote(ticker, provider=provider))
    return _try_providers(
        lambda p: obb.equity.price.quote(ticker, provider=p),
        *_get_providers("fmp", "yfinance"),
    )


def get_price_history(
    ticker: str,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    interval: str = "1d",
    provider: str | None = None,
) -> pd.DataFrame:
    """Get historical OHLCV (K-line) data.

    OpenBB: obb.equity.price.historical()

    Args:
        ticker: Stock symbol.
        start: Start date (YYYY-MM-DD string or datetime). Default: 1 year ago.
        end: End date. Default: today.
        interval: '1m', '5m', '15m', '30m', '1h', '1d', '1wk', '1mo'.
        provider: Override the default provider.
    """
    if start is None:
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    if isinstance(start, datetime):
        start = start.strftime("%Y-%m-%d")
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if isinstance(end, datetime):
        end = end.strftime("%Y-%m-%d")
    if provider:
        return _to_df(obb.equity.price.historical(ticker, start_date=start, end_date=end, interval=interval, provider=provider))
    return _try_providers(
        lambda p: obb.equity.price.historical(ticker, start_date=start, end_date=end, interval=interval, provider=p),
        *_get_providers("fmp", "tiingo", "yfinance"),
    )


# ── Company Profile & Fundamentals ───────────────────────────────────────────

def get_profile(ticker: str, provider: str | None = None) -> pd.DataFrame:
    """Get company profile: sector, industry, market cap, employees, description.

    OpenBB: obb.equity.profile()
    """
    p = _resolve_provider(provider, "fmp", "yfinance", "intrinio")
    try:
        return _to_df(obb.equity.profile(ticker, provider=p))
    except Exception as e:
        warnings.warn(f"get_profile({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


# ── Provider Fallback Logic ──────────────────────────────────────────────────
# When FMP free tier blocks a ticker (402 error), automatically try yfinance/SEC.

def _get_providers(*preferred: str) -> list[str]:
    """Build a fallback chain: configured providers first, then free ones."""
    config = load_config()
    result: list[str] = []
    for p in preferred:
        if p in ("yfinance", "sec"):
            result.append(p)
        else:
            key_map = {"fmp": ("fmp", "api_key"), "tiingo": ("tiingo", "api_key"),
                       "intrinio": ("intrinio", "api_key"), "benzinga": ("benzinga", "api_key"),}
            if p in key_map:
                section, field = key_map[p]
                if config.get(section, {}).get(field, ""):
                    result.append(p)
    # Always append yfinance and sec as ultimate fallbacks
    if "yfinance" not in result:
        result.append("yfinance")
    if "sec" not in result:
        result.append("sec")
    return result


def _try_providers(func, *providers: str, **kwargs) -> pd.DataFrame:
    """Call func(provider=p, **kwargs) for each p, return first non-empty result."""
    for p in providers:
        try:
            df = _to_df(func(p, **kwargs))
            if not df.empty:
                return df
        except Exception:
            continue
    return pd.DataFrame()


def get_income_statement(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get income statement (revenue, gross profit, net income, EPS, etc.)."""
    if provider:
        return _to_df(obb.equity.fundamental.income(ticker, period=period, limit=limit, provider=provider))
    return _try_providers(
        lambda p: obb.equity.fundamental.income(ticker, period=period, limit=limit, provider=p),
        *_get_providers("fmp", "sec", "yfinance"),
    )


def get_balance_sheet(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get balance sheet: assets, liabilities, equity, debt, cash."""
    if provider:
        return _to_df(obb.equity.fundamental.balance(ticker, period=period, limit=limit, provider=provider))
    return _try_providers(
        lambda p: obb.equity.fundamental.balance(ticker, period=period, limit=limit, provider=p),
        *_get_providers("fmp", "sec", "yfinance"),
    )


def get_cash_flow(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get cash flow statement: operating cash flow, capex, FCF."""
    if provider:
        return _to_df(obb.equity.fundamental.cash(ticker, period=period, limit=limit, provider=provider))
    return _try_providers(
        lambda p: obb.equity.fundamental.cash(ticker, period=period, limit=limit, provider=p),
        *_get_providers("fmp", "sec", "yfinance"),
    )


def get_key_metrics(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get key financial metrics: P/E, P/B, ROE, ROA, margins, etc."""
    if provider:
        return _to_df(obb.equity.fundamental.metrics(ticker, period=period, limit=limit, provider=provider))
    return _try_providers(
        lambda p: obb.equity.fundamental.metrics(ticker, period=period, limit=limit, provider=p),
        *_get_providers("fmp", "yfinance"),
    )


def get_ratios(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get financial ratios: current ratio, D/E, interest coverage, etc.

    OpenBB: obb.equity.fundamental.ratios()
    Requires FMP provider (premium).
    """
    p = _resolve_provider(provider, "fmp", "intrinio")
    try:
        return _to_df(obb.equity.fundamental.ratios(
            ticker, period=period, limit=limit, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_ratios({ticker}) failed: {e}")
        return pd.DataFrame()


# ── Earnings & Estimates ─────────────────────────────────────────────────────

def get_earnings_history(
    ticker: str,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get historical EPS data.

    OpenBB: obb.equity.fundamental.historical_eps()
    Requires FMP provider.
    """
    p = _resolve_provider(provider, "fmp")
    try:
        return _to_df(obb.equity.fundamental.historical_eps(ticker, provider=p))
    except Exception as e:
        warnings.warn(f"get_earnings_history({ticker}) failed: {e}")
        return pd.DataFrame()


def get_estimates_consensus(
    ticker: str,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get analyst consensus estimates (EPS, revenue, target price).

    OpenBB: obb.equity.estimates.consensus()
    Works with yfinance (free) and fmp (premium).
    """
    if provider:
        return _to_df(obb.equity.estimates.consensus(ticker, provider=provider))
    return _try_providers(
        lambda p: obb.equity.estimates.consensus(ticker, provider=p),
        *_get_providers("fmp", "yfinance"),
    )


def get_price_targets(
    ticker: str,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get analyst price targets.

    OpenBB: obb.equity.estimates.price_target()
    Requires benzinga or fmp.
    """
    p = _resolve_provider(provider, "fmp", "benzinga")
    try:
        return _to_df(obb.equity.estimates.price_target(ticker, provider=p))
    except Exception as e:
        warnings.warn(f"get_price_targets({ticker}) failed: {e}")
        return pd.DataFrame()


# ── News ─────────────────────────────────────────────────────────────────────

def get_news(
    ticker: str,
    start: str | datetime | None = None,
    end: str | datetime | None = None,
    limit: int = 25,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get company-specific news articles.

    OpenBB: obb.news.company()
    Works with yfinance (free), fmp, benzinga, tiingo.

    Args:
        ticker: Stock symbol. Supports multi-ticker: 'AAPL,MSFT'.
        start: Start date. Default: 7 days ago.
        end: End date. Default: today.
        limit: Max articles to return.
    """
    p = _resolve_provider(provider, "tiingo", "yfinance", "fmp", "benzinga")
    if start is None:
        start = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    if isinstance(start, datetime):
        start = start.strftime("%Y-%m-%d")
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if isinstance(end, datetime):
        end = end.strftime("%Y-%m-%d")
    try:
        return _to_df(obb.news.company(
            ticker, start_date=start, end_date=end, limit=limit, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_news({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


# ── SEC Filings ──────────────────────────────────────────────────────────────

def get_sec_filings(
    ticker: str,
    form_type: str | None = None,
    limit: int = 10,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get SEC EDGAR filings for a company.

    OpenBB: obb.equity.fundamental.filings()
    SEC provider is free. FMP also available.

    Args:
        ticker: Stock symbol.
        form_type: Filter by form type (e.g., '10-K', '10-Q', '8-K'). None = all.
        limit: Max filings to return.
    """
    p = _resolve_provider(provider, "fmp", "sec")
    try:
        kwargs = {"symbol": ticker, "limit": limit, "provider": p}
        if form_type is not None:
            kwargs["form_type"] = form_type
        return _to_df(obb.equity.fundamental.filings(**kwargs))
    except Exception as e:
        warnings.warn(f"get_sec_filings({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


def get_insider_trading(
    ticker: str,
    limit: int = 50,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get insider trading activity (Form 4 filings).

    OpenBB: obb.equity.ownership.insider_trading()
    SEC provider is free; FMP also available.
    """
    p = _resolve_provider(provider, "sec", "fmp")
    try:
        return _to_df(obb.equity.ownership.insider_trading(
            ticker, limit=limit, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_insider_trading({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


# ── Peer Comparison ──────────────────────────────────────────────────────────

def get_peers(
    ticker: str,
    provider: str | None = None,
) -> list[str]:
    """Get peer companies for a ticker.

    OpenBB: obb.equity.compare.peers()
    Requires FMP provider.
    """
    p = _resolve_provider(provider, "fmp")
    try:
        result = obb.equity.compare.peers(ticker, provider=p)
        data = _safe_result(result)
        if isinstance(data, list):
            return [str(d.peer if hasattr(d, "peer") else d) for d in data]
        return []
    except Exception as e:
        warnings.warn(f"get_peers({ticker}) failed: {e}")
        return []


def get_peer_metrics(
    tickers: list[str],
    provider: str | None = None,
) -> pd.DataFrame:
    """Get key metrics for a list of peer tickers.

    Fetches metrics + ratios for each ticker and combines into a comparison table.
    Uses FMP ratios for valuation multiples when available.

    Args:
        tickers: List of ticker symbols.
        provider: Override the default provider.

    Returns:
        DataFrame with one row per ticker, columns for key valuation metrics.
    """
    all_metrics = []
    for t in tickers:
        try:
            profile = get_profile(t, provider=provider)
            metrics = get_key_metrics(t, limit=1, provider=provider)
            ratios = get_ratios(t, limit=1, provider=provider)

            row: dict[str, Any] = {"ticker": t.upper()}

            if not profile.empty:
                row["name"] = _col(profile, "name", "company_name")
                row["sector"] = _col(profile, "sector")
                row["market_cap"] = _col(profile, "market_cap")

            # Merge metrics + ratios: ratios has P/E, P/B, etc. (FMP)
            for source in [metrics, ratios]:
                if source is None or source.empty:
                    continue
                m = source.iloc[0]
                for field in [
                    "pe_ratio", "pb_ratio", "ps_ratio", "price_to_fcf",
                    "ev_to_ebitda", "ev_to_sales", "peg_ratio",
                    "roe", "roa", "roic",
                    "gross_margin", "operating_margin", "net_margin",
                    "revenue_growth",
                    "debt_to_equity", "current_ratio", "dividend_yield",
                    "earnings_yield", "fcf_yield",
                ]:
                    if field in source.columns and field not in row:
                        val = m[field]
                        if val is not None and not (isinstance(val, float) and pd.isna(val)):
                            row[field] = val

            all_metrics.append(row)
        except Exception as e:
            warnings.warn(f"get_peer_metrics: failed for {t}: {e}")
            all_metrics.append({"ticker": t.upper(), "name": t})

    return pd.DataFrame(all_metrics)


# ── Convenience ──────────────────────────────────────────────────────────────

def fetch_all_financials(
    ticker: str,
    provider: str | None = None,
) -> dict[str, pd.DataFrame]:
    """Fetch all financial statements for a ticker in one call.

    Args:
        ticker: Stock symbol.
        provider: Override the default.

    Returns:
        Dict with keys: profile, income, balance, cashflow, metrics, estimates.
    """
    return {
        "profile": get_profile(ticker, provider=provider),
        "income": get_income_statement(ticker, provider=provider),
        "balance": get_balance_sheet(ticker, provider=provider),
        "cashflow": get_cash_flow(ticker, provider=provider),
        "metrics": get_key_metrics(ticker, provider=provider),
        "estimates": get_estimates_consensus(ticker, provider=provider),
    }


def fetch_all_for_ticker(
    ticker: str,
    days_of_news: int = 7,
    provider: str | None = None,
) -> dict[str, Any]:
    """Fetch ALL data for a ticker — financials + news + filings + price.

    This is the one-stop-shop for any ticker. Used by scripts and notebooks.

    Returns:
        Dict with: ticker, profile, income, balance, cashflow, metrics,
                   estimates, news, filings, insider_trades, peers, price_history.
    """
    data: dict[str, Any] = {"ticker": ticker.upper()}

    # Financials
    data["profile"] = get_profile(ticker, provider=provider)
    data["income"] = get_income_statement(ticker, provider=provider)
    data["balance"] = get_balance_sheet(ticker, provider=provider)
    data["cashflow"] = get_cash_flow(ticker, provider=provider)
    data["metrics"] = get_key_metrics(ticker, provider=provider)
    data["ratios"] = get_ratios(ticker, provider=provider)
    data["estimates"] = get_estimates_consensus(ticker, provider=provider)

    # News — convert days to date range
    end_date = datetime.now().strftime("%Y-%m-%d")
    start_date = (datetime.now() - timedelta(days=days_of_news)).strftime("%Y-%m-%d")
    data["news"] = get_news(ticker, start=start_date, end=end_date, limit=50, provider=provider)

    # SEC
    data["filings"] = get_sec_filings(ticker, limit=10, provider=provider)
    data["insider_trades"] = get_insider_trading(ticker, limit=20, provider=provider)

    # Price
    data["price_history"] = get_price_history(ticker, provider=provider)
    data["quote"] = get_quote(ticker, provider=provider)

    # Peers
    data["peers"] = get_peers(ticker, provider=provider)

    return data
