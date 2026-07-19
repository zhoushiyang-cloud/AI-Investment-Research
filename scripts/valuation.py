"""
valuation.py — Run valuation models using live data from OpenBB.

Models:
    - Discounted Cash Flow (DCF) — auto-populated from financials
    - Comparable Company Analysis (Comps)
    - Graham Number

Usage:
    python scripts/valuation.py --ticker NVDA [--model dcf] [--model comps] [--all-models]
    python scripts/valuation.py --all --all-models
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_engine import (
    get_cash_flow,
    get_income_statement,
    get_balance_sheet,
    get_key_metrics,
    get_estimates_consensus,
    get_profile,
    get_peer_metrics,
)
from src.config import load_config


# ── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class DCFParams:
    free_cash_flow: float   # TTM FCF in millions
    growth_rate: float      # Next 5yr annual growth (e.g., 0.25 = 25%)
    terminal_growth: float = 0.03
    discount_rate: float = 0.10
    shares_outstanding: float = 1.0  # In millions
    net_debt: float = 0.0   # In millions (negative = net cash)
    years: int = 5


@dataclass
class DCFResult:
    fair_value_per_share: float
    total_enterprise_value: float
    implied_market_cap: float
    annual_fcfs: list[float]
    terminal_value: float


@dataclass
class CompsResult:
    ticker: str
    peer_metrics: pd.DataFrame
    median_pe: float | None
    median_ev_ebitda: float | None
    implied_pe_price: float | None
    implied_ev_price: float | None
    current_price: float | None


# ── DCF Model ────────────────────────────────────────────────────────────────

def run_dcf(params: DCFParams) -> DCFResult:
    """Run a Discounted Cash Flow valuation.

    Args:
        params: DCF input parameters.

    Returns:
        DCFResult with fair value estimate.
    """
    annual_fcfs: list[float] = []
    fcf = params.free_cash_flow

    for year in range(1, params.years + 1):
        fcf *= (1 + params.growth_rate)
        annual_fcfs.append(fcf)

    # Terminal value (Gordon Growth Model)
    terminal_fcf = annual_fcfs[-1] * (1 + params.terminal_growth)
    terminal_value = terminal_fcf / (params.discount_rate - params.terminal_growth)

    # Discount projected FCFs
    pv_fcfs = sum(
        fcf / (1 + params.discount_rate) ** (i + 1)
        for i, fcf in enumerate(annual_fcfs)
    )
    pv_terminal = terminal_value / (1 + params.discount_rate) ** params.years

    enterprise_value = pv_fcfs + pv_terminal
    market_cap = enterprise_value - params.net_debt
    fair_value = market_cap / params.shares_outstanding

    return DCFResult(
        fair_value_per_share=round(fair_value, 2),
        total_enterprise_value=round(enterprise_value, 2),
        implied_market_cap=round(market_cap, 2),
        annual_fcfs=[round(f, 2) for f in annual_fcfs],
        terminal_value=round(terminal_value, 2),
    )


def auto_dcf_params(ticker: str, discount_rate: float = 0.10,
                    terminal_growth: float = 0.03) -> DCFParams | None:
    """Auto-populate DCF parameters from live financial data.

    Args:
        ticker: Stock ticker symbol.
        discount_rate: WACC override (default 10%).
        terminal_growth: Terminal growth rate (default 3%).

    Returns:
        DCFParams populated from data, or None if data unavailable.
    """
    # Cash flow → FCF
    cf = get_cash_flow(ticker, period="annual", limit=1)
    fcf = 0
    if not cf.empty:
        if "free_cash_flow" in cf.columns and pd.notna(cf.iloc[0]["free_cash_flow"]):
            fcf = float(cf.iloc[0]["free_cash_flow"]) / 1_000_000  # To millions
        elif "operating_cash_flow" in cf.columns and "capital_expenditure" in cf.columns:
            ocf = float(cf.iloc[0]["operating_cash_flow"] or 0)
            capex = float(cf.iloc[0]["capital_expenditure"] or 0)
            fcf = (ocf - abs(capex)) / 1_000_000

    if fcf <= 0:
        print(f"  ⚠️  Cannot derive positive FCF for {ticker}. Using estimate.")
        fcf = 10_000  # Fallback

    # Revenue growth from income statement (CAGR over historical periods)
    income = get_income_statement(ticker, period="annual", limit=5)
    growth_rate = 0.15  # Default 15%
    if not income.empty and "total_revenue" in income.columns and len(income) >= 2:
        # Sort oldest-first for correct CAGR computation
        if "period_ending" in income.columns:
            income = income.sort_values("period_ending")
        revs = income["total_revenue"].dropna().values
        if len(revs) >= 2 and revs[0] > 0:
            cagr = (revs[-1] / revs[0]) ** (1 / (len(revs) - 1)) - 1
            growth_rate = max(0.03, min(0.60, cagr))  # Clamp 3%-60%

    # Shares outstanding from metrics
    metrics = get_key_metrics(ticker, limit=1)
    shares = 1_000  # Default 1B shares
    if not metrics.empty:
        for col in ["shares_outstanding", "weighted_average_shares"]:
            if col in metrics.columns and pd.notna(metrics.iloc[0].get(col)):
                shares = float(metrics.iloc[0][col]) / 1_000_000  # To millions
                break

    # Net debt from balance sheet
    balance = get_balance_sheet(ticker, period="annual", limit=1)
    net_debt = 0
    if not balance.empty:
        total_debt = 0
        cash = 0
        if "total_debt" in balance.columns:
            total_debt = float(balance.iloc[0]["total_debt"] or 0) / 1_000_000
        if "cash_and_equivalents" in balance.columns:
            cash = float(balance.iloc[0]["cash_and_equivalents"] or 0) / 1_000_000
        net_debt = total_debt - cash

    return DCFParams(
        free_cash_flow=fcf,
        growth_rate=growth_rate,
        terminal_growth=terminal_growth,
        discount_rate=discount_rate,
        shares_outstanding=shares,
        net_debt=net_debt,
    )


def sensitivity_analysis(params: DCFParams) -> pd.DataFrame:
    """Run DCF sensitivity across growth and discount rate ranges.

    Returns a matrix DataFrame: rows=discount rates, cols=growth rates.
    """
    wacc_range = [params.discount_rate + d for d in [-0.03, -0.02, -0.01, 0, 0.01, 0.02, 0.03]
                  if params.discount_rate + d > params.terminal_growth]
    growth_range = [params.growth_rate + g for g in [-0.10, -0.05, 0, 0.05, 0.10]
                    if params.growth_rate + g > 0]

    matrix: dict[str, list[float]] = {}
    for wacc in wacc_range:
        row: list[float] = []
        for growth in growth_range:
            p = DCFParams(
                free_cash_flow=params.free_cash_flow,
                growth_rate=growth,
                terminal_growth=params.terminal_growth,
                discount_rate=wacc,
                shares_outstanding=params.shares_outstanding,
                net_debt=params.net_debt,
                years=params.years,
            )
            r = run_dcf(p)
            row.append(r.fair_value_per_share)
        matrix[f"WACC {wacc:.0%}"] = row

    index = [f"Growth {g:.0%}" for g in growth_range]
    return pd.DataFrame(matrix, index=index)


# ── Comps Model ──────────────────────────────────────────────────────────────

def run_comps(ticker: str, peers: list[str] | None = None) -> CompsResult | None:
    """Run comparable company analysis.

    Args:
        ticker: Target stock ticker.
        peers: List of peer tickers. Auto-detected if None.

    Returns:
        CompsResult with relative valuation analysis.
    """
    if peers is None:
        peers = {
            "NVDA": ["AMD", "INTC", "AVGO", "QCOM", "MRVL"],
            "AVGO": ["NVDA", "AMD", "MRVL", "QCOM", "INTC"],
            "ORCL": ["MSFT", "CRM", "ADBE", "SAP", "IBM"],
        }.get(ticker.upper(), ["AMD", "INTC"])

    all_tickers = [ticker] + peers
    df = get_peer_metrics(all_tickers)

    if df.empty or "ticker" not in df.columns:
        print("  ⚠️  No peer data available.")
        return None

    target_row = df[df["ticker"] == ticker.upper()]
    peer_rows = df[df["ticker"] != ticker.upper()]

    # Filter: only positive P/E (negative = unprofitable, doesn't make sense for comps)
    valid_pe = peer_rows[peer_rows["pe_ratio"] > 0]["pe_ratio"] if "pe_ratio" in peer_rows else pd.Series()
    median_pe = valid_pe.dropna().median() if len(valid_pe) > 0 else None
    valid_ev = peer_rows[peer_rows["ev_to_ebitda"] > 0]["ev_to_ebitda"] if "ev_to_ebitda" in peer_rows else pd.Series()
    median_ev_ebitda = valid_ev.dropna().median() if len(valid_ev) > 0 else None

    # Implied prices
    target_eps = target_row.iloc[0].get("pe_ratio")
    # Derive EPS from P/E: EPS = Price / PE
    implied_pe_price = None
    implied_ev_price = None

    print(f"\n{'='*60}")
    print(f"  Comps Analysis — {ticker}")
    print(f"{'='*60}")
    print(f"\n  Peer Group: {', '.join(peers)}")
    print(f"\n  {'Ticker':<8} {'P/E':>8} {'EV/EBITDA':>10} {'Rev Growth':>10} {'Gross Margin':>12}")
    print(f"  {'─'*8} {'─'*8} {'─'*10} {'─'*10} {'─'*12}")
    for _, row in df.iterrows():
        t = row.get("ticker", "—")
        pe = row.get("pe_ratio")
        ev = row.get("ev_to_ebitda")
        rg = row.get("revenue_growth")
        gm = row.get("gross_margin")
        print(f"  {t:<8} {pe:>8.1f}" if pe else f"  {t:<8} {'—':>8}",
              end="")
        print(f" {ev:>10.1f}" if ev else f" {'—':>10}", end="")
        print(f" {rg:>10.1%}" if rg and not (isinstance(rg, float) and pd.isna(rg)) else f" {'—':>10}", end="")
        print(f" {gm:>12.1%}" if gm and not (isinstance(gm, float) and pd.isna(gm)) else f" {'—':>12}")

    print(f"\n  Median P/E:     {median_pe:.1f}x" if median_pe and not pd.isna(median_pe) else "\n  Median P/E:     —")
    print(f"  Median EV/EBITDA: {median_ev_ebitda:.1f}x" if median_ev_ebitda and not pd.isna(median_ev_ebitda) else "  Median EV/EBITDA: —")
    print(f"{'='*60}\n")

    return CompsResult(
        ticker=ticker,
        peer_metrics=df,
        median_pe=median_pe if not pd.isna(median_pe) else None,
        median_ev_ebitda=median_ev_ebitda if not pd.isna(median_ev_ebitda) else None,
        implied_pe_price=implied_pe_price,
        implied_ev_price=implied_ev_price,
        current_price=None,
    )


# ── Graham Number ────────────────────────────────────────────────────────────

def run_graham(ticker: str) -> dict[str, Any]:
    """Calculate the Graham Number: sqrt(22.5 × EPS × BVPS).

    If Graham Number > current price, the stock may be undervalued
    per Benjamin Graham's value investing criteria.

    Args:
        ticker: Stock ticker symbol.

    Returns:
        Dict with EPS, BVPS, Graham Number, and current price.
    """
    income = get_income_statement(ticker, period="annual", limit=1)
    balance = get_balance_sheet(ticker, period="annual", limit=1)
    metrics = get_key_metrics(ticker, limit=1)

    eps = None
    bvps = None

    if not income.empty and "eps_diluted" in income.columns:
        eps = income.iloc[0]["eps_diluted"]

    if not balance.empty and "total_equity" in balance.columns:
        equity = float(balance.iloc[0]["total_equity"] or 0) / 1_000_000  # To millions
        shares = 1_000
        if not metrics.empty and "shares_outstanding" in metrics.columns:
            shares = float(metrics.iloc[0].get("shares_outstanding", 1_000_000_000)) / 1_000_000
        if shares > 0:
            bvps = equity / shares

    print(f"\n{'='*60}")
    print(f"  Graham Number — {ticker}")
    print(f"{'='*60}")

    graham_number = None
    if eps and bvps and eps > 0 and bvps > 0:
        graham_number = (22.5 * eps * bvps) ** 0.5
        print(f"  EPS (TTM):       ${eps:.2f}")
        print(f"  Book Value/Sh:   ${bvps:.2f}")
        print(f"  Graham Number:   ${graham_number:.2f}")
        print(f"\n  Interpretation: Graham suggested buying below ${graham_number:.2f}")
    else:
        print(f"  ⚠️  Insufficient data. EPS={eps}, BVPS={bvps}")
    print(f"{'='*60}\n")

    return {"eps": eps, "bvps": bvps, "graham_number": graham_number}


# ── Display Helpers ──────────────────────────────────────────────────────────

def print_dcf_result(ticker: str, params: DCFParams, result: DCFResult) -> None:
    """Pretty-print DCF valuation result."""
    print(f"\n{'='*60}")
    print(f"  DCF Valuation — {ticker.upper()}")
    print(f"{'='*60}")
    print(f"  TTM FCF:           ${params.free_cash_flow:,.0f}M")
    print(f"  Growth Rate:       {params.growth_rate:.0%}")
    print(f"  Terminal Growth:   {params.terminal_growth:.0%}")
    print(f"  Discount Rate:     {params.discount_rate:.0%}")
    print(f"  Shares Out:        {params.shares_outstanding:,.0f}M")
    print(f"{'─'*60}")
    for i, fcf in enumerate(result.annual_fcfs, 1):
        print(f"  Year {i} FCF:         ${fcf:,.0f}M")
    print(f"  Terminal Value:    ${result.terminal_value:,.0f}M")
    print(f"{'─'*60}")
    print(f"  Enterprise Value:  ${result.total_enterprise_value:,.0f}M")
    print(f"  Fair Value/Share:  ${result.fair_value_per_share:.2f}")
    print(f"{'='*60}\n")


def print_sensitivity(params: DCFParams, sens: pd.DataFrame) -> None:
    """Print sensitivity analysis table."""
    print(f"\n{'='*60}")
    print(f"  Sensitivity Analysis — Fair Value / Share")
    print(f"  (Discount Rate ↓ vs Growth Rate →)")
    print(f"{'='*60}")
    print(sens.to_string(float_format=lambda x: f"${x:.2f}"))
    print(f"{'='*60}\n")


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Run valuation models")
    parser.add_argument("--ticker", type=str, help="Ticker to value")
    parser.add_argument("--all", action="store_true", help="Value all tracked companies")
    parser.add_argument("--model", type=str, action="append", dest="models",
                        choices=["dcf", "comps", "graham"],
                        help="Valuation model(s) to run")
    parser.add_argument("--all-models", action="store_true", help="Run all models")
    parser.add_argument("--wacc", type=float, default=0.10, help="Discount rate (default: 0.10)")
    parser.add_argument("--growth", type=float, help="Override auto-detected growth rate")
    parser.add_argument("--terminal", type=float, default=0.03, help="Terminal growth (default: 0.03)")
    parser.add_argument("--sensitivity", action="store_true", help="Run DCF sensitivity analysis")
    args = parser.parse_args()

    models: list[str] = args.models or []
    if args.all_models:
        models = ["dcf", "comps", "graham"]

    if not models:
        print("Usage: python valuation.py --ticker NVDA [--model dcf] [--all-models] [--sensitivity]")
        sys.exit(1)

    tracked = ["NVDA", "AVGO", "ORCL"]
    tickers: list[str] = []
    if args.all:
        tickers = tracked
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        print("Please specify --ticker or --all")
        sys.exit(1)

    for ticker in tickers:
        for model in models:
            if model == "dcf":
                params = auto_dcf_params(
                    ticker,
                    discount_rate=args.wacc,
                    terminal_growth=args.terminal,
                )
                if args.growth is not None:
                    params.growth_rate = args.growth
                result = run_dcf(params)
                print_dcf_result(ticker, params, result)

                if args.sensitivity:
                    sens = sensitivity_analysis(params)
                    print_sensitivity(params, sens)

            elif model == "comps":
                run_comps(ticker)

            elif model == "graham":
                run_graham(ticker)


if __name__ == "__main__":
    main()
