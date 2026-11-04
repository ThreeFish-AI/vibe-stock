#!/usr/bin/env python3
"""持仓股加仓决策轨（add-on track）——确定性资格门与三段确认制。

定位（references/10 SSOT）：裁决链**之外**的确定性编排算术（同 batch/
portfolio.py 先例）——不进五信号聚合、不改 RiskGuard、不投方向票；对已
持有股票回答「该不该加、加多少、什么价位、加错怎么撤销」。三道门：
  门1 资格冻结/解冻：短线终判 sell 族 / risk veto·downgrade / 中线降档 /
     风险链 A-1~A-5 任一命中即冻结；解冻只能来自信号族自然修复（只冻
     不升格，与 RiskGuard 只降不升对称）。
  门2 触发：顺势轨（多头排列 + bull_trend/shrink_pullback 买点 + 回踩
     在场 + RSI<78 + 不超 ma20+10%）；逆势窄门（quality_value 买点 +
     lens「有支撑」+ 现价<ma20 + 零风险链）。禁用理由：摊薄成本/跌多了/
     回本心态（09 规约）。
  门3 手数与节奏：单次 ≤现仓 1/3（顺势）/ 1/6（逆势），100 股取整，
     首加=批上限的 1/2（半批不足 1 手不拆批不加）→ T+3 确认（信号日后
     前 3 根收盘不破 add_ref−3% 且不创新低）→ 确认加剩余；确认加成交
     （信号日后第 2 笔 buy）进入冷却；同票 60 日 ≤2 次（冷却只拦新登记，
     不拦在途复核）；加仓后浮亏 ≥15% 禁再加（包络）。idle 触发前过 addon
     自身置信门（≥0.5，同 adjudicate.CONFIDENCE_GATE 口径；不要求
     executable——hold 日加仓是设计内形态，09「定位」）。

执行态从 portfolio.json operations + signals 历史推导（不新增状态文件）：
operations 是成交事实 SSOT（04 契约），addon 信号 pending 与否是建议在途
态。汇率红线（03）：包络不引入 HKD/CNY 换算——跨币种权重线留 P2。
"""

import datetime as _dt
import json
import math
import os

# ---------------------------------------------------------------- 常量（判据 SSOT，改判据须同步 references/10 与 CHANGELOG）

FREEZE_SIGNALS = {"sell", "strong_sell"}   # 门1：短线终判卖族即冻结
UNLOCK_DAYS = 90            # A-1：60 交易日 ≈ 90 日历日近似（确定性可算）
UNLOCK_RATIO = 3.0          # A-1（→08 ①-3）：解禁比例 ≥3% 必查
VAL_PCT = 90.0              # A-2（→08 ②-4）：PE/PB 5 年分位 >90 冻结
TSMOM_WARN = 100.0          # A-4（→08 ②-7 收严实现）：250 日动量 >+100% 冻结
RSI_CAP = 78.0              # 顺势轨：RSI 超买警戒（08 口径）
MA20_STRETCH = 0.10         # 顺势轨：现价高出 ma20 ≥10% 不追
PULLBACK_MIN = 0.03         # 顺势轨：距 20 日高回撤 ≥3% 才算回踩在场
MA10_TOL = 1.02             # 顺势轨：现价 ≤ ma10×1.02 视为回踩至均线带
SIZE_DIVISOR = {"trend": 3, "value": 6}  # 门3：单次上限=现仓/3（顺势）、/6（逆势）
LOT = 100                   # 手数取整（港股 board lot 贴合为 P2）
CONFIRM_CUT = 0.97          # T+3 确认线=撤销线：add_ref×0.97（守住确认/破位撤销）
COOLDOWN_DAYS = 60          # 同票加仓信号 60 日限频窗（日历日近似）
MAX_ADDONS_60D = 2          # 同票 60 日加仓信号 ≤2 条
LOSS_ENVELOPE = 0.15        # 包络：加仓后浮亏 ≥15% 禁再加
NARROW_CONF = {"high", "medium"}  # 逆势窄门：lens 置信下限
CONF_GATE = 0.5             # addon 轨置信门（口径同 adjudicate.CONFIDENCE_GATE——
                            # 不要求 executable：hold 日加仓是设计内形态，09「定位」）


# ---------------------------------------------------------------- 小工具

def _blk(evidence, name):
    """统一取块：返回 (state, data)；data 兼容扁平与 data 包裹两形态。"""
    b = (evidence.get("blocks") or {}).get(name) or {}
    st = b.get("state", "missing")
    data = b.get("data", b) if isinstance(b.get("data", b), dict) else {}
    return st, data


def _f(v):
    """数值容错读：非有限数值折 None（手维/上游脏值不得让判据崩栈）。"""
    try:
        x = float(v)
    except (TypeError, ValueError, OverflowError):  # 309 位以上整数同拒（archive 口径）
        return None
    return x if math.isfinite(x) else None


def _bars_of(evidence):
    """日 K 序列统一提取（块扁平与 data 包裹两形态；畸形折空列表）。"""
    b = (evidence.get("blocks") or {}).get("daily_bars") or {}
    d = b.get("data") if isinstance(b.get("data"), dict) else b
    bars = d.get("bars")
    return bars if isinstance(bars, list) else []


def _price_of(evidence):
    """现价：quote.price 优先，缺则日 K 末根收盘（与 pack/报告口径一致）。"""
    q = (evidence.get("blocks") or {}).get("quote") or {}
    d = q.get("data") if isinstance(q.get("data"), dict) else q
    price = _f(d.get("price"))
    if price is None:
        bars = _bars_of(evidence)
        price = _f(bars[-1].get("close")) if bars else None
    return price


def load_operations(state_dir):
    """portfolio.json operations 原始读取（load_portfolio 只归一持仓值，
    不含成交流水——addon 需要「建议后是否真的买了」这一执行事实）。契约
    外形态（缺键/非列表）一律折空列表：脏数据不开门也不崩栈。"""
    path = os.path.join(os.path.expanduser(state_dir), "portfolio.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return []
    ops = data.get("operations") if isinstance(data, dict) else None
    return [o for o in ops if isinstance(o, dict)] if isinstance(ops, list) else []


# ---------------------------------------------------------------- 门1：风险链与资格冻结

def risk_chain(evidence, today):
    """A 族风险链确定性判据（字段口径见 references/10；数值判据指回 08）。
    返回 (reasons, detail)：reasons 非空=冻结；detail 逐条给
    green/red/skip（skip=制度性无数据或字段未接入，09 缺证据口径）。"""
    reasons, detail = [], {}

    # A-1 临近解禁（→08 ①-3）：60 交易日内 ratio_pct≥3%。not_supported
    # （港股制度性无此披露）→ skip；available 但缺 upcoming 键 → skip+注记
    st, data = _blk(evidence, "unlock")
    if st == "not_supported":
        detail["A-1"] = "skip（not_supported：港股无解禁披露形态）"
    else:
        up = data.get("upcoming")
        if not isinstance(up, list):
            detail["A-1"] = "skip（无 upcoming 数据，不判）"
        else:
            hit = False
            for e in up:
                d = str(e.get("date") or "")
                r = _f(e.get("ratio_pct"))
                if len(d) >= 10 and r is not None and r >= UNLOCK_RATIO:
                    try:
                        days = (_dt_date(d[:10]) - today).days  # 未来解禁日为正
                    except ValueError:
                        continue
                    if 0 <= days <= UNLOCK_DAYS:
                        hit = True
                        break
            if hit:
                reasons.append("A-1 临近解禁（60 交易日内比例 ≥%.0f%%）"
                               % UNLOCK_RATIO)
                detail["A-1"] = "red"
            else:
                detail["A-1"] = "green"

    # A-2 估值极端（→08 ②-4）：PE/PB 5 年分位 >90（分位缺失逐项跳过）
    st, data = _blk(evidence, "valuation")
    if st == "not_supported":
        detail["A-2"] = "skip（not_supported）"
    else:
        pe, pb = _f(data.get("pe_percentile_5y")), _f(data.get("pb_percentile_5y"))
        if pe is not None and pe > VAL_PCT:
            reasons.append("A-2 估值极端（PE 5 年分位 %.1f>%.0f）" % (pe, VAL_PCT))
            detail["A-2"] = "red"
        elif pb is not None and pb > VAL_PCT:
            reasons.append("A-2 估值极端（PB 5 年分位 %.1f>%.0f）" % (pb, VAL_PCT))
            detail["A-2"] = "red"
        elif pe is None and pb is None:
            detail["A-2"] = "skip（分位字段缺失，不判）"
        else:
            detail["A-2"] = "green"

    # A-3 EPS 90 日下修：字段在场才判（A 股侧上游常缺席=08 P4 未接入，
    # 缺席不判；接入后收严为缺席即冻结——收严路径见 09）
    st, data = _blk(evidence, "research")
    eps = ((data.get("consensus") or {}).get("eps_revision_90d") or {}
           if isinstance(data.get("consensus"), dict) else {})
    if st == "not_supported":
        detail["A-3"] = "skip（not_supported）"
    elif not eps:
        detail["A-3"] = "skip（eps_revision_90d 未接入，不判）"
    elif eps.get("direction") == "down":
        reasons.append("A-3 EPS 90 日下修（%s→%s）"
                       % (eps.get("ago_90d"), eps.get("current")))
        detail["A-3"] = "red"
    else:
        detail["A-3"] = "green"

    # A-4 两年翻倍警戒（→08 ②-7 的收严实现：tsmom_250d>+100% 即冻结，
    # 不要求 rv 抬升佐证——方向只收严）
    st, data = _blk(evidence, "technical")
    tsmom = _f(((data.get("mid_term") or {}) if isinstance(data.get("mid_term"),
                dict) else {}).get("tsmom_250d"))
    if tsmom is not None and tsmom > TSMOM_WARN:
        reasons.append("A-4 两年翻倍警戒（tsmom_250d %+.1f%%）" % tsmom)
        detail["A-4"] = "red"
    elif tsmom is None:
        detail["A-4"] = "skip（tsmom_250d 缺失，不判）"
    else:
        detail["A-4"] = "green"

    # A-5 当期亏损（v1 单期口径：fundamentals 为单期扁平结构，无 history
    # 序列；fetch 暴露多期后收严为「连续 3 期亏损」——收严路径见 09）
    st, data = _blk(evidence, "fundamentals")
    np_ = _f(data.get("归母净利润(亿元)"))
    if st == "not_supported" or np_ is None:
        detail["A-5"] = "skip（无当期净利数据，不判）"
    elif np_ < 0:
        reasons.append("A-5 当期亏损（归母净利润 %.1f 亿）" % np_)
        detail["A-5"] = "red"
    else:
        detail["A-5"] = "green"

    return reasons, detail


def gate1(verdict, pverdict, risk, evidence, today):
    """门1 资格冻结/解冻。返回 (ok, reasons, detail)。"""
    reasons, detail = [], {}
    final = ((verdict or {}).get("risk_guard") or {}).get("final")
    if final in FREEZE_SIGNALS:
        reasons.append("短线终判 %s（卖族冻结）" % final)
        detail["signal"] = "red"
    else:
        detail["signal"] = "green"
    if isinstance(risk, dict) and (risk.get("veto") or risk.get("downgrade")):
        reasons.append("风险角色 veto/downgrade（%s）"
                       % "、".join(k for k in ("veto", "downgrade")
                                   if risk.get(k)))
        detail["risk_role"] = "red"
    else:
        detail["risk_role"] = "green"
    pf = ((pverdict or {}).get("risk_guard") or {}).get("final")
    if pverdict and (pf in FREEZE_SIGNALS):
        reasons.append("中线终判 %s（卖族冻结）" % pf)
        detail["position"] = "red"
    elif pverdict:
        detail["position"] = "green" if pf else "skip（无中线裁决）"
    else:
        detail["position"] = "skip（无中线裁决）"
    chain, chain_detail = risk_chain(evidence, today)
    reasons.extend(chain)
    detail.update(chain_detail)
    return (not reasons), reasons, detail


# ---------------------------------------------------------------- 门2：触发（策略买点在场）

def trend_trigger(evidence, verdict):
    """顺势轨：多头排列 + bull_trend/shrink_pullback 买点 + 回踩在场 +
    RSI<78 + 不超 ma20+10%。返回 (ok, blockers, ctx)。"""
    _, tech = _blk(evidence, "technical")
    price = _price_of(evidence)
    ma5, ma10, ma20 = _f(tech.get("ma5")), _f(tech.get("ma10")), _f(tech.get("ma20"))
    rsi = _f(tech.get("rsi14"))
    bars = _bars_of(evidence)
    highs = [_f(b.get("close")) for b in bars[-20:]]
    highs = [h for h in highs if h is not None]
    high20 = max(highs) if highs else None
    blockers, ctx = [], {"price": price, "ma10": ma10, "ma20": ma20,
                         "high20": high20, "pullback": None}
    if None in (price, ma5, ma10, ma20):
        blockers.append("均线/现价数据缺失")
        return False, blockers, ctx
    pullback = (high20 is not None
                and (high20 - price) / high20 >= PULLBACK_MIN) \
        or price <= ma10 * MA10_TOL
    ctx["pullback"] = pullback
    if not (ma5 > ma10 > ma20 and price >= ma20):
        blockers.append("多头排列不在场（ma5>ma10>ma20 且现价≥ma20 不满足）")
    buys = {o.get("source"): o.get("signal") for o in
            (verdict or {}).get("valid_opinions", [])}
    if not any(buys.get("strategy:" + s) in ("buy", "strong_buy")
               for s in ("bull_trend", "shrink_pullback")):
        blockers.append("bull_trend/shrink_pullback 无买点意见")
    if not pullback:
        blockers.append("回踩不在场（距 20 日高 <%.0f%% 且现价 > ma10×%.2f）"
                        % (PULLBACK_MIN * 100, MA10_TOL))
    if rsi is None or rsi >= RSI_CAP:
        blockers.append("rsi14 ≥%.0f 超买" % RSI_CAP if rsi is not None
                        else "rsi14 缺失")
    if price >= ma20 * (1 + MA20_STRETCH):  # 规约「高出 <10%」——恰 10% 即拦（收严）
        blockers.append("现价高出 ma20 ≥%.0f%%（追高禁手）" % (MA20_STRETCH * 100))
    return (not blockers), blockers, ctx


def value_trigger(evidence, verdict, lens):
    """逆势窄门：quality_value 买点 + lens「有支撑」（置信≥medium）+
    现价<ma20。返回 (ok, blockers)。lens 三档在门内作资格输入是 03 透镜
    红线的显式例外（裁决链外资格门，03/09 已注记）。"""
    _, tech = _blk(evidence, "technical")
    price, ma20 = _price_of(evidence), _f(tech.get("ma20"))
    blockers = []
    buys = {o.get("source"): o.get("signal") for o in
            (verdict or {}).get("valid_opinions", [])}
    if buys.get("strategy:quality_value") not in ("buy", "strong_buy"):
        blockers.append("quality_value 无买点意见")
    if not isinstance(lens, dict) or lens.get("tier") != "有支撑":
        blockers.append("基本面锚非「有支撑」")
    elif lens.get("confidence") not in NARROW_CONF:
        blockers.append("基本面锚置信不足（%s）" % lens.get("confidence"))
    if None in (price, ma20):
        blockers.append("现价/ma20 缺失")
    elif price >= ma20:
        blockers.append("现价 ≥ ma20（非逆势区，走顺势轨判据）")
    return (not blockers), blockers


# ---------------------------------------------------------------- 门3：手数、包络与三段状态机

def size_cap(qty, track):
    """单次加仓手数上限：⌊现仓/divisor⌋ 向 LOT 取整；不足 1 手上限为 0
    （现仓太小不拆批，禁加）。"""
    cap = int(qty) // SIZE_DIVISOR[track]
    return max(0, cap // LOT * LOT)


def envelope(price, qty, cost, size, add_ref):
    """包络（汇率红线：不引入换汇）：加仓后新加权成本与浮亏线；浮亏
    ≥15% 禁再加。返回 (ok, reason, info)。"""
    if None in (price, qty, cost) or size <= 0:
        return False, "持仓/成本/手数数据缺失", {}
    new_cost = (qty * cost + size * add_ref) / (qty + size)
    loss_pct = (price - new_cost) / new_cost
    info = {"new_cost": round(new_cost, 4), "loss_pct": round(loss_pct, 4)}
    if loss_pct <= -LOSS_ENVELOPE:
        return False, ("加仓后浮亏 %.1f%% ≥%.0f%%（包络禁手）"
                       % (-loss_pct * 100, LOSS_ENVELOPE * 100)), info
    return True, "", info


def _dt_date(s):
    return _dt.date.fromisoformat(s)


def stage_state(stock_signals, operations, today):
    """三段确认制状态推导（执行事实=operations，在途建议=pending addon
    信号；不新增状态文件）。返回 (stage, in_flight)。stage ∈
    idle/first_pending/first_filled/completed/cooldown。在途信号优先于
    限频冷却——冷却只拦新登记，不拦在途的 T+3 确认/撤销复核（09 门 3）；
    确认加成交（信号日后第 2 笔 buy，按笔计）后 completed 进入冷却。"""
    pend = [s for s in stock_signals
            if s.get("profile") == "addon" and s.get("status") == "pending"]
    if pend:
        sig = pend[0]
        sig_day = _dt_date(str(sig.get("date"))[:10])
        filled = [o for o in operations
                  if str(o.get("code", "")).zfill(5) == str(sig.get("code", "")).zfill(5)
                  and str(o.get("action")) == "buy"
                  and str(o.get("time", ""))[:10] >= sig_day.isoformat()]
        if len(filled) >= 2:  # 首加 + 确认加均已成交（按笔计，09）
            return "completed", sig
        if not filled:
            return "first_pending", sig
        # T+3 确认窗（交易日近似：≤5 日历日）：窗内低点守住确认线且未创新低
        # → 确认加；破线或创新低 → 撤销（由调用方用 evidence bars 判窗内低点）
        return "first_filled", sig
    recent = [s for s in stock_signals if s.get("profile") == "addon"
              and s.get("date") and
              0 <= (today - _dt_date(str(s["date"])[:10])).days <= COOLDOWN_DAYS]
    if len(recent) >= MAX_ADDONS_60D:
        return "cooldown", None
    return "idle", None


def confirm_window(bars, sig_date, add_ref):
    """first_filled 段的 T+3 窗评估：信号日**之后**的前 3 根收盘（T+3，
    ≈5 日历日近似——T+N=信号日后第 N 根，与 postmortem horizons 同口径）
    对照 add_ref×0.97 确认线与信号前 20 根低点。窗未满 3 根且守住 →
    pending；窗内任一收盘破线/创新低 → 立即 abort（提前撤销，收严方向）；
    满 3 根守住 → confirm。返回 confirm/abort/pending + 窗内最低价。"""
    closes = [(str(b.get("date"))[:10], _f(b.get("close")))
              for b in bars if _f(b.get("close")) is not None]
    pre = [c for d, c in closes if d < sig_date][-20:]
    post = [(d, c) for d, c in closes if d > sig_date][:3]
    if not post:
        return "pending", None
    lo = min(c for _, c in post)
    cut = add_ref * CONFIRM_CUT
    if lo < cut or (pre and lo < min(pre)):
        return "abort", lo
    if len(post) >= 3:
        return "confirm", lo
    return "pending", lo


# ---------------------------------------------------------------- 主入口

def evaluate_addon(code, market, holding, verdict, pverdict, risk, evidence,
                   lens, stock_signals, operations, today):
    """加仓轨总评。holding 为 load_portfolio 归一 {qty,cost}（None=未持有
    → addon 不适用）。返回 dict（advice ∈ first_add/hold/wait_pullback/
    confirm_add/abort/frozen/cooldown/none + 渲染所需全部字段）。门 1 先于
    冷却/在途判定（gate_detail 全态可溯源）；冷却只拦新登记、不拦在途的
    T+3 复核；idle 触发前过 addon 自身置信门（CONF_GATE，09「定位」）。"""
    out = {"held": bool(holding and (_f(holding.get("qty")) or 0) > 0),
           "eligible": False, "frozen_reasons": [], "gate_detail": {},
           "track": "none", "triggered": False, "trigger_blockers": [],
           "stage": "n/a", "advice": "none", "size_cap": None,
           "first_qty": None, "add_ref": None, "confirm_lo": None,
           "envelope": None, "rationale": ""}
    if not out["held"]:
        out["rationale"] = "未持有（portfolio 无该票或数量为 0），加仓轨不适用"
        return out
    qty, cost = _f(holding.get("qty")), _f(holding.get("cost"))
    stage, in_flight = stage_state(stock_signals, operations, today)
    out["stage"] = stage
    # 门 1 先行（09 产出契约：冷却态同样出 gate_detail/冻结原因，不让冷却
    # 吞掉资格溯源信息）
    ok, reasons, detail = gate1(verdict, pverdict, risk, evidence, today)
    out["gate_detail"] = detail
    if not ok:
        out["frozen_reasons"] = reasons
        out["advice"] = "frozen"
        out["rationale"] = "资格冻结：" + "；".join(reasons) + \
            "。解冻=信号族自然修复（非卖族且无 downgrade），无人工升格通道"
        return out
    out["eligible"] = True
    if stage == "cooldown":
        out["advice"] = "cooldown"
        out["rationale"] = ("60 日内加仓信号已 %d 条（上限 %d），冷却中——"
                            "冷却只拦新登记，不拦在途复核"
                            % (MAX_ADDONS_60D, MAX_ADDONS_60D))
        return out
    if stage == "completed":
        out["advice"] = "cooldown"
        out["rationale"] = ("首加与确认加均已成交（信号日后 buy ≥2 笔），"
                            "本信号批次完成，冷却中")
        return out
    if stage == "first_filled" and in_flight:
        kl = (in_flight.get("key_levels") or {})
        add_ref = _f(kl.get("add_ref"))
        bars = _bars_of(evidence)
        verdict_w, lo = confirm_window(
            bars, str(in_flight.get("date"))[:10], add_ref) \
            if add_ref is not None else ("pending", None)
        if verdict_w == "confirm":
            out["advice"], out["add_ref"] = "confirm_add", add_ref
            out["confirm_lo"] = round(add_ref * CONFIRM_CUT, 4)
            rest = None
            if isinstance(kl.get("size_cap"), (int, float)):
                rest = max(0, int(kl["size_cap"]) - int(kl.get("first_qty") or 0))
            out["rationale"] = ("T+3 窗守住确认线（窗内最低 %s ≥ %s）：确认加"
                                "剩余批次%s" % (lo, out["confirm_lo"],
                                               "（≤%d 股）" % rest if rest else ""))
        elif verdict_w == "abort":
            out["advice"], out["add_ref"] = "abort", add_ref
            out["confirm_lo"] = round(add_ref * CONFIRM_CUT, 4)
            out["rationale"] = ("T+3 窗破位（窗内最低 %s < %s 或创新低）：撤销，"
                                "剩余批次不加，首加部分按当日短线信号处置"
                                % (lo, out["confirm_lo"]))
        else:
            out["advice"] = "hold"
            out["rationale"] = "首加在途，T+3 确认窗未满，不动作"
        return out
    if stage == "first_pending":
        # 在途建议复核：门仍开才维持，否则撤销提示（登记侧由下一诊覆盖）
        out["advice"] = "hold"
        out["rationale"] = "首加建议在途未执行（门开维持；收盘前未成交按当日收盘复核）"
        return out
    # idle：门开，先过 addon 置信门（09「定位」：低置信日不出买入侧建议，
    # 与 04 §7「检查没过结论停在保守档」对齐；在途 confirm/abort 复核不受
    # 此门——撤销是风险动作必须送达）
    conf = ((verdict or {}).get("aggregate") or {}).get("confidence")
    if conf is None or conf < CONF_GATE:
        out["advice"] = "hold"
        out["rationale"] = ("置信门未过（confidence=%s < %.1f），不出加仓建议"
                            % (conf, CONF_GATE))
        return out
    t_ok, t_block, t_ctx = trend_trigger(evidence, verdict)
    v_ok, v_block = value_trigger(evidence, verdict, lens)
    price = t_ctx.get("price")
    if t_ok:
        track = "trend"
    elif v_ok:
        track = "value"
    else:
        out["trigger_blockers"] = t_block + v_block
        ma10, ma20 = t_ctx.get("ma10"), t_ctx.get("ma20")
        # 等回踩只在「唯一缺失条件是回踩」时成立（多头排列在场、现价仍在
        # 均线带上方、其余顺势条件全绿）——破位/买点缺席形态落普通 hold
        # 并列出全部 blockers（09）
        if t_ctx.get("pullback") is False and len(t_block) == 1:
            out["advice"] = "wait_pullback"
            out["rationale"] = ("资格开（顺势轨）：多头排列在场，等回踩至 "
                                "%s~%s 区间再评估（现价 %s 不追）"
                                % (round(ma10, 2), round(ma20, 2), price))
        else:
            out["advice"] = "hold"
            out["rationale"] = "资格开但触发条件不满足：" + "；".join(
                out["trigger_blockers"])
        return out
    out["track"], out["triggered"] = track, True
    size = size_cap(int(qty), track)
    if size <= 0:
        out["advice"] = "hold"
        out["rationale"] = "现仓 %d 股过小，单次上限不足 1 手（%d 股），不拆批" % (qty, size)
        return out
    ma10, ma20 = t_ctx.get("ma10"), t_ctx.get("ma20")
    # add_ref（09 门 3）：顺势=均线带上沿但不高于触发时现价（深回踩形态以
    # 现价为锚——锚高于成交价会让确认线必然高于市价，首加即自噬撤销）；
    # 逆势=触发时价（与信号登记价同口径：盘中运行为盘中价，price_kind 标注）
    add_ref = (round(min(max(ma10, ma20), price), 2)
               if track == "trend" and ma10 and ma20 else round(price, 2))
    first = size // 2 // LOT * LOT  # 首加 = 批上限的 1/2（100 股向下取整）
    if first < LOT:  # 半批不足 1 手：不拆批不加（收严，09）
        out["advice"] = "hold"
        out["rationale"] = ("单次上限 %d 股的半批不足 1 手（%d 股），不拆批不加"
                            % (size, size // 2))
        return out
    e_ok, e_reason, e_info = envelope(price, qty, cost, size, add_ref)
    out["envelope"] = e_info
    if not e_ok:
        out["advice"] = "hold"
        out["rationale"] = e_reason
        return out
    out["advice"], out["size_cap"], out["first_qty"] = "first_add", size, first
    out["add_ref"] = add_ref
    out["confirm_lo"] = round(add_ref * CONFIRM_CUT, 4)
    out["rationale"] = (
        "%s轨首加 1/2 批：首加 ≤%d 股（整批上限 %d 的一半）@参考 %s；"
        "T+3 守住 %s 确认加剩余 ≤%d 股，破位或创新低撤销剩余批次（%s）"
        % ("顺势" if track == "trend" else "逆势窄门", first, size, add_ref,
           out["confirm_lo"], size - first,
           "策略买点在场" if track == "trend" else "价值锚支撑+零风险链"))
    return out


# ---------------------------------------------------------------- selftest（零网络，内联 fixture）

def selftest():
    def ev(**kw):
        base = {"meta": {"market": "cn"}, "blocks": kw}
        return base

    def tech(ma5=10.0, ma10=9.5, ma20=9.0, rsi=50.0, tsmom=None):
        t = {"ma5": ma5, "ma10": ma10, "ma20": ma20, "rsi14": rsi}
        if tsmom is not None:
            t["mid_term"] = {"tsmom_250d": tsmom}
        return t

    def bars_from(closes, start="2026-10-01"):
        import datetime as _d
        d0 = _d.date.fromisoformat(start)
        return [{"date": (d0 + _d.timedelta(days=i)).isoformat(), "close": c}
                for i, c in enumerate(closes)]

    def verdict_of(final="hold", opinions=()):
        return {"risk_guard": {"final": final}, "aggregate": {"confidence": 0.5},
                "valid_opinions": [{"source": s, "signal": sig, "confidence": 0.6,
                                    "weight": 1.0} for s, sig in opinions]}

    today = _dt.date(2026, 11, 4)
    hold = {"qty": 1000, "cost": 10.0}
    good = ev(technical=tech(), quote={"price": 9.6},
              daily_bars={"bars": bars_from([9.0] * 19 + [9.6])},
              unlock={"state": "available", "data": {"upcoming": []}},
              valuation={"state": "available",
                         "data": {"pe_percentile_5y": 40, "pb_percentile_5y": 30}},
              research={"state": "available", "data": {"consensus": {}}},
              fundamentals={"state": "available", "data": {"归母净利润(亿元)": 5.0}})
    v_trend = verdict_of("hold", [("strategy:bull_trend", "buy"),
                                  ("role:技术", "buy")])
    lens_sup = {"tier": "有支撑", "confidence": "high"}
    v_value = verdict_of("hold", [("strategy:quality_value", "buy")])

    def run(evidence=good, verdict=v_trend, pverdict=None, risk=None, lens=None,
            holding=hold, signals=None, ops=None):
        return evaluate_addon("600000", "cn", holding, verdict, pverdict, risk,
                              evidence, lens, signals or [], ops or [], today)

    print("== 加仓轨 selftest ==")

    # 1) 顺势触发全绿：首加建议 + 手数 1/3（首加=半批）+ add_ref 钳制口径
    r = run()
    assert r["advice"] == "first_add" and r["track"] == "trend", r
    assert r["size_cap"] == 300, r["size_cap"]   # 1000/3 → 300
    assert r["first_qty"] == 100, r["first_qty"]  # 首加=半批 150 向下取整到 100 股
    assert r["add_ref"] == 9.5 and r["confirm_lo"] == round(9.5 * 0.97, 4), r
    assert r["envelope"]["new_cost"] == round((1000 * 10 + 300 * 9.5) / 1300, 4)
    print("  ok 顺势首加（手数/首加半批/add_ref/包络）")

    # 2) 门1 冻结族：短线卖族 / risk downgrade / A-1~A-5 逐条
    assert run(verdict=verdict_of("sell"))["advice"] == "frozen"
    assert run(risk={"veto": False, "downgrade": True})["advice"] == "frozen"
    assert run(pverdict=verdict_of("strong_sell"))["advice"] == "frozen"
    u = {"state": "available", "data": {"upcoming": [
        {"date": "2026-12-01", "ratio_pct": 5.0}]}}
    r = run(evidence=ev(**{**good["blocks"], "unlock": u}))
    assert r["advice"] == "frozen" and any("A-1" in x for x in r["frozen_reasons"])
    assert run(evidence=ev(**{**good["blocks"],
        "valuation": {"state": "available",
                      "data": {"pe_percentile_5y": 95, "pb_percentile_5y": 30}}})
        )["advice"] == "frozen"
    eps_down = {"state": "available", "data": {"consensus": {
        "eps_revision_90d": {"direction": "down", "current": -9.7, "ago_90d": -9.3}}}}
    assert run(evidence=ev(**{**good["blocks"], "research": eps_down})
               )["advice"] == "frozen"
    assert run(evidence=ev(**{**good["blocks"],
        "technical": tech(tsmom=229.6)}))["advice"] == "frozen"
    assert run(evidence=ev(**{**good["blocks"],
        "fundamentals": {"state": "available", "data": {"归母净利润(亿元)": -20.7}}})
        )["advice"] == "frozen"
    print("  ok 门1 冻结族（卖族/risk/中线/A-1~A-5）")

    # 3) 缺证据口径：not_supported 与未接字段=skip 不冻结（A 股 eps 缺席常态）
    hk = ev(technical=tech(tsmom=-15), quote={"price": 9.6},
            daily_bars={"bars": bars_from([9.0] * 19 + [9.6])},
            unlock={"state": "not_supported"}, valuation={"state": "available",
            "data": {}}, research={"state": "available", "data": {}},
            fundamentals={"state": "available", "data": {}})
    r = run(evidence=hk)
    assert r["advice"] == "first_add", r
    assert "skip" in r["gate_detail"]["A-1"] and "skip" in r["gate_detail"]["A-3"]
    print("  ok 缺证据 skip 口径（not_supported/未接入不冻结）")

    # 4) 回踩不在场（唯一缺失条件）→ wait_pullback（创新高顶端不追）
    r = run(evidence=ev(**{**good["blocks"],
        "daily_bars": {"bars": bars_from([9.0] * 19 + [9.85])},
        "quote": {"price": 9.85}, "technical": tech(rsi=74.0)}))
    assert r["advice"] == "wait_pullback", r
    print("  ok 回踩不在场 → wait_pullback")

    # 5) 逆势窄门：现价<ma20 + quality_value + 有支撑
    v_ev = ev(technical=tech(ma5=8.5, ma10=9.0, ma20=9.6), quote={"price": 9.0},
              daily_bars={"bars": bars_from([9.5] * 19 + [9.0])},
              unlock={"state": "available", "data": {"upcoming": []}},
              valuation={"state": "available", "data": {}},
              research={"state": "available", "data": {}},
              fundamentals={"state": "available", "data": {}})
    r = run(evidence=v_ev, verdict=v_value, lens=lens_sup, holding={"qty": 1200, "cost": 9.0})
    assert r["advice"] == "first_add" and r["track"] == "value", r
    assert r["size_cap"] == 200 and r["first_qty"] == 100, r  # 1200/6 → 200、半批 100
    assert r["add_ref"] == 9.0   # 逆势=触发时价（与登记价同口径，09）
    assert run(evidence=v_ev, verdict=v_value, lens={"tier": "中性"})["advice"] != "first_add"
    print("  ok 逆势窄门（1/6 手数/锚支撑缺失不开门）")

    # 6) 三段状态机：pending → 窗未满 pending → filled(confirm/abort) / 限频
    sig = {"profile": "addon", "status": "pending", "date": "2026-11-02",
           "code": "600000", "key_levels": {"add_ref": 9.5, "size_cap": 300,
                                            "first_qty": 150}}
    r = run(signals=[sig], ops=[{"code": "600000", "action": "buy",
                                "time": "2026-11-03T14:00:00+08:00"}],
            evidence=ev(**{**good["blocks"], "daily_bars": {"bars": bars_from(
                [9.0] * 20 + [9.55, 9.5, 9.45], start="2026-10-13")}}))
    assert r["advice"] == "hold" and "确认窗未满" in r["rationale"], r  # T+3=信号日后 3 根（不含信号日）
    r = run(signals=[sig], ops=[{"code": "600000", "action": "buy",
                                "time": "2026-11-03T14:00:00+08:00"}],
            evidence=ev(**{**good["blocks"], "daily_bars": {"bars": bars_from(
                [9.0] * 20 + [9.55, 9.5, 9.45, 9.5], start="2026-10-13")}}))
    assert r["advice"] == "confirm_add" and "≤150 股" in r["rationale"], r
    r = run(signals=[sig], ops=[{"code": "600000", "action": "buy",
                                "time": "2026-11-03T14:00:00+08:00"}],
            evidence=ev(**{**good["blocks"], "daily_bars": {"bars": bars_from(
                [9.0] * 20 + [9.5, 9.1, 8.9, 8.8], start="2026-10-13")}}))
    assert r["advice"] == "abort", r
    recent = [{"profile": "addon", "status": "evaluated", "date": "2026-10-20",
               "code": "600000"},
              {"profile": "addon", "status": "evaluated", "date": "2026-11-01",
               "code": "600000"}]
    assert run(signals=recent)["advice"] == "cooldown"
    print("  ok 三段状态机（T+3 窗/confirm 带剩余手数/abort/60 日限频）")

    # 7) 包络：现价深低于新成本 → 禁
    r = run(holding={"qty": 1000, "cost": 50.0})
    assert r["advice"] == "hold" and "包络" in r["rationale"], r
    print("  ok 包络浮亏禁手")

    # 8) 破坏性实验：拿掉门2 买点判据 → wait/hold 不再 first_add（门不可绕）
    v_nobuy = verdict_of("hold", [("strategy:bull_trend", "hold")])
    assert run(verdict=v_nobuy)["advice"] != "first_add"
    assert run(holding=None)["advice"] == "none"
    print("  ok 破坏性实验（买点缺席/未持有）")

    # 9) 冷却只拦新登记不拦在途复核；确认加成交终态；冷却态门1 仍可溯源；
    #    手维数字 code 不崩栈（脏数据不开门也不崩栈口径）
    r = run(signals=recent)
    assert r["advice"] == "cooldown" and r["gate_detail"], r  # 冷却态也出 gate_detail
    sig2 = dict(sig, date="2026-11-03")
    r = run(signals=recent + [sig2], ops=[{"code": "600000", "action": "buy",
                                           "time": "2026-11-04T10:00:00+08:00"}],
            evidence=ev(**{**good["blocks"], "daily_bars": {"bars": bars_from(
                [9.0] * 20 + [9.55, 9.5, 9.45, 9.5, 9.5], start="2026-10-13")}}))
    assert r["advice"] == "confirm_add", r  # recent 已满 2 条但在途复核不被冷却吞
    r = run(signals=recent + [sig2], ops=[
        {"code": "600000", "action": "buy", "time": "2026-11-04T10:00:00+08:00"},
        {"code": 600000, "action": "buy", "time": "2026-11-05T10:00:00+08:00"}],
        evidence=ev(**{**good["blocks"], "daily_bars": {"bars": bars_from(
            [9.0] * 20 + [9.55, 9.5, 9.45, 9.5, 9.5], start="2026-10-13")}}))
    assert r["advice"] == "cooldown" and "批次完成" in r["rationale"], r  # ≥2 笔 buy → 终态
    print("  ok 冷却不吞在途/确认加终态/冷却态门1 溯源/数字 code 容错")

    # 10) 置信门（<0.5 不出首加）；add_ref 深回踩钳制；追高恰 10% 边界拦截；
    #     破位/买点缺席形态不出「等回踩」；半批不足 1 手不加
    assert run(verdict={**v_trend, "aggregate": {"confidence": 0.45}}
               )["advice"] == "hold", "置信门：低置信不出买入侧建议"
    deep = ev(**{**good["blocks"], "technical": tech(ma5=10.2, ma10=10.0, ma20=9.0),
                 "quote": {"price": 9.1}, "daily_bars": {"bars": bars_from(
                     [9.0] * 16 + [10.4, 10.3, 9.5, 9.1])}})
    r = run(evidence=deep)
    assert r["advice"] == "first_add" and r["add_ref"] == 9.1, r  # 锚不高于现价（防自噬撤销）
    assert r["confirm_lo"] < 9.1, r
    exact10 = ev(**{**good["blocks"], "technical": tech(ma5=5.8, ma10=5.6, ma20=5.0),
                    "quote": {"price": 5.5}, "daily_bars": {"bars": bars_from(
                        [5.0] * 19 + [5.5])}})
    r = run(evidence=exact10)
    assert r["advice"] != "first_add" and any(
        "追高" in b for b in r["trigger_blockers"]), r  # 恰 +10% 拦截（≥ 口径）
    broken = ev(**{**good["blocks"], "technical": tech(ma5=10.6, ma10=10.4, ma20=10.2),
                   "quote": {"price": 9.3}, "daily_bars": {"bars": bars_from(
                       [9.0] * 18 + [10.8, 9.3])}})
    r = run(evidence=broken)
    assert r["advice"] == "hold" and "多头排列不在场" in r["rationale"], r  # 破位不出「等回踩」
    assert run(verdict=verdict_of("hold", [("role:技术", "buy")])
               )["advice"] == "hold", "买点缺席不出「等回踩」"
    r = run(holding={"qty": 450, "cost": 9.0})
    assert r["advice"] == "hold" and "半批不足" in r["rationale"], r  # 450/3=100、半批 50 → 不加
    print("  ok 置信门/add_ref 钳制/追高边界/等回踩门槛/半批取整")

    print("SELFTEST PASSED ✔")


if __name__ == "__main__":
    import sys
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
