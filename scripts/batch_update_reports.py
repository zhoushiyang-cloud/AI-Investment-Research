"""
batch_update_reports.py — Daily rotation: update N companies per run, then sync portal.

Runs the full 3-step pipeline for a batch of tracked companies, rebuilds the portal,
and pushes to GitHub. Designed for daily scheduling to stay within free API rate limits.

Usage:
    python scripts/batch_update_reports.py              # update 5 oldest, then sync
    python scripts/batch_update_reports.py --count 3    # update 3 companies
    python scripts/batch_update_reports.py --ticker NVDA # update single company
    python scripts/batch_update_reports.py --list       # show update status
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATE_FILE = PROJECT_ROOT / "data" / "update_state.json"

# All tracked companies (synced with companies/ folder)
def get_tracked() -> list[str]:
    """Get all tracked tickers from companies/ folder."""
    companies_dir = PROJECT_ROOT / "companies"
    tickers = sorted([
        f.stem for f in companies_dir.glob("*.md")
    ])
    return tickers


def load_state() -> dict:
    """Load the update tracking state."""
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text(encoding="utf-8"))
    return {}


def save_state(state: dict) -> None:
    """Save the update tracking state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")


def run_step(ticker: str, step_name: str, cmd: list[str]) -> bool:
    """Run one pipeline step for a ticker. Return True on success."""
    print(f"    [{step_name}] {ticker}...", end=" ", flush=True)
    try:
        result = subprocess.run(
            cmd, cwd=str(PROJECT_ROOT),
            capture_output=True, text=True,
            encoding="utf-8", errors="replace",
            timeout=180,
        )
        if result.returncode == 0:
            # Extract OK/status line
            for line in result.stdout.split("\n"):
                if "OK" in line or "Saved" in line or "Done" in line:
                    print(line.strip()[:80])
                    break
            else:
                print("OK")
            return True
        else:
            err = result.stderr.strip()[-100:] if result.stderr else "Unknown error"
            print(f"FAILED: {err}")
            return False
    except subprocess.TimeoutExpired:
        print("TIMEOUT")
        return False
    except Exception as e:
        print(f"ERROR: {e}")
        return False


def update_company(ticker: str) -> bool:
    """Run the full 3-step pipeline for one company."""
    python = sys.executable
    scripts = PROJECT_ROOT / "scripts"

    steps = [
        ("Data", [python, str(scripts / "update_company.py"), "--ticker", ticker]),
        ("Valuation", [python, str(scripts / "valuation.py"), "--ticker", ticker, "--all-models"]),
        ("Report", [python, str(scripts / "generate_report.py"), "--ticker", ticker, "--provider", "deepseek"]),
        ("Translate", [python, str(scripts / "translate_reports.py"), "--ticker", ticker]),
    ]

    all_ok = True
    for step_name, cmd in steps:
        if not run_step(ticker, step_name, cmd):
            all_ok = False
            # Don't stop — run remaining steps anyway
    return all_ok


def list_status() -> None:
    """Print update status for all tracked companies."""
    tracked = get_tracked()
    state = load_state()

    print(f"\n{'Ticker':<8} {'Last Updated':<22} {'Days Ago':<10}")
    print("-" * 42)
    for t in tracked:
        info = state.get(t, {})
        last_updated = info.get("last_updated", "Never")
        if last_updated != "Never":
            dt = datetime.fromisoformat(last_updated)
            days_ago = (datetime.now() - dt).days
            days_str = f"{days_ago}d"
        else:
            days_str = "—"
        print(f"{t:<8} {last_updated:<22} {days_str:<10}")


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Batch update investment reports")
    parser.add_argument("--count", type=int, default=5, help="Number of companies to update (default: 5)")
    parser.add_argument("--ticker", type=str, help="Update a specific company only")
    parser.add_argument("--list", action="store_true", help="Show update status for all tracked")
    parser.add_argument("--no-sync", action="store_true", help="Skip portal sync after update")
    args = parser.parse_args()

    if args.list:
        list_status()
        return

    tracked = get_tracked()
    if not tracked:
        print("No tracked companies found in companies/")
        return

    # Determine which companies to update
    if args.ticker:
        tickers_to_update = [args.ticker.upper()]
    else:
        state = load_state()
        # Sort by last_updated (oldest first), then by ticker
        def sort_key(t: str) -> tuple[int, str]:
            info = state.get(t, {})
            last = info.get("last_updated", "2000-01-01")
            return (last, t)

        sorted_tickers = sorted(tracked, key=sort_key)
        tickers_to_update = sorted_tickers[:args.count]

    print(f"\n{'='*60}")
    print(f"  Batch Report Update — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  Updating: {', '.join(tickers_to_update)}")
    print(f"{'='*60}\n")

    state = load_state()
    success_count = 0

    for ticker in tickers_to_update:
        print(f"  [{ticker}] Starting pipeline...")
        ok = update_company(ticker)
        state[ticker] = {
            "last_updated": datetime.now().isoformat(),
            "success": ok,
        }
        save_state(state)
        if ok:
            success_count += 1
            print(f"  [{ticker}] ✅ Complete\n")
        else:
            print(f"  [{ticker}] ⚠️ Some steps failed\n")
        time.sleep(2)  # Brief pause between companies

    print(f"\n{'='*60}")
    print(f"  Summary: {success_count}/{len(tickers_to_update)} companies updated")
    print(f"{'='*60}")

    # Sync portal
    if not args.no_sync:
        print("\n  Rebuilding and syncing portal...")
        result = subprocess.run(
            [sys.executable, str(PROJECT_ROOT / "scripts" / "sync_portal.py")],
            cwd=str(PROJECT_ROOT),
        )
        if result.returncode == 0:
            print("  [OK] Portal synced!")
        else:
            print("  [WARN] Portal sync had issues — check logs.")


if __name__ == "__main__":
    main()
