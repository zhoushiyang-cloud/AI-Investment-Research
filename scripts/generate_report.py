"""
generate_report.py — LLM-powered investment research report generator.

Uses the Anthropic (Claude) or OpenAI API to synthesize all available
financial data into a professional investment memo.

Usage:
    python scripts/generate_report.py --ticker NVDA
    python scripts/generate_report.py --all
    python scripts/generate_report.py --ticker NVDA --provider openai
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_engine import fetch_all_for_ticker, get_price_targets
from src.markdown import generate_report_md
from src.config import load_config


def build_analysis_prompt(ticker: str, data: dict) -> str:
    """Build a comprehensive analysis prompt from ALL available live data.

    Uses EVERY data source from fetch_all_for_ticker() — profile, metrics, ratios,
    financial statements, estimates, price targets, K-line price history,
    SEC filings, insider trades, news, peers, and current quote.

    Args:
        ticker: Stock ticker symbol.
        data: Full data dict from fetch_all_for_ticker().

    Returns:
        Prompt string ready for an LLM, packed with all available data.
    """
    profile = data.get("profile")
    metrics = data.get("metrics")
    ratios = data.get("ratios")
    income = data.get("income")
    balance = data.get("balance")
    cashflow = data.get("cashflow")
    estimates = data.get("estimates")
    price_targets = data.get("price_targets")
    news = data.get("news")
    filings = data.get("filings")
    insider = data.get("insider_trades")
    price_history = data.get("price_history")
    quote = data.get("quote")
    peers = data.get("peers", [])

    # Build a data-rich context block
    prompt = f"""You are a senior equity research analyst. Write a professional investment memo for {ticker}.

## Available Data

### Current Quote
"""
    if quote is not None and not quote.empty:
        for col in quote.columns:
            val = quote.iloc[0][col]
            if val is not None:
                prompt += f"- {col}: {val}\n"

    prompt += "\n### Company Profile\n"
    if profile is not None and not profile.empty:
        for col in profile.columns:
            val = profile.iloc[0][col]
            if val is not None:
                prompt += f"- {col}: {val}\n"

    if metrics is not None and not metrics.empty:
        prompt += "\n### Key Metrics (Latest)\n"
        m = metrics.iloc[0]
        for col in metrics.columns:
            val = m[col]
            if val is not None:
                prompt += f"- {col}: {val}\n"

    if ratios is not None and not ratios.empty:
        prompt += "\n### Financial Ratios (Latest)\n"
        r = ratios.iloc[0]
        for col in ratios.columns:
            val = r[col]
            if val is not None:
                prompt += f"- {col}: {val}\n"

    if income is not None and not income.empty:
        prompt += f"\n### Income Statement\n{income.head(3).to_string()}\n"

    if balance is not None and not balance.empty:
        prompt += f"\n### Balance Sheet\n{balance.head(3).to_string()}\n"

    if cashflow is not None and not cashflow.empty:
        prompt += f"\n### Cash Flow\n{cashflow.head(3).to_string()}\n"

    if estimates is not None and not estimates.empty:
        prompt += f"\n### Analyst Estimates\n{estimates.to_string()}\n"

    if price_targets is not None and not price_targets.empty:
        prompt += f"\n### Price Targets\n{price_targets.to_string()}\n"

    if price_history is not None and not price_history.empty:
        prompt += "\n### Recent Price History (K-Line, last 10 days)\n"
        prompt += f"{price_history.tail(10).to_string()}\n"
        # Add price trend summary
        if len(price_history) >= 10:
            recent = price_history.tail(10)
            if "close" in recent.columns:
                first_close = recent.iloc[0]["close"]
                last_close = recent.iloc[-1]["close"]
                high_val = recent["high"].max()
                low_val = recent["low"].min()
                change_pct = ((last_close - first_close) / first_close) * 100
                prompt += f"Price trend: {first_close:.2f} → {last_close:.2f} ({change_pct:+.1f}%), "
                prompt += f"high ${high_val:.2f}, low ${low_val:.2f}\n"

    if news is not None and not news.empty:
        prompt += "\n### Recent News Headlines\n"
        for _, a in news.head(15).iterrows():
            title = a.get("title", "N/A")
            source = a.get("source", "")
            date_str = str(a.get("date", ""))[:10] if a.get("date") is not None else "?"
            prompt += f"- [{date_str}] {title} ({source})\n"

    if filings is not None and not filings.empty:
        prompt += "\n### Recent SEC Filings\n"
        for _, f in filings.head(10).iterrows():
            filing_date = str(f.get("filing_date", "?"))[:10]
            form = f.get("form_type", f.get("type", "?"))
            prompt += f"- {filing_date}: {form}\n"

    if insider is not None and not insider.empty:
        prompt += "\n### Recent Insider Trading\n"
        for _, t in insider.head(10).iterrows():
            name = t.get("name", t.get("reporting_person", "?"))
            tran_type = t.get("transaction_type", t.get("type", "?"))
            shares = t.get("shares", t.get("shares_traded", "?"))
            price = t.get("price", t.get("transaction_price", "?"))
            prompt += f"- {name}: {tran_type} {shares} shares @ ${price}\n"

    if peers:
        prompt += f"\n### Peers\n{', '.join(str(p) for p in peers)}\n"

    prompt += """
## Instructions

Write a comprehensive investment memo. **Use Obsidian callout syntax** throughout:

> [!abstract] Executive Summary
> 3-5 bullet points — key takeaways in 30 seconds

> [!info] Business Overview
> What the company does, competitive position, key segments with revenue share

> [!example] Financial Analysis
> Revenue trends, margins, cash flow, balance sheet. **Cite specific numbers** from the data above.

> [!info] Valuation Assessment
> Current multiples (P/E, EV/EBITDA, etc.) vs peers vs history. Are they justified?

> [!warning] Risks
> Numbered list with severity tags: `#critical`, `#medium`, `#low`. Concrete risks — NOT generic.

> [!tip] Catalysts
> What could drive upside in 6-18 months. Tag each: `#near-term` or `#medium-term`.

> [!quote] Recommendation
> **Buy / Hold / Sell** with conviction (High/Medium/Low). Price target and 12-month thesis.

IMPORTANT:
- Output ONLY the callout blocks above, filled with analysis. No preamble, no sign-off.
- Use [[wikilinks]] when referencing other companies: [[NVDA]], [[AVGO]], etc.
- **Cite specific numbers from the data above.** NEVER invent or hallucinate financial figures.
- If a data section above is empty/missing, say "data not available" — do NOT guess.
- For Risks, use this format:
  ```
  > [!warning] Risks
  > 1. **Risk Name** `#critical`
  >    Specific explanation with numbers if applicable
  > 2. **Risk Name** `#medium`
  >    ...
  ```
- Keep each section concise. The reader is an experienced investor.
"""

    return prompt


def run_claude(prompt: str, config: dict) -> str | None:
    """Call Claude API for report generation.

    Args:
        prompt: The analysis prompt.
        config: Full config dict.

    Returns:
        Generated report text, or None on failure.
    """
    try:
        from anthropic import Anthropic
    except ImportError:
        print("  [WARN] anthropic package not installed. Run: pip install anthropic")
        return None

    api_key = config.get("anthropic", {}).get("api_key", "")
    model = config.get("anthropic", {}).get("model", "claude-sonnet-4-20250514")

    if not api_key:
        print("  [WARN] No Anthropic API key configured in config/api_keys.toml")
        return None

    print(f"  [LLM] Calling Claude ({model})...")

    try:
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            messages=[{"role": "user", "content": prompt}],
        )
        # Extract text from response
        for block in response.content:
            if hasattr(block, "text"):
                return block.text
        return str(response.content[0])
    except Exception as e:
        print(f"  [Error]Claude API error: {e}")
        return None


def run_openai(prompt: str, config: dict) -> str | None:
    """Call OpenAI API for report generation.

    Args:
        prompt: The analysis prompt.
        config: Full config dict.

    Returns:
        Generated report text, or None on failure.
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("  [WARN] openai package not installed. Run: pip install openai")
        return None

    api_key = config.get("openai", {}).get("api_key", "")
    model = config.get("openai", {}).get("model", "gpt-4o")

    if not api_key:
        print("  [WARN] No OpenAI API key configured in config/api_keys.toml")
        return None

    print(f"  [LLM] Calling OpenAI ({model})...")

    try:
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  [Error] OpenAI API: {e}")
        return None


def run_deepseek(prompt: str, config: dict) -> str | None:
    """Call DeepSeek API for report generation.

    DeepSeek's API is OpenAI-compatible (https://api.deepseek.com/v1).
    Use your DeepSeek API key — the same one you configured in Claude Code
    via `cc switch`.

    Args:
        prompt: The analysis prompt.
        config: Full config dict.

    Returns:
        Generated report text, or None on failure.
    """
    try:
        from openai import OpenAI
    except ImportError:
        print("  [WARN] openai package not installed. Run: pip install openai")
        return None

    api_key = config.get("deepseek", {}).get("api_key", "")
    model = config.get("deepseek", {}).get("model", "deepseek-chat")
    base_url = config.get("deepseek", {}).get("base_url", "https://api.deepseek.com/v1")

    if not api_key:
        print("  [WARN] No DeepSeek API key configured in config/api_keys.toml")
        print("  Add [deepseek] section with api_key and base_url.")
        return None

    print(f"  [LLM] Calling DeepSeek ({model}) via {base_url}...")

    try:
        client = OpenAI(api_key=api_key, base_url=base_url)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=4096,
            temperature=0.3,
        )
        return response.choices[0].message.content
    except Exception as e:
        print(f"  [Error] DeepSeek API: {e}")
        return None


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate LLM investment research reports")
    parser.add_argument("--ticker", type=str, help="Single ticker to analyze")
    parser.add_argument("--all", action="store_true", help="Generate for all tracked companies")
    parser.add_argument("--provider", type=str, default="deepseek",
                        choices=["anthropic", "openai", "deepseek"],
                        help="LLM provider (default: deepseek)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show prompt without calling LLM")
    parser.add_argument("--sync", action="store_true", default=True,
                        help="Auto-sync portal after report generation (default: True)")
    parser.add_argument("--no-sync", action="store_true",
                        help="Skip portal sync after report generation")
    args = parser.parse_args()

    tracked = ["NVDA", "AVGO", "ORCL"]

    tickers: list[str] = []
    if args.all:
        tickers = tracked
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        print("Usage: python generate_report.py [--ticker NVDA] [--all]")
        sys.exit(1)

    config = load_config()
    reports_dir = Path(__file__).resolve().parent.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)

    for ticker in tickers:
        print(f"\n{'='*60}")
        print(f"  Generating Report: {ticker}")
        print(f"{'='*60}")

        # Fetch all data (30 days news for richer context)
        print(f"  [Data] Fetching financials, metrics, news (30d), filings, insider trades, K-line...")
        data = fetch_all_for_ticker(ticker, days_of_news=30)

        # Also try fetching price targets from Benzinga/FMP
        print(f"  [Data] Fetching analyst price targets (Benzinga/FMP)...")
        data["price_targets"] = get_price_targets(ticker)

        # Build enriched prompt
        prompt = build_analysis_prompt(ticker, data)

        if args.dry_run:
            prompt_path = reports_dir / f"{ticker}_prompt_{datetime.now().strftime('%Y-%m-%d')}.md"
            prompt_path.write_text(prompt, encoding="utf-8")
            print(f"  [DryRun] Prompt saved to {prompt_path}")
            print(f"  [DryRun] No LLM called.")
            continue

        # Call LLM
        if args.provider == "deepseek":
            analysis = run_deepseek(prompt, config)
        elif args.provider == "openai":
            analysis = run_openai(prompt, config)
        else:
            analysis = run_claude(prompt, config)

        if analysis is None:
            print(f"  [WARN] Report generation failed for {ticker}.")
            continue

        # Generate and save report
        report = generate_report_md(ticker, data, analysis)
        report_path = reports_dir / f"{ticker}_report_{datetime.now().strftime('%Y-%m-%d')}.md"
        report_path.write_text(report, encoding="utf-8")

        print(f"  [OK]Report saved to {report_path}")

    print(f"\n[Done] Report generation complete.")

    # Auto-sync portal if enabled
    if not args.dry_run and args.sync and not args.no_sync:
        print(f"\n{'='*60}")
        print(f"  Auto-syncing portal to GitHub Pages...")
        print(f"{'='*60}")
        import subprocess
        result = subprocess.run(
            [sys.executable, str(Path(__file__).resolve().parent / "sync_portal.py")],
            capture_output=False,
        )
        if result.returncode != 0:
            print("  [WARN] Portal sync had issues — run 'python scripts/sync_portal.py' manually.")


if __name__ == "__main__":
    main()
