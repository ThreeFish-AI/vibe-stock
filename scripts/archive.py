#!/usr/bin/env python3
"""archive.py · vibe-stock 报告归档层（布局 / 单日多版本 / 时间线索引 / 存量迁移）。

规约见 references/04-report.md（布局与去冗余）、references/05-postmortem.md（信号字段）：
  - reports/<code>.<market>/<date>.md：一股一日一文件，同日重跑追加 v<N> 版本，
    与上一版逐字相同的节写「同 vK。」；快照模式进 _snapshot/<code>/。
  - reports/<code>.<market>/index.md 与 reports/index.md：signals.json 的派生视图，
    report / postmortem 时整体重建。
  - 函数一律显式接收 reports_dir / 路径，不读全局状态目录（selftest 靠参数隔离）。
由 diagnose.py（report / migrate-reports）与 postmortem.py 调用，自身无 CLI。
"""
import datetime as dt
import hashlib
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fetch as fx  # noqa: E402

MARKETS = ("cn", "hk")
CODE_RE = {"cn": re.compile(r"\d{6}"), "hk": re.compile(r"\d{5}")}
SNAPSHOT_CODE_RE = re.compile(r"[0-9A-Za-z]{1,16}")
VER_RE = re.compile(r"^## v(\d+) · (\d\d:\d\d:\d\d)$")
SAME_RE = re.compile(r"^同 v(\d+)。$")
LEGACY_RE = re.compile(r"^(.+)-(\d{4}-\d{2}-\d{2})\.md$")
LOST = "（报告已被覆盖，无法恢复）"
HORIZONS = (1, 3, 5, 10)
INDEX_NOTE = "> 由 signals.json 派生：report / postmortem 时整体重建，勿手改。"
OWNER_TOLERANCE_S = 2  # 迁移：文件 mtime 与信号 created_at 同刻判定容差


# ---------------------------------------------------------------- 原子读写

def load_signals(path):
    """严格加载：文件缺失=[]；解析失败或非列表抛 ValueError，调用方不得写回。"""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("signals.json 顶层须为列表")
    return data


def _write_atomic(path, text):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(text)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)


def write_json_atomic(path, obj):
    _write_atomic(path, json.dumps(obj, ensure_ascii=False, indent=1))


def _read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------- 布局

def stock_dir(reports_dir, market, code):
    """股票目录（路径穿越闸门）：cn/hk → <code>.<market>，其余（快照 "?"）
    → _snapshot/<code>；code 不合形态抛 ValueError。"""
    code = str(code)
    if market in MARKETS:
        if not CODE_RE[market].fullmatch(code):
            raise ValueError("%s 代码须为规范形态：%r" % (market, code))
        return os.path.join(reports_dir, "%s.%s" % (code, market))
    if market != "?" or not SNAPSHOT_CODE_RE.fullmatch(code):
        raise ValueError("非法报告身份：market=%r code=%r" % (market, code))
    return os.path.join(reports_dir, "_snapshot", code)


def day_title(dirname, date):
    return "诊股报告 · %s · %s" % (dirname, date)


# ---------------------------------------------------------------- 单日多版本

def _footer_cut(lines):
    """末个裸 `---` 行之后为免责段；无则全文为正文。"""
    for i in range(len(lines) - 1, -1, -1):
        if lines[i] == "---":
            return i
    return len(lines)


def _esc(ln):
    return "\\" + ln if ln.startswith("#") else ln


def _unesc(ln):
    return ln[1:] if ln.startswith("\\#") else ln


def split_report(md):
    """render_report 单版 markdown → (sections, footer)；sections=[(节名, 正文)]，
    正文为原始形态。以 # 起头的正文行转义为 \\# 防伪造节头——compose 写出时
    同规则转义、parse 读回时去转义，三处对称。坑位：`## ` 行是切节依据，正文
    内出现伪 `## ` 无法在此区分，须由源头根除（render_report 的 rationale/note
    均已压单行）。"""
    lines = md.rstrip("\n").split("\n")
    cut = _footer_cut(lines)
    sections, heading, buf = [], None, []
    for ln in lines[:cut]:
        if heading is None and not sections:
            if ln.startswith("# "):  # 首个 H1 是标题，其余标题区内容丢弃
                continue
        if ln.startswith("## "):
            if heading is not None:
                sections.append((heading, "\n".join(buf).strip("\n")))
            heading, buf = ln[3:], []
            continue
        if heading is not None:
            buf.append(ln)  # 原始形态；转义只发生在 compose 写文件时
    if heading is not None:
        sections.append((heading, "\n".join(buf).strip("\n")))
    return sections, "\n".join(lines[cut + 1:]).strip()


def compose_day(title, versions, footer):
    """versions=[{"n","time","sections"}]，sections=None 表丢失版。与上一个
    有内容版本逐字相同的节写「同 vK。」，K 回溯到该内容最早出现的版本。"""
    out = ["# " + title, ""]
    prev = {}
    for v in versions:
        out += ["## v%d · %s" % (v["n"], v["time"]), ""]
        if v["sections"] is None:
            out += [LOST, ""]
            continue
        cur = {}
        for h, body in v["sections"]:
            p = prev.get(h)
            if p and p[1] == body:
                out += ["### " + h, "同 v%d。" % p[0], ""]
                cur[h] = p
            else:
                out += ["### " + h, "\n".join(_esc(x) for x in body.split("\n")), ""]
                cur[h] = (v["n"], body)
        prev = cur
    out += ["---", footer]
    return "\n".join(out) + "\n"


def parse_day(text):
    """compose_day 的逆：返回 (title, versions, footer)，「同 vK。」已回溯为原文。"""
    lines = text.rstrip("\n").split("\n")
    cut = _footer_cut(lines)
    title, versions, heading, buf = "", [], None, []

    def flush():
        body = "\n".join(buf).strip("\n")
        if heading is not None:
            versions[-1]["sections"].append((heading, body))
        elif versions and body == LOST:
            versions[-1]["sections"] = None

    for ln in lines[:cut]:
        m = VER_RE.match(ln)
        if m:
            if versions:
                flush()
            versions.append({"n": int(m.group(1)), "time": m.group(2),
                             "sections": []})
            heading, buf = None, []
        elif ln.startswith("### ") and versions and versions[-1]["sections"] is not None:
            flush()
            heading, buf = ln[4:], []
        elif ln.startswith("# ") and not versions:
            title = ln[2:]
        elif versions:
            buf.append(ln)
    if versions:
        flush()
    resolved = {}
    for v in versions:
        if v["sections"] is None:
            continue
        secs = []
        for h, body in v["sections"]:
            m = SAME_RE.match(body)
            if m:
                body = resolved.get(int(m.group(1)), {}).get(h, body)
            secs.append((h, "\n".join(_unesc(x) for x in body.split("\n"))))
        v["sections"] = secs
        resolved[v["n"]] = dict(secs)
    return title, versions, "\n".join(lines[cut + 1:]).strip()


def append_version(path, title, sections, footer, hhmmss):
    """把一版追加进单日文件（不存在则新建），原子写；返回版本号。"""
    versions = []
    if os.path.exists(path):
        title, versions, _ = parse_day(_read(path))
        if not versions:
            # 零版本头＝非本工具产物（compose 恒写版本头）：拒绝重写，防外部
            # 损坏文件被静默重置 v1、存量信号的 report_version 悬空
            raise ValueError("单日文件 %s 无可解析版本头（外部损坏？），拒绝重写"
                             % path)
    n = max([v["n"] for v in versions] or [0]) + 1
    versions.append({"n": n, "time": hhmmss, "sections": sections})
    _write_atomic(path, compose_day(title, versions, footer))
    return n


# ---------------------------------------------------------------- 时间线索引

def _fmt(v, nd=2):
    return "—" if v is None else ("%.*f" % (nd, v))


def _horizon_cell(s, h):
    ev = (s.get("evaluated") or {}).get(str(h))
    if not ev:
        return "—"
    base, outcome = s.get("close_at_signal"), ev.get("outcome", "")
    pct = ("%+.1f%%" % ((ev["close"] / base - 1) * 100)
           if base and ev.get("close") is not None else "")
    return " ".join(x for x in (pct, "" if outcome == "observed" else outcome) if x) or "—"


def _report_cell(s, dirname):
    rp = s.get("report_path")
    if rp and os.path.basename(os.path.dirname(rp)) == dirname:
        name = os.path.basename(rp)
        return "[%s](%s)" % (name[:-3], name)
    return (s.get("created_at") or s.get("date") or "—")[:10]


def _ordered(signals):
    return sorted(signals, key=lambda s: (s.get("created_at") or "", s.get("id") or ""),
                  reverse=True)


def _group_name(signals):
    """组内最新非空 stock_name（某次取数失败不冲掉已知名称）；未知 None。"""
    for s in _ordered(signals):
        if s.get("stock_name"):
            return s["stock_name"]
    return None


# ---------------------------------------------------------------- 显示名缓存

def names_path(state_dir):
    return os.path.join(state_dir, "names.json")


def load_names(state_dir):
    """code→名称 显示缓存（market:code 键）。可再生的派生缓存：缺失/损坏
    一律回 {}（下次 report 写穿自愈），不做严格加载。"""
    try:
        with open(names_path(state_dir), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def update_names(state_dir, market, code, name):
    """report 写穿：把本次取到的名称并进缓存，返回合并后全量（索引重建直用）。
    信号侧 stock_name 是登记时刻的历史名，本缓存是显示时刻的当前名——存量
    信号（早于名称功能）经此路径也能显名。"""
    names = load_names(state_dir)
    names["%s:%s" % (market, code)] = name
    write_json_atomic(names_path(state_dir), names)
    return names


def _display_name(signals, market, code, names):
    """名称解析顺序：组内最新非空 stock_name（历史名优先）→ names 缓存 → None。"""
    return _group_name(signals) or (names or {}).get("%s:%s" % (market, code))


def render_stock_index(signals, market, code, names=None):
    dirname = "%s.%s" % (code, market)
    rows = [s for s in signals if s.get("market") == market and s.get("code") == code]
    name = _display_name(rows, market, code, names)
    L = ["# %s%s · 诊股时间线" % (dirname, " · %s" % name if name else ""),
         "", INDEX_NOTE, "",
         "| 日期 | 版本 | 信号→动作 | 置信 | 登记价 | 状态 | %s |" %
         " | ".join("T+%d" % h for h in HORIZONS),
         "| --- | --- | --- | --- | --- | --- | %s |" % " | ".join("---" for _ in HORIZONS)]
    for s in _ordered(rows):
        ver = "v%d" % s["report_version"] if s.get("report_version") else "—"
        if s.get("report_lost"):
            ver += "（已丢失）"
        L.append("| %s | %s | %s→%s | %s | %s | %s | %s |" % (
            _report_cell(s, dirname), ver, s.get("signal", "?"), s.get("action", "?"),
            _fmt(s.get("confidence")), _fmt(s.get("close_at_signal")),
            s.get("status", "?"), " | ".join(_horizon_cell(s, h) for h in HORIZONS)))
    return "\n".join(L) + "\n"


def render_root_index(signals, names=None):
    groups = {}
    for s in signals:
        groups.setdefault((s.get("market"), s.get("code")), []).append(s)
    latest = sorted(((_ordered(g)[0], g) for g in groups.values()),
                    key=lambda x: (x[0].get("created_at") or "", x[0].get("id") or ""),
                    reverse=True)
    L = ["# 诊股总览", "", INDEX_NOTE, "",
         "| 股票 | 股票名称 | 最新日期 | 最新信号→动作 | 置信 | 诊断次数 | pending |",
         "| --- | --- | --- | --- | --- | --- | --- |"]
    for s, g in latest:
        dirname = "%s.%s" % (s["code"], s["market"])
        L.append("| [%s](%s/index.md) | %s | %s | %s→%s | %s | %d | %d |" % (
            dirname, dirname, _display_name(g, g[0].get("market"), g[0].get("code"), names) or "—",
            (s.get("created_at") or s.get("date") or "—")[:10],
            s.get("signal", "?"), s.get("action", "?"), _fmt(s.get("confidence")),
            len(g), sum(1 for x in g if x.get("status") == "pending")))
    return "\n".join(L) + "\n"


def _write_if_changed(path, text):
    try:
        if os.path.exists(path) and _read(path) == text:
            return
    except (OSError, ValueError):
        pass  # 旧索引损坏/不可读：视为有差异直接覆盖，坏索引须能被重建自愈
    _write_atomic(path, text)


def rebuild_indexes(reports_dir, signals, names=None):
    """整体重建 cn/hk 各股 index.md 与总览；身份不合规（如旧 4 位港码）的信号
    不进索引（迁移 dry-run 告警）。names=显示名缓存（report 写穿 names.json），
    存量信号（无 stock_name）经缓存显名。同输入字节相同，未变不重写。"""
    live = []
    for s in signals:
        if s.get("snapshot"):
            # 快照登记信号：市场推导后身份是 (cn/hk, 归一码)，但报告在 _snapshot/——
            # 不进实盘 index/总览（市场推导引入前以 market='?' 天然排除，推导后须显式排除）
            continue
        try:
            d = stock_dir(reports_dir, s.get("market"), s.get("code"))
        except ValueError:
            continue
        if s.get("market") in MARKETS:
            live.append((d, s))
    if not live:
        return
    by_dir = {}
    for d, s in live:
        by_dir.setdefault(d, []).append(s)
    for d, group in by_dir.items():
        _write_if_changed(os.path.join(d, "index.md"),
                          render_stock_index(group, group[0]["market"],
                                             group[0]["code"], names))
    _write_if_changed(os.path.join(reports_dir, "index.md"),
                      render_root_index([s for _, s in live], names))


# ---------------------------------------------------------------- 存量迁移

def _ts(s):
    """认领信号的 created_at；缺失/非 ISO 视为不可用（None，不参与认领）。
    带时区形态先转本地再摘 tzinfo——mtime 是本地 naive，直接相减会抛
    TypeError，只 replace 不换时区则偏移量错算。"""
    t = s.get("created_at")
    if not isinstance(t, str):
        return None
    try:
        t = dt.datetime.fromisoformat(t)
    except ValueError:
        return None
    # is not None 而非真值：零偏移（+00:00/Z）utcoffset() 是 timedelta(0)，
    # 按真值判会把 aware 原样放行，与 naive mtime 相减仍抛 TypeError
    return t.astimezone().replace(tzinfo=None) if t.utcoffset() is not None else t


def plan_migration(reports_dir, signals):
    """扫描 reports/ 顶层平铺 <code>-<date>.md，按 report_id（= 文件名主干，迁移
    不改）认领信号，还原单日多版本：与 mtime 同刻（≤2s）的最后一条为内容版，
    其余为丢失版。纯函数（只读文件系统）。"""
    plan = {"items": [], "unmatched": [], "warnings": []}
    if not os.path.isdir(reports_dir):
        return plan
    claimed = set()
    for name in sorted(os.listdir(reports_dir)):
        old = os.path.join(reports_dir, name)
        if not os.path.isfile(old) or name.startswith(".") or name == "index.md":
            continue
        m = LEGACY_RE.match(name)
        if not m:
            plan["unmatched"].append(name)
            continue
        stem, date = name[:-3], m.group(2)
        owners = sorted((s for s in signals if s.get("report_id") == stem),
                        key=lambda s: (s.get("created_at") or "", s.get("id") or ""))
        markets = {s.get("market") for s in owners}
        try:
            if markets == {"?"}:
                # 快照主干读时归一（与写侧 stock_code 同口径）：hk00700/0700.HK
                # 等历史形态统一进 _snapshot/<规范码>，不可识别原样交形态校验
                try:
                    code = fx.detect_market(m.group(1))[1]
                except SystemExit:
                    code = m.group(1)
                market = "?"
            else:
                market, code = fx.detect_market(m.group(1))
            sdir = stock_dir(reports_dir, market, code)
        except (SystemExit, ValueError):
            plan["unmatched"].append(name)
            continue
        item = {"name": name, "old": old, "new": os.path.join(sdir, date + ".md"),
                "status": "new", "anomaly": "", "updates": {}, "versions": []}
        plan["items"].append(item)
        if len(markets) > 1 or (markets and markets != {"?"} and market not in markets):
            item["status"], item["anomaly"] = "conflict", "认领信号市场不一致：%s" % sorted(
                map(str, markets))
            continue
        if item["new"] in claimed:
            item["status"], item["anomaly"] = "conflict", "目标与另一平铺文件重合"
            continue
        claimed.add(item["new"])
        mtime = dt.datetime.fromtimestamp(os.stat(old).st_mtime).replace(microsecond=0)
        owner = None
        for s in owners:
            t = _ts(s)
            if t is not None and abs((t - mtime).total_seconds()) <= OWNER_TOLERANCE_S:
                owner = s
        usable = [s for s in owners if _ts(s) is not None]
        for s in owners:
            if _ts(s) is None:
                plan["warnings"].append("%s 缺可用 created_at，跳过认领（不改写）"
                                        % s.get("id"))
        if owner is None and usable:
            # mtime 漂移（备份恢复/编辑器重存）：分级布局前平铺是最后写者胜，回退按
            # 最后一次运行归属内容版，避免把当日全部信号误标丢失
            owner = max(usable, key=_ts)
            item["anomaly"] = "mtime %s 与任何信号不同刻，按最后运行归属内容版" \
                % mtime.isoformat()
        elif owner is None:
            item["anomaly"] = "无可用信号与文件 mtime %s 同刻，内容版不归属任何信号" \
                % mtime.isoformat()
        if mtime.date().isoformat() != date:
            item["anomaly"] = (item["anomaly"] + "；" if item["anomaly"] else "") + \
                "mtime 日期与文件名日期不符"
        sections, footer = split_report(_read(old))
        if not sections:
            # 零节头＝非本工具产物/截断文件（render_report 恒写「## 结论」）：
            # 与 append_version 拒绝零版本头对称，不生成空壳单日文件（否则正文
            # 静默消失且 report_lost 不置位），原文件原地不动、信号不改写
            item["status"], item["anomaly"] = "conflict", "无可解析节头，原样跳过"
            claimed.discard(item["new"])  # 不占位：同目标的合法文件仍可认领
            continue
        entries = [(_ts(s), s, None) for s in usable if s is not owner]
        entries.append((_ts(owner) if owner else mtime, owner, sections))
        entries.sort(key=lambda e: (e[0], e[2] is not None))
        versions = []
        for n, (t, s, secs) in enumerate(entries, 1):
            versions.append({"n": n, "time": t.strftime("%H:%M:%S"), "sections": secs})
            if s is not None:
                upd = {"report_path": item["new"], "report_version": n}
                if secs is None:
                    upd["report_lost"] = True
                item["updates"][s["id"]] = upd
        item["versions"] = versions
        item["text"] = compose_day(day_title(os.path.basename(sdir), date), versions, footer)
        if os.path.exists(item["new"]):
            item["status"] = "done" if _read(item["new"]) == item["text"] else "conflict"
            if item["status"] == "conflict":
                item["anomaly"] = "目标已存在且内容不同"
    for s in signals:
        if s.get("market") == "hk" and not CODE_RE["hk"].fullmatch(str(s.get("code"))):
            plan["warnings"].append("%s 港股代码 %r 非 5 位规范形态，不进索引（不改写）"
                                    % (s.get("id"), s.get("code")))
    return plan


def signals_digest(path):
    if not os.path.exists(path):
        return None
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def apply_migration(reports_dir, signals_path, plan, base_digest, now):
    """按 plan 执行（每步可重入）：①写单日文件 ②CAS 后备份并改写信号指针
    ③原平铺文件移入 _legacy/（归档不删）④重建索引。signals.json 在 plan 之后
    被改动则中止（RuntimeError），零写入。"""
    if signals_digest(signals_path) != base_digest:
        raise RuntimeError("signals.json 在预览后被改动，迁移中止；请重跑")
    go = [it for it in plan["items"] if it["status"] in ("new", "done")]
    for it in go:
        if it["status"] == "new":
            _write_atomic(it["new"], it["text"])
    signals = load_signals(signals_path)
    updates = {sid: u for it in go for sid, u in it["updates"].items()}
    changed = False
    for s in signals:
        for k, v in updates.get(s.get("id"), {}).items():
            if s.get(k) != v:
                s[k], changed = v, True
    backup = None
    if changed:
        if signals_digest(signals_path) != base_digest:
            raise RuntimeError("signals.json 在迁移中被改动，指针未改写；请重跑")
        backup = "%s.bak-%s" % (signals_path, now.strftime("%Y%m%d%H%M%S"))
        with open(signals_path, "rb") as src, open(backup, "xb") as dst:
            dst.write(src.read())
        write_json_atomic(signals_path, signals)
    moved, skipped = [], []
    legacy = os.path.join(reports_dir, "_legacy")
    for it in go:
        if not os.path.exists(it["old"]):
            continue
        dst = os.path.join(legacy, it["name"])
        if os.path.exists(dst):
            skipped.append(it["name"])
            continue
        os.makedirs(legacy, exist_ok=True)
        os.replace(it["old"], dst)
        moved.append(it["name"])
    index_warn = None
    try:  # 派生视图放最后：挂了不吞迁移主流程（①-③已落盘），只告警带回
        rebuild_indexes(reports_dir, signals,
                        load_names(os.path.dirname(signals_path)))
    except (OSError, ValueError) as e:
        index_warn = str(e)
    return {"backup": backup, "moved": moved, "skipped": skipped,
            "signals_changed": changed, "index_warn": index_warn}


def migration_lines(plan):
    L = []
    for it in plan["items"]:
        L.append("%-8s %s -> %s" % (it["status"], it["name"], it["new"]))
        for v in it["versions"]:
            sid = next((k for k, u in it["updates"].items()
                        if u["report_version"] == v["n"]), "—")
            L.append("         v%d · %s %s %s" % (
                v["n"], v["time"], "丢失" if v["sections"] is None else "内容", sid))
        if it["anomaly"]:
            L.append("         ! %s" % it["anomaly"])
    for name in plan["unmatched"]:
        L.append("skip     %s（非平铺报告命名，原地不动）" % name)
    for w in plan["warnings"]:
        L.append("warn     %s" % w)
    return L
