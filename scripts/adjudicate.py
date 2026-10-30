#!/usr/bin/env python3
"""adjudicate.py · vibe-stock 确定性裁决器。

蓝本：DSA（ZhuLinsen/daily_stock_analysis）受控综合链路 + negentropy 178 精读原型
dsa_lab.py 的 M4/M5。本文件回答「意见合不合法、共识是什么、最终裁决是什么」，
全部确定性——LLM 只产意见，裁决一律代码。

链路（与 references/03-synthesis.md 同源，改任一侧须同步）：
  ① 信号资格分选：意见必须落在五个标准信号；别名归一化失败 → 移入诊断记录，
     不进意见链（证据链与诊断互斥且穷尽）。
  ② 确定性聚合：权重 = 置信度 × 绩效因子（Beta(15,15) 收缩、钳 0.83–1.2、样本
     <30 中性 1.0，读 ledger.json）；加权分映射阈值 4.5/3.5/2.5/1.5；有效意见
     零/一条/置信度全零 → insufficient（hold、置信 0）。
  ③ 分歧检测：方向对立 / 置信离散 / 高置信异见（三类；加减分矛盾由策略侧
     rationale 承载，RiskGuard 兜底）；高严重度冲突 → 共识 low。
  ④ 分歧摘要：三桶（bullish/bearish/neutral）显式上桌。
  ⑤ RiskGuard 只降不升：veto 把买入族压 hold；降档沿 buy→hold→sell 单向
     （高严重度可两档）；任何情况不升级。
  ⑥ 置信帽：核心证据块降级（evidence 质量分档 limited 及以下）时，strong_* 一律
     压一档——证据不够，不许嘴硬。

用法：
  uv run --no-project scripts/adjudicate.py --selftest
  uv run --no-project scripts/adjudicate.py \
      --opinions opinions.json --risk risk.json [--evidence evidence.json] \
      [--ledger ~/.vibe-stock/ledger.json] --out verdict.json
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as fx  # noqa: E402  （仅 detect_market：verdict 绑定股票身份）

# ---------------------------------------------------------------- 常量（SSOT：references/03）

CANONICAL = ["strong_buy", "buy", "hold", "sell", "strong_sell"]
LADDER = ["strong_buy", "buy", "hold", "sell", "strong_sell"]
ALIAS = {
    "strong buy": "strong_buy", "strong-buy": "strong_buy", "strongbuy": "strong_buy",
    "accumulating buy": "strong_buy", "加仓买入": "strong_buy",
    "buy": "buy", "long": "buy", "买入": "buy", "增持": "buy",
    "hold": "hold", "neutral": "hold", "持有": "hold", "观望": "hold",
    "sell": "sell", "short": "sell", "卖出": "sell", "减持": "sell",
    "strong sell": "strong_sell", "strong-sell": "strong_sell",
    "strongsell": "strong_sell", "清仓卖出": "strong_sell",
}
AGG_THRESH = [(4.5, "strong_buy"), (3.5, "buy"), (2.5, "hold"), (1.5, "sell")]
CORE_BLOCKS = {"quote", "daily_bars", "technical"}
STATE_SCORE = {"available": 100, "fallback": 85, "partial": 70, "stale": 60,
               "estimated": 55, "missing": 30, "not_supported": 30, "fetch_failed": 25}
BLOCKS = [("quote", 25), ("daily_bars", 25), ("technical", 25),
          ("news", 10), ("fundamentals", 10), ("chip", 5)]
# 0.2.0 扩展块镜像（fetch.EXT_BLOCKS 为 SSOT，此处只作裁决侧口径声明）：
# evidence_cap 有意只算 BLOCKS 六块——扩展块零权重（信息面不是裁决面，置信帽
# 只反映核心行情链可用性）。修订此口径属 0.3.0 级语义变更：须人工评审 + golden
# 重建（selftest E4/E5 两钉冻结当前语义）。
EXT_BLOCKS = ["moneyflow", "notices", "research", "forecast", "unlock",
              "holder", "market", "industry", "valuation"]
PF_CLAMP = (0.83, 1.2)
PF_PRIOR = 15.0        # Beta(15,15) 先验
PF_MIN_SAMPLES = 30    # 样本不足 → 中性 1.0
CONFIDENCE_GATE = 0.5  # buy 族信号登记门槛


# ---------------------------------------------------------------- ① 信号资格分选

def valid_signal(raw):
    """返回标准信号或 None（无效）。只收表内别名；表外自由文本一律无效。"""
    if raw in CANONICAL:
        return raw
    return ALIAS.get(str(raw).strip().lower())


def partition(opinions):
    """opinions: [{source, signal, confidence, rationale?}]。
    返回 (valid, diagnostics)：每个意见恰好落进其一，互斥且穷尽。"""
    valid, diag = [], []
    for o in opinions:
        sig = valid_signal(o.get("signal", ""))
        if sig is None:
            diag.append({"source": o.get("source", "?"),
                         "raw": o.get("signal", ""), "reason": "invalid_signal"})
            continue
        conf = float(o.get("confidence", 0))
        if not 0.0 <= conf <= 1.0:
            diag.append({"source": o.get("source", "?"),
                         "raw": o.get("signal", ""), "reason": "confidence_out_of_range"})
            continue
        valid.append({"source": o["source"], "signal": sig, "confidence": conf,
                      "rationale": o.get("rationale", "")})
    return valid, diag


# ---------------------------------------------------------------- ② 聚合 + ③ 分歧

def performance_factor(ledger, source):
    """ledger: {"<source>": {"wins": w, "losses": l}}；Beta(15,15) 收缩 + 钳制。"""
    rec = (ledger or {}).get(source, {})
    w, l = float(rec.get("wins", 0)), float(rec.get("losses", 0))
    if w + l < PF_MIN_SAMPLES:
        return 1.0
    pf = (w + PF_PRIOR) / (w + l + 2 * PF_PRIOR) * 2  # 收缩到 1 附近
    return round(max(PF_CLAMP[0], min(PF_CLAMP[1], pf)), 4)


def aggregate(valid, ledger=None):
    """确定性聚合。返回 {final_signal, confidence, consensus_level, conflicts, _valid}。"""
    ledger = ledger or {}
    for o in valid:
        o["weight"] = performance_factor(ledger, o["source"])
    if len(valid) <= 1 or sum(o["confidence"] for o in valid) == 0:
        return {"final_signal": "hold", "confidence": 0.0,
                "consensus_level": "insufficient", "conflicts": [], "_valid": valid}
    bull = [o for o in valid if o["signal"] in ("strong_buy", "buy")]
    bear = [o for o in valid if o["signal"] in ("strong_sell", "sell")]
    conflicts = []
    if bull and bear:
        conflicts.append({"type": "direction_opposition", "severity": "high"})
    confs = [o["confidence"] for o in valid]
    if max(confs) - min(confs) >= 0.3:
        conflicts.append({"type": "spread", "severity": "medium"})
    final_sig = max(valid, key=lambda o: o["confidence"] * o["weight"])
    for o in valid:
        if (o["confidence"] >= 0.75 and o is not final_sig
                and abs(LADDER.index(o["signal"]) -
                        LADDER.index(final_sig["signal"])) >= 2):
            conflicts.append({"type": "high_conf_dissent",
                              "severity": "high" if o["confidence"] >= 0.9 else "medium"})
    aligned = len([o for o in valid if o["signal"] == final_sig["signal"]]) / len(valid)
    if any(c["severity"] == "high" for c in conflicts):
        level = "low"
    elif aligned >= 2 / 3 and not conflicts:
        level = "high"
    else:
        level = "medium"
    wscore = max(o["confidence"] * o["weight"] * 5 for o in valid)
    for th, sig in AGG_THRESH:
        if wscore >= th:
            return {"final_signal": sig, "confidence": round(final_sig["confidence"], 2),
                    "consensus_level": level, "conflicts": conflicts, "_valid": valid}
    return {"final_signal": "hold", "confidence": round(final_sig["confidence"], 2),
            "consensus_level": level, "conflicts": conflicts, "_valid": valid}


# ---------------------------------------------------------------- ④ 分歧摘要

def disagreement_summary(agg):
    buckets = {"bullish": [], "bearish": [], "neutral": []}
    for o in agg["_valid"]:
        if o["signal"] in ("strong_buy", "buy"):
            buckets["bullish"].append(o["source"])
        elif o["signal"] in ("strong_sell", "sell"):
            buckets["bearish"].append(o["source"])
        else:
            buckets["neutral"].append(o["source"])
    return {"buckets": buckets, "conflicts": agg["conflicts"]}


# ---------------------------------------------------------------- ⑤ RiskGuard（只降不升）

def risk_guard(decision, veto=False, downgrade=False, severity_high=False):
    """veto: 买入族→hold；downgrade: 单向降一/两档。永不升级。返回 (final, log)。"""
    d = LADDER.index(decision)
    if veto and decision in ("buy", "strong_buy"):
        return "hold", "veto %s->hold" % decision
    if downgrade:
        steps = 2 if severity_high else 1
        return LADDER[min(d + steps, 4)], "downgrade %s->%s" % (
            decision, LADDER[min(d + steps, 4)])
    return decision, "no-op"


# ---------------------------------------------------------------- ⑥ 置信帽

def evidence_cap(evidence):
    """evidence.json 的 blocks → (score, tier, cap)。cap=low 时 strong_* 压一档。"""
    blocks = (evidence or {}).get("blocks", {})
    states = {n: (blocks.get(n, {}) or {}).get("state", "missing") for n, _ in BLOCKS}
    score = sum(STATE_SCORE.get(states.get(n, "missing"), 0) * w for n, w in BLOCKS) // 100
    tier = ("good" if score >= 85 else "usable" if score >= 70
            else "limited" if score >= 55 else "poor")
    core_degraded = any(states.get(n, "missing") not in ("available", "fallback")
                        for n in CORE_BLOCKS)
    return score, tier, ("low" if core_degraded else "high")


def apply_confidence_cap(signal, cap):
    if cap != "low" or signal not in ("strong_buy", "strong_sell"):
        return signal, "no-op"
    pressed = "buy" if signal == "strong_buy" else "sell"
    return pressed, "confidence_cap %s->%s (core evidence degraded)" % (signal, pressed)


# ---------------------------------------------------------------- 编排

def adjudicate(opinions, risk, evidence=None, ledger=None):
    """全链路。risk: {veto, downgrade, severity, rationale}；返回 verdict dict。"""
    valid, diagnostics = partition(opinions)
    agg = aggregate(valid, ledger)
    ds = disagreement_summary(agg)
    initial = agg["final_signal"]
    guarded, glog = risk_guard(initial, bool(risk.get("veto")),
                               bool(risk.get("downgrade")),
                               risk.get("severity") == "high")
    score, tier, cap = evidence_cap(evidence)
    final, caplog = apply_confidence_cap(guarded, cap)
    executable = final in ("buy", "strong_buy") and agg["confidence"] >= CONFIDENCE_GATE
    meta = ((evidence or {}).get("meta") or {})
    # 身份闸门比对键：推导唯一实现处 fx.meta_stock_code（与 diagnose 同源），
    # 不可识别回 None（闸门对 None 放行，兼容旧版/手写 verdict）
    code, recognized = fx.meta_stock_code(meta)
    stock_code = code if recognized else None
    return {
        "stock_code": stock_code,
        "valid_opinions": [{k: o[k] for k in ("source", "signal", "confidence", "weight")}
                           for o in agg["_valid"]],
        "diagnostics": diagnostics,
        "aggregate": {k: agg[k] for k in
                      ("final_signal", "confidence", "consensus_level", "conflicts")},
        "disagreement": ds,
        "risk_guard": {"initial": initial, "final_before_cap": guarded, "final": final,
                       "log": [glog, caplog]},
        "evidence_quality": {"score": score, "tier": tier, "confidence_cap": cap},
        "executable": executable,
    }


# ---------------------------------------------------------------- selftest（回归底线，只收严）

def _check(name, got, want):
    assert got == want, "%s: got %r want %r" % (name, got, want)
    print("  ok %-34s %r" % (name, got))


def selftest():
    print("== 正常路径 ==")
    ops = [
        {"source": "strategy:ma_golden_cross", "signal": "buy", "confidence": 0.8},
        {"source": "strategy:bull_trend", "signal": "strong buy", "confidence": 0.9},
        {"source": "strategy:chan_theory", "signal": "buy", "confidence": 0.7},
    ]
    ev = {"blocks": {n: {"state": "available"} for n, _ in BLOCKS}}
    v = adjudicate(ops, {}, ev)
    _check("valid count", len(v["valid_opinions"]), 3)
    _check("alias normalize", v["valid_opinions"][1]["signal"], "strong_buy")
    _check("agg signal", v["aggregate"]["final_signal"], "strong_buy")
    _check("consensus medium(1/3 aligned)", v["aggregate"]["consensus_level"], "medium")
    _check("no-op guard", v["risk_guard"]["final"], "strong_buy")
    _check("executable gate", v["executable"], True)
    _check("stock_code 无 meta 回退 None", v["stock_code"], None)
    ev_hk = {"meta": {"market": "hk", "code": "0700"},
             "blocks": {n: {"state": "available"} for n, _ in BLOCKS}}
    _check("stock_code 港股归一 5 位", adjudicate(ops, {}, ev_hk)["stock_code"], "00700")

    print("== 无效意见进诊断（互斥且穷尽） ==")
    ops2 = ops + [{"source": "strategy:hot_theme", "signal": "看多!!!", "confidence": 0.95},
                  {"source": "role:technical", "signal": "buy", "confidence": 7}]
    v2 = adjudicate(ops2, {}, ev)
    _check("diag count", len(v2["diagnostics"]), 2)
    _check("diag reason 1", v2["diagnostics"][0]["reason"], "invalid_signal")
    _check("diag reason 2", v2["diagnostics"][1]["reason"], "confidence_out_of_range")
    _check("pollution blocked", "hot_theme" not in
           [o["source"] for o in v2["valid_opinions"]], True)

    print("== insufficient（单条/全零置信） ==")
    v3 = adjudicate([ops[0]], {}, ev)
    _check("single insufficient", v3["aggregate"]["consensus_level"], "insufficient")
    _check("single final", v3["risk_guard"]["final"], "hold")
    v3b = adjudicate([{"source": "a", "signal": "buy", "confidence": 0.0},
                      {"source": "b", "signal": "buy", "confidence": 0.0}], {}, ev)
    _check("zero-conf insufficient", v3b["aggregate"]["consensus_level"], "insufficient")

    print("== 方向冲突 → low；veto 压 hold ==")
    ops4 = [
        {"source": "strategy:bull_trend", "signal": "buy", "confidence": 0.85},
        {"source": "strategy:wave_theory", "signal": "sell", "confidence": 0.8},
    ]
    v4 = adjudicate(ops4, {"veto": True}, ev)
    _check("direction conflict", v4["aggregate"]["conflicts"][0]["type"],
           "direction_opposition")
    _check("consensus low", v4["aggregate"]["consensus_level"], "low")
    _check("veto hold", v4["risk_guard"]["final"], "hold")
    _check("buckets", (v4["disagreement"]["buckets"]["bullish"],
                       v4["disagreement"]["buckets"]["bearish"]),
           (["strategy:bull_trend"], ["strategy:wave_theory"]))

    print("== RiskGuard 只降不升（高严重度两档） ==")
    v5 = adjudicate(ops, {"downgrade": True, "severity": "high"}, ev)
    _check("strong_buy -2 = hold", v5["risk_guard"]["final"], "hold")
    _check("buy -2 = sell", risk_guard("buy", downgrade=True, severity_high=True)[0],
           "sell")
    _check("veto only hits buy family", risk_guard("hold", veto=True)[0], "hold")
    _check("never upgrades sell", risk_guard("sell", downgrade=True)[0], "strong_sell")

    print("== 绩效因子（Beta 收缩 + 钳制 + 样本门） ==")
    _check("pf <30 samples", performance_factor({"s": {"wins": 9, "losses": 1}}, "s"), 1.0)
    _check("pf 30/0 clamp", performance_factor({"s": {"wins": 30, "losses": 0}}, "s"), 1.2)
    _check("pf 0/30 clamp", performance_factor({"s": {"wins": 0, "losses": 30}}, "s"), 0.83)
    pf_mid = performance_factor({"s": {"wins": 30, "losses": 30}}, "s")
    _check("pf 50% ≈1.0", 0.98 <= pf_mid <= 1.02, True)

    print("== 置信帽（核心块降级禁高置信） ==")
    ev_bad = {"blocks": {"quote": {"state": "stale"}, "daily_bars": {"state": "fallback"},
                         "technical": {"state": "available"}, "news": {"state": "missing"},
                         "fundamentals": {"state": "missing"},
                         "chip": {"state": "fetch_failed"}}}
    v6 = adjudicate(ops, {}, ev_bad)
    _check("cap low", v6["evidence_quality"]["confidence_cap"], "low")
    _check("tier limited", v6["evidence_quality"]["tier"], "limited")
    _check("strong pressed", v6["risk_guard"]["final"], "buy")
    _check("cap log", "confidence_cap" in v6["risk_guard"]["log"][1], True)

    print("== 破坏性实验（证明各机制不可拆） ==")
    # 拆验票门：无效信号（「看多!!!」当 strong_buy）直进意见链的后果
    polluted = aggregate([
        {"source": "strategy:hot_theme", "signal": "strong_buy", "confidence": 0.95},
        {"source": "strategy:wave_theory", "signal": "sell", "confidence": 0.7}], {})
    _check("E1 no-partition pollution", polluted["final_signal"], "strong_buy")
    # 拆只降不升：允许升级的后果（直接演示被禁形态）
    _check("E2 upgrade forbidden by design", risk_guard("hold", downgrade=True)[0]
           in LADDER[LADDER.index("hold"):], True)
    # 拆置信帽：核心块降级仍放行 strong_*
    no_cap, _ = apply_confidence_cap("strong_buy", "high")
    _check("E3 no-cap keeps strong", (no_cap, apply_confidence_cap("strong_buy", "low")[0]),
           ("strong_buy", "buy"))
    # 拆零权重钉（0.2.0）：扩展块状态任意变化不得扰动质量分/档位/置信帽
    ev_base = {"blocks": {n: {"state": "available"} for n, _ in BLOCKS}}
    ev_ext_failed = {"blocks": {**{n: {"state": "available"} for n, _ in BLOCKS},
                                **{n: {"state": "fetch_failed"} for n in EXT_BLOCKS}}}
    _check("E4 ext blocks zero-weight", evidence_cap(ev_ext_failed),
           evidence_cap(ev_base))
    # 前向兼容钉：未知名块静默忽略不报错（fetch 层加块无须同步本文件）。
    # future_block 必须放进 blocks 内——真实场景是 fetch 往 blocks 加新键，
    # 放外层对 evidence_cap 是恒真测试，钉不住该不变量。
    ev_unknown = {"blocks": {**{n: {"state": "available"} for n, _ in BLOCKS},
                             "future_block": {"state": "available"}}}
    _check("E5 unknown block ignored", evidence_cap(ev_unknown), evidence_cap(ev_base))
    print("SELFTEST PASSED ✔")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--opinions")
    ap.add_argument("--risk", default='{"veto": false, "downgrade": false}')
    ap.add_argument("--evidence")
    ap.add_argument("--ledger")
    ap.add_argument("--out", default="verdict.json")
    args = ap.parse_args()
    if args.selftest:
        selftest()
        return
    if not args.opinions:
        ap.error("需要 --opinions（或 --selftest）")
    if args.evidence and not os.path.exists(args.evidence):
        ap.error("--evidence 文件不存在：%s" % args.evidence)  # 防静默降级为 missing
    load = lambda p, d: json.load(open(p, encoding="utf-8")) if p and os.path.exists(p) else d
    verdict = adjudicate(load(args.opinions, []),
                         load(args.risk, {}),
                         load(args.evidence, None),
                         load(args.ledger, None))
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(verdict, f, ensure_ascii=False, indent=1)
    print(json.dumps(verdict, ensure_ascii=False, indent=1))
    sys.exit(0 if verdict["valid_opinions"] or verdict["diagnostics"] else 1)


if __name__ == "__main__":
    main()
