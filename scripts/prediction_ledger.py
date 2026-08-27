"""
prediction_ledger.py — 预测台账 + 事后打分（研究质量的反馈闭环）

这是「评判标准」的核心：把每次研报的预测（评级 / 信心 / 目标价）记录成结构化台账，
之后用真实行情回填结果，算出方向命中率、收益率、以及是否跑赢标普(SPY)。

用法:
    python scripts/prediction_ledger.py --score        # 给已有预测打分
    python scripts/prediction_ledger.py --backfill     # 从 reports/*.md 回填历史预测
    python scripts/prediction_ledger.py --list         # 查看台账

自动记录: generate_report.py 每次生成研报后会自动调用 record_prediction()。
"""

import argparse
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

# Windows 控制台默认 GBK/cp1252，统一成 UTF-8 避免 emoji/中文报错
if sys.stdout.encoding and sys.stdout.encoding.lower().replace("-", "") not in ("utf8", "utf_8"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.data_engine import get_price_history

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEDGER_PATH = PROJECT_ROOT / "data" / "predictions.json"
REPORTS_DIR = PROJECT_ROOT / "reports"

# ── 归一化映射：把中文/英文自由文本映射成机器可读值 ───────────────────────────

RATING_MAP = {
    "buy": "BUY", "买入": "BUY", "增持": "BUY", "强烈买入": "BUY", "强烈增持": "BUY",
    "sell": "SELL", "卖出": "SELL", "减持": "SELL",
    "hold": "HOLD", "持有": "HOLD", "中性": "HOLD", "观望": "HOLD", "中性偏多": "HOLD",
}

CONVICTION_MAP = {
    "高": "high", "high": "high", "强烈": "high",
    "中高": "medium_high", "medium_high": "medium_high", "medium-high": "medium_high",
    "中": "medium", "medium": "medium",
    "低": "low", "low": "low",
}


def load_ledger() -> dict:
    """读取台账，不存在则返回空结构。"""
    if LEDGER_PATH.exists():
        try:
            return json.loads(LEDGER_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"predictions": []}


def save_ledger(ledger: dict) -> None:
    LEDGER_PATH.parent.mkdir(parents=True, exist_ok=True)
    LEDGER_PATH.write_text(
        json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def normalize_rating(raw: str) -> str | None:
    """把 '评级：BUY（逢低布局）' / '**Buy**' 之类归一成 BUY/SELL/HOLD。

    按 key 长度降序匹配，避免「买入」被「强烈买入」里的短 key 抢先命中。
    """
    if not raw:
        return None
    s = raw.lower()
    for key in sorted(RATING_MAP, key=len, reverse=True):
        if key in s:
            return RATING_MAP[key]
    return None


def normalize_conviction(raw: str) -> str | None:
    """归一信心值。长 key 优先，避免「中高」被「高」误命中。"""
    if not raw:
        return None
    s = raw.lower()
    for key in sorted(CONVICTION_MAP, key=len, reverse=True):
        if key in s:
            return CONVICTION_MAP[key]
    return None


def record_prediction(
    ticker: str,
    date: str,
    rating: str,
    conviction: str | None = None,
    start_price: float | None = None,
    price_target: float | None = None,
    horizon_months: int | None = 12,
    report_file: str | None = None,
    note: str | None = None,
) -> dict:
    """追加一条预测到台账（按 ticker+date 去重，重复调用只更新）。"""
    ledger = load_ledger()
    pid = f"{ticker}-{date}"

    entry = {
        "id": pid,
        "ticker": ticker,
        "date": date,
        "rating": rating,
        "conviction": conviction,
        "start_price": start_price,
        "price_target": price_target,
        "horizon_months": horizon_months,
        "report_file": report_file,
        "note": note,
    }

    # 去重：同 ticker + date 已存在则覆盖更新
    existing = [p for p in ledger["predictions"] if p.get("id") == pid]
    if existing:
        existing[0].update(entry)
    else:
        ledger["predictions"].append(entry)

    save_ledger(ledger)
    return entry


# ── 从研报提取预测（回填 / 兜底）──────────────────────────────────────────────

def extract_prediction_from_text(ticker: str, date: str, text: str) -> dict | None:
    """从研报文本里提取评级/信心/目标价。找不到评级则返回 None。"""
    rating = None
    m = re.search(r"评级\s*[：:]\s*[（(]?([A-Za-z]{3,4}|买入|卖出|持有|增持|减持)", text)
    if m:
        rating = normalize_rating(m.group(1))
    if rating is None:
        # 兜底：直接找 BUY/SELL/HOLD 关键词
        m = re.search(r"\b(BUY|SELL|HOLD)\b", text, re.IGNORECASE)
        if m:
            rating = m.group(1).upper()

    if rating is None:
        return None

    conviction = None
    m = re.search(r"[Cc]onviction\s*[：:]?\s*\*{0,2}(高|中高|中|低|High|Medium|Low)\*{0,2}", text)
    if m:
        conviction = normalize_conviction(m.group(1))

    # 目标价：研报里若有「目标价 $xxx」或「$xxx」出现在 recommendation 附近，尽力提取
    price_target = None
    m = re.search(r"目标价\s*[：:]?\s*\$?\s*([\d,]+(?:\.\d+)?)", text)
    if m:
        price_target = float(m.group(1).replace(",", ""))

    return {
        "rating": rating,
        "conviction": conviction,
        "price_target": price_target,
        "horizon_months": 12,
    }


def extract_structured_prediction(text: str) -> dict | None:
    """解析研报里机器可读的 PREDICTION 行（提示词要求 LLM 输出的固定格式）。

    格式: PREDICTION|rating=BUY|conviction=high|price_target=123.45|horizon_months=12
    解析失败返回 None（调用方应回退到 extract_prediction_from_text）。
    """
    m = re.search(r"PREDICTION\s*\|([^\n]+)", text)
    if not m:
        return None

    kv = {}
    for part in m.group(1).split("|"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            kv[k.strip()] = v.strip().strip("\"'")

    rating = normalize_rating(kv.get("rating", ""))
    if not rating:
        return None

    price_target = None
    if kv.get("price_target"):
        try:
            price_target = float(kv["price_target"])
        except (ValueError, TypeError):
            pass

    horizon = None
    if kv.get("horizon_months"):
        try:
            horizon = int(float(kv["horizon_months"]))
        except (ValueError, TypeError):
            pass

    return {
        "rating": rating,
        "conviction": normalize_conviction(kv.get("conviction", "")),
        "price_target": price_target,
        "horizon_months": horizon or 12,
    }


def strip_prediction_line(text: str) -> str:
    """从研报文本里剥离 PREDICTION 机器行，保持人读报告干净。"""
    return re.sub(r"\n?PREDICTION\s*\|[^\n]*", "", text)


def _report_frontmatter(path: Path) -> dict:
    """读取研报 YAML frontmatter 的 ticker / date。"""
    text = path.read_text(encoding="utf-8")
    ticker = None
    date = None
    m = re.search(r"^ticker\s*:\s*(\S+)", text, re.MULTILINE)
    if m:
        ticker = m.group(1).strip().upper()
    m = re.search(r"^date\s*:\s*(\d{4}-\d{2}-\d{2})", text, re.MULTILINE)
    if m:
        date = m.group(1)
    return {"ticker": ticker, "date": date}


def _price_on_or_after(ticker: str, date: str) -> float | None:
    """取预测日（含）之后第一个收盘价，用于回填 start_price。"""
    try:
        end = (datetime.strptime(date, "%Y-%m-%d") + timedelta(days=5)).strftime("%Y-%m-%d")
        df = get_price_history(ticker, start=date, end=end)
        if df is None or df.empty:
            return None
        close_col = "close" if "close" in df.columns else df.columns[-1]
        return float(df[close_col].iloc[0])
    except Exception:
        return None


def backfill() -> int:
    """扫描 reports/*.md，回填历史预测到台账。返回新增条数。"""
    ledger = load_ledger()
    existing_ids = {p.get("id") for p in ledger["predictions"]}
    added = 0

    for path in sorted(REPORTS_DIR.glob("*_report_*.md")):
        fm = _report_frontmatter(path)
        ticker, date = fm["ticker"], fm["date"]
        if not ticker or not date:
            continue
        pid = f"{ticker}-{date}"
        if pid in existing_ids:
            continue

        text = path.read_text(encoding="utf-8")
        pred = extract_prediction_from_text(ticker, date, text)
        if pred is None:
            continue

        start_price = _price_on_or_after(ticker, date)
        record_prediction(
            ticker=ticker,
            date=date,
            rating=pred["rating"],
            conviction=pred.get("conviction"),
            start_price=start_price,
            price_target=pred.get("price_target"),
            horizon_months=12,
            report_file=path.name,
        )
        existing_ids.add(pid)
        added += 1
        print(f"  ✅ {pid}  {pred['rating']:<4} {pred.get('conviction') or '-':<12} start=${start_price}")

    print(f"\n回填完成：新增 {added} 条，台账共 {len(existing_ids)} 条。")
    return added


# ── 打分 ──────────────────────────────────────────────────────────────────────

def _close_at(ticker: str, start: str) -> float | None:
    """取 start 之后最近的收盘价（用于当前价 / SPY 基准）。"""
    try:
        df = get_price_history(ticker, start=start)
        if df is None or df.empty:
            return None
        close_col = "close" if "close" in df.columns else df.columns[-1]
        return float(df[close_col].iloc[-1])
    except Exception:
        return None


def score() -> None:
    """给台账里的每条预测打分，输出 scorecard。"""
    ledger = load_ledger()
    preds = ledger["predictions"]
    if not preds:
        print("台账为空。先运行 --backfill 回填历史研报，或让 generate_report.py 自动记录。")
        return

    rows = []
    for p in preds:
        if not p.get("start_price"):
            continue
        end_price = _close_at(p["ticker"], p["date"])
        if end_price is None:
            continue
        spy_end = _close_at("SPY", p["date"])
        # SPY 基准：取同一窗口的涨跌。用 SPY 在预测日的收盘做起点近似
        spy_start = _price_on_or_after("SPY", p["date"])

        ret = (end_price - p["start_price"]) / p["start_price"] * 100
        spy_ret = (spy_end - spy_start) / spy_start * 100 if (spy_start and spy_end) else None
        excess = (ret - spy_ret) if spy_ret is not None else None
        days = (datetime.now() - datetime.strptime(p["date"], "%Y-%m-%d")).days

        rating = p.get("rating")
        if rating == "BUY":
            correct = ret > 0
        elif rating == "SELL":
            correct = ret < 0
        else:
            correct = None  # HOLD 不算方向

        rows.append({
            **p,
            "end_price": round(end_price, 2),
            "days": days,
            "return_pct": round(ret, 2),
            "excess_pct": round(excess, 2) if excess is not None else None,
            "correct": correct,
        })

    if not rows:
        print("没有可打分的预测（缺 start_price 或行情）。")
        return

    # 聚合
    directional = [r for r in rows if r["correct"] is not None]
    correct_cnt = sum(1 for r in directional if r["correct"])
    hit_rate = correct_cnt / len(directional) * 100 if directional else 0.0
    avg_ret = sum(r["return_pct"] for r in rows) / len(rows)
    with_excess = [r for r in rows if r["excess_pct"] is not None]
    avg_excess = sum(r["excess_pct"] for r in with_excess) / len(with_excess) if with_excess else 0.0
    beat_cnt = sum(1 for r in with_excess if r["excess_pct"] > 0)

    by_rating: dict[str, list] = {}
    for r in rows:
        by_rating.setdefault(r["rating"], []).append(r)

    print("\n" + "=" * 64)
    print("  预测台账评分（Prediction Scorecard）")
    print("=" * 64)
    print(f"  预测总数    : {len(rows)}")
    for rating, rs in sorted(by_rating.items()):
        avg = sum(x['return_pct'] for x in rs) / len(rs)
        print(f"    {rating:<5} {len(rs):>3} 条  平均收益 {avg:+.2f}%")
    print(f"  方向命中率  : {correct_cnt}/{len(directional)} = {hit_rate:.1f}%  (只统计 BUY/SELL)")
    print(f"  平均收益率  : {avg_ret:+.2f}%")
    print(f"  平均超额    : {avg_excess:+.2f}% (对 SPY)")
    print(f"  跑赢 SPY    : {beat_cnt}/{len(with_excess)} = {beat_cnt/len(with_excess)*100:.1f}%" if with_excess else "  跑赢 SPY    : N/A")

    print("\n  " + "-" * 60)
    print(f"  {'Ticker':<7} {'日期':<12} {'评级':<6} {'天数':>4} {'收益':>8} {'超额':>8}  方向")
    print("  " + "-" * 60)
    for r in sorted(rows, key=lambda x: x["date"]):
        correct_mark = "✓" if r["correct"] is True else ("✗" if r["correct"] is False else "—")
        print(
            f"  {r['ticker']:<7} {r['date']:<12} {r['rating']:<6} {r['days']:>4} "
            f"{r['return_pct']:>+7.2f}% {r['excess_pct'] if r['excess_pct'] is not None else 'N/A':>7}  {correct_mark}"
        )
    print("  " + "-" * 60)
    print("  ✓=方向正确  ✗=方向错误  —=HOLD不计方向\n")


def list_predictions() -> None:
    ledger = load_ledger()
    preds = ledger["predictions"]
    if not preds:
        print("台账为空。")
        return
    print(f"\n台账共 {len(preds)} 条预测：")
    for p in sorted(preds, key=lambda x: x["date"]):
        print(
            f"  {p['id']:<20} {p['rating']:<5} {p.get('conviction') or '-':<12} "
            f"start=${p.get('start_price')}  target=${p.get('price_target') or '—'}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="预测台账 + 事后打分")
    parser.add_argument("--score", action="store_true", help="给已有预测打分")
    parser.add_argument("--backfill", action="store_true", help="从 reports/*.md 回填历史预测")
    parser.add_argument("--list", action="store_true", help="查看台账")
    args = parser.parse_args()

    if args.backfill:
        backfill()
    if args.score:
        score()
    if args.list or not (args.backfill or args.score):
        list_predictions()


if __name__ == "__main__":
    main()
