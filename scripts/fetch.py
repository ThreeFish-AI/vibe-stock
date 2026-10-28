#!/usr/bin/env python3
"""fetch.py · vibe-stock 证据取数层（蓝本：DSA data_provider 多源回退链）。

机制（与 references/01-evidence.md 同源）：
  - 市场分流：A 股链 akshare → efinance → yfinance；港股链 akshare → yfinance。
  - 回退链逐源尝试；任一成功即继续，状态标 available/fallback。
  - 熔断：单源连续 3 次失败停 300s（半开放行单次探测）；连接失败冷却 15s。
    状态持久化在 ~/.vibe-stock/fetch_state.json（真实时钟，秒）。
  - 八态标注：每个数据块独立标 available/missing/not_supported/fallback/stale/
    estimated/partial/fetch_failed——缺什么写什么，绝不静默消失。
  - 技术指标（MA/RSI/MACD/量比等）由日 K 纯标准库推导，不依赖三方库。
  - 快照模式：--snapshot-dir 提供预置 JSON（无网兜底），状态按文件声明或 estimated。

用法（联网全量）：
  uv run --no-project --with akshare --with efinance --with yfinance \
      scripts/fetch.py --stock 600519 --out evidence.json
  uv run --no-project --with akshare --with yfinance \
      scripts/fetch.py --stock hk00700 --out evidence.json
快照模式（零依赖）：
  uv run --no-project scripts/fetch.py --stock 600519 \
      --snapshot-dir evals/fixture/snapshot --out evidence.json
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

STATE_DIR = os.path.expanduser("~/.vibe-stock")
FETCH_STATE = os.path.join(STATE_DIR, "fetch_state.json")

BREAKER_FAILS, BREAKER_COOLDOWN = 3, 300
CONN_COOLDOWN = 15
BARS_WINDOW = 250
STALE_DAYS = {"quote": 1, "daily_bars": 5, "news": 3, "fundamentals": 120, "chip": 5}

CHAINS = {
    "cn": ["akshare", "efinance", "yfinance"],
    "hk": ["akshare", "yfinance"],
}


# ---------------------------------------------------------------- 市场与代码

def detect_market(symbol):
    s = symbol.strip().lower()
    if re.fullmatch(r"(sh|sz)?\d{6}", s):
        return "cn", re.sub(r"^(sh|sz)", "", s)
    m = re.fullmatch(r"(?:hk)?(\d{4,5})(?:\.hk)?", s)
    if m:
        return "hk", m.group(1)
    raise SystemExit("无法识别市场，示例：600519 / sz000001 / hk00700 / 0700.HK")


def yf_ticker(market, code):
    if market == "hk":
        return str(int(code)).zfill(4) + ".HK"  # Yahoo 港码 4 位：00700→0700.HK
    return code + (".SS" if code.startswith(("6", "9", "5")) else ".SZ")


# ---------------------------------------------------------------- 熔断与冷却（持久化）

def load_fetch_state():
    try:
        with open(FETCH_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"breakers": {}, "cooldowns": {}}


def save_fetch_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(FETCH_STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def source_allowed(st, name, now):
    br = st["breakers"].get(name, {})
    if br.get("open_until", 0) > now:
        return False, "skipped_open"
    if st["cooldowns"].get(name, 0) > now:
        return False, "skipped_cooldown"
    return True, ""


def record(st, name, ok, err, now):
    br = st["breakers"].setdefault(name, {"fails": 0, "open_until": 0})
    if ok:
        br["fails"], br["open_until"] = 0, 0
        st["cooldowns"].pop(name, None)
        return
    if "connection" in err or "timeout" in err.lower():
        st["cooldowns"][name] = now + CONN_COOLDOWN
    br["fails"] += 1
    if br["fails"] >= BREAKER_FAILS:
        br["open_until"] = now + BREAKER_COOLDOWN


# ---------------------------------------------------------------- 各源取数（懒加载）

def _daily_via_akshare(market, code):
    import akshare as ak  # noqa: 延迟导入，缺库不致命
    df = (ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
          if market == "cn" else
          ak.stock_hk_hist(symbol=code.zfill(5), period="daily", adjust="qfq"))
    return [{"date": str(r["日期"]), "open": float(r["开盘"]), "high": float(r["最高"]),
             "low": float(r["最低"]), "close": float(r["收盘"]),
             "volume": float(r["成交量"])} for _, r in df.tail(BARS_WINDOW).iterrows()]


def _daily_via_efinance(market, code):
    import efinance as ef
    df = ef.stock.get_quote_history(code)
    key = {"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
           "收盘": "close", "成交量": "volume"}
    rows = []
    for _, r in df.tail(BARS_WINDOW).iterrows():
        row = {}
        for cn, en in key.items():
            if cn in r:
                row[en] = str(r[cn]) if en == "date" else float(r[cn])
        rows.append(row)
    return rows


def _daily_via_yfinance(market, code):
    import yfinance
    tk = yfinance.Ticker(yf_ticker(market, code))
    df = tk.history(period="1y")
    return [{"date": str(i.date()), "open": float(r.Open), "high": float(r.High),
             "low": float(r.Low), "close": float(r.Close),
             "volume": float(r.Volume)} for i, r in df.tail(BARS_WINDOW).iterrows()]


DAILY_FETCHERS = {"akshare": _daily_via_akshare,
                  "efinance": _daily_via_efinance,
                  "yfinance": _daily_via_yfinance}


def fetch_daily_bars(market, code, st, now):
    """回退链取日 K。返回 (rows, state, source, tried)。全链失败 → fetch_failed。"""
    tried, first_fail = [], None
    for name in CHAINS[market]:
        ok, why = source_allowed(st, name, now)
        if not ok:
            tried.append((name, why))
            continue
        try:
            rows = DAILY_FETCHERS[name](market, code)
            if not rows:
                raise ValueError("empty bars")
            record(st, name, True, "", now)
            state = "available" if first_fail is None else "fallback"
            return rows, state, name, tried
        except ImportError as e:
            tried.append((name, "import_missing"))
            first_fail = first_fail or name  # 缺库不记熔断（环境问题非源问题）
        except Exception as e:
            record(st, name, False, str(e), now)
            tried.append((name, "fail: %s" % type(e).__name__))
            first_fail = first_fail or name
    return [], "fetch_failed", "", tried


# 派生块（从日 K 推导，零三方依赖）
def derive_quote(bars):
    last = bars[-1]
    prev = bars[-2]["close"] if len(bars) > 1 else last["close"]
    return {"price": last["close"], "prev_close": prev,
            "change_pct": round((last["close"] / prev - 1) * 100, 2),
            "date": last["date"]}


def _ma(closes, n):
    return round(sum(closes[-n:]) / n, 3) if len(closes) >= n else None


def _rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[-(n + 1):-1], closes[-n:]):
        d = b - a
        gains, losses = gains + max(d, 0), losses + max(-d, 0)
    if gains + losses == 0:
        return 50.0
    return round(100 * gains / (gains + losses), 2)


def _macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return None
    ema = lambda k: _ema_series(closes, k)
    dif = [f - s for f, s in zip(_ema_series(closes, fast), _ema_series(closes, slow))]
    dea = _ema_series(dif, signal)[-1]
    return {"dif": round(dif[-1], 3), "dea": round(dea, 3),
            "macd": round((dif[-1] - dea) * 2, 3)}


def _ema_series(vals, n):
    out, k = [], 2 / (n + 1)
    e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def derive_technical(bars):
    closes = [b["close"] for b in bars]
    vols = [b["volume"] for b in bars]
    hi52 = max(b["high"] for b in bars)
    lo52 = min(b["low"] for b in bars)
    return {
        "ma5": _ma(closes, 5), "ma10": _ma(closes, 10), "ma20": _ma(closes, 20),
        "ma60": _ma(closes, 60), "rsi14": _rsi(closes), "macd": _macd(closes),
        "vol_ratio_5": round(vols[-1] / (sum(vols[-6:-1]) / 5 + 1e-9), 2),
        "pct_from_52w_high": round((closes[-1] / hi52 - 1) * 100, 2),
        "pct_from_52w_low": round((closes[-1] / lo52 - 1) * 100, 2),
        "bars_count": len(bars),
    }


def fetch_news(market, code, st, now):
    """新闻块：A 股 akshare；港股 not_supported（v1 诚实标注）。"""
    if market == "hk":
        return {"state": "not_supported", "source": "",
                "note": "港股新闻源 v1 未接入"}
    ok, why = source_allowed(st, "akshare", now)
    if not ok:
        return {"state": "fetch_failed", "source": "akshare", "note": why}
    try:
        import akshare as ak
        df = ak.stock_news_em(symbol=code)
        items = [{"title": str(r["新闻标题"]), "content": str(r["新闻内容"])[:200],
                  "time": str(r["发布时间"])} for _, r in df.head(10).iterrows()]
        return {"state": "available", "source": "akshare", "items": items}
    except ImportError:
        return {"state": "fetch_failed", "source": "akshare", "note": "import_missing"}
    except Exception as e:
        record(st, "akshare", False, str(e), now)
        return {"state": "fetch_failed", "source": "akshare",
                "note": type(e).__name__}


def fetch_fundamentals(market, code, st, now):
    if market == "hk":
        return {"state": "not_supported", "source": "",
                "note": "港股财务指标 v1 未接入"}
    ok, why = source_allowed(st, "akshare", now)
    if not ok:
        return {"state": "fetch_failed", "source": "akshare", "note": why}
    try:
        import akshare as ak
        df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2024")
        row = df.iloc[-1] if len(df) else {}
        keys = ["净资产收益率(%)", "每股收益(元)", "主营业务收入增长率(%)",
                "资产负债率(%)"]
        return {"state": "available", "source": "akshare",
                "data": {k: (None if k not in row else _num(row[k])) for k in keys}}
    except ImportError:
        return {"state": "fetch_failed", "source": "akshare", "note": "import_missing"}
    except Exception as e:
        record(st, "akshare", False, str(e), now)
        return {"state": "fetch_failed", "source": "akshare",
                "note": type(e).__name__}


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("--", "nan"))
    except Exception:
        return None


def fetch_chip(market, code, st, now):
    """筹码分布：A 股专属，港股 not_supported（能力差异摆到明面上）。"""
    if market == "hk":
        return {"state": "not_supported", "source": "",
                "note": "筹码数据仅 A 股"}
    ok, why = source_allowed(st, "akshare", now)
    if not ok:
        return {"state": "fetch_failed", "source": "akshare", "note": why}
    try:
        import akshare as ak
        df = ak.stock_cyq_em(symbol=code, adjust="qfq")
        row = df.iloc[-1] if len(df) else {}
        keys = ["获利比例", "平均成本", "90成本-低", "90成本-高"]
        return {"state": "available", "source": "akshare",
                "data": {k: (None if k not in row else _num(row[k])) for k in keys}}
    except ImportError:
        return {"state": "fetch_failed", "source": "akshare", "note": "import_missing"}
    except Exception as e:
        record(st, "akshare", False, str(e), now)
        return {"state": "fetch_failed", "source": "akshare",
                "note": type(e).__name__}


# ---------------------------------------------------------------- 质量分（与 adjudicate.evidence_cap 同源）

BLOCK_WEIGHTS = [("quote", 25), ("daily_bars", 25), ("technical", 25),
                 ("news", 10), ("fundamentals", 10), ("chip", 5)]
STATE_SCORE = {"available": 100, "fallback": 85, "partial": 70, "stale": 60,
               "estimated": 55, "missing": 30, "not_supported": 30, "fetch_failed": 25}
CORE_BLOCKS = {"quote", "daily_bars", "technical"}


def quality(blocks):
    score = sum(STATE_SCORE.get(blocks.get(n, {}).get("state", "missing"), 0) * w
                for n, w in BLOCK_WEIGHTS) // 100
    tier = ("good" if score >= 85 else "usable" if score >= 70
            else "limited" if score >= 55 else "poor")
    core_degraded = any(blocks.get(n, {}).get("state", "missing")
                        not in ("available", "fallback") for n in CORE_BLOCKS)
    return {"score": score, "tier": tier,
            "confidence_cap": "low" if core_degraded else "high"}


# ---------------------------------------------------------------- 快照模式

def snapshot_blocks(snapshot_dir):
    blocks = {}
    for name, _w in BLOCK_WEIGHTS:
        path = os.path.join(snapshot_dir, name + ".json")
        if not os.path.exists(path):
            blocks[name] = {"state": "missing", "source": "snapshot",
                            "note": "快照目录未提供"}
            continue
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            state = payload.pop("state", "estimated")
            blocks[name] = {"state": state, "source": "snapshot", **payload}
        except Exception as e:
            blocks[name] = {"state": "partial", "source": "snapshot",
                            "note": "快照解析失败: %s" % type(e).__name__}
    return blocks


# ---------------------------------------------------------------- 主流程

def fetch(symbol, snapshot_dir=None):
    now = int(time.time())
    if snapshot_dir:
        blocks = snapshot_blocks(snapshot_dir)
        meta = {"symbol": symbol, "snapshot": True}
    else:
        market, code = detect_market(symbol)
        st = load_fetch_state()
        bars, bars_state, bars_src, tried = fetch_daily_bars(market, code, st, now)
        save_fetch_state(st)
        blocks = {"daily_bars": {"state": bars_state, "source": bars_src,
                                 "tried": tried,
                                 "bars": bars[-BARS_WINDOW:]}}
        if bars:
            q = derive_quote(bars)
            blocks["quote"] = {"state": ("available" if bars_state == "available"
                                         else bars_state),
                               "source": "derived:" + bars_src, **q}
            blocks["technical"] = {"state": ("available" if bars_state == "available"
                                             else bars_state),
                                   "source": "derived", **derive_technical(bars)}
        else:
            blocks["quote"] = {"state": "missing", "source": "",
                               "note": "日 K 缺失，报价无从而来"}
            blocks["technical"] = {"state": "missing", "source": "",
                                   "note": "日 K 缺失，指标无从而来"}
        blocks["news"] = fetch_news(market, code, st, now)
        blocks["fundamentals"] = fetch_fundamentals(market, code, st, now)
        blocks["chip"] = fetch_chip(market, code, st, now)
        save_fetch_state(st)
        market_meta = {"symbol": symbol, "market": market, "code": code,
                       "tried": tried}
        meta = market_meta
    if blocks.get("daily_bars", {}).get("bars"):
        bars = blocks["daily_bars"]["bars"]
        bars_state = blocks["daily_bars"].get("state", "estimated")
        for name in ("technical",):
            if blocks.get(name, {}).get("state") in (None, "missing"):
                blocks[name] = {"state": bars_state, "source": "derived",
                                **derive_technical(bars)}
            else:
                blocks[name] = {**blocks.get(name, {}),
                                **derive_technical(bars)}
        if blocks.get("quote", {}).get("state") in (None, "missing"):
            blocks["quote"] = {"state": bars_state, "source": "derived:" +
                               blocks["daily_bars"].get("source", ""),
                               **derive_quote(bars)}
    evidence = {"meta": meta, "fetched_at": dt.datetime.now().isoformat(
        timespec="seconds"), "blocks": blocks, "quality": quality(blocks)}
    return evidence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True)
    ap.add_argument("--snapshot-dir")
    ap.add_argument("--out", default="evidence.json")
    args = ap.parse_args()
    evidence = fetch(args.stock, args.snapshot_dir)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=1)
    q = evidence["quality"]
    print("evidence -> %s · quality %s(%s) cap=%s" %
          (args.out, q["score"], q["tier"], q["confidence_cap"]))
    for n, _w in BLOCK_WEIGHTS:
        b = evidence["blocks"].get(n, {})
        print("  %-13s %-13s %s" % (n, b.get("state", "missing"), b.get("source", "")))
    if evidence["blocks"]["daily_bars"]["state"] == "fetch_failed":
        sys.exit(2)


if __name__ == "__main__":
    main()
