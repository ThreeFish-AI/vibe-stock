# 09 · 持仓股加仓决策轨（add-on track）

> 适用对象：**已持有**（`~/.vibe-stock/portfolio.json` holdings 在册且数量 >0）的股票。
> 未持有者不适用本轨——买入候选的入口是 [06](06-batch-scan.md) 批量扫描，不是持仓重诊。
> 实现：`scripts/addon.py`（纯函数判据库 + `--selftest`），由 `diagnose.py report`
> 在双轨裁决后调用；裁决链（[03](03-synthesis.md)）零改动。

## 定位（与既有红线的关系）

- 加仓轨是**裁决链之外的确定性资格门**（编排算术，同 [06] Stage D 的
  portfolio.py 先例）：不进五信号聚合、不进置信帽、不改 RiskGuard、不投
  方向票。`action=add_on` 独立于 `ACTION_OF` 五信号映射——不是升档通道。
- 与 [02](02-strategies.md) 末条「永不提供升档通道」的关系：本轨不给任何
  股票的当日信号升档；它只在**信号族已经健康**（门 1 全绿）时对**持仓者**
  给出独立的加仓动作建议，空仓者建议仍由五信号驱动。
- 与 [03]「透镜不进裁决」红线的显式例外：lens 三档中的「**有支撑**（置信
  ≥medium）」在**门 2 逆势窄门**内作资格输入。这是本规约对 03 该节的一次
  显式修订（裁决链外的资格门不属「裁决环节」），已在 CHANGELOG 0.0.18 记录；
  除此一处外透镜输出仍不进任何判定。收紧/修订本例外属 minor 级语义变更。
- 汇率红线（[03]）沿用：门 3 包络不引入 HKD/CNY 换算（跨币种权重线留 P2，
  待裁定是否豁免汇率红线于仓位工程或引入恒定换算口径）。

## 门 1 · 资格冻结/解冻（只冻不升格）

任一命中即冻结（`frozen_reasons` 逐条落报告）：

| 判据 | 数值口径 | 冻结条件 |
|---|---|---|
| 短线卖族 | verdict.risk_guard.final | ∈ {sell, strong_sell} |
| 风险角色 | risk.json | veto 或 downgrade = true |
| 中线卖族 | verdict.position.risk_guard.final | ∈ {sell, strong_sell}（无中线裁决不冻结） |
| A-1 临近解禁（→08 ①-3） | `unlock.upcoming[].{date,ratio_pct}` | 未来 90 日历日（≈60 交易日近似）内 ratio_pct ≥3% |
| A-2 估值极端（→08 ②-4） | `valuation.{pe,pb}_percentile_5y` | 任一 >90（逐项缺失跳过） |
| A-3 EPS 90 日下修 | `research.consensus.eps_revision_90d.direction` | == "down" |
| A-4 两年翻倍警戒（→08 ②-7 收严实现） | `technical.mid_term.tsmom_250d` | > +100%（不要求 rv 抬升佐证，方向只收严） |
| A-5 当期亏损（新增，方向收严） | `fundamentals.归母净利润(亿元)` | < 0 |

- **缺证据口径**：块 `not_supported`（制度性无数据，如港股 unlock/forecast）
  或字段未接入（A 股 eps_revision_90d 现状=08 P4 backlog）→ 该判据 **skip 不
  冻结**并在 gate_detail 注记；块 available 但数值畸形 → 视同缺数据 skip
  （脏数据不开门也不崩栈）。A-3 接入后收严为「缺席即冻结」；A-5 在 fetch
  暴露多期 history 后收严为「连续 3 期亏损」——两条收严路径已预留。
- **解冻**：只能来自下一诊的信号族自然修复（非卖族且无 downgrade），无任何
  人工/判据升格通道——与 RiskGuard 只降不升对称的「只冻不升格」。

## 门 2 · 触发（策略买点在场，非情绪）

两轨任一全绿才触发（`trigger_blockers` 逐条落报告）：

- **顺势轨**（主轨，同时满足）：多头排列 `ma5>ma10>ma20` 且现价 ≥ ma20；
  `bull_trend` 或 `shrink_pullback` 在 valid_opinions 有 buy 族意见；**回踩在
  场**：距 20 日高回撤 ≥3% 或现价 ≤ ma10×1.02（防追高顶端）；rsi14 < 78
  （08 超买警戒）；现价高出 ma20 < 10%。
- **逆势窄门**（同时满足）：`quality_value` buy 族意见；lens「有支撑」且置信
  ≥medium；现价 < ma20（≥ma20 属顺势区，走顺势轨判据）；门 1 全绿（含 skip）。

**禁用理由**（无条件全局规则：加仓动作的 rationale 不得出现以下动机）：
摊薄成本 / 跌多了 / 回本心态。rationale 必须引用策略买点与证据字段——
加仓是一次独立的买入决策，不是亏损的会计处理。

## 门 3 · 手数与节奏（三段确认制）

- 单次上限：顺势 ≤ ⌊现仓/3⌋、逆势 ≤ ⌊现仓/6⌋，100 股向下取整；不足 1
  手（100 股）→ 现仓过小不拆批，不加。港股暂按 100 股取整，board lot
  贴合留 P2。
- **三段确认制**（执行态从 portfolio.json `operations` + signals 推导，
  不新增状态文件）：
  1. `idle` 门开触发 → 建议**首加 1/2 批**；add_ref：顺势=ma10~ma20 区间
     上沿（max(ma10, ma20)），逆势=触发日收盘；此建议登记 addon 信号
     （profile=addon，action=add_on，key_levels 附 add_ref/confirm_lo）。
  2. 首加成交（operations 出现信号日后的 buy）→ **T+3 确认窗**（≤5 日历
     日近似）：窗内最低收盘 ≥ add_ref×0.97 且不低于信号前 20 日低 → 建议
     **确认加**剩余；破线或创新低 → **撤销**：剩余批次不加，首加部分按当日
     短线信号处置。confirm/abort 是同段在途复核，**不重复登记**（不双计样本）。
  3. 确认加成交后进入冷却：**同票 60 日（日历近似）加仓信号 ≤2 条**，超出
     仅报告提示冷却。
- **包络**（汇率红线内）：加仓后新加权成本对现价浮亏 ≥15% → 禁再加
  （新加权成本在报告 envelope 块如实展示）。

## 产出与登记

- 报告「## 操作建议」持仓者分支**五档**：可加仓（轨道/手数上限/add_ref/
  确认与撤销条件）/ 持有（含「等回踩至 ma10~ma20」变体）/ 持有观察 /
  减仓 / 离场；冻结时维持信号档并附「加仓资格冻结」原因行。
- 报告新增「### 加仓评估（addon）」节：门 1 逐项 green/red/skip、阶段与
  建议、rationale——三道门逐项可溯源。
- signals.json：profile=`addon`、action=`add_on`、family=bull、horizons=
  T+1/3/5/10（[05] 短线带 ±2%）——**加仓建议照常进后验记分**（按 bull 族），
  台账归 `ledger.json`（与 default 同账本、同 sources 归因）；个股时间线
  索引表收 addon 行，总览「最新信号/诊断次数」列仍只算 default 轨（addon
  是持仓者辅助建议，不污染主信号语义）。
- portfolio.json 契约（[04]）不变：仓内**永不写回**持仓；加仓成交后由用户
  按 operations_schema 手维登记（先记 operations 再同步 holdings），下一诊
  的状态机自动消费。

## 门禁

- `uv run --no-project scripts/addon.py --selftest`：冻结族/缺证据 skip/
  触发族/手数取整/三段状态机/包络/破坏性实验（拿掉门 2 买点判据结论须
  翻转）全绿；与 scripts/ 四件同列提交前置（AGENTS.md）。
- 判据只许收严：放宽任一门槛须人工评审并在 CHANGELOG 记录（AGENTS.md 红线）。
