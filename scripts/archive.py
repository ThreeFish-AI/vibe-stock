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


def render_stock_index(signals, market, code):
    dirname = "%s.%s" % (code, market)
    rows = [s for s in signals if s.get("market") == market and s.get("code") == code]
    L = ["# %s · 诊股时间线" % dirname, "", INDEX_NOTE, "",
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


def render_root_index(signals):
    groups = {}
    for s in signals:
        groups.setdefault((s.get("market"), s.get("code")), []).append(s)
    latest = sorted(((_ordered(g)[0], g) for g in groups.values()),
                    key=lambda x: (x[0].get("created_at") or "", x[0].get("id") or ""),
                    reverse=True)
    L = ["# 诊股总览", "", INDEX_NOTE, "",
         "| 股票 | 最新日期 | 最新信号→动作 | 置信 | 诊断次数 | pending |",
         "| --- | --- | --- | --- | --- | --- |"]
    for s, g in latest:
        dirname = "%s.%s" % (s["code"], s["market"])
        L.append("| [%s](%s/index.md) | %s | %s→%s | %s | %d | %d |" % (
            dirname, dirname, (s.get("created_at") or s.get("date") or "—")[:10],
            s.get("signal", "?"), s.get("action", "?"), _fmt(s.get("confidence")),
            len(g), sum(1 for x in g if x.get("status") == "pending")))
    return "\n".join(L) + "\n"


def _write_if_changed(path, text):
    if os.path.exists(path) and _read(path) == text:
        return
    _write_atomic(path, text)


def rebuild_indexes(reports_dir, signals):
    """整体重建 cn/hk 各股 index.md 与总览；身份不合规（如旧 4 位港码）的信号
    不进索引（迁移 dry-run 告警）。同输入字节相同，未变不重写。"""
    live = []
    for s in signals:
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
                          render_stock_index(group, group[0]["market"], group[0]["code"]))
    _write_if_changed(os.path.join(reports_dir, "index.md"),
                      render_root_index([s for _, s in live]))


# ---------------------------------------------------------------- 存量迁移

def _ts(s):
    """认领信号的 created_at；缺失/非 ISO 视为不可用（None，不参与认领）。"""
    t = s.get("created_at")
    return dt.datetime.fromisoformat(t) if isinstance(t, str) else None


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
                market, code = "?", m.group(1)
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
            # mtime 漂移（备份恢复/编辑器重存）：0.2.0 平铺是最后写者胜，回退按
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
    rebuild_indexes(reports_dir, signals)
    return {"backup": backup, "moved": moved, "skipped": skipped,
            "signals_changed": changed}


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
