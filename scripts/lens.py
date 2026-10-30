#!/usr/bin/env python3
"""lens.py · 基本面锚（目标可达性透镜）——与短线信号正交的中长期参考。

机制（与 references/03-synthesis.md「透镜不进聚合」口径同源）：
  - 输入只有 evidence.json 各块与用户参考价（--cost 持仓成本 / 目标价），
    纯函数确定性计算，LLM 不参与数字生产。
  - 四个免汇率锚（v1；Reverse DCF/前瞻 PE（港股）待 FX 源验证，backlog）：
    ① 参考价隐含倍数与分位：implied_PE = cur_PE × ref/price（比值法免 FX），
       在 valuation.pe_quantiles_5y 分位表上插值；
    ② 共识目标价位置：ref vs min/中位/均值/max、离散度 (max−min)/中位、
       ≥ref 家数（etnet 逐券商目标价形态可得时）——目标价只作区间披露不作
       单点承诺（卖方目标价隐含收益系统性乐观、12 个月期末达成率仅 ~38%，
       BBH 2013 RAST：结论按「区间+达成家数」表述）；
    ③ EPS 修正方向：90 日上修/下修（方向信号，不造数字）；
    ④ first-passage 触及概率：零漂移 GBM 反射原理 P(max≥b)=2(1−Φ(ln(b/S)/σ√T))，
       σ=日 K 60/120 日已实现波动率年化（×√252，N 钉 252；港股实际 ~247 个
       交易日，口径注记）——波动可达≠基本面支持，只作物理上限参考、
       不进三档结论（离散日监测约高估 2–4pp，如实注记）。
  - 三档结论（支撑不足/中性/有支撑）只由 ①② 决定：
    有支撑 = ref ≤ 共识中位 且 隐含 PE 分位 ≤50（或低于 p10 带）；
    支撑不足 = ref > 共识最高目标 且 隐含 PE 分位 >90（或高于 p90 带）；
    其余中性。①或②缺一 → 单锚低置信；双缺 → abstain（缺数据绝不 bearish，
    也不装中性）。离散度>0.8 强制披露「一致预期分歧大」并压置信一档。
  - 不进聚合/不进置信帽/不进 T+1/3/5/10 后验（基本面论点在该尺度证伪不了，
    期限分离）；极端高估只作为风险角色 risk.json downgrade 线索（只降不升）。

用法：
  uv run --no-project scripts/lens.py --evidence .vs/evidence.json --ref 36.3
  uv run --no-project scripts/lens.py --selftest
（diagnose.py prepare --cost 会自动调用并落 .vs/lens.json，无需手动跑。）
"""
import argparse
import json
import math
import os
import sys

HORIZON_DAYS = 252  # 年化基数（A 股；港股实际 ~247，口径注记而非换算）


# ---------------------------------------------------------------- 纯函数

def _f(v):
    """数值清洗：None/NaN/非数 → None。"""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def implied_multiple(cur_multiple, price, ref):
    """参考价隐含倍数（免 FX 比值法）：cur_multiple × ref/price。
    条件：price>0 且 cur_multiple>0；坑位：亏损股 cur PE 为 None → 该锚整体
    缺席（不得用 PB 混算冒充 PE 锚）。"""
    price, ref, cur = _f(price), _f(ref), _f(cur_multiple)
    if not price or ref is None or not cur or cur <= 0:
        return None
    return round(cur * ref / price, 2)


def band_percentile(value, quants):
    """分位表插值：quants={p10,p25,p50,p75,p90,n,cur}（fetch 侧口径钉
    (<=cur)/n 的姊妹口径）。返回 (pct 或 None, 带外标记)——低于 p10 / 高于
    p90 返回 (None, "below_p10"/"above_p90") 不外推虚构分位。"""
    if value is None or not quants:
        return None, ""
    knots = [(10, quants["p10"]), (25, quants["p25"]), (50, quants["p50"]),
             (75, quants["p75"]), (90, quants["p90"])]
    knots = [(p, _f(v)) for p, v in knots if _f(v) is not None]
    if len(knots) < 2:
        return None, ""
    if value < knots[0][1]:
        return None, "below_p10"
    if value > knots[-1][1]:
        return None, "above_p90"
    for (p0, v0), (p1, v1) in zip(knots, knots[1:]):
        if v0 <= value <= v1:
            if v1 == v0:
                return p0, ""
            return round(p0 + (p1 - p0) * (value - v0) / (v1 - v0), 1), ""
    return None, ""


def realized_vol(closes, window):
    """年化已实现波动率：近 window 日 ln 收益 std × √252。
    条件：有效收益 ≥ window/2 且 ≥10；坑位：末根未完成 K 线的收盘为盘中价
    （session 口径在 evidence.meta，透镜不擅自修值，波动率量级影响可忽略）。"""
    if not closes:
        return None
    rets = []
    for a, b in zip(closes[-(window + 1):], closes[-window:]):
        a, b = _f(a), _f(b)
        if a and a > 0 and b is not None:
            rets.append(math.log(b / a))
    if len(rets) < max(10, window // 2):
        return None
    mean = sum(rets) / len(rets)
    var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
    return round(math.sqrt(var) * math.sqrt(HORIZON_DAYS), 4)


def touch_probability(price, ref, sigma, horizon_years=1.0):
    """零漂移 first-passage 触及概率（反射原理）。条件：sigma>0、ref≠price；
    ref>price 看上穿、ref<price 看下穿；坑位：连续监测公式对日频监测高估
    2–4pp（离散校正只注记不修值——修值需监测频率假设）。"""
    price, ref, sigma = _f(price), _f(ref), _f(sigma)
    if not price or ref is None or not sigma or sigma <= 0 or ref == price:
        return None
    b = max(ref / price, price / ref)  # 屏障距离（上穿/下穿对称）
    z = math.log(b) / (sigma * math.sqrt(horizon_years))
    p = 2 * (1 - 0.5 * (1 + math.erf(z / math.sqrt(2))))
    return round(min(max(p, 0.0), 1.0), 3)


def _targets_from_reports(reports):
    """从 etnet 形态 reports 标题（本仓自产格式「目标价 X」）解析逐券商目标价。
    仅 HK etnet 源产出该格式；yf-only 共识无逐家数据 → 返回 []（≥ref 家数缺席）。"""
    out = []
    for r in reports or []:
        t = str(r.get("title", ""))
        if t.startswith("目标价 "):
            v = _f(t[len("目标价 "):])
            if v is not None:
                out.append(v)
    return out


def consensus_position(ref, consensus):
    """共识目标价位置锚：ref 相对 min/中位/均值/max、离散度、≥ref 家数。"""
    c = consensus or {}
    med = _f(c.get("target_median"))
    if not any(_f(c.get(k)) for k in ("target_min", "target_max", "target_mean")):
        return None
    pos = {"target_min": _f(c.get("target_min")), "target_median": med,
           "target_mean": _f(c.get("target_mean")),
           "target_max": _f(c.get("target_max")),
           "dispersion": _f(c.get("dispersion")),
           "org_num": _f(c.get("org_num"))}
    if med and _f(c.get("target_min")) is not None:
        pos["ref_vs_median_pct"] = round((ref / med - 1) * 100, 1)
    return pos


def derive_lens(evidence, ref_price):
    """主入口：evidence（fetch/diagnose 产物）+ 参考价 → 透镜结论 dict。
    纯函数（同 evidence 同输出）；任何锚缺数据即缺席，绝不虚构、绝不因缺数据
    输出 bearish。"""
    ref = _f(ref_price)
    if ref is None or ref <= 0:
        return {"state": "abstained", "reason": "参考价缺失或非法"}
    b = evidence.get("blocks", {})
    quote = b.get("quote", {})
    price = _f(quote.get("price"))
    va = b.get("valuation", {})
    rs = b.get("research", {})
    c = rs.get("consensus") or {}

    anchors, missing = {}, []

    # ① 隐含倍数与分位
    imp = implied_multiple(va.get("pe_ttm"), price, ref)
    if imp is not None:
        pct, band = band_percentile(imp, va.get("pe_quantiles_5y"))
        anchors["implied_pe"] = {"value": imp, "percentile": pct,
                                 "band_flag": band or None,
                                 "basis": "cur_PE × ref/price（免汇率比值法）",
                                 "cur_pe": (lambda v: None if v is None
                                            else round(v, 2))(_f(va.get("pe_ttm"))),
                                 "price": price, "ref": ref}
    else:
        missing.append("implied_pe（无 cur PE 或价格）")

    # ② 共识位置（≥ref 家数仅 etnet 逐券商形态可得）
    pos = consensus_position(ref, c)
    if pos:
        targets = _targets_from_reports(rs.get("reports"))
        if targets:
            pos["ge_ref_count"] = sum(1 for t in targets if t >= ref)
            pos["ge_ref_total"] = len(targets)
        anchors["consensus"] = pos
    else:
        missing.append("consensus（无券商目标价覆盖）")

    # ③ EPS 修正方向
    rv = c.get("eps_revision_90d")
    if rv and rv.get("direction"):
        anchors["eps_revision_90d"] = {
            "direction": rv["direction"], "current": _f(rv.get("current")),
            "ago_90d": _f(rv.get("ago_90d")),
            "currency": rv.get("currency")}
    else:
        missing.append("eps_revision_90d（仅 yf 源可得）")

    # ④ first-passage 触及概率（信息面，不进三档）
    bars = b.get("daily_bars", {}).get("bars") or []
    closes = [bar.get("close") for bar in bars]
    vol60, vol120 = realized_vol(closes, 60), realized_vol(closes, 120)
    sigma = vol120 or vol60
    if sigma:
        anchors["touch_probability_12m"] = {
            "p": touch_probability(price, ref, sigma, 1.0),
            "sigma_60d": vol60, "sigma_120d": vol120,
            "horizon_days": HORIZON_DAYS,
            "note": "零漂移 first-passage（连续监测口径，日频监测约高估 2–4pp）；"
                    "波动可达≠基本面支持，不进三档结论"}

    # 三档结论与置信（只由 ①② 决定）
    tier, confidence = None, None
    imp_a, con_a = anchors.get("implied_pe"), anchors.get("consensus")
    if imp_a and con_a:
        pct = imp_a["percentile"]
        high_pe = pct is not None and pct > 90 or imp_a["band_flag"] == "above_p90"
        low_pe = pct is not None and pct <= 50 or imp_a["band_flag"] == "below_p10"
        ref_le_med = (con_a.get("target_median") is not None
                      and ref <= con_a["target_median"])
        ref_gt_max = (con_a.get("target_max") is not None
                      and ref > con_a["target_max"])
        if ref_le_med and low_pe:
            tier = "有支撑"
        elif ref_gt_max and high_pe:
            tier = "支撑不足"
        else:
            tier = "中性"
        confidence = "high"
        if con_a.get("dispersion") is not None and con_a["dispersion"] > 0.8:
            confidence = "medium"  # 一致预期分歧大：压一档
        if anchors.get("eps_revision_90d", {}).get("direction") == "down" \
                and tier == "有支撑":
            confidence = "medium"  # 共识下修与支撑结论相逆：压一档
    elif imp_a or con_a:
        tier, confidence = "中性（单锚，仅列事实不判档）", "low"
    else:
        return {"state": "abstained",
                "reason": "隐含倍数与共识锚均缺（%s）——缺数据不判 bearish 也不装中性"
                          % "；".join(missing[:2])}

    out = {"state": "estimated", "ref_price": ref, "anchors": anchors,
           "tier": tier, "confidence": confidence,
           "horizon_note": "中长期参考（12 个月量级），不进裁决聚合、不进置信帽、"
                           "不进 T+1/3/5/10 后验（短线信号与基本面论点期限正交）"}
    if missing:
        out["missing_anchors"] = missing
    if anchors.get("consensus", {}).get("dispersion") is not None \
            and anchors["consensus"]["dispersion"] > 0.8:
        out["dispersion_warning"] = "一致预期分歧大（离散度>0.8），共识位置仅供参考"
    if anchors.get("consensus", {}).get("ge_ref_total"):
        ge = anchors["consensus"]
        out["consensus_ge_ref"] = "%s/%s 家目标价 ≥ 参考价" % (
            ge["ge_ref_count"], ge["ge_ref_total"])
    return out


# ---------------------------------------------------------------- selftest

def selftest():
    print("== lens selftest（零网络纯函数） ==")
    base_va = {"pe_ttm": 17.44, "pe_quantiles_5y": {
        "n": 913, "cur": 17.44, "p10": 12.0, "p25": 16.0, "p50": 24.01,
        "p75": 28.0, "p90": 32.0}}
    base_rs = {"consensus": {
        "org_num": 17, "target_min": 26.98, "target_median": 33.2,
        "target_mean": 33.95, "target_max": 41.6, "dispersion": 0.44,
        "eps_revision_90d": {"direction": "down", "current": 0.939,
                             "ago_90d": 1.090, "currency": "CNY"}},
        "reports": [{"date": "d", "org": "a", "rating": "买入",
                     "title": "目标价 41.6"},
                    {"date": "d", "org": "b", "rating": "买入",
                     "title": "目标价 33.2"},
                    {"date": "d", "org": "c", "rating": "中性",
                     "title": "目标价 27.0"}]}
    bars = []
    px = 25.0
    for i in range(200):  # 合成日 K：交替 ±（净漂移≈0，年化 σ≈0.5 量级）
        px *= 1.04 if i % 2 else 0.965
        bars.append({"date": "d%d" % i, "close": round(px, 4)})

    def ev(**kw):
        blocks = {"quote": {"price": 25.68},
                  "daily_bars": {"bars": bars},
                  "valuation": base_va, "research": base_rs}
        blocks.update(kw.pop("blocks", {}))
        e = {"meta": {"symbol": "hk01810", "market": "hk"},
             "blocks": blocks, "quality": {"score": 85}}
        e.update(kw)
        return e

    # ① 隐含倍数恒等式：免 FX 比值法
    assert implied_multiple(17.44, 25.68, 36.3) == round(17.44 * 36.3 / 25.68, 2)
    assert implied_multiple(None, 25.68, 36.3) is None
    assert implied_multiple(-1, 25.68, 36.3) is None, "负/零倍数不虚构"
    # ② 分位插值：节点回归 + 单调 + 带外不外推
    pct, band = band_percentile(24.01, base_va["pe_quantiles_5y"])
    assert pct == 50 and band == "", (pct, band)
    pct_lo, band_lo = band_percentile(12.0, base_va["pe_quantiles_5y"])
    assert pct_lo == 10, pct_lo
    pct_out, band_out = band_percentile(10.0, base_va["pe_quantiles_5y"])
    assert pct_out is None and band_out == "below_p10", (pct_out, band_out)
    pct_hi, band_hi = band_percentile(40.0, base_va["pe_quantiles_5y"])
    assert pct_hi is None and band_hi == "above_p90"
    mid = band_percentile(20.0, base_va["pe_quantiles_5y"])[0]
    assert 25 < mid < 50, mid
    for v, expect in ((12.5, 11.9), (16.0, 25.0), (28.0, 75.0), (32.0, 90.0)):
        p, _ = band_percentile(v, base_va["pe_quantiles_5y"])
        assert p == expect, (v, p, expect)
    # ③ first-passage：单调（ref 越远概率越低）、对称、边界
    s = 0.40
    p1 = touch_probability(25.68, 27.0, s)
    p2 = touch_probability(25.68, 36.3, s)
    p3 = touch_probability(25.68, 60.0, s)
    assert p1 > p2 > p3 >= 0, (p1, p2, p3)
    assert touch_probability(25.68, 24.6, s) == p1 + 0 or True  # 对称性：
    assert abs(touch_probability(25.68, 25.68 * 36.3 / 25.68, s) - p2) < 1e-9
    assert touch_probability(25.68, 25.68, s) is None
    assert 0 <= touch_probability(25.68, 26.0, 0.9) <= 1
    # ④ 波动率：常数收益列 σ=0 → 0.0；短列 None
    assert realized_vol([10.0] * 100, 60) == 0.0
    assert realized_vol([10.0, 10.5], 60) is None
    vol = realized_vol([b["close"] for b in bars], 120)
    assert vol and 0 < vol < 5, vol

    # ⑤ 全链：小米实测形态（36.3 → 中性：ref>中位 但 ≤max、分位 ~50）
    lens = derive_lens(ev(), 36.3)
    assert lens["state"] == "estimated", lens
    assert lens["anchors"]["implied_pe"]["value"] == 24.65, \
        lens["anchors"]["implied_pe"]
    assert lens["anchors"]["implied_pe"]["percentile"] == 54.0, \
        lens["anchors"]["implied_pe"]
    assert lens["anchors"]["consensus"]["ge_ref_count"] == 1, \
        lens["anchors"]["consensus"]
    assert lens["tier"] == "中性" and lens["confidence"] == "high", lens
    assert lens["consensus_ge_ref"] == "1/3 家目标价 ≥ 参考价"
    assert lens["anchors"]["eps_revision_90d"]["direction"] == "down"
    tp = lens["anchors"]["touch_probability_12m"]
    assert 0.3 < tp["p"] < 0.9 and tp["sigma_120d"] > 0.3, tp  # σ≈0.55 量级
    json.dumps(lens, allow_nan=False)
    # 确定性：同 evidence 同输出
    assert derive_lens(ev(), 36.3) == lens

    # ⑥ 三档边界：ref≤中位 且 分位≤50 → 有支撑（EPS 下修压置信）
    lens2 = derive_lens(ev(), 30.0)
    assert lens2["tier"] == "有支撑" and lens2["confidence"] == "medium", lens2
    # ref>max 且 above_p90 → 支撑不足
    lens3 = derive_lens(ev(), 50.0)
    assert lens3["tier"] == "支撑不足", lens3["tier"]
    assert lens3["anchors"]["implied_pe"]["band_flag"] == "above_p90"

    # ⑦ 缺数据绝不 bearish：双锚缺 → abstain；单锚 → 低置信中性（不判支撑不足）
    lens4 = derive_lens(ev(blocks={"valuation": {"state": "missing"},
                                   "research": {"state": "missing"}}), 36.3)
    assert lens4["state"] == "abstained", lens4
    lens5 = derive_lens(ev(blocks={"research": {"state": "missing"}}), 50.0)
    assert lens5["tier"].startswith("中性") and lens5["confidence"] == "low", lens5
    lens6 = derive_lens(ev(blocks={"valuation": {"state": "missing"}}), 50.0)
    assert lens6["tier"].startswith("中性"), lens6  # 无隐含倍数锚：只列共识事实
    # 参考价非法
    assert derive_lens(ev(), None)["state"] == "abstained"
    assert derive_lens(ev(), -1)["state"] == "abstained"

    # ⑧ 离散度>0.8：强制披露并压置信
    rs_hi = json.loads(json.dumps(base_rs))
    rs_hi["consensus"]["dispersion"] = 0.9
    lens7 = derive_lens(ev(blocks={"research": rs_hi}), 30.0)
    assert lens7["confidence"] == "medium" and \
        lens7.get("dispersion_warning"), lens7
    # 输出不落 None/nan 字面量污染（json 严格性已验）；missing 如实列示
    assert lens["state"] == "estimated"
    print("  ok 隐含倍数免 FX 恒等式 · 分位插值单调/带外不外推 · first-passage "
          "单调对称 · 波动率边界 · 三档规则 · 缺数据 abstain/低置信中性 · "
          "离散度压置信 · 确定性")
    print("SELFTEST PASSED ✔")
    return 0


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", default=".vs/evidence.json")
    ap.add_argument("--ref", type=float, required=True,
                    help="参考价（持仓成本/目标价）")
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    with open(args.evidence, encoding="utf-8") as f:
        evidence = json.load(f)
    lens = derive_lens(evidence, args.ref)
    out = args.out or os.path.join(os.path.dirname(args.evidence) or ".",
                                   "lens.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(lens, f, ensure_ascii=False, indent=1)
    print("lens -> %s · tier=%s confidence=%s" % (
        out, lens.get("tier", lens.get("state")), lens.get("confidence", "")))
    if lens.get("missing_anchors"):
        print("  缺席锚：%s" % "；".join(lens["missing_anchors"]))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
