# Changelog

本文件只登记版本级变化；条目遵循 Keep a Changelog、[SemVer 2.0.0](https://semver.org/lang/zh-CN/)。

> 版本序列说明（2026-10-30 起）：项目未到稳定发布，版本号统一回归 **0.0.x** patch 序列；
> 存量 0.1.0–0.2.1 六版已按发布顺序一一重编号为 0.0.1–0.0.6，合并时又把并行合入的
> 0.2.2/0.2.3 两版重编号为 0.0.7/0.0.8（仅改 header，条目正文维持原样），
> 此后默认只升 0.0.x patch，minor（0.1.0）预留给语义级变更。

## [0.0.21] - 2026-11-04

### Added

- 走势参考 P3 两件（09 分期表收官；RiskGuard 接入经用户「继续 P3」指令
  完成评审授权——判据只收严方向）：
  ① 08 ②族新增判据 ②-8「市场级杠杆拥挤」（0.0.21）：margin 块 70 日分位
  >90 且 Δ5d >+2% 且个股级拥挤键并发（turnover_pctile_250>80 或
  limit_up_count_20d≥2）→ 风险角色 downgrade（medium，rationale 引用数值）
  ——走既有 risk.json 通道只降不升；市场级形态单独出现不独立降档；阈值
  属首版防御性设定非实证结论，放宽须评审。
  ② 预测带自校准后验：`outlook_daily --calibrate`——历史卡 × 锚 × horizon
  触及概率 vs 实际触及（方向按卡日收盘定：上方锚看上穿/下方锚看回落——
  双向或判对上方锚恒真的缺陷已修并有钉；不满整窗不记防右删），样本幂等
  台账 `~/.vibe-stock/outlook-calibration.jsonl`（坏行/标量行自愈）、
  `outlook/calibration.md` 分桶校准表（桶 n<30 标不足）；信息面披露不进
  裁决/台账/不改预测带公式。首跑 34 样本落地（低 p 桶实际 3.8% vs 预测
  2.8%，量级吻合）。outlook selftest 新增校准钉（触及判定四态/样本流/
  分桶/幂等合并/坏行自愈）。
- 版本依据：一条 LLM 判据（只降不升方向）+ 信息面后验，按 0.0.x patch。

## [0.0.20] - 2026-11-04

### Added

- 走势参考 P2 两件（[09](references/09-outlook.md) 分期表）：
  ① day-summary 附件：close_pass 渲染「走势参考（上一张收盘卡 · <date>）」
  指针节——由 close_pass 自身消费 outlook jsonl 重算（幂等；外挂追加会被
  重渲冲掉的问题形态不存在）；全文指针 + 市场级摘要行 + 零权重尾注；当日
  卡 17:35 才出、收盘复核只见 <today 卡（语义钉）；watch selftest 新增 5
  checks（31→36：无目录不出节/有卡出节/市场级行/零权重尾注/当日卡不进
  附件）。
  ② launchd 17:35 独立槽模板 `batch/outlook/com.threefish.vibestock.outlook.plist`
  （周一至五单槽每日批量、与 16:15 兜底槽错峰 80min、一次性命令无
  KeepAlive 失败次日自愈、RunAtLoad=false、节假日误拉一次无害——无交易日
  历取舍同 07 P4；plistlib 解析钉含 --daily 参数与五槽 17:35 形态）。
- 版本依据：编排面与模板新增（脚本核心件零改动），按 0.0.x patch 升版。

## [0.0.19] - 2026-11-04

### Added

- 市场级情绪五块 + 指数日 K 链共享件一次全落（用户 2026-11-04 裁定 5；
  [09](references/09-outlook.md) 分期表 v2）：fetch.py 新增五个零权重扩展块
  ——margin 两融余额（dc `RPTA_RZRQ_LSHJ` 直连主源·全市场·元·单次 70 日，
  金十转发回退·沪深两所合计差北交所 ~0.33% 如实披露；backlog 原报表名
  RPT_RZRQ_LSHJ 已失效——改名多一个 A）、index 指数基准（HS300/ALLA/
  HSI 快照 + MA60 + 距 MA60%；腾讯主源→新浪回退、HSI yf→新浪港股；坑位
  钉死：腾讯指数 amount 列实为量手非额、000985 新浪断更 2016、yf MultiIndex
  单列 DataFrame 陷阱、当日行 Volume=0）、turnover_pctile 全A换手分位
  （000985 量滚动 250 日分位——成交活跃度代理，东财换手率列补测后升级）、
  erp（月频乐咕沪深300 滚动 PE×东财 10Y，ERP=1/PE−y10，5 年月频分位；日频
  中证官网 000300 P/E2 增量台账 `~/.vibe-stock/erp_pe_daily.jsonl`，满 250
  日出日频分位——裁定 7 的经验积累载体）、margin_accounts 两融账户参与度
  （日频·户；裁定 6：原「新开户」上游 2023-09 停更的替代口径，不冒充新开户）。
- 市场维度共享取数：fetch 层 `_MKT_CACHE` 同进程一次取数（单诊 +2~6 HTTP、
  批量 +8~14）；batch/outlook_daily.py build_evidence 注入五块；簇 16→20
  （jin10/sina_idx/legulegu/csindex 新增，dc-margin/dc-bond/em-mkt-account
  归 em_datacenter、tx-idx 归 qq）。
- 消费面：卡片 emotion.market 五块投影（全缺 abstained）+ pack「市场级情绪」
  行；日表「市场级情绪」节出实数；diagnose render_ext_blocks 五节有界渲染
  （EXT_PACK_BUDGET 2–5 行）+ 截断 heads 五节头；adjudicate EXT_BLOCKS
  镜像加宽；diagnose selftest 簇数钉 16→20 与 hk 能力钉集合扩容。
- 指针：01 扩展块表 +5 行与 backlog 两融转正（东财指数换手率列补测位）；
  08 Phase 5 预留节指针化（市场级已实施、指数链就绪、超额收益带实施随期别）；
  07 P3 指数链就绪句；09 分期表 v2 ✅；SKILL（0.0.19+description 十五块）/
  PIPELINE（21 块）/README 块数口径同步。
- 版本依据：纯信息面扩展块（零权重、裁决链零改动），按 0.0.x patch 升版。

### Fixed（0.0.19 合入前独立盲审修复）

- C1：erp partial「仅日频积累、无数值键」形态（月频链失败——五新源常态
  路径）曾把 `ERP None%` 字面量渗进 pack 与日表——投影处按数值键收口
  （erp 无 erp_pct 不入卡），破坏性实验钉进 outlook selftest（全 pack 禁
  None 字面量）。
- W1：`_MKT_CACHE` 只缓存成功数据——fetch_failed 不入缓存（首股瞬态失败
  曾固化成全批 21 股终局、绕过熔断器「连续 3 败」阈值；重试节流由既有
  冷却承担）。
- W2：HSI 新浪回退补 `>=60` 序列守卫（与 yf 主源对称，短序列不出
  ma60=None 快照、日表不出「距 MA60 None%」）。
- S1/S4：ERP 台账合法 JSON 标量行（非 dict）按坏行自愈跳过；margin
  docstring「行内自校验」措辞改为口径声明（未做数值校验不虚称）。
- W3/S2 声明为既定取舍并写入 09 并发节：ERP 台账 last-writer-wins
  （增量 20 日重叠、次日自愈）；跨进程无市场级缓存（06 批量 subprocess
  形态每股全价，后续按当日 jsonl 缓存收口）。
- 源验证：三份探针实测报告（两融/指数+ERP/新开户，含字段逐字记录、交叉
  验证与失败形态）存 `.context/probe-*.md` 并摘录进 PR 描述；五块联网实跑
  冒烟全通（margin 22988.6 亿与三所加总闭合、ERP 6.2%=1/12.8−1.61%、
  HS300/ALLA 当日 K、HSI 修复后入列）。

## [0.0.18] - 2026-11-04

### Added

- 在册股短/中期走势参考机制（用户 2026-11-04 五项裁定：生成时机=收盘批量
  +决策现算混合、覆盖=全在册 universe 21 只、情绪面含市场级块、权限=零权重
  纯参考、市场级四块一次全落——后者随 0.0.19 落地）：新增
  `references/09-outlook.md`（机制 SSOT）、`scripts/outlook.py`（第五件硬
  门禁纯函数件：双轨 σ√h 预测带 + first-passage 触及概率（复用 lens/
  realized_vol/HORIZONS_OF/MIN_SAMPLES，import 禁复制）、个股级情绪键与资金
  流投影、每股×轨×horizon 经验计数桶（observed 不入桶、n<MIN_SAMPLES 标
  不足）、与前卡确定性日差连向、实盘股用户锚脱敏投影（operations 只读
  time/code/action/price，quantity/cost_price/成本派生涨幅绝不落盘，负断言
  钉））、`batch/outlook_daily.py`（非门禁编排：universe import watch、
  FetchLock 单窗 + 股间 8–12s 退避、收盘卡幂等 upsert 入
  `~/.vibe-stock/outlook/<date>.jsonl`、`<date>.md` 全集日表；盘中卡拒写、
  当日已卡幂等跳过）。
- 诊股注入（diagnose.py）：prepare 恒现算落 `.vs/outlook.json`（失败/弃权/
  快照即清除残留卡，lens 清理同款不变式）；context-pack 新增「走势参考
  （零权重）」节并**置于扩展块之前**（超预算时扩展节先截、本节存活，截断序
  selftest 钉）；报告新增 4c「短/中期走势参考（零权重 · 不进裁决）」条件节
  （band/beta/零权重三声明；身份软校验不符只跳节+warn——与裁决事实面身份
  exit 2 的分级依据）。
- 两把尺分立与零权重执法面：band_note 逐字钉（预测带≠后验判定带：default
  ±2% 固定带、position σ√h 仅 T+60 记分——判定带 SSOT 仍在 postmortem，
  卡片只引用）；outlook selftest E4 同构钉（evidence 挂卡不扰动
  evidence_cap）；03「透镜不进裁决」节 outlook 并列句共用同一执法面。
- 门禁升格：scripts/ 四件 → **五件**（`outlook.py --selftest` 提交前置；
  AGENTS 测试节/目录表、evals/README、PIPELINE 回归块、README 四处同步 +
  SKILL 判表命令入口；monitor 两件的「非阻塞第五条」措辞改「非阻塞旁路
  门禁」防与第五件硬门禁撞名）；指针全套同步（SKILL frontmatter 0.0.18+description+判表+工作
  流注释、PIPELINE 头部/② 段/命令速查、README、AGENTS、knowledge-map、04
  4c 条目与 portfolio 契约表 operations 消费行）。
- 版本依据：信息面新增机制 + 门禁收严（四件→五件），裁决链与后验零改动，
  按 0.0.x patch 升版。

### Fixed（0.0.18 合入前独立盲审 22 项全修）

- 严重三项：S1 selftest fixture 与真实持仓零重合改为**动态负断言**（两侧
  `_norm_code` 归一、覆盖 holdings∪operations 全量码，不再假设码段永真；
  hk fixture 换合成段并构造 4/5 位真互通用例）；S2 `persist_card` 落盘前
  剥离 `user_anchor`（实盘操作价/成本派生 move_pct 绝不入全局时序——只住
  workdir 现算卡，存量卡已清洗重写，selftest 钉）；S3 满卡 17 行超 pack
  截界致零权重声明被截（改为截内容不截声明、报告侧按内容过滤，破坏性
  实验钉）。
- 较严重六项：M1 `_streak` None 改真断链（中段缺值掐断历史，不桥接）；
  M2 批量取数 now 每股现取（冷却/熔断/时段判定不吃批次开头陈旧值）；
  M3 熔断账本落盘移入 finally + 出卡计算并入 try（异常/Ctrl-C 不丢账本）；
  M4/L8 新增 **<17:10 墙钟门**（代码闸：收盘竞价定型窗内早跑会把未定型 K
  钉成当日卡且幂等键当日不再重取——「≥17:10」时点纪律落成代码，--force
  可越过）；M5 signals 快照合成信号不入经验桶/不作锚（archive 索引同口径）；
  M6 门禁登记口径修正为四处（SKILL 判表只登记命令入口）+ batch/README、
  07「四件」→「五件」存量指针同步 + monitor「非阻塞第五条」改「非阻塞
  旁路门禁」防撞名。
- 一般项：anchors_source 三态精确化（无有效键=abstained）· σ 退化链删不可
  达的 rv120 中间档（注释同步「宁宽勿窄」）· 预测带下沿夹 0（极端波动）·
  first-passage 高估注记随 pack σ 行输出 · `--daily`/`--stock` 显式旗标
  （裸跑不触发 ~84 HTTP）+ 抖动改 random.uniform · 锁竞争独立计数不入
  「盘中拒写」· jsonl 坏行统一跳过 + tmp 补 fsync · prepare 日 K 全链失败
  早退同清残留卡 · 经验桶 n 含 neutral 与台账 MIN_SAMPLES 只数 decisive
  的口径差异在 09 显式声明 · pack 预算挤占记为已知取舍 · operations 读入
  按 time 排序防乱序登记 · prepare selftest 用例 STATE_DIR 重定向临时目录
  （门禁封闭不触真实状态文件）。

## [0.0.17] - 2026-11-03

### Fixed

- 盯盘 launchd 模板重启/开机后当日不再拉起（I-009）：StartCalendarInterval
  仅 09:15 单槽且 RunAtLoad=false，工作日 09:15 后系统重启/开机/重新登录，
  LaunchAgent 重新加载后当日已无日历槽，盯盘盲窗直至手动 kickstart
  （launchd.plist(5) 只承诺睡眠期间错过的触发唤醒时合并补发一次，关机/重启
  期间错过的不补发）。模板改为 09:15 主槽 + 周一至周五交易时段补拉槽
  （09:45–11:45、13:15–15:45 各每 30min，相邻槽交易盲窗 ≤30min，覆盖 A 股
  与港股交易时段，两市共同休市窗零槽）+ 16:15 盘后兜底槽（进程在收盘复核前
  死亡时 `close_done` 未置则重拉补跑 `--close`，已置则立即 exit 0）；watch.py
  运行时零改动（任意时刻拉起自洽），`watch.py --selftest` 新增 launchd 模板
  回归钉 8 项（RunAtLoad=false、KeepAlive 崩溃自愈+防投机拉起、槽位仅工作日
  且五日一致、补拉间隔、盘后兜底槽等），22→30 checks；07「宿主形态」补拉槽
  语义与四坑位（运行期间槽位被直接丢弃的探针实测、本地时区假设、当日停盯
  须 bootout、P2 会话接管协调）、batch/monitor/README 迁移提示与 README 同步。
  附带修复：模板注释含 XML 非法的连续连字符（`--loop` 写入注释），plutil 容忍
  但标准 XML/plistlib 拒解析——重写注释后模板可被 plistlib 解析（selftest 钉
  依赖此性质）。

### Changed

- 盯盘当日停盘操作语义：kill 进程不再等于当日停盯（会被下一补拉槽重新拉起
  ——交易盲窗 ≤30min，午休跨槽至 13:15），彻底停当日盯盘须 `launchctl bootout`
  卸载作业；已装单槽旧模板升级
  须 bootout 后按新模板重装（盘中执行会杀掉在跑进程，建议收盘后操作）。

## [0.0.16] - 2026-11-03

### Added

- 中线（1–6 个月）视角一次性完整落地（用户 2026-11-03 裁定：完整中线轨、
  版本 0.0.x patch、默认双轨、06/07 同步接入、Phase 2/3 与 Phase 1 同 PR 同
  版本落实——[references/08](references/08-midterm.md)）：
  - `references/08-midterm.md`（新建 SSOT）：mid_term 因子口径表（条件/坑位
    逐字段）、三族**只降不升**风险判据——利好出尽（隔夜/日内拆分、抢跑透支、
    解禁分级、高送转×减持并发、软/硬事件分诊等八条）/ 主题拥挤与 AI 情绪
    （异常换手、彩票效应、涨停注意力、估值-动量双热、题材真伪三问、两年翻倍
    警戒）/ 制度与政策（壳/退市出清、监管敏感行业点名即降档、反内卷衰减窗）
    ——全部经既有风险角色 risk.json 通道，adjudicate 零改动执法；四张静态表
    （监管敏感行业/政策日历/强周期映射/A-HK 往返成本常量）与证据准入四问、
    拒绝清单只增不删口径。
  - `fetch.derive_technical` 新增 `mid_term` 嵌套派生（纯标准库）：跳月动量
    ret_6_1/ret_12_1_approx（≈11 个月近似注记）、tsmom_250d、rv60/rv120、
    max_ret_20d、按代码段涨停计数（主板 10/创业科创 20/北交 30、0.15pp 容差；
    ST 5% 特例依赖 quote.name 交 LLM 收严判读）、mdd_250/cur_dd、ma150/ma200、
    vr_63d 方差比（重叠窗口只作方向参考）、异常换手三键（换手列仅 ak-em/ef-em
    链首回收，qq-tx/yf 回退时缺席不虚构）；`realized_vol` 由 lens 迁 fetch 共享
    （SSOT 防双实现漂移，lens 留同名导出，调用方零改动）。
  - moneyflow 中线扩行：A 股 summary 增 20/60 日主力累计（序列 60 日封顶、不足
    缺省）；港股南向单页 65 行出持股比 20/60 日变化（同端点零增请求，按披露
    行数回看、停牌缺行时跨度比名义窗更长如实注记）。
  - context-pack 渲染 mid_term 三行（动量/长均线 · 波动/回撤 · 情绪/拥挤，缺项
    不落 None 字面量）与资金流 20/60 日行（A/HK 两态）。
  - `docs/research/midterm-strategies.md`（新建）：22-agent 调研 Workflow
    （8 维度文献调研 → 逐条对抗核验 → 3 方案比选）产出的中线策略调研报告，
    15 章 + 拒绝引入清单（13 条）+ 证据块映射表（20 行）；调研共 124 条
    findings（100 confirmed / 20 weakened / 4 unverifiable，逐条经引文存在
    性/效应量转述/发表后衰减对抗核验），正文以 IEEE 引文显式引用其中关键
    条目、weakened/unverifiable 均带显式降权标注——后续中线判据的证据准入
    以本报告与 08 四问为准。
  - 策略只收严补句：bull_trend 增反转警戒（A 股月度反转强于动量——近 20 日
    涨幅 >+20% 且逼近 52 周高降档、换手分位 >95% 滞涨禁 strong_buy）；
    dragon_head 增题材真伪三问（蹭热点不给题材溢价）与注意力过热禁 strong_buy。
  - 回归：diagnose selftest 新增 mid_term 手算钉（250 根合成序列：跳月动量
    10.0/回撤 −9.54/长均线/涨停分段计数/异常换手 1.852 与 (<=cur)/n 分位）、
    VR 方向钉（季度级趋势摆动 >1 vs 日频交替 <1）、短窗缺项缺席钉、realized_vol
    SSOT 钉、pack mid_term 与资金流 20/60 渲染钉；四件 selftest + 监盘两件全绿。
  - **Phase 2 双轨管道**：`archive.HORIZONS_OF` 期限轨 SSOT（default=
    [1,3,5,10]、position=[20,60,120]）；`register_signal` 参数化 profile/
    horizons——对立失效与同 report_id 旧版 superseded（I-004 落地）均按
    profile 隔离（存量无 profile 键按 default 兜底，向 05 规约看齐）；
    `_mid_key_levels` 波段带三键（band_lo/band_hi/trail_ref=MA60，带宽
    g=max(2σ_d×√21, 3×往返成本)，`fetch.ROUNDTRIP_COST` 常量）；报告新增
    「中线裁决」节（verdict.position.json 存在才出，单轨形态逐字节兼容）；
    cmd_report 可选二登记；postmortem：σ√h 判定带（σ_d=信号日前 60 日已实现
    日波动无前视，不足退化 2%×√(h/10) 注记）、仅 T+60 记分（T+20/120 照落
    实判供展示、不进台账——伪重复治理）、台账分文件 ledger.position.json、
    **复权基准修复
    两轨同修**（判定与展示基准改同复权 closes[i]，evaluated 落 base——修
    qt 未复权价 vs 前复权日 K 的系统性低估；±2%/σ√h 阈值不动）、超窗信号
    warn 诊断（不再静默永久 pending）、索引重建条件改「evaluated 有落笔」；
    archive 单股双表（短线 T+1/3/5/10 + 中线 T+20/60/120）与总览中线两列
    （短线列只算 default 轨）；batch/monitor/watch.py 价位锚按 profile 过滤
    （position 波段带不覆盖短线止损/目标锚）。
  - **Phase 3 中线策略与编排**：五个 `profile: position` 策略 YAML（quality_
    value 质量价值 / revision_momentum 预期修正 / policy_staged 国策四级分层 /
    turnaround_catalyst 翻身催化 / swing_band regime 门控波段带，置信帽
    0.65、缺证据弃权、风险向一律走 risk.json）；references/06 中线档（三价
    参数化 60/120 日窗+σ 带+箱体下沿−5% 总回撤门、波动倒数权重、卫星仓硬帽
    ≤30%、20 交易日复核）；references/07 价位锚分轨句与 P2 波段带带内状态
    规约；strategies/README profile 字段说明。
  - 指针同步：SKILL.md（version/头部指针/判表「中线视角」行/工作流 ③④ 双轨
    意见与双跑命令/后验段）、README（「中线双轨」节 + 十五策略）、PIPELINE.md
    （双跑命令与后验口径）、AGENTS.md 目录表、knowledge-map、references/
    01/02/03/04/05/06/07 各期限轨指针；`.gitignore` 增 `.temp/`。
  - 回归补钉（Phase 2/3）：diagnose——跨轨对立不失效/同 profile 照常失效/
    同 report_id superseded/无 profile 键兜底/波段带数学钉/中线裁决节要素/
    索引双表与总览两列；postmortem——σ√h 手算钉/仅 T+60 记分/台账分桶/
    复权基准钉（登记价≠closes[i] 形态）/超窗诊断钉/退化带注记钉/损坏
    signals.json 严格加载中止钉（I-005）；watch（23 checks）——position
    波段带不覆盖短线锚。
  - 对抗评审修复（4 维度 24-agent Review，20 条确认项全修）：创业板 302
    号段涨停阈值；mid_term.rv 改喂原始序列（坏点断链与 lens 透镜同输入同
    输出）；ret_12_1_approx 短窗（<127 根）缺席不虚构（次新股虚假动量）；
    rets20 坏点断链配对；换手三键末根门；efinance 换手列坏值防护（_tor 模块
    级共用）；快照 meta 回填 market/code（涨停计数不再缺席，推不出维持 '?'
    契约）；pack 渲染次新股涨跌幅如实口径；南向单页 65 行口径对齐（01/08/
    代码注释）；带宽 σ_d 语义注记（月窗 2σ_d×√21）；调研报告引文补全与
    计数口径澄清；拒绝清单计数对齐（13 条）；PIPELINE 08 指针补齐。
  - 评审二轮修复（5 镜头独立 finder + 3 视轴多数决对抗复核，24 条确认项
    全修，均附回归钉或指针同步）：postmortem selftest 未隔离 STATE_DIR——
    neutral-only 索引重建会把合成 index 写进真实 ~/.vibe-stock/reports/
    （P1，补隔离与钉）；_mid_term 新增 ret_20d/ret_60d 累计涨幅——判据族
    「近 20 日涨幅 >+20%」「60 日涨幅 >+40%」此前在证据包无数值锚（P1）；
    pack fundamentals 渲染 2 期→4 期（quality_value/turnaround 的 4 期
    门槛可得，P1）；pack 意见产出要求双轨化（短线轨只读 default 策略，
    防混轨）；rets20 改喂原始末 21 根真断链（预过滤序列会跨坏点拼「单日」
    涨幅、虚计涨停）；换手三键双层 A 股门控（ak-em 港股列不回收 + 因子层
    market 门，港股南向代理口径）；trail_ref 不足 60 根省键（数值锚不落
    「—」哨兵）；「中线裁决」节 −5%% 文案修复；verdict.position.json 损坏
    显式中止（不再静默单轨）；总览表去掉 position 顶替短线列的 or g 兜底
    （04 分轨规约）；_tor 并入 _fnum（坏值清洗单一实现）；02 schema 补
    profile、PIPELINE 五段图双轨、SKILL description 十五策略、06 中线档
    「规约先行」限定、08 教培量级 −54%~−70% 与 P4/Phase 5 分标、
    policy_staged 十五五清单指针改逐案核对、dragon_head 题材三问改「全否
    +不确定不降」、revision_momentum 表头效应量对齐调研报告实数、
    issue.md I-004 ✅/I-005 🔄 状态同步、台账宽松加载注释如实化（I-005②
    在册）、调研报告翻身阈值 30 亿→10 亿对齐 08。

## [0.0.15] - 2026-11-02

### Added

- 盯盘子技能 P1（在册股票盘中监控，[references/07-monitor.md](references/07-monitor.md)
  规约 SSOT + [batch/monitor/](batch/monitor/) 参考实现 + LaunchAgent 模板）：
  SKILL.md 边界修订——「不用于盯盘推送」细化为「盘中本地价位监控与本地告警
  允许；禁止第三方推送通道与任何自动交易执行」（用户 2026-11-02 裁定）。
  - `watch.py`：宇宙派生（实盘持仓 + 模拟配置 + 观察票；脱敏——零成本/数量
    落盘，价位锚 SSOT 取 signals.json 组内最新 key_levels，模拟回退 allocation
    三价，缺锚降级告警不静默）/ 价格面轮询（qt 批量快照 30 码/批，按市场独立
    计时与退避；A 股 `v_shXXXXXX` 与港股 `v_r_hkXXXXX` 位序 2026-11-02 实测
    钉住，结构自洽校验防位序漂移，科创 688 量纲为股，缺行出 source_dropped
    事件不静默失明）/ 本地事实告警（osascript，零指令性建议，全部通知尾注
    「待收盘复核·非投资建议」）/ 收盘复核 `--close`（15:10/16:10，事件股与全部
    港股重拉日 K 终判：止损确认/whipsaw/撤回/挂起；day-summary 派生幂等重渲，
    含覆盖区间与缺口、港股源抽检、免责）/ 港股源验证 `--verify-hk`（收盘后
    r_hk × 新浪 rt_hk × 日 K 三方对照，结论持久化）/ launchd 常驻模板（uv 绝对
    路径占位、`KeepAlive.Crashed` 只认信号崩溃故 `--loop` 未捕获异常转 SIGABRT
    自愈、`AfterInitialDemand` 防投机拉起）。
  - `rules.py`：确定性触发引擎——止损击穿/确认/加深穿透/收回（收回后再破属
    事实反转必投递）、触目标与 ±% 异动 episode 语义（越线首报、复位后再报）、
    开盘静默窗、跳空一次性、近触板、T2 限价推演（只推演不写回）、停牌冻结/
    复牌（午休豁免且轮次清零，当日再冻结只留痕）、快照日期守卫（全组最大日期
    判休市、可恢复，不误杀全市场）、港股延迟降级（午休豁免）；抑制链全留痕
    （30min 冷却/单股日上限/组合风暴闸 + 带代码聚合摘要），mech_risk 风险事实
    豁免日上限与风暴闸。量能禁用跨源量比（量纲按板块分裂，错向 100 倍）。
  - 红线落地：永不写 signals.json（当日信号登记唯一归每晚全诊，防 I-004
    重复登记）；盯盘轮询失败只计本地退避、不写共享熔断账本，仅日 K 拉取经
    flock 全局锁 `fetch_state.lock`；selftest fixture 一律合成标的并带「与真实
    portfolio.json 零重合」负断言；scripts/ 四件零改动。
  - 回归：`rules.py --selftest`（36 checks）+ `watch.py --selftest`
    （22 checks）离线钉死，AGENTS.md 测试段第五条非阻塞门禁；变更集经 4 维度
    对抗评审（37 条确认项全部修复或如实改写规约）。
  - P2（局部重诊升级链/建议卡/只降不升三重锚/意见保鲜门/权重分桶不折算）、
    P3（sim SSOT 实施写回/事件独立后验画像）、P4（机械降档判据进 scripts/ 与
    RSI-20261102-01 修法合流、交易日历）规约已预留于 07，未实施。

## [0.0.14] - 2026-11-02

### Added

- portfolio.json 契约锚与漂移可观测（RSI-20261102-01，I-006 防范条机制化）：
  `~/.vibe-stock/portfolio.json` 由仓外手维、仓内无写入方，原降级设计把
  「文件存在但读不出可用持仓」与「文件不存在」同样静默处理，契约漂移（键
  改名、holdings 缺失、元素全不合格、值非数值）会伪装成「无持仓」或整列 —，
  总览持仓列静默失效。现 references/04-report.md 新增「portfolio.json 契约」节作文件契约
  唯一定义处（字段表），loader docstring、selftest 注释与 I-006 只放指针；
  `load_portfolio` 增可选 `problems` 旁路诊断（返回值与降级渲染不变），
  report / postmortem 在文件存在但与契约不符时打一行 `warn:`（只含键名、
  类型与条数，不回显持仓值），文件缺失与合法空表保持静默；04 同节立规约句：
  改动消费此类仓外状态文件时，合入前须对真实文件做 schema 探查 + loader
  端到端重建，Fixture 以 04 契约为准。selftest 增 T11d（diagnose）与持仓
  契约段（postmortem）钉漂移出 warn、缺失/合法/空表静默。持仓格对超 float
  上限的整数字面量（json 可解析、float() 抛 OverflowError）同样降级 —，
  不再让索引重建崩栈。
  Review 补收严（对抗审查 5 项确认）：全角数字 code（\d 兼配 Unicode Nd）
  原漏过形态校验——持仓列 — 且零告警，正是「渲染不出持仓值一律出声」的
  漏网分支，现 isascii 复核后计入不合目录形态诊断；04 降级/漂移枚举补
  「超 float 上限整数」与 code ASCII 形态；T11d 补全角、多种类合一行、
  chmod 不可读（OSError 臂）三 Fixture，负断言扩钉 code/currency 标识类
  值不回显。
  版本依据：报告/索引层可观测性增补（裁决链零改动），按 0.0.x patch 序列
  升 0.0.14。

## [0.0.13] - 2026-11-01

### Added

- index 总览原生持仓列与三价位列（RSI-20261101-01）：实盘持仓登记后
  reports/index.md 手工补的持仓/价位列在每次 report / postmortem 整表重建时
  被冲掉——索引渲染器数据源单一只读 signals.json，持仓与关键价位均无持久化
  事实源。现 report 注册信号时把关键价位三价落进 signal 记录
  （`key_levels={entry_ref, stop, target1}`，与报告「关键价位」节同一函数
  取数，公式即 06 三价纪律：止损 = max(−5% 线, 0.99×20 日低) 取紧、参考
  买点 = max(lo20, 0.97×现价)、目标1 = hi20；报告侧止损显示由 −5% 线收敛
  为取紧口径，与括注「跌破 20 日低/−5%」语义对齐），总览渲染器存在性合并
  `~/.vibe-stock/portfolio.json`（持仓 SSOT，v2 结构：持仓在 `holdings`
  列表，加载归一 `<code>.<market>` → quantity/cost_price，只读合并、永不
  写回、不复制进 signals.json）渲染持仓数量/持仓成本列，并按组内最新
  signal 的 key_levels 渲染参考买点/止损/目标1 列；portfolio.json 缺失/
  损坏/空持仓表整体跳过持仓两列，老信号无 key_levels 与脏持仓字段（非
  数值/非有限值）一律标 — 优雅降级，绝不中断索引重建；老信号不迁移、
  向后兼容。
  版本依据：报告/索引层新增（裁决链零改动），按 0.0.x patch 序列升 0.0.13。

## [0.0.12] - 2026-10-30

### Added

- 批量诊股子技能（RSI-20261030-05）：「指数成分股批量诊股→精选 N 只→深评
  排名→资金配置」方法沉淀为 references/06-batch-scan.md（SSOT）+ batch/
  参考实现。四阶段编排——Stage A 机械粗筛（bulk 接口+回退链、均衡复合分、
  价格可配性硬滤、行业帽选 N+断崖弹性）；Stage B 单股全管线批量（取数强制
  串行——fetch_state.json 整体写竞态属正确性问题；波次+波后健康门+retry；
  意见层宿主子代理并行、纪律与单股一致）；Stage C 门限筛 G1–G5（降档逐档
  如实记录、不足不硬凑）+ 对抗核验（只降不升）+ 三 lens 独立评审 + 确定性
  合分；Stage D 手数贴合+三段建仓+三价纪律+一致性校验。产物 SSOT 落
  `~/.vibe-stock/reports/_scans/<date>-<pool>/`（每类信息唯一落点、digest
  按需派生不落盘、index.md 渲染勿手改），批量登记信号照常走 postmortem
  后验。边界改写：SKILL.md 原「不用于选股批量扫描」改为批量走子技能
  （编排层不触碰单股裁决链），仍不用于回测引擎、自动交易、盯盘推送。
  版本依据：编排层新增（单股裁决链零改动、不触语义口径），按 0.0.x patch
  序列升 0.0.12（minor 预留语义级变更）。


## [0.0.11] - 2026-10-30

### Added

- 港股人民币口径：fx 扩展块与 postmortem `--cny` 展示（RSI-20261030-05）：
  港股诊断的 context-pack 与报告全程无 HKD/CNY 信息、postmortem 对 hk 信号只
  比港币收盘——人民币投资者实际收益含汇兑项（2026 年内 HKD/CNY 约 −5%，量级
  可在 ±2% 判定带附近翻转体感）；现新增第十个零权重扩展块 fx（hk 经 yfinance
  HKDCNY=X 近 1 年日线，取当前值/近 20 日/年内变动，cn 标的以人民币计价恒
  not_supported，取数封装 `hkd_cny_daily` 为 SSOT、熔断走 yf 簇），pack 与
  report 情报面同源渲染人民币敞口行，postmortem `--cny` 对 hk 信号 evaluated
  附 cny_close/cny_chg_pct 展示字段（汇率缺根如实缺省、取数失败不阻断评估）；
  红线明文：汇率不进信号判定、聚合、置信帽、策略 YAML 与 RiskGuard——outcome
  判定与台账归因默认仍按港币，selftest 钉住 fx hk/cn 状态、cny 字段不改变
  outcome、fx 状态扰动不扰质量分/置信帽。

## [0.0.10] - 2026-10-30

### Added

- **基本面锚（目标可达性透镜）**：新 `scripts/lens.py` 纯函数模块 + `prepare
  --cost <持仓成本>`——与短线信号正交的中长期参考，四个免汇率锚：
  ① 参考价隐含 PE = cur_PE×ref/price（比值法免 FX），在 valuation 新增的
  pe_quantiles_5y 分位表（p10/25/50/75/90+n）上插值（带外不外推，标
  above_p90/below_p10 带）；② 共识目标价位置（min/中位/均值/max、离散度、
  ≥参考价家数——etnet 逐券商目标价形态可得；目标价只作区间披露，口径依据
  卖方目标价系统性乐观证据）；③ EPS 90 日修正方向；④ 12 个月零漂移
  first-passage 触及概率（σ=60/120 日已实现波动率年化 ×√252，连续监测口径
  约高估 2–4pp 如实注记，注明「波动可达≠基本面支持」、不进三档）。
  三档结论（支撑不足/中性/有支撑）只由 ①② 决定；离散度>0.8 压置信一档并
  强制披露「分歧大」；**缺数据 abstain/低置信中性，绝不 bearish**；同
  evidence 同输出（确定性）。
- context-pack 新节「## 基本面锚（中长期参考，不进裁决/不进后验）」（入
  16k 护栏 heads 截断元组）；报告「关键价位」后新节「## 目标可达性」（含
  期限正交与免责声明）；lens.json/user_ref.json 只落 workdir（.vs 已
  gitignore，不进全局状态目录）。
- 规约同步：03 新节「基本面锚（透镜）不进裁决」（不进聚合/置信帽/后验，
  极端高估只作 risk.json downgrade 线索）；02 透镜风险分流句；04 目标可达
  性节模板（第 4 条，后续条目重编号）；05 透镜不进后验句；AGENTS 测试口径
  三件→四件（+lens.py --selftest，加门禁属收严）；PIPELINE/SKILL/README。
- lens selftest：隐含倍数免 FX 恒等式、分位插值节点回归与带外不外推、
  first-passage 单调/对称/边界、波动率边界、三档规则边界、缺数据
  abstain/单锚低置信中性、离散度压置信、确定性；diagnose selftest 增透镜
  渲染钉（estimated 出节/abstained 弃权行/无 cost 不出节/报告正交声明）。

## [0.0.9] - 2026-10-30

### Added

- **港股数据面五块接入**（全部免 key 公开源，2026-10-30 逐源实测）：
  - fundamentals（核心 10 分块）：东财 HKF10 主指标 RPT_HKF10_FN_MAININDICATOR
    （经 akshare 币种校正）→yfinance info 兜底；概念键与 A 股 em-fin 对齐
    （EPS/ROE/营收增速/负债率/毛利率/净利率/ROIC/归母净利同比+近 4 期 history），
    另透出 CURRENCY 键（报表币种人民币 vs 行情 HKD，context-pack 单独成行）。
    港股质量分 78→85（usable→good）——数据可用性的如实反映，置信帽只看核心
    三块、口径不变。
  - valuation：A 路 em-hk-ind 具名列快照（RPT_CUSTOM_HKF10，PE-TTM/PB/总市值
    /股息，无位序风险）+B 路百度 5 年分位（stock_hk_valuation_baidu）；qt 港股
    快照因实时字段位序未多标的复核不入链（backlog）。A/HK 两路均新增
    pe_quantiles_5y 分位表（p10/25/50/75/90+n+cur，供估值透镜插值）。
  - research：etnet（逐券商目标价去重取最新/EPS 分→元/评级分布，新簇 etnet）
    →yfinance（目标价互验+eps_trend 90 日修正方向）双源；互差>15% 记 note 不弃；
    etnet 活但零覆盖→yf 兜底标 fallback；东财 reportapi 港股 0 覆盖不入链。
  - notices：em-notice-h（np-anotice ann_type=H 直连）单源；盈警/正面盈利预告
    /股份购回标题简繁两体分型；HKEXnews 权威回退在 backlog。
  - moneyflow：南向持股 RPT_MUTUAL_STOCK_HOLDRANKS 直连（簇 em_datacenter，
    pageSize=10；akshare 封装翻全史禁用）；T-1=披露制度口径（available+note
    注明 HOLD_DATE，超 10 自然日才 stale）；非港股通标的空结果=not_supported。
- **MARKET_CAPS 市场能力表**：块级能力 SSOT 替代 10 处分散 `if market=="hk"`
  守卫；selftest 破坏性钉（未配源块=not_supported、守卫先于网络调用）根治
  「删守卫不换源把 _dc_rows 9201 空结果伪造成 available」的坑。
- **A 股前瞻 EPS 零调用回收**：RPT_WEB_RESPREDICT 既有 EPS1..4+YEAR_MARK
  此前被丢弃，consensus 新增 eps_by_year（2025A=65.85/2026E=67.18 形态）；
  context-pack 研报节新增「目标价统计（中位/均值/离散度）」（港股双源形态）
  与「一致预期 EPS」（港 A 两用）渲染行。
- 港股 context-pack 口径行（无业绩预告制度——无预告≠无雷/南向 T-1/报表币种
  分离）；fundamentals CURRENCY 行；南向持股节渲染。
- CLUSTERS 15→16 簇（etnet）；em 系港股新源键（em-fin-hk/em-hk-ind/dc-hsgt/
  em-notice-h/yf-fin/yf-analyst）归既有簇；diagnose 簇等式钉同步。
- selftest 新增破坏性钉：CAPS 守卫（HK 未配源块必 not_supported 且不计熔断）、
  HKF10 空表不伪 available、etnet+yf 共识合并/高盛去重取最新/互验 note、南向
  T-1 与 .HK 后缀坑、eps_by_year 回收与缺失不虚构、quantile 单调+n 不含占位、
  港股 pack 渲染（南向节/目标价统计/报表币种/港股口径行）。

### Changed

- fetch_fundamentals/FUNDAMENTALS_FETCHERS 按市场分派链（cn/hk 各自链表，
  函数名与签名不变）；notices 链 NOTICES_CHAINS 同构化（港股单源链空结果=
  available 事实）；valuation 双路架构按市场参数化。
- references/01-evidence.md 六块表/扩展块表/16 簇/市场能力表/南向 T-1/forecast
  制度差异/分位表规约句+backlog 八项（qt HK 快照/HKEXnews/CCASS/卖空/回购
  金额/HK 行业/Reverse DCF/theses）；PIPELINE 港股速查重写；README 港股覆盖节。

### Fixed

- 独立评审修复（etnet/yf 数值与终态如实化）：etnet 目标价/EPS 改 `_fnum`
  （01810 实测概览 50 行 33 个 NaN 目标价，此前 NaN 可混入 median/mean/
  dispersion）；目标价全缺时 `target_mean` 除零；中位数改 `statistics.median`
  （偶数长度不再取上中位）；无目标价券商 reports 标题不再落 None；yfinance
  `eps_trend` 无 `currency` 列形态（Yahoo 未回 epsTrendCurrency/旧版库）不再
  KeyERROR 连坐 yf 簇熔断；yf 评级计数 NaN 防 `int(nan)`。
- 无覆盖标的不计熔断（能力边界不变量）：HKF10 未覆盖标的（如 GEM 股）
  datacenter 返回 result=null 经 akshare 抛 TypeError——`_fund_via_hk_em`/
  `_hk_indicator_snapshot` 转 NotSupportedSymbol（fundamentals 换链、估值 A 路
  让位 B 路，不记 em_datacenter 共享簇失败连坐 A 股 dc 块）；etnet 无覆盖标的
  空壳页解包异常（No tables found / list.remove 两实测形态）归零覆盖走 yf
  兜底，不记 etnet 簇失败。
- 港股评级分布渲染：research 共识 rating_dist（etnet 券商原语/yf 四档）分桶
  直出，替代 A 股 buy/add/neutral/reduce 四槽行（缺键硬渲染「减持 0」属虚构
  市场事实）；南向 `_yi`/一致预期 EPS 年份 NaN 防御；`_hk_indicator_snapshot`
  全字段 `_fnum` 对齐；`_fund_via_yf` 兜底口径 TTM note 落实（docstring 承诺
  此前未实现）。
- 港股研报链终态如实：无共识且含失败痕迹时 note 由 all_failed 改 no_consensus，
  tried 补齐「etnet:概览空 / yf-analyst:无覆盖」事实；eps_by_year 改按自身
  非空挂载（etnet 概览空不再连坐丢弃综合盈利预测表）。
- 南向 note 措辞 HOLD_DATE→披露日（该字段实为 TRADE_DATE，note 勿伪字段名）；
  删 `_dc_rows` 死参数 base_url 与 `_research_hk_etnet` 死变量 srt。
- selftest 判据只收严：CAPS↔NOTICES_CHAINS/FUNDAMENTALS_FETCHERS 一致性钉、
  etnet 偶数中位+NaN 目标价钉、eps_trend 缺 currency 列钉、no_consensus
  tried 留痕钉、HKF10/etnet 无覆盖不计熔断钉（breakers 零计数）、港股 pack
  评级分布行钉（含「减持 0」不出现）。
- 文档同步：01-evidence 六块表 fundamentals 港股列改 em_datacenter(HKF10)→
  yfinance（此前残留 not_supported(v1) 失同步）、补市场能力表规约句与 baidu
  港股「近五年」有效坑位（akshare docstring period 域陈旧）；PIPELINE 港股
  HTTP 计数 +8→+12；04-report/archive 版本锚改语义描述（重编号后 0.2.x 锚
  失效）。

## [0.0.8] - 2026-10-30

### Fixed

- postmortem 未知市场跳过守卫 + `--stock` 过滤生效（RSI-20261030-04）：原
  `run()` 把全部 pending 信号的 (market, code) 去重后无条件取日 K，market 不在
  取数链（如快照兜底登记的 `?`）一条即 `CHAINS` KeyError 崩溃、全量后验被
  阻塞；且 `--stock` 实参从未被消费（全量扫描，参数装饰性）。现无有效
  market/code 的记录逐条打印跳过诊断（id/code/market 实际值）、保持 pending
  不动、不借同 code 已知市场的日 K 代评，其余信号照常评估；`--stock` 经
  detect_market 归一后只评该 code 的 pending（识别失败如实报错退出、无匹配
  如实打印且不写文件），缺省保持全量。收尾口径同收紧——全部跳过/未到期时
  如实打印「本次无台账变动」，不落「已更新」失实陈述、不空写台账文件。
- 快照模式登记市场推导（RSI-20261030-04）：原 `register_signal` 对 meta 无
  market 的 evidence（快照模式真实路径——fetch 快照分支不判市场）一律兜底
  `?`，正是后验坏记录的源头；现可推导时经 detect_market 从 meta 的 code/symbol
  推 (market, 归一 code) 成对登记（同源成对防「market 已知而 code 仍是原始
  symbol 形态、取不到日 K」），推不出维持 `?`（与 postmortem 跳过守卫构成双层
  防线）；坑位——合成快照（evals 演示 fixture）勿跑 report 登记信号，推得市场
  后后验将以真实日 K 评虚构基准价、台账遭污染。对立失效匹配对 market 不在取数链的
  存量（`?` + 原始 symbol 形态 code）记录同经 detect_market 归一比对（推不出维持
  不匹配），防归一身份切换后同股对立记录漏失效沦为僵尸 pending。
- 与 0.2.2 报告归档层的合并裁决：快照登记信号带 `snapshot: true` 稀疏标记——
  市场推导后身份虽为 (cn/hk, 归一码)，报告路由不随推导变（仍 `_snapshot/`），
  实盘时间线索引与总览显式排除快照信号（0.2.2 前以 market='?' 天然排除，
  推导后须显式排除，防合成信号混入实盘索引）。
## [0.0.7] - 2026-10-30

### Added

- `scripts/archive.py` 报告归档层：`reports/<code>.<market>/<date>.md` 一股一日一文件，
  同日重跑追加 `vN` 版本，与上一个有内容版本逐字相同的节写「同 vK。」去冗余；快照模式隔离到
  `_snapshot/<code>/`。
- 时间线索引：各股 `index.md`（版本、信号→动作、置信、登记价、T+1/3/5/10 后验）与
  总览 `reports/index.md`，由 signals.json 派生，report / postmortem 后整体重建；
  postmortem 侧重建排在台账落盘之后且失败只告警——派生视图故障不吞后验归因。
- `diagnose.py migrate-reports [--apply]`：平铺旧报告一次性迁入分级布局（默认
  dry-run；CAS + `signals.json.bak-<ts>` 备份；原文件归档 `_legacy/` 不删；可重入）。
  认领容错：缺/非 ISO created_at 跳过不改写、带时区形态转本地 naive、mtime 漂移
  （备份恢复/编辑器重存）回退按最后运行归属内容版并列 anomaly、非规范港码信号
  （含 evaluated 等非 pending 态）一律告警；报告文件解码失败按文件归因中止、
  零节头文件（非工具产物/截断）conflict 原样跳过。
- 信号新增 `report_version`（单日文件内版本号）；迁移还原的丢失版带 `report_lost`。
- 时间线索引增「股票名称」列（信号 `stock_name`：A 股取 qt 全量快照、港股取 qt
  紧凑快照 `s_hk<code>`——紧凑位序三市一致 f[1]=名称，2026-10-30 实测钉住；
  report 另写穿 `names.json` 显示名缓存，存量信号（早于本功能的）经缓存显名；
  解析顺序组内最新非空→缓存→`—`）。

### Changed

- 报告落盘从平铺 `reports/<code>-<date>.md` 改为分级布局（规则见 references/04
  「落盘与跟踪」）；`report_id` 仍为日级 `<code>-<date>`。

### Fixed

- 同日重跑覆盖报告，导致多条信号指向同一份被覆盖的文件（信号→报告指针失真）。
- 港股代码归一：`0700.HK` / `hk0700` 原得 `0700`、`hk00700` 得 `00700`，同一标的
  分裂成两个身份；`detect_market` 统一补 5 位（腾讯资讯 `hk0700` 拼码顺带修正）。
  对立失效比对同步按读时归一：存量 4 位港码旧 pending 信号与 5 位新信号、
  快照存量后缀形态（`0700.HK` / `hk00700`）与新归一码均互通。
- signals.json 解析失败被静默当空列表，下次 report 覆盖全部历史：改严格加载 +
  原子写，损坏时 report exit 2 且零写入。
- report 写盘前无任何身份校验：`.vs/` 残留上一只票的证据/裁决会被写进当前股票
  报告并登记错误归因信号。现三方交叉校验（证据身份 ↔ `--stock`、verdict 绑定
  `stock_code`）不符即 exit 2 零写入，另加代码形态闸门防路径穿越。
- 报告文件日期与信号 `created_at` 各取各的时钟，跨零点运行会对不上：现同取一次
  now（文件日期、版本时刻、created_at 三处一致）。
- 证据块 note 原样内插进报告表格：多行会拆坏表格、伪造单日文件的版本/
  节头，现折单行（rationale 折单行与剥哨兵已由 0.2.1 交付）。

### Notes

- 升级后先跑 `migrate-reports` 预览再 `--apply`；旧平铺路径的外部链接以迁移打印的
  映射为准。601888 2026-10-28 前两次运行的报告在 0.2.2 之前已被覆盖，迁移后如实
  标为丢失版。
## [0.0.6] - 2026-10-30
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
- 合并前独立评审收口（六镜头评审 + 对抗核验确认项）：附录诊断行的
  source/原始输出改走 rationale 同通道处置（剥哨兵+转全角+折单行）——原 %r
  原样回显会把无效意见 signal 携带的哨兵原文逐字写进报告（先存缺口，本 PR
  规约句同爆炸半径内补全）；_one_line 增方括号/反引号转全角，掐断 rationale
  经 markdown 链接/图片语法注入渲染器；快照模式二次推导合并时清除 session
  门控关闭后的残留 vol_ratio_5_projected（不再孤儿穿透渲染出 None/None 分钟
  数的无时段背书外推行）。

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
  - 收严面：高置信空头/中性板不再恒买入族（旧口径 wscore=max(置信×绩效×5)
    与方向无关——绩效中性时板上最高置信 ≥0.70 即恒落买入族，数学恒真），
    单条 ≥0.9 独裁终结；selftest 显式钉 9hold+4sell 板（最高
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

## [0.0.5] - 2026-10-28

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

## [0.0.4] - 2026-10-28

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

## [0.0.3] - 2026-10-28

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

## [0.0.2] - 2026-10-28

### Fixed

- `fetch.py` `detect_market` 接受 7 位前导零 A 股输入（0601888→601888），
  部分行情系统导出沪市代码形态不再被误拒；其余格式行为不变
  （A 股 6 位/sh|sz 前缀、港股 4–5 位/hk 前缀/.hk 后缀、7 位非 0 开头、
  ≥8 位仍拒绝），回归断言并入 `diagnose.py --selftest`。
- 报告渲染：检查清单 ±10%% 双百分号展示修正（先于本版合入 main，补登）。

## [0.0.1] - 2026-10-28

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
