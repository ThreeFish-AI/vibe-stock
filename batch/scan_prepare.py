#!/usr/bin/env python3
"""Stage B 取数驱动器 + shortlist 登记器（批量子技能参考实现）。

默认模式：对 Stage A 入选股**串行**跑 skill 的 diagnose.py prepare（波次+股间
间隔+波后健康门+retry 波一次）。正确性依据（无条件全局规则）：fetch() 对
fetch_state.json 是整体 load-modify-save，并发互踩熔断账本——取数必须串行。
--register 模式：对 midtier.jsonl 中 shortlisted 的股票逐只跑 diagnose.py
report（个股报告 + signals.json 登记）；当日已登记（signals.json 已有该
code 当日记录）复用不重跑，防同日重复 signal。

用法（sk=skill 根目录；scan_root=批量运行根目录）：
  uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \\
    <sk>/batch/scan_prepare.py --scan-root ~/.vibe-stock/reports/_scans/<date>-<pool> \\
    --skill-dir <sk>
  uv run --no-project <sk>/batch/scan_prepare.py --scan-root <scan_root> \\
    --skill-dir <sk> --register        # Stage C 后登记 shortlist
退出码：0 全成功或如实记录失败；2 = 无任何成功股票。
"""
import argparse
import csv
import datetime as dt
import json
import os
import random
import subprocess
import sys
import time

FETCH_STATE = os.path.expanduser("~/.vibe-stock/fetch_state.json")
SIGNALS = os.path.expanduser("~/.vibe-stock/signals.json")
WAVE = 6
STOCK_GAP = (8, 12)


def run_prepare(skill_dir, scan_root, code):
    wd = os.path.join(scan_root, "vs", code)
    os.makedirs(wd, exist_ok=True)
    cmd = ["uv", "run", "--no-project", "--with", "akshare==1.20.*", "--with", "efinance",
           "--with", "yfinance", os.path.join(skill_dir, "scripts", "diagnose.py"),
           "prepare", "--stock", code, "--workdir", wd]
    t0 = time.time()
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=240)
    except subprocess.TimeoutExpired:  # 单股超时按失败记账继续，不炸整个驱动器
        return {"code": code, "ok": False, "rc": "timeout", "bars": "no_evidence",
                "dur_s": round(time.time() - t0, 1), "tail": "timeout after 240s"}
    dur = round(time.time() - t0, 1)
    ev = os.path.join(wd, "evidence.json")
    bars_state = "no_evidence"
    if os.path.exists(ev):
        try:
            with open(ev, encoding="utf-8") as f:
                bars_state = (json.load(f).get("blocks", {}).get("daily_bars", {}) or {}) \
                    .get("state", "missing")
        except Exception:  # noqa: BLE001
            bars_state = "unreadable"
    ok = p.returncode == 0 and bars_state in ("available", "fallback")
    return {"code": code, "ok": ok, "rc": p.returncode, "bars": bars_state, "dur_s": dur,
            "tail": (p.stdout or p.stderr or "")[-400:]}


def breaker_wait(label):
    """任一簇 breakers.open_until > now → 睡到 open_until+30。返回等待秒数。

    坑位：状态键名是 breakers（非 clusters）——读错键会静默失守。
    """
    if not os.path.exists(FETCH_STATE):
        return 0
    try:
        with open(FETCH_STATE, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:  # noqa: BLE001
        return 0
    now = time.time()
    open_until = 0
    for c in (st.get("breakers") or {}).values():
        try:
            open_until = max(open_until, (c or {}).get("open_until", 0) or 0)
        except Exception:  # noqa: BLE001
            pass
    if open_until > now:
        wait = open_until + 30 - now
        print(f"[gate] {label}: breaker open, sleep {wait:.0f}s", flush=True)
        time.sleep(wait)
        return wait
    return 0


def drive_prepare(a):
    codes = []
    with open(os.path.join(a.scan_root, "stageA", f"screen_top{a.top_n}.csv"),
              encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            codes.append(row["code"].zfill(6))
    print(f"prepare driver: {len(codes)} stocks, wave={a.wave}", flush=True)
    results = []
    for wi in range(0, len(codes), a.wave):
        wave = codes[wi:wi + a.wave]
        print(f"--- wave {wi // a.wave + 1}: {wave}", flush=True)
        for code in wave:
            r = run_prepare(a.skill_dir, a.scan_root, code)
            results.append(r)
            print(f"  {code} ok={r['ok']} rc={r['rc']} bars={r['bars']} {r['dur_s']}s",
                  flush=True)
            time.sleep(random.uniform(*STOCK_GAP))
        breaker_wait(f"wave {wi // a.wave + 1}")

    fails = [r for r in results if not r["ok"]]
    if fails:
        print(f"--- retry wave after 300s cooldown: {[r['code'] for r in fails]}",
              flush=True)
        time.sleep(300)
        breaker_wait("retry")
        retried = []
        for r in fails:
            nr = run_prepare(a.skill_dir, a.scan_root, r["code"])
            nr["retried"] = True
            retried.append(nr)
            print(f"  retry {r['code']} ok={nr['ok']} rc={nr['rc']} bars={nr['bars']}",
                  flush=True)
            time.sleep(random.uniform(*STOCK_GAP))
        results = [r for r in results if r["ok"]] + [r for r in retried if r["ok"]] + \
                  [r for r in retried if not r["ok"]]

    # N x 16 块状态矩阵（核心六块 + 扩展十块，含 fx 的 not_supported 行）
    lines = [f"# 取数矩阵（{len(codes)} 只 x 16 块）", ""]
    for r in sorted(results, key=lambda x: x["code"]):
        ev = os.path.join(a.scan_root, "vs", r["code"], "evidence.json")
        if os.path.exists(ev):
            with open(ev, encoding="utf-8") as f:
                evd = json.load(f)
            states = {n: (b or {}).get("state", "missing")
                      for n, b in evd.get("blocks", {}).items()}
            q = evd.get("quality", {})
            lines.append(f"## {r['code']} — {states.get('daily_bars', '-')} "
                         f"| tier={q.get('tier')} cap={q.get('confidence_cap')} "
                         f"score={q.get('score')}")
            lines.append("  " + " ".join(f"{n}:{s}" for n, s in sorted(states.items())))
        else:
            lines.append(f"## {r['code']} — NO EVIDENCE")
    with open(os.path.join(a.scan_root, "vs", "_fetch_matrix.md"), "w",
              encoding="utf-8") as f:
        f.write("\n".join(lines))
    ok_codes = [r["code"] for r in results if r["ok"]]
    print(f"DONE ok={len(ok_codes)}/{len(codes)}: {ok_codes}", flush=True)
    return 0 if ok_codes else 2


def register_shortlist(a):
    """shortlisted 股逐只跑 diagnose.py report；已登记复用不重跑。

    去重键与登记写入同源（数据日而非运行日）：register_signal 落的 date 取
    quote.date/末根日 K 日期，周末/节假日重跑时运行日 ≠ 数据日——只比运行日
    会重复 append 信号污染台账，故比对「该股将写入的数据日」。"""
    today = a.date or dt.date.today().isoformat()
    try:
        with open(SIGNALS, encoding="utf-8") as f:
            signals = json.load(f)
    except Exception:  # noqa: BLE001
        signals = []
    with open(os.path.join(a.scan_root, "midtier.jsonl"), encoding="utf-8") as f:
        sel = [r for r in map(json.loads, f) if r.get("shortlisted")]

    def data_date(code):
        """该股本次将登记的数据日（register_signal 同源口径），读不出退运行日。"""
        try:
            with open(os.path.join(a.scan_root, "vs", code, "evidence.json"),
                      encoding="utf-8") as f:
                b = json.load(f).get("blocks", {})
            q = (b.get("quote") or {}).get("date")
            if q:
                return str(q)[:10]
            bars = (b.get("daily_bars") or {}).get("bars") or []
            if bars:
                return str(bars[-1].get("date", ""))[:10]
        except Exception:  # noqa: BLE001
            pass
        return today

    n_ok = 0
    for r in sel:
        code = r["code"]
        d0 = data_date(code)
        if any(s.get("code") == code and s.get("date") in (d0, today)
               for s in signals):
            n_ok += 1
            print(f"{code}: 已登记（signals.json date={d0}），复用不重跑")
            continue
        try:
            p = subprocess.run(
                ["uv", "run", "--no-project", os.path.join(a.skill_dir, "scripts",
                                                           "diagnose.py"), "report",
                 "--stock", code, "--workdir", os.path.join(a.scan_root, "vs", code)],
                capture_output=True, text=True, timeout=120)
            rc, tail = p.returncode, (p.stdout or p.stderr or "")[-120:]
        except subprocess.TimeoutExpired:  # 单股超时按失败继续，不炸登记器
            rc, tail = "timeout", "timeout after 120s"
        n_ok += rc == 0
        print(f"{code}: rc={rc} {tail}")
    print(f"DONE: {n_ok}/{len(sel)}")
    return 0 if sel else 2


def main():
    ap = argparse.ArgumentParser(description="Stage B 取数驱动 + shortlist 登记（参考实现）")
    ap.add_argument("--scan-root", required=True, help="批量运行根目录")
    ap.add_argument("--skill-dir", default=os.path.expanduser(
        "~/.claude/skills/vibe-stock"), help="skill 根目录（scripts/ 所在）")
    ap.add_argument("--top-n", type=int, default=30, help="Stage A 入选数（文件名拼接）")
    ap.add_argument("--wave", type=int, default=WAVE, help="每波取数股数")
    ap.add_argument("--register", action="store_true",
                    help="登记模式：对 midtier.jsonl 的 shortlisted 跑 report")
    ap.add_argument("--date", default=None, help="登记当日复用判定的基准日（缺省今天）")
    a = ap.parse_args()
    sys.exit(register_shortlist(a) if a.register else drive_prepare(a))


if __name__ == "__main__":
    main()
