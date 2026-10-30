# 04 · 决策报告（模板与渲染口径）

渲染实现：[scripts/diagnose.py](../scripts/diagnose.py) `render_report`
（结构以实现为准，本文件讲规则）；输出 `~/.vibe-stock/reports/<code>-<date>.md`。

## 结构（结论先行）

1. **结论**：最终信号 + 置信 + 共识等级 + 可执行与否 + 一句理由摘要 +
   完整裁决链（聚合初判 → RiskGuard 各步 → 置信帽）+ 分歧概览 + 意见分布。
   理由摘要支撑终裁信号（RiskGuard 与置信帽之后的 final）。条件：结论句挂
   理由时；做法：终裁≠初判且由 RiskGuard 改判 → 优先挂 risk.json.rationale 摘要
   并注明「初判 X 经 RiskGuard 改判为 Y」；否则取与终裁同信号（其次同方向族）的
   最高置信意见 rationale，置信帽压档（strong_*→buy/sell）时径取同方向族；都
   没有则不挂（不硬凑）；坑位：按聚合初判选理由会在 RiskGuard 改判后挂出与终裁
   反向的意见（sell 结论配 hold 理由）。
2. **证据状态**：全部块状态/来源表（核心六块标权重、扩展九块标 0 分）——
   缺失可见落在产品面；forecast/unlock 有数据时附「近期事件」（披露日历/
   解禁批次）。
3. **关键价位**：现价 / 20 日高低 / MA20 / 参考买点 / 止损 / 目标。盘中取数时
   现价注明「（盘中价）」，取数时段口径见 [01 · 盘中口径](01-evidence.md#盘中口径未完成-k-线)。
4. **风险与利好**：逐条挂反对意见与支持意见的 rationale（有据可查）。条件：
   `report` 渲染（读 workdir 的 opinions.json 与 risk.json）；做法：风险栏=卖出族
   意见 + 风险角色 risk.json.rationale（标注 veto/downgrade 触发态），利好栏=买入族
   意见，逐条带 source 与 signal/置信，空栏如实写「（无登记）」；rationale 的 SSOT
   是 opinions.json（verdict.valid_opinions 只存四键），按 source 接回且只挂过验票
   门的意见（`partition` 同一判据）；坑位：按 source 集合朴素过滤会把同 source
   表外写法意见的 rationale 混挂进来。
5. **操作建议**：空仓者与持仓者分开、按最终信号给纪律性动作（不追高/止损位）。
6. **检查清单**：核心证据齐备 / 无高严重度分歧 / 置信 ≥0.5 / 未偏离 MA20 过远
   ——未通过项如实打叉，检查没过照样出报告，但结论停在保守档。
7. **附**：各意见（含绩效因子加权，附 rationale 原文）与诊断记录。
8. **免责段**（无条件全局规则：金融用途安全边界）——固定文案见 DISCLAIMER，
   任何报告不得省略。

## 规约

- 每个判断可溯源：结论句引用意见 rationale，意见引用证据块数值。RiskGuard
  改判时结论句引用 risk.json.rationale（选取规则见上文结构第 1 条）。
- 报告不复述哨兵原文；新闻只以事实转述进风险/利好。rationale 是 LLM 产出、
  可入报告，入报告前剥哨兵标记、尖括号转全角并折成单行。
- 可执行门槛：buy 族登记为可执行建议须置信 ≥0.5（CONFIDENCE_GATE），
   否则降为 watch 并注明。
