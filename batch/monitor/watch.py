#!/usr/bin/env python3
"""盯盘守卫（P1）——在册股票盘中监控：宇宙派生 / 价格面轮询 / 触发告警 /
收盘复核。口径以 references/07-monitor.md 为准（本文件是参考实现）。

红线落地：只提示不执行（无任何交易接口）；本地通知只报事实（零成本
绝对值、零指令性建议，尾注「待收盘复核·非投资建议」）；永不写
signals.json（当日信号登记唯一归每晚全诊）；盘中结论以收盘复核为准。

用法（sk = skill 根目录）：
  uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \\
    <sk>/batch/monitor/watch.py --loop            # 常驻：盘前等待→盘中轮询→收盘复核→退出
  <sk>/batch/monitor/watch.py --print-universe    # 派生盯盘宇宙（脱敏：只投影阈值）
  <sk>/batch/monitor/watch.py --once              # 单轮（launchd 补轮/调试）
  <sk>/batch/monitor/watch.py --close             # 收盘复核（幂等重渲）
  <sk>/batch/monitor/watch.py --verify-hk         # 港股源验证（收盘后跑）
  <sk>/batch/monitor/watch.py --selftest          # 离线回归（零网络）
"""
import argparse
import datetime as dt
import fcntl
import json
import os
import subprocess
import sys
import time

_SK = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_SK, "scripts"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import fetch as vfetch          # noqa: E402  _http_text/_parse_qt_s/session_phase/
#                               cn_exchange/load_fetch_state/save_fetch_state/fetch_daily_bars
import archive as varchive      # noqa: E402  write_json_atomic/load_portfolio
import rules as vrules          # noqa: E402

TZ = vfetch.TZ_CN
REVIEW_MIN = {"cn": 910, "hk": 970}   # 收盘复核时点 15:10 / 16:10（盘后定价/收盘竞价缓冲）
DISCLAIMER = ("本监控由 vibe-stock 生成，仅供学习与研究参考，不构成投资建议；"
              "系统不下单。")

# 通知文案（事实级；指令性建议一律不进通知——07「通知口径」）
_RULE_TEXT = {
    "stop_break": "跌破止损线", "stop_break_confirmed": "持续跌破止损线（2 轮确认）",
    "whipsaw": "击穿后收回（待收盘终判）", "target_hit": "触及目标价1",
    "abnormal_move": "盘中异动", "gap_open": "跳空开盘",
    "limit_hit": "触板", "t2_pending_fill": "T2 限价触价（推演成交，未写回）",
    "frozen": "疑似停牌（价量冻结）", "resumed": "复牌", "gap_move": "复牌异动",
    "market_halted": "休市停轮", "market_resumed": "解除停轮",
    "hk_delayed": "港股行情延迟", "storm_digest": "事件聚合",
    "source_dropped": "行情缺行",
}


def _now():
    return dt.datetime.now(TZ)


# ---------------------------------------------------------------- 基础设施

def monitor_paths(state_dir):
    m = os.path.join(state_dir, "monitor")
    return {"root": m, "universe": os.path.join(m, "universe.json"),
            "state": os.path.join(m, "state.json"),
            "ticks": os.path.join(m, "ticks"), "events": os.path.join(m, "events"),
            "summary": os.path.join(m, "day-summary"), "logs": os.path.join(m, "logs")}


def ensure_state(state_dir, today):
    """加载当日状态（日期变更整体归零——盯盘状态是日粒度的）。"""
    st = {}
    path = monitor_paths(state_dir)["state"]
    if os.path.exists(path):
        try:
            with open(path, encoding="utf-8") as f:
                st = json.load(f)
        except (OSError, ValueError):
            st = {}
    rs = st.get("rules") or {}
    if rs.get("date") != today:
        rs = vrules.fresh_state(today)
    for k, v in vrules.fresh_state(today).items():   # 老版本 state 升级不缺键
        rs.setdefault(k, v)
    same_day = st.get("date") == today
    return {"date": today, "rules": rs,
            "src_fail": st.get("src_fail", {}) if same_day else {},
            "hk_source": st.get("hk_source"),
            "close_done": st.get("close_done", False) if same_day else False,
            "next_due": st.get("next_due", {}) if same_day else {}}


def save_state(state_dir, st):
    p = monitor_paths(state_dir)
    os.makedirs(p["root"], exist_ok=True)
    varchive.write_json_atomic(p["state"], st)


def append_jsonl(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "a", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def read_jsonl(path):
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


class SingleInstance:
    """watch 单实例锁（防 launchd 双开；I-005：fetch_state 无锁的教训）。"""

    def __init__(self, state_dir):
        os.makedirs(monitor_paths(state_dir)["root"], exist_ok=True)
        self.path = os.path.join(monitor_paths(state_dir)["root"], "watch.lock")
        self.fd = None

    def acquire(self):
        self.fd = open(self.path, "a+")
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.fd.seek(0)
            self.fd.truncate()
            self.fd.write("%d\n" % os.getpid())
            self.fd.flush()
            return True
        except OSError:
            self.fd.close()
            self.fd = None
            return False

    def release(self):
        if self.fd:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()
            self.fd = None


class FetchLock:
    """全局取数锁（flock 咨询锁：持有进程退出即由内核释放，不支持抢占存活
    持有者，竞争超时即挂起告警）。watch 侧统一入口；全诊 prepare 不识别此锁
    ——盯盘期间不跑全诊仍是使用纪律（07「熔断隔离」）。"""

    def __init__(self, state_dir):
        self.path = os.path.join(state_dir, "fetch_state.lock")
        self.fd = None

    def acquire(self, timeout=120):
        deadline = time.time() + timeout
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        while True:
            self.fd = open(self.path, "a+")
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.fd.seek(0)
                self.fd.truncate()
                self.fd.write("%d %s\n" % (os.getpid(), _now().isoformat()))
                self.fd.flush()
                return True
            except OSError:
                self.fd.close()
                self.fd = None
                if time.time() >= deadline:
                    return False
                time.sleep(3)

    def release(self):
        if self.fd:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()
            self.fd = None


NOTIFY_TAIL = " ·待收盘复核·非投资建议"


def notify(msg, title="vibe-stock 盯盘", sound=False, no_notify=False):
    """macOS 本地通知（osascript，零第三方通道——07「告警边界」）。尾注统一在
    此追加（07「通知口径」：全部通知含运维类一律带尾注，无例外）。"""
    msg = msg + NOTIFY_TAIL
    print("notify: [%s] %s" % (title, msg), flush=True)
    if no_notify:
        return
    safe = msg.replace("\\", "\\\\").replace('"', '\\"')
    script = ('display notification "%s" with title "%s"%s'
              % (safe, title, ' sound name "Submarine"' if sound else ""))
    try:
        subprocess.run(["osascript", "-e", script], timeout=10,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (OSError, subprocess.SubprocessError):
        pass   # 无 GUI（SSH/未登入）时静默降级为 stdout——台账仍有全量


# ---------------------------------------------------------------- 宇宙派生

def latest_allocation(state_dir):
    """最新批量配置（模拟组合三价常量）：目录名日期最大且 rows 非空。"""
    scans = os.path.join(state_dir, "reports", "_scans")
    if not os.path.isdir(scans):
        return None
    for d in sorted(os.listdir(scans), reverse=True):
        path = os.path.join(scans, d, "portfolio", "allocation.json")
        if not os.path.exists(path):
            continue
        try:
            with open(path, encoding="utf-8") as f:
                alloc = json.load(f)
            if alloc.get("rows"):
                return {"scan": d, "rows": alloc["rows"]}
        except (OSError, ValueError):
            continue
    return None


def latest_signals(state_dir):
    """signals.json 组内最新信号（价位锚 SSOT）：{code: {...}}（append 序，
    后写覆盖前写 = 组内最新）。只取 default 轨——position 轨的波段带键
    （band_lo/band_hi/trail_ref）语义不同，混入会覆盖短线止损/目标锚
    （07「价位锚分轨」句；波段带锚走 P2 带内状态规则，另行接入）。"""
    path = os.path.join(state_dir, "signals.json")
    out = {}
    if not os.path.exists(path):
        return out
    try:
        with open(path, encoding="utf-8") as f:
            sigs = json.load(f)
    except (OSError, ValueError):
        return out
    for s in sigs:
        if s.get("profile", "default") != "default":
            continue
        out[s["code"]] = {"market": s.get("market"), "name": s.get("stock_name"),
                          "key_levels": s.get("key_levels") or {},
                          "date": s.get("date")}
    return out


def limit_pct_cn(code, name):
    """A 股近触板限幅：创业/科创 20、北交 30、主板 10；名称含 ST 主板减半。
    （已知简化：创业/科创 ST 不减半——07「触板规则」句。）"""
    if code.startswith(("30", "68")):
        return 20.0
    if code.startswith(("8", "4", "92")):
        return 30.0
    return 5.0 if name and "ST" in name.upper() else 10.0


def derive_universe(state_dir):
    """盯盘宇宙 = 实盘持仓 ∪ 模拟配置 ∪ 信号观察票。脱敏（无条件规则）：
    只投影阈值与派生量，成本/数量绝不落盘——运行期现算现用。"""
    problems = []
    real = varchive.load_portfolio(state_dir, problems)
    real_codes = {}
    for key in real:
        code, _, market = key.rpartition(".")
        real_codes[code] = market
    alloc = latest_allocation(state_dir)
    sim_codes = {}
    if alloc:
        for r in alloc["rows"]:
            sim_codes[r["code"]] = {
                "market": "cn" if len(r["code"]) == 6 and r["code"].isdigit() else "hk",
                "stop": r.get("stop"), "entry_ref": r.get("entry_ref"),
                "target1": r.get("target1")}
    sigs = latest_signals(state_dir)
    names = {}
    names_path = os.path.join(state_dir, "names.json")
    if os.path.exists(names_path):
        try:
            with open(names_path, encoding="utf-8") as f:
                names = json.load(f)
        except (OSError, ValueError):
            names = {}

    rows, warnings = [], list(problems)
    for code in dict.fromkeys(list(real_codes) + list(sim_codes) + list(sigs)):
        kind = "real" if code in real_codes else ("sim" if code in sim_codes else "watch")
        market = (real_codes.get(code) or sim_codes.get(code, {}).get("market")
                  or (sigs.get(code) or {}).get("market"))
        if market not in ("cn", "hk"):
            continue
        name = names.get("%s:%s" % (market, code)) \
            or (sigs.get(code) or {}).get("name") or code
        kl = (sigs.get(code) or {}).get("key_levels") or {}
        levels = {"stop": kl.get("stop"), "target1": kl.get("target1"),
                  "entry_ref": kl.get("entry_ref")}
        source = "signals"
        if kind == "sim" and levels["stop"] is None and sim_codes[code].get("stop"):
            levels = {k: sim_codes[code].get(k) for k in levels}
            source = "allocation"
        if levels["stop"] is None and levels["target1"] is None:
            warnings.append("%s %s 无价位锚（signals/allocation 均缺），降级为仅 "
                            "%%/触板监控" % (code, name))
            source = "none"
        rows.append({"code": code, "market": market, "kind": kind, "name": name,
                     "stop": levels["stop"], "target1": levels["target1"],
                     "entry_ref": levels["entry_ref"], "levels_source": source,
                     "limit_pct": limit_pct_cn(code, name) if market == "cn" else None,
                     "signal_date": (sigs.get(code) or {}).get("date")})
    order = {"real": 0, "sim": 1, "watch": 2}
    rows.sort(key=lambda r: (order[r["kind"]], r["market"], r["code"]))
    return {"generated_at": _now().isoformat(timespec="seconds"),
            "date": _now().date().isoformat(), "rows": rows,
            "counts": {k: sum(1 for r in rows if r["kind"] == k)
                       for k in ("real", "sim", "watch")},
            "warnings": warnings}


def load_universe(state_dir, regenerate=False):
    """加载当日宇宙（跨日或缺失时自动重派生；--print-universe 强制重派生）。"""
    p = monitor_paths(state_dir)
    uni = None
    if not regenerate and os.path.exists(p["universe"]):
        try:
            with open(p["universe"], encoding="utf-8") as f:
                uni = json.load(f)
        except (OSError, ValueError):
            uni = None
    if uni is None or uni.get("date") != _now().date().isoformat():
        uni = derive_universe(state_dir)
        os.makedirs(p["root"], exist_ok=True)
        varchive.write_json_atomic(p["universe"], uni)
    return uni


# ---------------------------------------------------------------- 价格面

def parse_qt_full_line(line):
    """qt 全量快照单行 → 监控 tick（A 股 v_shXXXXXX 与港股 r_hkXXXXX 同构）。
    位序（0 基，与 fetch._parse_qt_full 同源钉住 + 监控扩展位）：1=名称
    3=现价 4=昨收 5=今开 6=成交量 30=时间戳 31=涨跌额 32=涨跌幅% 33=最高
    34=最低 37=成交额 38=换手率%。位序漂移防护：结构自洽校验不过即弃。"""
    if '"' not in line:
        return None
    body = line[line.index('"') + 1:line.rindex('"')]
    f = body.split("~")
    if len(f) < 39:
        return None

    def num(i):
        try:
            return float(f[i])
        except (IndexError, ValueError):
            return None

    if not num(3) or num(3) <= 0 or not num(4):
        return None
    ts = None
    try:
        if len(f[30]) >= 14 and f[30][:14].isdigit():      # A 股：20261102150441
            ts = dt.datetime.strptime(f[30][:14], "%Y%m%d%H%M%S")
        elif "/" in f[30]:                                 # 港股：2026/11/02 15:04:23
            ts = dt.datetime.strptime(f[30][:19], "%Y/%m/%d %H:%M:%S")
    except ValueError:
        ts = None
    ts = ts.replace(tzinfo=TZ) if ts else None
    return {"code": f[2], "name": f[1], "price": num(3), "prev_close": num(4),
            "open": num(5),
            "volume": num(6), "ts_raw": f[30], "change_amt": num(31),
            "change_pct": num(32), "high": num(33), "low": num(34),
            "amount": num(37), "turnover_pct": num(38),
            "ts_utc8": ts.isoformat(timespec="seconds") if ts else None}


def structural_check(tick, market):
    """结构自洽校验（防上游位序漂移静默错价——07「源校验」）：涨跌额==价差、
    low≤{price,open}≤high；A 股另验 vwap∈[low,high]±2%（量纲手→股；港股量
    纲未钉不消费量能，不验）。"""
    eps = max(0.02, 0.002 * tick["price"])
    if tick["change_amt"] is not None and \
            abs((tick["price"] - tick["prev_close"]) - tick["change_amt"]) > eps:
        return False
    for v in [x for x in (tick["price"], tick["open"]) if x is not None]:
        if tick["low"] is not None and v < tick["low"] - eps:
            return False
        if tick["high"] is not None and v > tick["high"] + eps:
            return False
    if market == "cn" and tick["volume"] and tick["amount"]:
        # A 股全量快照量纲：主板/创业/北交为手、科创 688 为股（2026-11-02 实测）
        shares = tick["volume"] * (1 if tick.get("code", "").startswith("688") else 100)
        vwap = tick["amount"] * 1e4 / shares if shares > 0 else None
        if vwap and tick["low"] and tick["high"] and \
                not (tick["low"] * 0.98 <= vwap <= tick["high"] * 1.02):
            return False
    return True


def parse_qt_response(text, market):
    """多行 qt 响应 → {变量名: tick}（v_shXXXXXX / r_hkXXXXX）；结构不过的
    行丢弃并计数。"""
    out, dropped = {}, 0
    for line in text.split(";"):
        line = line.strip()
        if '"' not in line:
            continue
        symbol = line.split("=", 1)[0].strip()
        tick = parse_qt_full_line(line)
        if tick is None or not structural_check(tick, market):
            dropped += 1
            continue
        out[symbol] = tick
    return out, dropped


def poll_market(market, rows, st, now, interval):
    """一轮价格面（≤2 次批量 HTTP + 指数 1 次）。失败本地退避计数，不写共享
    fetch_state（07「熔断隔离」：盯盘预算不耗诊股侧熔断额度）。"""
    cn = [vfetch.cn_exchange(r["code"]) + r["code"] for r in rows
          if r["market"] == "cn"]
    hk = ["r_hk" + r["code"].zfill(5) for r in rows if r["market"] == "hk"]
    syms = cn if market == "cn" else hk
    if not syms:
        return [], {"ok": True, "dropped": 0}
    url = "https://qt.gtimg.cn/q="
    parsed, dropped = {}, 0
    try:
        for i in range(0, len(syms), 30):   # 30 码/批（stage_a 同限）
            raw = vfetch._http_text(url + ",".join(syms[i:i + 30]), timeout=10)
            got, d = parse_qt_response(raw, market)
            parsed.update(got)
            dropped += d
        idx = "s_sh000300" if market == "cn" else "s_hkHSI"
        try:
            indices = vfetch._parse_qt_s(vfetch._http_text(url + idx, timeout=10))
        except Exception:
            indices = []
    except Exception as e:
        st["src_fail"][market] = st["src_fail"].get(market, 0) + 1
        return None, {"ok": False, "err": str(e)[:200],
                      "backoff_s": next_delay(st, market, interval)}
    st["src_fail"][market] = 0
    tick_dates = [t["ts_utc8"][:10] for t in parsed.values() if t["ts_utc8"]]
    ticks = []
    for r in rows:
        sym = ("v_" + vfetch.cn_exchange(r["code"]) + r["code"]) if market == "cn" \
            else "v_r_hk" + r["code"].zfill(5)
        t = parsed.get(sym)
        if t is None:
            continue
        lag = ((now - dt.datetime.fromisoformat(t["ts_utc8"])).total_seconds() / 60
               if t["ts_utc8"] else None)
        ticks.append({"code": r["code"], "market": market, "price": t["price"],
                      "prev_close": t["prev_close"], "open": t["open"],
                      "high": t["high"], "low": t["low"], "change_pct": t["change_pct"],
                      "volume": t["volume"], "amount": t["amount"],
                      "turnover_pct": t["turnover_pct"], "ts_utc8": t["ts_utc8"],
                      "lag_min": round(lag, 1) if lag is not None else None,
                      "local_ts": now.isoformat(timespec="seconds")})
    missing = [r["code"] for r in rows if r["code"] not in {t["code"] for t in ticks}]
    return ticks, {"ok": True, "dropped": dropped, "missing": missing, "n": len(ticks),
                   "tick_dates": tick_dates,
                   "indices": indices}


def next_delay(st, market, base_interval):
    """本地指数退避（独立于 fetch_state 共享账本）：180→540→600 封顶。"""
    n = st["src_fail"].get(market, 0)
    return min(base_interval * (3 ** min(n, 2)), 600) if n else base_interval


# ---------------------------------------------------------------- 事件派发

def fmt_facts(rule, facts, name):
    if rule in ("stop_break", "stop_break_confirmed"):
        return "%s 现价 %.2f 已低于止损线 %.2f（-%.2f%%）" % (
            name, facts["price"], facts["stop"], facts["depth_pct"])
    if rule == "whipsaw":
        return "%s 现价 %.2f 回到止损线 %.2f 上方" % (name, facts["price"], facts["stop"])
    if rule == "target_hit":
        return "%s 现价 %.2f 触及目标价1 %.2f" % (name, facts["price"], facts["target1"])
    if rule == "abnormal_move":
        return "%s 现价 %.2f 涨跌幅 %.1f%%" % (name, facts["price"], facts["change_pct"])
    if rule == "gap_open":
        return "%s 跳空开盘 %.2f（昨收 %.2f，%.1f%%）" % (
            name, facts["open"], facts["prev_close"], facts["gap_pct"])
    if rule == "limit_hit":
        return "%s %s（涨跌幅 %.1f%%，限幅 %.0f%%）" % (
            name, "近涨停" if facts["direction"] == "up" else "近跌停",
            facts["change_pct"], facts["limit_pct"])
    if rule == "t2_pending_fill":
        return "%s 盘中低点 %.2f 触及 T2 限价 %.2f（推演成交 %.2f，未写回）" % (
            name, facts["low"], facts["entry_ref"], facts["fill_price_assumed"])
    if rule == "frozen":
        return "%s 价量连续 %d 轮不变，疑似停牌" % (name, facts["rounds"])
    if rule in ("resumed", "gap_move"):
        return "%s 复牌现价 %.2f（冻结价 %.2f）" % (
            name, facts["price"], facts.get("frozen_price", facts["price"]))
    if rule == "storm_digest":
        return "风暴闸压制 %d 条事件：%s（明细见台账）" % (
            facts["suppressed_count"],
            "；".join("%s %s" % (_RULE_TEXT.get(k, k), ",".join(v))
                     for k, v in sorted(facts["kinds"].items())))
    if rule == "market_halted":
        return "%s 全组快照日期 %s 非今日，判休市停轮" % (name, facts["snapshot_date"])
    if rule == "market_resumed":
        return "%s 快照恢复今日时间戳，解除停轮" % name
    if rule == "hk_delayed":
        return "港股行情延迟 %.0f 分钟（阈值 %d），降级为延迟盯盘" % (
            facts["max_lag_min"], facts["threshold_min"])
    if rule == "source_dropped":
        return "%s 行情缺行/校验未过，本轮失明：%s" % (name, ",".join(facts["codes"]))
    return "%s %s" % (name, json.dumps(facts, ensure_ascii=False))


def dispatch(events, uni_rows, no_notify, hk_delayed=False):
    """通知派发：只对 notify=True 的事件发电磁通知（其余已留痕台账）。
    港股在延迟降级态时文案加「延迟行情」前缀（如实标注，07「延迟口径」）。"""
    names = {r["code"]: r["name"] for r in uni_rows}
    names.update({"*": "", "cn": "A 股", "hk": "港股"})
    for ev in events:
        if not ev.get("notify"):
            continue
        label = names.get(ev["code"]) or names.get(ev.get("market"), "")
        msg = fmt_facts(ev["rule"], ev["facts"], label or ev["code"])
        if hk_delayed and ev.get("market") == "hk":
            msg = "(延迟行情) " + msg
        notify(msg,
               sound=ev["rule"] in ("stop_break_confirmed", "market_halted"),
               no_notify=no_notify)


def run_round(state_dir, uni, st, cfg, no_notify, now=None):
    """单轮：逐市场门控轮询 → 守卫/规则 → 台账 + 状态 + 通知。"""
    cfg = {**vrules.DEFAULT_CFG, **(cfg or {})}
    now = now or _now()
    today = now.date().isoformat()
    p = monitor_paths(state_dir)
    interval = cfg.get("interval_s", 180)
    all_events, all_ticks, hk_delayed = [], [], False
    due = st.setdefault("next_due", {})
    for market in ("cn", "hk"):
        rows_m = [r for r in uni["rows"] if r["market"] == market]
        if not rows_m or st["rules"]["halted"].get(market):
            continue
        if vfetch.session_phase(market, None, now)["phase"] != "intraday":
            continue
        if due.get(market) and now < dt.datetime.fromisoformat(due[market]):
            continue   # 该市场仍在退避窗内（按市场独立计时）
        ticks, meta = poll_market(market, rows_m, st, now, interval)
        due[market] = (now + dt.timedelta(seconds=next_delay(st, market, interval))
                       ).isoformat(timespec="seconds")
        if ticks is None:
            print("poll fail %s: %s（退避 %ds）"
                  % (market, meta.get("err"), meta.get("backoff_s")), flush=True)
            continue
        # 快照时间戳日期守卫（休市工作日静态快照防线——07「日期守卫」）
        all_events += vrules.evaluate_market_guard(
            market, meta.get("tick_dates"), today, st["rules"], cfg, now)
        if meta.get("missing"):   # 结构校验弃行/未返回：一次性留痕+通知，不静默失明
            flag = "%s|source_dropped" % market
            new = [c for c in meta["missing"]
                   if c not in st["rules"]["day_flags"].get(flag, [])]
            if new:
                st["rules"]["day_flags"][flag] = \
                    st["rules"]["day_flags"].get(flag, []) + new
                all_events.append({
                    "ts": now.isoformat(timespec="seconds"), "code": "*",
                    "market": market, "kind": "*", "rule": "source_dropped",
                    "level": "T0", "notify": True, "mech_risk": None,
                    "facts": {"codes": new, "dropped": meta.get("dropped"),
                              "note": "快照缺行或结构校验不过，以下票本轮失明"}})
        if st["rules"]["halted"].get(market):
            continue
        lunch = vrules.LUNCH["hk"]
        if market == "hk" and not lunch[0] <= now.hour * 60 + now.minute < lunch[1]:
            lags = [t["lag_min"] for t in ticks if t["lag_min"] is not None
                    and not st["rules"]["suspended"].get(t["code"])]
            if lags:
                hk_delayed = max(lags) > cfg["hk_delay_min"]
                all_events += vrules.evaluate_hk_delay(max(lags), st["rules"],
                                                       cfg, now)
        events, _ = vrules.evaluate(ticks, uni["rows"], st["rules"], cfg, now)
        all_events += events
        all_ticks += ticks
        if meta.get("indices"):
            all_ticks.append({"market": market, "index": meta["indices"],
                              "local_ts": now.isoformat(timespec="seconds")})
    if all_ticks:
        append_jsonl(os.path.join(p["ticks"], today + ".jsonl"), all_ticks)
    if all_events:
        append_jsonl(os.path.join(p["events"], today + ".jsonl"), all_events)
        dispatch(all_events, uni["rows"], no_notify, hk_delayed)
    save_state(state_dir, st)
    return all_events


# ---------------------------------------------------------------- 收盘复核

PRICE_RULES = {"stop_break", "stop_break_confirmed", "whipsaw", "target_hit",
               "t2_pending_fill"}


def classify_close(ev_stocks, bars_by_code, uni_rows, today):
    """对当日价位类事件做收盘终判（07「收盘复核」口径：确认/whipsaw/撤回/
    挂起）。"""
    rows = {r["code"]: r for r in uni_rows}
    out = []
    for code, evs in ev_stocks.items():
        row = rows.get(code)
        if row is None:
            continue
        bars = bars_by_code.get(code)
        if not bars or str(bars[-1].get("date", ""))[:10] != today:
            out.append({"code": code, "name": row["name"], "verdict": "挂起",
                        "verdicts": ["末根日 K 未出或非当日，次日补判"]})
            continue
        bar = bars[-1]
        kinds = {e["rule"] for e in evs}
        item = {"code": code, "name": row["name"], "close": bar["close"],
                "verdicts": []}
        if row["stop"] is not None and kinds & {"stop_break", "stop_break_confirmed",
                                                "whipsaw"}:
            if bar["close"] < row["stop"]:
                item["verdicts"].append("止损确认（收盘 %.2f < 止损线 %.2f）"
                                        % (bar["close"], row["stop"]))
            elif bar["low"] < row["stop"]:
                item["verdicts"].append("whipsaw 坐实（盘中低 %.2f 破线，收盘收回）"
                                        % bar["low"])
            else:
                item["verdicts"].append("止损事件收盘撤回")
        if row["target1"] is not None and "target_hit" in kinds:
            item["verdicts"].append("目标1 收盘%s（%.2f / %.2f）" % (
                "站上" if bar["close"] >= row["target1"] else "回落",
                bar["close"], row["target1"]))
        if "t2_pending_fill" in kinds and row.get("entry_ref") is not None \
                and bar["low"] <= row["entry_ref"]:
            item["verdicts"].append("T2 触价坐实（推演成交 %.2f，写回属 P3）"
                                    % min(bar["open"], row["entry_ref"]))
        if not item["verdicts"]:
            item["verdicts"].append("盘中事件收盘全部撤回（以全诊为准）")
        out.append(item)
    return out


def coverage_gaps(ticks, market, interval_s):
    """盯盘覆盖缺口：相邻 tick 间隔 >2×interval 且不在午休窗内的区间。"""
    lunch = vrules.LUNCH[market]
    ts = sorted({t["local_ts"] for t in ticks
                 if t.get("market") == market and t.get("code")})
    gaps = []
    for a, b in zip(ts, ts[1:]):
        da, db = dt.datetime.fromisoformat(a), dt.datetime.fromisoformat(b)
        in_lunch = lunch[0] <= da.hour * 60 + da.minute < lunch[1] or \
            lunch[0] <= db.hour * 60 + db.minute <= lunch[1]
        if (db - da).total_seconds() > 2 * interval_s and not in_lunch:
            gaps.append("%s–%s" % (a[11:16], b[11:16]))
    return ts, gaps


def close_pass(state_dir, uni, st, cfg, no_notify, no_bars=False):
    """收盘复核：全局取数锁下重拉事件股 + 全部港股（抽检）日 K → 终判 →
    day-summary 派生重渲（幂等：events/ticks 台账是事实源，日报是派生视图）。
    当日无事件也照常出日报（覆盖区间可审计）。"""
    now = _now()
    today = now.date().isoformat()
    p = monitor_paths(state_dir)
    events = read_jsonl(os.path.join(p["events"], today + ".jsonl"))
    ticks = read_jsonl(os.path.join(p["ticks"], today + ".jsonl"))
    if not markets_done(st, uni, now):
        # 时点门（无条件规则：未收盘拉到的日 K 末根是盘中价，终判与源抽检都会
        # 错判且 close_done 会固化错误结论）——手动 --close 与 --loop 同一把门
        print("close: 未到收盘复核时点（A 15:10 / 港 16:10），拒跑", flush=True)
        return
    if not events and not ticks:
        print("close: 当日无盯盘记录（非交易日/未启动轮询），跳过", flush=True)
        st["close_done"] = True
        save_state(state_dir, st)
        return
    ev_stocks = {}
    for e in events:
        if e.get("rule") in PRICE_RULES and e.get("code") != "*":
            ev_stocks.setdefault(e["code"], []).append(e)
    hk_codes = [r["code"] for r in uni["rows"] if r["market"] == "hk"
                and any(t.get("code") == r["code"] for t in ticks)]
    need = list(dict.fromkeys(list(ev_stocks) + hk_codes))
    bars_by_code = {}
    if need and not no_bars:
        lock = FetchLock(state_dir)
        if not lock.acquire(timeout=120):
            notify("收盘复核被取数锁阻塞（fetch_state.lock 竞争），本次挂起，"
                   "请重跑 --close", sound=True, no_notify=no_notify)
            print("close: 锁竞争挂起", flush=True)
            return
        try:
            fs = vfetch.load_fetch_state()
            rows = {r["code"]: r for r in uni["rows"]}
            for code in need:
                row = rows.get(code)
                if row is None:
                    continue
                bars, bstate, _src, _tried = vfetch.fetch_daily_bars(
                    row["market"], code, fs, int(now.timestamp()))
                if bars:
                    bars_by_code[code] = bars
                else:
                    print("bars %s %s: %s" % (bstate, code, _tried), flush=True)
            vfetch.save_fetch_state(fs)
        finally:
            lock.release()
    verdicts = classify_close(ev_stocks, bars_by_code, uni["rows"], today)

    # 港股源每日抽检（07「源校验」：全部在盯港股，末轮快照 vs 当日收盘价；
    # 末轮距收盘竞价有缓冲，阈值 0.5%——P1 只作标注，不改变盘中取数源）
    hk_last = {t["code"]: t for t in ticks
               if t.get("market") == "hk" and t.get("code")}
    hk_note = ""
    checked = [c for c in hk_codes if c in bars_by_code and c in hk_last
               and str(bars_by_code[c][-1].get("date", ""))[:10] == today
               and bars_by_code[c][-1]["close"]]
    bad = [c for c in checked
           if abs(hk_last[c]["price"] / bars_by_code[c][-1]["close"] - 1) > 0.005]
    if checked:
        st["hk_source"] = {**(st.get("hk_source") or {}),
                           "daily_check": {"date": today, "checked": checked,
                                           "bad": bad}}
        hk_note = ("港股末轮快照与收盘价偏差 >0.5%%（%s），疑似源漂移/延迟，已标注"
                   % ",".join(bad) if bad else
                   "港股末轮快照与收盘价一致（%d 只抽检通过）" % len(checked))

    lines = ["# 盯盘日报 %s" % today, ""]
    for market, title in (("cn", "A 股收盘复核"), ("hk", "港股收盘复核")):
        codes = {r["code"] for r in uni["rows"] if r["market"] == market}
        items = [v for v in verdicts if v["code"] in codes]
        if not items:
            continue
        lines.append("## %s" % title)
        for it in items:
            lines.append("- **%s %s**：%s" % (it["code"], it["name"],
                                             "；".join(it["verdicts"])))
        lines.append("")
    if not verdicts:
        lines += ["## 收盘复核", "- 当日无价位类事件", ""]
    if hk_note:
        lines += ["## 源健康", "- " + hk_note, ""]
    lines.append("## 盯盘覆盖")
    for market in ("cn", "hk"):
        ts, gaps = coverage_gaps(ticks, market, cfg.get("interval_s", 180))
        if ts:
            lines.append("- %s：%s–%s（%d 轮）%s%s" % (
                market, ts[0][11:19], ts[-1][11:19], len(ts),
                "；缺口 " + "、".join(gaps) + "（缺口内事件以收盘复核为准）"
                if gaps else "",
                "；当日判休市停轮" if st["rules"]["halted"].get(market) else ""))
    lines.append("")
    unresolved = [e for e in events if e.get("code") != "*"
                  and (e.get("mech_risk") or {}).get("downgrade")
                  and e["rule"] in PRICE_RULES]
    lines.append("## 次日盯盘重点")
    for code in dict.fromkeys(e["code"] for e in unresolved):
        lines.append("- %s：止损线击穿确认（机械降档事实待全诊消费）" % code)
    if not unresolved:
        lines.append("- 无未处理机械降档事件")
    lines += ["", "*%s*" % DISCLAIMER, ""]
    os.makedirs(p["summary"], exist_ok=True)
    with open(os.path.join(p["summary"], today + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("close: 终判 %d 只，日报已渲染 monitor/day-summary/%s.md"
          % (len(verdicts), today), flush=True)
    st["close_done"] = True
    save_state(state_dir, st)


# ---------------------------------------------------------------- 港股源验证

def _parse_sina_hk_body(text):
    """新浪 rt_hk 行情体解析：0=名称 1=开 2=昨收 3=现价 4=高 5=低（结构
    自洽不过即弃）。"""
    if '"' not in text:
        return None
    body = text[text.index('"') + 1:text.rindex('"')]
    f = body.split(",")
    try:
        o, prev, px, hi, lo = (float(f[1]), float(f[2]), float(f[3]), float(f[4]),
                               float(f[5]))
    except (IndexError, ValueError):
        return None
    if not (lo <= px <= hi and prev > 0):
        return None
    return {"open": o, "prev_close": prev, "price": px, "high": hi, "low": lo}


def fetch_sina_rt_hk(code):
    """新浪 rt_hk 交叉源（带 Referer——07「回退链」）。"""
    url = "https://hq.sinajs.cn/list=rt_hk" + code.zfill(5)
    text = vfetch._http_text(url, headers={"Referer": "https://finance.sina.com.cn"})
    return _parse_sina_hk_body(text)


def verify_hk(state_dir, uni, st, no_notify):
    """港股源验证（收盘后跑）：r_hk 快照 × 新浪 rt_hk × 日 K 收盘三方对照，
    结论持久化 state.hk_source（07「源验证」：多时点一致才转正源）。"""
    now = _now()
    hk_rows = [r for r in uni["rows"] if r["market"] == "hk"]
    if not hk_rows:
        print("verify-hk: 宇宙无港股，跳过")
        return
    if now.weekday() < 5 and now.hour * 60 + now.minute < REVIEW_MIN["hk"]:
        print("verify-hk: 港股未收盘（16:10 后跑：末根=收盘价，残余差即纯延迟）",
              flush=True)
        return
    lock = FetchLock(state_dir)
    if not lock.acquire(timeout=60):
        print("verify-hk: 取数锁竞争，稍后重跑", flush=True)
        return
    samples, fs = [], vfetch.load_fetch_state()
    try:
        for r in hk_rows:
            try:
                raw = vfetch._http_text("https://qt.gtimg.cn/q=r_hk"
                                        + r["code"].zfill(5))
                qt = parse_qt_full_line(raw)
                sina = fetch_sina_rt_hk(r["code"])
                bars, _bst, _src, _tried = vfetch.fetch_daily_bars(
                    "hk", r["code"], fs, int(now.timestamp()))
            except Exception as e:
                samples.append({"code": r["code"], "err": str(e)[:120]})
                continue
            close = bars[-1]["close"] if bars else None
            samples.append({
                "code": r["code"], "qt": qt and qt["price"],
                "sina": sina and sina["price"], "close": close,
                "dev_sina_pct": round(abs(qt["price"] / sina["price"] - 1) * 100, 3)
                if qt and sina else None,
                "dev_close_pct": round(abs(qt["price"] / close - 1) * 100, 3)
                if qt and close else None})
        vfetch.save_fetch_state(fs)
    finally:
        lock.release()
    usable = [s for s in samples if s.get("dev_close_pct") is not None]
    ok = bool(usable) and all(s["dev_close_pct"] <= 0.3 for s in usable)
    st["hk_source"] = {"mode": "r_hk" if ok else "bars_fallback",
                       "verified_at": now.isoformat(timespec="seconds"),
                       "samples": samples}
    save_state(state_dir, st)
    print("verify-hk: %s（%d/%d 只可对照，明细入 state.hk_source）"
          % (st["hk_source"]["mode"], len(usable), len(samples)), flush=True)


# ---------------------------------------------------------------- 循环



def markets_done(st, uni, now):
    """当日盯盘是否收口（全部市场收盘之后 / 判休市）。"""
    minute = now.hour * 60 + now.minute
    return all(st["rules"]["halted"].get(m) or minute >= REVIEW_MIN[m]
               for m in {r["market"] for r in uni["rows"]})


def run_loop(state_dir, cfg, no_notify, no_bars=False):
    uni = load_universe(state_dir)
    st = ensure_state(state_dir, _now().date().isoformat())
    for w in uni["warnings"]:
        print("warn:", w, flush=True)
    while True:
        now = _now()
        if markets_done(st, uni, now):
            if not st["close_done"]:
                close_pass(state_dir, uni, st, cfg, no_notify, no_bars)
            print("loop: 当日盯盘收口，退出（明日由 launchd 拉起）", flush=True)
            return
        run_round(state_dir, uni, st, cfg, no_notify, now=now)
        # 退避按市场独立（next_due）：sleep 到最早到期的市场，一个市场退避不拖慢另一个
        dues = [dt.datetime.fromisoformat(v) for v in st.get("next_due", {}).values()]
        wait = min([(d - _now()).total_seconds() for d in dues]
                   + [cfg.get("interval_s", 180)])
        time.sleep(max(5, wait))


# ---------------------------------------------------------------- selftest

def _mk_line(fields):
    return "~".join(str(x) for x in fields)


def _qt_fields(name, code, price, prev, open_, vol, ts, chg_amt, chg_pct, high,
               low, amount, turnover, cls="51"):
    """构造 39 字段 qt 全量快照行（0..6 基础 + 7..29 占位 + 30..38 监控位）。"""
    return ([cls, name, code, price, prev, open_, vol] + [""] * 23
            + [ts, chg_amt, chg_pct, high, low, "", "", amount, turnover])


def selftest():
    import tempfile
    ok = [0]

    def check(name, cond):
        ok[0] += 1
        if not cond:
            raise AssertionError("FAIL: %s" % name)

    # 1) qt 全量快照解析 + 结构校验（A 股合成行：现价 26.10 / 昨收 27.15）
    raw = 'v_sh600001="%s";' % _mk_line(_qt_fields(
        "合成甲", "600001", "26.10", "27.15", "26.50", "1234567",
        "20261103100003", "-1.05", "-3.87", "27.30", "26.05", "329629", "0.51"))
    raw += 'v_sh600003="%s";' % _mk_line(_qt_fields(
        "合成丙", "600003", "1432.99", "1444.00", "1440.00", "73033",
        "20261103100005", "-11.01", "-0.76", "1445.00", "1428.00", "1046200",
        "0.58"))
    parsed, dropped = parse_qt_response(raw, "cn")
    check("A 股快照解析零弃", dropped == 0 and len(parsed) == 2)
    t = parsed["v_sh600001"]
    check("字段位序", t["price"] == 26.10 and t["prev_close"] == 27.15
          and t["ts_utc8"].startswith("2026-11-03T10:00:03")
          and t["high"] == 27.30
          and t["low"] == 26.05 and t["change_amt"] == -1.05)

    # 2) r_hk 全量快照解析（港股；结构校验跳过量能）
    parsed, dropped = parse_qt_response(
        'v_r_hk00001="%s";' % _mk_line(_qt_fields(
            "合成港甲", "00001", "8.49", "8.42", "8.45", "3000000",
            "2026/11/03 10:00:05", "0.07", "0.83", "8.55", "8.40", "25470", "0.31",
            cls="100")), "hk")
    check("港股快照解析", dropped == 0 and parsed["v_r_hk00001"]["price"] == 8.49
          and parsed["v_r_hk00001"]["ts_utc8"].startswith("2026-11-03T10:00:05"))

    # 3) 结构自洽拦截位序漂移（涨跌额与价差矛盾 → 整行弃）
    parsed, dropped = parse_qt_response(
        'v_sh600002="%s";' % _mk_line(_qt_fields(
            "合成丁", "600002", "8.93", "8.90", "8.91", "123456",
            "20261103100003", "0.50", "-5.60", "9.10", "8.80", "12345", "2.31")),
        "cn")
    check("结构矛盾行被弃", dropped == 1 and not parsed)

    # 4) 新浪 rt_hk 解析
    body = ('var hq_str_rt_hk00001="合成港甲,8.45,8.42,8.49,8.55,8.40,8.48,8.50,'
            '3000000,25470000,,,2026-11-03,10:00:05";')
    s = _parse_sina_hk_body(body)
    check("新浪 rt_hk 解析", s and s["price"] == 8.49 and s["prev_close"] == 8.42
          and s["low"] <= s["price"] <= s["high"])
    check("新浪 rt_hk 坏体被弃", _parse_sina_hk_body('x="合成港甲,9.9,8.42,9.9,8.0,9.0";')
          is None)

    # 5) 宇宙派生（合成状态目录：代码与数值均为虚构——红线：fixture 不得含真实持仓）
    with tempfile.TemporaryDirectory() as td:
        scan = os.path.join(td, "reports", "_scans", "2026-11-01-x", "portfolio")
        os.makedirs(scan)
        with open(os.path.join(td, "portfolio.json"), "w", encoding="utf-8") as f:
            json.dump({"holdings": [
                {"code": "600001", "market": "cn", "quantity": 100,
                 "cost_price": 10.00},
                {"code": "00001", "market": "hk", "quantity": 100,
                 "cost_price": 10.00}]}, f)
        with open(os.path.join(scan, "allocation.json"), "w", encoding="utf-8") as f:
            json.dump({"rows": [{"code": "000002", "name": "合成乙",
                                 "stop": 9.50, "entry_ref": 9.70,
                                 "target1": 11.00}]}, f)
        with open(os.path.join(td, "signals.json"), "w", encoding="utf-8") as f:
            json.dump([
                {"code": "600001", "market": "cn", "stock_name": "合成甲",
                 "date": "2026-11-02",
                 "key_levels": {"stop": 9.80, "target1": 11.50}},
                {"code": "600003", "market": "cn", "stock_name": "合成丙",
                 "date": "2026-11-02",
                 "key_levels": {"stop": 19.00, "target1": 22.00}},
                # position 轨波段带信号：不得覆盖短线三价锚（profile 过滤钉）
                {"code": "600001", "market": "cn", "profile": "position",
                 "date": "2026-11-03",
                 "key_levels": {"band_lo": 8.00, "band_hi": 12.00,
                                "trail_ref": 10.50}}], f)
        with open(os.path.join(td, "names.json"), "w", encoding="utf-8") as f:
            json.dump({"cn:600001": "合成甲", "cn:000002": "合成乙"}, f)
        uni = derive_universe(td)
        check("宇宙构成 real2/sim1/watch1",
              uni["counts"] == {"real": 2, "sim": 1, "watch": 1}
              and uni["rows"][0]["code"] == "600001")
        by = {r["code"]: r for r in uni["rows"]}
        check("实盘取 signals 价位", by["600001"]["stop"] == 9.80
              and by["600001"]["kind"] == "real")
        check("position 轨波段带不覆盖短线锚（profile 过滤）",
              by["600001"]["target1"] == 11.50
              and "band_lo" not in by["600001"].get("key_levels", {}))
        check("模拟回退 allocation", by["000002"]["stop"] == 9.50
              and by["000002"]["levels_source"] == "allocation"
              and by["000002"]["entry_ref"] == 9.70)
        check("观察票带锚", by["600003"]["kind"] == "watch"
              and by["600003"]["stop"] == 19.00)
        check("缺锚降级告警", any("无价位锚" in w for w in uni["warnings"])
              and by["00001"]["levels_source"] == "none")
        check("脱敏：宇宙零成本/数量字段",
              not any(k in json.dumps(uni) for k in ("cost_price", '"cost"',
                                                     "quantity")))
    # 负断言：本 fixture 的 (code, cost) 不得与真实 portfolio.json 重合（文件缺失跳过）
    real = varchive.load_portfolio(os.path.expanduser("~/.vibe-stock"))
    fixture_pairs = {("600001.cn", 10.00), ("00001.hk", 10.00)}
    check("fixture 与真实持仓零重合",
          not any((k, v.get("cost")) in fixture_pairs for k, v in real.items()))

    # 5b) 跨日状态归零（close_done/src_fail/next_due 随日期重置；hk_source 保留）
    with tempfile.TemporaryDirectory() as td:
        st = ensure_state(td, "2026-11-02")
        st.update({"close_done": True, "src_fail": {"hk": 2},
                   "next_due": {"hk": "2026-11-02T15:00:00+08:00"},
                   "hk_source": {"mode": "r_hk"}})
        save_state(td, st)
        st2 = ensure_state(td, "2026-11-03")
        check("跨日 close_done/src_fail/next_due 归零",
              st2["close_done"] is False and st2["src_fail"] == {}
              and st2["next_due"] == {} and st2["hk_source"] == {"mode": "r_hk"})
        check("同日状态沿用", ensure_state(td, "2026-11-02")["close_done"] is True)

    # 5c) 科创 688 量纲（股）不被结构校验误弃；价格 0 行被拒
    parsed, dropped = parse_qt_response('v_sh688001="%s";' % _mk_line(_qt_fields(
        "合成科创", "688001", "50.00", "49.00", "49.50", "2000000",
        "20261103100003", "1.00", "2.04", "51.00", "49.00", "10000", "1.20")),
        "cn")
    check("科创 688 量纲为股不误弃", dropped == 0 and "v_sh688001" in parsed)
    parsed, dropped = parse_qt_response('v_sh600001="%s";' % _mk_line(_qt_fields(
        "合成甲", "600001", "0.00", "10.00", "0.00", "0",
        "20261103100003", "", "", "0.00", "0.00", "0", "0")), "cn")
    check("现价 0 行被拒", dropped == 1 and not parsed)
    parsed, dropped = parse_qt_response('v_sh600001="%s";' % _mk_line(_qt_fields(
        "合成甲", "600001", "10.10", "10.00", "10.00", "1000",
        "00000000000000", "0.10", "1.00", "10.20", "9.90", "101", "0.5")), "cn")
    check("非法时间戳只置空不崩", "v_sh600001" in parsed
          and parsed["v_sh600001"]["ts_utc8"] is None)

    # 5d) 覆盖缺口（午休不算缺口）
    tk = [{"market": "cn", "code": "600001", "local_ts": x} for x in (
        "2026-11-03T10:00:00+08:00", "2026-11-03T10:03:00+08:00",
        "2026-11-03T10:30:00+08:00", "2026-11-03T11:29:00+08:00",
        "2026-11-03T13:00:00+08:00")]
    _ts, gaps = coverage_gaps(tk, "cn", 180)
    check("覆盖缺口识别且豁免午休", gaps == ["10:03–10:30", "10:30–11:29"])

    # 6) 收盘终判
    uni_rows = [{"code": "600001", "market": "cn", "name": "合成甲", "kind": "real",
                 "stop": 9.80, "target1": 11.50, "entry_ref": None},
                {"code": "000002", "market": "cn", "name": "合成乙", "kind": "sim",
                 "stop": 9.50, "target1": 11.00, "entry_ref": 9.70}]
    today = _now().date().isoformat()
    bars = {"600001": [{"date": today, "close": 9.70, "low": 9.60, "high": 10.1,
                        "open": 10.0}],
            "000002": [{"date": today, "close": 9.80, "low": 9.65, "high": 9.9,
                        "open": 9.85}]}
    out = classify_close({"600001": [{"rule": "stop_break"}],
                          "000002": [{"rule": "t2_pending_fill"}]},
                         bars, uni_rows, today)
    v1 = [x for x in out if x["code"] == "600001"][0]
    v2 = [x for x in out if x["code"] == "000002"][0]
    check("止损收盘确认", any("止损确认" in s for s in v1["verdicts"]))
    check("T2 触价坐实", any("T2 触价坐实" in s for s in v2["verdicts"]))
    out = classify_close({"600001": [{"rule": "stop_break"}]},
                         {"600001": [{"date": "2026-11-01", "close": 9.7}]},
                         uni_rows, today)
    check("末根非当日挂起", out[0]["verdicts"] == ["末根日 K 未出或非当日，次日补判"])

    # 7) launchd 模板回归钉（I-009：仅 09:15 单槽时重启/开机后当日盲窗——钉住
    #    补拉槽语义；模板与 selftest 同目录，plistlib 解析兼钉标准 XML 合法）
    import plistlib
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "com.threefish.vibestock.monitor.plist"), "rb") as f:
        job = plistlib.load(f)
    check("模板拉起 --loop", "--loop" in job["ProgramArguments"])
    check("KeepAlive 崩溃自愈 + 防投机拉起",
          job["KeepAlive"] == {"Crashed": True, "AfterInitialDemand": True})
    check("RunAtLoad=false（I-008 初衷不回退）", job["RunAtLoad"] is False)
    day_slots = {}
    for ent in job["StartCalendarInterval"]:
        day_slots.setdefault(ent["Weekday"], set()).add(
            ent["Hour"] * 60 + ent["Minute"])
    check("槽位仅周一至周五且五日一致",
          sorted(day_slots) == [1, 2, 3, 4, 5]
          and len({frozenset(v) for v in day_slots.values()}) == 1)
    mins = sorted(next(iter(day_slots.values())))
    check("09:15 主槽在列", 9 * 60 + 15 in mins)
    check("两市共同休市零槽（12:00–13:00）",
          not any(12 * 60 <= m < 13 * 60 for m in mins))
    trade = ((570, 720), (780, 960))   # A+港并集交易分钟：09:30–12:00 / 13:00–16:00

    def blind(a, b):                   # 相邻槽 [a,b) 内未覆盖的交易分钟数
        return sum(max(0, min(b, hi) - max(a, lo)) for lo, hi in trade)

    cyc = mins + [mins[0] + 1440]      # 跨日闭环：单槽形态即整日盲窗，必红
    check("相邻补拉槽交易盲窗 ≤30min",
          max(blind(a, b) for a, b in zip(cyc, cyc[1:])) <= 30)
    check("盘后兜底槽在 16:10–16:40（收盘复核补跑）",
          any(16 * 60 + 10 <= m <= 16 * 60 + 40 for m in mins))

    print("watch selftest: %d checks OK" % ok[0])
    return True


def main():
    ap = argparse.ArgumentParser(description="盯盘守卫（参考实现，口径见 references/07）")
    ap.add_argument("--state-dir", default=os.path.expanduser("~/.vibe-stock"))
    ap.add_argument("--print-universe", action="store_true")
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--loop", action="store_true")
    ap.add_argument("--close", action="store_true")
    ap.add_argument("--verify-hk", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--interval", type=int, default=180, help="轮询间隔秒（默认 180）")
    ap.add_argument("--no-notify", action="store_true", help="不发系统通知（调试）")
    ap.add_argument("--no-bars", action="store_true",
                    help="close 不拉日 K（离线调试：全部终判挂起）")
    ap.add_argument("--config", default="{}", help="规则参数 JSON 覆盖")
    a = ap.parse_args()

    if a.selftest:
        selftest()
        return
    cfg = json.loads(a.config) if a.config and a.config != "{}" else {}
    cfg.setdefault("interval_s", a.interval)

    if a.print_universe:
        uni = load_universe(a.state_dir, regenerate=True)
        print(json.dumps({k: uni[k] for k in ("date", "counts", "warnings")},
                         ensure_ascii=False, indent=1))
        for r in uni["rows"]:
            print("%-8s %-3s %-5s stop=%-9s target1=%-9s entry_ref=%-9s (%s)"
                  % (r["code"], r["market"], r["kind"], r["stop"], r["target1"],
                     r["entry_ref"], r["levels_source"]))
        return

    os.makedirs(monitor_paths(a.state_dir)["logs"], exist_ok=True)   # launchd 日志父目录
    lock = SingleInstance(a.state_dir)
    if not lock.acquire():
        print("watch: 已有实例在运行（monitor/watch.lock），退出", flush=True)
        sys.exit(3)
    try:
        uni = load_universe(a.state_dir)
        st = ensure_state(a.state_dir, _now().date().isoformat())
        if a.verify_hk:
            verify_hk(a.state_dir, uni, st, a.no_notify)
        elif a.close:
            close_pass(a.state_dir, uni, st, cfg, a.no_notify, no_bars=a.no_bars)
        elif a.once:
            run_round(a.state_dir, uni, st, cfg, a.no_notify)
        elif a.loop:
            try:
                run_loop(a.state_dir, cfg, a.no_notify, no_bars=a.no_bars)
            except Exception:
                import traceback
                traceback.print_exc()
                notify("盯盘进程异常退出，launchd 将自动重拉；手动恢复：watch.py --loop",
                       sound=True, no_notify=a.no_notify)
                lock.release()
                # launchd KeepAlive.Crashed 只认信号级崩溃：Python 异常转 SIGABRT 才能自愈
                os.abort()
        else:
            ap.print_help()
    finally:
        lock.release()


if __name__ == "__main__":
    main()
