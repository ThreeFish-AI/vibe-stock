#!/usr/bin/env python3
"""盯盘触发规则引擎（P1 价位类，确定性纯函数，离线可测）。

口径以 references/07-monitor.md 为准（本文件是参考实现）。输入 = 当轮
tick × 宇宙行（价位锚）× 当日状态；输出 = 事件列表（含通知抑制裁决，
抑制原因留痕）。全部规则不触网络、时间可注入——selftest 离线穷举钉死。

红线落地：事件只描述事实（价位/百分比/距离），不带成本绝对值与指令性
建议；量能不进 P1 判据（外推口径坑位见 01/07）；盘中结论一律
「待收盘复核」。机械风险事实（mech_risk）只降不升，P2 升级链消费。
0.0.25 起事件可带「××复核」级短语（07「通知口径」修订：措辞限定「复核」，
禁减仓/离场/加仓等指令词）——随事件落台账（含被压制行），通知面由
fmt_facts 追加。
"""
import argparse
import datetime as dt
import json
import sys

TZ = dt.timezone(dt.timedelta(hours=8))  # 与 fetch.SESSIONS 同口径：沪港固定 UTC+8

DEFAULT_CFG = {
    "move_pct_cn": 5.0,        # ±% 异动阈值（A 股）
    "move_pct_hk": 8.0,        # ±% 异动阈值（港股）
    "quiet_window_min": 10,    # 开盘静默窗：窗内 abnormal_move 只记不发
    "cooldown_min": 30,        # 同股同规则冷却
    "deepen_pct": 2.0,         # 击穿加深再报阈值（相对 stop 再跌 %，可穿透冷却）
    "frozen_rounds": 5,        # 连续 N 轮价量完全不变 → 停牌/冻结
    "gap_move_pct": 3.0,       # 冻结复牌后差异提醒阈值
    "storm_window_min": 10,    # 组合级风暴闸窗口
    "storm_max": 8,            # 窗口内通知上限，超出聚合摘要
    "stock_daily_notify_cap": 6,   # 单股每日通知上限（超出只进台账）
    "limit_margin_pp": 0.3,    # 近触板判定：限幅 − 0.3 个百分点
    "hk_delay_min": 15,        # 港股快照延迟降级阈值（用户裁定：接受延迟但如实标注）
    "ma20_break_ratio": 0.98,  # MA20 破位判定系数（07 P2 预钉：price < ma20×0.98）
    "trailing_arm_pct": 1.15,  # 跟踪止损武装线（06 三价纪律：+15% 后改 trailing）
    "tech_warmup_max_tries": 3,  # 当日 technical 预热重试上限（耗尽出 data_stale）
}

# 免冷却的一次性事件（当日每股每方向至多一次，用 day-flag 去重）
_ONESHOT = ("gap_open", "limit_hit", "frozen", "resumed", "gap_move",
            "market_halted", "market_resumed", "hk_delayed", "t2_pending_fill",
            "target_hit", "abnormal_move",   # 后两者为 episode 语义，去重靠 day_flags
            "trailing_armed", "trailing_exit", "band_lo_touch", "band_hi_touch")

# 事件级「××复核」短语（07「通知口径」0.0.25 修订：措辞限定「复核」、≤6 字，
# 禁减仓/离场/加仓等指令词——沿 07 波段带「低吸/高抛复核」预钉先例）。
# 运维类规则一律不登记（selftest 负断言钉）。
_REVIEW_HINT = {
    "stop_break": "止损复核", "stop_break_confirmed": "止损复核",
    "whipsaw": "止损复核", "target_hit": "止盈复核",
    "abnormal_move": "消息面复核", "t2_pending_fill": "T2成交复核",
    "ma20_break": "均线复核", "trailing_armed": "跟踪止损复核",
    "trailing_exit": "跟踪止损复核", "band_lo_touch": "低吸复核",
    "band_hi_touch": "高抛复核", "band_trail_break": "波段结束复核",
}

# 午休窗口（分钟，UTC+8）：午休价量冻结是常态，不进停牌检测（session_phase
# 的 intraday 判定含午休——见 fetch.SESSIONS 坑位）
LUNCH = {"cn": (690, 780), "hk": (720, 780)}


def _iso(now):
    return now.isoformat(timespec="seconds")


def fresh_state(date_str):
    """当日状态骨架（日期变更即整体归零——盯盘状态是日粒度的；跨日的
    trailing 跟踪态在 watch 侧 st 顶层承载，不在此键内）。"""
    return {"date": date_str, "cooldowns": {}, "streak": {}, "episode": {},
            "day_flags": {}, "frozen": {}, "suspended": {}, "halted": {},
            "notify_log": [], "stock_notify_count": {}, "digest_pending": {},
            "hk_delay_notified": False, "ma20_ep": {}}


def _market_open_minutes(market, now):
    """距开盘已过分钟（含午休折算：午休视作上午满额——与外推口径一致，
    仅用于静默窗判定，粗粒度即可）。"""
    open_min = {"cn": 570, "hk": 570}[market]
    m = now.hour * 60 + now.minute
    return m - open_min if m >= open_min else 0


def _prune_notify_log(state, cfg, now):
    window_start = now - dt.timedelta(minutes=cfg["storm_window_min"])
    state["notify_log"] = [t for t in state["notify_log"]
                           if dt.datetime.fromisoformat(t) > window_start]


def _gate_notify(ev, code, state, cfg, now, bypass_cooldown=False):
    """通知抑制链（全部留痕）：冷却 → 单股日上限 → 组合风暴闸。
    bypass_cooldown 只用于事实升级/反转（击穿加深、收回后再确认）。
    mech_risk 事件（止损确认/加深）豁免日上限与风暴闸——风险事实不得被
    信息类事件挤掉（无条件规则：风暴日正是止损最密集时）。"""
    if not ev["notify"]:
        return ev
    key = "%s|%s" % (code, ev["rule"])
    if not bypass_cooldown:
        until = state["cooldowns"].get(key)
        if until is not None and now < dt.datetime.fromisoformat(until):
            ev["notify"] = False
            ev["suppress_reason"] = "cooldown"
            return ev
    risk = bool(ev.get("mech_risk"))
    _prune_notify_log(state, cfg, now)
    if not risk:
        if state["stock_notify_count"].get(code, 0) >= cfg["stock_daily_notify_cap"]:
            ev["notify"] = False
            ev["suppress_reason"] = "stock_daily_cap"
            return ev
        if len(state["notify_log"]) >= cfg["storm_max"]:
            ev["notify"] = False
            ev["suppress_reason"] = "storm_gate"
            d = state["digest_pending"]
            d["count"] = d.get("count", 0) + 1
            codes = d.setdefault("kinds", {}).setdefault(ev["rule"], [])
            if code not in codes:
                codes.append(code)
            return ev
    state["notify_log"].append(_iso(now))
    state["stock_notify_count"][code] = state["stock_notify_count"].get(code, 0) + 1
    if ev["rule"] not in _ONESHOT and not bypass_cooldown:
        state["cooldowns"][key] = _iso(now + dt.timedelta(minutes=cfg["cooldown_min"]))
    return ev


def _emit(events, state, cfg, now, code, market, kind, rule, facts,
          notify=True, mech_risk=None, suppress_reason=None,
          bypass_cooldown=False):
    ev = {"ts": _iso(now), "code": code, "market": market, "kind": kind,
          "rule": rule, "level": "T0", "notify": notify,
          "mech_risk": mech_risk, "facts": facts}
    if suppress_reason:
        ev["suppress_reason"] = suppress_reason
    hint = _REVIEW_HINT.get(rule)
    if hint:
        ev["review"] = hint   # 事件语义属性：随台账落全量（含被压制行），不受抑制链影响
    ev = _gate_notify(ev, code, state, cfg, now, bypass_cooldown)
    events.append(ev)


def _streak(state, key, hit):
    n = state["streak"].get(key, 0)
    n = n + 1 if hit else 0
    state["streak"][key] = n
    return n


def evaluate(ticks, universe, state, cfg, now, trailing=None):
    """一轮规则评估。ticks=[{code,market,price,prev_close,open,high,low,
    change_pct,ts_utc8,lag_min,...}]；universe rows 以 (code,market) 索引
    （0.0.25 起可带运行期注入键 _ma20/_cost，缺省即 P2 机械判据自然禁用）。
    trailing=跨日跟踪态 {code:{armed,high}}（watch 侧 st 顶层持久化，原地更新）。
    返回 (events, state)；state 原地更新（调用方负责持久化）。"""
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    events = []
    rows = {(r["code"], r["market"]): r for r in universe}
    quiet = {m: _market_open_minutes(m, now) < cfg["quiet_window_min"]
             for m in ("cn", "hk")}

    for t in ticks:
        code, market = t["code"], t["market"]
        row = rows.get((code, market))
        if row is None or state["halted"].get(market) or not t.get("price"):
            continue
        kind = row.get("kind", "watch")
        chg = t.get("change_pct")

        # ---- 停牌/冻结检测（先于价位规则：冻结价不做触发判定）----
        fz = state["frozen"].get(code)
        same = (fz is not None and t["price"] == fz["price"]
                and t.get("volume") == fz.get("volume"))
        lunch = LUNCH.get(market, (0, 0))
        if lunch[0] <= now.hour * 60 + now.minute < lunch[1]:
            if fz is not None:
                fz["rounds"] = 0   # 午休冻结是常态：轮次清零，午后重新计
            if same:
                continue
        if state["suspended"].get(code):
            if same:
                continue
            state["suspended"][code] = False
            move = (t["price"] / fz["price"] - 1) * 100 if fz["price"] else 0.0
            _emit(events, state, cfg, now, code, market, kind, "resumed",
                  {"price": t["price"], "frozen_price": fz["price"],
                   "change_pct_since_frozen": round(move, 2)})
            if abs(move) >= cfg["gap_move_pct"]:
                _emit(events, state, cfg, now, code, market, kind, "gap_move",
                      {"price": t["price"], "frozen_price": fz["price"],
                       "change_pct_since_frozen": round(move, 2)})
            state["frozen"][code] = None
        elif same:
            fz["rounds"] += 1
            if fz["rounds"] >= cfg["frozen_rounds"] and not fz.get("flagged"):
                fz["flagged"] = True
                state["suspended"][code] = True
                flag = "%s|%s|frozen" % (code, market)
                first = not state["day_flags"].get(flag)
                state["day_flags"][flag] = True
                # 当日首次冻结才通知；低流动性票反复冻结/成交只留痕（防挤占日上限）
                _emit(events, state, cfg, now, code, market, kind, "frozen",
                      {"price": fz["price"], "rounds": fz["rounds"],
                       "note": "价量连续不变，疑似停牌/休市，挂起该票轮询"},
                      notify=first,
                      suppress_reason=None if first else "repeat_frozen")
        else:
            state["frozen"][code] = {"price": t["price"], "volume": t.get("volume"),
                                     "rounds": 1, "flagged": False}
        if state["suspended"].get(code):
            continue

        stop, target1, entry_ref = row.get("stop"), row.get("target1"), row.get("entry_ref")
        ep = state["episode"].setdefault(code, {"touched": False, "depth": 0.0,
                                                "reclaimed": False})
        ep.setdefault("reclaimed", False)

        # ---- 止损击穿 / 确认 / 加深 / 收回（episode 语义）----
        if stop is not None:
            if t["price"] < stop:
                depth = round((1 - t["price"] / stop) * 100, 2)
                n = _streak(state, "%s|below_stop" % code, True)
                reversal = ep["reclaimed"]   # 收回后再破 = 事实反转，穿透冷却
                if not ep["touched"]:
                    ep["touched"], ep["depth"] = True, depth
                    _emit(events, state, cfg, now, code, market, kind, "stop_break",
                          {"price": t["price"], "stop": stop, "depth_pct": depth},
                          bypass_cooldown=reversal)
                elif n == 2:
                    ep["depth"] = max(ep["depth"], depth)
                    ep["reclaimed"] = False
                    _emit(events, state, cfg, now, code, market, kind,
                          "stop_break_confirmed",
                          {"price": t["price"], "stop": stop, "depth_pct": depth},
                          mech_risk={"downgrade": True, "severity": "high"},
                          bypass_cooldown=reversal)
                elif depth >= ep["depth"] + cfg["deepen_pct"]:
                    ep["depth"] = depth
                    _emit(events, state, cfg, now, code, market, kind, "stop_break",
                          {"price": t["price"], "stop": stop, "depth_pct": depth,
                           "deepened": True},
                          mech_risk={"downgrade": True, "severity": "high"},
                          bypass_cooldown=True)
            else:
                _streak(state, "%s|below_stop" % code, False)
                if ep["touched"]:
                    ep["touched"], ep["depth"], ep["reclaimed"] = False, 0.0, True
                    _emit(events, state, cfg, now, code, market, kind, "whipsaw",
                          {"price": t["price"], "stop": stop,
                           "note": "击穿后收回，以收盘复核终判"})

        # ---- 触目标位（episode：越线首报，回落到线下后再越线才再报）----
        if target1 is not None:
            tk = "%s|above_target" % code
            if t["price"] >= target1:
                if not state["day_flags"].get(tk):
                    state["day_flags"][tk] = True
                    _emit(events, state, cfg, now, code, market, kind, "target_hit",
                          {"price": t["price"], "target1": target1,
                           "gap_pct": round((t["price"] / target1 - 1) * 100, 2)})
            else:
                state["day_flags"][tk] = False

        # ---- P2 机械判据族（0.0.25；前置门=watch 侧 technical 预热当日性，
        #      _ma20 缺省即整族禁用——data_stale 日不判，不虚构判据）----
        ma20 = row.get("_ma20")
        if ma20 is not None:
            # MA20 破位（episode：回线上复位再破再报；机械降档事实只降不升）
            ep20 = state["ma20_ep"].setdefault(code, {"touched": False})
            if t["price"] < ma20 * cfg["ma20_break_ratio"]:
                if not ep20["touched"]:
                    ep20["touched"] = True
                    _emit(events, state, cfg, now, code, market, kind, "ma20_break",
                          {"price": t["price"], "ma20": ma20,
                           "dist_pct": round((t["price"] / ma20 - 1) * 100, 2),
                           "note": "盘中根口径（estimated），收盘以完整根终判"},
                          mech_risk={"downgrade": True, "severity": "medium"})
            else:
                ep20["touched"] = False

            # 跟踪止损（06 三价纪律：high_since_entry ≥ 成本×1.15 武装，武装后
            # 破 MA20 → trailing_exit 当日一次）。成本运行期注入（row["_cost"]），
            # facts 只落派生量——成本与武装线值绝不落台账（脱敏红线）
            tr = None
            if trailing is not None and row.get("_cost"):
                # 坑位：空 dict 为 falsy——「trailing or {}」会换一次性 dict 丢状态，
                # 跨日持久化态必须显式判 None
                tr = trailing.get(code)
                if tr is None:
                    tr = trailing[code] = {"armed": False, "high": 0.0}
                was_armed = bool(tr.get("armed"))   # 退出只认「先前已武装」态：
                # 武装当轮价格本就在 MA20 下方不算新「破」（06：+15% 改锚后破线离场）
                # high 累积含快照当日高点（与 close_pass bar high 归并同口径；
                # 只用 price 会漏开盘竞价/快照间隙脉冲，低估「盘中高点」事实）
                tr["high"] = max(tr.get("high") or 0.0, t["price"],
                                 t.get("high") or 0.0)
                if not tr.get("armed") and tr["high"] >= row["_cost"] \
                        * cfg["trailing_arm_pct"]:
                    tr["armed"] = True
                    _emit(events, state, cfg, now, code, market, kind,
                          "trailing_armed",
                          {"high_since_entry": tr["high"],
                           "dist_ma20_pct": round((t["price"] / ma20 - 1) * 100, 2),
                           "note": "浮盈达武装线（06：+15% 后改 trailing，"
                                   "收盘破 MA20 终判口径）"})
                ex_flag = "%s|trailing_exit" % code
                if was_armed and t["price"] < ma20 \
                        and not state["day_flags"].get(ex_flag):
                    state["day_flags"][ex_flag] = True
                    _emit(events, state, cfg, now, code, market, kind,
                          "trailing_exit",
                          {"price": t["price"], "ma20": ma20,
                           "high_since_entry": tr["high"],
                           "dist_ma20_pct": round((t["price"] / ma20 - 1) * 100, 2)})

        # ---- 波段带带内状态（0.0.25 实施 07 P2 预钉；position 轨锚并行投影、
        #      与 default 三价不互覆；day_flag 电平：回落复位再报）----
        for edge, rule in (("band_lo", "band_lo_touch"), ("band_hi", "band_hi_touch")):
            lvl = row.get(edge)
            if lvl is None:
                continue
            bf = "%s|%s" % (code, rule)
            hit = t["price"] <= lvl if edge == "band_lo" else t["price"] >= lvl
            if hit:
                if not state["day_flags"].get(bf):
                    state["day_flags"][bf] = True
                    _emit(events, state, cfg, now, code, market, kind, rule,
                          {"price": t["price"], edge: lvl,
                           "dist_pct": round((t["price"] / lvl - 1) * 100, 2),
                           "note": "position 轨波段带（纪律参考线非止损指令，"
                                   "08 三层下行门是唯一离场口径）"})
            else:
                state["day_flags"][bf] = False

        # ---- 跳空（首轮判定，一次性）----
        thr = cfg["move_pct_cn"] if market == "cn" else cfg["move_pct_hk"]
        gap_flag = "%s|%s|gap_open" % (code, market)
        if t.get("prev_close") and t.get("open") and not state["day_flags"].get(
                gap_flag) and state["streak"].get("%s|seen" % code, 0) == 0:
            gap = (t["open"] / t["prev_close"] - 1) * 100
            if abs(gap) >= thr:
                state["day_flags"][gap_flag] = True
                _emit(events, state, cfg, now, code, market, kind, "gap_open",
                      {"open": t["open"], "prev_close": t["prev_close"],
                       "gap_pct": round(gap, 2)})
        _streak(state, "%s|seen" % code, True)

        # ---- ±% 异动（双轮消抖 + 开盘静默窗 + episode：回到阈值内才复位）----
        mk = "%s|abnormal_reported" % code
        if chg is not None and abs(chg) >= thr:
            n = _streak(state, "%s|abnormal" % code, True)
            if n >= 2 and not state["day_flags"].get(mk):
                state["day_flags"][mk] = True
                _emit(events, state, cfg, now, code, market, kind, "abnormal_move",
                      {"price": t["price"], "change_pct": chg},
                      notify=not quiet[market],
                      suppress_reason="opening_quiet_window" if quiet[market] else None)
        else:
            _streak(state, "%s|abnormal" % code, False)
            state["day_flags"][mk] = False

        # ---- 近触板（A 股；涨停价四舍五入有坑，近触板更稳）----
        if market == "cn" and row.get("limit_pct") and chg is not None:
            lim = row["limit_pct"] - cfg["limit_margin_pp"]
            for direction, hit in (("up", chg >= lim), ("down", chg <= -lim)):
                flag = "%s|%s|limit_%s" % (code, market, direction)
                if hit and not state["day_flags"].get(flag):
                    state["day_flags"][flag] = True
                    _emit(events, state, cfg, now, code, market, kind, "limit_hit",
                          {"change_pct": chg, "direction": direction,
                           "limit_pct": row["limit_pct"],
                           "note": "封板期间可能无法成交"})

        # ---- 模拟 T2 限价触价（只推演，写回属 P3 sim SSOT）----
        t2_flag = "%s|%s|t2fill" % (code, market)
        if kind == "sim" and entry_ref is not None and t.get("low") is not None \
                and t["low"] <= entry_ref and not state["day_flags"].get(t2_flag):
            state["day_flags"][t2_flag] = True
            fill = min(t["open"], entry_ref) if t.get("open") else entry_ref
            _emit(events, state, cfg, now, code, market, kind, "t2_pending_fill",
                  {"low": t["low"], "entry_ref": entry_ref,
                   "fill_price_assumed": fill,
                   "note": "限价触价推演成交，未写回（sim SSOT 写回属 P3）"})

    _flush_digest(events, state, cfg, now)
    return events, state


def _flush_digest(events, state, cfg, now):
    """风暴闸解除后补发一条聚合摘要（digest 事件不占通知预算、不进冷却）。"""
    d = state.get("digest_pending") or {}
    _prune_notify_log(state, cfg, now)
    if d.get("count") and len(state["notify_log"]) < cfg["storm_max"]:
        events.append({"ts": _iso(now), "code": "*", "market": "*",
                       "kind": "*", "rule": "storm_digest", "level": "T0",
                       "notify": True,
                       "mech_risk": None,
                       "facts": {"suppressed_count": d["count"],
                                 "kinds": d["kinds"],
                                 "note": "风暴闸压制期事件汇总，明细见台账"}})
        state["digest_pending"] = {}


def evaluate_market_guard(market, tick_dates, today_str, state, cfg, now):
    """快照时间戳日期守卫（休市工作日静态快照防线——P1 必备，不待 P4 日历）。
    判据取当轮全部 tick 的最大日期：只有全组都非今日才判休市（单票停牌/未成交
    的陈旧时间戳交给冻结检测，不误杀全市场）；halted 后出现今日时间戳即恢复。"""
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    events = []
    dates = [d for d in (tick_dates or []) if d]
    if not dates:
        return events
    latest = max(dates)
    if latest != today_str and not state["halted"].get(market):
        state["halted"][market] = True
        _emit(events, state, cfg, now, "*", market, "*", "market_halted",
              {"snapshot_date": latest, "today": today_str,
               "note": "全组快照日期非今日，判休市停轮（防静态快照假事件）"})
    elif latest == today_str and state["halted"].get(market):
        state["halted"][market] = False
        _emit(events, state, cfg, now, "*", market, "*", "market_resumed",
              {"snapshot_date": latest, "note": "快照恢复今日时间戳，解除停轮"})
    return events


def evaluate_hk_delay(max_lag_min, state, cfg, now):
    """港股源延迟降级（用户裁定：>15min 接受延迟盯盘、如实标注）。"""
    cfg = {**DEFAULT_CFG, **(cfg or {})}
    events = []
    if max_lag_min is not None and max_lag_min > cfg["hk_delay_min"] \
            and not state["hk_delay_notified"]:
        state["hk_delay_notified"] = True
        _emit(events, state, cfg, now, "*", "hk", "*", "hk_delayed",
              {"max_lag_min": round(max_lag_min, 1),
               "threshold_min": cfg["hk_delay_min"],
               "note": "港股行情延迟超阈值，降级为延迟盯盘（如实标注）"})
    return events


# ---------------------------------------------------------------- selftest

def _mk(code="600001", market="cn", kind="real", stop=26.00, target1=30.00,
        entry_ref=None, limit_pct=10.0, band_lo=None, band_hi=None,
        _ma20=None, _cost=None):
    row = {"code": code, "market": market, "kind": kind, "stop": stop,
           "target1": target1, "entry_ref": entry_ref, "limit_pct": limit_pct}
    for k, v in (("band_lo", band_lo), ("band_hi", band_hi),
                 ("_ma20", _ma20), ("_cost", _cost)):
        if v is not None:
            row[k] = v
    return row


def _tick(code="600001", market="cn", price=25.90, prev=27.15, opn=27.0,
          high=27.2, low=26.05, chg=None, vol=100000, ts="2026-11-03T10:00:00"):
    return {"code": code, "market": market, "price": price, "prev_close": prev,
            "open": opn, "high": high, "low": low,
            "change_pct": chg if chg is not None else round((price / prev - 1) * 100, 2),
            "volume": vol, "ts_utc8": ts, "lag_min": 0.0}


def selftest():
    ok = [0]

    def check(name, cond):
        ok[0] += 1
        if not cond:
            raise AssertionError("FAIL: %s" % name)

    t0 = dt.datetime(2026, 11, 3, 10, 0, 0, tzinfo=TZ)   # 周二，开盘后 30min
    cfg = {}

    def mins(m):
        return t0 + dt.timedelta(minutes=m)

    # 1) 止损：首触即报 → 次轮确认（机械降档事实）→ 收回 whipsaw
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick()], [_mk()], st, cfg, t0)
    check("首触 stop_break 通知", len(ev) == 1 and ev[0]["rule"] == "stop_break"
          and ev[0]["notify"] and ev[0]["facts"]["depth_pct"] > 0)
    ev, _ = evaluate([_tick(price=25.80)], [_mk()], st, cfg, mins(1.5))
    conf = [e for e in ev if e["rule"] == "stop_break_confirmed"]
    check("次轮确认+机械降档", conf and conf[0]["mech_risk"]["downgrade"])
    ev, _ = evaluate([_tick(price=26.20)], [_mk()], st, cfg, mins(3))
    check("收回 whipsaw", any(e["rule"] == "whipsaw" and e["notify"] for e in ev))
    # 收回后再破 = 事实反转：首触与再确认都必须穿透冷却投递（通知面最新状态不得停在「已收回」）
    ev, _ = evaluate([_tick(price=25.95)], [_mk()], st, cfg, mins(4))
    check("收回后再破穿透冷却", any(e["rule"] == "stop_break" and e["notify"] for e in ev))
    ev, _ = evaluate([_tick(price=25.90)], [_mk()], st, cfg, mins(5))
    check("收回后再确认穿透冷却",
          any(e["rule"] == "stop_break_confirmed" and e["notify"] for e in ev))
    # 加深穿透冷却
    st3 = fresh_state("2026-11-03")
    evaluate([_tick(price=25.80)], [_mk()], st3, cfg, t0)
    evaluate([_tick(price=25.20)], [_mk()], st3, cfg, mins(1.5))
    ev, _ = evaluate([_tick(price=24.60)], [_mk()], st3, cfg, mins(2))
    check("加深穿透冷却", any(e["rule"] == "stop_break" and e["notify"]
                              and e["facts"].get("deepened") for e in ev))
    # 确认后回升不报加深（基线随确认深度更新）
    st4 = fresh_state("2026-11-03")
    evaluate([_tick(price=25.87)], [_mk()], st4, cfg, t0)
    evaluate([_tick(price=25.20)], [_mk()], st4, cfg, mins(1.5))
    ev, _ = evaluate([_tick(price=25.30)], [_mk()], st4, cfg, mins(3))
    check("确认后回升不报加深", not any(e["facts"].get("deepened") for e in ev))

    # 2) 触目标 episode + 双轮异动 + 静默窗
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick(price=30.9, chg=6.0, high=31.0, low=27.0, opn=27.2)],
                     [_mk()], st, cfg, t0)
    check("触目标通知", any(e["rule"] == "target_hit" and e["notify"] for e in ev))
    check("异动首轮不报（双轮消抖）", not any(e["rule"] == "abnormal_move" for e in ev))
    ev, _ = evaluate([_tick(price=31.0, chg=6.2)], [_mk()], st, cfg, mins(1.5))
    check("异动次轮报", any(e["rule"] == "abnormal_move" and e["notify"] for e in ev))
    check("目标持续在线上不重报", not any(e["rule"] == "target_hit" for e in ev))
    ev, _ = evaluate([_tick(price=31.0, chg=6.2)], [_mk()], st, cfg, mins(40))
    check("电平事件冷却过期不重报", not any(e["rule"] in ("target_hit", "abnormal_move")
                                            for e in ev))
    evaluate([_tick(price=29.5, chg=4.0)], [_mk()], st, cfg, mins(41))
    ev, _ = evaluate([_tick(price=30.9, chg=4.5)], [_mk()], st, cfg, mins(42))
    check("回落后再越线才再报（冷却未过期则压制留痕）",
          any(e["rule"] == "target_hit" for e in ev))
    st2 = fresh_state("2026-11-03")
    early = dt.datetime(2026, 11, 3, 9, 33, 0, tzinfo=TZ)   # 静默窗内
    evaluate([_tick(price=31.0, chg=6.2)], [_mk()], st2, cfg, early)
    ev, _ = evaluate([_tick(price=31.1, chg=6.3)], [_mk()], st2, cfg,
                     early + dt.timedelta(seconds=60))
    am = [e for e in ev if e["rule"] == "abnormal_move"]
    check("静默窗内异动只记不发", am and not am[0]["notify"]
          and am[0]["suppress_reason"] == "opening_quiet_window")

    # 3) 跳空一次性（首轮判定）
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick(opn=25.0, price=26.3, chg=-3.1, low=24.9)],
                     [_mk()], st, cfg, t0)
    check("跳空开盘一次性报", any(e["rule"] == "gap_open" and e["notify"] for e in ev))
    ev, _ = evaluate([_tick(opn=25.0, price=26.3, chg=-3.1, low=24.9)],
                     [_mk()], st, cfg, mins(1.5))
    check("跳空不重复", not any(e["rule"] == "gap_open" for e in ev))

    # 4) 近触板 + change_pct 缺失健壮性
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick(price=29.9, chg=9.8, high=29.95)], [_mk()], st, cfg, t0)
    check("主板近涨停报", any(e["rule"] == "limit_hit"
                             and e["facts"]["direction"] == "up" for e in ev))
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick(code="300001", price=210.0, prev=180.0, opn=185.0,
                           high=212.0, low=184.0, chg=16.6)],
                     [_mk(code="300001", limit_pct=20.0, stop=None, target1=None)],
                     st, cfg, t0)
    check("创业板 16.6% 不触 20% 板", not any(e["rule"] == "limit_hit" for e in ev))
    st = fresh_state("2026-11-03")
    bad = _tick(price=25.80)
    bad["change_pct"] = None
    ev, _ = evaluate([bad], [_mk()], st, cfg, t0)
    check("change_pct=None 不崩且价位规则照判",
          any(e["rule"] == "stop_break" for e in ev))

    # 5) T2 限价触价推演（只 sim；fill=min(open, entry_ref)；当日一次）
    st = fresh_state("2026-11-03")
    sim = _mk(code="002648", kind="sim", stop=24.29, target1=27.77, entry_ref=24.54)
    ev, _ = evaluate([_tick(code="002648", price=24.60, prev=24.80, opn=24.70,
                           high=24.75, low=24.50, chg=-0.8)], [sim], st, cfg, t0)
    t2 = [e for e in ev if e["rule"] == "t2_pending_fill"]
    check("T2 触价推演", t2 and t2[0]["facts"]["fill_price_assumed"] == 24.54
          and t2[0]["notify"])
    ev, _ = evaluate([_tick(code="002648", price=24.40, prev=24.80, opn=24.70,
                           high=24.75, low=24.30, chg=-1.6)], [sim], st, cfg, mins(1.5))
    check("T2 当日只报一次", not any(e["rule"] == "t2_pending_fill" for e in ev))
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick(code="600002", price=8.9, prev=8.85, opn=8.88,
                           high=8.95, low=8.8, chg=0.6)],
                     [_mk(code="600002", kind="real", stop=None, target1=None,
                          entry_ref=8.85)], st, cfg, t0)
    check("实盘不做 T2 推演", not any(e["rule"] == "t2_pending_fill" for e in ev))

    # 6) 冻结 5 轮 → 挂起 → 复牌 + gap；当日再冻结只留痕
    st = fresh_state("2026-11-03")
    row = _mk(stop=None, target1=None)
    for i in range(5):
        ev, _ = evaluate([_tick(price=8.80, vol=0, chg=-0.6)], [row], st, cfg, mins(i))
    check("冻结挂起", st["suspended"].get("600001") and
          any(e["rule"] == "frozen" and e["notify"] for e in ev))
    ev, _ = evaluate([_tick(price=7.90, vol=50000, chg=-10.7)], [row], st, cfg, mins(6))
    check("复牌 + gap 提醒", any(e["rule"] == "resumed" for e in ev)
          and any(e["rule"] == "gap_move" for e in ev))
    for i in range(5):
        ev, _ = evaluate([_tick(price=7.90, vol=50000, chg=-10.7)], [row], st, cfg,
                         mins(7 + i))
    fr = [e for e in ev if e["rule"] == "frozen"]
    check("当日再冻结只留痕不通知", fr and not fr[0]["notify"]
          and fr[0]["suppress_reason"] == "repeat_frozen")
    # 午休冻结豁免：午前累计 4 轮 → 午休 → 13:00 首轮不变不误判 frozen
    st = fresh_state("2026-11-03")
    pre = dt.datetime(2026, 11, 3, 11, 20, 0, tzinfo=TZ)
    for i in range(4):
        evaluate([_tick(price=8.80, vol=0, chg=-0.6)], [row], st, cfg,
                 pre + dt.timedelta(minutes=2 * i))
    for i in range(6):
        evaluate([_tick(price=8.80, vol=0, chg=-0.6)], [row], st, cfg,
                 dt.datetime(2026, 11, 3, 11, 40 + i, 0, tzinfo=TZ))
    ev, _ = evaluate([_tick(price=8.80, vol=0, chg=-0.6)], [row], st, cfg,
                     dt.datetime(2026, 11, 3, 13, 0, 0, tzinfo=TZ))
    check("午休清零：午后首轮不误判停牌", not st["suspended"].get("600001")
          and not any(e["rule"] == "frozen" for e in ev))

    # 7) 日期守卫（全组最大日期判定 + 可恢复）与港股延迟
    st = fresh_state("2026-11-03")
    ev = evaluate_market_guard("cn", ["2026-10-30", "2026-11-03"], "2026-11-03",
                               st, cfg, t0)
    check("单票陈旧不误杀全市场", not ev and not st["halted"].get("cn"))
    ev = evaluate_market_guard("cn", ["2026-10-30", "2026-10-30"], "2026-11-03",
                               st, cfg, t0)
    check("全组陈旧判休市停轮", st["halted"]["cn"] and ev[0]["rule"] == "market_halted")
    check("守卫一次性", not evaluate_market_guard("cn", ["2026-10-30"], "2026-11-03",
                                                   st, cfg, mins(3)))
    ev = evaluate_market_guard("cn", ["2026-11-03"], "2026-11-03", st, cfg, mins(6))
    check("今日时间戳恢复解除停轮", not st["halted"]["cn"]
          and ev[0]["rule"] == "market_resumed")
    st = fresh_state("2026-11-03")
    ev = evaluate_hk_delay(18.0, st, cfg, t0)
    check("港股延迟降级一次性", ev and ev[0]["rule"] == "hk_delayed"
          and not evaluate_hk_delay(20.0, st, cfg, t0))

    # 7b) 事件级「××复核」短语（0.0.25）：注入族 + 被压制行仍带 + 运维类零短语
    check("fresh_state 含 ma20_ep 键", "ma20_ep" in fresh_state("2026-11-03"))
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick()], [_mk()], st, cfg, t0)
    hint = {e["rule"]: e.get("review") for e in ev}
    check("止损事件带复核短语", hint.get("stop_break") == "止损复核")
    st = fresh_state("2026-11-03")
    ev, _ = evaluate([_tick(price=30.9, chg=6.0, high=31.0, low=27.0, opn=27.2)],
                     [_mk()], st, cfg, t0)
    check("触目标带止盈复核短语",
          any(e["rule"] == "target_hit" and e.get("review") == "止盈复核"
              for e in ev))
    st["stock_notify_count"]["600001"] = 6   # 压到单股日上限：短语仍随台账落
    evaluate([_tick(price=29.5, chg=1.0)], [_mk()], st, cfg, mins(1))
    ev, _ = evaluate([_tick(price=30.5, chg=1.0)], [_mk()], st, cfg, mins(2))
    sup = [e for e in ev if e.get("suppress_reason") == "stock_daily_cap"]
    check("被压制事件仍带复核短语",
          sup and sup[0].get("review") == "止盈复核")
    ops_rules = ("gap_open", "limit_hit", "frozen", "resumed", "gap_move",
                 "market_halted", "market_resumed", "hk_delayed", "storm_digest",
                 "source_dropped", "data_stale")
    check("运维类规则零复核短语",
          not any(r in _REVIEW_HINT for r in ops_rules))

    # 8a) MA20 破位（episode：首报降档 medium，回线复位再破再报；缺 _ma20 不判）
    st = fresh_state("2026-11-03")
    row20 = _mk(stop=None, target1=None, _ma20=28.00)
    ev, _ = evaluate([_tick(price=27.30, chg=-1.0)], [row20], st, cfg, t0)
    mb = [e for e in ev if e["rule"] == "ma20_break"]
    check("MA20 破位首报+机械降档 medium",
          mb and mb[0]["mech_risk"] == {"downgrade": True, "severity": "medium"}
          and mb[0].get("review") == "均线复核" and "dist_pct" in mb[0]["facts"])
    ev, _ = evaluate([_tick(price=27.31, chg=-1.0)], [row20], st, cfg, mins(1))
    check("破位持续不重报", not any(e["rule"] == "ma20_break" for e in ev))
    ev, _ = evaluate([_tick(price=27.60, chg=-1.0)], [row20], st, cfg, mins(2))
    ev, _ = evaluate([_tick(price=27.29, chg=-1.0)], [row20], st, cfg, mins(3))
    check("回线复位后再破再报", any(e["rule"] == "ma20_break" for e in ev))
    ev, _ = evaluate([_tick(price=25.90)], [_mk(stop=None, target1=None)], st, cfg,
                     mins(4))
    check("缺 _ma20 整族禁用（data_stale 日不判）",
          not any(e["rule"] == "ma20_break" for e in ev))

    # 8b) 跟踪止损：+15% 武装（跨日态）→ 武装后破 MA20 退出；facts 零成本派生量
    st = fresh_state("2026-11-03")
    tr = {}
    rowt = _mk(stop=None, target1=None, _ma20=11.00, _cost=10.00)
    ev, _ = evaluate([_tick(price=11.60, chg=1.0, high=11.7, low=11.5, opn=11.5)],
                     [rowt], st, cfg, t0, trailing=tr)
    check("浮盈达武装线触发武装事件",
          any(e["rule"] == "trailing_armed" and e.get("review") == "跟踪止损复核"
              for e in ev) and tr["600001"]["armed"] is True
          and tr["600001"]["high"] == 11.7)   # 含快照当日高点（price 11.60 < high 11.70）
    check("武装当轮在 MA20 上方不出退出事件",
          not any(e["rule"] == "trailing_exit" for e in ev))
    ar = [e for e in ev if e["rule"] == "trailing_armed"][0]
    check("武装事件 facts 零成本派生量（脱敏）",
          "gain" not in json.dumps(ar["facts"]) and "arm_level" not in
          json.dumps(ar["facts"]) and "cost" not in json.dumps(ar["facts"]))
    ev, _ = evaluate([_tick(price=11.65, chg=1.0, high=11.8)], [rowt], st, cfg,
                     mins(1), trailing=tr)
    check("high 跨轮 max 更新（含快照当日高点）", tr["600001"]["high"] == 11.8
          and not any(e["rule"] == "trailing_exit" for e in ev))
    ev, _ = evaluate([_tick(price=10.90, chg=1.0, high=10.90)], [rowt], st, cfg,
                     mins(2), trailing=tr)
    check("武装后破 MA20 出退出事件",
          any(e["rule"] == "trailing_exit" and e["notify"] for e in ev))
    ev, _ = evaluate([_tick(price=10.89, chg=1.0, high=10.89)], [rowt], st, cfg,
                     mins(3), trailing=tr)
    check("退出事件当日一次", not any(e["rule"] == "trailing_exit" for e in ev))
    st2 = fresh_state("2026-11-03")
    tr2 = {}
    ev, _ = evaluate([_tick(price=10.50, chg=1.0, high=10.50)], [rowt], st2, cfg,
                     t0, trailing=tr2)
    ev, _ = evaluate([_tick(price=10.90, chg=1.0, high=10.90)], [rowt], st2, cfg,
                     mins(1), trailing=tr2)
    check("未武装破 MA20 不出退出事件",
          not any(e["rule"] == "trailing_exit" for e in ev)
          and not tr2.get("600001", {}).get("armed"))

    # 8c) 波段带带内状态（day_flag 电平：回落复位再报；缺锚不判）
    st = fresh_state("2026-11-03")
    rowb = _mk(stop=None, target1=None, band_lo=25.00, band_hi=31.00)
    ev, _ = evaluate([_tick(price=24.90, chg=-1.0)], [rowb], st, cfg, t0)
    check("触及下沿低吸复核",
          any(e["rule"] == "band_lo_touch" and e.get("review") == "低吸复核"
              for e in ev))
    ev, _ = evaluate([_tick(price=24.80, chg=-1.0)], [rowb], st, cfg, mins(1))
    check("下沿持续在线不重报", not any(e["rule"] == "band_lo_touch" for e in ev))
    evaluate([_tick(price=25.50, chg=-1.0)], [rowb], st, cfg, mins(2))
    ev, _ = evaluate([_tick(price=24.95, chg=-1.0)], [rowb], st, cfg, mins(3))
    check("回升复位后再触再报", any(e["rule"] == "band_lo_touch" for e in ev))
    ev, _ = evaluate([_tick(price=31.10, chg=1.0)], [rowb], st, cfg, mins(4))
    check("触及上沿高抛复核",
          any(e["rule"] == "band_hi_touch" and e.get("review") == "高抛复核"
              for e in ev))
    ev, _ = evaluate([_tick(price=30.00, chg=1.0)],
                     [_mk(stop=None, target1=None)], st, cfg, mins(5))
    check("缺波段带锚不判", not any(e["rule"].startswith("band_") for e in ev))

    # 8) 风暴闸：9 只齐触 → 第 9 条压制（digest 带代码）→ 无新事件也能补发摘要
    st = fresh_state("2026-11-03")
    uni = [_mk(code="6019%02d" % i, stop=None, target1=100.0 + i, limit_pct=20.0)
           for i in range(9)]
    ticks = [_tick(code="6019%02d" % i, price=100.0 + i, prev=90.0, opn=94.0,
                   high=101.0, low=93.0, chg=11.1) for i in range(9)]
    ev, _ = evaluate(ticks, uni, st, cfg, t0)
    notified = [e for e in ev if e["notify"]]
    suppressed = [e for e in ev if e.get("suppress_reason") == "storm_gate"]
    check("风暴闸压制第 9 条", len(notified) == 8 and len(suppressed) == 1
          and st["digest_pending"]["kinds"]["target_hit"] == ["601908"])
    ev, _ = evaluate([], uni, st, cfg, mins(11))
    dg = [e for e in ev if e["rule"] == "storm_digest"]
    check("无新事件窗口滚动后仍补发摘要（带代码）",
          dg and dg[0]["facts"]["kinds"]["target_hit"] == ["601908"])
    # 风险事实豁免风暴闸
    st = fresh_state("2026-11-03")
    evaluate(ticks, uni, st, cfg, t0)
    risk_uni = [_mk(code="601999", stop=26.00, target1=None)]
    evaluate([_tick(code="601999", price=25.80)], risk_uni, st, cfg, mins(0.5))
    ev, _ = evaluate([_tick(code="601999", price=25.70)], risk_uni, st, cfg, mins(1))
    check("止损确认豁免风暴闸",
          any(e["rule"] == "stop_break_confirmed" and e["notify"] for e in ev))
    # 单股日上限：信息类耗尽上限后止损确认仍投递
    st = fresh_state("2026-11-03")
    st["stock_notify_count"]["600001"] = 6
    ev, _ = evaluate([_tick(price=31.0, chg=1.0)], [_mk()], st, cfg, t0)
    check("信息类事件受单股日上限",
          any(e.get("suppress_reason") == "stock_daily_cap" for e in ev))
    evaluate([_tick(price=25.80, chg=-4.0)], [_mk()], st, cfg, mins(1))
    ev, _ = evaluate([_tick(price=25.70, chg=-4.4)], [_mk()], st, cfg, mins(2))
    check("止损确认豁免单股日上限",
          any(e["rule"] == "stop_break_confirmed" and e["notify"] for e in ev))

    print("rules selftest: %d checks OK" % ok[0])
    return True


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="盯盘规则引擎（参考实现，口径见 references/07）")
    ap.add_argument("--selftest", action="store_true", help="离线回归（零网络）")
    a = ap.parse_args()
    if a.selftest:
        selftest()
        sys.exit(0)
    print(__doc__, file=sys.stderr)
    sys.exit(2)
