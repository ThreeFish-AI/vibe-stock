# Changelog

本文件只登记版本级变化；条目遵循 Keep a Changelog、[SemVer 2.0.0](https://semver.org/lang/zh-CN/)。

## [0.2.0] - 2026-10-28

### Added

- 九扩展证据块（零权重纯情报面，不进六块质量分与置信帽）：moneyflow（新浪直连
  60 日四档净额，主力=超大单+大单自算+四档和自洽校验）/notices（em_notice→cninfo
  双源）/research（研报列表+评级共识机构目标价直连）/forecast（业绩预告+披露
  日历，空结果=available 语义钉）/unlock（解禁批次）/holder（emweb F10 股东户数
  近 8 期）/market（qt 指数快照零额外调用）/industry（申万归属+同花顺板块匹配，
  三口径标注）/valuation（qt 快照+百度 5 年分位）。
- CLUSTERS 扩容 6→15 簇，簇判定规则成文（主机/服务族粒度故障域：同厂商不同
  服务族分簇、同子域多端点合簇）。
- 港股 news 解除 not_supported（qq_news 单源）；quote 实时叠加 qt 快照与换手率。
- technical 派生扩容：20 日新高/新低、60 日箱体、近 10 日量比序列、K 线形态、
  连续收涨天数、MACD hist_rising——修复 pack 只渲染收盘价导致 volume_breakout/
  box_oscillation/bottom_volume 等策略判据失明的消费矩阵缺陷。
- money_flow 策略（十策略）；事件风险类维度走风险角色 risk.json 通道。
- L0 情报兜底：allowed-tools 增 WebSearch/WebFetch，情报角色 fetch 失败时可补
  线索（rationale 标注「web-search 兜底」降置信一档，不回写证据包）。
- adjudicate E4/E5 破坏性实验钉：扩展块零权重、未知块前向兼容。

### Changed

- 命令面统一锁 `akshare==1.20.*`（minor 锁防上游接口迁移断链，升版流程见
  PIPELINE.md）；postmortem 命令补 `--with efinance`。
- context-pack：近 10 根 K 改 OHLCV+涨跌幅七列；报价节键位修复（price/
  change_pct 原挂 technical 白名单恒不渲染）；扩展块有界渲染（EXT_PACK_BUDGET
  每块预算+16k 全局护栏）；报告证据状态表全块化+近期事件节。
- fundamentals 链首插 em_datacenter（近 4 报告期全量指标：毛利率/净利率/ROIC/
  归母净利/同比）；AGENTS/PIPELINE/README 三件 selftest 口径统一。

### Fixed

- sina 财务源「每股收益(元)」键名错位恒 None（实为「摊薄每股收益(元)」，
  RSI-20261028-03）；sina 毛利率 2025 起停更恒 NaN，禁取。
- chip 改本地自算（CYQ 三角分布换手衰减，与官方接口同口径列名全同，状态
  estimated 如实），em_quote 源降为复活回退位；volume 手/股单位按源判定。
- datacenter 侧 RPT_HOLDERNUM_DET 数据集停在 2022（服务端排序亦不生效），
  股东户数事实源切 emweb F10 gdrs。

## [0.1.2] - 2026-10-28

### Changed

- fetch.py 熔断/冷却计账从库名改为上游服务簇（em_quote/em_search/sina/ths/qq/yf）：
  东财行情簇故障不再连坐新闻（em_search）与财务（sina/ths）取数（2026-10-28
  实跑实证修复）；旧库名熔断键自然过期，不迁移不删除。
- A 股日 K 回退链补腾讯源（qq 簇 qfq）：em_quote(akshare→efinance 簇内次选)→
  腾讯→yfinance；新浪源实测不复权，不入链。
- fundamentals 补同花顺簇回退（stock_financial_abstract_ths，概念键与新浪源对齐）；
  情报块成功取数同步重置所属簇失败计数。
- references/01-evidence.md 回退链与熔断口径同步为簇粒度；chip 单簇坑位注记
  （唯一上游=em_quote 簇+本地 JS 换算，akshare 全包无第二筹码接口）。

### Added

- diagnose.py selftest 增熔断按簇计账回归断言：行情簇熔断不连坐 em_search/
  sina/ths/qq/yf；日K链 em_quote 熔断时跳过同簇两源、自腾讯源取到数据；
  补财务回退链（sina 占位→ths 接管标 fallback、双败 all_failed）、`_num`
  百分号清洗与 NaN 形态、情报块成功重置簇计数断言。

### Fixed

- 日K链备选源取到的状态口径对齐八态 SSOT：先行源被熔断/冷却跳过或失败后由
  备选源取到，一律标 fallback（原 skip 不计败误标 available，三核心块质量分
  各虚高 15 分）。
- fundamentals 空值守卫修 NaN 击穿（`--` 占位经 `_num` 成 NaN 而非 None）；
  news/chip 空响应不再标 available 并重置簇失败计数（空数据不算成功）。

## [0.1.1] - 2026-10-28

### Fixed

- `fetch.py` `detect_market` 接受 7 位前导零 A 股输入（0601888→601888），
  部分行情系统导出沪市代码形态不再被误拒；其余格式行为不变
  （A 股 6 位/sh|sz 前缀、港股 4–5 位/hk 前缀/.hk 后缀、7 位非 0 开头、
  ≥8 位仍拒绝），回归断言并入 `diagnose.py --selftest`。

## [0.1.0] - 2026-10-28

### Added

- 首版诊股流水线：`fetch.py`（A/港市场分流、akshare→efinance→yfinance 回退链、
  熔断 3 败 300s、连接冷却 15s、八态标注、六块质量分、快照模式）；
  `adjudicate.py`（信号资格分选、绩效因子聚合、三类冲突、RiskGuard 只降不升、
  置信帽，`--selftest` 回归底线）；`diagnose.py`（context-pack 有界证据包、
  不可信哨兵、报告渲染、八元组信号登记与对立失效）；`postmortem.py`
  （1/3/5/10 交易日后验、±2% 中性带、归因台账、画像升降档）。
- 策略库九策略（趋势/金叉/突破/回踩/箱体/龙头/情绪/事件/底部放量），
  结构借鉴 DSA strategies（MIT），判据按本项目证据模型重写。
- 规约五篇（证据/策略/综合/报告/后验）+ PIPELINE + SKILL.md 路由壳。
