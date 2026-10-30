# evals · 合成样例与黄金样本

- `fixture/snapshot/`：快照模式合成数据（60 根上行日 K + 一条示例新闻；
  另含 forecast/moneyflow/notices 三件扩展块快照——扩展块文件可选，缺失=missing
  如实标注）——`diagnose.py prepare --stock 600519 --snapshot-dir evals/fixture/snapshot`。
- `golden/`：验票-聚合-RiskGuard 黄金样本（evidence/opinions/risk → 期望 verdict）。
  断言要点：置信收缩加权分 3.48 → hold（hold 同族置信 0.63）——veto 只压买入族，
  初判 hold 时无从触达（RiskGuard no-op）；0.85 strong_buy 与主信号 hold 隔 2 档
  构成 high_conf_dissent（medium），另置信离散（medium）、共识 medium；快照
  质量分 good；零权重样本——扩展块 moneyflow=available/valuation=fetch_failed
  不扰动 verdict 与 quality（零权重钉）。
- 回归执法：`scripts/adjudicate.py --selftest`、`scripts/diagnose.py --selftest`、
  `scripts/postmortem.py --selftest` 三件全绿是提交前置（AGENTS.md）。
