# 03 · 受控综合：聚合、分歧、RiskGuard（SSOT）

执法在 [scripts/adjudicate.py](../scripts/adjudicate.py)（`aggregate` /
`disagreement_summary` / `risk_guard` / `apply_confidence_cap`）；本文件是口径。

## 聚合（纯确定性）

- **绩效因子**（该 source 历史后验战绩：Beta(15,15) 收缩、钳制 0.83–1.2、
  样本 <30 一律中性 1.0；台账见 [05](05-postmortem.md)）——聚合 mass 与聚合
  置信都按它加权（verdict 的 weight 字段即绩效因子）；置信只衰减方向幅度，
  不缩 mass。
- 加权分映射：≥4.5 strong_buy / ≥3.5 buy / ≥2.5 hold / ≥1.5 sell /
  更低 strong_sell。加权分 = 3 + Σ(绩效ᵢ × 置信ᵢ × (档位值ᵢ−3)) / Σ绩效ᵢ，
  档位值 strong_buy=5 / buy=4 / hold=3 / sell=2 / strong_sell=1——置信收缩
  向 hold：每条意见先按 1−置信ᵢ 向 hold 收缩，再按绩效因子加权平均，四位
  小数取整后比阈值。条件：insufficient 之外的全部聚合；坑位：两种死形态都
  要防——取单条意见「最高权重×5」会让信号档位不参与聚合（纯空头板只要最高
  置信 ≥0.70 就被映射成 buy，单条 ≥0.9 意见可无视全板产出 strong_buy）；
  纯加权均值 Σ(权重ᵢ×档位值ᵢ)/Σ权重ᵢ 对置信等比缩放不变，两条 0.1 置信
  strong_sell 也出 strong_sell——绝对置信必须衰减幅度：strong_buy 板进
  strong_buy 须平均置信 ≥0.75、sell 板进 sell 须 >0.5（恰 0.5 时 score=2.5
  落 hold）、strong_sell 板进 strong_sell 须 >0.75（与 CONFIDENCE_GATE
  同量纲）；坑位：strong_* 板进相邻档门槛减半——strong_buy 板 ≥0.25 即
  聚合 buy、strong_sell 板 >0.25 即聚合 sell。
- 聚合置信：只取与聚合信号同方向族（买入族 strong_buy/buy · hold · 卖出族
  sell/strong_sell）的意见，按绩效因子加权平均其置信，不超过同族最高置信；
  无同族支撑（多空对冲落 hold 而板上无 hold 意见）→ 0.0。条件：insufficient
  之外；坑位：取全板最高置信会让异向意见的置信冒名过 0.5 登记门
  （CONFIDENCE_GATE）；同族取最高置信则单条高置信意见可独自撑过该门。
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

- **veto**（风险角色一票否决）：buy/strong_buy → hold。与 downgrade 同真时两者
  都生效：各自对同一初判施加、取档位更保守者（档位索引取大），log 两步都记。
  条件：risk.json veto 与 downgrade 同为 true；坑位：veto 先返回会吞掉 downgrade
  ——buy 经 severity=high 两档降本应 sell，加 veto 反被截停在 hold；改成依次叠加
  （压 hold 后再降档）则同一条风险理由计罚两次，strong_buy 一步落到 strong_sell。
- **downgrade**：沿 strong_buy→buy→hold→sell→strong_sell 单向降档；
  severity=high 可一次两档。
- **永不升级**：任何配置、任何共识等级都不能把裁决往激进方向掰。
  这是防「模型激进 + 意见污染」的最后闸门，放宽即违背本仓红线（AGENTS.md）。
  单调收紧：veto / downgrade / severity=high 任一由 false 变 true，终裁档位不得
  更激进（selftest 穷举五档 × 八组合钉住）。

## 置信帽（证据不够，不许嘴硬）

核心块降级（质量分口径见 [01](01-evidence.md)）→ strong_buy/strong_sell
机械压一档。条件：置信帽 low；坑位：压档发生在 RiskGuard 之后、报告之前。
扩展九块（0.2.0）不参与质量分与置信帽（信息面不是裁决面）；修订此口径属
0.3.0 级语义变更：须人工评审 + golden 重建。
报告必须把这条裁决链写出来（可审计）。
