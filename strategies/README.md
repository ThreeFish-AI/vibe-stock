# 策略库

每个策略一个 YAML「说明书」：声明元数据（name/category/priority/market_regimes/
aliases/required_evidence），正文 `instructions` 是写给模型读的自然语言交易逻辑。
结构与形态借鉴 ZhuLinsen/daily_stock_analysis 的 strategies/（MIT），判据口径按
vibe-stock 证据包（evidence.json 的 blocks/technical 字段）重写。

## 使用与扩展

- 产出意见：策略按 instructions 对证据包出一条意见
  `{source: "strategy:<name>", signal: 五标准信号, confidence, rationale}`，
  过 [adjudicate.py](../scripts/adjudicate.py) 信号资格分选——表外写法一律判无效
  进诊断记录，不进意见链（规约见 [references/02](../references/02-strategies.md)）。
- 自定义：新策略按同结构放本目录即可被加载；同名时用户策略优先（YAML 加载器
  按目录序后者覆盖）。策略即数据——改说明书等于改策略，无需改代码。
- required_evidence 中的块缺失时，策略应在 rationale 注明证据缺失并降置信，
  而非假装看得到（八态规约见 [references/01](../references/01-evidence.md)）。
- 绩效反馈：每条意见的 source 会进入 [后验台账](../references/05-postmortem.md)，
  命中率影响该策略下次聚合权重（绩效因子，Beta(15,15) 收缩、钳 0.83–1.2）。
