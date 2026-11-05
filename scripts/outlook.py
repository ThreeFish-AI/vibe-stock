#!/usr/bin/env python3
"""outlook.py · 在册股短/中期走势参考卡——零权重纯参考（references/09 SSOT）。

机制（期限口径与双轨完全同构，archive.HORIZONS_OF 为期限 SSOT）：
  - 三面：数学面（零漂移 ±σ_d×√h 预测带 + first-passage 触及概率 + mid_term
    投影 + 与前卡确定性日差）；情绪面（个股级=mid_term 情绪键与资金流扩行
    投影，零新增取数；市场级块 0.0.19 接入前 abstain）；经验面（signals.json
    evaluated 的每股×轨×horizon 计数桶——描述性统计，非绩效因子）。
  - 零权重（用户 2026-11-04 裁定 4）：不进裁决聚合/置信帽/两轨后验记分/
    RiskGuard/策略 YAML；进 context-pack（信息面）与报告 4c 条件节；LLM 可
    引用其数字作 rationale 素材但裁决链零感知。
  - 两把尺分立（band_note 逐字钉）：预测带只描述价格分布量级，判定带口径
    SSOT 在 postmortem（default 恒 ±2%、position σ√h 仅 T+60 记分），本卡只
    引用不复算。
  - 写拓扑（无条件）：全局时序 ~/.vibe-stock/outlook/<date>.jsonl 唯一写者
    =batch 侧批量命令（收盘后、FetchLock 窗内、末根未完成不落盘）；诊股
    prepare 恒现算、只落 workdir（.vs/outlook.json，lens 同款），失败/弃权
    即清除残留卡。
  - 脱敏（无条件）：operations 只投影 time/action/price 与其后公开行情涨跌，
    quantity/cost_price/成本派生涨幅绝不消费绝不落盘。

用法：
  uv run --no-project scripts/outlook.py --evidence .vs/evidence.json [--out …]
  uv run --no-project scripts/outlook.py --selftest
（diagnose.py prepare 自动调用；批量走 batch/outlook_daily.py。）
"""
import argparse
import datetime as dt
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import archive as ar        # noqa: E402  HORIZONS_OF/load_signals/write_json_atomic
import fetch as fx          # noqa: E402  realized_vol（σ SSOT）
import lens as lens_mod     # noqa: E402  touch_probability（first-passage SSOT）
import postmortem as pm     # noqa: E402  MIN_SAMPLES（小样本降级 SSOT）

STATE_DIR = os.path.expanduser("~/.vibe-stock")
SCHEMA = "outlook/1"
# 下列固定文案为 selftest 逐字钉（规约句 SSOT 在 references/09，文案两处同步）
BAND_NOTE = ("预测带≠后验判定带：default 轨 ±2% 固定带、position 轨 σ√h 带仅 "
             "T+60 记分（references/05）——本带只描述价格分布量级")
ZERO_WEIGHT_NOTE = ("零权重参考：不进裁决聚合/置信帽/两轨后验记分/RiskGuard/"
                    "策略 YAML；机械降档接入待评审")
BETA_NOTE = ("预测带未剔除大盘 beta（个股口径；指数链已就绪，剥离 beta 的"
             "超额收益带随 references/08 Phase 5 实施）")
EXP_NOTE = "描述性统计（该股信号后验计数），非绩效因子，不进聚合与台账"
SIGMA_FLOOR = 0.02   # σ 退化链兜底日波动：宁宽勿窄（宽于 postmortem 退化带
#                    # 2%×√(h/10) 的隐含 σ_d≈0.63%——预测带是参考量级不是判定带）
OPS_NOTE = ("成交价为券商裸价、行情为 qfq 复权口径（除权除息期二者有差异）；"
            "零指令纯事实呈现")
DELTA_KEYS = ("rv60", "ret_20d", "turnover_pctile_250")   # 日差/连向跟踪键
CLOSE_GATE_HM = (17, 10)   # 收盘定型墙钟门 SSOT（09「时点墙钟门」）：编排层
#                          # batch/outlook_daily 禁内联该字面量（单源，I-023）


def close_gate_open(now_dt):
    """收盘定型墙钟门（无条件前置，代码闸非使用纪律；--force 由调用方越过）：
    本地时区 ≥17:10 才放行。坑位：早跑会把未定型收盘价钉成当日卡/错误校准
    样本，且幂等键（persisted_at 运行日 / 台账键）让当日不再重取（I-014）。"""
    return (now_dt.hour, now_dt.minute) >= CLOSE_GATE_HM


def final_bars(bars, market):
    """末根未完成过滤（根本防线，--force 越过墙钟门后仍生效）：判窗只用已
    定型 K——session_phase 判据=末根日==今日且盘中；盘中半根 K 一旦入校准
    台账即永久错误样本（幂等键永不重判）。"""
    if bars and fx.session_phase(market, bars[-1]["date"])["last_bar_partial"]:
        return bars[:-1]
    return bars


def count_new_samples(rows, run_stamp):
    """本次运行真实新增样本数（I-015③）：按本运行 judged_at 戳计——幂等
    重跑如实 0，不按满窗计算数虚报。"""
    return sum(1 for r in rows if r.get("judged_at") == run_stamp)


def _f(v):
    """数值清洗：None/NaN/非数 → None（lens 同款）。"""
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return v if v == v else None


def _norm_code(market, code):
    """读时归一（05 口径）：港股补 5 位；其余原样字符串化。"""
    code = str(code or "")
    return code.zfill(5) if market == "hk" else code


def outlook_dir(state_dir):
    return os.path.join(state_dir, "outlook")


# ---------------------------------------------------------------- 数学面

def sigma_daily(closes):
    """σ_d 与退化链：rv60 → rv120 → 2% 兜底（标注 src；realized_vol 为年化
    口径，σ_d=rv/√252）。返回 (σ_d, src)；closes 为空 → (None, None)。"""
    if not closes:
        return None, None
    # 退化链 rv60→2% 兜底（rv60 需 ≥30 有效收益，不足时 rv120 的 ≥60 门槛
    # 必不满足——中间档事实不可达，不设）
    rv = fx.realized_vol(closes, 60)
    if rv:
        return round(rv / math.sqrt(252), 6), "60d"
    return SIGMA_FLOOR, "floor_2pct"


def horizon_bands(price, sigma_d, horizons):
    """零漂移预测带：逐 horizon ±σ_d×√h（band_note 分立判定带）。"""
    out = {}
    for h in horizons:
        band = round(sigma_d * math.sqrt(h) * 100, 2)
        # lo 夹 0：极端波动（σ_ann≳146% 的新股/小票）下线性带下沿可为负
        out[str(h)] = {"band_pct": band,
                       "lo": round(max(0.0, price * (1 - sigma_d * math.sqrt(h))), 3),
                       "hi": round(price * (1 + sigma_d * math.sqrt(h)), 3)}
    return out


def anchor_set(price, sigma_ann, anchors, horizons):
    """锚位投影：现价距锚百分比 + first-passage 触及概率（lens SSOT 封装）。
    anchors={name: value}；非法/缺失锚整体跳过（不虚构）。"""
    out = {}
    for name, raw in (anchors or {}).items():
        v = _f(raw)
        if v is None or v <= 0 or not price or not sigma_ann:
            continue
        touch = {}
        for h in horizons:
            p = lens_mod.touch_probability(price, v, sigma_ann, h / 252.0)
            if p is not None:
                touch[str(h)] = p
        out[name] = {"value": round(v, 3),
                     "dist_pct": round((v / price - 1) * 100, 2), "touch": touch}
    return out


# ---------------------------------------------------------------- 经验面

def experience_tracks(signals, market, code):
    """每股×轨×horizon 计数桶：只数 evaluated 落账的 outcome（hit/miss/
    neutral；observed 不记分——05 口径），n<MIN_SAMPLES 标 insufficient。"""
    want = _norm_code(market, code)
    tracks = {}
    for s in signals or []:
        if s.get("snapshot") or s.get("market") != market \
                or _norm_code(market, s.get("code", "")) != want:
            continue  # 快照合成信号不入桶（archive 索引同口径排除）
        prof = s.get("profile") or "default"
        ev = s.get("evaluated") or {}
        bucket = tracks.setdefault(prof, {})
        for h, res in ev.items():
            oc = (res or {}).get("outcome")
            if oc not in ("hit", "miss", "neutral"):
                continue
            b = bucket.setdefault(str(h), {"n": 0, "hit": 0, "miss": 0,
                                           "neutral": 0})
            b["n"] += 1
            b[oc] += 1
    for prof, bucket in tracks.items():
        for h, b in bucket.items():
            b["insufficient"] = b["n"] < pm.MIN_SAMPLES
    return tracks


def latest_signal_levels(signals, market, code, profile):
    """组内最新信号的 key_levels（价位锚 SSOT 在 signals；07「价位锚分轨」：
    default 三价 / position 波段带三键，各取各轨）。"""
    want = _norm_code(market, code)
    best = None
    for s in signals or []:
        if s.get("snapshot") or s.get("market") != market \
                or _norm_code(market, s.get("code", "")) != want:
            continue  # 快照合成信号不作锚（04：实盘索引排除快照信号）
        if (s.get("profile") or "default") != profile:
            continue
        key = (str(s.get("date", "")), str(s.get("created_at", "")))
        if best is None or key >= best[0]:
            best = (key, s)
    return (best[1].get("key_levels") or {}) if best else None


# ---------------------------------------------------------------- 日差与连向

def _streak(series, rising):
    """末位起连续同向计数。None 是**断链**不是桥接：从最新端往回走原始序列，
    遇 None 即停（中段 None 掐断历史）；最新端自身 None → None（连向不挂在
    缺今日值的卡上）；有效段 <2 → None。"""
    seq = list(series)
    if not seq or seq[-1] is None:
        return None
    n = 0
    for prev, cur in zip(seq[-2::-1], seq[::-1]):
        if prev is None or cur is None:
            break
        if (rising and cur > prev) or (not rising and cur < prev):
            n += 1
        else:
            break
    return n or None


def derive_deltas(recent_cards, card):
    """与前卡的确定性日差 + 近几卡连向计数（纯派生事实，零判断标签）。
    recent_cards=按时间升序的前卡（不含当前）；任何缺值如实缺席。"""
    seq = list(recent_cards or []) + [card]
    prev = seq[-2] if len(seq) >= 2 else None
    changes, streaks = {}, {}
    if prev:
        pp, cp = _f(prev.get("price")), _f(card.get("price"))
        if pp and cp:
            changes["price_pct"] = round((cp / pp - 1) * 100, 2)
        for k in DELTA_KEYS:
            a = _f((prev.get("math", {}).get("mid_term") or {}).get(k))
            b = _f((card.get("math", {}).get("mid_term") or {}).get(k))
            if a is not None and b is not None:
                changes[k] = round(b - a, 4)
    mt_series = [(c.get("math", {}).get("mid_term") or {}) for c in seq]
    streaks["rv60_down"] = _streak([_f(m.get("rv60")) for m in mt_series], False)
    streaks["ret_20d_up"] = _streak([_f(m.get("ret_20d")) for m in mt_series], True)
    streaks["turnover_pctile_250_up"] = _streak(
        [_f(m.get("turnover_pctile_250")) for m in mt_series], True)
    out = {"streaks": {k: v for k, v in streaks.items() if v is not None}}
    if prev:
        out["prev_date"] = prev.get("date")
        out["changes"] = changes
    return out


# ---------------------------------------------------------------- 用户锚（脱敏）

def _read_portfolio_raw(state_dir):
    p = os.path.join(state_dir, "portfolio.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def project_user_anchor(state_dir, market, code, price, band_hi=None):
    """实盘股用户情绪锚（裁定 2；严格脱敏）：只投影 operations 的
    time/action/price 与其后公开行情涨跌% + 现价距波段带上沿%（获利了结
    风险的事实面，对齐用户偏好——零指令）。quantity/cost_price/成本派生
    涨幅绝不读取进产物（负断言钉）。非实盘股返回 None。"""
    raw = _read_portfolio_raw(state_dir)
    if not isinstance(raw, dict):
        return None
    holdings = raw.get("holdings")
    if not isinstance(holdings, list):
        return None
    want = _norm_code(market, code)
    real = any(h.get("market") == market
               and _norm_code(market, h.get("code", "")) == want
               for h in holdings if isinstance(h, dict))
    if not real:
        return None
    ops = []
    for o in raw.get("operations") or []:
        if not isinstance(o, dict) or o.get("market") == "?" or \
                _norm_code(market, o.get("code", "")) != want:
            continue
        op_px, cur = _f(o.get("price")), _f(price)
        item = {"time": o.get("time"), "action": o.get("action"),
                "price": op_px}
        if op_px and cur:
            item["move_pct"] = round((cur / op_px - 1) * 100, 2)
        ops.append(item)
    ops.sort(key=lambda x: str(x.get("time") or ""))  # 时间升序防乱序登记
    out = {"ops": ops[-5:], "note": OPS_NOTE}
    bh = _f(band_hi)
    if bh and _f(price):
        out["band_hi_dist_pct"] = round((price / bh - 1) * 100, 2)
    return out


# ---------------------------------------------------------------- 上下文装配

def load_recent_cards(state_dir, market, code, before_date, max_prev=6):
    """全局时序里的前卡（升序、不含 before_date 当日）——经验日差的输入。
    任何损坏行跳过（派生视图自愈，不阻断）。"""
    d = outlook_dir(state_dir)
    if not os.path.isdir(d):
        return []
    want = _norm_code(market, code)
    found = []
    for name in sorted(os.listdir(d)):
        if not name.endswith(".jsonl") or name[:10] >= str(before_date):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                for line in f:
                    if not line.strip():
                        continue
                    try:
                        c = json.loads(line)
                    except ValueError:
                        continue
                    if c.get("market") == market and \
                            _norm_code(market, c.get("code", "")) == want:
                        found.append(c)
        except OSError:
            continue
    return found[-max_prev:]


def gather_ctx(state_dir, market, code, date, fallback_levels=None):
    """只读装配：signals 切片 / 前卡 / 实盘判定（operations 裸文件在
    project_user_anchor 内部消费）。任一缺即对应维度缺席，绝不阻断。"""
    ctx = {"signals": [], "recent_cards": []}
    try:
        ctx["signals"] = ar.load_signals(os.path.join(state_dir, "signals.json"))
    except (OSError, ValueError):
        pass
    ctx["recent_cards"] = load_recent_cards(state_dir, market, code, date)
    ctx["fallback_levels"] = fallback_levels or None
    return ctx


# ---------------------------------------------------------------- 主派生

def derive_outlook(evidence, ctx):
    """主入口：evidence（fetch/diagnose 产物）+ ctx → 走势参考卡。
    纯函数（同输入同输出）；缺价格/日 K → abstained（仍出卡，pack 如实一行）。"""
    b = evidence.get("blocks", {})
    meta = evidence.get("meta", {})
    market = meta.get("market")
    code = meta.get("code") or str(meta.get("symbol", "")).split(".")[0]
    bars = (b.get("daily_bars") or {}).get("bars") or []
    closes = [bar.get("close") for bar in bars]
    price = _f((b.get("quote") or {}).get("price")) or (
        _f(closes[-1]) if closes else None)
    if price is not None:
        price = round(price, 3)  # 源侧 float32 噪声（yf 港股 8.2600002…）不入卡
    date = str(bars[-1]["date"])[:10] if bars else None
    ss = meta.get("session") or {}
    price_kind = {"intraday": "intraday", "closed": "close"}.get(
        ss.get("phase"), "unknown")
    card = {"schema": SCHEMA, "state": "abstained", "market": market,
            "code": code, "name": (b.get("quote") or {}).get("name"),
            "date": date, "price": price, "price_kind": price_kind,
            "zero_weight_note": ZERO_WEIGHT_NOTE, "band_note": BAND_NOTE,
            "beta_note": BETA_NOTE}
    if market not in ar.MARKETS or not price or not closes or not date:
        card["reason"] = "缺市场/价格/日 K（快照或取数失败形态）——如实弃权"
        return card

    card["state"] = "estimated"
    signals = (ctx or {}).get("signals") or []
    sigma_d, sigma_src = sigma_daily(closes)
    sigma_ann = round(sigma_d * math.sqrt(252), 6) if sigma_d else None
    mt = dict((b.get("technical") or {}).get("mid_term") or {})
    card["math"] = {"sigma_daily": sigma_d, "sigma_src": sigma_src,
                    "mid_term": {k: mt[k] for k in
                                 ("ret_20d", "ret_60d", "ret_6_1", "tsmom_250d",
                                  "rv60", "rv120", "mdd_250", "cur_dd", "ma150",
                                  "ma200", "vr_63d", "max_ret_20d",
                                  "limit_up_count_20d", "turnover_avg_20d",
                                  "turnover_abnormal", "turnover_pctile_250")
                                 if mt.get(k) is not None}}
    tracks = {}
    for prof, key in (("default", ("entry_ref", "stop", "target1")),
                      ("position", ("band_lo", "band_hi", "trail_ref"))):
        horizons = ar.HORIZONS_OF[prof]
        t = {"horizons": horizon_bands(price, sigma_d, horizons)}
        levels = latest_signal_levels(signals, market, code, prof) or {}
        src = "signals"
        if prof == "default" and not any(_f(levels.get(k)) for k in key):
            fb = (ctx or {}).get("fallback_levels") or {}
            if fb:  # sim 股无信号时回退 allocation 三价（levels_source 同 07）
                levels = {k: fb.get(k) for k in key}
                src = "allocation"
        if any(_f(levels.get(k)) for k in key):
            t["anchors_source"] = src
            t["anchors"] = anchor_set(price, sigma_ann,
                                      {k: levels.get(k) for k in key}, horizons)
        else:
            t["anchors_source"] = "abstained"
            if prof == "position":
                t["anchors"] = None
                t["anchors_note"] = "无可用 position 锚（波段带三键以登记信号" \
                                    "为 SSOT，禁现算充锚）"
        tracks[prof] = t
    card["math"]["tracks"] = tracks

    mf = (b.get("moneyflow") or {}).get("summary") or {}
    # 市场级情绪五块投影（0.0.19）：市场维度共享数据，取可用块关键字段；
    # 全缺 → abstained（块状态行在 pack 证据面仍如实可见）
    _mkt_keys = {
        "margin": ("balance_yi", "chg_1d_pct", "chg_5d_pct", "chg_20d_pct",
                   "pctile_70d", "as_of", "source"),
        "index": ("indices", "source"),
        "turnover_pctile": ("pctile", "window", "as_of", "source"),
        "erp": ("erp_pct", "pctile_5y_monthly", "monthly_pe", "y10_pct",
                "as_of", "daily_ready", "source"),
        "margin_accounts": ("traders", "traders_chg_5d_pct",
                            "traders_chg_20d_pct", "debt_holders",
                            "as_of", "source"),
    }
    mkt = {}
    for name, keys in _mkt_keys.items():
        blk = b.get(name) or {}
        if blk.get("state") not in ("available", "partial"):
            continue
        # C1 钉：erp 的 partial 可达形态是「仅日频积累、无数值键」（月频链
        # 失败）——无数值键的块不入卡，防 "ERP None%" 字面量渗进 pack/日表
        if name == "erp" and blk.get("erp_pct") is None:
            continue
        proj = {k: blk.get(k) for k in keys if blk.get(k) is not None}
        if proj:
            mkt[name] = proj
    card["emotion"] = {
        "stock": {k: card["math"]["mid_term"].get(k) for k in
                  ("max_ret_20d", "limit_up_count_20d", "turnover_avg_20d",
                   "turnover_abnormal", "turnover_pctile_250", "vr_63d")
                  if card["math"]["mid_term"].get(k) is not None},
        "moneyflow": mf or None,
        "market": ({"state": "estimated", **mkt} if mkt else
                   {"state": "abstained",
                    "note": "市场级五块全部不可用（状态行见证据面）"})}
    card["experience"] = {"tracks": experience_tracks(signals, market, code),
                          "note": EXP_NOTE}
    card["deltas"] = derive_deltas((ctx or {}).get("recent_cards") or [], card)
    band_hi = ((tracks.get("position", {}).get("anchors") or {})
               .get("band_hi", {}) or {}).get("value")
    card["user_anchor"] = project_user_anchor(
        (ctx or {}).get("state_dir") or STATE_DIR, market, code, price, band_hi)
    return card


def compute_card(evidence, state_dir, fallback_levels=None):
    """workdir/批量共入口：从 evidence 推 (market, code) 并装配上下文。"""
    meta = evidence.get("meta", {})
    market = meta.get("market")
    code = meta.get("code")
    if not code:
        try:
            market, code = fx.detect_market(str(meta.get("symbol", "")))
        except SystemExit:
            market, code = None, None
    if market not in ar.MARKETS or not code:
        return None
    bars = (evidence.get("blocks", {}).get("daily_bars") or {}).get("bars") or []
    date = str(bars[-1]["date"])[:10] if bars else "0000-00-00"
    ctx = gather_ctx(state_dir, market, code, date, fallback_levels)
    ctx["state_dir"] = state_dir
    return derive_outlook(evidence, ctx)


# ---------------------------------------------------------------- 持久化（batch 侧专用）

def persist_card(state_dir, card, now_iso=None):
    """收盘卡入全局时序：<date>.jsonl 按 (market, code) 同日幂等 upsert、
    原子替换。无条件前置：price_kind != "intraday"（盘中卡不入日序——09 写
    拓扑；违者抛 ValueError）。"""
    if card.get("price_kind") == "intraday":
        raise ValueError("盘中卡不入全局时序（收盘后重跑；references/09 写拓扑）")
    date = str(card.get("date") or "")[:10]
    if not date or date.startswith("0000"):
        raise ValueError("卡片缺交易日 date，拒绝落盘")
    card = dict(card)
    card.pop("user_anchor", None)  # 脱敏（S2）：实盘操作价/成本派生涨幅绝不
    # 入全局时序——user_anchor 只在 workdir 现算卡（决策侧 pack/4c 消费）；
    # 全局时序至今无消费方（日差/连向/日表均不读它）
    if now_iso:
        card["persisted_at"] = now_iso
    d = outlook_dir(state_dir)
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, date + ".jsonl")
    rows = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:  # 坏行跳过（与 load_recent_cards 同口径：一行坏
                if not line.strip():  # 数据不得让当日全部 persist 判拒/渲染崩
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue
    want = (card.get("market"), _norm_code(card.get("market"), card.get("code", "")))
    rows = [r for r in rows
            if (r.get("market"), _norm_code(r.get("market"), r.get("code", "")))
            != want]
    rows.append(card)
    rows.sort(key=lambda r: (r.get("market"), str(r.get("code"))))
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:  # tmp+fsync+replace（对齐
        for r in rows:                          # archive._write_atomic 原子性）
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return path


def load_cards(state_dir, date):
    """读某日全部收盘卡（缺文件空表；坏行跳过不崩——派生视图自愈口径）。"""
    path = os.path.join(outlook_dir(state_dir), "%s.jsonl" % date)
    out = []
    if not os.path.exists(path):
        return out
    with open(path, encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                out.append(json.loads(line))
            except ValueError:
                continue
    return out


def latest_cards(state_dir, max_days=10):
    """每股最新一张卡（跨日文件；渲染日表与幂等判断用）。坑位：卡片按末根
    日 K 交易日分文件——盘后数据源更新时差（A 股源末根滞后、港股已出）
    会让同一批次跨两个日文件，按单日读会漏股（2026-11-04 实跑实证）。"""
    d = outlook_dir(state_dir)
    if not os.path.isdir(d):
        return {}
    days = sorted(f[:-6] for f in os.listdir(d) if f.endswith(".jsonl"))
    out = {}
    for day in days[-max_days:]:
        for c in load_cards(state_dir, day):
            key = (c.get("market"), _norm_code(c.get("market"), c.get("code", "")))
            out[key] = c  # 升序遍历：后者覆盖前者
    return out


# ---------------------------------------------------------------- 预测带自校准（P3）

def touch_judgment(bars, card_date, anchor, h):
    """触及判定（校准后验的判定器）：方向按卡日收盘定（first-passage 屏障
    对称——上方锚只看上穿 high≥anchor、下方锚只看回落 low≤anchor；锚在
    现价上方时 low≤anchor 恒真，双向或判是错的）。bars 升序全量日 K；
    不足 h 根 → None（右删防护：不满整窗不记样本——新卡天然不足，等窗满
    再记）；卡日收盘缺失 → None（无方向基准）。"""
    if not bars or anchor is None or not h:
        return None
    base = None
    after = []
    for b in bars:
        d = str(b.get("date", ""))[:10]
        if d == str(card_date):
            base = _f(b.get("close"))
        elif d > str(card_date):
            after.append(b)
    if base is None or len(after) < h:
        return None
    win = after[:h]
    if anchor > base:  # 上方锚：看上穿
        return bool(any((_f(b.get("high")) or 0) >= anchor for b in win))
    if anchor < base:  # 下方锚：看回落
        return bool(any((_f(b.get("low")) or 1e18) <= anchor for b in win))
    return None


def calibration_samples(cards, bars_by_code):
    """历史卡 × 锚 × horizon → (p, touched) 样本流（幂等键 card date+code+
    track+anchor+h；touched=None 的不满窗样本丢弃）。纯函数。qfq 重基准
    防御：bars 全链 adjust=qfq，除权除息后整条历史重定价——卡锚（卡时点
    绝对价）vs 新序列会系统性偏（上方锚触及被压低/下方抬高），卡 price 与
    序列在卡日收盘偏离 >0.5% 判重基准、整卡丢样本。"""
    out = []
    for c in cards or []:
        if c.get("state") != "estimated":
            continue
        key = (c.get("market"), c.get("code"))
        bars = bars_by_code.get(key) or []
        cpx = _f(c.get("price"))
        if cpx:
            base_px = None
            for b in bars:
                if str(b.get("date", ""))[:10] == str(c.get("date", ""))[:10]:
                    base_px = _f(b.get("close"))
                    break
            if base_px and abs(base_px / cpx - 1) > 0.005:
                continue  # 重基准卡整卡丢弃（偏置样本比缺样本更坏）
        for track, t in (c.get("math", {}).get("tracks") or {}).items():
            horizons = ar.HORIZONS_OF.get(track, ())
            for name, a in (t.get("anchors") or {}).items():
                anchor = _f(a.get("value"))
                for h_str, p in (a.get("touch") or {}).items():
                    h = int(h_str)
                    if h not in horizons or _f(p) is None:
                        continue
                    touched = touch_judgment(bars, c.get("date"), anchor, h)
                    if touched is None:
                        continue
                    out.append({"date": c.get("date"), "market": c.get("market"),
                                "code": c.get("code"), "track": track,
                                "anchor": name, "h": h, "p": _f(p),
                                "touched": bool(touched)})
    return out


def calibration_buckets(samples, min_n=30):
    """分桶校准表：p 五桶 [0,.2/.2,.4/.4,.6/.6,.8/.8,1] 的预测均值 vs 实际
    触及频率；n<min_n 标 insufficient（与台账 MIN_SAMPLES 哲学同源、独立
    常量——校准是信息面披露不是绩效因子）。"""
    edges = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)
    out = []
    for lo, hi in zip(edges, edges[1:]):
        bucket = [s for s in samples
                  if lo <= s["p"] < hi or (hi == 1.0 and s["p"] == 1.0)]
        if not bucket:
            continue
        n = len(bucket)
        out.append({"bucket": "%.1f–%.1f" % (lo, hi), "n": n,
                    "mean_p": round(sum(s["p"] for s in bucket) / n, 3),
                    "actual_rate": round(
                        sum(1 for s in bucket if s["touched"]) / n, 3),
                    "insufficient": n < min_n})
    return out


def _valid_cal_row(r):
    """台账行 schema 校验（坏行自愈的宽度口径）：类型损坏行（合法 JSON 但
    h 非整数/p 非数/touched 非布尔等）与缺键行一并跳过——此类行会让 sort/
    buckets 抛异常且崩点在台账写回之后（写回自愈永不触发），必须载入即滤。"""
    return (isinstance(r, dict)
            and isinstance(r.get("date"), str) and r.get("date")
            and isinstance(r.get("market"), str) and r.get("market")
            and isinstance(r.get("code"), str) and r.get("code")
            and isinstance(r.get("track"), str) and r.get("track")
            and isinstance(r.get("anchor"), str) and r.get("anchor")
            and isinstance(r.get("h"), int) and not isinstance(r.get("h"), bool)
            and isinstance(r.get("p"), (int, float))
            and not isinstance(r.get("p"), bool)
            and isinstance(r.get("touched"), bool))


def merge_calibration(state_dir, new_samples, now_iso=None):
    """校准样本台账 append（幂等：键 date+market+code+track+anchor+h 去重；
    坏行/类型损坏行载入即滤、重写时自愈清除；tmp+replace 原子写）。返回
    合并后全量样本。取舍：幂等键不含锚值/p——同键 --force 重跑且锚值更新时
    保留首判样本（台账以首次判定为准，judged_at 不刷新）。"""
    path = os.path.join(state_dir, "outlook-calibration.jsonl")
    seen, rows = set(), []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    r = json.loads(line)
                except ValueError:
                    continue
                if not _valid_cal_row(r):
                    continue
                k = (r.get("date"), r.get("market"), str(r.get("code")),
                     r.get("track"), r.get("anchor"), r.get("h"))
                if k in seen:
                    continue
                seen.add(k)
                rows.append(r)
    for s in new_samples:
        k = (s["date"], s["market"], str(s["code"]), s["track"], s["anchor"],
             s["h"])
        if k in seen:
            continue
        seen.add(k)
        s = dict(s, judged_at=now_iso) if now_iso else dict(s)
        rows.append(s)
    rows.sort(key=lambda r: (str(r.get("date")), str(r.get("market")),
                             str(r.get("code")), str(r.get("track")),
                             str(r.get("anchor")), int(r.get("h") or 0)))
    tmp = path + ".tmp"
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(tmp, "w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    return rows


# ---------------------------------------------------------------- 渲染（数字 SSOT 全在卡）

def render_pack_block(card):
    """pack「走势参考（零权重）」节正文（不含节头；有界 ~15 行；abstained
    如实一行）。节头由 render_context_pack 加；置于扩展块之前（截断序钉）。"""
    if not card or card.get("state") != "estimated":
        return ["弃权：%s（零权重参考，不影响裁决）" % (
            card.get("reason", "数据不足") if card else "无卡片")]

    def _d(v):  # C1 收口：投影端滤 None 键后渲染端不得再渗 "None%" 字面量
        return "—" if v is None else v

    L = []
    m = card.get("math", {})
    L.append("σ_d=%s（%s）· 预测带=零漂移 ±σ_d×√h（%s；触及概率为 "
             "first-passage 连续监测口径，离散日监测高估、短窗更甚——参考上限）" % (
                 m.get("sigma_daily"), m.get("sigma_src"), BAND_NOTE))
    for prof, label in (("default", "短线 T+1/3/5/10"), ("position", "中线 T+20/60/120")):
        t = (m.get("tracks") or {}).get(prof) or {}
        hz = t.get("horizons") or {}
        if hz:
            L.append("%s 带宽%%：%s" % (label, " / ".join(
                "T+%s=%s" % (h, v.get("band_pct")) for h, v in hz.items())))
        anchors = t.get("anchors") or {}
        if not anchors and t.get("anchors_source") == "abstained":
            # 弃权可见化（0.0.24）：弃权事实与原因进消费面——pack/4c 此前
            # 只以「锚行结构性缺失」呈现，读者无从区分缺锚与弃权
            L.append("%s 锚：弃权——%s" % (label, t.get("anchors_note")
                                           or "无可用锚"))
        # 锚来源标注（0.0.24）：allocation 回退三价禁被读成登记信号价位
        src_tag = "（allocation）" if t.get("anchors_source") == \
            "allocation" else ""
        for name, a in anchors.items():
            touch = a.get("touch") or {}
            tp = " ".join("T+%s:%s%%" % (h, round(p * 100, 1))
                          for h, p in touch.items())
            # 方向显式化：锚在现价上方=上穿触及、下方=回落触及（first-passage
            # 屏障对称，数值同式——不标方向会把「回落触及」误读成「涨到」）
            arrow = "↑上穿" if (a.get("dist_pct") or 0) > 0 else "↓回落"
            L.append("%s 锚%s %s=%s（距 %s%%%s）" % (
                label, src_tag, name, a.get("value"), a.get("dist_pct"),
                " · %s触及 %s" % (arrow, tp) if tp else ""))
    em = card.get("emotion", {})
    stk = " ".join("%s=%s" % (k, v) for k, v in (em.get("stock") or {}).items())
    if stk:
        L.append("个股情绪：%s（口径同 mid_term：max_ret_20d/换手键为百分数、"
                 "vr_63d 为比值——见 references/08）" % stk)
    mf = em.get("moneyflow") or {}
    mfs = " ".join("%s=%s" % (k, v) for k, v in mf.items() if v is not None)
    if mfs:
        L.append("资金面：%s（A 股主力净额亿元 / 港股南向持股比百分点变化）" % mfs)
    mk = em.get("market") or {}
    if mk.get("state") == "estimated":
        parts = []
        mg = mk.get("margin") or {}
        if mg:
            parts.append("两融 %s 亿（Δ5d %s%%·分位 %s%%）" % (
                _d(mg.get("balance_yi")), _d(mg.get("chg_5d_pct")),
                _d(mg.get("pctile_70d"))))
        tp = mk.get("turnover_pctile") or {}
        if tp:
            parts.append("全A换手分位 %s%%" % _d(tp.get("pctile")))
        ep = mk.get("erp") or {}
        if ep:
            parts.append("ERP %s%%（分位 %s%%）" % (
                _d(ep.get("erp_pct")), _d(ep.get("pctile_5y_monthly"))))
        ma = mk.get("margin_accounts") or {}
        if ma:
            parts.append("两融参与 %s 户（Δ5d %s%%）" % (
                _d(ma.get("traders")), _d(ma.get("traders_chg_5d_pct"))))
        if parts:
            L.append("市场级情绪：%s（市场维度共享数据·T+1 披露为主）"
                     % " · ".join(parts))
    exp = (card.get("experience", {}).get("tracks") or {})
    for prof, bucket in exp.items():
        parts = ["T+%s:%s样本%s" % (h, b.get("n"),
                                    "（不足）" if b.get("insufficient") else "")
                 for h, b in bucket.items()]
        if parts:
            L.append("经验计数（%s 轨，%s）：%s" % (prof, EXP_NOTE, " · ".join(parts)))
    d = card.get("deltas") or {}
    ch = d.get("changes") or {}
    if ch:
        L.append("日差（vs %s）：%s" % (d.get("prev_date"), " ".join(
            "%s=%s" % (k, v) for k, v in ch.items())))
    st = d.get("streaks") or {}
    if st:
        L.append("连向：%s" % " ".join("%s×%s" % (k, v) for k, v in st.items()))
    ua = card.get("user_anchor")
    if ua:
        ops = "；".join("%s %s@%s（后 %s%%）" % (
            str(o.get("time"))[:10], o.get("action"), o.get("price"),
            o.get("move_pct")) for o in ua.get("ops", []))
        bh = ua.get("band_hi_dist_pct")
        L.append("用户锚：%s%s%s" % (
            ops or "无近期操作记录",
            " · 现价距波段带上沿 %s%%" % bh if bh is not None else "",
            "（%s）" % OPS_NOTE if ops else ""))
    L.append(ZERO_WEIGHT_NOTE)
    # 满卡破坏性实验钉：内容行超界时截内容（声明恒为末行不被截——LLM 在最
    # 需要边界声明的实盘满卡上恰不能丢「不进裁决」）
    if len(L) > 16:
        L = L[:15] + [ZERO_WEIGHT_NOTE]
    return L


def render_report_section(card):
    """报告 4c 节（04 规约）：state != estimated 不出节（不硬凑）。"""
    if not card or card.get("state") != "estimated":
        return []
    L = ["", "## 短/中期走势参考（零权重 · 不进裁决）"]
    L.extend("  " + ln if ln.startswith(("短线", "中线")) else "- " + ln
             for ln in render_pack_block(card)
             if ln != ZERO_WEIGHT_NOTE)  # 声明由本节末尾统一重述
    L.append("- %s" % card["band_note"])
    L.append("- %s" % card["beta_note"])
    L.append("- %s——本节不构成投资建议。" % ZERO_WEIGHT_NOTE)
    return L


def render_day_row(card):
    """日表一行（batch 渲染 <date>.md 用）：短/中带宽 + 最新信号经验 + 情绪
    概览；abstained 如实标注。零指令、脱敏（只含公开行情派生量）。"""
    if card.get("state") != "estimated":
        return {"code": card.get("code"), "market": card.get("market"),
                "name": card.get("name"), "state": "abstained",
                "reason": card.get("reason", "")}
    m = card.get("math", {})
    t_def = (m.get("tracks") or {}).get("default", {}).get("horizons", {})
    t_pos = (m.get("tracks") or {}).get("position", {}).get("horizons", {})
    exp = (card.get("experience", {}).get("tracks") or {}).get("default", {})
    return {"code": card.get("code"), "market": card.get("market"),
            "name": card.get("name"), "state": "estimated",
            "date": card.get("date"), "price": card.get("price"),
            "band_10d_pct": (t_def.get("10") or {}).get("band_pct"),
            "band_60d_pct": (t_pos.get("60") or {}).get("band_pct"),
            "exp_t1": exp.get("1"), "exp_t10": exp.get("10"),
            "turnover_pctile_250": m.get("mid_term", {}).get(
                "turnover_pctile_250"),
            "limit_up_count_20d": m.get("mid_term", {}).get(
                "limit_up_count_20d")}


# ---------------------------------------------------------------- selftest

def selftest():
    print("== outlook selftest（零网络纯函数 + 破坏性实验） ==")
    import tempfile
    # ---- 合成 fixture（零重合由文末动态负断言保证——不假设任何码段永非真码）
    bars, px = [], 100.0
    for i in range(200):
        px *= 1.021 if i % 2 else 0.988
        bars.append({"date": "2026-06-%02d" % (i % 28 + 1), "open": px,
                     "high": px * 1.01, "low": px * 0.99,
                     "close": round(px, 4), "volume": 1000 + i})
    closes = [b["close"] for b in bars]
    pe = closes[-1]  # 末价：锚位按相对价构造（合成列净上行 ≈2.4×）

    def ev(**kw):
        blocks = {"quote": {"price": round(px, 3), "name": "合成fixture"},
                  "daily_bars": {"bars": bars},
                  "technical": {"mid_term": {
                      "ret_20d": 0.05, "ret_60d": 0.12, "rv60": 0.28,
                      "vr_63d": 1.05, "max_ret_20d": 0.04,
                      "limit_up_count_20d": 1, "turnover_avg_20d": 2.1,
                      "turnover_abnormal": 1.3, "turnover_pctile_250": 88.0}},
                  "moneyflow": {"summary": {"main_net_20d_yi": 3.2,
                                            "main_net_60d_yi": 8.9}}}
        blocks.update(kw.pop("blocks", {}))
        e = {"meta": {"symbol": "999999", "market": "cn", "code": "999999",
                      "session": {"phase": "closed"}}, "blocks": blocks,
             "quality": {"score": 90}}
        e.update(kw)
        return e

    def sig(**kw):
        s = {"market": "cn", "code": "999999", "profile": "default",
             "date": "2026-11-01", "created_at": "2026-11-01T16:00",
             "key_levels": {"entry_ref": round(pe * 0.97, 2),
                            "stop": round(pe * 0.94, 2),
                            "target1": round(pe * 1.08, 2)},
             "evaluated": {}}
        s.update(kw)
        return s

    ctx = {"signals": [sig(evaluated={"1": {"outcome": "hit"},
                                      "3": {"outcome": "neutral"},
                                      "10": {"outcome": "miss"}}),
                       sig(evaluated={"1": {"outcome": "hit"}}),
                       sig(profile="position", date="2026-11-02",
                           created_at="2026-11-02T16:00",
                           key_levels={"band_lo": round(pe * 0.92, 2),
                                       "band_hi": round(pe * 1.05, 2),
                                       "trail_ref": round(pe * 0.99, 2)},
                           evaluated={"60": {"outcome": "hit"}})],
          "recent_cards": [], "state_dir": "/nonexistent-outlook-ctx"}
    card = derive_outlook(ev(), ctx)

    # ① 状态与结构
    assert card["state"] == "estimated" and card["schema"] == SCHEMA
    assert card["date"] == bars[-1]["date"][:10]
    assert card["price_kind"] == "close"
    # 固定文案逐字钉（两把尺分立 + 零权重边界 + beta 局限）
    assert card["band_note"] == BAND_NOTE == (
        "预测带≠后验判定带：default 轨 ±2% 固定带、position 轨 σ√h 带仅 "
        "T+60 记分（references/05）——本带只描述价格分布量级")
    assert "不进裁决聚合" in ZERO_WEIGHT_NOTE and "RiskGuard" in ZERO_WEIGHT_NOTE
    assert "beta" in card["beta_note"]
    json.dumps(card, allow_nan=False)

    # ② σ 与预测带数学：σ_d=rv/√252；带宽 ∝ √h 单调
    sd, src = sigma_daily(closes)
    rv60 = fx.realized_vol(closes, 60)
    assert src == "60d" and abs(sd - rv60 / math.sqrt(252)) < 1e-6
    bands = card["math"]["tracks"]["default"]["horizons"]
    assert [bands[k]["band_pct"] for k in ("1", "3", "5", "10")] == \
        sorted(bands[k]["band_pct"] for k in ("1", "3", "5", "10"))
    for h, v in bands.items():
        assert abs(v["hi"] - v["lo"]) / 2 / card["price"] * 100 - \
            v["band_pct"] < 0.01
        assert v["lo"] < card["price"] < v["hi"]
    assert sigma_daily([]) == (None, None)
    # 退化链：常数列 rv=None → floor
    assert sigma_daily([10.0] * 100)[1] == "floor_2pct"
    assert sigma_daily([10.0] * 100)[0] == SIGMA_FLOOR

    # ③ 锚投影：距锚百分比 + 触及概率单调（锚越远概率越低）
    anchors = card["math"]["tracks"]["default"]["anchors"]
    assert anchors["target1"]["dist_pct"] > 0 > anchors["stop"]["dist_pct"]
    t = anchors["target1"]["touch"]
    assert t["1"] <= t["10"], "同锚远 horizon 触及概率不减"
    near = anchor_set(100.0, 0.3, {"a": 101.0}, (1, 10))
    far = anchor_set(100.0, 0.3, {"a": 120.0}, (1, 10))
    assert near["a"]["touch"]["10"] > far["a"]["touch"]["10"]
    assert anchor_set(100.0, 0.3, {"bad": None, "neg": -5}, ()) == {}
    # position 锚：band_hi/band_lo/trail_ref 全在；无 position 信号 → abstain
    pans = card["math"]["tracks"]["position"]["anchors"]
    assert set(pans) == {"band_lo", "band_hi", "trail_ref"}
    ctx_np = dict(ctx, signals=[s for s in ctx["signals"]
                                if s.get("profile") != "position"])
    card_np = derive_outlook(ev(), ctx_np)
    tp = card_np["math"]["tracks"]["position"]
    assert tp["anchors"] is None and "禁现算充锚" in tp["anchors_note"]
    # 港股补 5 位归一：signals 存 5 位、evidence 用 4 位旧形态（真实互通用例
    # ——fixture 码 88000/合成段，零重合负断言在文末动态覆盖）
    hk_sig = [sig(market="hk", code="08800", key_levels={
        "entry_ref": round(pe * 0.98, 2), "stop": round(pe * 0.95, 2),
        "target1": round(pe * 1.06, 2)})]
    hk_ev = ev(meta={"symbol": "hk8800", "market": "hk", "code": "8800",
                     "session": {"phase": "closed"}})
    hk_card = derive_outlook(hk_ev, dict(ctx, signals=hk_sig))
    assert hk_card["math"]["tracks"]["default"]["anchors"]["stop"]["value"] \
        == round(pe * 0.95, 2)

    # ④ 经验计数：桶聚合 + MIN_SAMPLES 降级（SSOT import 自 postmortem）
    exp = card["experience"]["tracks"]["default"]
    assert exp["1"]["n"] == 2 and exp["1"]["hit"] == 2
    assert exp["3"]["n"] == 1 and exp["3"]["neutral"] == 1
    assert exp["10"]["n"] == 1 and exp["10"]["miss"] == 1
    assert exp["1"]["insufficient"] is True  # 2 < MIN_SAMPLES
    big = [sig(evaluated={"1": {"outcome": "hit"}}) for _ in range(
        pm.MIN_SAMPLES)]
    assert experience_tracks(big, "cn", "999999")["default"]["1"][
        "insufficient"] is False
    assert pm.MIN_SAMPLES == 10, "小样本阈值 SSOT 漂移"
    # observed 不入桶（watch/hold 只观察不记分——05 口径）：无 scorable 键
    obs = [sig(evaluated={"1": {"outcome": "observed"}})]
    assert experience_tracks(obs, "cn", "999999")["default"] == {}
    assert "非绩效因子" in card["experience"]["note"]

    # ⑤ 日差与连向：前卡 join + 纯派生
    prev = {"date": "2026-11-03", "price": card["price"] * 0.98,
            "math": {"mid_term": {"rv60": card["math"]["mid_term"]["rv60"]
                                  + 0.02, "ret_20d": 0.04,
                                  "turnover_pctile_250": 80.0}}}
    card_d = derive_outlook(ev(), dict(ctx, recent_cards=[prev]))
    ch = card_d["deltas"]["changes"]
    assert abs(ch["price_pct"] - round(100 / 0.98 - 100, 2)) < 0.01
    assert abs(ch["rv60"] + 0.02) < 1e-9
    assert card_d["deltas"]["streaks"]["rv60_down"] == 1  # rv60 下降 1 日
    assert card_d["deltas"]["streaks"]["ret_20d_up"] == 1
    # 连向断链（M1 语义钉）：None 是断链不是桥接——中段缺值掐断历史
    # [T-3=0.40, T-2=None, T-1=σ+0.02, 今日=σ] → 连向=1（桥接旧实现会给 2）
    rv_today = card["math"]["mid_term"]["rv60"]
    card_m = derive_outlook(ev(), dict(ctx, recent_cards=[
        {"date": "d1", "price": 1.0, "math": {"mid_term": {"rv60": 0.40}}},
        {"date": "d2", "price": 1.0, "math": {"mid_term": {}}},
        {"date": "d3", "price": 1.0,
         "math": {"mid_term": {"rv60": round(rv_today + 0.02, 4)}}}]))
    assert card_m["deltas"]["streaks"]["rv60_down"] == 1
    # 前卡整体缺值：连向不挂在缺基期上
    card_d2 = derive_outlook(ev(), dict(ctx, recent_cards=[
        {"date": "d0", "price": None, "math": {"mid_term": {}}}]))
    assert "rv60_down" not in card_d2["deltas"]["streaks"]
    # 无前卡：只有 streaks 无 changes
    assert "changes" not in card["deltas"]

    # ⑥ 脱敏负断言：产物不得含 quantity/cost_price/金额/成本派生键
    def _walk(o, hits):
        if isinstance(o, dict):
            for k, v in o.items():
                if str(k).lower() in ("quantity", "qty", "cost_price", "cost",
                                      "amount", "pnl", "pnl_pct", "market_value"):
                    hits.append(k)
                _walk(v, hits)
        elif isinstance(o, list):
            for v in o:
                _walk(v, hits)
    with tempfile.TemporaryDirectory() as td:
        with open(os.path.join(td, "portfolio.json"), "w",
                  encoding="utf-8") as f:
            json.dump({"holdings": [{"code": "999999", "market": "cn",
                                     "quantity": 123,
                                     "cost_price": 88.8}],
                       "operations": [{"code": "999999", "market": "cn",
                                       "time": "2026-11-01T10:00:00+08:00",
                                       "action": "buy", "price": 90.0,
                                       "quantity": 100}]}, f)
        ua = project_user_anchor(td, "cn", "999999", card["price"], 120.0)
        assert ua["ops"] == [{"time": "2026-11-01T10:00:00+08:00",
                              "action": "buy", "price": 90.0,
                              "move_pct": round(
                                  (card["price"] / 90.0 - 1) * 100, 2)}]
        assert ua["band_hi_dist_pct"] == round(
            (card["price"] / 120.0 - 1) * 100, 2)
        card_u = derive_outlook(ev(), dict(ctx, state_dir=td))
        hits = []
        _walk(card_u, hits)
        assert not hits, "脱敏违例键：%s" % hits
        # 非实盘（sim/watch）：无用户锚
        assert project_user_anchor(td, "cn", "888888", 10.0) is None
        assert project_user_anchor("/nonexistent", "cn", "999999", 10.0) is None

    # ⑦ 弃权：缺 K → abstained；quote 缺失但日 K 在 → 价格回落末根收盘
    #    （quote 本就是日 K 派生块，回落是既有口径不是虚构）
    c = derive_outlook(ev(blocks={"daily_bars": {"bars": []}}), ctx)
    assert c["state"] == "abstained" and c.get("reason")
    c2 = derive_outlook(ev(blocks={"quote": {"state": "missing"}}), ctx)
    assert c2["state"] == "estimated" and c2["price"] == round(closes[-1], 3)
    snap = derive_outlook(ev(meta={"symbol": "600519", "market": "?",
                                   "snapshot": True}), ctx)
    assert snap["state"] == "abstained"

    # ⑧ 渲染：pack 有界、报告节不出 abstained、日表行脱敏
    lines = render_pack_block(card)
    assert len(lines) <= 16 and any("预测带" in ln for ln in lines)
    # 满卡破坏性实验（S3 钉）：内容行超界截内容、零权重声明恒为末行；
    # 报告节声明自述不受 pack 截界影响
    full = json.loads(json.dumps(card))
    full["experience"]["tracks"]["position"] = {
        "60": {"n": 3, "hit": 2, "miss": 1, "neutral": 0, "insufficient": True}}
    full["user_anchor"] = {"ops": [{"time": "2026-11-01T10:00:00+08:00",
                                    "action": "buy", "price": 90.0,
                                    "move_pct": 1.0}],
                           "band_hi_dist_pct": -3.1, "note": OPS_NOTE}
    full["deltas"] = {"prev_date": "2026-11-03",
                      "changes": {"price_pct": 1.2}, "streaks": {"rv60_down": 2}}
    flines = render_pack_block(full)
    assert len(flines) == 16 and flines[-1] == ZERO_WEIGHT_NOTE, \
        "满卡必须截内容不截声明（%d 行，末行=%r）" % (len(flines), flines[-1])
    fsec = render_report_section(full)
    assert fsec[-1].endswith("本节不构成投资建议。")
    # 触及方向显式化钉：上方锚=↑上穿、下方锚=↓回落（防把回落触及读成涨到）
    assert any("target1" in ln and "↑上穿触及" in ln for ln in lines)
    assert any("stop" in ln and "↓回落触及" in ln for ln in lines)
    assert any(ln.startswith("资金面：") for ln in lines)
    # 弃权可见化钉（0.0.24）：position 无锚卡（card_np 即该形态）须出注记行
    # ——弃权事实进消费面，不得以锚行结构性缺失静默呈现
    assert any(ln.startswith("中线") and "锚：弃权——" in ln and
               "禁现算" in ln for ln in render_pack_block(card_np)), \
        "position 弃权须在 pack 可见"
    assert any(ln.strip().startswith("中线") and "锚：弃权——" in ln
               for ln in render_report_section(card_np)), \
        "position 弃权须进报告 4c 节"
    # allocation 回退锚来源标注钉（0.0.24）：sim 股三价禁被读成登记信号价位
    card_fb = derive_outlook(ev(), dict(ctx, signals=[], fallback_levels={
        "stop": round(closes[-1] * 0.95, 2),
        "entry_ref": round(closes[-1] * 0.98, 2),
        "target1": round(closes[-1] * 1.06, 2)}))
    assert card_fb["math"]["tracks"]["default"]["anchors_source"] == \
        "allocation"
    assert any(ln.startswith("短线") and "锚（allocation）" in ln
               for ln in render_pack_block(card_fb)), \
        "allocation 回退锚须在 pack 标注来源"
    assert render_pack_block({"state": "abstained", "reason": "x"}) == \
        ["弃权：x（零权重参考，不影响裁决）"]
    assert render_report_section(None) == []
    assert render_report_section({"state": "abstained"}) == []
    sec = render_report_section(card)
    assert sec[1].startswith("## 短/中期走势参考") and sec[-1].endswith(
        "本节不构成投资建议。")
    row = render_day_row(card)
    assert row["state"] == "estimated" and row["band_10d_pct"] == \
        card["math"]["tracks"]["default"]["horizons"]["10"]["band_pct"]
    hits = []
    _walk(render_day_row(card), hits)
    assert not hits
    _walk(render_pack_block(card), hits)
    assert not hits

    # ⑨ 持久化：upsert 幂等 + 盘中拒落盘 + 原子性（读回一致）
    with tempfile.TemporaryDirectory() as td:
        c1 = derive_outlook(ev(), ctx)
        p1 = persist_card(td, c1, "2026-11-04T17:30:00+08:00")
        c1b = derive_outlook(ev(), dict(ctx, recent_cards=[]))
        c1b["price"] = c1b["price"] * 1.01  # 同日新版本
        persist_card(td, c1b, "2026-11-04T18:00:00+08:00")
        cards = load_cards(td, c1["date"])
        assert len(cards) == 1 and cards[0]["price"] == c1b["price"], \
            "同日同股须 upsert 单行"
        # S2 脱敏钉：全局时序卡不得含 user_anchor（操作价/成本派生涨幅只住
        # workdir 现算卡；全局时序至今无该维度消费方）
        assert "user_anchor" not in cards[0], cards[0].get("user_anchor")
        # 跨日合并：源末根时差让同批次分落两个交易日文件，latest_cards 每股
        # 取最新一张、不漏股（2026-11-04 实跑实证）
        c_old = dict(c1, date="2026-01-02", code="888888", price=1.0)
        persist_card(td, c_old)
        lc = latest_cards(td)
        assert ("cn", "999999") in lc and ("cn", "888888") in lc, lc.keys()
        assert lc[("cn", "999999")]["price"] == c1b["price"]
        # 源侧 float32 噪声取整（yf 港股 8.2600002… 实测）
        noisy = derive_outlook(ev(blocks={"quote": {"price": 8.260000228881836}}),
                               ctx)
        assert noisy["price"] == 8.26
        intraday = derive_outlook(
            ev(meta={"symbol": "999999", "market": "cn", "code": "999999",
                     "session": {"phase": "intraday"}}), ctx)
        try:
            persist_card(td, intraday)
            raise AssertionError("盘中卡必须拒落盘")
        except ValueError:
            pass
        # 零重合断言（I-007 红线）：fixture (market, code) ∩ 真实持仓∪成交流
        # == ∅——两侧 _norm_code 归一（4/5 位互通），动态比对全量真实码
        real = _read_portfolio_raw(STATE_DIR)
        if real:
            real_keys = set()
            for it in list(real.get("holdings") or []) + \
                    list(real.get("operations") or []):
                if isinstance(it, dict) and it.get("market") in ar.MARKETS:
                    real_keys.add((it["market"],
                                   _norm_code(it["market"], it.get("code", ""))))
            fx_keys = {("cn", "999999"), ("cn", "888888"),
                       ("hk", "88000"), ("hk", "08800")}
            clash = fx_keys & real_keys
            assert not clash, "fixture 与真实持仓零重合被破坏：%s" % clash

    # ⑩-前 市场级情绪五块投影（0.0.19）：可用块入卡、pack 出市场级行；
    #     全缺 abstained；hk not_supported 不入
    ev_mkt = ev(blocks={
        "margin": {"state": "available", "source": "dc-margin",
                   "balance_yi": 22988.6, "chg_1d_pct": 0.1,
                   "chg_5d_pct": 0.8, "chg_20d_pct": 2.1,
                   "pctile_70d": 88.0, "as_of": "2026-11-03"},
        "turnover_pctile": {"state": "available", "source": "tx-idx",
                            "pctile": 71.2, "window": 250,
                            "as_of": "2026-11-03"},
        "erp": {"state": "available", "source": "legu-pe+dc-bond+csindex",
                "erp_pct": 3.1, "pctile_5y_monthly": 42.0,
                "monthly_pe": 16.2, "y10_pct": 2.9, "as_of": "2026-10",
                "daily_ready": False},
        "margin_accounts": {"state": "available", "source": "em-mkt-account",
                            "traders": 324753.0, "traders_chg_5d_pct": 8.1,
                            "traders_chg_20d_pct": -0.4,
                            "debt_holders": 280123.0, "as_of": "2026-11-03"},
        "index": {"state": "available", "source": "tx-idx",
                  "indices": {"HS300": {"as_of": "2026-11-03",
                                        "close": 4008.9, "ma60": 3950.2,
                                        "dist_ma60_pct": 1.5}}}})
    card_m = derive_outlook(ev_mkt, ctx)
    mkt = card_m["emotion"]["market"]
    assert mkt["state"] == "estimated" and set(
        mkt) >= {"margin", "turnover_pctile", "erp", "margin_accounts",
                 "index"}, mkt.keys()
    assert mkt["margin"]["balance_yi"] == 22988.6
    assert mkt["margin_accounts"]["traders"] == 324753.0
    assert any(ln.startswith("市场级情绪：") for ln in render_pack_block(card_m))
    assert card["emotion"]["market"]["state"] == "abstained", \
        "无市场块 fixture 须 abstained"
    hk_only = derive_outlook(
        ev(meta={"symbol": "hk8800", "market": "hk", "code": "8800",
                 "session": {"phase": "closed"}},
           blocks={"margin": {"state": "not_supported"},
                   "index": {"state": "not_supported"},
                   "turnover_pctile": {"state": "not_supported"},
                   "erp": {"state": "not_supported"},
                   "margin_accounts": {"state": "not_supported"}}),
        dict(ctx, signals=hk_sig))
    assert hk_only["emotion"]["market"]["state"] == "abstained"
    # C1 破坏性钉：erp partial「仅日频积累、无数值键」形态不入卡——防
    # "ERP None%" 字面量渗进 pack/日表（月频链失败是五新源的常态路径）
    ev_erp_part = ev(blocks={
        "erp": {"state": "partial", "source": "csindex",
                "daily_pe_accum": 20, "daily_ready": False},
        "turnover_pctile": {"state": "available", "source": "tx-idx",
                            "pctile": 71.2, "window": 250,
                            "as_of": "2026-11-03"}})
    card_ep = derive_outlook(ev_erp_part, ctx)
    mk_ep = card_ep["emotion"]["market"]
    assert mk_ep["state"] == "estimated" and "erp" not in mk_ep \
        and "turnover_pctile" in mk_ep, mk_ep.keys()
    assert "None" not in "".join(render_pack_block(card_ep)), \
        "pack 不得出现 None 字面量"
    # ⑩-前2 预测带自校准（P3）：触及判定/样本/分桶/幂等台账
    cb = [{"date": "2026-06-01", "open": 10, "high": 10.5, "low": 9.8,
           "close": 10.2, "volume": 1},
          {"date": "2026-06-02", "open": 10, "high": 11.0, "low": 10.0,
           "close": 10.8, "volume": 1},
          {"date": "2026-06-03", "open": 10, "high": 10.4, "low": 9.5,
           "close": 9.9, "volume": 1},
          {"date": "2026-06-04", "open": 10, "high": 10.2, "low": 9.9,
           "close": 10.0, "volume": 1}]
    assert touch_judgment(cb, "2026-06-01", 10.9, 1) is True   # 卡后首根 high 11.0 上穿
    assert touch_judgment(cb, "2026-06-01", 11.5, 3) is False  # 窗内最高 11.0 未及
    assert touch_judgment(cb, "2026-06-01", 9.6, 2) is True    # low 9.5 回落触及
    assert touch_judgment(cb, "2026-06-01", 10.9, 5) is None, "不满窗不记（右删防护）"
    assert touch_judgment(cb, "2026-06-01", None, 2) is None
    cal_card = {"state": "estimated", "market": "cn", "code": "999999",
                "date": "2026-06-01", "price": 10.2,  # 卡日收盘（qfq 防御基准）
                "math": {"tracks": {"default": {"anchors": {
                    "target1": {"value": 10.9,
                                "touch": {"1": 0.3, "3": 0.5}},
                    "stop": {"value": 9.7,
                             "touch": {"1": 0.4, "3": 0.6}}}}}}}
    smp = calibration_samples([cal_card], {("cn", "999999"): cb})
    # 卡日收盘 10.2：target1=10.9 上穿锚（h=1 即触，06-02 high 11.0）；
    # stop=9.7 回落锚（h=1 未触 low 10.0，h=3 触 06-03 low 9.5）
    assert {(s["anchor"], s["h"], s["touched"]) for s in smp} == {
        ("target1", 1, True), ("target1", 3, True),
        ("stop", 1, False), ("stop", 3, True)}, smp
    many = ([dict(s, p=0.1, touched=False) for s in smp] +
            [dict(s, p=0.9, touched=True) for s in smp] * 35)
    bk = calibration_buckets(many)
    assert any(b["n"] >= 30 and not b["insufficient"] and
               b["actual_rate"] == 1.0 for b in bk
               if b["bucket"].startswith("0.8")), bk
    assert all(b["insufficient"] for b in bk if b["n"] < 30)
    with tempfile.TemporaryDirectory() as td_c:
        r1 = merge_calibration(td_c, smp, "2026-11-04T20:00:00+08:00")
        assert len(r1) == len(smp)
        r2 = merge_calibration(td_c, smp)  # 幂等：重复合并零增
        assert r2 == r1
        with open(os.path.join(td_c, "outlook-calibration.jsonl"),
                  encoding="utf-8") as f:
            assert len([l for l in f if l.strip()]) == len(smp)
        with open(os.path.join(td_c, "outlook-calibration.jsonl"), "a",
                  encoding="utf-8") as f:  # 坏行/标量行/类型损坏行自愈
            f.write("not-json\n123\n"
                    '{"date":"2026-06-01","market":"cn","code":"1","track":'
                    '"default","anchor":"t","h":"x","p":0.3,"touched":true}\n'
                    '{"date":"2026-06-01","market":"cn","code":"1","track":'
                    '"default","anchor":"t","p":0.3}\n')
        r3 = merge_calibration(td_c, [])
        assert len(r3) == len(smp), "类型损坏行须载入即滤（防 sort/buckets 毒丸）"
        assert all(_valid_cal_row(r) for r in r3)
    # qfq 重基准防御钉：卡 price 与序列卡日收盘偏离 >0.5% → 整卡丢样本
    rebase_bars = [dict(b, close=round(b["close"] * 0.8, 3))  # 模拟除权重定价
                   for b in cb]
    assert calibration_samples([cal_card], {("cn", "999999"): rebase_bars}) == []
    near_bars = [dict(b, close=round(b["close"] * 1.004, 3))  # 0.4% 噪声不丢
                 for b in cb]
    assert calibration_samples([cal_card], {("cn", "999999"): near_bars}), \
        "≤0.5% 偏离属正常价差噪声，不得丢样本"

    # C1 扩展钉：margin 缺变动/分位键（短序列残块形态）——渲染端 _d 兜底
    # 出「—」而非 "None%" 字面量（投影端滤键只堵了入卡侧，渲染侧是第二道）
    ev_mg_part = ev(blocks={
        "margin": {"state": "available", "source": "dc-margin",
                   "balance_yi": 22988.6, "as_of": "2026-11-03"}})
    card_mg = derive_outlook(ev_mg_part, ctx)
    mk_mg = card_mg["emotion"]["market"]
    assert mk_mg["state"] == "estimated" and "margin" in mk_mg \
        and "chg_5d_pct" not in mk_mg["margin"], mk_mg.keys()
    _mg_line = "".join(ln for ln in render_pack_block(card_mg)
                       if ln.startswith("市场级情绪："))
    assert _mg_line and "None" not in _mg_line and "—" in _mg_line, _mg_line
    #     质量分与置信帽——裁决对走势参考结构性零感知（outlook 无意见通道，
    #     LLM 只能引用其数字作 rationale 素材，与 mid_term 同地位）
    import adjudicate as aj
    ev_base = {"meta": {"symbol": "999999", "market": "cn"},
               "blocks": {"quote": {"state": "available"},
                          "daily_bars": {"state": "available"},
                          "technical": {"state": "available"}}}
    ev_with = json.loads(json.dumps(ev_base))
    ev_with["blocks"]["outlook"] = card          # 卡片作为伪扩展块挂入
    ev_with["outlook_card"] = card               # 顶层冗余键（前向兼容面）
    assert aj.evidence_cap(ev_with) == aj.evidence_cap(ev_base), \
        "outlook 卡不得扰动质量分/置信帽（E4 同构）"
    # 收官钉（0.0.24 · I-023）：强制防线收编进纯函数件——墙钟门/末根过滤/
    # 真实增量计数此前住编排层（batch 无 selftest，回归无门禁可拦）；
    # touch 对称补钉（规约声称「对称/单调」，此前只有单调）
    assert close_gate_open(dt.datetime(2026, 11, 4, 17, 10)) and \
        close_gate_open(dt.datetime(2026, 11, 4, 23, 59))
    assert not close_gate_open(dt.datetime(2026, 11, 4, 17, 9)) and \
        not close_gate_open(dt.datetime(2026, 11, 4, 9, 30)), \
        "墙钟门 17:10 边界（含）双侧钉"
    _sp_orig = fx.session_phase
    fx.session_phase = lambda m, d, now=None: \
        {"last_bar_partial": d == "2026-11-05"}
    try:
        assert final_bars([{"date": "2026-11-04"}, {"date": "2026-11-05"}],
                          "cn") == [{"date": "2026-11-04"}], \
            "末根未完成须滤（--force 越过墙钟门后的根本防线）"
        assert final_bars([{"date": "2026-11-04"}], "cn") == \
            [{"date": "2026-11-04"}], "已定型末根不动"
        assert final_bars([], "cn") == []
    finally:
        fx.session_phase = _sp_orig
    _cnt_rows = [{"judged_at": "t1"}, {"judged_at": "t2"},
                 {"judged_at": "t2"}, {}]
    assert count_new_samples(_cnt_rows, "t2") == 2 and \
        count_new_samples(_cnt_rows, "t9") == 0, \
        "增量按本运行 judged_at 戳计——幂等重跑如实 0（I-015③）"
    assert lens_mod.touch_probability(10.0, 10.5, 0.3) == \
        lens_mod.touch_probability(10.0, round(10.0 / 1.05, 4), 0.3), \
        "触及概率对称（对数等距上下锚同值——屏障距离 b=max(r/p,p/r) 对称）"
    # 确定性
    assert derive_outlook(ev(), ctx) == card
    print("  ok 预测带数学/单调 · 触及概率复用 lens · 锚按轨（禁现算充锚）· "
          "经验计数+MIN_SAMPLES · 日差连向 · 脱敏负断言 · 弃权如实 · "
          "upsert 幂等+盘中拒写 · 零权重金标准 · 确定性")
    print("SELFTEST PASSED ✔")
    return 0


# ---------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--evidence", default=".vs/evidence.json")
    ap.add_argument("--state-dir", default=STATE_DIR)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    with open(args.evidence, encoding="utf-8") as f:
        evidence = json.load(f)
    card = compute_card(evidence, args.state_dir)
    if card is None:
        print("市场不可识别（快照兜底形态）——不出卡")
        return 2
    out = args.out or os.path.join(
        os.path.dirname(args.evidence) or ".", "outlook.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(card, f, ensure_ascii=False, indent=1)
    print("outlook -> %s · state=%s date=%s" % (
        out, card.get("state"), card.get("date")))
    return 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
