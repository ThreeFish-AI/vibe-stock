#!/usr/bin/env python3
"""postmortem.py · 决策信号后验自校准（蓝本：DSA decision_signal_outcome_service）。

机制（与 references/05-postmortem.md 同源）：
  - 对每条 pending 信号，回看 1/3/5/10 个交易日后的实际收盘价：
    买入族 ≥ +2% 记 hit、≤ −2% 记 miss、中间记 neutral；卖出族对称。
    watch/hold/avoid/alert 只观察不记分。
  - 每个判定结果按信号记录时的 sources 归因，累计进 ledger.json（wins/losses）。
  - 绩效因子与画像升降档由 adjudicate.performance_factor / profile 消费：
    命中率 ≥60% 且样本 ≥10 → promote；≤40% 且样本 ≥10 → demote；否则 observe。

用法：
  uv run --no-project --with 'akshare==1.20.*' --with yfinance --with efinance \
    scripts/postmortem.py --stock 600519
  uv run --no-project scripts/postmortem.py --selftest
"""
import argparse
import bisect
import datetime as dt
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as fx  # noqa: E402

STATE_DIR = os.path.expanduser("~/.vibe-stock")
SIGNALS = os.path.join(STATE_DIR, "signals.json")
LEDGER = os.path.join(STATE_DIR, "ledger.json")

NEUTRAL_BAND = 0.02
PROMOTE_RATE, DEMOTE_RATE, MIN_SAMPLES = 0.60, 0.40, 10
SCORABLE = {"buy": "bull", "reduce": "bear", "sell": "bear"}


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, obj):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=1)


def score(action, base, later):
    """返回 hit/miss/neutral 或 None（不可判定）。"""
    chg = later / base - 1 if base else None
    if chg is None:
        return None
    fam = SCORABLE.get(action)
    if fam == "bull":
        return ("hit" if chg >= NEUTRAL_BAND else
                "miss" if chg <= -NEUTRAL_BAND else "neutral")
    if fam == "bear":
        return ("hit" if chg <= -NEUTRAL_BAND else
                "miss" if chg >= NEUTRAL_BAND else "neutral")
    return None  # watch/hold 等只观察


def _fx_on(series, keys, date):
    """汇率序列按日取值：回退到 ≤ date 的最近一根（与信号日非交易日回退同
    思路）；date 早于首根（序列窗口不足）返回 None，消费侧如实缺省不附字段。"""
    i = bisect.bisect_right(keys, date) - 1
    return series[keys[i]] if i >= 0 else None


def evaluate_signals(signals, bars_by_code, cny_by_date=None):
    """就 bars（按代码）评估已到期 horizon；原位更新 signals，返回归因增量。
    cny_by_date（--cny 时传入 fx.hkd_cny_daily 产物）：hk 信号的 evaluated 附
    cny_close / cny_chg_pct 展示字段（人民币口径收益，含汇兑项）——仅展示，
    outcome 判定与台账归因仍按标的币种收盘（默认口径不变）。"""
    ledger_delta = {}
    fx_keys = sorted(cny_by_date) if cny_by_date else []
    for s in signals:
        if s.get("status") != "pending":
            continue
        bars = bars_by_code.get(s["code"])
        if not bars:
            continue
        dates = [b["date"] for b in bars]
        closes = [b["close"] for b in bars]
        try:
            i = dates.index(s["date"])
        except ValueError:
            # 非交易日登记的信号（周末/节假日 qt 静态快照使 quote.date 落在非
            # 交易日）：回退到 ≤ 信号日的最近一根日 K——非交易日 qt 静态价＝
            # 最后交易日收盘，价与该 bar 同刻，绩效基准不失真；信号日新于最新
            # bar（当日盘中登记、日 K 未出）属未到期，跳过不评估（同 j 越界分支）。
            j = bisect.bisect_right(dates, s["date"]) - 1
            if j < 0 or s["date"] > dates[-1]:
                continue
            i = j
        for h in s["horizons"]:
            if str(h) in s.get("evaluated", {}):
                continue
            j = i + h
            if j >= len(closes):
                continue  # 未到期
            outcome = score(s["action"], s["close_at_signal"], closes[j])
            entry = {"close": closes[j], "date": dates[j],
                     "outcome": outcome or "observed"}
            if fx_keys and s.get("market") == "hk":
                fx0 = _fx_on(cny_by_date, fx_keys, s["date"])
                fx1 = _fx_on(cny_by_date, fx_keys, dates[j])
                if fx0 and fx1:
                    base_cny = s["close_at_signal"] * fx0
                    if base_cny:
                        entry["cny_close"] = round(closes[j] * fx1, 4)
                        entry["cny_chg_pct"] = round(
                            (closes[j] * fx1 / base_cny - 1) * 100, 2)
            s.setdefault("evaluated", {})[str(h)] = entry
            if outcome in ("hit", "miss"):
                for src in s.get("sources", []):
                    d = ledger_delta.setdefault(src, {"wins": 0, "losses": 0})
                    d["wins" if outcome == "hit" else "losses"] += 1
        if all(str(h) in s["evaluated"] for h in s["horizons"]):
            decisive = [v["outcome"] for v in s["evaluated"].values()
                        if v["outcome"] in ("hit", "miss")]
            s["status"] = "evaluated" if decisive else "observed"
    return ledger_delta


def merge_ledger(ledger, delta):
    for src, d in delta.items():
        rec = ledger.setdefault(src, {"wins": 0, "losses": 0})
        rec["wins"] += d["wins"]
        rec["losses"] += d["losses"]
    return ledger


def profile_report(ledger):
    """画像升降档（≤40% 降、≥60% 升、样本 <10 只观察）。"""
    rows = []
    for src, rec in sorted(ledger.items()):
        w, l = rec["wins"], rec["losses"]
        n = w + l
        if n < MIN_SAMPLES:
            verdict = "observe（样本 %d < %d，不动手）" % (n, MIN_SAMPLES)
        else:
            rate = w / n
            verdict = ("promote（命中率 %.0f%% ≥ 60%%）" % (rate * 100) if rate >= PROMOTE_RATE
                       else "demote（命中率 %.0f%% ≤ 40%%）" % (rate * 100)
                       if rate <= DEMOTE_RATE else "hold（命中率 %.0f%%）" % (rate * 100))
        rows.append("%-34s %d 胜 / %d 负 → %s" % (src, w, l, verdict))
    return rows


def run(args):
    signals = _load(SIGNALS, [])
    if not signals:
        print("signals.json 为空：先跑 diagnose.py report 登记信号")
        return 0
    symbols = sorted({(s["market"], s["code"]) for s in signals
                      if s.get("status") == "pending"})
    bars_by_code = {}
    for market, code in symbols:
        st = fx.load_fetch_state()
        bars, _state, _src, _tried = fx.fetch_daily_bars(market, code, st,
                                                         int(dt.datetime.now().timestamp()))
        fx.save_fetch_state(st)
        if bars:
            bars_by_code[code] = bars
    cny_by_date = None
    if getattr(args, "cny", False):
        if any(m == "hk" for m, _ in symbols):
            # 汇率仅展示口径：取数失败不阻断评估，outcome 照常按港币判定
            st_fx = fx.load_fetch_state()
            cny_by_date, err = fx.hkd_cny_daily(
                st_fx, int(dt.datetime.now().timestamp()))
            fx.save_fetch_state(st_fx)
            if not cny_by_date:
                print("人民币口径不可用（%s）：outcome 仍按港币评估" % err)
        else:
            print("--cny：待评估信号无港股标的，人民币口径不适用")
    delta = evaluate_signals(signals, bars_by_code, cny_by_date)
    _save(SIGNALS, signals)
    ledger = merge_ledger(_load(LEDGER, {}), delta)
    _save(LEDGER, ledger)
    print("评估完成；台账与绩效已更新（%s）" % LEDGER)
    for src, d in delta.items():
        print("  归因 %s：+%d 胜 / +%d 负" % (src, d["wins"], d["losses"]))
    rows = profile_report(ledger)
    if rows:
        print("画像升降档：")
        for r in rows:
            print("  " + r)
    return 0


def selftest():
    print("== postmortem selftest ==")
    bars = []
    price = 100.0
    for d in range(1, 31):
        price *= 1.02 if d % 2 else 0.995  # 缓慢上行
        bars.append({"date": "2026-10-%02d" % d, "open": price, "high": price,
                     "low": price, "close": round(price, 3), "volume": 100})
    sig_buy = {"id": "b1", "market": "cn", "code": "000001", "profile": "default",
               "action": "buy", "family": "bull", "horizons": [1, 3, 5, 10],
               "date": "2026-10-01", "close_at_signal": 100.0, "status": "pending",
               "evaluated": {}, "sources": ["strategy:bull_trend"]}
    sig_watch = {**sig_buy, "id": "w1", "action": "watch", "family": "neutral",
                 "sources": ["role:技术"], "horizons": [1, 3, 5, 10],
                 "evaluated": {}}
    delta = evaluate_signals([sig_buy, sig_watch], {"000001": bars})
    assert sig_buy["evaluated"]["1"]["outcome"] in ("hit", "miss", "neutral")
    assert sig_watch["evaluated"]["1"]["outcome"] == "observed", "watch 只观察"
    assert sig_buy["status"] in ("evaluated", "observed"), "全部 horizon 到期应收口"
    assert delta["strategy:bull_trend"]["wins"] + \
        delta["strategy:bull_trend"]["losses"] <= 4
    ledger = merge_ledger({}, delta)
    assert profile_report(ledger)[0].startswith("strategy:bull_trend")
    # 阈值路径
    assert profile_report({"s": {"wins": 10, "losses": 0}})[0].endswith(
        "promote（命中率 100% ≥ 60%）")
    assert profile_report({"s": {"wins": 0, "losses": 10}})[0].endswith(
        "demote（命中率 0% ≤ 40%）")
    assert "observe" in profile_report({"s": {"wins": 5, "losses": 0}})[0]
    # 未到期不动
    s2 = {**sig_buy, "id": "b2", "date": "2026-10-30", "status": "pending",
          "horizons": [1, 3, 5, 10], "evaluated": {}}
    evaluate_signals([s2], {"000001": bars})
    assert s2["evaluated"] == {} and s2["status"] == "pending"
    # 非交易日登记信号（周末 qt 静态快照使 date 落在非交易日）：回退 ≤ 信号日
    # 最近 bar 评估，不静默永久失配；信号日新于最新 bar 仍属未到期跳过
    bars_g = [{"date": "2026-10-%02d" % d, "open": 1.0, "high": 1.0, "low": 1.0,
               "close": 10.0 + d, "volume": 1} for d in (2, 9, 16, 23, 30)]
    s3 = {**sig_buy, "id": "b3", "date": "2026-10-10", "close_at_signal": 19.0,
          "status": "pending", "horizons": [1], "evaluated": {}}
    evaluate_signals([s3], {"000001": bars_g})
    assert s3["evaluated"]["1"]["date"] == "2026-10-16", \
        "非交易日信号须回退最近 bar（10-09）后按 horizon 推进"
    s4 = {**sig_buy, "id": "b4", "date": "2026-11-01", "status": "pending",
          "horizons": [1], "evaluated": {}}
    evaluate_signals([s4], {"000001": bars_g})
    assert s4["evaluated"] == {} and s4["status"] == "pending", \
        "信号日新于最新 bar 属未到期，不得提前评估"
    # 人民币口径展示（--cny）：hk 信号附 cny_close/cny_chg_pct（含汇兑项），
    # outcome 判定与归因不变——默认口径（不传 cny_by_date）不附 cny 字段
    cny_map = {"2026-10-%02d" % d: 0.90 - 0.001 * d for d in range(1, 31)}
    sig_hk = {**sig_buy, "id": "h1", "market": "hk", "code": "01810",
              "close_at_signal": 100.0, "status": "pending", "evaluated": {}}
    sig_hk_base = {**sig_hk, "id": "h2", "evaluated": {}}
    evaluate_signals([sig_hk], {"01810": bars}, cny_map)
    evaluate_signals([sig_hk_base], {"01810": bars})
    for h in ("1", "3", "5", "10"):
        assert sig_hk["evaluated"][h]["outcome"] == \
            sig_hk_base["evaluated"][h]["outcome"], "人民币口径不得改变 outcome"
        assert "cny_close" in sig_hk["evaluated"][h] and \
            "cny_chg_pct" in sig_hk["evaluated"][h], h
    assert "cny_close" not in sig_hk_base["evaluated"]["1"], \
        "默认口径不得附 cny 展示字段"
    # 数学钉：h=1 → 10-02 收盘 101.49×汇率 0.898 / 基准 100×0.899 − 1
    ev1 = sig_hk["evaluated"]["1"]
    assert abs(ev1["cny_close"] - 101.49 * 0.898) < 0.01, ev1
    assert abs(ev1["cny_chg_pct"]
               - (101.49 * 0.898 / (100 * 0.899) - 1) * 100) < 0.01, ev1
    # 汇率序列窗口不足（信号日早于汇率首根）：如实缺省不附字段、不误报
    s5 = {**sig_buy, "id": "h3", "market": "hk", "code": "01810",
          "close_at_signal": 100.0, "status": "pending", "date": "2026-10-05",
          "horizons": [1], "evaluated": {}}
    evaluate_signals([s5], {"01810": bars}, {"2026-10-15": 0.89})
    assert s5["evaluated"]["1"]["outcome"] in ("hit", "miss", "neutral"), \
        "汇率缺根不得影响 outcome 本身"
    assert "cny_close" not in s5["evaluated"]["1"], "汇率缺根须如实缺省"
    print("  ok 买入/观察双路径 · 归因台账 · 升降档阈值 · 未到期不动 · 非交易日回退")
    print("  ok 人民币口径展示：hk 附 cny 字段 · outcome/归因仍港币 · 缺根如实缺省")
    print("SELFTEST PASSED ✔")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--stock", help="提示性参数：实际按 signals.json 待评估项取数")
    ap.add_argument("--cny", action="store_true",
                    help="港股信号附人民币口径展示（cny_close/cny_chg_pct，含汇兑项）；"
                         "outcome 判定与台账归因仍按港币（默认口径不变）")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    sys.exit(run(args))


if __name__ == "__main__":
    main()
