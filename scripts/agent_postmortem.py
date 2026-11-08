#!/usr/bin/env python3
"""agent: 前缀独立画像（主 Agent decision log 的 T2 建议卡后验记分，07 L118 预留位落地）。

数据源：~/.vibe-stock/agent/decisions.jsonl（写者=stock-trading-agent 主 Agent，本脚本只读）
的 advice_card_written 决策行（payload：code/date/final_signal/candidate_action，全脱敏）。
判定口径：T+1/3/5 收盘 ±2% 同式判定——import scripts/postmortem.py 的 score/NEUTRAL_BAND
（禁复制实现，06「聚合分复算逐字同步」同类教训）；到期收盘门 I-016 同判（末根=盘中未完成
K 线不评，收盘后下一次运行补评）。
台账：ledger.agent.json 独立画像（沿 monitor: 前缀先例——不进 ledger.json /
ledger.position.json）；归因子 agent:<final_signal>（五词）；evaluated 索引防重评（幂等）。
运行形态：手动或与 18:05 postmortem 槽串联（plist 串联命令见 batch/postmortem/ README，
暂不装独立槽）。advice_refused 风险提示类方向语义不同构（避开回撤即有效），攒样本后经
RSI 评审再入回路（07 P3 先例同款留位）——本脚本只记分 advice_card_written。
"""

import argparse
import bisect
import datetime as dt
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive as ar  # noqa: E402
import fetch as fx  # noqa: E402
import postmortem as pm  # noqa: E402

HOME = os.path.expanduser("~/.vibe-stock")
DECISIONS = os.path.join(HOME, "agent", "decisions.jsonl")
LEDGER_AGENT = os.path.join(HOME, "ledger.agent.json")
HORIZONS = (1, 3, 5)  # 07 L118：T+1/3/5 同式判定
CARD_KIND = "advice_card_written"


def signal_to_action(final_signal):
    """final_signal 五词 → 记分动作（bull/bear 家族桥；hold 只观察不记分）。

    非复制 ACTION_OF：取 score() 的 SCORABLE 家族语义最小桥（buy=bull、sell=bear）。
    """
    if final_signal in ("strong_buy", "buy"):
        return "buy"
    if final_signal in ("sell", "strong_sell"):
        return "sell"
    return None  # hold：只观察


def load_agent_cards(path=DECISIONS):
    """decisions.jsonl → {key: payload}（只取 advice_card_written；后写覆盖先写）。"""
    cards = {}
    if not os.path.exists(path):
        return cards
    with open(path, encoding="utf-8") as f:
        for raw in f:
            raw = raw.strip()
            if not raw:
                continue
            try:
                line = json.loads(raw)
            except json.JSONDecodeError:
                continue  # append-only 尾行截断容错（与产品仓解析纪律同式）
            if not isinstance(line, dict) or line.get("kind") != CARD_KIND:
                continue
            payload = line.get("payload") or {}
            code, date = payload.get("code"), payload.get("date")
            if not code or not date:
                continue
            cards[f"{date}:{code}"] = payload
    return cards


def evaluate_card(payload, bars, market, now=None):
    """单卡 T+1/3/5 同式判定；返回 {h: outcome}（未到期 horizon 不在返回值中）。

    基准=卡面 date 当日收盘（非交易日回退最近一根，与 postmortem 非交易日信号同判）；
    I-016 到期收盘门：j==末根 且 last_bar_partial → 视为未到期。
    """
    action = signal_to_action(payload.get("final_signal"))
    if action is None:
        return {}
    dates = [b["date"] for b in bars]
    closes = [b["close"] for b in bars]
    if payload["date"] < dates[0]:
        return {}  # 超窗（BARS_WINDOW=250 之外）：跳过，诊断由调用方打印
    try:
        i = dates.index(payload["date"])
    except ValueError:
        j = bisect.bisect_right(dates, payload["date"]) - 1
        if j < 0 or payload["date"] > dates[-1]:
            return {}
        i = j
    last_partial = fx.session_phase(market, dates[-1], now).get("last_bar_partial")
    outcomes = {}
    for h in HORIZONS:
        j = i + h
        if j >= len(closes):
            continue  # 未到期
        if j == len(closes) - 1 and last_partial:
            continue  # I-016：末根盘中未完成 → 收盘后补评
        outcome = pm.score(action, closes[i], closes[j])
        if outcome is not None:
            outcomes[h] = outcome
    return outcomes


def _load_ledger(path=LEDGER_AGENT):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_ledger(path, obj):
    ar.write_json_atomic(path, obj)  # I-005 原子写（与 postmortem 同式）


def run(args):
    cards = load_agent_cards(args.decisions)
    if not cards:
        print("decisions.jsonl 无 %s 决策，无可评估项" % CARD_KIND)
        return 0
    ledger = _load_ledger(args.ledger)
    evaluated = ledger.setdefault("evaluated", {})
    attribution = ledger.setdefault("attribution", {})
    bars_cache = {}
    scored = 0
    for key, payload in sorted(cards.items()):
        pending_h = [h for h in HORIZONS if evaluated.get(f"{key}:h{h}") is None]
        if not pending_h:
            continue  # 幂等：全 horizon 已评
        market = "hk" if len(payload["code"]) == 5 else "cn"
        if payload["code"] not in bars_cache:
            st = fx.load_fetch_state()
            bars, _s, _src, _tried = fx.fetch_daily_bars(
                market, payload["code"], st, int(dt.datetime.now().timestamp()))
            fx.save_fetch_state(st)
            bars_cache[payload["code"]] = bars or []
        bars = bars_cache[payload["code"]]
        if not bars:
            print("warn: %s 日 K 不可得，跳过本轮（下次运行补评）" % payload["code"])
            continue
        outcomes = evaluate_card(payload, bars, market)
        if not outcomes:
            print("warn: %s（%s）未到期或超窗，保持待评" % (payload["code"], payload["date"]))
            continue
        for h, outcome in outcomes.items():
            evaluated[f"{key}:h{h}"] = outcome
            src = "agent:%s" % payload.get("final_signal")
            bucket = attribution.setdefault(src, {"wins": 0, "losses": 0})
            if outcome == "hit":
                bucket["wins"] += 1
            elif outcome == "miss":
                bucket["losses"] += 1
            scored += 1
    if scored:
        _save_ledger(args.ledger, ledger)
        print("评估完成：%d 个 horizon 落账（%s）" % (scored, args.ledger))
        for src, d in sorted(attribution.items()):
            print("  归因 %s：+%d 胜 / +%d 负" % (src, d["wins"], d["losses"]))
    else:
        print("无新到期 horizon（不落「已更新」失实陈述，亦不空写台账）")
    return 0


def selftest():
    ok = True

    def check(name, cond):
        nonlocal ok
        print(("PASS" if cond else "FAIL"), name)
        ok = ok and cond

    check("signal_to_action 桥", signal_to_action("buy") == "buy"
          and signal_to_action("strong_sell") == "sell" and signal_to_action("hold") is None)
    bars = [{"date": "2026-11-0%d" % d, "close": 10.0 if d < 5 else 10.5} for d in range(1, 8)]
    out = evaluate_card({"date": "2026-11-02", "final_signal": "buy"}, bars, "cn")
    check("到期窗判定", out == {1: "neutral", 3: "hit", 5: "hit"})
    # 坏行容错
    import tempfile
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False) as fh:
        fh.write('{bad\n{"kind":"%s","payload":{"code":"600519","date":"2026-11-07",'
                 '"final_signal":"buy"}}\n' % CARD_KIND)
        tmp = fh.name
    cards = load_agent_cards(tmp)
    check("decisions 解析容错", list(cards) == ["2026-11-07:600519"])
    os.unlink(tmp)
    # score import 契约（禁复制）：同式 ±2%
    check("score 同式 import", pm.score("buy", 10.0, 10.3) == "hit"
          and pm.score("buy", 10.0, 9.7) == "miss")
    print("agent_postmortem selftest:", "ALL PASS" if ok else "FAILED")
    return 0 if ok else 1


def main():
    ap = argparse.ArgumentParser(description="agent: 前缀独立画像（07 L118）")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--decisions", default=DECISIONS)
    ap.add_argument("--ledger", default=LEDGER_AGENT)
    args = ap.parse_args()
    if args.selftest:
        return selftest()
    return run(args)


if __name__ == "__main__":
    sys.exit(main())
