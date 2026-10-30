# 05 · 决策信号后验自校准（SSOT）

后验只评估短线信号（策略/角色意见）：基本面锚（lens.py 三档结论，12 个月
量级）不进后验——T+1/3/5/10 短窗证伪不了基本面论点（期限正交），把透镜塞进
短窗归因只会错杀长周期视角。

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
- **市场推导**：适用条件——evidence.meta 无 market 字段（快照模式的真实路径：
  `fetch.py` 快照分支不判市场，meta 只有 symbol）；做法——经 `fetch.detect_market`
  从 meta 的 code/symbol 推导 (market, 归一 code) 成对落账（market 与 code 必须同源，
  只推 market 会留下原始 symbol 形态的 code 而取不到日 K）；推不出（symbol 非
  A/港代码形态，如合成符号）维持兜底 `?` + 原样 code，由后验侧未知市场跳过守卫
  兜底（双层防线）；对立失效匹配对 market 不在取数链的存量记录（`?` + 原始
  symbol 形态 code）同经 detect_market 归一比对（推不出维持不匹配）——归一身份
  切换不得使存量同股对立记录漏失效；快照登记信号带 `snapshot: true` 稀疏标记，
  报告路由不随推导变（仍 `_snapshot/`），实盘时间线索引/总览排除快照信号（防
  合成信号混入实盘索引）；坑位——快照基准价 `close_at_signal` 是
  快照价，推得市场后后验会以真实日 K 评分——合成快照（如 evals 演示 fixture）
  勿跑 report 登记信号，否则虚构基准价与真实行情混算、台账遭污染。

## 后验（postmortem 时）

- **未知市场跳过**：适用条件——pending 信号 market 不在 `fetch.CHAINS`
  （如快照兜底登记的 `?`、缺 market/code 字段的陈旧记录）；做法——逐条打印
  跳过诊断行（id、code、market 实际值与缺失项），该记录保持 pending 不动、
  其余信号照常评估（不可借同 code 已知市场的日 K 代评——同码跨市场互评
  与跳过守卫矛盾，评估集按守卫过滤）；坑位——跳过不是修复，坏记录每次
  全量后验都会重复报告，人工修正 market 字段后重跑即入评估，不代改
  signals.json（状态文件是用户本地事实）。
- **`--stock` 过滤**：适用条件——给参时；做法——经 `fetch.detect_market` 归一出
  (market, code)，只评该 code 的 pending 信号（同 code 未知市场记录仍在过滤集内、
  由上方守卫如实报跳过，不静默吞）；识别失败以 SystemExit 如实报错退出；
  无匹配打印说明、退出码 0（不写 signals/ledger）；坑位——匹配键是 detect_market
  归一后形态，存量 code 未归一（快照兜底登记的原始 symbol 形态）会匹配不上，
  以无参全量跑（守卫跳过口径）兜底。
- 回看各 horizon 实际收盘：买入族 ≥+2% hit / ≤−2% miss / 其间 neutral；
  卖出族对称；watch/hold 只观察不记分。
- 归因：hit/miss 计入信号登记时的每个 source 的台账（ledger.json wins/losses）。
- 绩效因子：见 [03](03-synthesis.md)（Beta(15,15)、钳 0.83–1.2、<30 样本中性）。
- 画像升降档：命中率 ≥60% 且样本 ≥10 → promote；≤40% 且样本 ≥10 → demote；
  其余 observe（<10 样本只观察不动手）。
- **人民币口径展示（`--cny`）**（条件：港股信号且需投资者本币视角；做法：经
  [01](01-evidence.md) fx 块同源的 `hkd_cny_daily` 取 HKD/CNY 日线，hk 信号
  evaluated 附 cny_close / cny_chg_pct（含汇兑项），汇率缺根如实缺省、取数失败
  不阻断评估；坑位：人民币只是展示维度——outcome 判定与台账归因**默认仍按
  港币**，不改判定口径即不改自校准语义）。
- 时间线索引（适用：postmortem 落盘末尾）：做法——台账写盘成功后重建
  reports/ 索引，T+n 结果进 `index.md`；坑位——索引是派生视图，重建失败只告警
  不回滚（事实源 signals.json / ledger.json 已先落盘）。

坑位：给出建议的人和核对建议的人是同一套系统，但核对用的是行情事实不是
模型自评——这是自校准成立的前提。
