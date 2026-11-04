#!/usr/bin/env python3
"""outlook_daily.py · 在册股走势参考收盘批量（编排层，非门禁件）。

口径 SSOT 在 references/09-outlook.md；本文件只做编排：宇宙派生（import
watch，禁复制）→ FetchLock 单窗逐股取数（close_pass 同款锁纪律；股间
unlocked 退避 8–12s——06 取数串行+抖动）→ scripts/outlook.py 纯函数出卡 →
收盘卡入全局时序（盘中不入，outlook.persist_card 前置闸）→ 渲染全集日表。

使用纪律（references/09 并发与预算节）：
  - 时点 ≥17:10（避开 16:15 盘后兜底槽 --close；「盯盘期间不跑本批次」——
    I-005 延伸句）；预算 ≈21 条日 K 链（回退全触发上界 ~84 HTTP）+
    moneyflow 每股 1 条，如实计入诊股额度（正经消耗，不走盯盘本地退避）。
  - 幂等：当日已卡非 --force 跳过取数；同日重跑按 (market,code) upsert。

用法（依赖同全诊：akshare/efinance/yfinance 经 uv run --with 临时装）：
  uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
    python batch/outlook_daily.py --daily [--force]
  uv run --no-project python batch/outlook_daily.py --render   # 零取数重渲日表
  uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
    python batch/outlook_daily.py --stock 600519               # 单股刷新
"""
import argparse
import datetime as dt
import json
import os
import random
import sys
import time

_SK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(_SK, "scripts"))
sys.path.insert(0, os.path.join(_SK, "batch", "monitor"))

import fetch as vfetch        # noqa: E402  fetch_daily_bars/derive_technical/fetch_moneyflow
import postmortem as vpm      # noqa: E402  MIN_SAMPLES（小样本阈值 SSOT）
import outlook as ol          # noqa: E402  compute_card/persist_card/render_day_row
from watch import FetchLock, load_universe  # noqa: E402  宇宙与全局取数锁（禁复制）

STATE_DIR = os.path.expanduser("~/.vibe-stock")
DISCLAIMER = ("本日表由 vibe-stock 生成，仅供学习与研究参考，不构成投资建议；"
              "零权重参考，不进任何裁决；收盘后参考·非投资建议。")
_KIND_CN = {"real": "实盘", "sim": "模拟", "watch": "观察"}


def _now():
    return dt.datetime.now(vfetch.TZ_CN)


def _norm(market, code):
    code = str(code or "")
    return code.zfill(5) if market == "hk" else code


def _stamp_day(card):
    """卡片入时序的墙钟日（persisted_at 前 10 位）——幂等判断按批次运行日，
    不按卡片交易日（源末根滞后会让当日已跑的卡 date 仍是前一交易日）。"""
    return str(card.get("persisted_at") or "")[:10]


def build_evidence(market, code, name, st, now):
    """最小证据包：日 K + 派生 quote/technical + moneyflow（情绪面扩行）。
    市场级块 0.0.19 接入（references/09 分期表）；失败如实标 state 不虚构。"""
    bars, bars_state, bars_src, _tried = vfetch.fetch_daily_bars(
        market, code, st, now)
    session = vfetch.session_phase(
        market, bars[-1]["date"] if bars else None,
        dt.datetime.fromtimestamp(now, vfetch.TZ_CN))
    quote = dict(vfetch.derive_quote(bars)) if bars else {}
    quote.update({"state": bars_state, "source": bars_src})
    if name:
        quote["name"] = name
    tech = vfetch.derive_technical(bars, session, market, code) if bars else {}
    tech["state"] = "available" if bars else bars_state
    mf = vfetch.fetch_moneyflow(market, code, st, now)
    blocks = {"daily_bars": {"state": bars_state, "source": bars_src,
                             "bars": bars},
              "quote": quote, "technical": tech, "moneyflow": mf}
    # 市场级五块（0.0.19）：市场维度共享——fetch 层 _MKT_CACHE 使 21 股批量
    # 只付一次取数（hk 守卫 not_supported 如实）
    for name in ("margin", "index", "turnover_pctile", "erp",
                 "margin_accounts"):
        blocks[name] = getattr(vfetch, "fetch_%s" % name)(market, code, st, now)
    return {"meta": {"symbol": code, "market": market, "code": code,
                     "session": session},
            "blocks": blocks}


def collect(state_dir, force=False, only=None):
    """取数补卡（FetchLock 单窗）。返回 (cards, failed, intraday, lock_blocked)。

    墙钟门（无条件前置，--force 可越过）：本地时区 <17:10 拒跑——收盘竞价
    定型窗（A 15:00–15:10、港 16:00–16:08）内源末根尚未定型，早跑会把
    未定型收盘价钉成当日卡且幂等键（persisted_at=运行日）让当日不再重取
    （I-010/M4/L8 一并堵死）；节假日/周末 17:10 后跑无害（末根=上一交易
    日，卡片如实带交易日）。"""
    now_dt = _now()
    if not force and (now_dt.hour, now_dt.minute) < (17, 10):
        print("拒跑：未到 17:10 收盘定型窗后（现 %02d:%02d）——早跑会把未定型"
              " K 线钉成当日卡；--force 越过需自担" % (now_dt.hour, now_dt.minute))
        return [], [], [], False
    uni = load_universe(state_dir)
    today = _now().date().isoformat()
    cached = ol.latest_cards(state_dir)
    rows = [r for r in uni["rows"]
            if only is None or _norm(r["market"], r["code"]) == only]
    todo = []
    for r in rows:
        c = cached.get((r["market"], _norm(r["market"], r["code"])))
        if not force and c and _stamp_day(c) == today:
            continue  # 当日已卡（按批次运行日）：幂等跳过取数
        todo.append(r)
    if not todo:
        print("当日卡齐备（%d 只）——零取数；--force 可全量重取" % len(rows))
        return [cached[(r["market"], _norm(r["market"], r["code"]))]
                for r in rows], [], [], False
    lock = FetchLock(state_dir)
    if not lock.acquire(timeout=120):
        print("warn: fetch_state.lock 竞争超时（全诊/--close 在跑？），本次挂起"
              "——稍后重跑幂等无损失")
        return [], [], [], True   # 锁竞争独立计数（L6：不计入盘中拒写）
    cards, failed, intraday = [], [], []
    st = vfetch.load_fetch_state()
    try:
        for i, r in enumerate(todo):
            market, code = r["market"], r["code"]
            if i:
                time.sleep(random.uniform(8, 12))  # 股间退避（06 串行+抖动）
            # M2：now 每股现取——冷却/熔断/时段判定不吃批次开头的陈旧值
            # （批次 4–7 分钟，首股冷却 15s 会把余股全压回退源、时段漂移会
            # 绕过盘中拒写闸）
            now = int(time.time())
            try:
                ev = build_evidence(market, code, r.get("name"), st, now)
            except Exception as e:  # 单股失败不连坐（回退链语义在 fetch 层）
                print("warn: %s %s 取数异常 %r" % (market, code, e))
                failed.append(code)
                continue
            if ev["blocks"]["daily_bars"]["state"] == "fetch_failed":
                print("warn: %s %s 日 K 全链失败（熔断账本已记）" % (market, code))
                failed.append(code)
                continue
            fallback = ({k: r.get(k) for k in
                         ("stop", "target1", "entry_ref")}
                        if r.get("levels_source") == "allocation" else None)
            try:
                card = ol.compute_card(ev, state_dir, fallback)
            except Exception as e:  # 计算段并入 try（M3：异常不丢熔断账本）
                print("warn: %s 出卡异常 %r" % (code, e))
                failed.append(code)
                continue
            if card.get("price_kind") == "intraday":
                intraday.append(code)  # 盘中卡不入全局时序（09 写拓扑）
                print("warn: %s 末根未完成（盘中运行？）——卡片未入全局时序"
                      % code)
                continue
            try:
                ol.persist_card(state_dir, card,
                                _now().isoformat(timespec="seconds"))
                cards.append(card)
                print("outlook: %s %s -> %s（%s）" % (
                    market, code, card.get("date"), card.get("state")))
            except (ValueError, OSError) as e:
                print("warn: %s 落盘被拒（%s）" % (code, e))
                failed.append(code)
    finally:
        try:
            vfetch.save_fetch_state(st)  # 熔断账本：finally 落盘（M3：Ctrl-C/
        except Exception:                 # 异常路径不丢已产生的熔断/冷却记录）
            pass
        lock.release()
    return cards, failed, intraday, False


def render_daily(state_dir):
    """渲染全在册日表：universe 每股取最新一张卡（跨日文件——源末根时差会让
    同批次分落两个交易日文件）；日表文件名=批次运行日（墙钟），每行带卡片
    交易日列如实披露时差；幂等重渲（day-summary 同款）。"""
    latest = ol.latest_cards(state_dir)
    if not latest:
        print("无任何收盘卡——先跑 --daily")
        return None
    uni = load_universe(state_dir)
    kind = {(r["market"], _norm(r["market"], r["code"])): r.get("kind", "watch")
            for r in uni["rows"]}
    cards = [latest[k] for k in kind if k in latest]
    missing = [k for k in kind if k not in latest]
    day = _now().date().isoformat()
    L = ["# 走势参考日表 · %s" % day, ""]
    L.append("零权重纯参考：不进裁决聚合/置信帽/后验记分/RiskGuard（用户裁定 4）；"
             "预测带是「另一把尺」——%s" % ol.BAND_NOTE)
    L.append("")
    L.append("## 个股走势参考")
    L.append("| 类别 | 市场 | 代码 | 名称 | 交易日 | 现价 | T+10 带% | T+60 带% | "
             "经验T+1 | 经验T+10 | 换手分位 | 20日涨停 | 状态 |")
    L.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"
             " --- | --- | --- |")

    def _cell(v, suffix=""):
        return "—" if v is None else "%s%s" % (v, suffix)

    def _exp(b):
        if not b:
            return "—"
        return "%s样%s" % (b.get("n"), "（不足）" if b.get("insufficient") else "")

    def _key(c):
        return (c.get("market"), _norm(c.get("market"), c.get("code")))

    rows = sorted(cards, key=lambda c: (
        {"real": 0, "sim": 1, "watch": 2}.get(kind.get(_key(c)), 3),
        c.get("market") or "", str(c.get("code"))))
    for c in rows:
        r = ol.render_day_row(c)
        k = kind.get(_key(c), "watch")
        head = "| %s | %s | %s | %s | %s |" % (
            _KIND_CN.get(k, k), c.get("market"), c.get("code"),
            c.get("name") or "—", c.get("date") or "—")
        if r.get("state") != "estimated":
            L.append(head + " — | — | — | — | — | — | — | 弃权 |")
            continue
        L.append(head + " %s | %s | %s | %s | %s | %s | %s | ok |" % (
            _cell(r.get("price")), _cell(r.get("band_10d_pct")),
            _cell(r.get("band_60d_pct")),
            _exp(r.get("exp_t1")), _exp(r.get("exp_t10")),
            _cell(r.get("turnover_pctile_250")),
            _cell(r.get("limit_up_count_20d"))))
    for m, code in missing:  # 在册却无卡（取数失败/新入册未跑）：如实列出
        L.append("| %s | %s | %s | — | — | — | — | — | — | — | — | — | 缺卡 |" % (
            _KIND_CN.get(kind[(m, code)], "观察"), m, code))
    L.append("")
    L.append("交易日列=卡片末根日 K 日期：盘后数据源更新有时差（A 股源末根常滞后、"
             "港股已出），同批次可跨两个交易日——如实披露不对齐。")
    L.append("")
    L.append("## 市场级情绪")
    mkt = None
    for c in cards:  # 市场维度共享：任取一张 estimated 卡的市场级投影
        em = c.get("emotion") or {}
        if (em.get("market") or {}).get("state") == "estimated":
            mkt = em["market"]
            break
    if mkt:
        mg = mkt.get("margin") or {}
        if mg:
            L.append("- 两融余额 %s 亿（%s）· Δ1d %s%% / Δ5d %s%% / Δ20d %s%% · "
                     "70 日分位 %s%%（%s）" % (
                         mg.get("balance_yi"), mg.get("as_of"),
                         mg.get("chg_1d_pct"), mg.get("chg_5d_pct"),
                         mg.get("chg_20d_pct"), mg.get("pctile_70d"),
                         mg.get("source")))
        tp = mkt.get("turnover_pctile") or {}
        if tp:
            L.append("- 全A换手分位 %s%%（%d 日窗，%s）" % (
                tp.get("pctile"), tp.get("window") or 0, tp.get("as_of")))
        ep = mkt.get("erp") or {}
        if ep:
            L.append("- ERP %s%%（月频 PE %s × 10Y %s%%，%s）· 5 年月频分位 "
                     "%s%% · 日频积累 %s" % (
                         ep.get("erp_pct"), ep.get("monthly_pe"),
                         ep.get("y10_pct"), ep.get("as_of"),
                         ep.get("pctile_5y_monthly"),
                         "就绪" if ep.get("daily_ready") else "进行中"))
        ma = mkt.get("margin_accounts") or {}
        if ma:
            L.append("- 两融账户参与度 %s 户（%s）· Δ5d %s%% / Δ20d %s%%"
                     % (ma.get("traders"), ma.get("as_of"),
                        ma.get("traders_chg_5d_pct"),
                        ma.get("traders_chg_20d_pct")))
        ix = mkt.get("index") or {}
        for name, s in (ix.get("indices") or {}).items():
            L.append("- 指数 %s %s（%s，距 MA60 %s%%，%s）" % (
                name, s.get("close"), s.get("as_of"),
                s.get("dist_ma60_pct"), s.get("source")))
    else:
        L.append("- abstained——市场级五块本批全部不可用（单块状态见各股诊股"
                 "证据面状态行；references/09）")
    L.append("")
    L.append("## 说明")
    L.append("- %s" % ol.ZERO_WEIGHT_NOTE)
    L.append("- %s" % ol.BETA_NOTE)
    L.append("- 经验计数：该股信号后验 evaluated 的计数桶——%s；n<%d 标"
              "「不足」" % (ol.EXP_NOTE, vpm.MIN_SAMPLES))
    L.append("- 用户锚（实盘股的操作复盘与波段带距离）见各股诊股报告 4c 节"
             "与本表之外的个股卡（脱敏口径：仅操作方向/时点/其后公开行情%）")
    L.append("")
    L.append("---")
    L.append("*%s*" % DISCLAIMER)
    path = os.path.join(ol.outlook_dir(state_dir), "%s.md" % day)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    return path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", action="store_true", help="收盘后批量（默认形态）")
    ap.add_argument("--force", action="store_true", help="忽略当日缓存全量重取")
    ap.add_argument("--stock", default="", help="单股刷新（归一匹配 universe 行）")
    ap.add_argument("--render", action="store_true", help="只重渲日表（零取数）")
    ap.add_argument("--state-dir", default=STATE_DIR)
    args = ap.parse_args()
    only = None
    if args.stock:
        market, code = vfetch.detect_market(args.stock)
        only = _norm(market, code)
    if args.daily or args.stock:
        cards, failed, intraday, locked = collect(
            args.state_dir, args.force, only)
        print("批量收口：出卡 %d · 取数失败 %d · 盘中拒写 %d · 锁竞争挂起 %s"
              % (len(cards), len(failed), len(intraday),
                 "是（稍后重跑幂等无损失）" if locked else "否"))
    elif not args.render:
        print("裸跑不取数（防误触发 ~84 HTTP）：取数用 --daily 或 --stock；"
              "重渲日表用 --render")
        return 2
    path = render_daily(args.state_dir)
    if path:
        print("day table -> %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
