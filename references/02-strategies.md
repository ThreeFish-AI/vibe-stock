# 02 · 策略层：说明书形态与信号资格分选（SSOT）

策略库在 [strategies/](../strategies/)；执法在 [scripts/adjudicate.py](../scripts/adjudicate.py)
（`partition`）。

## 五个标准信号（唯一合法输出词）

`strong_buy / buy / hold / sell / strong_sell`

别名归一表（收英文变体与本表中文交易术语；**表外自由文本一律判无效**）：
strong buy / strong-buy / strongbuy / 加仓买入 → strong_buy；buy / long / 买入 /
增持 → buy；hold / neutral / 持有 / 观望 → hold；sell / short / 卖出 / 减持 →
sell；strong sell / 清仓卖出 → strong_sell。

## 验票门（互斥且穷尽）

每个意见（角色与策略一视同仁）恰好落进二者之一：

- **过门** → 进意见链参与聚合；
- **不过门**（表外信号 / 置信出界）→ 移入诊断记录留档，**绝不进意见链**、
  不静默删除、不修正为中性。

条件：所有外来意见（策略 YAML、自定义策略）；做法：代码执法（partition）；
坑位：LLM 产意见必须写五标准信号**原词**——「看多!!!」「大概能买」这类表达
会整条进诊断，等于该策略本轮弃权（这是特性不是 bug：先保证进门的可计算，
再谈观点对错）。

## 角色 vs 策略的待遇

- 内置三角色（技术 / 情报 / 风险）与策略意见走**同一道验票门**；差异在
  角色还能给 risk.json（veto / downgrade / severity 建议，供 RiskGuard 消费）。
- 策略说明书 = 数据：`name/display_name/category/required_evidence/aliases/
  default_priority/market_regimes` + `instructions`（自然语言交易逻辑）。
  required_evidence 的块缺失时策略须降置信并注明，不得假装看得到。
- 量能类判据（vol_ratio_5 / vol_series_10）在 context-pack 头部出现盘中警示行
  时，以外推值 `vol_ratio_5_projected`（estimated）或收盘后复核为准——盘中末根
  为未完成 K 线，YAML 阈值直接消费会假缩量/假放量（规约见
  [01 · 盘中口径](01-evidence.md#盘中口径未完成-k-线)）。
- 扩展事件块按事件方向分流：**风险向事件**（业绩预亏/首亏、大比例解禁临近、
  减持类公告）走**风险角色 risk.json 通道**（veto/downgrade 线索，非对称闸门
  只降不升），不在投票策略出方向票；**正向催化**（业绩预增、回购、重大合同、
  政策利好）可入 event_driven 事件策略；中性场景（披露日历等）不贡献噪音票。
- **基本面锚只作风险线索**（条件：`--cost` 触发 lens 后风险角色评估时）：
  做法：透镜「支撑不足」形态（参考价高于共识最高目标，且隐含 PE 分位 >90
  或高于 p90 带）只作为 risk.json downgrade 线索移交风险角色，永不提供升档
  通道、不投方向票、不进 ledger 绩效归因；坑位：透镜三档是 12 个月量级的中
  长期参考，勿当短线信号消费，也勿把「中性」当利空、把 abstain 当看空。
