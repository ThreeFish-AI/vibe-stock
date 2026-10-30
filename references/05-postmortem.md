# 05 · 决策信号后验自校准（SSOT）

实现：[scripts/diagnose.py](../scripts/diagnose.py) `register_signal` +
[scripts/postmortem.py](../scripts/postmortem.py)；状态在 `~/.vibe-stock/`。

## 信号登记（report 时）

- 信号动作八态：buy / add / hold / reduce / sell / watch / avoid / alert
  （最终信号映射：strong_buy→buy、buy→buy、hold→watch、sell→reduce、
  strong_sell→sell）。
- 身份键 (report_id, source_type, market, code, profile, action, horizon,
  regime) 即八元组；**去重未实现**：同日重跑每版各登记一条信号（挂起项见
  [docs/.agents/issue.md](../docs/.agents/issue.md) I-004）。
- **对立失效**：同 market+code+profile 下，新对立族信号（bull/bear）把旧 pending
  对立信号标 invalidated——不同 profile 可并存相反动作；比对按读时归一（港股
  补 5 位；快照符号两侧同口径归一），存量 4 位港码/带后缀旧形态信号同样互通。
- **置信门**：buy 族置信 <0.5 → 登记 watch（不算可执行建议）。
- 期限 horizons = [1, 3, 5, 10] 个交易日。
- 报告指针（适用：读信号定位报告时）：做法——`report_id` = `<code>-<date>` 日级
  分组键，定位用 `report_path` + `report_version`（布局见 [04](04-report.md)
  「落盘与跟踪」）；坑位——迁移还原的丢失版带 `report_lost: true`，正文不可得。
- 股票名称（适用：索引「股票名称」列数据源）：做法——report 时从 quote 块
  `name`（A 股 qt 全量快照 / 港股 qt 紧凑快照 `s_hk<code>`）写入信号
  `stock_name` 并写穿 `names.json` 显示名缓存（`market:code` 键），索引组内
  取最新非空、回落缓存；坑位——名称是行情面数据，取数失败如实缺省 `—`，
  不做本地映射回退；缓存是可再生的派生文件，损坏自愈为空。
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
- 时间线索引（适用：postmortem 落盘末尾）：做法——台账写盘成功后重建
  reports/ 索引，T+n 结果进 `index.md`；坑位——索引是派生视图，重建失败只告警
  不回滚（事实源 signals.json / ledger.json 已先落盘）。

坑位：给出建议的人和核对建议的人是同一套系统，但核对用的是行情事实不是
模型自评——这是自校准成立的前提。
