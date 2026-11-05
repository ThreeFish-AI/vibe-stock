# 策略库

每个策略一个 YAML「说明书」：声明元数据（name/category/priority/market_regimes/aliases/required_evidence/profile），正文 `instructions` 是写给模型读的自然语言交易逻辑。结构与形态借鉴 ZhuLinsen/daily_stock_analysis 的 strategies/（MIT），判据口径按 vibe-stock 证据包（evidence.json 的 blocks/technical 字段）重写。

## 期限轨（profile）

- `profile` 缺省 = `default`（短线轨：读全部证据出意见进 opinions.json，T+1/3/5/10 后验）；`profile: position`（中线轨：只写进 opinions.position.json，T+20/60/120 后验、仅 T+60 记分，置信上限 0.65，台账 ledger.position.json——规约见 [references/08](../references/08-midterm.md) 与 [references/05](../references/05-postmortem.md)「期限轨」）。
- 短线意见生产时只读 default 策略；中线意见只读 position 策略——两轨意见不混写（裁决器各跑一次，见 [SKILL.md](../SKILL.md) 工作流）。

## 使用与扩展

- 产出意见：策略按 instructions 对证据包出一条意见 `{source: "strategy:<name>", signal: 五标准信号, confidence, rationale}`，过 [adjudicate.py](../scripts/adjudicate.py) 信号资格分选——表外写法一律判无效进诊断记录，不进意见链（规约见 [references/02](../references/02-strategies.md)）。
- 自定义：新策略按同结构放本目录即可被加载；同名时用户策略优先（YAML 加载器按目录序后者覆盖）。策略即数据——改说明书等于改策略，无需改代码。
- required_evidence 中的块缺失时，策略应在 rationale 注明证据缺失并降置信，而非假装看得到（八态规约见 [references/01](../references/01-evidence.md)）。
- 绩效反馈：每条意见的 source 会进入 [后验台账](../references/05-postmortem.md)，命中率影响该策略下次聚合权重（绩效因子，Beta(15,15) 收缩、钳 0.83–1.2）。
