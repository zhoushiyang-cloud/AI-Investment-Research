"""Company catalyst calendar — surface events that a macro economic calendar misses.

Two reliable free sources combined:
  1. Nasdaq earnings calendar (free, no key)  → upcoming earnings for tracked tickers
  2. SEC EDGAR 8-K filings (free)             → recent material events, decoded by item

Why this exists: investor days / analyst days / analyst-conference appearances are
NOT on economic calendars (investing.com, FXStreet). They surface as (a) press
releases / IR-page announcements (1–3 weeks ahead), and (b) 8-K "Item 7.01 Reg FD"
or "Item 8.01" filings when presentation materials drop. This script catches (b)
and the upcoming-earnings layer, which is the reliable, automatable 80%.

Usage:
    python scripts/catalyst_calendar.py                      # last 14d 8-K + next 30d earnings
    python scripts/catalyst_calendar.py --lookback 7 --forward 14
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# Windows console is often GBK; force UTF-8 so Chinese/emoji don't crash prints.
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from src.data_engine import get_sec_filings  # noqa: E402

NASDAQ_API = "https://api.nasdaq.com/api/calendar/earnings"
NASDAQ_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json",
}
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "outputs"

# ── 8-K item decoder ────────────────────────────────────────────────────────────
# SEC Form 8-K "Item X.XX" → what the event actually is. The catalyst-relevant ones
# are flagged with ⭐.
ITEM_DECODE: dict[str, tuple[str, int]] = {
    "1.01": ("重大协议（客户/供应/授信）", 3),   # ⭐⭐ big for AI/memory supply deals
    "1.02": ("终止重大协议", 1),
    "1.03": ("破产/接管", 3),
    "2.01": ("完成并购/资产处置", 3),
    "2.02": ("业绩发布（财报/指引）", 3),        # ⭐ the classic catalyst
    "2.03": ("新增重大负债", 2),
    "2.04": ("触发违约/加速到期", 2),
    "2.05": ("退出成本", 1),
    "2.06": ("资产减值", 2),
    "3.01": ("退市/转板通知", 3),
    "3.02": ("未注册证券销售", 1),
    "3.03": ("重大权利变更", 2),
    "4.01": ("审计师变更", 2),
    "4.02": ("重述/不可依赖财报", 3),
    "5.01": ("控制权变更", 3),
    "5.02": ("高管/董事变动", 2),
    "5.03": ("章程修订", 1),
    "5.07": ("股东投票（薪酬/治理）", 1),
    "7.01": ("Reg FD 披露（投资者日/演示材料）", 3),  # ⭐ investor day / presentation
    "8.01": ("其他重大事件（常含投资者日公告）", 3),  # ⭐ often investor-day announcement
    "9.01": ("财报/附件", 0),
}

# Highest-priority items → shown first in the report
CATALYST_ITEMS = {"2.02", "7.01", "8.01", "1.01", "2.01", "5.02"}


def get_tracked_tickers() -> list[str]:
    """Read tracked tickers from the companies/ directory (single source of truth)."""
    comp_dir = Path(__file__).resolve().parent.parent / "companies"
    tickers = sorted(p.stem for p in comp_dir.glob("*.md"))
    return tickers


# ── Nasdaq earnings (upcoming) ──────────────────────────────────────────────────

def fetch_earnings_day(date_str: str) -> list[dict]:
    try:
        r = requests.get(NASDAQ_API, params={"date": date_str}, headers=NASDAQ_HEADERS, timeout=15)
        if r.status_code != 200:
            return []
        return r.json().get("data", {}).get("rows") or []
    except Exception:
        return []


def fetch_upcoming_earnings(tracked: set[str], forward_days: int) -> list[dict]:
    """Scan the next `forward_days` days and keep only tracked tickers."""
    today = datetime.now()
    out: list[dict] = []
    for offset in range(forward_days + 1):
        date_str = (today + timedelta(days=offset)).strftime("%Y-%m-%d")
        for ev in fetch_earnings_day(date_str):
            sym = (ev.get("symbol") or "").upper().strip()
            if sym in tracked:
                out.append({
                    "ticker": sym,
                    "name": ev.get("name", "?"),
                    "date": date_str,
                    "time": ev.get("time", "?"),
                    "eps_forecast": ev.get("epsForecast", "N/A"),
                    "market_cap": ev.get("marketCap", "N/A"),
                })
    # dedupe (a ticker can appear once per quarter, but be safe)
    seen, dedup = set(), []
    for ev in out:
        k = (ev["ticker"], ev["date"])
        if k not in seen:
            seen.add(k)
            dedup.append(ev)
    return sorted(dedup, key=lambda x: (x["date"], x["ticker"]))


# ── SEC 8-K (recent material events) ───────────────────────────────────────────

def fetch_recent_8k(tracked: list[str], lookback_days: int) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=lookback_days)
    out: list[dict] = []
    for tk in tracked:
        try:
            df = get_sec_filings(tk, limit=12, provider="sec")
        except Exception:
            continue
        if df is None or df.empty or "report_type" not in df.columns:
            continue
        for _, row in df.iterrows():
            rtype = str(row.get("report_type", "")).upper()
            if "8-K" not in rtype:
                continue
            fd = row.get("filing_date")
            try:
                fdate = pd_to_date(fd)
            except Exception:
                fdate = None
            if fdate is None or fdate < cutoff:
                continue
            items = str(row.get("items", "")).strip()
            out.append({
                "ticker": tk,
                "date": fdate,
                "items": items,
                "url": row.get("filing_detail_url", ""),
                "desc": row.get("primary_doc_description", ""),
            })
    return sorted(out, key=lambda x: (x["date"], x["ticker"]), reverse=True)


def pd_to_date(v) -> datetime | None:
    import pandas as pd
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return None
    if isinstance(v, datetime):
        return v
    if isinstance(v, str):
        return datetime.fromisoformat(v[:10])
    return pd.Timestamp(v).to_pydatetime()


def decode_items(items: str) -> list[str]:
    if not items:
        return ["（未标注条目）"]
    decoded = []
    for part in items.split(","):
        code = part.strip()
        if code in ITEM_DECODE:
            label, _ = ITEM_DECODE[code]
            flag = "⭐" if code in CATALYST_ITEMS else ""
            decoded.append(f"{flag}{code} {label}")
        elif code:
            decoded.append(code)
    return decoded


# ── Rendering ───────────────────────────────────────────────────────────────────

def render_markdown(earnings: list[dict], eight_k: list[dict]) -> str:
    today = datetime.now().strftime("%Y-%m-%d")
    lines = [
        "# 公司催化剂日历",
        "",
        f"> 生成日期：{today} · 数据源：Nasdaq 财报 API + SEC EDGAR 8-K（均免费）",
        "> 说明：经济日历（investing.com 等）覆盖不到的公司特定事件——投资者日/分析师会议/业绩预告/重大协议，",
        "> 这里用「财报日历（未来）」+「8-K 重大事件（近期）」两层补上。8-K 的 `7.01`/`8.01` 条目尤其值得盯：",
        "> 投资者日/演示材料发布时常走这两条。",
        "",
        "---",
        "",
        "## 一、未来财报（跟踪标的）",
        "",
    ]
    if earnings:
        lines.append("| 日期 | 代码 | 名称 | 时间 | EPS 预期 |")
        lines.append("|---|---|---|---|---|")
        for e in earnings:
            lines.append(f"| {e['date']} | **{e['ticker']}** | {e['name']} | {e['time']} | {e['eps_forecast']} |")
    else:
        lines.append("_未来窗口内没有跟踪标的的财报。_")
    lines += ["", "---", "", "## 二、近期 8-K 重大事件（已解码）", ""]
    if eight_k:
        lines.append("| 日期 | 代码 | 事件条目 | 链接 |")
        lines.append("|---|---|---|---|")
        for e in eight_k:
            items_txt = "、".join(decode_items(e["items"]))
            link = f"[查看]({e['url']})" if e["url"] else "—"
            lines.append(f"| {e['date'].strftime('%Y-%m-%d')} | **{e['ticker']}** | {items_txt} | {link} |")
    else:
        lines.append("_近 N 天没有跟踪标的的 8-K 重大事件。_")
    lines += ["", "---", "", "*自动生成 · `scripts/catalyst_calendar.py`*", ""]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description="公司催化剂日历（财报 + 8-K 事件）")
    ap.add_argument("--lookback", type=int, default=14, help="8-K 回看天数（默认 14）")
    ap.add_argument("--forward", type=int, default=60, help="财报前瞻天数（默认 60）")
    ap.add_argument("--no-file", action="store_true", help="不写文件，只打印")
    args = ap.parse_args()

    tracked = get_tracked_tickers()
    print(f"跟踪标的：{len(tracked)} 个 → {', '.join(tracked)}")

    print(f"\n[1/2] 拉取未来 {args.forward} 天财报（Nasdaq，免费）…")
    earnings = fetch_upcoming_earnings(set(tracked), args.forward)
    print(f"  命中 {len(earnings)} 条跟踪标的财报")

    print(f"\n[2/2] 拉取近 {args.lookback} 天 8-K 事件（SEC EDGAR，免费）…")
    eight_k = fetch_recent_8k(tracked, args.lookback)
    print(f"  命中 {len(eight_k)} 条 8-K")

    md = render_markdown(earnings, eight_k)

    if not args.no_file:
        out_path = OUTPUT_DIR / f"公司催化剂日历_{datetime.now().strftime('%Y-%m-%d')}.md"
        out_path.write_text(md, encoding="utf-8")
        print(f"\n[OK] 已写入 {out_path}")

    print("\n" + "=" * 70)
    print(md)
    print("=" * 70)


if __name__ == "__main__":
    main()
