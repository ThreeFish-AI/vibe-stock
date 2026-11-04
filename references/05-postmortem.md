# 05 · 决策信号后验自校准（SSOT）

后验评估各期限轨（default/position/addon）的信号（策略/角色意见）：基本面锚
（lens.py 三档结论，
12 个月量级）仍不进后验——两轨窗都证伪不了基本面论点（期限正交），把透镜
塞进短窗归因只会错杀长周期视角。

实现：[scripts/diagnose.py](../scripts/diagnose.py) `register_signal` +
[scripts/postmortem.py](../scripts/postmortem.py)；状态在 `~/.vibe-stock/`。

## 期限轨（profile，0.0.16 起）

- **多轨登记**（条件：`diagnose.py report`；做法：default 轨照旧登记一条；
  workdir 存在 `verdict.position.json` 时同刻再登记一条 `profile=position`
  信号——horizons 取 `archive.HORIZONS_OF` SSOT（default=[1,3,5,10]、
  position=[20,60,120]≈1/3/6 个月），key_levels 按轨取（default=20 日三价、
  position=波段带三键，见 [04](04-report.md) 4b）；坑位：无 position 文件时
  单轨登记，行为与历史逐字节一致；两轨同用同一份 evidence/报告文件，
  report_id 相同、profile 不同）。
- **addon 轨登记**（0.0.18 起，[09](09-add-on.md)）：持仓股 report 段加仓轨
  判定 advice=first_add 时经 `action_override=add_on` 登记一条
  `profile=addon` 信号（action=add_on、family=bull、horizons=[1,3,5,10]、
  key_levels 附 add_ref/confirm_lo/size_cap/first_qty）；confirm/abort 是
  在途复核不登记（不双计样本）；快照 addon 信号不进实盘状态机。
- **对立失效按 profile 隔离**（无条件全局规则：期限正交的执法面）：失效与
  superseded 都只作用于同 profile 的信号——短线 sell 不得把中线 pending buy
  标 invalidated（反之亦然），存量无 profile 键的信号按 default 兜底。
- **superseded（I-004 落地）**（条件：同股、同 profile、同 report_id 的旧
  pending 信号；做法：登记新版时旧版标 `superseded`——同日重跑以最新版为
  准，不再一事多票污染样本；坑位：superseded 保持未评估形态（区别于
  invalidated 的对立失效与 evaluated 的到期收口）。
- **position 轨判定带**：band=σ_d×√h（σ_d=信号日**前** 60 日已实现日波动，
  无前视；样本不足退化 2%×√(h/10) 并在 evaluated entry 的 note 注记）——
  ±2% 固定带在 T+120 neutral 占比仅 ~7%、判定退化为大盘 beta 方向；
  default 轨判定带恒 ±2%（`NEUTRAL_BAND` 逐字不变，07 P3 import 兼容）。
- **仅 T+60 记分**（position 轨）：T+20/120 照落 evaluated 实判（hit/miss/
  neutral）供展示、不进台账——多期限记分是伪重复样本（T+60 与 T+120 收益
  相关约 0.71），会使信号提前离开 <30 样本中性门、破坏 Beta(15,15) 收缩。
- **台账分文件**：default 增量写 `ledger.json`（裸键原样）、position 写
  `ledger.position.json`；addon 增量并入 `ledger.json`（与 default 同账本、
  同 sources 归因、delta 分桶不串样本——09：加仓建议也要被市场打分）；
  裁决器经 `--ledger` 按轨查表（[03](03-synthesis.md)
  双跑制），绩效因子与画像升降档互不串轨。
- **复权基准（两轨同修，正确性修正）**：outcome 判定与涨跌幅展示基准=
  同复权 `closes[i]`（evaluated entry 落 `base`），不用 `close_at_signal`
  （qt 实时未复权价——窗口内除息/送转系统性低估收益、高股息 buy 偏 miss）；
  `close_at_signal` 仍作登记价与索引展示兜底（存量旧 entry 无 base 键时）。
  ±2%/σ√h 阈值本身不动（判据未放宽，修的是基准价口径）。
- **超窗诊断**（条件：信号日早于日 K 窗口首日（BARS_WINDOW=250））：
  做法——打印 `warn:` 诊断行并保持 pending（不再静默永久 pending）；
  坑位：跳过不是修复，超窗信号每次后验都会重复报告，人工决定留档或清理。
- **索引重建条件**：evaluated 有任何落笔（含 neutral-only）即重建——
  原「台账有增量才重建」会让纯 neutral 评估的索引滞后。

## 信号登记（report 时）

- 信号动作九态：buy / add / hold / reduce / sell / watch / avoid / alert /
  add_on（0.0.18 起，仅 addon 轨经 action_override 产生，按 bull 记分；
  最终信号映射：strong_buy→buy、buy→buy、hold→watch、sell→reduce、
  strong_sell→sell）。
- 身份键 (report_id, source_type, market, code, profile, action, horizon,
  regime) 即八元组；**去重未实现**：同日重跑每版各登记一条信号（挂起项见
  [docs/.agents/issue.md](../docs/.agents/issue.md) I-004）。
- **对立失效**：同 market+code+profile 下，新对立族信号（bull/bear）把旧 pending
  对立信号标 invalidated——不同 profile 可并存相反动作；比对按读时归一（港股
  补 5 位；快照符号两侧同口径归一），存量 4 位港码/带后缀旧形态信号同样互通。
- **置信门**：buy 族置信 <0.5 → 登记 watch（不算可执行建议）。
- 期限 horizons 按轨取 `archive.HORIZONS_OF`：default=[1,3,5,10]、
  addon=[1,3,5,10]、position=[20,60,120]（交易日）。
- 报告指针（适用：读信号定位报告时）：做法——`report_id` = `<code>-<date>` 日级
  分组键，定位用 `report_path` + `report_version`（布局见 [04](04-report.md)
  「落盘与跟踪」）；坑位——迁移还原的丢失版带 `report_lost: true`，正文不可得。
- 股票名称（适用：索引「股票名称」列数据源）：做法——report 时从 quote 块
  `name`（A 股 qt 全量快照 / 港股 qt 紧凑快照 `s_hk<code>`）写入信号
  `stock_name` 并写穿 `names.json` 显示名缓存（`market:code` 键），索引组内
  取最新非空、回落缓存；坑位——名称是行情面数据，取数失败如实缺省 `—`，
  不做本地映射回退；缓存是可再生的派生文件，损坏自愈为空。
- **价格口径**：盘中取数登记时 close_at_signal 是盘中价而非收盘价——
  price_kind（intraday/close/unknown）如实标注；close_at_signal 仅作登记与
  索引展示兜底，判定与展示基准=同复权信号日收盘（盘中登记的信号，基准即其
  信号日收盘——与「复权基准」节同一口径，存量旧 entry 无 base 键时回落
  登记价）（时段判定见 [01 · 盘中口径](01-evidence.md#盘中口径未完成-k-线)）。
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
- 回看各 horizon 实际收盘：买入族 ≥+band hit / ≤−band miss / 其间 neutral；
  卖出族对称；watch/hold 只观察不记分——band 见上文「期限轨」（default 恒
  ±2%、position=σ_d×√h）。
- **到期收盘门（I-010）**（条件：到期 horizon 落在日 K 序列末根、末根日期==
  当日（UTC+8）且该市场盘中——`fetch.session_phase` 的 `last_bar_partial`
  判据，时钟可注入）；做法——视为未到期：不评估、保持 pending，待收盘后
  下一次运行补评（周末/节假日自然收盘态、正常评估）；坑位——盘中价不是
  收盘事实，误评即伪命中且已落盘 evaluated 不回改（守卫修复前的存量伪命中
  是否回改需人工评审）。
- 归因：hit/miss 计入信号登记时的每个 source 的台账——default 轨
  ledger.json、position 轨 ledger.position.json（分文件不串轨；position 仅
  T+60 记分）。
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
