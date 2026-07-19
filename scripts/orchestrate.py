"""
orchestrate.py — Master pipeline runner for the AI Investment System.

Runs the full data → analysis → export pipeline in order:
  1. update_company.py  — fetch fundamentals, regenerate company .md files
  2. update_news.py     — fetch latest news, save JSON + append to .md
  3. valuation.py       — run DCF + comps + Graham models
  4. export_obsidian.py — export everything to Obsidian vault
  5. generate_report.py — (optional) LLM investment reports

Usage:
    python scripts/orchestrate.py [--tickers NVDA,AVGO] [--all]
    python scripts/orchestrate.py --all --with-reports
    python scripts/orchestrate.py --ticker NVDA --skip-valuation
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = PROJECT_ROOT / "scripts"


def run_step(name: str, args: list[str]) -> tuple[bool, float]:
    """Run a pipeline step and report its status.

    Args:
        name: Human-readable step name.
        args: Command arguments (passed to subprocess).

    Returns:
        (success, elapsed_seconds).
    """
    print(f"\n{'━'*60}")
    print(f"  ⚡ {name}")
    print(f"{'━'*60}")

    start = time.time()
    cmd = [sys.executable] + args
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    elapsed = time.time() - start

    if result.returncode == 0:
        print(f"  ✅ {name} — completed in {elapsed:.1f}s")
        return True, elapsed
    else:
        print(f"  ❌ {name} — FAILED (exit code {result.returncode}) in {elapsed:.1f}s")
        return False, elapsed


def main() -> None:
    parser = argparse.ArgumentParser(description="Master pipeline orchestrator")
    parser.add_argument("--ticker", type=str, help="Single ticker to process")
    parser.add_argument("--tickers", type=str, help="Comma-separated list of tickers")
    parser.add_argument("--all", action="store_true", help="Process all tracked companies")
    parser.add_argument("--skip-news", action="store_true", help="Skip news update step")
    parser.add_argument("--skip-valuation", action="store_true", help="Skip valuation step")
    parser.add_argument("--skip-export", action="store_true", help="Skip Obsidian export step")
    parser.add_argument("--with-reports", action="store_true", help="Generate LLM reports")
    parser.add_argument("--days", type=int, default=7, help="Days of news (default: 7)")
    parser.add_argument("--wacc", type=float, default=0.10, help="Discount rate for DCF")
    parser.add_argument("--sensitivity", action="store_true", help="Run DCF sensitivity analysis")
    args = parser.parse_args()

    # Resolve tickers
    tickers: list[str] = []
    if args.all:
        tickers = ["NVDA", "AVGO", "ORCL"]
    elif args.tickers:
        tickers = [t.strip().upper() for t in args.tickers.split(",")]
    elif args.ticker:
        tickers = [args.ticker.upper()]
    else:
        print("Usage: python orchestrate.py [--ticker NVDA] [--tickers NVDA,AVGO] [--all]")
        sys.exit(1)

    print(f"\n{'='*60}")
    print(f"  🚀 AI Investment System — Pipeline Start")
    print(f"  Tickers: {', '.join(tickers)}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    pipeline_start = time.time()
    results: dict[str, dict] = {}

    # ── Step 1: Update Company Data ──
    for ticker in tickers:
        ok, elapsed = run_step(
            f"Update Company: {ticker}",
            [str(SCRIPTS_DIR / "update_company.py"), "--ticker", ticker, "--days", str(args.days)],
        )
        results.setdefault(ticker, {})["company"] = ok

    # ── Step 2: Update News ──
    if not args.skip_news:
        for ticker in tickers:
            ok, elapsed = run_step(
                f"Update News: {ticker}",
                [str(SCRIPTS_DIR / "update_news.py"), "--ticker", ticker, "--days", str(args.days)],
            )
            results.setdefault(ticker, {})["news"] = ok
    else:
        print("\n  ⏭️  Skipping news update (--skip-news)")

    # ── Step 3: Valuation ──
    if not args.skip_valuation:
        for ticker in tickers:
            val_args = [
                str(SCRIPTS_DIR / "valuation.py"),
                "--ticker", ticker,
                "--all-models",
                "--wacc", str(args.wacc),
            ]
            if args.sensitivity:
                val_args.append("--sensitivity")
            ok, elapsed = run_step(f"Valuation: {ticker}", val_args)
            results.setdefault(ticker, {})["valuation"] = ok
    else:
        print("\n  ⏭️  Skipping valuation (--skip-valuation)")

    # ── Step 4: Export to Obsidian ──
    if not args.skip_export:
        ok, elapsed = run_step(
            "Export Obsidian",
            [str(SCRIPTS_DIR / "export_obsidian.py")],
        )
        results["_export"] = {"ok": ok}
    else:
        print("\n  ⏭️  Skipping export (--skip-export)")

    # ── Step 5: LLM Reports (optional) ──
    if args.with_reports:
        for ticker in tickers:
            ok, elapsed = run_step(
                f"Generate Report: {ticker}",
                [str(SCRIPTS_DIR / "generate_report.py"), "--ticker", ticker],
            )
            results.setdefault(ticker, {})["report"] = ok

    # ── Summary ──
    total_elapsed = time.time() - pipeline_start
    print(f"\n{'='*60}")
    print(f"  📊 Pipeline Summary")
    print(f"{'='*60}")

    success_count = 0
    fail_count = 0
    for ticker in tickers:
        t = results.get(ticker, {})
        statuses = []
        if "company" in t:
            statuses.append("📄" if t["company"] else "❌")
        if "news" in t:
            statuses.append("📰" if t["news"] else "❌")
        if "valuation" in t:
            statuses.append("💰" if t["valuation"] else "❌")
        if "report" in t:
            statuses.append("📝" if t["report"] else "❌")

        failed = sum(1 for s in statuses if s == "❌")
        if failed == 0:
            success_count += 1
            print(f"  ✅ {ticker}: {' '.join(statuses)} — All steps passed")
        else:
            fail_count += 1
            print(f"  ⚠️  {ticker}: {' '.join(statuses)} — {failed} step(s) failed")

    if results.get("_export", {}).get("ok"):
        print(f"  ✅ Obsidian Export: complete")
    else:
        print(f"  ⚠️  Obsidian Export: skipped or failed")

    print(f"\n  Total: {success_count} successful, {fail_count} with errors")
    print(f"  Duration: {total_elapsed:.0f}s ({total_elapsed/60:.1f} min)")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
