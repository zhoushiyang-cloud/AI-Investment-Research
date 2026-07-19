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
        return result.to_dataframe(**kwargs)  # type: ignore[union-attr]
    except Exception:
        # Fallback: try to build DataFrame from results list
        data = _safe_result(result)
        if isinstance(data, pd.DataFrame):
            return data
        if isinstance(data, list) and len(data) > 0:
            try:
                return pd.DataFrame([d.model_dump() if hasattr(d, "model_dump") else d for d in data])
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


# ── Price & Market Data ──────────────────────────────────────────────────────

def get_quote(ticker: str, provider: str | None = None) -> pd.DataFrame:
    """Get real-time quote for a ticker.

    OpenBB: obb.equity.price.quote()
    """
    p = _resolve_provider(provider, "yfinance", "fmp", "intrinio")
    try:
        return _to_df(obb.equity.price.quote(ticker, provider=p))
    except Exception as e:
        warnings.warn(f"get_quote({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


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
    p = _resolve_provider(provider, "yfinance", "fmp", "tiingo")
    if start is None:
        start = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    if isinstance(start, datetime):
        start = start.strftime("%Y-%m-%d")
    if end is None:
        end = datetime.now().strftime("%Y-%m-%d")
    if isinstance(end, datetime):
        end = end.strftime("%Y-%m-%d")
    try:
        return _to_df(obb.equity.price.historical(
            ticker, start_date=start, end_date=end, interval=interval, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_price_history({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


# ── Company Profile & Fundamentals ───────────────────────────────────────────

def get_profile(ticker: str, provider: str | None = None) -> pd.DataFrame:
    """Get company profile: sector, industry, market cap, employees, description.

    OpenBB: obb.equity.profile()
    """
    p = _resolve_provider(provider, "yfinance", "fmp", "intrinio")
    try:
        return _to_df(obb.equity.profile(ticker, provider=p))
    except Exception as e:
        warnings.warn(f"get_profile({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


def get_income_statement(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get income statement (revenue, gross profit, net income, EPS, etc.).

    OpenBB: obb.equity.fundamental.income()

    Args:
        ticker: Stock symbol.
        period: 'annual' or 'quarter'.
        limit: Number of periods to return.
    """
    p = _resolve_provider(provider, "yfinance", "fmp", "intrinio", "sec")
    try:
        return _to_df(obb.equity.fundamental.income(
            ticker, period=period, limit=limit, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_income_statement({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


def get_balance_sheet(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get balance sheet: assets, liabilities, equity, debt, cash.

    OpenBB: obb.equity.fundamental.balance()
    """
    p = _resolve_provider(provider, "yfinance", "fmp", "intrinio", "sec")
    try:
        return _to_df(obb.equity.fundamental.balance(
            ticker, period=period, limit=limit, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_balance_sheet({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


def get_cash_flow(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get cash flow statement: operating cash flow, capex, FCF.

    OpenBB: obb.equity.fundamental.cash()
    """
    p = _resolve_provider(provider, "yfinance", "fmp", "intrinio", "sec")
    try:
        return _to_df(obb.equity.fundamental.cash(
            ticker, period=period, limit=limit, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_cash_flow({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


def get_key_metrics(
    ticker: str,
    period: str = "annual",
    limit: int = 5,
    provider: str | None = None,
) -> pd.DataFrame:
    """Get key financial metrics: P/E, P/B, ROE, ROA, margins, etc.

    OpenBB: obb.equity.fundamental.metrics()
    """
    p = _resolve_provider(provider, "yfinance", "fmp", "intrinio")
    try:
        return _to_df(obb.equity.fundamental.metrics(
            ticker, period=period, limit=limit, provider=p,
        ))
    except Exception as e:
        warnings.warn(f"get_key_metrics({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


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
    p = _resolve_provider(provider, "yfinance", "fmp")
    try:
        return _to_df(obb.equity.estimates.consensus(ticker, provider=p))
    except Exception as e:
        warnings.warn(f"get_estimates_consensus({ticker}) failed with {p}: {e}")
        return pd.DataFrame()


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
    p = _resolve_provider(provider, "yfinance", "benzinga", "fmp", "tiingo")
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
    SEC provider is free.

    Args:
        ticker: Stock symbol.
        form_type: Filter by form type (e.g., '10-K', '10-Q', '8-K'). None = all.
        limit: Max filings to return.
    """
    p = _resolve_provider(provider, "sec", "fmp")
    try:
        return _to_df(obb.equity.fundamental.filings(
            ticker, form_type=form_type, limit=limit, provider=p,
        ))
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

    Fetches metrics for each ticker and combines into a comparison table.

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

            row: dict[str, Any] = {"ticker": t.upper()}

            if not profile.empty:
                row["name"] = profile.iloc[0].get("name", t)
                row["sector"] = profile.iloc[0].get("sector", "")
                row["market_cap"] = profile.iloc[0].get("market_cap", None)

            if not metrics.empty:
                m = metrics.iloc[0]
                row["pe_ratio"] = m.get("pe_ratio", None)
                row["pb_ratio"] = m.get("pb_ratio", None)
                row["ps_ratio"] = m.get("ps_ratio", None)
                row["ev_to_ebitda"] = m.get("ev_to_ebitda", None)
                row["roe"] = m.get("roe", None)
                row["roa"] = m.get("roa", None)
                row["revenue_growth"] = m.get("revenue_growth", None)
                row["gross_margin"] = m.get("gross_margin", None)
                row["operating_margin"] = m.get("operating_margin", None)
                row["net_margin"] = m.get("net_margin", None)

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
    data["estimates"] = get_estimates_consensus(ticker, provider=provider)

    # News
    data["news"] = get_news(ticker, days=days_of_news, provider=provider)

    # SEC
    data["filings"] = get_sec_filings(ticker, limit=10, provider=provider)
    data["insider_trades"] = get_insider_trading(ticker, limit=20, provider=provider)

    # Price
    data["price_history"] = get_price_history(ticker, provider=provider)
    data["quote"] = get_quote(ticker, provider=provider)

    # Peers
    data["peers"] = get_peers(ticker, provider=provider)

    return data
