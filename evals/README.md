# evals · 合成样例与黄金样本

- `fixture/snapshot/`：快照模式合成数据（60 根上行日 K + 一条示例新闻）——
  `diagnose.py prepare --stock 600519 --snapshot-dir evals/fixture/snapshot`。
- `golden/`：验票-聚合-RiskGuard 黄金样本（evidence/opinions/risk → 期望 verdict）。
  断言要点：加权分到 strong_buy 但被风险角色 veto 压 hold；0.9 高置信 hold 与
  strong_buy 隔 2 档构成 high_conf_dissent（medium）；快照质量分 good。
- 回归执法：`scripts/adjudicate.py --selftest`、`scripts/diagnose.py --selftest`、
  `scripts/postmortem.py --selftest` 三件全绿是提交前置（AGENTS.md）。
