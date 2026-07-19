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

from src.data_engine import fetch_all_for_ticker
from src.markdown import generate_report_md
from src.config import load_config


def build_analysis_prompt(ticker: str, data: dict) -> str:
    """Build a comprehensive analysis prompt from live data.

    Args:
        ticker: Stock ticker symbol.
        data: Full data dict from fetch_all_for_ticker().

    Returns:
        Prompt string ready for an LLM.
    """
    profile = data.get("profile")
    metrics = data.get("metrics")
    income = data.get("income")
    balance = data.get("balance")
    cashflow = data.get("cashflow")
    estimates = data.get("estimates")
    news = data.get("news")
    peers = data.get("peers", [])

    # Build a data-rich but concise context block
    prompt = f"""You are a senior equity research analyst. Write a professional investment memo for {ticker}.

## Available Data

### Company Profile
"""
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

    if income is not None and not income.empty:
        prompt += f"\n### Income Statement\n{income.head(3).to_string()}\n"

    if balance is not None and not balance.empty:
        prompt += f"\n### Balance Sheet\n{balance.head(3).to_string()}\n"

    if cashflow is not None and not cashflow.empty:
        prompt += f"\n### Cash Flow\n{cashflow.head(3).to_string()}\n"

    if estimates is not None and not estimates.empty:
        prompt += f"\n### Analyst Estimates\n{estimates.to_string()}\n"

    if news is not None and not news.empty:
        prompt += "\n### Recent News Headlines\n"
        for _, a in news.head(10).iterrows():
            title = a.get("title", "N/A")
            source = a.get("source", "")
            prompt += f"- {title} ({source})\n"

    if peers:
        prompt += f"\n### Peers\n{', '.join(str(p) for p in peers)}\n"

    prompt += """
## Instructions

Write a comprehensive investment memo with these sections:

### 1. Executive Summary (3-5 bullet points)
Key takeaways an investor needs in 30 seconds.

### 2. Business Overview
What the company does, competitive position, key segments.

### 3. Financial Analysis
Revenue trends, margins, cash flow, balance sheet health. Include specific numbers.

### 4. Valuation Assessment
Are the current multiples justified by growth? Compare to peers and history.

### 5. Risks (numbered, with severity: High/Medium/Low)
Concrete, specific risks — not generic boilerplate.

### 6. Catalysts (with timeline: Near-term / Medium-term)
What could drive upside in 6-18 months?

### 7. Recommendation
Buy / Hold / Sell with conviction level (High / Medium / Low) and 12-month thesis.

Format in clean markdown. Use Obsidian [[wikilinks]] where appropriate.
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

        # Fetch all data
        print(f"  [Data] Fetching financials, metrics, news...")
        data = fetch_all_for_ticker(ticker)

        # Build prompt
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


if __name__ == "__main__":
    main()
