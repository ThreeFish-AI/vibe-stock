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


def evaluate_signals(signals, bars_by_code):
    """就 bars（按代码）评估已到期 horizon；原位更新 signals，返回归因增量。"""
    ledger_delta = {}
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
            s.setdefault("evaluated", {})[str(h)] = {
                "close": closes[j], "date": dates[j],
                "outcome": outcome or "observed"}
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
    # --stock 先归一：识别失败 detect_market 以 SystemExit 如实报错退出（不碰状态文件）
    want = fx.detect_market(args.stock) if args.stock else None
    signals = _load(SIGNALS, [])
    if not signals:
        print("signals.json 为空：先跑 diagnose.py report 登记信号")
        return 0
    pending = [s for s in signals if s.get("status") == "pending"]
    if want:  # 只评该股；同码未知市场记录留给下方守卫如实报跳过，不静默吞
        pending = [s for s in pending if s.get("code") == want[1] and
                   (s.get("market") == want[0] or s.get("market") not in fx.CHAINS)]
        if not pending:
            print("无 %s:%s 的 pending 信号，无可评估项" % want)
            return 0
    evaluable = []
    for s in pending:  # 不可取数的坏记录（如快照兜底 market='?'）跳过并保持 pending，不阻塞其余后验
        why = []
        if s.get("market") not in fx.CHAINS:
            why.append("market=%r 不在取数链（%s）" % (s.get("market"), "/".join(sorted(fx.CHAINS))))
        if not s.get("code"):
            why.append("缺 code")
        if why:
            print("跳过 %s（code=%s）：%s；保持 pending，人工修正后重跑"
                  % (s.get("id"), s.get("code"), "、".join(why)))
        else:
            evaluable.append(s)
    symbols = sorted({(s["market"], s["code"]) for s in evaluable})
    bars_by_code = {}
    for market, code in symbols:
        st = fx.load_fetch_state()
        bars, _state, _src, _tried = fx.fetch_daily_bars(market, code, st,
                                                         int(dt.datetime.now().timestamp()))
        fx.save_fetch_state(st)
        if bars:
            bars_by_code[code] = bars
    delta = evaluate_signals(evaluable, bars_by_code)
    _save(SIGNALS, signals)
    if delta:
        ledger = merge_ledger(_load(LEDGER, {}), delta)
        _save(LEDGER, ledger)
        print("评估完成；台账与绩效已更新（%s）" % LEDGER)
        for src, d in delta.items():
            print("  归因 %s：+%d 胜 / +%d 负" % (src, d["wins"], d["losses"]))
    else:  # 全部跳过/未到期时不落「已更新」失实陈述，亦不空写台账文件
        ledger = _load(LEDGER, {})
        print("评估完成；本次无台账变动（无可评估项或未到期）")
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
    # run() 市场守卫 + --stock 过滤（零网络：fetch_state 与日 K 全走桩替；
    # 守卫回退时坏记录流入 symbols——market=None 在 sorted() 即 TypeError、
    # market='?' 在真实 fetch_daily_bars 的 CHAINS 查表 KeyError，任一必被本段捕获）
    import argparse
    import contextlib
    import io
    with tempfile.TemporaryDirectory() as td:
        global SIGNALS, LEDGER
        _old_paths = (SIGNALS, LEDGER, fx.STATE_DIR, fx.FETCH_STATE)
        _old_fns = (fx.load_fetch_state, fx.save_fetch_state, dict(fx.DAILY_FETCHERS))
        SIGNALS, LEDGER = os.path.join(td, "signals.json"), os.path.join(td, "ledger.json")
        fx.STATE_DIR, fx.FETCH_STATE = td, os.path.join(td, "fetch_state.json")
        fx.load_fetch_state = lambda: {"breakers": {}, "cooldowns": {}}
        fx.save_fetch_state = lambda st: None
        rbars = [{"date": "2026-10-%02d" % d, "open": 1, "high": 1, "low": 1,
                  "close": 100.0 + d, "volume": 1} for d in range(1, 31)]
        calls = []
        for k in list(fx.DAILY_FETCHERS):
            fx.DAILY_FETCHERS[k] = lambda m, c, _k=k: (calls.append((m, c)), rbars)[1]
        def _mk(i, market, code, action):
            return {"id": i, "market": market, "code": code, "action": action,
                    "horizons": [1], "date": "2026-10-01", "close_at_signal": 102.0,
                    "status": "pending", "evaluated": {}, "sources": ["strategy:demo"]}
        def _state():
            return [_mk("x1", "?", "000001", "buy"), _mk("n1", None, "000002", "buy"),
                    _mk("c1", "cn", "000001", "buy"), _mk("c2", "cn", "600519", "reduce"),
                    _mk("k1", "cn", None, "buy"), _mk("k2", None, None, "buy")]
        try:
            _save(SIGNALS, _state())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert run(argparse.Namespace(stock=None)) == 0
            txt = out.getvalue()
            assert "跳过 x1" in txt and "跳过 n1" in txt, txt
            assert "market='?'" in txt and "market=None" in txt
            assert "跳过 k1（code=None）：缺 code；" in txt, txt
            assert "跳过 k2（code=None）：market=None 不在取数链（cn/hk）、缺 code；" in txt, txt
            assert sorted(calls) == [("cn", "000001"), ("cn", "600519")], calls
            sigs = {s["id"]: s for s in _load(SIGNALS, [])}
            assert sigs["x1"]["status"] == "pending" and sigs["x1"]["evaluated"] == {}, \
                "坏市场记录须保持 pending 不动（即便与可评估记录同 code）"
            assert sigs["n1"]["status"] == "pending" and sigs["n1"]["evaluated"] == {}
            assert sigs["k1"]["status"] == "pending" and sigs["k2"]["status"] == "pending", \
                "缺 code 记录须保持 pending 不动"
            assert "1" in sigs["c1"]["evaluated"] and "1" in sigs["c2"]["evaluated"]
            assert sigs["c1"]["status"] == "observed" and sigs["c2"]["status"] == "observed"
            # --stock 过滤：归一（sh600519→cn:600519）后只评该股；未入过滤集的坏记录不报
            calls.clear()
            _save(SIGNALS, _state())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert run(argparse.Namespace(stock="sh600519")) == 0
            txt2 = out.getvalue()
            assert calls == [("cn", "600519")], calls
            sigs = {s["id"]: s for s in _load(SIGNALS, [])}
            assert "1" in sigs["c2"]["evaluated"] and sigs["c2"]["status"] == "observed", \
                "--stock 过滤只评目标股"
            assert sigs["c1"]["status"] == "pending" and sigs["c1"]["evaluated"] == {}, \
                "--stock 过滤下未指定股票的 pending 信号不得被评估"
            assert "跳过" not in txt2, "过滤集外的坏记录不报跳过"
            # --stock 命中 + 同码坏记录：坏记录走守卫报跳过、好记录照常评估
            calls.clear()
            _save(SIGNALS, _state())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert run(argparse.Namespace(stock="000001")) == 0
            sigs = {s["id"]: s for s in _load(SIGNALS, [])}
            assert "1" in sigs["c1"]["evaluated"] and sigs["c1"]["status"] == "observed"
            assert sigs["x1"]["status"] == "pending" and sigs["x1"]["evaluated"] == {}
            assert "跳过 x1" in out.getvalue()
            # 无匹配 / 识别失败：如实报、不取数
            calls.clear()
            _save(SIGNALS, _state())
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert run(argparse.Namespace(stock="hk01888")) == 0
            assert "无 hk:01888 的 pending" in out.getvalue() and calls == []
            try:
                run(argparse.Namespace(stock="abc"))
                raise AssertionError("--stock 不可识别应 SystemExit 报错退出")
            except SystemExit:
                pass
            assert calls == []
        finally:
            SIGNALS, LEDGER = _old_paths[:2]
            fx.STATE_DIR, fx.FETCH_STATE = _old_paths[2:]
            (fx.load_fetch_state, fx.save_fetch_state) = _old_fns[:2]
            fx.DAILY_FETCHERS.clear()
            fx.DAILY_FETCHERS.update(_old_fns[2])
    print("  ok run() 守卫：未知市场跳过不阻塞 · --stock 过滤/归一/无匹配/识别失败")
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
    print("  ok 买入/观察双路径 · 归因台账 · 升降档阈值 · 未到期不动 · 非交易日回退")
    print("SELFTEST PASSED ✔")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--stock", help="只评该股的 pending 信号（经 detect_market 归一）；不给则全量")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    sys.exit(run(args))


if __name__ == "__main__":
    main()
