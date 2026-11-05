#!/usr/bin/env python3
"""盯盘守卫（P1）——在册股票盘中监控：宇宙派生 / 价格面轮询 / 触发告警 /
收盘复核。口径以 references/07-monitor.md 为准（本文件是参考实现）。

红线落地：只提示不执行（无任何交易接口）；本地通知报事实 + 事件级
「××复核」短语（0.0.25 修订：措辞限定「复核」、禁减仓/离场/加仓等指令词；
零成本绝对值；尾注「待收盘复核·非投资建议」）；永不写 signals.json
（当日信号登记唯一归每晚全诊）；盘中结论以收盘复核为准。

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

# 通知文案（事实级；指令性建议一律不进通知——07「通知口径」0.0.25 修订：
# 事件级「××复核」短语由 ev.review 承载、fmt_facts 尾拼，运维类零短语）
_RULE_TEXT = {
    "stop_break": "跌破止损线", "stop_break_confirmed": "持续跌破止损线（2 轮确认）",
    "whipsaw": "击穿后收回（待收盘终判）", "target_hit": "触及目标价1",
    "abnormal_move": "盘中异动", "gap_open": "跳空开盘",
    "limit_hit": "触板", "t2_pending_fill": "T2 限价触价（推演成交，未写回）",
    "frozen": "疑似停牌（价量冻结）", "resumed": "复牌", "gap_move": "复牌异动",
    "market_halted": "休市停轮", "market_resumed": "解除停轮",
    "hk_delayed": "港股行情延迟", "storm_digest": "事件聚合",
    "source_dropped": "行情缺行",
    "ma20_break": "跌破 MA20（0.98×）", "trailing_armed": "浮盈武装跟踪止损",
    "trailing_exit": "跟踪止损破 MA20", "band_lo_touch": "触及波段带下沿",
    "band_hi_touch": "触及波段带上沿", "band_trail_break": "收盘破波段带 trail_ref",
    "data_stale": "technical 预热未得当日数据",
}


def _now():
    return dt.datetime.now(TZ)


# ---------------------------------------------------------------- 基础设施

def monitor_paths(state_dir):
    m = os.path.join(state_dir, "monitor")
    return {"root": m, "universe": os.path.join(m, "universe.json"),
            "state": os.path.join(m, "state.json"),
            "ticks": os.path.join(m, "ticks"), "events": os.path.join(m, "events"),
            "summary": os.path.join(m, "day-summary"), "logs": os.path.join(m, "logs"),
            "tech_cache": os.path.join(m, "technical-cache.json")}


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
    tech = st.get("tech") if same_day else None
    return {"date": today, "rules": rs,
            "src_fail": st.get("src_fail", {}) if same_day else {},
            "hk_source": st.get("hk_source"),
            "close_done": st.get("close_done", False) if same_day else False,
            "next_due": st.get("next_due", {}) if same_day else {},
            # trailing 跟踪态跨日保留（07 0.0.25：armed/high 是持仓持续态，
            # 日归零会系统性漏报隔日 trailing_exit）；tech 预热计数同日继承
            "trailing": st.get("trailing") or {},
            "tech": tech if tech and tech.get("date") == today
            else {"date": today, "tries": 0, "stale_notified": False}}


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


def latest_signals(state_dir, profile="default"):
    """signals.json 组内最新信号（价位锚 SSOT）：{code: {...}}（append 序，
    后写覆盖前写 = 组内最新）。按轨取（profile="default" 三价锚 /
    "position" 波段带三键——0.0.25 起波段带锚并行投影、与 default 三价
    不互覆，07「价位锚分轨」句）。投影带 action/family（收盘操作复核的
    五档机械映射代理——只投影不重裁决）。"""
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
        if s.get("profile", "default") != profile:
            continue
        out[s["code"]] = {"market": s.get("market"), "name": s.get("stock_name"),
                          "key_levels": s.get("key_levels") or {},
                          "date": s.get("date"),
                          "action": s.get("action"), "family": s.get("family")}
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
    psigs = latest_signals(state_dir, profile="position")   # 波段带三键并行投影
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
        pkl = (psigs.get(code) or {}).get("key_levels") or {}
        rows.append({"code": code, "market": market, "kind": kind, "name": name,
                     "stop": levels["stop"], "target1": levels["target1"],
                     "entry_ref": levels["entry_ref"], "levels_source": source,
                     # 波段带三键独立行键（不塞 key_levels——07「价位锚分轨」：
                     # position 锚与 default 三价并行不互覆；无 position 信号
                     # 则整组缺省不判，禁现算充锚）
                     "band_lo": pkl.get("band_lo"), "band_hi": pkl.get("band_hi"),
                     "trail_ref": pkl.get("trail_ref"),
                     "band_levels_source": "signals" if pkl else "none",
                     # 收盘操作复核的五档投影代理（只投影不重裁决，以报告原文为准）
                     "signal_action": (sigs.get(code) or {}).get("action"),
                     "signal_family": (sigs.get(code) or {}).get("family"),
                     "pos_signal_action": (psigs.get(code) or {}).get("action"),
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


# ------------------------------------------------- technical 预热（0.0.25 P2 前置门数据通道）

def load_tech_cache(state_dir):
    p = monitor_paths(state_dir)
    if not os.path.exists(p["tech_cache"]):
        return {}
    try:
        with open(p["tech_cache"], encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _data_stale_event(now, lacking, total):
    """一次性 data_stale 运维事件（watch 级手工构造，仿 source_dropped——
    不带复核短语）。MA20/跟踪止损判据对缺数票当日禁用（_ma20 缺省自然跳过）。"""
    return {"ts": now.isoformat(timespec="seconds"), "code": "*", "market": "*",
            "kind": "*", "rule": "data_stale", "level": "T0", "notify": True,
            "mech_risk": None,
            "facts": {"lacking": len(lacking), "total": total,
                      "codes": lacking[:8],
                      "note": "technical 预热重试耗尽（末根非当日/源熔断），"
                              "MA20/跟踪止损判据今日禁用，收盘复核以完整根重算"}}


def warmup_technical(state_dir, uni, st, cfg, now=None):
    """当日 technical 预热：FetchLock + fetch_state 账本下拉宇宙日 K →
    ma20 派生 → technical-cache.json（只落派生量，脱敏红线）。不可得
    （末根非今日/源熔断）重试 ≤tech_warmup_max_tries，耗尽出一次性
    data_stale 事件。返回 (cache, events)——events 由调用方并入当轮台账。
    盘中根 ma20 为 estimated 口径，收盘终判以完整根重算。"""
    now = now or _now()
    today = now.date().isoformat()
    p = monitor_paths(state_dir)
    cache = load_tech_cache(state_dir)
    if cache.get("date") != today:
        cache = {"date": today, "generated_at": now.isoformat(timespec="seconds"),
                 "codes": {}}
    tech_st = st.setdefault("tech", {})
    if tech_st.get("date") != today:
        tech_st.update({"date": today, "tries": 0, "stale_notified": False})
    rows = [r for r in uni["rows"] if r.get("kind") in ("real", "sim")]
    lacking = [r for r in rows
               if (cache["codes"].get(r["code"]) or {}).get("data_date") != today]
    if not lacking:
        return cache, []
    if tech_st["tries"] >= cfg.get("tech_warmup_max_tries", 3):
        if not tech_st.get("stale_notified"):
            tech_st["stale_notified"] = True
            return cache, [_data_stale_event(now, [r["code"] for r in lacking],
                                             len(rows))]
        return cache, []
    tech_st["tries"] += 1
    lock = FetchLock(state_dir)
    if not lock.acquire(timeout=30):   # 与 --close/outlook 批量竞争：让路不硬等
        tech_st["tries"] -= 1   # 让路不计次（P2-4：锁竞争消耗重试会 ~10min 烧穿全日判据）
        return cache, []
    try:
        fs = vfetch.load_fetch_state()
        for r in lacking:
            bars, _state, _src, _tried = vfetch.fetch_daily_bars(
                r["market"], r["code"], fs, int(now.timestamp()))
            last_date = str(bars[-1].get("date", ""))[:10] if bars else None
            ma20 = vfetch._ma([b["close"] for b in bars], 20) if bars else None
            cache["codes"][r["code"]] = {
                "ma20": ma20, "data_date": last_date,
                "state": "ok" if last_date == today and ma20 is not None else "stale"}
        vfetch.save_fetch_state(fs)
    finally:
        lock.release()
    cache["generated_at"] = now.isoformat(timespec="seconds")
    os.makedirs(p["root"], exist_ok=True)
    varchive.write_json_atomic(p["tech_cache"], cache)
    still = [r for r in rows
             if (cache["codes"].get(r["code"]) or {}).get("data_date") != today]
    if still and tech_st["tries"] >= cfg.get("tech_warmup_max_tries", 3) \
            and not tech_st.get("stale_notified"):
        tech_st["stale_notified"] = True
        return cache, [_data_stale_event(now, [r["code"] for r in still],
                                         len(rows))]
    return cache, []


def annotate_runtime(rows, state_dir, cache):
    """运行期现算现用注入（脱敏红线：成本/数量绝不落盘——注入发生在宇宙
    落盘之后的内存态，磁盘产物零污染）。real 成本=portfolio cost_price
    （archive.load_portfolio）；sim 每股成本=allocation 配置日价
    （cost/(lots×100)≡price 实证，P3 sim-portfolio.json 落地后切换口径）；
    ma20←当日预热缓存（缺省即 P2 机械判据自然禁用）。数量仅供权重分桶
    现算（收盘操作复核），同样不落盘。"""
    problems = []
    real = varchive.load_portfolio(state_dir, problems)
    alloc = latest_allocation(state_dir)
    sim_rows = {a["code"]: a for a in (alloc["rows"] if alloc else [])}
    today = (cache or {}).get("date")
    for r in rows:
        key = "%s.%s" % (r["code"], r["market"])
        if r.get("kind") == "real":
            ent = real.get(key) or {}
            r["_cost"] = ent.get("cost")
            r["_qty"] = ent.get("qty")
        elif r.get("kind") == "sim":
            a = sim_rows.get(r["code"]) or {}
            r["_cost"] = a.get("price") if a.get("price") else (
                a["cost"] / (a["lots"] * 100)
                if a.get("cost") and a.get("lots") else None)
            r["_qty"] = a["lots"] * 100 if a.get("lots") else None
        c = (cache.get("codes") or {}).get(r["code"]) or {}
        r["_ma20"] = c.get("ma20") if c.get("data_date") == today else None


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

def fmt_facts(rule, facts, name, review=None):
    if rule in ("stop_break", "stop_break_confirmed"):
        s = "%s 现价 %.2f 已低于止损线 %.2f（-%.2f%%）" % (
            name, facts["price"], facts["stop"], facts["depth_pct"])
    elif rule == "whipsaw":
        s = "%s 现价 %.2f 回到止损线 %.2f 上方" % (name, facts["price"], facts["stop"])
    elif rule == "target_hit":
        # 坑位（I-027）：标签序号与数值连读会被看成「触及目标价1 19.43」——
        # 「目标价1=%.2f」用等号钉住归属
        s = "%s 现价 %.2f 触及目标价1=%.2f" % (name, facts["price"], facts["target1"])
    elif rule == "abnormal_move":
        s = "%s 现价 %.2f 涨跌幅 %.1f%%" % (name, facts["price"], facts["change_pct"])
    elif rule == "gap_open":
        s = "%s 跳空开盘 %.2f（昨收 %.2f，%.1f%%）" % (
            name, facts["open"], facts["prev_close"], facts["gap_pct"])
    elif rule == "limit_hit":
        s = "%s %s（涨跌幅 %.1f%%，限幅 %.0f%%）" % (
            name, "近涨停" if facts["direction"] == "up" else "近跌停",
            facts["change_pct"], facts["limit_pct"])
    elif rule == "t2_pending_fill":
        s = "%s 盘中低点 %.2f 触及 T2 限价 %.2f（推演成交 %.2f，未写回）" % (
            name, facts["low"], facts["entry_ref"], facts["fill_price_assumed"])
    elif rule == "frozen":
        s = "%s 价量连续 %d 轮不变，疑似停牌" % (name, facts["rounds"])
    elif rule in ("resumed", "gap_move"):
        s = "%s 复牌现价 %.2f（冻结价 %.2f）" % (
            name, facts["price"], facts.get("frozen_price", facts["price"]))
    elif rule == "storm_digest":
        s = "风暴闸压制 %d 条事件：%s（明细见台账）" % (
            facts["suppressed_count"],
            "；".join("%s %s" % (_RULE_TEXT.get(k, k), ",".join(v))
                      for k, v in sorted(facts["kinds"].items())))
    elif rule == "market_halted":
        s = "%s 全组快照日期 %s 非今日，判休市停轮" % (name, facts["snapshot_date"])
    elif rule == "market_resumed":
        s = "%s 快照恢复今日时间戳，解除停轮" % name
    elif rule == "hk_delayed":
        s = "港股行情延迟 %.0f 分钟（阈值 %d），降级为延迟盯盘" % (
            facts["max_lag_min"], facts["threshold_min"])
    elif rule == "source_dropped":
        s = "%s 行情缺行/校验未过，本轮失明：%s" % (name, ",".join(facts["codes"]))
    elif rule == "ma20_break":
        s = "%s 现价 %.2f 跌破 MA20=%.2f（%.2f%%，盘中根口径）" % (
            name, facts["price"], facts["ma20"], facts["dist_pct"])
    elif rule == "trailing_armed":
        s = "%s 盘中高点 %.2f 触发跟踪止损武装（+15%% 口径，破 MA20 终判）" % (
            name, facts["high_since_entry"])
    elif rule == "trailing_exit":
        s = "%s 现价 %.2f 跌破 MA20=%.2f（跟踪止损已武装）" % (
            name, facts["price"], facts["ma20"])
    elif rule == "band_lo_touch":
        s = "%s 现价 %.2f 触及波段带下沿=%.2f（%.2f%%）" % (
            name, facts["price"], facts["band_lo"], facts["dist_pct"])
    elif rule == "band_hi_touch":
        s = "%s 现价 %.2f 触及波段带上沿=%.2f（%.2f%%）" % (
            name, facts["price"], facts["band_hi"], facts["dist_pct"])
    elif rule == "band_trail_break":
        s = "%s 收盘 %.2f 跌破波段带 trail_ref=%.2f" % (
            name, facts["close"], facts["trail_ref"])
    elif rule == "data_stale":
        s = "technical 预热未得当日数据（%d/%d 票），MA20/跟踪止损判据今日禁用" % (
            facts.get("lacking", 0), facts.get("total", 0))
    else:
        s = "%s %s" % (name, json.dumps(facts, ensure_ascii=False))
    if review:
        s = "%s ·%s" % (s, review)   # 事件级复核短语（07 通知口径 0.0.25 修订）
    return s


def dispatch(events, uni_rows, no_notify, hk_delayed=False):
    """通知派发：只对 notify=True 的事件发电磁通知（其余已留痕台账）。
    港股在延迟降级态时文案加「延迟行情」前缀（如实标注，07「延迟口径」）。"""
    names = {r["code"]: r["name"] for r in uni_rows}
    names.update({"*": "", "cn": "A 股", "hk": "港股"})
    for ev in events:
        if not ev.get("notify"):
            continue
        label = names.get(ev["code"]) or names.get(ev.get("market"), "")
        msg = fmt_facts(ev["rule"], ev["facts"], label or ev["code"],
                        review=ev.get("review"))
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
    # 当日 technical 预热（0.0.25 P2 前置门数据通道）：只在交易时段尝试，
    # 非交易日/盘后不烧重试次数；成功后当日短路（cache 全新鲜即零请求）
    if any(vfetch.session_phase(m, None, now)["phase"] == "intraday"
           for m in ("cn", "hk")):
        cache, tech_events = warmup_technical(state_dir, uni, st, cfg, now=now)
        all_events += tech_events
        annotate_runtime(uni["rows"], state_dir, cache)
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
        events, _ = vrules.evaluate(ticks, uni["rows"], st["rules"], cfg, now,
                                    trailing=st.get("trailing"))
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
               "t2_pending_fill", "ma20_break", "trailing_exit",
               "band_lo_touch", "band_hi_touch"}


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
        # 0.0.25 新判据终判：一律用当日完整根现算（盘中根 ma20 是 estimated，
        # 勿复用缓存值——两把尺坑位）
        closes = [b["close"] for b in bars]
        ma20_full = vfetch._ma(closes, 20)
        if "ma20_break" in kinds:
            if ma20_full is not None:
                # 系数引 rules DEFAULT_CFG（SSOT）：盘中触发与收盘终判同一把尺
                hit = bar["close"] < ma20_full * vrules.DEFAULT_CFG["ma20_break_ratio"]
                item["verdicts"].append("MA20 破位收盘%s（%.2f / MA20 %.2f，完整根）"
                                        % ("确认" if hit else "撤回",
                                           bar["close"], ma20_full))
            else:
                item["verdicts"].append("MA20 完整根不足 20 根，无法终判（挂全诊）")
        if "trailing_exit" in kinds:
            if ma20_full is not None:
                hit = bar["close"] < ma20_full
                item["verdicts"].append("跟踪止损破线收盘%s（%.2f / MA20 %.2f）"
                                        % ("确认" if hit else "撤回",
                                           bar["close"], ma20_full))
            else:
                item["verdicts"].append("跟踪止损终判缺 MA20 完整根（挂全诊）")
        for edge, label, lo_hit in (("band_lo", "波段带下沿", True),
                                    ("band_hi", "波段带上沿", False)):
            rule = "band_lo_touch" if lo_hit else "band_hi_touch"
            if rule in kinds and row.get(edge) is not None:
                lvl = row[edge]
                hit = bar["close"] <= lvl if lo_hit else bar["close"] >= lvl
                item["verdicts"].append("%s 收盘%s（%.2f / %.2f）"
                                        % (label, "坐实" if hit else "收回",
                                           bar["close"], lvl))
        if not item["verdicts"]:
            item["verdicts"].append("盘中事件收盘全部撤回（以全诊为准）")
        out.append(item)
    return out


def trail_break_scan(uni_rows, bars_by_code, today):
    """收盘直判 band_trail_break（07 P2 波段带预钉：收盘破 trail_ref →
    「波段结束复核」）。只扫有 position 波段带锚的票；末根非当日不判。"""
    out = []
    for r in uni_rows:
        ref = r.get("trail_ref")
        bars = bars_by_code.get(r["code"])
        if ref is None or not bars \
                or str(bars[-1].get("date", ""))[:10] != today:
            continue
        close = bars[-1]["close"]
        if close < ref:
            out.append({"code": r["code"], "name": r.get("name", r["code"]),
                        "close": close, "trail_ref": ref})
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


def _outlook_digest(state_dir, today):
    """day-summary 附件：收盘复核时刻可得的最新一张收盘卡（<today，通常是
    昨日——当日卡 17:35 批量才出）。零权重指针节：全文指 outlook/<date>.md
    + 市场级摘要行；无卡/无目录不出节（幂等：close_pass 重渲由本函数重算，
    不存在外挂追加被冲掉的问题——09 分期表 P2 形态）。"""
    try:
        import outlook as vol
    except ImportError:
        return []
    d = vol.outlook_dir(state_dir)
    if not os.path.isdir(d):
        return []
    days = sorted(f[:-6] for f in os.listdir(d)
                  if f.endswith(".jsonl") and f[:-6] < today)
    if not days:
        return []
    day = days[-1]
    cards = vol.load_cards(state_dir, day)
    if not cards:
        return []
    lines = ["## 走势参考（上一张收盘卡 · %s）" % day, ""]

    def _d(v):  # C1 收口同律：投影端滤 None 键后渲染端不得渗 "None%" 字面量
        return "—" if v is None else v
    lines.append("- 全文（全集日表 + 预测带/经验计数）：%s.md"
                 % os.path.join(vol.outlook_dir(state_dir), day))
    for c in cards:  # 市场维度共享：任取一张卡的市场级投影
        mk = (c.get("emotion") or {}).get("market") or {}
        if mk.get("state") != "estimated":
            continue
        mg = mk.get("margin") or {}
        if mg:
            lines.append("- 两融余额 %s 亿（%s，Δ5d %s%%，70 日分位 %s%%）"
                         % (_d(mg.get("balance_yi")), mg.get("as_of"),
                            _d(mg.get("chg_5d_pct")),
                            _d(mg.get("pctile_70d"))))
        tp = mk.get("turnover_pctile") or {}
        if tp:
            lines.append("- 全A换手分位 %s%%（%s）" % (_d(tp.get("pctile")),
                                                      tp.get("as_of")))
        ep = mk.get("erp") or {}
        if ep:
            lines.append("- ERP %s%%（%s，5 年月频分位 %s%%）" % (
                _d(ep.get("erp_pct")), ep.get("as_of"),
                _d(ep.get("pctile_5y_monthly"))))
        break
    lines.append("- 当日收盘卡由 17:35 批量产出（outlook_daily --daily）；零权重"
                 "参考，非投资建议")
    return lines + [""]


# ------------------------------------------------- 收盘操作复核（0.0.25）

# 五档机械投影（04「操作建议」持仓者分支的动作分类学；只投影不重裁决，
# 以报告原文为准——signals.json 的 action 是结构化代理，非报告正文）
_TIER_TEXT = {
    "strong_buy": "持有（strong_buy 族：逢高减仓口径见报告）",
    "buy": "持有（buy 族：逢高减仓口径见报告）",
    "hold": "持有观察（hold：按止损纪律执行）",
    "watch": "持有观察（watch）",
    "reduce": "减仓档复核（reduce）",
    "sell": "离场档复核（sell 族：减仓或离场，以报告原文为准）",
    "strong_sell": "离场档复核（strong_sell）",
    "add_on": "加仓轨在途（addon：三段确认制，见 10）",
}


def render_review_lines(events, uni_rows):
    """操作复核节（事件 × 既有纪律映射的确定性投影；零 LLM、离线可测）。
    纪律原文锚：06 三价（target1=hi20、+15% 后改 trailing 收盘破 MA20 离场）
    /持有期（止损止盈后资金留存不追补）/波段带（纪律参考线非止损指令，
    08 三层下行门是唯一离场口径）——两套离场口径分行列不互引。"""
    rows = {r["code"]: r for r in uni_rows}
    # 复核节覆盖集 ≠ PRICE_RULES（终判集）：trailing_armed/band_trail_break 无
    # 收盘终判语义但必须进操作复核（07「日报行」承诺），扩集不得反向进
    # classify_close/ev_stocks 终判路径
    review_rules = PRICE_RULES | {"trailing_armed", "band_trail_break"}
    by_code = {}
    for e in events:
        if e.get("code") == "*" or e.get("rule") not in review_rules:
            continue
        by_code.setdefault(e["code"], set()).add(e["rule"])
    if not by_code:
        return []
    lines = []
    for code in sorted(by_code):
        rls = by_code[code]
        r = rows.get(code)
        if r is None:
            continue
        acts = []
        if "target_hit" in rls and r.get("target1") is not None:
            acts.append("止盈纪律复核：目标1=hi20 站上——06 三价纪律 +15% 后改 "
                        "trailing（收盘破 MA20 离场）；止盈后资金留存不追补")
        if {"stop_break", "stop_break_confirmed", "whipsaw"} & rls:
            acts.append("止损纪律复核：06 持有期纪律——触发后资金留存不追补")
        if "ma20_break" in rls:
            acts.append("均线纪律复核：破 MA20×0.98（机械降档 medium，待全诊消费）")
        if "trailing_armed" in rls:
            acts.append("跟踪止损已武装（+15% 口径，06 三价纪律改锚）")
        if "trailing_exit" in rls:
            acts.append("跟踪止损复核：武装态破 MA20（06：收盘破 MA20 离场口径）")
        if "band_lo_touch" in rls:
            acts.append("低吸复核：position 轨波段带下沿（纪律参考线非止损指令，"
                        "离场唯一口径是 08 三层下行门）")
        if "band_hi_touch" in rls:
            acts.append("高抛复核：position 轨波段带上沿（纪律参考线非止损指令）")
        if "t2_pending_fill" in rls:
            acts.append("T2 成交复核：推演成交未写回（写回属 P3 sim SSOT）")
        if "band_trail_break" in rls:
            acts.append("波段结束复核：收盘破 trail_ref（position 轨纪律参考线，"
                        "离场唯一口径是 08 三层下行门）")
        if not acts:
            continue
        sig = []
        if r.get("signal_action"):
            sig.append("default 轨最近信号 %s → %s" % (
                r["signal_action"],
                _TIER_TEXT.get(r["signal_action"], "档位见报告原文")))
        if r.get("pos_signal_action"):
            sig.append("position 轨最近信号 %s" % r["pos_signal_action"])
        tail = "；最近信号投影：%s（只投影不重裁决，以报告原文为准）" % \
            "；".join(sig) if sig else ""
        lines.append("- **%s %s**（%s）：%s%s" % (
            code, r.get("name", code), r.get("kind", "?"), "；".join(acts), tail))
    return lines


def weight_review_lines(uni_rows, ticks):
    """权重提示（用户 2026-11-02 裁定分桶不折算；0.0.25 评审收口：**限实盘
    持仓**——06 持有期漂移锚是实盘组合纪律，sim 推演盘混入会稀释实盘真实
    权重且无操作意义）：收盘以末轮 tick 价 × 持仓数量现算市值，A（CNY）/
    港（HKD）各以本桶实盘总市值为分母，单仓 >16% → 「次日减至 ≤14%」复核行
    （06 持有期漂移锚，与建仓带 14.5% 是两把尺）；fx 不进判定（SKILL 红线
    4）。只落百分比——金额/数量不落任何产物（脱敏红线）；单票桶分母无分散
    意义，跳过。"""
    last_px = {}
    for t in ticks:
        if t.get("code"):
            last_px[t["code"]] = t.get("price")   # jsonl 顺序读，后写覆盖
    lines = []
    for market, label in (("cn", "A 股桶（CNY）"), ("hk", "港股桶（HKD）")):
        hold = [(r["code"], r.get("name", r["code"]),
                 (last_px.get(r["code"]) or 0) * (r.get("_qty") or 0))
                for r in uni_rows
                if r.get("market") == market and r.get("_qty")
                and r.get("kind") == "real" and last_px.get(r["code"])]
        if len(hold) < 2:
            continue
        total = sum(v for _, _, v in hold)
        if total <= 0:
            continue
        for code, name, mv in hold:
            w = mv / total * 100
            if w > 16:
                lines.append("- **%s %s**：单仓权重 %.1f%%（%s）＞16%%——持有期纪律"
                             "「次日减至 ≤14%%」（06 漂移锚）" % (code, name, w, label))
    return lines


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
    annotate_runtime(uni["rows"], state_dir, load_tech_cache(state_dir))
    hk_codes = [r["code"] for r in uni["rows"] if r["market"] == "hk"
                and any(t.get("code") == r["code"] for t in ticks)]
    # 波段带 trail_ref 收盘直判票（band_trail_break）与有成本票（trailing high
    # 收盘归并——data_stale 日盘中判据禁用时当日 high 只能收盘补，P2-3）并入
    # 取数集（≈持仓数请求，与 --close 既有量级同阶）
    trail_codes = [r["code"] for r in uni["rows"] if r.get("trail_ref") is not None]
    cost_codes = [r["code"] for r in uni["rows"] if r.get("_cost")]
    need = list(dict.fromkeys(list(ev_stocks) + hk_codes + trail_codes
                              + cost_codes))
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

    # trailing 跟踪态收盘更新（跨日持续态：high 以当日完整根 high 归并——
    # 自 0.0.25 部署日起累积，不回溯建仓前历史，如实口径）
    tr_st = st.setdefault("trailing", {})
    for r in uni["rows"]:
        bars = bars_by_code.get(r["code"])
        if r.get("_cost") and bars \
                and str(bars[-1].get("date", ""))[:10] == today and bars[-1].get("high"):
            tr = tr_st.setdefault(r["code"], {"armed": False, "high": 0.0})
            tr["high"] = max(tr.get("high") or 0.0, bars[-1]["high"])

    # 波段带 trail_ref 收盘直判（07 P2 预钉「波段结束复核」）：台账留痕
    # （notify=False——收盘批量的通知面是「收盘复核完成」运维条，不逐票打扰）；
    # 幂等去重：--close 重跑不重复追加（台账是事实源，重复行会污染复核节渲染）
    trail_breaks = trail_break_scan(uni["rows"], bars_by_code, today)
    if trail_breaks:
        seen_tb = {e["code"] for e in events if e.get("rule") == "band_trail_break"}
        trail_breaks = [b for b in trail_breaks if b["code"] not in seen_tb]
    if trail_breaks:
        append_jsonl(os.path.join(p["events"], today + ".jsonl"), [
            {"ts": _now().isoformat(timespec="seconds"), "code": b["code"],
             "market": next((r["market"] for r in uni["rows"]
                             if r["code"] == b["code"]), "?"),
             "kind": "close", "rule": "band_trail_break", "level": "T0",
             "notify": False, "mech_risk": None,
             "review": vrules._REVIEW_HINT["band_trail_break"],
             "facts": {"close": b["close"], "trail_ref": b["trail_ref"],
                       "dist_pct": round((b["close"] / b["trail_ref"] - 1) * 100, 2),
                       "note": "收盘破波段带 trail_ref（position 轨纪律参考线）"}}
            for b in trail_breaks])
        events = read_jsonl(os.path.join(p["events"], today + ".jsonl"))

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
    # 操作复核节（0.0.25）：事件 × 纪律映射投影 + 权重分桶提示（只投影
    # 不重裁决；权重只落百分比——金额/数量不落盘）
    review_lines = render_review_lines(events, uni["rows"])
    weight_lines = weight_review_lines(uni["rows"], ticks)
    if review_lines or weight_lines:
        lines.append("## 操作复核（事件 × 纪律映射 · 只投影不重裁决 · 待用户裁量）")
        lines.append("")
        lines += review_lines
        if weight_lines:
            lines.append("- 权重提示（A/港分桶不折算，fx 不进判定）：")
            lines += ["  " + w for w in weight_lines]
        lines.append("")
    unresolved = [e for e in events if e.get("code") != "*"
                  and (e.get("mech_risk") or {}).get("downgrade")
                  and e["rule"] in PRICE_RULES]
    # 按 rule 出摘要词（P1-2：机械降档族已不止止损——ma20_break 是 ×0.98 破位，
    # 止损时代硬编码文案会张冠李戴）
    _focus_text = {"stop_break": "止损击穿加深", "stop_break_confirmed": "止损线击穿确认",
                   "ma20_break": "MA20 破位（×0.98）降档 medium"}
    by_code = {}
    for e in unresolved:
        by_code.setdefault(e["code"], set()).add(e["rule"])
    lines.append("## 次日盯盘重点")
    for code, rls in sorted(by_code.items()):
        lines.append("- %s：%s（机械降档事实待全诊消费）" % (
            code, "；".join(sorted(_focus_text.get(r, r) for r in rls))))
    if not unresolved:
        lines.append("- 无未处理机械降档事件")
    lines += [""]
    lines += _outlook_digest(state_dir, today)  # 09 P2：上一张收盘卡指针节
    lines += ["*%s*" % DISCLAIMER, ""]
    os.makedirs(p["summary"], exist_ok=True)
    with open(os.path.join(p["summary"], today + ".md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print("close: 终判 %d 只，日报已渲染 monitor/day-summary/%s.md"
          % (len(verdicts), today), flush=True)
    notify("收盘复核完成：终判 %d 只 · 操作复核与全文见 day-summary/%s.md"
           % (len(verdicts), today), no_notify=no_notify)   # 运维类（事实级）
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
        check("波段带三键并行投影（0.0.25：独立行键不互覆）",
              by["600001"]["band_lo"] == 8.00 and
              by["600001"]["band_hi"] == 12.00 and
              by["600001"]["trail_ref"] == 10.50 and
              by["600001"]["band_levels_source"] == "signals")
        check("无 position 信号票波段带缺省（禁现算充锚）",
              by["600003"].get("band_lo") is None
              and by["600003"]["band_levels_source"] == "none")
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

    # 6c) 复核短语文案钉（07 通知口径 0.0.25 修订）：带短语 rule 以「·XX复核」
    #     结尾；运维类零「复核」负断言；目标价1= 排版修复钉（I-027 连读歧义）
    s = fmt_facts("target_hit", {"price": 9.47, "target1": 9.43}, "金蝶国际",
                  review="止盈复核")
    check("target_hit 文案带复核短语与等号排版",
          s.endswith("·止盈复核") and "目标价1=9.43" in s and "目标价1 9.43" not in s)
    check("止损文案带复核短语",
          fmt_facts("stop_break", {"price": 9.0, "stop": 9.8, "depth_pct": 8.2},
                    "甲", review="止损复核").endswith("·止损复核"))
    check("ma20_break 文案带复核短语",
          fmt_facts("ma20_break", {"price": 27.3, "ma20": 28.0, "dist_pct": -2.5},
                    "甲", review="均线复核").endswith("·均线复核"))
    check("trailing_exit 文案带复核短语",
          fmt_facts("trailing_exit", {"price": 27.9, "ma20": 28.0,
                                      "high_since_entry": 30.0,
                                      "dist_ma20_pct": -0.4},
                    "甲", review="跟踪止损复核").endswith("·跟踪止损复核"))
    check("波段带文案带复核短语",
          fmt_facts("band_lo_touch", {"price": 24.9, "band_lo": 25.0,
                                      "dist_pct": -0.4},
                    "甲", review="低吸复核").endswith("·低吸复核"))
    for r, f in (("frozen", {"rounds": 5}),
                 ("market_halted", {"snapshot_date": "2026-11-01"}),
                 ("hk_delayed", {"max_lag_min": 18, "threshold_min": 15}),
                 ("source_dropped", {"codes": ["600001"]}),
                 ("storm_digest", {"suppressed_count": 3, "kinds": {}})):
        check("运维类 %s 零复核短语" % r, "复核" not in fmt_facts(r, f, "甲"))
    import io
    import contextlib
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        notify("文案链路钉", no_notify=True)
    check("notify 尾注单点追加",
          "文案链路钉" in buf.getvalue()
          and NOTIFY_TAIL in buf.getvalue())

    # 6d) technical 预热门（0.0.25）：data_stale 事件构造（当日性门以
    #     warmup_technical 内联逐票 data_date 判定为单一事实源，无独立谓词）
    dse = _data_stale_event(_now(), ["600001", "000002"], 21)
    check("data_stale 事件形态（运维类零短语）",
          dse["rule"] == "data_stale" and dse["notify"]
          and "review" not in dse and dse["facts"]["lacking"] == 2)

    # 6e) 运行期注入（annotate_runtime）：内存生效、磁盘宇宙零污染（脱敏）
    with tempfile.TemporaryDirectory() as td:
        os.makedirs(os.path.join(td, "monitor"))
        with open(os.path.join(td, "portfolio.json"), "w", encoding="utf-8") as f:
            json.dump({"holdings": [{"code": "600001", "market": "cn",
                                     "quantity": 100, "cost_price": 10.00}]}, f)
        scan = os.path.join(td, "reports", "_scans", "d", "portfolio")
        os.makedirs(scan)
        with open(os.path.join(scan, "allocation.json"), "w", encoding="utf-8") as f:
            json.dump({"rows": [{"code": "600009", "price": 9.90, "lots": 4,
                                 "cost": 3960, "stop": 9.5, "entry_ref": 9.7,
                                 "target1": 11.0}]}, f)
        rows = [{"code": "600001", "market": "cn", "kind": "real"},
                {"code": "600009", "market": "cn", "kind": "sim"},
                {"code": "600100", "market": "cn", "kind": "watch"}]
        uni_disk = {"date": "2026-11-03", "rows": [dict(r) for r in rows]}
        varchive.write_json_atomic(os.path.join(td, "monitor", "universe.json"),
                                   uni_disk)
        before = open(os.path.join(td, "monitor", "universe.json"),
                      encoding="utf-8").read()
        cache = {"date": "2026-11-03",
                 "codes": {"600001": {"ma20": 9.9, "data_date": "2026-11-03"},
                           "600009": {"ma20": None, "data_date": "2026-11-02"}}}
        annotate_runtime(rows, td, cache)
        by = {r["code"]: r for r in rows}
        check("real 注入成本/数量/ma20",
              by["600001"]["_cost"] == 10.0 and by["600001"]["_qty"] == 100
              and by["600001"]["_ma20"] == 9.9)
        check("sim 成本=配置日价（cost≡lots×100×price）、末根非当日 ma20 禁用",
              by["600009"]["_cost"] == 9.90 and by["600009"]["_qty"] == 400
              and by["600009"]["_ma20"] is None)
        check("watch 档不注入成本", by["600100"].get("_cost") is None)
        after = open(os.path.join(td, "monitor", "universe.json"),
                     encoding="utf-8").read()
        check("注入零落盘（磁盘宇宙不变，脱敏）", before == after
              and "_cost" not in after and "_ma20" not in after)

    # 6f) 收盘终判新分支：MA20/trailing_exit/band（完整根现算口径）
    bars20 = [{"date": "2026-10-%02d" % d, "close": 30.0, "low": 29.0,
               "high": 31.0, "open": 30.0} for d in range(1, 21)]
    uni_rows2 = [{"code": "600010", "market": "cn", "name": "甲", "kind": "real",
                  "stop": None, "target1": None, "entry_ref": None,
                  "band_lo": 25.0, "band_hi": 31.0, "trail_ref": 20.0}]
    bb = bars20 + [{"date": today, "close": 27.0, "low": 26.5, "high": 29.0,
                    "open": 28.5}]
    out = classify_close({"600010": [{"rule": "ma20_break"},
                                     {"rule": "trailing_exit"},
                                     {"rule": "band_lo_touch"},
                                     {"rule": "band_hi_touch"}]},
                         {"600010": bb}, uni_rows2, today)
    vs = "；".join(out[0]["verdicts"])
    ma20_r = round(sum(b["close"] for b in bb[-20:]) / 20, 3)
    check("MA20 破位完整根终判（勿复用盘中 estimated）",
          "MA20 破位收盘确认" in vs and ("%.2f" % ma20_r) in vs)
    check("trailing_exit 终判与波段带终判",
          "跟踪止损破线收盘确认" in vs and "波段带下沿 收盘收回" in vs)
    out = classify_close({"600010": [{"rule": "band_hi_touch"}]},
                         {"600010": bb}, uni_rows2, today)
    check("波段带上沿收盘收回", "波段带上沿 收盘收回" in out[0]["verdicts"][0])

    # 6g) band_trail_break 收盘直判扫（trail_ref 破线出、未破不出、末根非当日不判）
    rows_t = [{"code": "600011", "name": "乙", "trail_ref": 28.0},
              {"code": "600012", "name": "丙", "trail_ref": 20.0}]
    bars_map = {"600011": bb, "600012": bb}
    tb = trail_break_scan(rows_t, bars_map, today)
    check("trail_ref 破线直判", [x["code"] for x in tb] == ["600011"]
          and tb[0]["close"] == 27.0)
    check("trail_ref 末根非当日不判",
          trail_break_scan(rows_t, bars_map, "2026-11-30") == [])

    # 6h) 操作复核节渲染（事件×纪律映射 + 五档投影；无事件不出）
    rows_r = [{"code": "600013", "market": "cn", "name": "丁", "kind": "real",
               "target1": 11.0, "stop": 9.5, "signal_action": "reduce",
               "signal_family": "bear", "pos_signal_action": "watch"}]
    evs = [{"code": "600013", "rule": "target_hit"},
           {"code": "*", "rule": "market_halted"},
           {"code": "600013", "rule": "abnormal_move"}]
    rl = render_review_lines(evs, rows_r)
    check("操作复核行含纪律映射与五档投影",
          any("止盈纪律复核" in x and "trailing" in x and "资金留存不追补" in x
              for x in rl)
          and any("default 轨最近信号 reduce → 减仓档复核" in x
                  and "position 轨最近信号 watch" in x for x in rl))
    check("非价位事件与无事件不出操作复核",
          all("600013" in x or True for x in rl)
          and render_review_lines([{"code": "*", "rule": "market_halted"}],
                                  rows_r) == [])
    # P1-1/P2-1 钉：trailing_armed/band_trail_break 在终判集（PRICE_RULES）外、
    # 但必须进操作复核（07「日报行」承诺）——复核覆盖集独立于终判集
    rl2 = render_review_lines([{"code": "600013", "rule": "band_trail_break"},
                               {"code": "600013", "rule": "trailing_armed"}],
                              rows_r)
    check("波段结束/武装事件进操作复核",
          any("波段结束复核" in x and "三层下行门" in x for x in rl2)
          and any("跟踪止损已武装" in x for x in rl2))

    # 6i) 权重分桶提示（>16% 出行、单票桶跳过、零金额数量落盘、限实盘）
    rows_w = [{"code": "600021", "market": "cn", "name": "戊", "kind": "real",
               "_qty": 100},
              {"code": "600022", "market": "cn", "name": "己", "kind": "real",
               "_qty": 100},
              {"code": "600023", "market": "cn", "name": "辛", "kind": "sim",
               "_qty": 100},
              {"code": "00005", "market": "hk", "name": "庚", "kind": "real",
               "_qty": 100}]
    tks = [{"code": "600021", "price": 30.0}, {"code": "600022", "price": 1.0},
           {"code": "600023", "price": 50.0}, {"code": "00005", "price": 9.0}]
    wl = weight_review_lines(rows_w, tks)
    check("权重 >16% 出复核行（本桶分母、fx 不进判定、sim 不混桶）",
          len(wl) == 1 and "600021" in wl[0] and "96.8%" in wl[0]
          and "次日减至 ≤14%" in wl[0] and "A 股桶（CNY）" in wl[0])
    check("权重行零金额数量字面量（脱敏）",
          not any(k in "".join(wl) for k in ("3000", "100 股", '"_qty"')))
    check("单票桶分母无分散意义跳过",
          weight_review_lines([rows_w[2]], tks) == [])

    # 6j) ensure_state：trailing 跨日保留、tech 同日继承跨日重置（0.0.25）
    with tempfile.TemporaryDirectory() as td:
        st = ensure_state(td, "2026-11-02")
        st["trailing"] = {"600001": {"armed": True, "high": 12.0}}
        st["tech"] = {"date": "2026-11-02", "tries": 2, "stale_notified": True}
        save_state(td, st)
        st2 = ensure_state(td, "2026-11-03")
        check("trailing 跨日保留（防隔日 trailing_exit 漏报）",
              st2["trailing"] == {"600001": {"armed": True, "high": 12.0}})
        check("tech 跨日重置", st2["tech"]["tries"] == 0
              and st2["tech"]["stale_notified"] is False)
        st3 = ensure_state(td, "2026-11-02")
        check("tech 同日继承", st3["tech"]["tries"] == 2)

    # 6b) 走势参考附件（09 P2）：close_pass 重渲消费上一张收盘卡（<today——
    #     当日卡 17:35 批量才出）；无目录/当日卡不出节
    import outlook as _vol
    _card = {"schema": "outlook/1", "state": "estimated", "market": "cn",
             "code": "600001", "date": "2026-11-03", "price": 10.0,
             "price_kind": "close",
             "emotion": {"market": {"state": "estimated", "margin": {
                 "balance_yi": 22988.6, "as_of": "2026-11-03",
                 "chg_5d_pct": -4.6, "pctile_70d": 1.4}}}}
    with tempfile.TemporaryDirectory() as td_ol, \
            tempfile.TemporaryDirectory() as td_none:
        check("附件-无目录不出节", _outlook_digest(td_none, today) == [])
        _vol.persist_card(td_ol, _card, "2026-11-03T18:00:00+08:00")
        dig = _outlook_digest(td_ol, "2026-11-04")
        check("附件-有卡出节", any("上一张收盘卡 · 2026-11-03" in s for s in dig))
        check("附件-市场级行", any("两融余额 22988.6" in s for s in dig))
        check("附件-零权重尾注",
              any("零权重" in s and "非投资建议" in s for s in dig))
        check("附件-当日卡不进附件", _outlook_digest(td_ol, "2026-11-03") == [])
        # C1 收口同律（I-012）：残块缺键的投影经 digest 渲染不得渗 None 字面量
        _card_part = json.loads(json.dumps(_card))
        _card_part["emotion"]["market"]["margin"] = {
            "balance_yi": 22988.6, "as_of": "2026-11-03"}
        _vol.persist_card(td_ol, _card_part, "2026-11-03T18:01:00+08:00")
        dig_p = _outlook_digest(td_ol, "2026-11-04")
        _mg = "".join(s for s in dig_p if "两融余额" in s)
        check("附件-缺键渲染—不渗None",
              _mg and "None" not in _mg and "—" in _mg)

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
    # 7b) outlook 17:35 收盘批量槽模板钉（09 P2 / 0.0.20 声明的 plistlib 解析
    #     钉落地：模板漂移无钉可拦的虚称补实；与 monitor 模板同目录上两级）
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(
            __file__))), "outlook",
            "com.threefish.vibestock.outlook.plist"), "rb") as f:
        ojob = plistlib.load(f)
    check("outlook 模板拉起 --daily", ojob["ProgramArguments"][-1] == "--daily")
    check("outlook 模板无 KeepAlive（一次性命令，失败次日自愈）",
          "KeepAlive" not in ojob)
    check("outlook 模板 RunAtLoad=false", ojob["RunAtLoad"] is False)
    o_slots = {}
    for ent in ojob["StartCalendarInterval"]:
        o_slots.setdefault(ent["Weekday"], set()).add(
            ent["Hour"] * 60 + ent["Minute"])
    check("outlook 模板周一至五单槽 17:35（≥17:10 定型窗后）",
          sorted(o_slots) == [1, 2, 3, 4, 5]
          and {frozenset(v) for v in o_slots.values()}
          == {frozenset({17 * 60 + 35})})
    check("outlook 槽与 monitor 最晚槽错峰 ≥60min（FetchLock 无重叠排队）",
          min(next(iter(o_slots.values()))) - max(mins) >= 60)

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
