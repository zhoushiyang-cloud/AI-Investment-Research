"""
sync_portal.py — Rebuild the GitHub Pages portal and push to GitHub.

Usage:
    python scripts/sync_portal.py                # build + commit + push
    python scripts/sync_portal.py --build-only   # only rebuild docs/, no push
    python scripts/sync_portal.py --push-only    # only commit + push existing docs/
"""

import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def run(cmd: str, cwd: Path | None = None) -> bool:
    """Run a shell command, print output, return True on success."""
    print(f"  $ {cmd}")
    result = subprocess.run(
        cmd, shell=True, cwd=str(cwd or PROJECT_ROOT),
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    if result.stdout:
        for line in result.stdout.strip().split("\n")[-5:]:
            print(f"    {line}")
    if result.returncode != 0:
        if result.stderr:
            err = result.stderr.strip()
            if err:
                print(f"  [ERR] {err[:200]}")
        return False
    return True


def build_site() -> bool:
    """Run build_site.py to regenerate docs/."""
    print("\n[1/3] Building portal site...")
    result = subprocess.run(
        [sys.executable, str(PROJECT_ROOT / "scripts" / "build_site.py")],
        cwd=str(PROJECT_ROOT), capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )
    if result.returncode == 0:
        for line in result.stdout.strip().split("\n")[-6:]:
            print(f"    {line}")
        return True
    print(f"  [ERR] Build failed: {result.stderr[:300]}")
    return False


def commit_and_push() -> bool:
    """Stage docs/, commit, and push with retries."""
    print("\n[2/3] Committing changes...")
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    if not run(f'git add docs/ scripts/'):
        # Try just docs/
        run("git add docs/")

    # Check if anything to commit
    result = subprocess.run(
        "git diff --cached --quiet", shell=True, cwd=str(PROJECT_ROOT),
    )
    if result.returncode == 0:
        print("    Nothing to commit — site is up to date.")
        return True

    run(f'git commit -m "Auto-sync: portal update {timestamp}"')

    print("\n[3/3] Pushing to GitHub...")
    for attempt in range(1, 6):
        print(f"    Attempt {attempt}/5...")
        if run("git push origin main"):
            print("  [OK] Push successful!")
            return True
        if attempt < 5:
            wait = attempt * 10
            print(f"    Retrying in {wait}s...")
            time.sleep(wait)

    print("  [WARN] Push failed after 5 attempts. Run 'git push' manually later.")
    return False


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="Sync portal to GitHub Pages")
    parser.add_argument("--build-only", action="store_true", help="Only rebuild docs/")
    parser.add_argument("--push-only", action="store_true", help="Only commit + push")
    args = parser.parse_args()

    if args.push_only:
        commit_and_push()
        return

    if not build_site():
        sys.exit(1)

    if args.build_only:
        print("\n[Done] Site rebuilt locally. Run with no flags to push.")
        return

    commit_and_push()
    print("\n[Done] Portal sync complete.")


if __name__ == "__main__":
    main()
