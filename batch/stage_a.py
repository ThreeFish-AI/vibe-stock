#!/usr/bin/env python3
"""Stage A：指数成分机械粗筛（池 → N），零 LLM——bulk 接口 + 探测回退。

口径以 references/06-batch-scan.md 为准（本脚本是参考实现）。数据：成分+
权重(csindex) + 全市场 spot 快照(EM，限流回退新浪+腾讯 qt 批量补) + 季度
业绩 bulk(stock_yjbb_em 双期 join)。评分：均衡风格 rank-based 复合分
（质量 .25 / 成长 .25 / 价值 .25 / 动量 .10 / 稳定 .15）。
产出：<scan-root>/stageA/{raw/, universe.csv, screen_top<N>.csv,
screen_report.md, fetch_log.json}。

用法（sk=skill 根目录）：
  uv run --no-project --with 'akshare==1.20.*' --with efinance \
    <sk>/batch/stage_a.py --pool hs300 --top-n 30 --budget 100000 \
    --scan-root ~/.vibe-stock/reports/_scans/$(date +%F)-hs300 \
    --skill-scripts <sk>/scripts
"""
import argparse
import datetime as dt
import json
import os
import sys
import time

import akshare as ak
import numpy as np
import pandas as pd

POOL_INDEX = {"hs300": ("000300", "沪深300", 300)}  # 池名 → (指数代码, 名称, 成分数)
FACTORS = {"quality": 0.25, "growth": 0.25, "value": 0.25, "momentum": 0.10, "stability": 0.15}
FETCH_LOG = []


def out_dirs(scan_root):
    out = os.path.join(scan_root, "stageA")
    os.makedirs(out, exist_ok=True)
    os.makedirs(os.path.join(out, "raw"), exist_ok=True)
    return out


def cached(raw_dir, name, fn):
    """raw 落盘缓存：重跑不重取网络。fn 可返回 df 或 (df, source) 或 None。"""
    p = os.path.join(raw_dir, f"{name}.csv")
    meta_p = os.path.join(raw_dir, f"{name}.src")
    if os.path.exists(p):
        src = open(meta_p, encoding="utf-8").read() if os.path.exists(meta_p) else "?"
        print(f"[cache] reuse {name} ({src})", flush=True)
        log_fetch(f"cache:{name}", True, 0.0, f"reused, src={src}")
        return pd.read_csv(p, dtype=str), src
    out = fn()
    if out is None:
        return None
    df, src = out if isinstance(out, tuple) else (out, "?")
    df.to_csv(p, index=False, encoding="utf-8-sig")
    with open(meta_p, "w", encoding="utf-8") as f:
        f.write(str(src))
    return df, src


def log_fetch(name, ok, dur, note=""):
    FETCH_LOG.append({"interface": name, "ok": bool(ok), "duration_s": round(dur, 1),
                      "note": str(note)[:300]})
    print(f"[fetch] {name} ok={ok} {dur:.1f}s {note}", flush=True)


def col(df, *cands):
    """模糊找列：候选子串任一命中即返回。"""
    for c in df.columns:
        cl = str(c)
        if any(cand in cl for cand in cands):
            return c
    return None


def zc(df, c):
    return pd.to_numeric(df[c], errors="coerce") if c else pd.Series(np.nan, index=df.index)


def recent_periods(date_iso, n=2):
    """最近 n 个已过季末（YYYYMMDD 降序）。披露滞后由双期 join + period_used 兜底。"""
    d = dt.date.fromisoformat(date_iso)
    today = d.strftime("%Y%m%d")
    ends = []
    for y in (d.year, d.year - 1):
        ends += [f"{y}0331", f"{y}0630", f"{y}0930", f"{y}1231"]
    return sorted((p for p in ends if p <= today), reverse=True)[:n]


def fetch_cons(index_code):
    t0 = time.time()
    for fn, tag in ((ak.index_stock_cons_weight_csindex, "csindex_weight"),
                    (ak.index_stock_cons_csindex, "csindex_plain")):
        try:
            df = fn(index_code)
            log_fetch(f"cons:{tag}", True, time.time() - t0, f"{len(df)} rows")
            return df, tag
        except Exception as e:  # noqa: BLE001
            log_fetch(f"cons:{tag}", False, time.time() - t0, repr(e)[:200])
    df = ak.index_stock_cons_sina("sh" + index_code)
    log_fetch("cons:sina", True, time.time() - t0, f"{len(df)} rows")
    return df, "sina"


def fetch_spot():
    t0 = time.time()
    try:
        df = ak.stock_zh_a_spot_em()
        log_fetch("stock_zh_a_spot_em", True, time.time() - t0, f"{len(df)} rows")
        return df, "em"
    except Exception as e:  # noqa: BLE001
        log_fetch("stock_zh_a_spot_em", False, time.time() - t0, repr(e)[:150])
    try:
        df = ak.stock_zh_a_spot()
        log_fetch("stock_zh_a_spot(sina fallback)", True, time.time() - t0, f"{len(df)} rows")
        return df, "sina_spot"
    except Exception as e:  # noqa: BLE001
        log_fetch("stock_zh_a_spot(sina fallback)", False, time.time() - t0, repr(e)[:150])
        return pd.DataFrame(columns=["代码"]), "qt_only"


def fetch_yjbb(date):
    t0 = time.time()
    try:
        df = ak.stock_yjbb_em(date=date)
        log_fetch(f"stock_yjbb_em({date})", True, time.time() - t0, f"{len(df)} rows")
        return df
    except Exception as e:  # noqa: BLE001
        log_fetch(f"stock_yjbb_em({date})", False, time.time() - t0, repr(e)[:200])
        return None


def pct_rank(s, ascending=True):
    return s.rank(pct=True, ascending=ascending, na_option="keep")


def qt_prefix(code):
    return ("sh" if code[0] in "69" else "bj" if code[0] in "48" else "sz") + code


def fetch_qt_fill(codes, skill_scripts):
    """spot 缺 PE/PB 时用腾讯 qt 快照批量补（30 码/请求；解析复用 skill 的 fetch._parse_qt_full）。"""
    if skill_scripts not in sys.path:
        sys.path.insert(0, skill_scripts)
    import fetch as vfetch  # noqa: PLC0415
    import urllib.request  # noqa: PLC0415
    rows = []
    t0 = time.time()
    codes = list(codes)
    for bi in range(0, len(codes), 30):
        batch = codes[bi:bi + 30]
        url = "https://qt.gtimg.cn/q=" + ",".join(qt_prefix(c) for c in batch)
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        text = urllib.request.urlopen(req, timeout=15).read().decode("gbk", errors="replace")
        for line in text.split(";"):
            line = line.strip()
            if '"' not in line or "~" not in line:
                continue
            code = line.split("=")[0].strip().replace("v_", "")[2:]
            try:
                p = vfetch._parse_qt_full(line)
            except Exception:  # noqa: BLE001
                continue
            rows.append({"code": code, "qt_price": p["price"], "qt_pe": p["pe_ttm"],
                         "qt_pb": p["pb"], "qt_dy": p["dividend_yield_ttm"],
                         "qt_turnover_wan": p["amount_wan"]})
        time.sleep(2.5)
    log_fetch("qt_fill(batchx%d)" % ((len(codes) + 29) // 30), len(rows) > 0,
              time.time() - t0, f"{len(rows)}/{len(codes)} stocks")
    return pd.DataFrame(rows)


def main():
    ap = argparse.ArgumentParser(description="Stage A 机械粗筛（批量子技能参考实现）")
    ap.add_argument("--pool", default="hs300", help="池名（POOL_INDEX 键）")
    ap.add_argument("--date", default=dt.date.today().isoformat(), help="基准日 YYYY-MM-DD")
    ap.add_argument("--top-n", type=int, default=30, help="粗筛入选数")
    ap.add_argument("--budget", type=float, default=1e5, help="总预算（元）")
    ap.add_argument("--w-max", type=float, default=0.145, help="单仓权重上限（价格硬滤用）")
    ap.add_argument("--min-turnover", type=float, default=1e8, help="流动性下限（日成交额，元）")
    ap.add_argument("--max-price", type=float, default=None,
                    help="价格硬滤上限；缺省按 w_max*budget/100/100 自动")
    ap.add_argument("--industry-cap", type=int, default=3, help="同行业入选上限")
    ap.add_argument("--scan-root", required=True, help="批量运行根目录（产物 SSOT）")
    ap.add_argument("--skill-scripts", default=os.path.expanduser(
        "~/.claude/skills/vibe-stock/scripts"), help="skill scripts 目录（qt 解析复用）")
    a = ap.parse_args()
    if a.pool not in POOL_INDEX:
        sys.exit(f"FATAL: 未知池 {a.pool}（已内置：{'/'.join(POOL_INDEX)}）")
    index_code, pool_name, n_expect = POOL_INDEX[a.pool]
    max_price = a.max_price if a.max_price is not None else a.w_max * a.budget / 100.0 / 100.0
    out = out_dirs(a.scan_root)

    print(f"akshare {ak.__version__}", flush=True)
    cons, cons_src = cached(out, "cons", lambda: fetch_cons(index_code))
    time.sleep(15)
    spot, spot_src = cached(out, "spot", fetch_spot)
    periods = recent_periods(a.date, 2)  # [primary, secondary]
    fin = {}
    for i, per in enumerate(periods):
        time.sleep(15)
        r = cached(out, f"yjbb_{per}", lambda p=per: fetch_yjbb(p))
        fin[per] = r[0] if r else None

    # ---- 成分表规范化 ----
    cc = col(cons, "成分券代码", "品种代码", "股票代码") or col(cons, "代码")
    cn = col(cons, "成分券名称", "品种名称", "股票简称") or col(cons, "名称")
    cw = col(cons, "权重")
    cons_df = pd.DataFrame({
        "code": cons[cc].astype(str).str.split(".").str[0].str.zfill(6),
        "name": cons[cn].astype(str).str.strip(),
        "idx_weight": zc(cons, cw) if cw else np.nan,
    })
    n_cons = len(cons_df)
    if n_cons != n_expect:
        print(f"FATAL: {pool_name} 成分行数 {n_cons} != {n_expect}（来源 {cons_src}），"
              f"列={list(cons.columns)}", flush=True)
        sys.exit(2)
    cons_df = cons_df.drop_duplicates("code")

    # ---- spot join ----
    sc = col(spot, "代码")
    m = {"price": col(spot, "最新价"), "turnover": col(spot, "成交额"),
         "pe": col(spot, "市盈率-动态", "市盈率"), "pb": col(spot, "市净率"),
         "chg60d": col(spot, "60日涨跌幅"), "chgytd": col(spot, "年初至今涨跌幅")}
    spot_df = pd.DataFrame({
        "code": spot[sc].astype(str).str.extract(r"(\d{6})", expand=False).fillna(
            spot[sc].astype(str)).str.zfill(6),
        **{k: zc(spot, c) for k, c in m.items()},
    })
    df = cons_df.merge(spot_df, on="code", how="left")
    # spot 缺 PE/PB（新浪回退）→ qt 批量补（价格/PE/PB 一并覆盖，双源更稳）
    if df["pe"].isna().all() or df["pb"].isna().all():
        qtf = cached(out, "qt_fill", lambda: fetch_qt_fill(cons_df["code"].tolist(),
                                                           a.skill_scripts))
        qtf = qtf[0] if isinstance(qtf, tuple) else qtf
        if qtf is not None and len(qtf):
            df = df.merge(qtf, on="code", how="left")
            for src, dst in [("qt_price", "price"), ("qt_pe", "pe"), ("qt_pb", "pb")]:
                df[dst] = df[dst].fillna(df[src])
            df["turnover"] = df["turnover"].fillna(df["qt_turnover_wan"] * 1e4)
            spot_src += "+qt_fill"

    # ---- yjbb join（primary 优先，secondary 兜底；period_used 逐股标记）----
    def yjbb_norm(y):
        if y is None:
            return None
        yc = col(y, "股票代码")
        return pd.DataFrame({
            "code": y[yc].astype(str).str.zfill(6),
            "eps": zc(y, col(y, "每股收益")),
            "rev_yoy": zc(y, col(y, "营业收入-同比增长")),
            "np_yoy": zc(y, col(y, "净利润-同比增长")),
            "roe": zc(y, col(y, "净资产收益率")),
            "bps": zc(y, col(y, "每股净资产")),
            "ocfps": zc(y, col(y, "每股经营现金流量")),
            "gpm": zc(y, col(y, "销售毛利率")),
            "industry": y[col(y, "所处行业")].astype(str) if col(y, "所处行业") else "未知",
        }).drop_duplicates("code")

    per_df = {p: yjbb_norm(fin.get(p)) for p in periods}
    pri_cov = int(df["code"].isin(per_df[periods[0]]["code"]).sum()) \
        if per_df[periods[0]] is not None else 0
    for c in ["eps", "rev_yoy", "np_yoy", "roe", "bps", "ocfps", "gpm"]:
        df[c] = np.nan
    df["industry"] = "未知"
    df["period_used"] = ""
    for per in periods:  # primary 先填，缺口由次期兜底
        q = per_df[per]
        if q is None:
            continue
        need_idx = df.index[df["period_used"] == ""]
        j = df.loc[need_idx].merge(q, on="code", how="left", suffixes=("", "_j"))
        got = j["eps_j"].notna() | j["roe_j"].notna()  # merge how=left 保左序
        got_idx = need_idx[got.values]
        for c in ["eps", "rev_yoy", "np_yoy", "roe", "bps", "ocfps", "gpm"]:
            df.loc[got_idx, c] = j.loc[got.values, f"{c}_j"].values
        df.loc[got_idx, "industry"] = j.loc[got.values, "industry"].values
        df.loc[got_idx, "period_used"] = per
    sec_backfill = int((df["period_used"] == periods[1]).sum()) if len(periods) > 1 else 0
    no_fin = int((df["period_used"] == "").sum())

    # ---- 因子构造（ROE/EPS 累计值年化：Q3 x4/3、H1 x2）----
    ann = {p: (4.0 / 3 if p[4:6] == "09" else 2.0 if p[4:6] == "06" else
               4.0 if p[4:6] == "03" else 1.0) for p in periods}
    df["roe_ann_est"] = df["roe"] * df["period_used"].map(ann)
    df["eps_ann"] = df["eps"] * df["period_used"].map(ann)
    df["f_quality"] = pct_rank(df["roe_ann_est"])
    df["f_growth"] = (0.6 * pct_rank(df["np_yoy"].clip(-95, 300))
                      + 0.4 * pct_rank(df["rev_yoy"].clip(-95, 300)))
    # spot 缺 PE/PB（新浪回退）时用业绩表推算：pe_est=price/eps 年化，flag 标注
    df["pe_est_flag"] = df["pe"].isna() & np.isfinite(df["eps_ann"])
    df["pb_est_flag"] = df["pb"].isna() & df["bps"].notna()
    df["pe_used"] = pd.Series(np.where(df["pe"] > 0, df["pe"], df["price"] / df["eps_ann"]),
                              index=df.index)
    df["pe_used"] = df["pe_used"].where(df["pe_used"] > 0)
    df["pb_used"] = df["pb"].fillna(df["price"] / df["bps"])
    pe_ok = df["pe_used"].notna()
    df["pe_inv"] = np.nan
    df.loc[pe_ok, "pe_inv"] = 1 - pct_rank(df.loc[pe_ok, "pe_used"])
    pb_inv = 1 - pct_rank(df["pb_used"])
    df["value_pe_missing"] = ~pe_ok
    df["momentum_missing"] = df["chg60d"].isna()
    df["f_value"] = np.where(pe_ok, 0.6 * df["pe_inv"].fillna(0) + 0.4 * pb_inv, pb_inv)
    mom = pct_rank(df["chg60d"]).clip(upper=0.90)
    df["f_momentum"] = (mom - 0.10 * (df["chgytd"] > 80).astype(float)).clip(lower=0)
    df["f_stability"] = 0.5 * pct_rank(df["gpm"]) + 0.5 * pct_rank(df["ocfps"] / df["price"])
    # 动量缺失中性化 0.3（缺失不是 0 分），其余因子缺失同按 0.3 中性
    df["composite"] = (FACTORS["quality"] * df["f_quality"].fillna(0.3)
                       + FACTORS["growth"] * df["f_growth"].fillna(0.3)
                       + FACTORS["value"] * df["f_value"].fillna(0.3)
                       + FACTORS["momentum"] * df["f_momentum"].fillna(0.3)
                       + FACTORS["stability"] * df["f_stability"].fillna(0.3))

    # ---- 硬过滤 ----
    df["hard_filter"] = np.where(df["price"].isna(), "no_price",
                          np.where(df["name"].str.contains("ST|退", na=False), "st",
                          np.where(df["turnover"].fillna(0) < a.min_turnover, "illiquid",
                          np.where(df["price"].fillna(1e9) > max_price,
                                   "price_gt_cap", ""))))
    pool = df[df["hard_filter"] == ""].copy()

    # ---- 选 N：composite 降序 greedy，同行业 ≤ cap；行业数 <8 放宽 cap+1 ----
    def greedy(cap):
        sel, cnt, skipped = [], {}, []
        for _, r in pool.sort_values("composite", ascending=False).iterrows():
            ind = r["industry"]
            if cnt.get(ind, 0) >= cap:
                skipped.append({"code": r["code"], "name": r["name"], "industry": ind,
                                "composite": round(r["composite"], 4)})
                continue
            sel.append(r)
            cnt[ind] = cnt.get(ind, 0) + 1
            if len(sel) == a.top_n:
                break
        return sel, skipped

    sel, skipped = greedy(a.industry_cap)
    if len({r["industry"] for r in sel}) < 8:
        sel, skipped = greedy(a.industry_cap + 1)
    sel_df = pd.DataFrame(sel).sort_values("composite", ascending=False).reset_index(drop=True)

    # 第 N/N+1/N+2 名分差（断崖弹性 28-32：只记录，不硬切）
    rest = pool.sort_values("composite", ascending=False).iloc[len(sel_df):len(sel_df) + 2]

    # ---- 输出 ----
    df.to_csv(os.path.join(out, "universe.csv"), index=False, encoding="utf-8-sig")
    sel_df.to_csv(os.path.join(out, f"screen_top{a.top_n}.csv"), index=False,
                  encoding="utf-8-sig")
    with open(os.path.join(out, "fetch_log.json"), "w", encoding="utf-8") as f:
        json.dump({"akshare": ak.__version__, "date": a.date, "pool": a.pool,
                   "pool_size": n_expect,
                   "cons_source": cons_src, "spot_source": spot_src, "periods": periods,
                   "primary_coverage": pri_cov, "secondary_backfill": sec_backfill,
                   "no_financial": no_fin, "max_price_cap": round(max_price, 1),
                   "momentum_neutralized": int(df["momentum_missing"].sum()),
                   "calls": FETCH_LOG}, f, ensure_ascii=False, indent=2)

    ind_dist = sel_df["industry"].value_counts().to_dict()
    hard_counts = df["hard_filter"][df["hard_filter"] != ""].value_counts().to_dict()
    lines = [
        f"# Stage A 粗筛报告（{pool_name} → {a.top_n}）",
        f"- akshare {ak.__version__}；基准日 {a.date}；成分源 {cons_src}（{n_cons} 行）；"
        f"spot 源 {spot_src}",
        f"- 业绩期 primary {periods[0]} 覆盖 {pri_cov}/{n_expect}；"
        f"secondary {periods[1] if len(periods) > 1 else '-'} 兜底 {sec_backfill}；"
        f"无财务 {no_fin}（period_used 逐股标记，ROE 累计年化折算）",
        f"- 硬过滤剔除（价格上限 {max_price:.0f}、日成交 ≥{a.min_turnover:.0e}）："
        f"{hard_counts or '无'}",
        f"- 动量因子缺失中性化（0.3）并如实标注：{int(df['momentum_missing'].sum())} 只",
        f"- 入选行业分布（{len(ind_dist)} 个行业）：{ind_dist}",
        f"- 行业帽({a.industry_cap})挤出高分票：{skipped[:10] if skipped else '无'}",
        f"- 第 {a.top_n}/{a.top_n + 1}/{a.top_n + 2} 名 composite："
        f"{[round(x, 4) for x in rest['composite'].tolist()]}（断崖弹性：分差 <0.01 可 ±2）",
        "",
        "| # | 代码 | 名称 | 行业 | 期间 | composite | ROEe | 净利YoY | PE | PB | 价 |",
        "|---|------|------|------|------|-----------|------|---------|----|----|----|",
    ]
    for i, r in sel_df.iterrows():
        lines.append(f"| {i + 1} | {r['code']} | {r['name']} | {r['industry']} | {r['period_used']} "
                     f"| {r['composite']:.4f} | {r['roe_ann_est']:.1f} | {r['np_yoy']:.1f}% "
                     f"| {r['pe']:.1f} | {r['pb']:.2f} | {r['price']:.2f} |")
    with open(os.path.join(out, "screen_report.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"OK: selected {len(sel_df)}, industries {len(ind_dist)}, "
          f"primary cov {pri_cov}/{n_expect}, sec bf {sec_backfill}", flush=True)
    print("TOP10:", sel_df[["code", "name", "composite"]].head(10).to_dict("records"),
          flush=True)


if __name__ == "__main__":
    main()
