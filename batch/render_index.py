#!/usr/bin/env python3
"""主报告 index.md 渲染器：所有数字从 SSOT 派生（stageC/ranking.json、
portfolio/allocation.json、midtier.jsonl、stageA/fetch_log.json、
portfolio/checks.txt），叙述为模板常量。重跑即重建，勿手改产物。

用法：uv run --no-project <sk>/batch/render_index.py --scan-root <scan_root> \\
  --pool hs300 [--skill-dir <sk>]
"""
import argparse
import csv
import json
import os
import sys
from decimal import ROUND_HALF_UP, Decimal

BUY = ("strong_buy", "buy")
POOL_NAME = {"hs300": "沪深300"}


def pct1(cost, budget):
    """权重百分比一位小数，按金额精确四舍五入（避开 0.1025 的浮点舍入偏差）。"""
    return str((Decimal(str(cost)) * 100 / Decimal(str(budget)))
               .quantize(Decimal("0.1"), ROUND_HALF_UP))


def load(scan_root, rel):
    with open(os.path.join(scan_root, rel), encoding="utf-8") as f:
        return json.load(f)


def main():
    ap = argparse.ArgumentParser(description="批量主报告渲染器（重跑即重建）")
    ap.add_argument("--scan-root", required=True, help="批量运行根目录")
    ap.add_argument("--top-n", type=int, default=30, help="Stage A 入选数（文件名拼接）")
    ap.add_argument("--shortlist-n", type=int, default=10, help="最终精选数")
    ap.add_argument("--pool", default="hs300", help="池名（标题用）")
    ap.add_argument("--skill-dir", default=os.path.expanduser(
        "~/.claude/skills/vibe-stock"), help="skill 根目录（复盘命令渲染用）")
    a = ap.parse_args()
    pool_name = POOL_NAME.get(a.pool, a.pool)
    sys.path.insert(0, os.path.join(a.skill_dir, "scripts"))
    import archive as ar  # noqa: PLC0415  个股目录布局唯一定义处

    reports = os.path.dirname(os.path.dirname(os.path.abspath(a.scan_root)))

    def link(code):
        """个股时间线相对链接：布局取 archive.stock_dir（SSOT），不硬编码。"""
        d = ar.stock_dir(reports, "cn", code)
        return "[%s](%s)" % (code, os.path.relpath(os.path.join(d, "index.md"), a.scan_root))

    rk = load(a.scan_root, "stageC/ranking.json")
    alloc = load(a.scan_root, "portfolio/allocation.json")
    fl = load(a.scan_root, "stageA/fetch_log.json")
    with open(os.path.join(a.scan_root, "midtier.jsonl"), encoding="utf-8") as f:
        mid = {r["code"]: r for r in map(json.loads, f)}
    with open(os.path.join(a.scan_root, "stageA", f"screen_top{a.top_n}.csv"),
              encoding="utf-8-sig") as f:
        n_ind = len({r["industry"] for r in csv.DictReader(f)})
    with open(os.path.join(a.scan_root, "portfolio", "checks.txt"), encoding="utf-8") as f:
        checks = [ln.split(" | ")[0] for ln in f if ln.strip()]

    ranking = rk["ranking"]
    rows = sorted(alloc["rows"], key=lambda r: r["rank"])
    allm = list(mid.values())
    n_buy_initial = sum(r["initial"] in BUY for r in allm)
    n_buy_final = sum(r["final"] in BUY for r in allm)
    g1 = next((r["gate_fail"][len("G1_not_"):] for r in allm
               if (r.get("gate_fail") or "").startswith("G1_not_")), "strict")
    alt = [r for r in allm if not r.get("gate_fail") and not r.get("shortlisted")]
    penal = [r for r in ranking if r["penalty"] < 1]
    n_hard = sum(bool(v.get("hard_falsified")) for v in rk["verifiers"].values())
    ws = [r["w_actual"] for r in rows]
    max_loss = sum(r["lots"] * 100 * (r["price"] - r["stop"]) for r in rows)
    tiers = sorted({r["evidence_tier"] for r in allm})
    n_unknown_ind = sum(r["industry"] == "未知" for r in allm)
    budget = alloc["budget"]

    L = [
        f"# A 股{pool_name} 批量诊断 · TOP{a.shortlist_n} 投资价值排名与配置方案", "",
        f"> 数据基准日：{fl.get('date')} · 管线：vibe-stock 五段流水线 × "
        f"{a.top_n} 只批量编排（references/06-batch-scan.md）",
        "> 由 [stageC/ranking.json](stageC/ranking.json)、"
        "[portfolio/allocation.json](portfolio/allocation.json)、"
        "[midtier.jsonl](midtier.jsonl) 派生："
        "`uv run --no-project bin/render_index.py` 重建，勿手改。",
        ">",
        "> **免责声明：本报告仅供学习与研究参考，不构成投资建议。系统不下单、"
        "不保证收益。数据可能缺失或滞后。**", "",
        f"## 一、投资价值排名（Top{a.shortlist_n}）", "",
        "综合分 = 0.30×聚合分归一 + 0.70×三 lens 均分归一；对抗核验反驳度 ≥0.7 "
        "者 ×0.85（只降不升）。", "",
        "| 排名 | 代码 | 名称 | 行业 | 初判¹ | 终裁 | 聚合分 | 反驳度 | 综合分 |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for r in ranking:
        m = mid[r["code"]]
        sig = m["initial"]
        L.append("| %d | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            r["rank"], link(r["code"]), r["name"], m["industry"], sig, m["final"],
            r.get("score") if r.get("score") is not None else "-",
            r["refuted"] if r["refuted"] is not None else "-",
            "%.3f" % r["final_score"]))
    L += [
        "",
        "¹ 聚合初判（aggregate.final_signal）与聚合分为 vibe-stock ≥0.2.1 管线口径"
        "（置信收缩加权分，信号档位进分）；终裁含 RiskGuard 只降不升与置信帽。"
        "意见 rationale 以 `vs/<code>/opinions.json` 为准。", "",
        "### 为何值此名次", "",
    ]
    for r in ranking:
        L.append("%d. **%s %s**：%s" % (r["rank"], r["code"], r["name"], r["why"]))
    L += [
        "", f"## 二、配置方案（满仓 {len(rows)} 只，信心度加权，行业 ≤2）", "",
        "仓位 = 综合分归一 × 手数贴合（100 股/手，单仓带 [%.1f%%, %.1f%%]，预算贴合 "
        "greedy），现金残留 ¥%s。" % (alloc["w_band"][0] * 100, alloc["w_band"][1] * 100,
                                     format(alloc["cash_left"], ",.0f")), "",
        "| 排名 | 代码 | 名称 | 现价 | 手数 | 金额 | 权重 | 止损² | 参考买点 | 目标1³ | 建仓 T1/T2/T3⁴ |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        t = r["tranches"]
        tr = "%d/%d/%d" % (t["T1_open"], t["T2_limit_entryref"], t["T3_trigger"])
        L.append("| %d | %s | %s | %.2f | %d | ¥%s | %s%% | %.2f | %.2f | %.2f | %s%s |" % (
            r["rank"], link(r["code"]), r["name"], r["price"], r["lots"],
            format(r["cost"], ",.0f"), pct1(r["cost"], budget), r["stop"],
            r["entry_ref"], r["target1"] if r["target1"] else 0, tr,
            "⁵" if r["lots"] == 1 else ""))
    L += [
        "",
        "² 止损 = max(−5% 线, 0.99×20 日低) 取紧者；³ 目标1 = 20 日高，+15% 后改 "
        "trailing（收盘破 MA20 离场）；⁴ T1 次日开盘（跳空 >+2% 等回落）、"
        "T2 限价=参考买点（10 日 GTC）、T3 触发站上目标1 或回踩 MA20±1%（20 日），"
        "未触发按收盘补足；⁵ 单手股单段建满。", "",
        "**纪律**：单仓 >16% 次日减至 ≤14%；止损/止盈触发后资金留存不追补；"
        "每 10 个交易日跑一次 postmortem 复盘（见 §五）；指数收盘破 MA60 → "
        "全组合降档评估。", "",
        "**组合级风险**：%d 只止损同时打穿的最大亏损 ¥%s（%.1f%%，不含跳空缺口）；"
        "行业敞口 ≤ 2×%.1f%% = %.1f%%；%d 只均为%s成分、内部相关性高，这是"
        "**系统性 β 暴露而非分散化**。%s %d 只带 0.85 降权（对抗核验反驳 ≥0.7），"
        "仓位与预期收益应相应下调看待。"
        % (len(rows), format(max_loss, ",.0f"), max_loss / budget * 100,
           alloc["w_band"][1] * 100, alloc["w_band"][1] * 2 * 100, len(rows),
           pool_name, "/".join(r["name"] for r in penal), len(penal)), "",
        "## 三、方法链路（可审计）", "",
        "- **Stage A 粗筛（%d→%d）**：csindex 官方成分+权重 → 全市场快照（`%s`）"
        "→ 业绩表 primary %s 覆盖 %d/%d、secondary 兜底 %d 并逐股标记期间"
        "（period_used，ROE 累计年化折算）→ 均衡复合分（质量 .25/成长 .25/"
        "价值 .25/动量 .10/稳定 .15）→ 硬过滤（价格可配、流动性下限）→ 行业帽 %d "
        "选 %d（%d 个行业）。明细见 [stageA/screen_report.md](stageA/screen_report.md)。"
        % (fl.get("pool_size", a.top_n), a.top_n, fl["spot_source"], fl["periods"][0],
           fl["primary_coverage"], fl.get("pool_size", 300), fl["secondary_backfill"],
           3, a.top_n, n_ind),
        "- **Stage B 全管线诊断（%d/%d）**：每股 15 证据块（取数状态见 "
        "[vs/_fetch_matrix.md](vs/_fetch_matrix.md)，证据档位 %s）→ 每股一 agent "
        "出意见板（每策略一条+三角色各一条）→ 确定性裁决（≥0.2.1 聚合口径，"
        "初判买入族 %d 只、终裁买入族 %d 只）。"
        % (len(allm), a.top_n, "/".join(tiers), n_buy_initial, n_buy_final),
        "- **Stage C 深评**：门限 G1–G5（G1 采用档 `%s`%s）→ %d 只对抗核验 → "
        "三 lens 独立评审 → 确定性合分；硬证伪 %d 只，降权 %d 只。"
        % (g1, "，候补：" + "、".join("%s %s" % (r["code"], r["score"]) for r in alt)
           if alt else "", a.shortlist_n, n_hard, len(penal)),
        "- **Stage D**：确定性手数贴合 + %d 项一致性校验（PASS %d / FAIL %d；"
        "权重和 %.2f%% + 现金 %.2f%%、单仓 ∈[%.1f%%, %.1f%%]）。见 "
        "[portfolio/checks.txt](portfolio/checks.txt)。"
        % (len(checks), checks.count("PASS"), checks.count("FAIL"), sum(ws) * 100,
           alloc["cash_left"] / budget * 100, min(ws) * 100, max(ws) * 100),
        "- 个股报告与信号时间线：上表代码列直达各股 `index.md`（登记结果以 "
        "`~/.vibe-stock/signals.json` 为准）；意见 rationale 以 "
        "`vs/<code>/opinions.json` 为准。", "",
        "## 四、已知降级", "",
    ]
    degrade = []
    if "qt_fill" in fl.get("spot_source", ""):
        degrade.append("快照主源限流 → 新浪+腾讯 qt 双源替代（PE/PB 为 qt 口径，"
                       "fetch_log 已标注）；")
    if fl.get("momentum_neutralized"):
        degrade.append("动量因子因 60 日涨幅字段缺失，池内中性化（0.3）%d 只，"
                       "由 Stage B 技术块在个股层补足；" % fl["momentum_neutralized"])
    if fl.get("secondary_backfill"):
        degrade.append("最近业绩期披露进行中，%d 只由上期兜底——`stageA/universe.csv` "
                       "的 period_used 列逐股标记；" % fl["secondary_backfill"])
    if n_unknown_ind:
        degrade.append("%d 只行业字段缺失归「未知」桶，行业帽按桶生效；" % n_unknown_ind)
    L += [f"{i+1}. {d.rstrip(';')}；" for i, d in enumerate(degrade)] or ["无。"]
    L += [
        "", "## 五、复盘钩子", "",
        f"TOP{a.shortlist_n} 信号已登记在 `~/.vibe-stock/signals.json`"
        "（horizons 1/3/5/10 交易日），复盘：", "",
        "```bash",
        "uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \\",
        "  %s/scripts/postmortem.py" % a.skill_dir,
        "```", "",
        "## 六、产物索引（每项为唯一事实源）", "",
        "- 粗筛：[stageA/universe.csv](stageA/universe.csv)（全池因子表）、"
        "[stageA/raw/](stageA/raw/)（原始取数）、[stageA/fetch_log.json](stageA/fetch_log.json)",
        f"- 诊断：`vs/<code>/` 五件套 ×{a.top_n}（evidence / context-pack / opinions / "
        "risk / verdict）",
        "- 中 tier：[midtier.jsonl](midtier.jsonl)（含 `shortlisted` 标记；"
        "[midtier_table.md](midtier_table.md) 为其可读视图）",
        "- 深评：[stageC/ranking.json](stageC/ranking.json)（排名、三 lens 子分、"
        "核验反驳明细）；深评输入摘要按需派生："
        "`uv run --no-project bin/digest.py --scan-root <scan_root> <code>`",
        "- 组合：[portfolio/allocation.json](portfolio/allocation.json)、"
        "[portfolio/checks.txt](portfolio/checks.txt)",
        "- 复现脚本：[bin/](bin/)；批量总览：`~/.vibe-stock/reports/_scans/`",
    ]
    with open(os.path.join(a.scan_root, "index.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(L) + "\n")
    print("index.md rendered:", len(L), "lines")


if __name__ == "__main__":
    main()
