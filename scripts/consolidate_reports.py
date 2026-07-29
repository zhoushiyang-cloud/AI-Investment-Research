"""
Consolidate report files: one EN file per ticker, merge Update Logs, delete _cn and older files.
"""
import os
import re
from pathlib import Path
from collections import defaultdict

REPORTS_DIR = Path(__file__).parent.parent / "reports"

def parse_update_logs(content: str) -> list[tuple[str, str]]:
    """Extract Update Log entries: [(date, full_block), ...]"""
    logs = []
    # Match from "## 📝 Update Log" or "### YYYY-MM-DD" blocks
    pattern = r'### (\d{4}-\d{2}-\d{2})\s*\n(.*?)(?=### \d{4}-\d{2}-\d{2}|\n> \[!note\]|## 📋 Financial|---\s*\n\*Report generated|\Z)'
    matches = re.findall(pattern, content, re.DOTALL)
    for date, block in matches:
        logs.append((date, block.strip()))
    return logs

def get_update_log_section(content: str) -> str:
    """Extract the entire Update Log section including header."""
    m = re.search(r'(## 📝 Update Log.*?)(?=\n---\s*\n\*Report generated|\Z)', content, re.DOTALL)
    return m.group(1) if m else ""

def has_update_log_header(content: str) -> bool:
    return "## 📝 Update Log" in content

def insert_update_log(content: str, new_entries: list[tuple[str, str]]) -> str:
    """Insert Update Log section before the final 'Report generated' line."""
    log_section = "## 📝 Update Log\n\n"
    for date, block in new_entries:
        log_section += f"### {date}\n\n{block}\n\n"

    # Find insertion point: before the final "---" + "Report generated" footer
    footer_pattern = r'\n---\s*\n\*Report generated'
    m = re.search(footer_pattern, content)
    if m:
        insertion_point = m.start()
        return content[:insertion_point] + "\n---\n\n" + log_section + "\n---\n" + content[insertion_point:].lstrip('-').lstrip()
    else:
        # No footer found, append at end
        return content.rstrip() + "\n\n---\n\n" + log_section

def main():
    # Group files by ticker
    files_by_ticker = defaultdict(list)
    for f in REPORTS_DIR.glob("*.md"):
        # Parse ticker and date from filename: {TICKER}_report_{DATE}.md or {TICKER}_report_{DATE}_cn.md
        name = f.stem
        is_cn = name.endswith("_cn")
        base = name.replace("_cn", "")
        parts = base.split("_report_")
        if len(parts) != 2:
            continue
        ticker = parts[0]
        date = parts[1]
        files_by_ticker[ticker].append((date, f, is_cn))

    deleted = []
    kept = []

    for ticker, files in files_by_ticker.items():
        # Sort by date descending
        en_files = [(d, f) for d, f, cn in files if not cn]
        cn_files = [(d, f) for d, f, cn in files if cn]

        if not en_files:
            continue

        en_files.sort(key=lambda x: x[0], reverse=True)
        latest_date, latest_path = en_files[0]
        older_en = en_files[1:]

        # Collect Update Log entries from older EN files
        all_log_entries = []
        # Read latest file first to see what it already has
        latest_content = latest_path.read_text(encoding="utf-8")
        existing_dates = {d for d, _ in parse_update_logs(latest_content)}

        for old_date, old_path in older_en:
            old_content = old_path.read_text(encoding="utf-8")
            old_logs = parse_update_logs(old_content)
            for d, block in old_logs:
                if d not in existing_dates:
                    all_log_entries.append((d, block))
                    existing_dates.add(d)
            # Also check if old file itself has its own old logs
            old_own_logs = parse_update_logs(old_content)

        # If latest doesn't have Update Log header but has content and we have entries to add
        if all_log_entries and not has_update_log_header(latest_content):
            # Check if this is a fresh report that needs the old update log merged
            all_log_entries.sort(key=lambda x: x[0])
            new_content = insert_update_log(latest_content, all_log_entries)
            latest_path.write_text(new_content, encoding="utf-8")
            print(f"  [MERGE] {ticker}: merged {len(all_log_entries)} update log entries from older files")
        elif has_update_log_header(latest_content):
            # Already has update log section, check if we need to add missing entries
            existing = {d for d, _ in parse_update_logs(latest_content)}
            missing = [(d, b) for d, b in all_log_entries if d not in existing]
            if missing:
                # Append missing entries
                missing.sort(key=lambda x: x[0])
                new_entries_text = "\n".join(
                    f"### {d}\n\n{b}" for d, b in missing
                )
                # Insert after existing update log entries
                insert_pos = latest_content.rfind("---\n\n*Report generated")
                if insert_pos == -1:
                    insert_pos = len(latest_content)
                # Find end of last update log entry
                before_footer = latest_content[:insert_pos]
                new_content = before_footer.rstrip() + "\n\n" + new_entries_text + "\n\n" + latest_content[insert_pos:]
                latest_path.write_text(new_content, encoding="utf-8")
                print(f"  [MERGE] {ticker}: added {len(missing)} missing update log entries")

        kept.append(latest_path)

        # Mark all _cn files and older EN files for deletion
        for _, path in cn_files:
            deleted.append(path)
        for _, path in older_en:
            deleted.append(path)

    # Delete files
    for path in deleted:
        path.unlink()
        print(f"  [DEL] {path.name}")

    print(f"\n{'='*50}")
    print(f"  Kept {len(kept)} EN reports, deleted {len(deleted)} files")
    print(f"{'='*50}")

    # List kept files
    print("\nRemaining reports:")
    for p in sorted(kept):
        print(f"  {p.name}")

if __name__ == "__main__":
    main()
