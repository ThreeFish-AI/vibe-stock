#!/usr/bin/env python3
"""深评输入摘要（按需派生，不落盘）：midtier.jsonl 一行 + vs/<code>/ 证据与意见
+ Stage A 财务因子 → stdout JSON。对抗核验与三 lens 评审 agent 的统一读面。

用法：uv run --no-project <sk>/batch/digest.py --scan-root <scan_root> <code>
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from midtier import fnum, load_universe  # noqa: E402

EXT = ("moneyflow", "notices", "research", "forecast", "unlock", "holder", "market", "industry")
TECH = ("rsi14", "macd", "vol_ratio_5", "pct_from_52w_high", "pct_from_52w_low",
        "new_high_20d", "box_60d")
FIN = ("roe_ann_est", "np_yoy", "rev_yoy", "gpm", "eps", "pe_used", "pb_used")


def trunc(obj, n=700):
    s = json.dumps(obj, ensure_ascii=False, default=str)
    return s[:n] + ("…[截断]" if len(s) > n else "")


def build(scan_root, top_n, code):
    with open(os.path.join(scan_root, "midtier.jsonl"), encoding="utf-8") as f:
        row = next(r for r in map(json.loads, f) if r["code"] == code)
    d = os.path.join(scan_root, "vs", code)
    with open(os.path.join(d, "evidence.json"), encoding="utf-8") as f:
        blocks = json.load(f).get("blocks", {})
    with open(os.path.join(d, "opinions.json"), encoding="utf-8") as f:
        opinions = json.load(f)
    uni = load_universe(scan_root, top_n)[code]

    def side(signals):
        return sorted((o for o in opinions if o.get("signal") in signals),
                      key=lambda o: -o.get("confidence", 0))[:3]

    out = {k: v for k, v in row.items() if k != "shortlisted"}
    out["financials"] = {k: fnum(uni.get(k)) for k in FIN}
    out["tech"] = {k: (blocks.get("technical") or {}).get(k) for k in TECH}
    out["top_bull_rationales"] = side(("strong_buy", "buy"))
    out["top_bear_rationales"] = side(("sell", "strong_sell"))
    out["ext_blocks_truncated"] = {n: trunc(blocks.get(n) or {}) for n in EXT}
    return out


def main():
    ap = argparse.ArgumentParser(description="深评输入摘要（stdout，不落盘）")
    ap.add_argument("--scan-root", required=True, help="批量运行根目录")
    ap.add_argument("--top-n", type=int, default=30, help="Stage A 入选数（文件名拼接）")
    ap.add_argument("code", help="股票代码（6 位）")
    a = ap.parse_args()
    print(json.dumps(build(a.scan_root, a.top_n, a.code), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
