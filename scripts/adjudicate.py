#!/usr/bin/env python3
"""adjudicate.py · vibe-stock 确定性裁决器。

蓝本：DSA（ZhuLinsen/daily_stock_analysis）受控综合链路 + negentropy 178 精读原型
dsa_lab.py 的 M4/M5。本文件回答「意见合不合法、共识是什么、最终裁决是什么」，
全部确定性——LLM 只产意见，裁决一律代码。

链路（与 references/03-synthesis.md 同源，改任一侧须同步）：
  ① 信号资格分选：意见必须落在五个标准信号；别名归一化失败 → 移入诊断记录，
     不进意见链（证据链与诊断互斥且穷尽）。
  ② 确定性聚合：权重 = 置信度 × 绩效因子（Beta(15,15) 收缩、钳 0.83–1.2、样本
     <30 中性 1.0，读 ledger.json）；加权分 = 3 + Σ(绩效×置信×(档位值−3)) / Σ绩效
     ——置信收缩向 hold（档位值 strong_buy=5 … strong_sell=1，低置信板向 hold 收），
     映射阈值 4.5/3.5/2.5/1.5；聚合置信只取与聚合信号同方向族的意见（绩效加权
     均值，无同族支撑为 0）；有效意见零/一条/置信度全零 → insufficient（hold、
     置信 0）。
  ③ 分歧检测：方向对立 / 置信离散 / 高置信异见（三类；加减分矛盾由策略侧
     rationale 承载，RiskGuard 兜底）；主信号 = 聚合信号；高严重度冲突 → 共识 low。
  ④ 分歧摘要：三桶（bullish/bearish/neutral）显式上桌。
  ⑤ RiskGuard 只降不升：veto 把买入族压 hold；降档沿 buy→hold→sell 单向
     （高严重度可两档）；任何情况不升级；veto 与降档同真时各自施加、取更保守者。
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
import fetch as fx  # noqa: E402  （仅 meta_stock_code：verdict 绑定股票身份）

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
LEVEL = {s: 5 - i for i, s in enumerate(LADDER)}  # 档位值 strong_buy=5 … strong_sell=1
FAMILY = {"strong_buy": "bull", "buy": "bull", "hold": "neutral",
          "sell": "bear", "strong_sell": "bear"}
CORE_BLOCKS = {"quote", "daily_bars", "technical"}
STATE_SCORE = {"available": 100, "fallback": 85, "partial": 70, "stale": 60,
               "estimated": 55, "missing": 30, "not_supported": 30, "fetch_failed": 25}
BLOCKS = [("quote", 25), ("daily_bars", 25), ("technical", 25),
          ("news", 10), ("fundamentals", 10), ("chip", 5)]
# 扩展块镜像（fetch.EXT_BLOCKS 为 SSOT，此处只作裁决侧口径声明）：
# evidence_cap 有意只算 BLOCKS 六块——扩展块零权重（信息面不是裁决面，置信帽
# 只反映核心行情链可用性）。修订此口径属 minor 级语义变更：须人工评审 + golden
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
    """确定性聚合。返回 {final_signal, score, confidence, consensus_level, conflicts, _valid}。"""
    ledger = ledger or {}
    for o in valid:
        o["weight"] = performance_factor(ledger, o["source"])
    if len(valid) <= 1 or sum(o["confidence"] for o in valid) == 0:
        return {"final_signal": "hold", "score": None, "confidence": 0.0,
                "consensus_level": "insufficient", "conflicts": [], "_valid": valid}
    # 置信收缩加权分：3 + Σ(绩效×置信×(档位值−3)) / Σ绩效。方向与绝对置信都进分
    # ——纯均值对全体置信等比缩放不变（两条 0.1 置信 strong_buy 也出 strong_buy），
    # 收缩后低置信板向 hold 收；四位小数取整，防浮点误差把恰在阈值上的分判错档
    p = [o["weight"] for o in valid]
    score = round(3 + sum(pi * o["confidence"] * (LEVEL[o["signal"]] - 3)
                          for pi, o in zip(p, valid)) / sum(p), 4)
    final = next((sig for th, sig in AGG_THRESH if score >= th), "strong_sell")
    # 聚合置信只认同方向族：绩效加权均值（≤ 同族最高置信），无同族支撑 → 0.0
    fam = [(pi, o["confidence"]) for pi, o in zip(p, valid)
           if FAMILY[o["signal"]] == FAMILY[final]]
    fw = sum(pi for pi, _ in fam)
    conf = (min(round(sum(pi * c for pi, c in fam) / fw, 2), max(c for _, c in fam))
            if fw else 0.0)
    bull = [o for o in valid if o["signal"] in ("strong_buy", "buy")]
    bear = [o for o in valid if o["signal"] in ("strong_sell", "sell")]
    conflicts = []
    if bull and bear:
        conflicts.append({"type": "direction_opposition", "severity": "high"})
    confs = [o["confidence"] for o in valid]
    if max(confs) - min(confs) >= 0.3:
        conflicts.append({"type": "spread", "severity": "medium"})
    # 主信号 = 聚合信号（不是置信×绩效最高的那条意见）：异见与共识都以它为锚
    for o in valid:
        if (o["confidence"] >= 0.75
                and abs(LADDER.index(o["signal"]) - LADDER.index(final)) >= 2):
            conflicts.append({"type": "high_conf_dissent",
                              "severity": "high" if o["confidence"] >= 0.9 else "medium"})
    aligned = len([o for o in valid if o["signal"] == final]) / len(valid)
    if any(c["severity"] == "high" for c in conflicts):
        level = "low"
    elif aligned >= 2 / 3 and not conflicts:
        level = "high"
    else:
        level = "medium"
    return {"final_signal": final, "score": score, "confidence": conf,
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
    """veto: 买入族→hold；downgrade: 单向降一/两档。永不升级。返回 (final, log)。
    同真时各自对同一初判施加、取更保守者（档位索引取大）：veto 不吞 downgrade，
    同一风险理由也不叠罚。"""
    d = LADDER.index(decision)
    cands, log = [d], []
    if veto and decision in ("buy", "strong_buy"):
        cands.append(LADDER.index("hold"))
        log.append("veto %s->hold" % decision)
    if downgrade:
        steps = 2 if severity_high else 1
        cands.append(min(d + steps, 4))
        log.append("downgrade %s->%s" % (decision, LADDER[min(d + steps, 4)]))
    final = LADDER[max(cands)]
    if len(log) == 2:
        log.append("stricter=%s" % final)
    return final, "; ".join(log) or "no-op"


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
    # 置信收缩 3+(0.8+0.9×2+0.7)/3=4.1 → buy；主信号 buy 2/3 同档、零冲突 → high
    _check("agg signal", v["aggregate"]["final_signal"], "buy")
    _check("consensus high(2/3 aligned)", v["aggregate"]["consensus_level"], "high")
    _check("no-op guard", v["risk_guard"]["final"], "buy")
    _check("agg conf = bull-family mean", v["aggregate"]["confidence"], 0.8)
    _check("executable gate", v["executable"], True)
    _check("stock_code 无 meta 回退 None", v["stock_code"], None)
    ev_hk = {"meta": {"market": "hk", "code": "0700"},
             "blocks": {n: {"state": "available"} for n, _ in BLOCKS}}
    _check("stock_code 港股归一 5 位", adjudicate(ops, {}, ev_hk)["stock_code"], "00700")
    # strong_* 初判 Fixture：置信帽、两档降级须以 strong_buy 为输入才触达
    # （收缩后进 strong_buy 须高置信一致：3+2×mean(c)≥4.5 → mean(c)≥0.75）
    ops_s = [
        {"source": "strategy:bull_trend", "signal": "strong_buy", "confidence": 0.9},
        {"source": "strategy:volume_breakout", "signal": "strong_buy", "confidence": 0.85},
        {"source": "strategy:chan_theory", "signal": "strong_buy", "confidence": 0.8},
    ]
    _check("agg strong_buy(score 4.7)", aggregate([dict(o) for o in ops_s])["score"], 4.7)
    _check("agg strong_buy signal", adjudicate(ops_s, {}, ev)["risk_guard"]["initial"],
           "strong_buy")

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

    print("== 聚合 = 置信收缩加权分（方向与绝对置信进分，置信只认同族） ==")
    board = lambda *spec: [{"source": "s%d" % i, "signal": s, "confidence": c}
                           for i, (s, c) in enumerate(spec)]
    # 旧实现（RSI-20261029-01 缺陷形态）：wscore = max(置信×绩效×5)，方向不进分。
    # 留作新旧对照基线，钉住下述放宽面/收严面（AGENTS.md 红线 4 须人工评审面）
    def legacy_max_signal(spec):
        for o in spec:
            o["weight"] = o.get("weight", 1.0)
        top = max(o["confidence"] * o["weight"] * 5 for o in spec)
        return next((sig for th, sig in AGG_THRESH if top >= th), "strong_sell")
    # 全空头板（最高置信是 0.70 sell）：旧 0.7×5=3.5 → buy；收缩 3−2.53/13=2.8054
    bear13 = board(*[("hold", c) for c in (0.2, 0.3, 0.35, 0.4, 0.45, 0.5, 0.5, 0.55, 0.6)],
                   *[("sell", c) for c in (0.65, 0.55, 0.7, 0.63)])
    a = aggregate(bear13)
    _check("bear board 9h+4s", (a["final_signal"], a["score"], a["confidence"]),
           ("hold", 2.8054, 0.43))
    # 收严面显式样例（新结果比旧结果更保守，供人工评审与 CHANGELOG 对账）
    _check("tighten: bear 9h+4s", (legacy_max_signal([dict(o) for o in bear13]),
                                   a["final_signal"]), ("buy", "hold"))
    bear2 = board(("sell", 0.9), ("sell", 0.9))
    _check("bear 2s", aggregate([dict(o) for o in bear2])["final_signal"], "sell")
    # <1.5 兜底 strong_sell 可达（旧实现兜底分支错写 hold、该档从未可达）：
    # 2×strong_sell 1.0 → 3−2×1.0=1.0 <1.5
    _check("agg strong_sell reachable",
           aggregate(board(("strong_sell", 1.0), ("strong_sell", 1.0)))["final_signal"],
           "strong_sell")
    # 纯中性板：hold；共识如实分级（同档 3/3 零冲突 high，置信离散 ≥0.3 → medium）
    a = aggregate(board(("hold", 0.4), ("hold", 0.5), ("hold", 0.6)))
    _check("neutral tight", (a["final_signal"], a["consensus_level"], a["confidence"]),
           ("hold", "high", 0.5))
    a = aggregate(board(("hold", 0.2), ("hold", 0.5), ("hold", 0.6)))
    _check("neutral spread", (a["final_signal"], a["consensus_level"]), ("hold", "medium"))
    # 单条 ≥0.9 高置信意见混在 hold 板里不得把聚合推进买入族/strong_*
    # （旧形态 0.95×5=4.75 → strong_buy；收缩 3+1.9/4=3.475 → hold）
    lone = board(("strong_buy", 0.95), ("hold", 0.5), ("hold", 0.5), ("hold", 0.4))
    a = aggregate([dict(o) for o in lone])
    _check("lone 0.95 strong_buy", a["final_signal"], "hold")
    _check("tighten: lone 0.95 sb", (legacy_max_signal([dict(o) for o in lone]),
                                     a["final_signal"]), ("strong_buy", "hold"))
    # 放宽面显式样例（新结果比旧结果更激进，红线 4 的须人工评审面，不得回避）：
    # 低置信一致多头板旧 max=0.6×5=3.0 → hold；收缩 3+0.6×2=4.2 → buy；
    # 高置信一致板旧 0.8×5=4.0 → buy；收缩 4.6 → strong_buy
    for spec, old_sig, new_sig in ((board(("strong_buy", 0.6), ("strong_buy", 0.6)),
                                    "hold", "buy"),
                                   (board(("strong_buy", 0.8), ("strong_buy", 0.8)),
                                    "buy", "strong_buy")):
        _check("relax: 2x sb", (legacy_max_signal([dict(o) for o in spec]),
                                aggregate([dict(o) for o in spec])["final_signal"]),
               (old_sig, new_sig))
    # 多空对冲落 hold 且无 hold 意见：无同族支撑 → 置信 0.0
    vh = adjudicate(board(("buy", 0.8), ("sell", 0.8)), {}, ev)
    _check("hedge no same-family", (vh["aggregate"]["final_signal"],
                                    vh["aggregate"]["confidence"]), ("hold", 0.0))
    # ≥0.9 异见升 high：sell 0.9 与主信号 buy（3+1.125=4.125）隔 2 档
    a = aggregate(board(("strong_buy", 0.9), ("strong_buy", 0.9), ("strong_buy", 0.9),
                        ("sell", 0.9)))
    _check("dissent >=0.9 high", a["conflicts"][-1],
           {"type": "high_conf_dissent", "severity": "high"})
    # 阈值边界：数学上恰 3.5（浮点 3.4999…）按四位小数取整归 ≥3.5 → buy
    _check("boundary 3.5 rounding",
           aggregate(board(("strong_buy", 0.35), ("strong_buy", 0.35),
                           ("buy", 0.1)))["score"], 3.5)
    # 聚合置信 ≤ 同族最高置信（无同族时上界 0.0）
    def within_family(spec):
        a = aggregate([dict(o, signal=valid_signal(o["signal"])) for o in spec])
        fam = [o["confidence"] for o in spec
               if FAMILY[valid_signal(o["signal"])] == FAMILY[a["final_signal"]]]
        return a["confidence"] <= max(fam, default=0.0)
    _check("agg conf <= family max", all(within_family(s) for s in (
        ops, ops_s, bear13, bear2, board(("buy", 0.8), ("sell", 0.8)),
        board(("strong_buy", 0.95), ("hold", 0.5), ("hold", 0.5), ("hold", 0.4))
    )), True)

    print("== 方向冲突 → low；veto 压 hold ==")
    # 初判须落买入族 veto 才触达：收缩 3+(0.95×2−0.8)/2=3.55 → buy
    ops4 = [
        {"source": "strategy:bull_trend", "signal": "strong_buy", "confidence": 0.95},
        {"source": "strategy:wave_theory", "signal": "sell", "confidence": 0.8},
    ]
    v4 = adjudicate(ops4, {"veto": True}, ev)
    _check("direction conflict", v4["aggregate"]["conflicts"][0]["type"],
           "direction_opposition")
    _check("consensus low", v4["aggregate"]["consensus_level"], "low")
    _check("veto reached (initial buy)", v4["risk_guard"]["initial"], "buy")
    _check("veto hold", v4["risk_guard"]["final"], "hold")
    # 高置信异见以聚合信号为锚：sell 0.8 与主信号 buy 隔 2 档 → medium
    _check("dissent anchored on agg", v4["aggregate"]["conflicts"][1],
           {"type": "high_conf_dissent", "severity": "medium"})
    _check("buckets", (v4["disagreement"]["buckets"]["bullish"],
                       v4["disagreement"]["buckets"]["bearish"]),
           (["strategy:bull_trend"], ["strategy:wave_theory"]))

    print("== RiskGuard 只降不升（高严重度两档） ==")
    v5 = adjudicate(ops_s, {"downgrade": True, "severity": "high"}, ev)
    _check("strong_buy -2 = hold", v5["risk_guard"]["final"], "hold")
    _check("buy -2 = sell", risk_guard("buy", downgrade=True, severity_high=True)[0],
           "sell")
    _check("veto only hits buy family", risk_guard("hold", veto=True)[0], "hold")
    _check("never upgrades sell", risk_guard("sell", downgrade=True)[0], "strong_sell")

    print("== RiskGuard veto+downgrade 同真（取更保守、单调收紧） ==")
    # downgrade(high) 单独已到 sell，加 veto 不得反被截停在 hold
    _check("buy+veto+downgrade(high)", risk_guard("buy", True, True, True),
           ("sell", "veto buy->hold; downgrade buy->sell; stricter=sell"))
    _check("strong_buy+veto+downgrade", risk_guard("strong_buy", True, True)[0], "hold")
    # 穷举五档 × veto/downgrade/severity_high：永不升级；任一风险输入 false→true 不更宽松
    flags = [(v, g, h) for v in (False, True) for g in (False, True) for h in (False, True)]
    rank = lambda d, f: LADDER.index(risk_guard(d, *f)[0])
    up = [(d, f) for d in LADDER for f in flags if rank(d, f) < LADDER.index(d)]
    flips = [(d, f, f[:k] + (True,) + f[k + 1:]) for d in LADDER for f in flags
             for k in range(3) if not f[k]]
    loose = [(d, f, g) for d, f, g in flips if rank(d, g) < rank(d, f)]
    _check("exhaustive never upgrades", (len(LADDER) * len(flags), up), (40, []))
    _check("exhaustive monotone", (len(flips), loose), (60, []))

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
    v6 = adjudicate(ops_s, {}, ev_bad)
    _check("cap low", v6["evidence_quality"]["confidence_cap"], "low")
    _check("tier limited", v6["evidence_quality"]["tier"], "limited")
    _check("strong pressed", v6["risk_guard"]["final"], "buy")
    _check("cap log", "confidence_cap" in v6["risk_guard"]["log"][1], True)

    print("== 破坏性实验（证明各机制不可拆） ==")
    # 拆验票门：无效信号（「看多!!!」当 strong_buy）与越界置信（7 当 buy）直进
    # 意见链的后果——过门时空头板 3−1.8/2=2.1 → sell；两条污染票直进后
    # 3+(1.9+7−1.8)/4=4.775 → strong_buy（越界置信 7 还会顶穿置信收缩）
    bear_ops = [{"source": "strategy:wave_theory", "signal": "sell", "confidence": 0.9},
                {"source": "strategy:chan_theory", "signal": "sell", "confidence": 0.9}]
    gated = adjudicate([{"source": "strategy:hot_theme", "signal": "看多!!!",
                         "confidence": 0.95},
                        {"source": "role:technical", "signal": "buy", "confidence": 7}]
                       + bear_ops, {}, ev)
    _check("E1 gated board stays bearish", gated["aggregate"]["final_signal"], "sell")
    polluted = aggregate([
        {"source": "strategy:hot_theme", "signal": "strong_buy", "confidence": 0.95},
        {"source": "role:technical", "signal": "buy", "confidence": 7}]
        + [dict(o) for o in bear_ops], {})
    _check("E1 no-partition pollution", polluted["final_signal"], "strong_buy")
    # 拆只降不升：允许升级的后果（直接演示被禁形态）
    _check("E2 upgrade forbidden by design", risk_guard("hold", downgrade=True)[0]
           in LADDER[LADDER.index("hold"):], True)
    # 拆置信帽：核心块降级仍放行 strong_*
    no_cap, _ = apply_confidence_cap("strong_buy", "high")
    _check("E3 no-cap keeps strong", (no_cap, apply_confidence_cap("strong_buy", "low")[0]),
           ("strong_buy", "buy"))
    # 拆零权重钉：扩展块状态任意变化不得扰动质量分/档位/置信帽
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
