#!/usr/bin/env python3
"""Stage B/C 汇总器：N 只 verdict × Stage A 因子 → midtier.jsonl（中 tier SSOT，
含 shortlisted 标记）+ midtier_table.md 可读视图 + 门限筛。

vibe-stock ≥0.2.1：直接消费 verdict.aggregate.final_signal（聚合已含信号
档位）；聚合分 score 按公式复算——verdict.aggregate 投影不含 score，以
verdict.valid_opinions 的 signal/confidence/weight（weight 即绩效因子）按
references/03-synthesis.md 同式复算，公式与 scripts/adjudicate.py 的
aggregate() 逐字同步（升版须同步）。中 tier 不跑 report 不登记信号。

用法（sk=skill 根目录）：
  uv run --no-project <sk>/batch/midtier.py --scan-root <scan_root> \\
    --skill-scripts <sk>/scripts [--shortlist-n 10]
"""
import argparse
import csv
import json
import os
import sys


def fnum(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load_adjudicate(skill_scripts):
    if skill_scripts not in sys.path:
        sys.path.insert(0, skill_scripts)
    import adjudicate as aj  # noqa: PLC0415
    return aj


def agg_score(aj, valid):
    """复算置信收缩加权分（与 adjudicate.aggregate() 同式）：
    score = 3 + Σ(绩效ᵢ×置信ᵢ×(档位值ᵢ−3)) / Σ绩效ᵢ，四位小数取整。
    valid 取自 verdict.valid_opinions（weight 已是绩效因子，不重算）。"""
    p = [o.get("weight", 1.0) or 1.0 for o in valid]
    if not valid or sum(p) == 0:
        return None
    return round(3 + sum(pi * o["confidence"] * (aj.LEVEL[o["signal"]] - 3)
                          for pi, o in zip(p, valid)) / sum(p), 4)


def bars_lo20hi20(evd):
    bars = ((evd.get("blocks", {}).get("daily_bars") or {}).get("bars")) or []
    closes = [b["close"] for b in bars if isinstance(b, dict) and b.get("close")]
    if not closes:
        return None, None
    w = closes[-20:]
    return round(min(w), 2), round(max(w), 2)


def load_universe(scan_root, top_n):
    u = {}
    with open(os.path.join(scan_root, "stageA", f"screen_top{top_n}.csv"),
              encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            u[r["code"].zfill(6)] = r
    return u


def main():
    ap = argparse.ArgumentParser(description="中 tier 汇总与门限筛（参考实现）")
    ap.add_argument("--scan-root", required=True, help="批量运行根目录")
    ap.add_argument("--top-n", type=int, default=30, help="Stage A 入选数（文件名拼接）")
    ap.add_argument("--skill-scripts", default=os.path.expanduser(
        "~/.claude/skills/vibe-stock/scripts"), help="skill scripts 目录")
    ap.add_argument("--shortlist-n", type=int, default=10, help="最终精选数")
    ap.add_argument("--g1-steps", default="3.2,3.0,2.8",
                    help="G1 方向门降档序列（逗号分隔，strict 之后逐档）")
    ap.add_argument("--min-pass", type=int, default=10,
                    help="G1 各档最少通过数（不足则如实交付不硬凑）")
    ap.add_argument("--budget", type=float, default=1e5, help="总预算（G5 价格门用）")
    ap.add_argument("--w-max", type=float, default=0.145, help="单仓权重上限")
    ap.add_argument("--max-price", type=float, default=None,
                    help="G5 价格上限；缺省按 w_max*budget/100（单手 100 股可配，与 Stage A 同式）")
    a = ap.parse_args()
    aj = load_adjudicate(a.skill_scripts)
    BUY = ("strong_buy", "buy")
    SELL = ("sell", "strong_sell")

    uni = load_universe(a.scan_root, a.top_n)
    rows = []
    for code in sorted(uni):
        d = os.path.join(a.scan_root, "vs", code)
        if not os.path.isfile(os.path.join(d, "verdict.json")):
            rows.append({"code": code, "excluded": "no_verdict"})
            continue
        with open(os.path.join(d, "verdict.json"), encoding="utf-8") as f:
            verdict = json.load(f)
        with open(os.path.join(d, "evidence.json"), encoding="utf-8") as f:
            evd = json.load(f)
        with open(os.path.join(d, "risk.json"), encoding="utf-8") as f:
            risk = json.load(f)
        with open(os.path.join(d, "opinions.json"), encoding="utf-8") as f:
            opinions = json.load(f)
        agg = verdict.get("aggregate") or {}
        rg = verdict.get("risk_guard") or {}
        eq = verdict.get("evidence_quality") or {}
        valid = verdict.get("valid_opinions") or []
        blocks = evd.get("blocks", {})
        val = blocks.get("valuation") or {}
        tech = blocks.get("technical") or {}
        lo20, hi20 = bars_lo20hi20(evd)
        price = fnum((blocks.get("quote") or {}).get("price")) or fnum(uni[code].get("price"))
        board = {"bull": 0, "bear": 0, "neutral": 0}
        for o in opinions:
            sg = o.get("signal")
            board["bull" if sg in BUY else "bear" if sg in SELL else "neutral"] += 1
        rows.append({
            "code": code, "name": uni[code]["name"], "industry": uni[code]["industry"],
            "composite_stageA": fnum(uni[code]["composite"]),
            "period_used": uni[code].get("period_used", ""),
            "price": price, "lo20": lo20, "hi20": hi20, "ma20": fnum(tech.get("ma20")),
            "initial": agg.get("final_signal"),          # 聚合初判（0.2.1 语义已修）
            "score": agg_score(aj, valid),               # 同式复算（见模块 docstring）
            "confidence": agg.get("confidence"),
            "consensus": agg.get("consensus_level"),
            "final": rg.get("final"),                    # RiskGuard+置信帽后终裁
            "n_valid": len(valid), "board": board,
            "evidence_tier": eq.get("tier"), "confidence_cap": eq.get("confidence_cap"),
            "quality_score": eq.get("score"),
            "risk": {"veto": bool(risk.get("veto")), "downgrade": bool(risk.get("downgrade")),
                     "severity": risk.get("severity")},
            "core_states": {k: (blocks.get(k) or {}).get("state", "missing")
                            for k in ("quote", "daily_bars", "technical")},
            "f_quality": fnum(uni[code].get("f_quality")), "f_growth": fnum(uni[code].get("f_growth")),
            "f_momentum": fnum(uni[code].get("f_momentum")), "pe_inv": fnum(uni[code].get("pe_inv")),
            "valuation": {k: val.get(k) for k in ("pe_ttm", "pb", "dividend_yield_ttm",
                                                  "pe_percentile_5y", "pb_percentile_5y")},
        })

    ok_rows = [r for r in rows if "excluded" not in r]
    # 股息率 rank（池内）
    dys = sorted([r["valuation"]["dividend_yield_ttm"] for r in ok_rows
                  if r["valuation"].get("dividend_yield_ttm") is not None])
    for r in ok_rows:
        dy = r["valuation"].get("dividend_yield_ttm")
        r["div_rank"] = (dys.index(dy) + 1) / len(dys) if dy is not None and dys else 0.3

    # R_sel（确定性排序分）
    for r in ok_rows:
        cs = r["score"]
        pe_norm = r["valuation"].get("pe_percentile_5y")
        pe_norm = pe_norm / 100 if pe_norm is not None else \
            (r["pe_inv"] if r["pe_inv"] is not None else 0.5)
        r["pe_norm_src"] = "baidu_5y" if r["valuation"].get("pe_percentile_5y") \
            is not None else "stageA_rank"
        dg = 0.5 if r["risk"]["downgrade"] else 1.0
        r["R_sel"] = round(
            0.40 * ((cs - 2.5) / 2.5 if cs is not None else 0)
            + 0.20 * (0.5 * (r["f_quality"] or 0.3) + 0.5 * (r["f_growth"] or 0.3))
            + 0.15 * (0.5 * (1 - pe_norm) + 0.5 * r["div_rank"])
            + 0.15 * dg
            + 0.10 * (r["f_momentum"] if r["f_momentum"] is not None else 0.3), 4)

    # 门限筛 G2-G5 → G1 逐档（不足 min_pass 如实交付不硬凑）
    max_price = a.max_price if a.max_price is not None else a.w_max * a.budget / 100.0

    def base_gates(r):
        if r["risk"]["veto"]:
            return "G2_veto"
        if r["evidence_tier"] not in ("good", "usable") or r["confidence_cap"] != "high":
            return f"G3_tier_{r['evidence_tier']}_{r['confidence_cap']}"
        bad_core = [k for k, v in r["core_states"].items()
                    if v not in ("available", "fallback")]
        if bad_core:
            return f"G4_core_{bad_core}"
        if r["price"] and r["price"] > max_price:
            return "G5_price"
        return None

    g1_steps = [("strict", lambda r: r["initial"] in BUY)]
    for th in [float(x) for x in a.g1_steps.split(",")]:
        g1_steps.append((f"score>={th}",
                         (lambda t: lambda r: (r["score"] or 0) >= t
                          and r["final"] not in SELL)(th)))
    gated = []
    for r in ok_rows:
        bg = base_gates(r)
        r["gate_fail"] = bg if bg else None
        if not bg:
            gated.append(r)
    chosen_step = None
    for step_name, pred in g1_steps:
        if len([r for r in gated if pred(r)]) >= a.min_pass:
            chosen_step = step_name
            break
    if chosen_step is None:
        chosen_step = g1_steps[-1][0]  # 兜底取最宽档，如实记录通过数不足
    for r in gated:
        if not dict(g1_steps)[chosen_step](r):
            r["gate_fail"] = f"G1_not_{chosen_step}"

    passed = [r for r in gated if not r["gate_fail"]]
    passed.sort(key=lambda r: -r["R_sel"])
    # 行业 ≤2 greedy 选最终 N
    sel, cnt, skipped_ind = [], {}, []
    for r in passed:
        ind = r["industry"]
        if cnt.get(ind, 0) >= 2:
            skipped_ind.append({"code": r["code"], "industry": ind, "R_sel": r["R_sel"]})
            continue
        sel.append(r)
        cnt[ind] = cnt.get(ind, 0) + 1
        if len(sel) == a.shortlist_n:
            break

    # ---- 输出（midtier.jsonl 是中 tier 唯一事实源，shortlisted 标记入选）----
    sel_codes = {r["code"] for r in sel}
    for r in rows:
        r["shortlisted"] = r["code"] in sel_codes
    with open(os.path.join(a.scan_root, "midtier.jsonl"), "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    lines = [f"# 中 tier 汇总（{len(ok_rows)} 只，vibe-stock ≥0.2.1 管线口径）", "",
             "| code | 名称 | 行业 | 初判 | 终裁 | 聚合分 | 板面B/H/S | tier | R_sel | 门限 |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for r in sorted(ok_rows, key=lambda x: -(x["R_sel"] or 0)):
        lines.append(f"| {r['code']} | {r['name']} | {r['industry']} | {r['initial']} "
                     f"| {r['final']} | {r['score']} "
                     f"| {r['board']['bull']}/{r['board']['neutral']}/{r['board']['bear']} "
                     f"| {r['evidence_tier']} | {r['R_sel']} | {r['gate_fail'] or 'PASS'} |")
    lines += [f"",
              f"- G1 采用档位：{chosen_step}；门限通过 {len(passed)}（--min-pass "
              f"{a.min_pass}，不足即如实交付不硬凑）；行业帽挤出 {skipped_ind}",
              f"- 最终 shortlist：{[r['code'] for r in sel]}（{len(sel)} 只；"
              f"登记走 scan_prepare.py --register）"]
    with open(os.path.join(a.scan_root, "midtier_table.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"OK midtier:{len(ok_rows)} ok, passed {len(passed)}, shortlist {len(sel)}: "
          f"{[r['code'] for r in sel]}")
    print(f"G1 step: {chosen_step}; gate_fails: "
          f"{ {r['code']: r['gate_fail'] for r in ok_rows if r['gate_fail']} }")


if __name__ == "__main__":
    main()
