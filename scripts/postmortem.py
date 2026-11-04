#!/usr/bin/env python3
"""postmortem.py · 决策信号后验自校准（蓝本：DSA decision_signal_outcome_service）。

机制（与 references/05-postmortem.md 同源）：
  - 对每条 pending 信号，按其 profile 的 horizons 回看实际收盘价：
    default=T+1/3/5/10、±2% 固定带；position=T+20/60/120、σ√h 判定带且
    仅 T+60 记分（T+20/120 照落实判供展示、不进台账）。
    买入族越过带上/下沿记 hit/miss、带内记 neutral；卖出族对称。
    watch/hold/avoid/alert 只观察不记分。
  - 到期判定排除当日盘中未完成日 K（I-016）：horizon 落末根且末根=当日盘中
    （fetch.session_phase 判据）时不评估、保持 pending，收盘后下一次运行补评。
  - 每个判定结果按信号记录时的 sources 归因，累计进各自台账（default=
    ledger.json、position=ledger.position.json，wins/losses）。
  - 绩效因子与画像升降档由 adjudicate.performance_factor / profile 消费：
    命中率 ≥60% 且样本 ≥10 → promote；≤40% 且样本 ≥10 → demote；否则 observe。
  - 评估后重建 reports/ 时间线索引（archive.rebuild_indexes），T+n 结果进 index.md。

用法：
  uv run --no-project --with 'akshare==1.20.*' --with yfinance --with efinance \
    scripts/postmortem.py --stock 600519
  uv run --no-project scripts/postmortem.py --selftest
"""
import argparse
import bisect
import datetime as dt
import json
import math
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive as ar  # noqa: E402
import fetch as fx  # noqa: E402

STATE_DIR = os.path.expanduser("~/.vibe-stock")
SIGNALS = os.path.join(STATE_DIR, "signals.json")
LEDGER = os.path.join(STATE_DIR, "ledger.json")
LEDGER_POSITION = os.path.join(STATE_DIR, "ledger.position.json")

NEUTRAL_BAND = 0.02
PROMOTE_RATE, DEMOTE_RATE, MIN_SAMPLES = 0.60, 0.40, 10
SCORABLE = {"buy": "bull", "reduce": "bear", "sell": "bear",
            "add_on": "bull"}  # add_on=加仓轨建议（09）：按 bull 记分进 ledger
# position 轨唯一记分期限：T+60 与 T+20/T+120 收益强相关（约 0.58/0.71），
# 多期限记分是伪重复样本——会使信号提前离开 <30 样本中性门、破坏 Beta(15,15)
# 收缩；20/120 照落 evaluated 实判（hit/miss/neutral）供展示、不进台账
# （规约见 references/05 期限轨）
LEDGER_HORIZON_POSITION = 60


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _save(path, obj):
    # I-005：原子写（tmp+replace），崩溃不留半截 JSON 被 _load 静默当空
    ar.write_json_atomic(path, obj)


def score(action, base, later, band=NEUTRAL_BAND):
    """返回 hit/miss/neutral 或 None（不可判定）。band=判定带半径（fraction）：
    default 轨恒 ±2%（NEUTRAL_BAND 逐字不变，07 P3 import 兼容）；position 轨
    按 horizon 波动率缩放（见 evaluate_signals——±2% 在 T+120 neutral 占比仅
    ~7%，判定退化为大盘 beta 方向，丧失区分度）。"""
    chg = later / base - 1 if base else None
    if chg is None:
        return None
    fam = SCORABLE.get(action)
    if fam == "bull":
        return ("hit" if chg >= band else
                "miss" if chg <= -band else "neutral")
    if fam == "bear":
        return ("hit" if chg <= -band else
                "miss" if chg >= band else "neutral")
    return None  # watch/hold 等只观察


def _fx_on(series, keys, date):
    """汇率序列按日取值：回退到 ≤ date 的最近一根（与信号日非交易日回退同
    思路）；date 早于首根（序列窗口不足）返回 None，消费侧如实缺省不附字段。"""
    i = bisect.bisect_right(keys, date) - 1
    return series[keys[i]] if i >= 0 else None


def evaluate_signals(signals, bars_by_code, cny_by_date=None, now=None):
    """就 bars（按代码）评估已到期 horizon；原位更新 signals，返回
    (ledger_delta_map, changed, notes)：delta_map 按 profile 分桶
    （{"default": {...}, "position": {...}, "addon": {...}}——default 与 addon
    同写 ledger.json（09 同账本、delta 分桶不串样本），position 独立
    ledger.position.json）；changed=是否有
    任何 evaluated 落笔（neutral-only 也算——索引重建据此触发，不再只看台账
    增量）；notes=诊断行（超窗信号等，run 侧打印）。
    判定口径（两轨同守）：基准价用同复权 closes[i]（与 closes[j] 同序列），
    不用 close_at_signal（qt 实时未复权价——窗口内除息/送转会系统性低估收益、
    高股息 buy 偏 miss）；close_at_signal 仅作登记价展示。
    position 轨判定带 band=σ_d×√h（σ_d=信号日前 60 日已实现日波动，无前视；
    样本不足退化 2%×√(h/10) 并在 entry 注记），且仅 h=60 记分（20/120 只观察）。
    cny_by_date（--cny 时传入 fx.hkd_cny_daily 产物）：hk 信号的 evaluated 附
    cny_close / cny_chg_pct 展示字段（人民币口径收益，含汇兑项）——仅展示，
    outcome 判定与台账归因仍按标的币种收盘（默认口径不变）。
    到期收盘门（I-016）：horizon 落在序列末根且末根=当日盘中未完成 K 线
    （fetch.session_phase 的 last_bar_partial 判据；now 可注入、None 即真实
    时钟）→ 视为未到期（跳过、保持 pending），待收盘后下一次运行补评。"""
    delta_map = {"default": {}, "position": {}, "addon": {}}
    changed, notes = False, []
    fx_keys = sorted(cny_by_date) if cny_by_date else []
    for s in signals:
        if s.get("status") != "pending":
            continue
        profile = s.get("profile", "default")
        bars = bars_by_code.get(s["code"])
        if not bars:
            continue
        dates = [b["date"] for b in bars]
        closes = [b["close"] for b in bars]
        if s["date"] < dates[0]:
            # 超窗：信号日早于取数窗口首日（BARS_WINDOW=250），此后每次后验
            # 都评不到——不再静默永久 pending，出诊断行（跳过不是修复，人工
            # 决定留档或清理；保持 pending 不动）
            notes.append("跳过 %s（%s · %s 轨）：信号日早于日 K 窗口首日 %s，"
                         "超窗无法后验，保持 pending" % (
                             s.get("id"), s.get("code"), profile, dates[0]))
            continue
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
        base_close = closes[i]  # 同复权基准（判定与展示百分比的 SSOT）
        # I-016 到期收盘门：末根=当日盘中未完成 K 线（session_phase 的
        # last_bar_partial 判据）时，落在末根的到期 horizon 不评估——盘中价
        # 非收盘事实，误评即伪命中且已落盘不回改；周末/节假日自然收盘态放行
        last_partial = fx.session_phase(
            s.get("market"), dates[-1], now).get("last_bar_partial")
        # position 轨 σ_d：只用信号日「之前」的收盘（无前视）
        band, band_note = NEUTRAL_BAND, ""
        if profile == "position":
            hist = closes[max(0, i - 60):i]
            sigma_d = (fx.realized_vol(hist, 60) or 0.0) / math.sqrt(252)
        for h in s["horizons"]:
            if str(h) in s.get("evaluated", {}):
                continue
            j = i + h
            if j >= len(closes):
                continue  # 未到期
            if j == len(closes) - 1 and last_partial:
                continue  # I-016：到期日 K 线未收盘 → 视为未到期保持 pending，收盘后补评
            if profile == "position":
                if sigma_d > 0:
                    band = sigma_d * math.sqrt(h)
                else:  # σ 样本不足：退化带并注记（不虚构精度）
                    band = NEUTRAL_BAND * math.sqrt(h / 10)
                    band_note = "band=退化 2%×√(h/10)"
            outcome = score(s["action"], base_close, closes[j], band)
            entry = {"close": closes[j], "date": dates[j],
                     "base": base_close, "outcome": outcome or "observed"}
            if band_note:
                entry["note"] = band_note
            if fx_keys and s.get("market") == "hk":
                fx0 = _fx_on(cny_by_date, fx_keys, s["date"])
                fx1 = _fx_on(cny_by_date, fx_keys, dates[j])
                if fx0 and fx1 and base_close:
                    base_cny = base_close * fx0
                    if base_cny:
                        entry["cny_close"] = round(closes[j] * fx1, 4)
                        entry["cny_chg_pct"] = round(
                            (closes[j] * fx1 / base_cny - 1) * 100, 2)
            s.setdefault("evaluated", {})[str(h)] = entry
            changed = True
            # 记分门：position 只记 T+60（伪重复治理）；其余期限照落 evaluated
            scoreable = (profile != "position"
                         or h == LEDGER_HORIZON_POSITION)
            if outcome in ("hit", "miss") and scoreable:
                for src in s.get("sources", []):
                    d = delta_map[profile].setdefault(
                        src, {"wins": 0, "losses": 0})
                    d["wins" if outcome == "hit" else "losses"] += 1
        if all(str(h) in s["evaluated"] for h in s["horizons"]):
            decisive = [v["outcome"] for v in s["evaluated"].values()
                        if v["outcome"] in ("hit", "miss")]
            s["status"] = "evaluated" if decisive else "observed"
    return delta_map, changed, notes


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
    # I-005：signals.json 严格加载——损坏即中止退出（状态文件是用户本地
    # 事实，绝不静默当空后整体覆盖）；台账仍宽松加载——损坏当空后，本次
    # 增量会整体覆盖写回（历史战绩清零风险，I-005② 在册待修，非无害）
    try:
        signals = ar.load_signals(SIGNALS)
    except ValueError as e:
        print("signals.json 无法解析（%s），后验中止——不覆盖状态文件" % e)
        return 2
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
    delta_map, changed, notes = evaluate_signals(evaluable, bars_by_code,
                                                 cny_by_date)
    for n in notes:  # 超窗等诊断行：不再静默永久 pending
        print("warn: %s" % n)
    _save(SIGNALS, signals)
    ledger = _load(LEDGER, {})
    wrote = []
    for profile, path in (("default", LEDGER), ("addon", LEDGER),
                          ("position", LEDGER_POSITION)):
        delta = delta_map.get(profile) or {}
        if not delta:
            continue
        led = merge_ledger(_load(path, {}), delta)
        _save(path, led)
        wrote.append((path, led, delta))
        if path == LEDGER:  # default 与 addon 同账本（09）：末次合并态作画像输入
            ledger = led
    if wrote:
        printed = set()  # default 与 addon 同账本（09）：同路径头行只打一次
        for path, led, delta in wrote:
            if path not in printed:
                print("评估完成；台账与绩效已更新（%s）" % path)
                printed.add(path)
            for src, d in delta.items():
                print("  归因 %s：+%d 胜 / +%d 负" % (src, d["wins"], d["losses"]))
    else:  # 全部跳过/未到期时不落「已更新」失实陈述，亦不空写台账文件
        print("评估完成；本次无台账变动（无可评估项或未到期）")
    # 中线台账画像（文件存在才打印——与 default 分开升降档，样本不串）
    for path, tag in ((LEDGER, "default"), (LEDGER_POSITION, "position")):
        led = ledger if tag == "default" else _load(path, {})
        rows = profile_report(led)
        if rows and tag == "position":
            print("中线画像升降档（ledger.position.json）：")
            for r in rows:
                print("  " + r)
    rows = profile_report(ledger)
    if rows:
        print("画像升降档：")
        for r in rows:
            print("  " + r)
    if changed or wrote:  # neutral-only 评估也重建索引（evaluated 有落笔即变）
        pf_warn = []
        try:  # 派生视图放最后：挂了不吞台账（事实源已落盘）；坏索引的
            # UnicodeDecodeError ⊂ ValueError 一并只告警
            ar.rebuild_indexes(os.path.join(STATE_DIR, "reports"), signals,
                               ar.load_names(STATE_DIR),
                               ar.load_portfolio(STATE_DIR, pf_warn))
        except (OSError, ValueError) as e:
            print("warn: 时间线索引重建失败（下次 report/postmortem 会重建）：%s" % e)
        for w in pf_warn:  # 持仓契约漂移可观测（与 diagnose report 同口径）
            print("warn: %s" % w)
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
    # addon 轨（09）：action=add_on 按 bull 记分（建议也要被市场打分），
    # 归因进 delta_map["addon"]（台账合并归 ledger.json，与 default 同账本）
    sig_addon = {**sig_buy, "id": "a1", "profile": "addon", "action": "add_on",
                 "key_levels": {"add_ref": 100.0, "confirm_lo": 97.0},
                 "evaluated": {}}
    delta_map, changed, notes = evaluate_signals([sig_buy, sig_watch, sig_addon],
                                                 {"000001": bars})
    delta = delta_map["default"]
    assert sig_addon["evaluated"]["1"]["outcome"] in ("hit", "miss", "neutral"), \
        "add_on 须按 bull 记分（SCORABLE），不得落 observed"
    assert delta_map["addon"]["strategy:bull_trend"]["wins"] + \
        delta_map["addon"]["strategy:bull_trend"]["losses"] >= 1, \
        "addon 建议的胜负须进 addon 归因（同源 sources）"
    assert sig_buy["evaluated"]["1"]["outcome"] in ("hit", "miss", "neutral")
    assert sig_watch["evaluated"]["1"]["outcome"] == "observed", "watch 只观察"
    assert sig_buy["status"] in ("evaluated", "observed"), "全部 horizon 到期应收口"
    assert changed and not notes
    # 复权基准修复：判定与展示基准=closes[i]（同复权序列），非 close_at_signal
    # （fixture 登记价 100.0 而 2026-10-01 收盘 102.0——除息/盘中价错位形态）
    assert sig_buy["evaluated"]["1"]["base"] == bars[0]["close"] == 102.0
    assert sig_buy["evaluated"]["1"]["base"] != sig_buy["close_at_signal"]
    # 时间线索引吃到后验结果：T+1 格带涨跌幅与判定（基准取 evaluated.base）
    row = [ln for ln in ar.render_stock_index([sig_buy], "cn", "000001").splitlines()
           if ln.startswith("| 2026-10-01")][0]
    assert "%+.1f%% %s" % ((sig_buy["evaluated"]["1"]["close"]
                            / sig_buy["evaluated"]["1"]["base"] - 1) * 100,
                           sig_buy["evaluated"]["1"]["outcome"]) in row, row
    assert delta["strategy:bull_trend"]["wins"] + \
        delta["strategy:bull_trend"]["losses"] <= 4
    ledger = merge_ledger({}, delta)
    assert profile_report(ledger)[0].startswith("strategy:bull_trend")
    # position 轨：σ√h 判定带 + 仅 T+60 记分（20/120 只观察）+ 台账分桶
    sig_pos = {**sig_buy, "id": "p1", "profile": "position",
               "horizons": [20, 60, 120], "date": "2026-10-01",
               "status": "pending", "evaluated": {}, "close_at_signal": 100.0}
    pm, pchg, pnotes = evaluate_signals([dict(sig_pos)],
                                        {"000001": bars})
    assert set(pm) == {"default", "position", "addon"} and not pm["default"], pm
    # 30 根合成日 K：T+20 落 evaluated、T+60/120 未到期（不虚构）
    assert "20" in sig_pos["evaluated"] and "60" not in sig_pos["evaluated"]
    assert sig_pos["evaluated"]["20"].get("base") == 102.0
    hist = [b["close"] for b in bars[:0]]  # σ_d=信号日前 60 日（i=0 无前史）
    assert not pm["position"], "i=0 无前史 σ 退化带下 T+20 也只观察不记分"
    # 退化带注记（σ 样本不足）
    assert sig_pos["evaluated"]["20"].get("note", "").startswith("band=退化"), \
        sig_pos["evaluated"]["20"]
    # 有前史的 σ 带：手工造 130 根（信号在第 100 根），band=σ_d×√20 手算钉
    bars2 = []
    q = 100.0
    for d in range(130):
        q *= 1.01 if d % 2 else 0.99  # 日波动 ≈1%
        bars2.append({"date": "2026-%02d-%02d" % (d // 28 + 1, d % 28 + 1),
                      "open": q, "high": q, "low": q, "close": round(q, 6),
                      "volume": 1})
    sig_pos2 = {**sig_buy, "id": "p2", "profile": "position",
                "horizons": [20], "date": bars2[100]["date"],
                "status": "pending", "evaluated": {}}
    pm2, _, _ = evaluate_signals([sig_pos2], {"000001": bars2})
    sigma_d = (fx.realized_vol([b["close"] for b in bars2[:100]], 60)
               or 0.0) / math.sqrt(252)
    want_band = sigma_d * math.sqrt(20)
    chg = (sig_pos2["evaluated"]["20"]["close"]
           / sig_pos2["evaluated"]["20"]["base"] - 1)
    want = ("hit" if chg >= want_band else "miss" if chg <= -want_band
            else "neutral") if sig_pos2["action"] == "buy" else None
    assert sig_pos2["evaluated"]["20"]["outcome"] == (want or "observed"), \
        (chg, want_band, sig_pos2["evaluated"]["20"])
    assert "note" not in sig_pos2["evaluated"]["20"], "σ 可得时不落退化注记"
    # 超窗诊断：信号日早于窗口首日 → 保持 pending + 诊断行（不再静默）
    sig_old = {**sig_buy, "id": "o1", "date": "2020-01-01",
               "status": "pending", "evaluated": {}}
    _, _, onotes = evaluate_signals([sig_old], {"000001": bars})
    assert sig_old["status"] == "pending" and sig_old["evaluated"] == {}
    assert any("超窗" in n and "o1" in n for n in onotes), onotes
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
        # STATE_DIR 一并隔离（run() 的索引重建/名单/持仓都读它）——否则
        # selftest 会把合成 index.md 写进真实 ~/.vibe-stock/reports/（覆盖
        # 用户真实总览，无告警）
        global STATE_DIR, SIGNALS, LEDGER, LEDGER_POSITION
        _old_paths = (STATE_DIR, SIGNALS, LEDGER, LEDGER_POSITION,
                      fx.STATE_DIR, fx.FETCH_STATE)
        _old_fns = (fx.load_fetch_state, fx.save_fetch_state, dict(fx.DAILY_FETCHERS))
        STATE_DIR = td
        SIGNALS, LEDGER = os.path.join(td, "signals.json"), os.path.join(td, "ledger.json")
        LEDGER_POSITION = os.path.join(td, "ledger.position.json")
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
            # 索引重建隔离钉：neutral-only 评估（changed=True）也触发重建，
            # 产物必须落在隔离 STATE_DIR——写真实目录即覆盖用户总览（回归）
            assert os.path.exists(os.path.join(td, "reports", "index.md")), \
                "run() 索引重建必须落在隔离 STATE_DIR（不得写真实 ~/.vibe-stock）"
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
            # I-005：signals.json 损坏 → 严格加载中止（退出码 2、文件字节不变）
            with open(SIGNALS, "w", encoding="utf-8") as f:
                f.write("{corrupt")
            before = open(SIGNALS, encoding="utf-8").read()
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                assert run(argparse.Namespace(stock=None)) == 2
            assert "后验中止" in out.getvalue() and \
                open(SIGNALS, encoding="utf-8").read() == before, \
                "损坏的 signals.json 不得被静默清空/覆盖"
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
            STATE_DIR, SIGNALS, LEDGER, LEDGER_POSITION = _old_paths[:4]
            fx.STATE_DIR, fx.FETCH_STATE = _old_paths[4:]
            (fx.load_fetch_state, fx.save_fetch_state) = _old_fns[:2]
            fx.DAILY_FETCHERS.clear()
            fx.DAILY_FETCHERS.update(_old_fns[2])
    print("  ok run() 守卫：未知市场跳过不阻塞 · --stock 过滤/归一/无匹配/识别失败")
    # 持仓契约漂移可观测（04「portfolio.json 契约」，与 diagnose report 同口径）：
    # 有新评估触发索引重建时，文件存在但与契约不符 → warn: 行、台账照常落盘；
    # 缺失 / 合法 v2 / 合法空表静默。STATE_DIR 一并隔离（不读真实状态目录；
    # global 声明已在前块——同名一处声明，此处复用）
    _old_pf = (STATE_DIR, SIGNALS, LEDGER, fx.STATE_DIR, fx.FETCH_STATE,
               fx.load_fetch_state, fx.save_fetch_state, dict(fx.DAILY_FETCHERS))
    good = {"code": "000001", "market": "cn", "quantity": 300, "cost_price": 12.5}
    pbars = [{"date": "2026-10-%02d" % d, "open": 1, "high": 1, "low": 1,
              "close": 100.0 + 5 * d, "volume": 1} for d in range(1, 31)]  # T+1 hit→重建
    try:
        for payload, n_warn, cols in (
                (None, 0, False), ({"version": 2, "holdings": [good]}, 0, True),
                ({"version": 2, "holdings": []}, 0, False),
                ({"version": 2, "positions": [good]}, 1, False)):
            with tempfile.TemporaryDirectory() as td:
                STATE_DIR, SIGNALS = td, os.path.join(td, "signals.json")
                LEDGER = os.path.join(td, "ledger.json")
                fx.STATE_DIR, fx.FETCH_STATE = td, os.path.join(td, "fetch_state.json")
                fx.load_fetch_state = lambda: {"breakers": {}, "cooldowns": {}}
                fx.save_fetch_state = lambda st: None
                for k in list(fx.DAILY_FETCHERS):
                    fx.DAILY_FETCHERS[k] = lambda m, c: pbars
                _save(SIGNALS, [{**sig_buy, "status": "pending", "evaluated": {},
                                 "horizons": [1]}])
                if payload is not None:
                    _save(os.path.join(td, "portfolio.json"), payload)
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    assert run(argparse.Namespace(stock=None)) == 0
                warns = [ln for ln in out.getvalue().splitlines()
                         if ln.startswith("warn:")]
                assert len(warns) == n_warn and "评估完成" in out.getvalue(), \
                    "契约漂移只告警不中断：%r → %s" % (payload, out.getvalue())
                assert all("portfolio.json 与契约不符" in w and "顶层缺 holdings 键" in w
                           for w in warns), warns
                with open(os.path.join(td, "reports", "index.md"), encoding="utf-8") as f:
                    assert ("持仓数量" in f.read()) is cols, payload
    finally:
        (STATE_DIR, SIGNALS, LEDGER, fx.STATE_DIR, fx.FETCH_STATE,
         fx.load_fetch_state, fx.save_fetch_state) = _old_pf[:7]
        fx.DAILY_FETCHERS.clear()
        fx.DAILY_FETCHERS.update(_old_pf[7])
    print("  ok 持仓契约漂移可观测：存在但不符 warn · 缺失/合法/空表静默 · 不中断台账")
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
    # I-016 到期收盘门：horizon 落末根且末根=当日盘中未完成 K 线（T+3 盘中
    # 跑 postmortem 被盘中价记伪命中的根因）→ 视为未到期保持 pending；
    # 同数据收盘后/周末跑 → 正常评估（session_phase 口径，now 注入钉两态）
    bars_p = bars + [{"date": "2026-11-02", "open": 90.0, "high": 90.0,
                      "low": 90.0, "close": 90.0, "volume": 50}]  # 周一盘中午半截 K
    s_g1 = {**sig_buy, "id": "g1", "date": "2026-10-30", "close_at_signal": 100.0,
            "status": "pending", "horizons": [1], "evaluated": {}}
    evaluate_signals([s_g1], {"000001": bars_p},
                     now=dt.datetime(2026, 11, 2, 10, 58, tzinfo=fx.TZ_CN))
    assert s_g1["evaluated"] == {} and s_g1["status"] == "pending", \
        "末根为当日盘中未完成 K 线：到期 horizon 不评估、保持 pending（I-016）"
    s_g2 = {**s_g1, "id": "g2", "evaluated": {}}
    evaluate_signals([s_g2], {"000001": bars_p},
                     now=dt.datetime(2026, 11, 2, 15, 5, tzinfo=fx.TZ_CN))
    assert s_g2["evaluated"]["1"]["close"] == 90.0 and s_g2["status"] != "pending", \
        "同数据收盘后（15:05 过 A 股收盘）：末根即完成 K 线，正常评估"
    s_g3 = {**sig_buy, "id": "g3", "date": "2026-10-29", "close_at_signal": 100.0,
            "status": "pending", "horizons": [1], "evaluated": {}}
    evaluate_signals([s_g3], {"000001": bars},
                     now=dt.datetime(2026, 10, 31, 10, 58, tzinfo=fx.TZ_CN))
    assert s_g3["evaluated"]["1"]["date"] == "2026-10-30", \
        "周末时段自然 closed：周五末根照常评估"
    # 破坏性实验：旁路 session_phase（守卫失效形态）→ 同一盘中数据被误评估
    # ——证明上钉守的是守卫本身而非数据形状（去掉守卫时 g1 断言必红）
    _sp = fx.session_phase
    fx.session_phase = lambda m, d, now=None: {"phase": "closed"}
    try:
        s_g4 = {**s_g1, "id": "g4", "evaluated": {}}
        evaluate_signals([s_g4], {"000001": bars_p},
                         now=dt.datetime(2026, 11, 2, 10, 58, tzinfo=fx.TZ_CN))
        assert "1" in s_g4["evaluated"] and \
            s_g4["evaluated"]["1"]["close"] == 90.0, \
            "守卫旁路时盘中价必被误评估（破坏性基准）"
    finally:
        fx.session_phase = _sp
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
    # 数学钉：h=1 → 10-02 收盘 101.49×汇率 0.898 / 基准 closes[i]=102×0.899 − 1
    # （复权基准修复后 cny 展示同用 closes[i]，与 outcome 同源；登记价 100 不再作基准）
    ev1 = sig_hk["evaluated"]["1"]
    assert ev1["base"] == 102.0
    assert abs(ev1["cny_close"] - 101.49 * 0.898) < 0.01, ev1
    assert abs(ev1["cny_chg_pct"]
               - (101.49 * 0.898 / (102 * 0.899) - 1) * 100) < 0.01, ev1
    # 汇率序列窗口不足（信号日早于汇率首根）：如实缺省不附字段、不误报
    s5 = {**sig_buy, "id": "h3", "market": "hk", "code": "01810",
          "close_at_signal": 100.0, "status": "pending", "date": "2026-10-05",
          "horizons": [1], "evaluated": {}}
    evaluate_signals([s5], {"01810": bars}, {"2026-10-15": 0.89})
    assert s5["evaluated"]["1"]["outcome"] in ("hit", "miss", "neutral"), \
        "汇率缺根不得影响 outcome 本身"
    assert "cny_close" not in s5["evaluated"]["1"], "汇率缺根须如实缺省"
    # 基准价 null 的 hk 信号（快照兜底登记的合法遗留形态）：--cny 只缺 cny
    # 字段、不得 TypeError 阻断整个评估（默认口径对 base=None 本就容忍）
    s6 = {**sig_buy, "id": "h4", "market": "hk", "code": "01810",
          "close_at_signal": None, "status": "pending", "date": "2026-10-01",
          "horizons": [1], "evaluated": {}}
    evaluate_signals([s6], {"01810": bars}, cny_map)
    assert s6["evaluated"]["1"]["outcome"] in ("hit", "miss", "neutral") \
        and "cny_close" in s6["evaluated"]["1"], \
        "复权基准修复后 null 登记价不再降级：outcome 与 cny 展示均以 closes[i] 为基"
    print("  ok 买入/观察双路径 · 归因台账 · 升降档阈值 · 未到期不动 · 非交易日回退 · 索引后验格")
    print("  ok I-016 到期收盘门：末根盘中不评保持 pending · 收盘后/周末补评 · 旁路必误评（破坏性）")
    print("  ok 人民币口径展示：hk 附 cny 字段 · outcome/归因仍港币 · 缺根如实缺省")
    print("SELFTEST PASSED ✔")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--stock", help="只评该股的 pending 信号（经 detect_market 归一）；不给则全量")
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
