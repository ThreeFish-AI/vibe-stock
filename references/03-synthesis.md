# 03 · 受控综合：聚合、分歧、RiskGuard（SSOT）

执法在 [scripts/adjudicate.py](../scripts/adjudicate.py)（`aggregate` /
`disagreement_summary` / `risk_guard` / `apply_confidence_cap`）；本文件是口径。

## 聚合（纯确定性）

- 权重 = 置信度 × **绩效因子**（该 source 历史后验战绩：Beta(15,15) 收缩、
  钳制 0.83–1.2、样本 <30 一律中性 1.0；台账见 [05](05-postmortem.md)）。
- 加权分（权重×5）映射：≥4.5 strong_buy / ≥3.5 buy / ≥2.5 hold / ≥1.5 sell /
  更低 strong_sell。加权分 = Σ(权重ᵢ × 档位值ᵢ) / Σ权重ᵢ，档位值 strong_buy=5 /
  buy=4 / hold=3 / sell=2 / strong_sell=1（「×5」指五档满分尺度），四位小数取整
  后比阈值。条件：insufficient 之外的全部聚合；坑位：取单条意见「最高权重×5」
  会让信号档位不参与聚合——纯空头板只要最高置信 ≥0.70 就被映射成 buy，单条
  ≥0.9 意见可无视全板产出 strong_buy。
- 聚合置信：只取与聚合信号同方向族（买入族 strong_buy/buy · hold · 卖出族
  sell/strong_sell）的意见，按权重加权平均其置信，不超过同族最高置信；无同族
  支撑（多空对冲落 hold 而板上无 hold 意见）→ 0.0。条件：insufficient 之外；
  坑位：取全板最高置信会让异向意见的置信冒名过 0.5 登记门（CONFIDENCE_GATE）；
  同族取最高置信则单条高置信意见可独自撑过该门。
- **insufficient 铁律**：有效意见为零、仅一条、或置信度全零 → hold、置信 0、
  共识 insufficient——单样本哪怕自洽也不许装出高共识。

## 分歧检测与共识分级

- 冲突三类：方向对立（high）/ 置信离散 ≥0.3（medium）/ 高置信异见（≥0.75 且
  与主信号隔 ≥2 档；≥0.9 升 high）。
- 共识：高严重度冲突 → low；≥2/3 同向且零冲突 → high；否则 medium。
- 主信号 = 聚合信号（上节加权分映射结果），「同向」按与主信号同档计。条件：
  高置信异见与共识分级两处同锚；坑位：以置信×绩效最高的单条意见为锚，会出现
  终裁 hold、共识与异见却按某条 sell 意见计的错位。
- 分歧摘要三桶（bullish/bearish/neutral）显式进报告——分歧上桌，不抹平。

## RiskGuard（只降不升——无条件全局规则：保守裁决不可被反向打开）

- **veto**（风险角色一票否决）：buy/strong_buy → hold。
- **downgrade**：沿 strong_buy→buy→hold→sell→strong_sell 单向降档；
  severity=high 可一次两档。
- **永不升级**：任何配置、任何共识等级都不能把裁决往激进方向掰。
  这是防「模型激进 + 意见污染」的最后闸门，放宽即违背本仓红线（AGENTS.md）。

## 置信帽（证据不够，不许嘴硬）

核心块降级（质量分口径见 [01](01-evidence.md)）→ strong_buy/strong_sell
机械压一档。条件：置信帽 low；坑位：压档发生在 RiskGuard 之后、报告之前。
扩展九块（0.2.0）不参与质量分与置信帽（信息面不是裁决面）；修订此口径属
0.3.0 级语义变更：须人工评审 + golden 重建。
报告必须把这条裁决链写出来（可审计）。
