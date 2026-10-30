# Changelog

本文件只登记版本级变化；条目遵循 Keep a Changelog、[SemVer 2.0.0](https://semver.org/lang/zh-CN/)。

## [0.2.1] - 2026-10-30

### Fixed

- 报告风险/利好/附录逐条接回意见与 risk.json 的 rationale
  （RSI-20261029-02）：原风险栏/利好栏恒「（无登记）」——旧实现
  verdict.valid_opinions 只投影四键、恒无 rationale，两栏从未列出条目；现
  经 partition 同一验票判据按 source 挂 rationale（未过验票不挂），风险
  角色理由标注 veto/downgrade 触发态，附录意见行附 rationale 原文，空栏
  仍如实「（无登记）」。
- RiskGuard veto 与 downgrade 同真时各自施加、取更保守者（RSI-20261030-01）：
  原实现 veto 提前返回吞掉 downgrade——buy 经 severity=high 两档降本应
  sell、加 veto 反被截停在 hold，风险输入越多终裁越宽松；现两者对同一初判
  各施其罚、取档位更保守者，log 同真时两步都记（stricter=终裁），selftest
  穷举五档 × veto/downgrade/severity_high 40 组合永不升级、60 个
  false→true 翻转单调不更宽松。
- 盘中未完成 K 线标注与量比线性外推，价格口径入信号登记（RSI-20261030-02）：
  原盘中跑把未收盘的半根 K 当完整 K，量比假缩量误导策略判据；现 session
  标注 SSOT 落 evidence.meta.session（phase/as_of/elapsed_min/session_min/
  last_bar_partial，快照模式不判时段=unknown），末根未完成时 technical
  原值保留、另出 vol_ratio_5_projected 按已开盘交易分钟线性外推
  （estimated；坑位：早盘量能 U 形分布下外推值系统性偏高），context-pack
  头部出盘中警示行点名末根 OHLCV/MA/RSI/MACD 末值等受影响口径，
  register_signal 增 price_kind（intraday/close/unknown）——price_kind=
  intraday 时 close_at_signal 为盘中价而非收盘价，后验解读注意（后验基准
  沿用登记价原样不回改），报告现价注明「（盘中价）」。
- 结论句理由按终裁信号选取（RSI-20261030-03）：原取「与聚合初判同信号的
  首条意见」，RiskGuard 改判后出现终裁 sell 却挂 hold 理由的错位；现改判
  致终裁≠初判时优先挂 risk.json.rationale 摘要并注明「初判 X 经 RiskGuard
  改判为 Y」，无改判取与终裁同信号（其次同方向族）的最高置信意见并标注
  source，置信帽压档时径取同族，都没有则不硬凑。

### Changed

- **聚合算法语义级变更（RSI-20261029-01）**：加权分由「最高置信×绩效×5」
  （wscore=max）改为置信收缩加权分 score = 3 + Σ(绩效ᵢ × 置信ᵢ ×
  (档位值ᵢ−3)) / Σ绩效ᵢ（档位值 strong_buy=5 … strong_sell=1：每条意见先按
  1−置信向 hold 收缩，再按绩效因子加权平均，四位小数取整比阈值）；主信号
  改锚聚合信号（共识与高置信异见同锚，消除「终裁 hold、共识按某条 sell
  意见计」错位），聚合置信只取与聚合信号同方向族按绩效加权（≤ 同族最高
  置信，无同族支撑 0.0）。旧实现两死形态：方向盲——信号档位不进分，纯
  空头板只要最高置信 ≥0.70 就 wscore≥3.5 恒出买入族；单条独裁——一条
  ≥0.9 意见可无视全板直接 strong_buy。
  - 收严面：高置信空头/中性板不再恒买入族（随机扫描此类板旧口径 85.6% 落
    买入族），单条 ≥0.9 独裁终结；selftest 显式钉 9hold+4sell 板（最高
    置信 0.70 sell）旧 buy→新 hold、单条 0.95 strong_buy 混 hold 板旧
    strong_buy→新 hold。
  - 放宽面（AGENTS.md 红线 4，逐条点名供人工评审）：放宽集中于一致/多数
    多头板与低置信板，含跨入买入族的形态——selftest 已钉 `relax: 2x sb`
    两例：2×strong_buy 0.6 旧 hold→新 buy、2×0.8 旧 buy→新 strong_buy
    （一致方向攒够幅度即进档）；最小反例 8×strong_buy 0.60 + 2×hold 0.50
    → 旧 hold / 新 buy——多数多头板一步跨进买入族；数学边界（可验证，
    同信号一致板）：buy 板进 buy 须平均置信 ≥0.5、strong_buy 板进
    strong_buy 须 ≥0.75（与 CONFIDENCE_GATE 同量纲）；strong_* 板进
    相邻档门槛减半——strong_buy 板 ≥0.25 即聚合 buy、strong_sell 板
    >0.25 即聚合 sell，评估放宽面勿按 0.5 门槛估。低置信一致空头板按
    [03] 字面旧判
    （<1.5→strong_sell）的 strong_sell→新 hold——低置信不再独裁最重卖出档。
  - <1.5 兜底由 hold 改 strong_sell，对齐 [03] 阈值表字面（旧代码兜底
    分支错写 hold，strong_sell 档从未可达）。
  - 共识分级锚修正：共识与高置信异见均以聚合信号为主信号（aligned 按与
    聚合信号同档计），正常路径样例 medium→high 属重算副作用。
  - golden verdict 重建：初判 hold（加权分 3.48、同族置信 0.63）、veto
    只压买入族故 no-op、0.85 strong_buy 隔 2 档构成 high_conf_dissent
    回归；evals/README 断言要点同步。
  - 本条为语义级变更，按默认纪律升 patch（0.2.1），维护者可改判 0.3.0
    再合并；selftest 判据改动逐条为重算/收严/新增钉，无删除断言（置信帽
    与两档降级换 strong_buy 初判 Fixture 保持触达）。

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
- 港股 news 解除 not_supported（qq_news 单源）；quote 实时叠加 qt 快照与换手率（A 股；港股位序未验证不叠加）。
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

## [0.1.3] - 2026-10-28

### Fixed

- 北交所代码（43/83/87/92 号段）交易所分流修正：新增 `cn_exchange` 统一判定
  （bj/sh/sz），Yahoo 后缀与腾讯源共用；腾讯源对北交所显式拒绝（2026-10-28
  实测：bj 前缀被拒、误挂 sz 亦无数据），拒绝走专用 `NotSupportedSymbol` 异常
  按 not_supported 记轨迹——确定性不覆盖不计熔断、不连坐他股腾讯回退；Yahoo
  `.BJ` 暂无数据则如实 fetch_failed；em 源走 akshare 既有 secid 规则
  （`0.830799`），待东财行情簇恢复后实网复核北交所取数。`detect_market` 收
  bj 前缀形态（bj830799，与 sh/sz 对称）；references/01-evidence.md 回退链
  口径同步北交所坑位。回归断言并入 `diagnose.py --selftest`（87/5 号段、
  .SS/.SZ 后缀、不覆盖不计熔断）。

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
- 报告渲染：检查清单 ±10%% 双百分号展示修正（先于本版合入 main，补登）。

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
