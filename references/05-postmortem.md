# 05 · 决策信号后验自校准（SSOT）

实现：[scripts/diagnose.py](../scripts/diagnose.py) `register_signal` +
[scripts/postmortem.py](../scripts/postmortem.py)；状态在 `~/.vibe-stock/`。

## 信号登记（report 时）

- 信号动作八态：buy / add / hold / reduce / sell / watch / avoid / alert
  （最终信号映射：strong_buy→buy、buy→buy、hold→watch、sell→reduce、
  strong_sell→sell）。
- 八元组身份去重：(report_id, source_type, market, code, profile, action,
  horizon, regime)。
- **对立失效**：同 market+code+profile 下，新对立族信号（bull/bear）把旧 pending
  对立信号标 invalidated——不同 profile 可并存相反动作。
- **置信门**：buy 族置信 <0.5 → 登记 watch（不算可执行建议）。
- 期限 horizons = [1, 3, 5, 10] 个交易日。
- **价格口径**：盘中取数登记时 close_at_signal 是盘中价而非收盘价——
  price_kind（intraday/close/unknown）如实标注，后验基准沿用登记价原样、
  不回改（时段判定见 [01 · 盘中口径](01-evidence.md#盘中口径未完成-k-线)）。

## 后验（postmortem 时）

- 回看各 horizon 实际收盘：买入族 ≥+2% hit / ≤−2% miss / 其间 neutral；
  卖出族对称；watch/hold 只观察不记分。
- 归因：hit/miss 计入信号登记时的每个 source 的台账（ledger.json wins/losses）。
- 绩效因子：见 [03](03-synthesis.md)（Beta(15,15)、钳 0.83–1.2、<30 样本中性）。
- 画像升降档：命中率 ≥60% 且样本 ≥10 → promote；≤40% 且样本 ≥10 → demote；
  其余 observe（<10 样本只观察不动手）。

坑位：给出建议的人和核对建议的人是同一套系统，但核对用的是行情事实不是
模型自评——这是自校准成立的前提。
