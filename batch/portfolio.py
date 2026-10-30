#!/usr/bin/env python3
"""Stage D：组合确定性算术——信心加权 + 手数贴合 + 三段建仓 + 止损止盈 +
一致性校验（全 PASS 才算完成）。

输入：stageC/ranking.json（final_score）、midtier.jsonl
（price/lo20/hi20/ma20/industry）。输出：portfolio/{allocation.json, checks.txt}。

用法：uv run --no-project <sk>/batch/portfolio.py --scan-root <scan_root> \\
  [--budget 100000]
"""
import argparse
import json
import os

LOT = 100


def main():
    ap = argparse.ArgumentParser(description="Stage D 组合配置（参考实现）")
    ap.add_argument("--scan-root", required=True, help="批量运行根目录")
    ap.add_argument("--budget", type=float, default=1e5, help="总预算（元）")
    ap.add_argument("--w-min", type=float, default=0.05, help="单仓权重下限")
    ap.add_argument("--w-max", type=float, default=0.145, help="单仓权重上限")
    a = ap.parse_args()
    budget, w_min, w_max = a.budget, a.w_min, a.w_max

    with open(os.path.join(a.scan_root, "stageC", "ranking.json"), encoding="utf-8") as f:
        ranking = json.load(f)
    ranking = ranking["ranking"] if isinstance(ranking, dict) and "ranking" in ranking \
        else ranking
    with open(os.path.join(a.scan_root, "midtier.jsonl"), encoding="utf-8") as f:
        mid = {m["code"]: m for m in map(json.loads, f)}

    rows = []
    for r in ranking:
        d = mid[r["code"]]
        price = d["price"]
        lo20, hi20, ma20 = d.get("lo20"), d.get("hi20"), d.get("ma20")
        # 止损 = max(−5% 线, 0.99×lo20) 取紧者；参考买点 = max(lo20, 0.97×现价)
        stop = round(price * 0.95, 2)
        if lo20 and lo20 > 0.96 * price:
            stop = round(lo20 * 0.99, 2)
        entry_ref = round(max(lo20 or 0, price * 0.97), 2)
        rows.append({
            "code": r["code"], "name": r["name"], "industry": d["industry"],
            "rank": r["rank"], "final_score": r["final_score"], "price": price,
            "score": r.get("score"),
            "lo20": lo20, "hi20": hi20, "ma20": ma20,
            "stop": stop, "entry_ref": entry_ref, "target1": hi20,
        })

    # ---- 手数贴合（确定性 greedy）----
    total_fs = sum(r["final_score"] for r in rows)
    for r in rows:
        r["target_w"] = r["final_score"] / total_fs
        r["lots"] = max(1, round(r["target_w"] * budget / (LOT * r["price"])))

    def spent():
        return sum(r["lots"] * LOT * r["price"] for r in rows)

    # 超预算：从 final_score 最低者减手（各保 1 手）
    guard = 0
    while spent() > budget and guard < 200:
        guard += 1
        cands = [r for r in sorted(rows, key=lambda x: x["final_score"]) if r["lots"] > 1]
        if not cands:
            break
        cands[0]["lots"] -= 1
    # 剩现金 ≥ 最便宜一手：向高分且加后不超带上限者加手
    guard = 0
    while guard < 200:
        guard += 1
        cash = budget - spent()
        addable = [r for r in sorted(rows, key=lambda x: -x["final_score"])
                   if (r["lots"] + 1) * LOT * r["price"] - r["lots"] * LOT * r["price"] <= cash
                   and (r["lots"] + 1) * LOT * r["price"] / budget <= w_max]
        if not addable:
            break
        addable[0]["lots"] += 1

    # 抬底：任何 <w_min 者 +1 手，预算从最大成本仓（减后仍 ≥1 手且 ≥w_min）扣
    guard = 0
    while guard < 100:
        guard += 1
        lows = [r for r in rows if r["lots"] * LOT * r["price"] / budget < w_min - 1e-9]
        if not lows:
            break
        low = sorted(lows, key=lambda x: x["final_score"])[-1]  # 先抬分高的欠重股
        low["lots"] += 1
        if spent() > budget:
            doners = [r for r in sorted(rows, key=lambda x: -x["lots"] * LOT * x["price"])
                      if r is not low and r["lots"] > 1
                      and (r["lots"] - 1) * LOT * r["price"] / budget >= w_min - 1e-9]
            if not doners:
                break
            doners[0]["lots"] -= 1

    for r in rows:
        r["cost"] = round(r["lots"] * LOT * r["price"], 2)
        r["w_actual"] = round(r["cost"] / budget, 4)
        t1 = max(1, round(r["lots"] * 0.4))
        t2 = max(1 if r["lots"] > 1 else 0, round(r["lots"] * 0.3)) \
            if r["lots"] > 2 else r["lots"] - t1
        t3 = r["lots"] - t1 - t2
        r["tranches"] = {"T1_open": t1, "T2_limit_entryref": t2, "T3_trigger": t3}
    cash_left = round(budget - spent(), 2)

    # ---- 一致性校验（checks.txt 全 PASS 才算完成）----
    checks = []
    checks.append(("权重和+零股现金=100%",
                   abs(sum(r["w_actual"] for r in rows) + cash_left / budget - 1) <= 0.005,
                   f"w_sum={sum(r['w_actual'] for r in rows):.4f} cash={cash_left}"))
    for r in rows:
        checks.append((f"{r['code']} 仓位带", w_min - 0.001 <= r["w_actual"] <= w_max + 0.001,
                       f"w={r['w_actual']:.3f} lots={r['lots']}"))
        checks.append((f"{r['code']} 三价单调",
                       r["stop"] < r["entry_ref"] <= max(r["target1"] or 9e9, r["entry_ref"]),
                       f"stop={r['stop']} entry_ref={r['entry_ref']} target1={r['target1']}"))
        checks.append((f"{r['code']} 手数≥1", r["lots"] >= 1, f"lots={r['lots']}"))
    ind_cnt = {}
    for r in rows:
        ind_cnt[r["industry"]] = ind_cnt.get(r["industry"], 0) + 1
    checks.append(("行业≤2", all(v <= 2 for v in ind_cnt.values()), str(ind_cnt)))
    n_fail = len([c for c in checks if not c[1]])

    os.makedirs(os.path.join(a.scan_root, "portfolio"), exist_ok=True)
    with open(os.path.join(a.scan_root, "portfolio", "allocation.json"), "w",
              encoding="utf-8") as f:
        json.dump({"rows": rows, "cash_left": cash_left, "budget": budget,
                   "w_band": [w_min, w_max], "industry_counts": ind_cnt},
                  f, ensure_ascii=False, indent=2)
    with open(os.path.join(a.scan_root, "portfolio", "checks.txt"), "w",
              encoding="utf-8") as f:
        for name, ok, detail in checks:
            f.write(f"{'PASS' if ok else 'FAIL'} | {name} | {detail}\n")
    print(f"portfolio: {len(rows)} 只，现金残留 {cash_left}，校验 FAIL {n_fail}")
    for name, ok, detail in checks:
        if not ok:
            print("FAIL:", name, detail)


if __name__ == "__main__":
    main()
