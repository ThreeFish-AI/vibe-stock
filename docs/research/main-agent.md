# 主 Agent（Claude Code 唯一大脑）前期技术与产品调研报告

调研日期：2026-11-06

**方法说明**：本报告由 159-agent 调研流水线产出（三段 Workflow + 主循环统稿）。WF-1「扇出+核验」（138 agent）：9 维并行（A 国内竞品 / B 国际竞品 / C 学术理论 / D 工程实践 / E 模拟盘与回测 / F Claude Code 集成 / G 安全合规 / H 定价产品化 / I 本地 Web 架构），47 个 finder 多模态检索（双语配额）→ 维度内追加轮 loop-until-dry → 每维信源可达性批检 + top-2 事实抽查（独立重走信源）+ 每维 1 个对抗 skeptic（只反驳不辩护、refuted 必须附反证 URL）+ 决策关键主张 3 lens 对抗 panel → 双 lens completeness critic 查漏 + 定向补漏。WF-2「收敛」（3 agent）：语义归并 56 组（646→575 条有效主张）、章节聚类（全量分配零遗漏）、冲突台账 20 对（并读 11 / 降权 7 / open_question 1（妙想自动执行边界，A-15 vs A-18）/ 主循环源码终裁 1（Backtrader 撮合边界，E-69 vs E-78））。WF-3「成文」（18 agent = 12 章草稿 + 3 方案候选 + 3 个 1-lens 评审）：章节草稿并行 + 候选设计 ×3 + 工程/合规/价值三 lens 评审确定性合分。共产出 646 条 findings：confirmed 583、weakened 4、unverifiable 13、补漏未核验 46、panel 证伪 0。降权规则：weakened 按第 13 章修正口径使用；unverifiable 与 gap_fill_unverified 只作线索注记、不作判据；媒体/社区档结论行内标注信源层级；每条结论挂 finding_id 可回溯，语料与台账存 `.temp/wf-mainagent/`（不入库）。配套方案文档见 [main-agent-proposal.md](main-agent-proposal.md)，架构图见 [docs/diagrams/main-agent/](../diagrams/main-agent/)。

**免责声明**：仅供学习研究，不构成投资建议；系统不下单、不改单、不撤单、不保证收益。

## 第 1 章 摘要与结论地图

调研结论六条主线，每条可直接映射到方案文档的对应设计：

① **学术同构性**：头部金融 LLM agent 框架与本仓机制高度同构——多角色出意见、风控否决、LLM 不碰数值与终审已成领域收敛（TradingAgents 五段流水线、FinRobot「models reason, software computes」）；但论文收益声称经不起审计（短窗、窄标的、零成本、前视污染、扩展复现归零），可借鉴的只有机制设计与评测纪律，机制价值靠自家 postmortem 前向自证（第 5 章）。

② **通用 agent 理论**：acting 优于自由推理、自纠错必须有外部 oracle、多 agent 辩论增益大半来自投票、任务级短会话+外置状态接力是 harness 共识——「LLM 只产意见 + 确定性裁决 + 每任务新会话 + 文件态 SSOT」的既定取向获官方文档与顶会论文双侧支撑；盘中重诊禁 LLM 自由反思、经验学习限定结算后短反思（第 6 章）。

③ **集成通道**：headless CLI 子进程为主通道（全旗标本机 2.1.310 实测，`--json-schema` 结构化输出、`--session-id` 确定性派生、预算闸、dontAsk 权限面齐备），Agent SDK 作对照（须 cli_path 钉同一二进制），mcp serve 拒入大脑链路；无人值守风险清单齐备（退出码三段判据、结构化输出静默回退、预算闸事后计价可越限、版本漂移治理），Python+CLI 主线可行且坑位已知（第 7、8 章）。

④ **模拟盘口径**：主流引擎在「触价 vs 严格穿价」上公开分裂，成交假设单独即可反转回测结论（±240bps 量级）；A 股本地化缺口是 T+1+涨跌停三态+费用栈；散户小单滑点由价差主导（5–10bp 固定值起步合理）；免费分钟级数据 A 股可用（五档快照+1 分钟分时），港股标的存在时戳新鲜度门禁阻塞——已裁定的「盘中限价+滑点」口径落地路径明确：严格穿价+悲观序+静态费用栈+T+1 模型（第 9 章）。

⑤ **合规与红线**：单用户本机自用定性下四功能均无法规增量禁止项（无客户、无收费、不向公众提供），绝对禁区是对接真实交易通道；措辞侧防 AI washing（「说做了什么就真做什么」）与免责四件套+AI 归责句；Anthropic 消费条款禁共享登录态——单用户本机是唯一合规形态（第 10 章）。

⑥ **产品与工程形态**：竞品验证了 Skill/MCP 生态与本地大脑形态（moomoo AI Agent Toolkit 官方明示兼容 Claude Code 且智能交易默认模拟盘+实盘二次确认、老虎 tigeropen-skill 可装入 `~/.claude/skills/`）；成本上订阅复用经济成立（单股诊股裸 token 成本美分级；叠加每次 spawn 固定开销后全成本约 $0.3–0.65/次，单只每交易日诊一次月约 $6.5–14 API 等价量级、随实盘只数线性放大，推导估算）；本地 Web 面板选型收敛（浏览器 tab 直连 FastAPI、htmx 轮询起步按需 SSE、沿用 launchd 不引第二套调度器）；差异化四支柱=可解释+后验校准公开+本地 SSOT 与 LLM 零直连审计线+确定性安全壳（第 2–4、11、12 章 → 方案文档）。

![主 Agent 双层架构总览](../diagrams/main-agent/main-architecture/main-architecture.svg)

图 1-1 六条主线汇聚成的方案双层架构（设计落点，机制细节见方案文档 §8）。

## 第 2 章 国内竞品 teardown

本章对问财、妙想、九方、券商 AI 与 OpenClaw 形态的国内产品逐家 teardown，聚焦诊股证据与输出形态、自动交易与条件单边界、模拟盘撮合规则三条轴线。总体图景：头部产品「结构化输出+可溯源」已与 vibe-stock 诊股报告同构，但证据深度浅、免费额度受限；自动执行是持牌券商卖点而非通用能力；各模拟盘公开撮合规则均未见滑点口径。

### 2.1 诊股与投研入口：问财、妙想、九方与长尾

问财诊股接受自然语言、语音与拍照输入，输出基本面/技术面/资金面三视图评分、估值分位与资金流向的结构化清单，声称结论可溯源（媒体评测）（A-01）。长江证券研报（雪球转载）确认 HithinkGPT 为真自研 decoder-only 架构（最高 130B），但上下文联系弱、提问须精确否则答非所问、对个股理解不深、尚不能替代人工投顾（社区转载研报）（A-62）；独立实测补充其额度墙：免费版每日深度思考仅 5 次、200 字（社区实测）（A-09）。

妙想 2025-03-24 全量开放，主打独家信源分级（EDB 数据库/公司公告/权威网站），称每一个回答都提供可追溯依据（媒体）（A-11）。九方智投「AI 诊股王」一键输出市场机会、技术趋势、资金流向、舆情、价值评估五面结论，另有「AI 顶底」择时（App Store 页）（A-34）；官网口径显示「九章」大模型实为融合科大讯飞星火，个股诊断结合 1000+ 量化因子与研报知识库（官方）（A-35）。九方另以全天候直播与短线向量化工具为主，结构化复盘形态缺位（媒体）（A-42）；新京报调查披露其 994 个 MCN 账号 6306 万关注、2025H1 营销开支 6.62 亿元，25800 元/6 月服务每周给 3 只个股买卖指导，退费率 24.6%（媒体调查）（A-43）。

长尾：百度股市通已 301 并入 finance.baidu.com、现标识 FinScope-AI，静态页未见 AI 诊股/盯盘披露（官方）（A-67）；指南针官网无任何 AI 诊股表述，仍为人工内参+300 堂课+电话/短信/弹窗时点服务，亮牌证券投资咨询编号 047183（官方）（A-71）。

### 2.2 自动交易与条件单：从提示到执行的光谱

「事件→执行」已被推到自动执行：妙想炒股 App 宣称设置盯盘偏好与交易指令后「自动跟踪并执行，你只需确认」，并配实盘一键跟投与 7x24 监控推送（App Store 页）（A-15）；富途 2025-12 上线 AI 程式交易，用户设定策略条件与风控规则后由系统自动执行，2026-03 披露 AI Agent 专属 Skills 并从机制上防交易密码暴露给 AI（富途. AI 产品上线新闻稿, as-of 2026-03-13. https://www.futuhk.com/about-us/newsroom/ai-product-launch）（A-32）；TigerGPT 2023-04 上线、2025-03-26 起接入 DeepSeek-R1，个股异动整合行情/资讯/技术走势/舆情四维并给透明推理依据，已通过香港证监会审视，底层模型可由 OpenAI 换为 DeepSeek，印证意见层与 LLM 底座解耦（官方新闻稿）（A-28）。

条件单侧，同花顺覆盖均线/MACD/止盈止损/日涨跌幅等类型（另有回落卖出、反弹买入、拐点交易），但实测触发价≠成交价、跌停无法卖出，且需逐股设置、每日复盘后手动维护（社区实测）（A-51）。

### 2.3 模拟盘撮合规则逐家 teardown

| 对象 | 撮合口径 | 费用与公司行为 | 初始资金与规模 | 信源 |
| --- | --- | --- | --- | --- |
| 同花顺 A 股模拟炒股 | 每 10 秒撮合一次；买入价≥卖一按卖一价成交、卖出价≤买一按买一价成交 | 按品种模拟收手续费；支持分红送转配股 | 初始 20 万元（社区问答佐证） | 官方规则页（A-45） |
| 东方财富模拟组合 | T+1；成交价统一取委托时最新价；涨跌停需对手盘有委托 | 佣金千1双向（含过户费）、印花税千1卖出；分红 R 日到账并代扣 10% 股息税；15:00–17:00 清算不收委托 | 100 万元/组合，每人至多 20 个 | 官方帮助页（A-46） |
| 雪球组合 | 净值型按比例调仓；开盘时段市价即时成交、不支持限价 | 无手续费模拟 | 每人 50 个（同时运行 20 个）、每组合 30 标的、只能关停不可删 | 社区（雪球官方小知识帖）（A-47） |
| moomoo 模拟交易 | 实时行情+虚拟资金，桌面与移动双端 | 股票/期权/期货全品类免费 | — | 官方（A-30） |
| Tiger Trade 模拟盘 | 6.2.0 仅做多美股正股；6.4.7 扩展做空、港股与换汇 | 资金亏完可重置 | — | 官方版本日志（A-31） |

同花顺模拟炒股为独立平台（moni.10jqka.com.cn），与真实行情同步撮合，问财 App 联动并提供官方免费虚拟资金（社区横评，软文来源、事实风险低）（A-06）。九方未见面向公众的独立模拟炒股，「PRO 模拟组合」仅为 139800 元/半年「超级投资家」套餐打包权益、机制未公开（媒体）（A-41）。撮合规则出处：同花顺. 模拟炒股规则页, as-of 2026-11-06. http://www.10jqka.com.cn/virtual_stock/virtual_stock.html；东方财富. 帮助页 Q037, as-of 2026-11-06. http://mobapppages.eastmoney.com/helper/Q037.html。

### 2.4 实测横评、失效模式与评测生态

2024-10 三家横评显示：妙想/蚂小财诊股可覆盖近 4 期财报但妙想不给明确投资建议，i问财指标少、无行业比较、图表解读弱且偶尔出错重复，三家的资产配置建议均不理想（社区横评，早于妙想 2025-03 全量开放）（A-19）。官媒实测将问财/妙想/九方灵犀在热点解读、条件选股、诊股三场景统一锚定为「辅助工具」，所引 83.7% 好评率出自九方自测而非独立第三方（媒体）（A-64）。

评测生态有偏：可检索的 moomoo AI/TigerGPT 评测几乎全为官方社区激励帖或厂商通稿，未见独立实测或负面评测（媒体）（A-33）；moomoo 官方亦自述 AI 走势分析仅为历史相似形态算法三角测量、准确性未经其验证（官方）（A-23）。新京报实测博主采纳 DeepSeek 等五模型荐股首日亏损 1593 元，荐股视频实为引流起号，律师称 AI 荐股亏损无人赔偿（媒体）（A-56）；另有报道 DeepSeek 联网荐股 6 只全跌、推荐理由为 2024 年旧报道且模型自称当前是 2023 年，骗局用 NLP 把「涨停」改「起飞」规避审核（媒体）（A-57）。

### 2.5 OpenClaw 形态的国内落地

财联社报道 OpenClaw 爆火使个人自建 AI 股票分析助手成现象级趋势，形态含定时复盘报告推送飞书/企微、个股深诊、板块热度跟踪、异动提醒，基础部署仅几十元数据费用，券商优势在持牌合规、数据权威、交易闭环（媒体）（A-20）。通达信 TdxClaw（体验测试版）为大厂落地先例：基于开源 OpenClaw 内核的 Windows 桌面投研工作台，7x24 投研与热点资金监测、多 Agent 投研团队、词元积分计费，官方文档自述默认约每 30 分钟心跳请求、持续消耗积分（通达信. TdxClaw 官网, as-of 2026-11-06. https://www.tdx.com.cn/tdxclaw/）（A-68）。

### 对本产品的启示

- 「结构化+每条结论挂可核验证据源」已是问财/妙想验证的主流形态，但竞品证据深度浅、输出无来源标注，八态证据面+确定性裁决可正面竞争（A-01/A-11/A-34/A-35）。
- 竞品模拟盘止步于对手价/最新价撮合与费用模拟、未见滑点口径，盘中限价+滑点是可宣传的拟真度差异点；费用、分红税与清算窗口应对齐东财公开标尺（A-45/A-46/A-47）。
- 自动执行是持牌券商能力，本产品「只提示不执行、不下单」红线应作为合规差异点显性化而非能力短板（A-15/A-32）。
- 条件单「触发价≠成交价+逐股每日手动维护」的痛点，正是「盯盘事件→建议卡+人工确认」可收编的每日工作流（A-51）。
- LLM 直接荐股的责任真空与幻觉失效模式（旧数据当实时、时间认知错乱），印证有界证据包+八态标注+不可信哨兵+免责段的必要性（A-56/A-57）。
- TdxClaw 每 30 分钟心跳持续耗积分的教训，对应无人值守拉起 LLM 的 M3 预算闸须默认关闭、显式开启（A-68）。

## 第 3 章 国际竞品 teardown

本章逐家拆解 Trade Ideas Holly、Danelfin、TrendSpider、TradingView、Bloomberg 及一批新生代 AI 投资助手，聚焦信号机制、回测与模拟成交口径、自动化能力与免责语汇。三条主线贯穿全章：头部信号引擎的回测口径普遍不含价差与滑点，战绩宣称缺独立审计甚至存在回溯重算；规则自动化平台「一套规则 schema 驱动警报、扫描与回测」的架构最值得借鉴；数据巨头已收敛到「通用模型+工具型 agent+专有数据」路线，与本产品「Claude Code 大脑+确定性脚本」选型同向。

### 3.1 信号引擎：Trade Ideas Holly 与 Danelfin

Holly 核心机制是「每夜选拔」：官方口径 60+ 专有策略每晚全量回测并逐参数优化，仅过「高概率线」者次日入选发信号，信号自带代码、入场价、约 3% 止损、目标与持有时间（B-01）。引擎分层：主引擎日内收盘全平，Long Term 窗口把催化剂延续信号延展为多日多周跟踪（手动移除、无自动离场），另有 Grail/2.0/Neo 三引擎各分三档风险（B-03）。形态上是单体「无需配置」助理：无角色分工概念、策略参数专有不可自定义，判断、风控与执行全留用户（B-04）。

战绩口径是这一家族的软肋：官方自评披露 OddsMaker 回测仅用 1 分钟线（非 tick）、不计买卖价差、只覆盖近期常规时段，全站不公布胜率统计，并以「publisher、不构成建议」定位免责（B-08）；StockBrokers 评审（4.5/5）指信号全付费社区共享致拥挤交易限制收益、展示战绩疑似 cherry-picked（媒体评测，B-06）；中文实测称官方宣称约 65% 准确率但无第三方审计，45 天约 280 个信号纸面追踪得 Grail 68–70%、主引擎 62–64%、Neo 52–55%，$50k 账户需额外约 5.5% 年化才覆盖订阅费（媒体评测，B-07）。Danelfin 是反面教材：2025-07 新模型公告披露历史分数被回溯重算，Score 10 年化 alpha 由旧口径 +15% 改写为新口径 +21%，官网宣称成绩并非当时实时输出（B-14）。

### 3.2 规则自动化：TrendSpider 与执行边界

策略测试器为无代码可视化引擎，成交语义是「收盘判定条件、次根 K 线开盘成交」，官方明示零手续费、完美成交零滑点、仅单时间框架（B-21）。多因子警报是表达力核心：嵌套条件树 DSL，组内 Any/All/None 组合、每条件独立时间框架、可跨标的，配 2–30 根 K 线确认窗，官方坑位提示同组互斥条件永不触发（B-22）。Script Manager 让同一条件脚本在警报、市场扫描、策略测试器三端复用，一套规则 schema 驱动三个产品面（B-23）；Sidekick AI 以文字或语音描述自动构建警报，是自然语言编译到确定性规则树的商业先例（B-25）。

执行侧，回测过的策略可克隆为锁定态机器人云端监控（K 线收盘后 40–60 秒判定），触发即发用户自定义 webhook 交第三方下单，同 K 线矛盾信号静音、信号漂移停机（B-24）；旗下 SignalStack 把 webhook 警报路由为 30+ 券商真实/模拟订单（<0.45 秒），免责明示不提供信号/研究/建议（B-71）。评测痛点集中在价格与集成：每档约比 TradingView 贵 4 倍、警报上限 100 vs 1000、券商直连依赖第三方、学习曲线陡（媒体评测，B-29、B-30）。自动趋势线（摆动高低点算法）右键即可挂突破/触碰/反弹警报，「分析新鲜度线」显式标记分析时点与过期（B-28）。

### 3.3 平台基线：TradingView 模拟盘与 Pine 生态

模拟交易全球免费开放，经订单票/DOM/图表交易三入口下单，支持市价/限价/止损单与止盈止损，默认 10 万虚拟美元，2025-01 起限价单可勾 Outside RTH 在盘前盘后执行（B-31、B-37）。关键边界在执行：Pine Script 策略不能直接下单（模拟盘也不行），信号只能经 alert webhook 转外部执行器路由，「信号→模拟成交→后验」的原生闭环是其生态空白（B-33）。分发侧 2026-11-01 起付费 Pine 脚本只能经官方 Marketplace 分发，未入驻作者脚本将被封禁，策略市场走向平台强管制（B-36）；Desktop 原生应用为 Web 功能全集外加多显示器布局与系统原生通知（B-35）。社区教训：免费层模拟行情延迟 15 分钟（2024-06 时点），模拟盘重置会清空全部持仓与历史且不可恢复（社区，B-38）。

### 3.4 数据巨头：Bloomberg 与 LLM 路线收敛

BloombergGPT 三年后由彭博终端产品负责人承认「只是研究模型，实际上没有用于任何产品」（媒体访谈，B-40）。替代路线 ASKB agentic AI（2026-02 beta）混合商业前沿模型、开放权重模型与自研小模型，多 agent 并行检索，查询路由到「能胜任的最便宜模型」，CTO 称 evals 是成败关键（媒体访谈，B-41）；2026-09 进而发布 Enterprise MCP，经 Model Context Protocol 把行情数据与 workflow Skills 接入企业自有 AI 应用（Bloomberg. Data License Plus 产品页, as-of 2026-09-29. https://professional.bloomberg.com/products/data/license/dl-plus）（B-43）。行业综述同向：摩根大通 LLM Suite、高盛 GS AI Assistant、路透 CoCounsel 均走「通用模型+多模型路由+专有数据」，单一自训金融大模型被称为海市蜃楼，「数据而非模型才是资产」（媒体综述，B-44）；路透以开源基座+专有内容训练专有模型（约 4000 万美元），客户产品仍是多模型设计（媒体综述，B-46）。中文综述量化能力落差：投研与资管是 LLM 最被高估的场景（FinGAIA 投资判断约 48.9%），主张「AI 负责萃取与理解，Python/SQL 负责确定性计算」（社区，B-45）。

### 3.5 新生代 AI 投资助手与替代数据平台

国际赛道正从「AI 评分网站」向「对话式 AI 助手+平台化」迁移（媒体评测，B-54），逐家口径如下。

| 对象 | 形态与口径 | 定价 | 信源 |
| :--- | :--- | :--- | :--- |
| Robinhood Cortex | Gold AI 助手+Portfolio Digests 组合驱动因素日报（日多次刷新），免责「informational purposes only/非研究非建议」；另支持自然语言下单（红线反面教材） | $5/月或 $50/年 | 官方（B-51） |
| Intellectia | 每周一盘前 top 10 选股+SwingMax 信号+Alphio 警报；券商直连但「用户对每笔订单与亏损自负」 | 免费层 $0 永久 | 官方（B-63） |
| Magnifi | plain English 选股+200 场景压测+模拟组合+回测，以 SEC 注册投顾（RIA）实体承载建议责任 | 页面未披露 | 官方（B-70） |
| AltIndex | 替代数据（Reddit 声量/流量/招聘）出 0–100 分+日扫千股，宣称全选股 61% 胜率（self-reported），提供 MCP server 与 API | 未见公开证据 | 官方（B-59） |
| QuiverQuant | 国会交易/游说/内幕等 20+ 替代数据集，Premium 含警报与回测，新上线 MCP Server | $25/月（年付 $300） | 官方（B-72） |
| AInvest Aime | 对话式 AI 助手实时选股与研究（双端 App） | 约 $9.99/月（第三方口径，低置信） | 应用商店（B-52） |
| Uptrends.ai | AI 聚合新闻/社媒推送个性化事件与情绪警报，3 个月破 1 万用户（公司通稿口径） | 分档订阅未披露 | 媒体通稿（B-53） |
| Prospero.ai | 自称 10,000+ 模型聚合机构信号，宣称 2025 选股 60% 胜率、年化跑赢 S&P 81%，免责「战绩系模拟非实盘」 | 免费 app | 官方（B-65） |
| Kavout | 官网已无 K Score 产品页，转零售 AI 套件（AI Stock Picker/Financial Agents/InvestGPT 等） | 未见公开证据 | 官方（B-61） |
| Perplexity Finance | 通用 AI 搜索厂商 2024-10 下场个股数据问答（数据源 Financial Modelling Prep） | 随主产品 | 媒体（B-67） |

### 对本产品的启示

- 借鉴 Holly「每夜回测竞争入选」与信号字段完整性（entry/stop/target/hold time）：与 postmortem 后验升降档同构，建议卡字段可直接对齐（B-01、B-03）。
- 拒绝竞品回测口径短板（OddsMaker 无价差、TrendSpider 零滑点）：本产品限价+滑点口径更保守可作卖点；后验记分须锁定信号时点与模型版本，防 Danelfin 式回溯重算（B-08、B-21、B-14）。
- 架构上抄 Script Manager：策略 YAML 单一事实源同构驱动盯盘判据与后验重放，不建两套规则；判据族可升级嵌套 Any/All/None 树+确认窗（B-22、B-23）。
- 战绩披露以全量登记含亏损信号对抗 cherry-picked 质疑；免责语汇借「publisher/informational purposes only/模拟非实盘」句式（B-06、B-08、B-51、B-65）。
- 复用通用模型路线已获基础设施级背书（BloombergGPT 未产品化、AskB 混合路由+evals、Enterprise MCP 及 QuiverQuant/AltIndex 的 MCP server）：差异化押注证据接地与裁决纪律，而非模型本身（B-40、B-41、B-43、B-44、B-59、B-72）。
- 执行边界是红线反面教材集中区：TrendSpider Bots webhook 下单、SignalStack 路由、Cortex 自然语言下单一律不抄，止步本地通知与人工逐笔确认；「信号→模拟成交→后验」闭环可作主 Agent 核心卖点（B-24、B-33、B-51、B-71）。

## 第 4 章 竞品→本产品功能映射与差异化定位

本章把 30 条已核验竞品证据按 Skill/MCP/Agent 形态、置信度呈现、复盘节律、盯盘预警与通知通道四类，映射到本产品（诊股·盯盘·操作策略·模拟盘主 Agent）功能面。主线有二：问财/老虎/通达信/moomoo 已把「Skill/MCP 分发+兼容 Claude 宿主」做成券商标准形态，本地 Claude Code 作大脑消费同类技能无范式障碍；竞品在逐信号置信度、「事件→复核动作」语义链与频率控制三处普遍缺位，是本产品的差异化空间。

### 4.1 Skill/MCP/Agent 开放形态：兼容 Claude 宿主已是券商标准件

问财 SkillHub 是金融域最大规模的 Skill 分发生态先例：技能为 meta.json+instructions.md（SOP+负样本示例）+scripts 三件套，与 Anthropic Agent Skills 范式同构，已汇集数十个官方技能与上百个社区技能（社区）（A-12）；技能以 Prompt 复制或一行命令安装，官方声明兼容 OpenClaw、Claude、ChatGPT、Cursor 等宿主（社区）（A-03），覆盖选股/行情/研报/模拟交易等全品类（社区）（A-13）。券商侧两例：老虎 tigeropen-skill 装入 ~/.claude/skills/、支持 Claude Code 等 8 类工具调用行情/交易/实时推送，文档明示交易前须独立核验（老虎证券. Tiger OpenAI Skills 文档, 2026-09-17. https://docs.itigerup.com/docs/skill）（A-25）；moomoo AI Agent Toolkit 提供 SKILL/MCP/OpenAPI/沙盒模拟交易/CLI 五形态、明示兼容 Claude Code，智能交易默认模拟盘、实盘需二次确认（moomoo. AI Trading 功能页, 2026-11-06. https://www.moomoo.com/au/hans/feature/aitrading）（A-24）。通达信为国产第二例 Skill 市场（提示词安装，弱于三件套）（A-69），其商城另上架「通达信MCP」付费商品（行情软件商售卖 MCP 先例），详情为 SPA 页面待人工核验（A-70）。开源参照：FinRobot 以四层架构+感知-大脑-行动工作流组织金融 Agent，README 免责不用于实盘（A-66）；微软 RD-Agent 以「LLM 提议+Qlib 回测」闭环挖掘因子，声称 <$10 实现 2 倍基准因子库 ARR、不用于实际投资（A-76）。映射：策略 YAML+Skill 封装与大厂路线一致；问财/老虎/moomoo 官方技能可评估为取数与模拟沙盒通道候选（仅限数据与模拟面，交易/实盘面一律禁用——见方案 NR-2），鉴权未披露、接入前须实测（A-03、A-24、A-25）。

### 4.2 可解释性与置信度呈现：从裸信号到三件套

国际竞品在「信号是否携带置信度」上呈三档光谱。Trade Ideas Holly 信号只含入场价/止损/目标价位档，无逐信号置信度或胜率分，置信度仅体现为策略级统计概率叙事与底层策略历史胜率（媒体评测）（B-02），其策略频道流与 TTS 朗读警报是通知 UX 参照（B-09）。Danelfin 以「可见各因子影响」作可解释性卖点，但第三方评测提醒 60%+ 胜率系回测口径、外部无法核验模型（媒体评测）（B-18）。Tickeron 最完整：形态搜索同时给出突破/目标价、置信度档与历史表现算得的「成功概率」，官网无胜率数字披露（B-57）。本产品有界证据包+置信帽+后验记分使裁决链全链路可自证，是黑盒与裸信号都做不到的透明度层级。

### 4.3 盘前/盘中/盘后复盘节律：三工作区与早晚报

复盘节律已有成熟形态，直接对标用户偏好。华泰 AI涨乐按「主 Agent+多专家 Agent」架构切分三工作区：早点听（盘前资讯预判）、特别提醒（盘中信号推送）、任务助手（投研与复盘），另含「事件→原材料→成本→利润」穿透式事件分析（社区）（A-17）。富途牛牛AI 按早晚报（开盘前/收盘后各一版）+周报节律输出，无值得关注信息即不显示解读，完整解读需 Premium 付费（富途. 牛牛AI 帮助中心, 2026-11-06. https://support.futunn.com/topic831）（A-26）。问财复盘主打「短线复盘」问句入口与自然语言回测，输出年化/回撤/超额与月度拆解、策略可保存复用，定位偏短线技术面（媒体评测）（A-07）。Simply Wall St 以 Snowflake 画像+Narratives 论点构建-跟踪-演化框架，配财报/分红/估值/内幕四类日频警报（B-73）。四例验证：按投资周期切分信息架构、固定节律输出、无信息即弃权均成熟，与本产品复盘+弃权可见化设计同构（A-17、A-26）。

### 4.4 盯盘预警与通知通道横评：事件词表成熟、语义链与频率控制缺位

| 对象 | 事件与判据 | 推送通道 | 信源 |
| :--- | :--- | :--- | :--- |
| 同花顺 | 价格/涨跌幅/涨速预警，盘口异动与涨停雷达（连板/炸板/资金异动） | App 推送+微信 | 媒体评测·AI 横评（A-48）；弹窗/铃声（社区，A-04） |
| 东方财富 | 宣称 7×24 全市场监控，推送带异动解读与资金分析的预警，含尾盘拉升/大跌/抢筹 | App 预警+行情订阅 | 媒体评测·AI 横评（A-49） |
| moomoo | 免设置智能盯盘：成交量异动 4 类+价格异动 7 类词表；AI 市场监控器含 AI 多空信号 | App 悬浮条+监控器 | 官方（A-29） |
| 九方智投 | 多空盯盘监控 23 个技术指标+大盘自选异动提醒 | App 推送 | App Store 页（A-36） |
| 雪球 | 股价提醒（买卖目标价）；除权后提醒价不自动重算 | App 内聊天消息，手机 PC 同推 | 社区（A-50） |
| 财搭子 | 一句话建盯盘任务，推送并呈触发条件+实时取值+时间线留痕，不绑券商 | App 内通知 | 媒体评测·自家 AI 营销（A-53） |
| 大智慧 | AI 全链预警为 VIP 付费卖点；首页未见投顾资质与免责 | 付费商城 | 官方（A-72） |
| TradingView | 服务端警报，价格/指标/形态逐标的，标准警报最长存活 2 个月 | App 推送/邮件/webhook 等 | 官方（B-34） |
| Stock Events | 财报/宏观/分红/评级事件日历+自选追踪 | App 推送 | 官方（B-64） |

横评结论：事件词表高度趋同（价格/量能/资金/封板），moomoo 11 类词表最完整、可映射 T0 机械判据族命名（A-29），东财「事件+原因解读+资金佐证」推送与 T0 事实事件+「××复核」短语同构（A-49）；微信/云推送/webhook 为竞品标配，本产品红线禁第三方通道、只走本地 osascript（A-04），TrendSpider 收盘确认与最低 5 分钟粒度可参考复核节奏（B-26）；「事件→候选操作」语义链与频率控制全行业缺位（A-36、A-14），另须防雪球式除权不重算实坑（A-50）。

### 对本产品的启示

- 借鉴问财三件套与老虎「Skill 文档+SDK+CLI」：策略 YAML+Skill 封装+本地 Claude Code 大脑已获大厂验证，问财/老虎/moomoo 官方技能可评估为取数与模拟沙盒通道候选（仅限数据与模拟面，交易/实盘面一律禁用——见方案 NR-2），接入前必须实测鉴权（A-03、A-24、A-25）。
- 拒绝竞品盯盘「指标阈值+异动提醒」止步形态：以 T0 事实事件+「××复核」+机械判据族把「事件→下一步复核动作」语义链做成独有能力，竞品词表只作命名参照（A-29、A-36、A-14）。
- 注意通知通道红线：微信/云推送/webhook 一律不可复制（仅本地 osascript/stdout/落盘），单条通知信息密度向「一张信号卡=一个完整交易计划」看齐（B-09、B-34）。
- 借鉴 AI涨乐三工作区与牛牛AI 早晚报：信息架构按盘前/盘中/盘后切分，复盘固定节律输出并显式承载「无值得关注信息即弃权」（A-17、A-26）。
- 注意盯盘工程坑位：阈值须挂除权/送股事件自动重算（雪球实坑），并在行业频率控制缺位处反向做显式节流声明（A-50、A-14）。
- 借鉴 Tickeron「目标价+置信档+成功概率」三件套，以有界证据包+置信帽+后验记分实现逐信号可自证（B-57、B-02、B-18）。

## 第 5 章 金融 LLM Agent 学术证据

本章汇总金融 LLM Agent 领域 67 条学术与开源证据。主线有二：机制上头部框架与本产品高度同构，多角色出意见、风控否决、LLM 不碰数值与终审已成收敛；口径上论文收益声称经不起审计（短窗、窄标的、零成本、前视污染、复现归零），可借鉴的只有机制设计与评测纪律。

### 5.1 多 agent 交易框架：三锚点机制事实

TradingAgents（Tauric Research. arXiv:2412.20138, 2025-06-03. [Online]. Available: https://arxiv.org/abs/2412.20138；repo 约 12.1 万 star，Apache-2.0）为五段流水线：基本面/情绪/新闻/技术四分析师并行→多空研究员辩论→交易员→激进/中性/保守三立场风控辩论→基金经理批准；agent 间以结构化报告通信防「电话效应」状态腐化；单次预测耗 11 次 LLM 调用+20 余次工具调用（C-01）。repo 原生支持 A 股与港股 ticker、按区域基准记 realized alpha（B-55）；README 声明仅供研究、非投资建议、订单只进模拟交易所（A-73），并承认同票同日两次运行结果可不同、回测不保证匹配已发表数字（C-52）。论文 v1–v7 七版零 ablation，辩论/风控/反思的独立贡献从未量化（C-02）。基金经理终审为单次 LLM 结构化输出调用合成五档评级，仅靠 prompt 反 Hold 偏向与防发言顺序偏置纠偏（C-05），反衬确定性 adjudicate 的必要。

| 对象 | 架构与记忆 | 口径弱点 | 实现可得性 |
| --- | --- | --- | --- |
| FinMem（arXiv:2311.13743，IEEE Trans. Big Data 正刊 2025，S2 引用 279，C-19） | Profiling 性格档案+Memory 分层记忆+Decision 三模块（B-60） | 测试窗整段落入 GPT-4-Turbo 预训练窗且论文未承认（C-15）；零交易成本、单股三动作（C-16） | 论文级设计，无工程化实现 |
| FinAgent（真身 arXiv:2402.18485，KDD 2024；grounding 锚 2402.18488 实为数学论文，引用链须纠偏，C-21） | 双层反思：低层看 K 线与技术指标，高层带买卖点标注图逐笔复盘对错并提炼教训（C-24）；记忆实为按模块三库向量库，无 STM/LTM 术语亦无记忆消融（C-23） | 6 资产逐只、约 145 交易日、无成本假设（C-25） | 官方 repo 仅 7 commits 纯操作指南，第三方复现已替换三库设计（C-29） |

FinMem 深层记忆显式存「累计交易收益、决策过程、成交量与底层原因」并日更（C-13），与 postmortem 台账/绩效因子同构；人格三档风险倾向下 self-adaptive 在 3 日累计收益转负时切保守（TSLA 消融 +54.70%，risk-seeking −19.41%），但双向切换违反只降不升红线（C-14）。开源平台同向收敛：FinRobot V0–V2（8.4k star）收敛于「models reason, software computes」——金融数值全由确定性 Python 算子计算（C-47）；ai-hedge-fund（64.5k star，MIT）paper trading 用 hash 链台账+逐笔审批+kill switch，声明纯教育用途不下单（C-95）；微软 RD-Agent(Q)（NeurIPS 2025）以 LLM 提假设+真实回测反馈闭环研发因子（C-103）。

### 5.2 记忆与自进化：主 Agent 记忆层先例

FinMem 分层记忆按时效组织：浅层日更新闻（Q=14d）、中层季更财报（Q=90d）、深层年报+交易复盘（Q=365d），条目含事件 ID/嵌入/时间戳/层归属（C-11）；清理与晋升用衰减阈值（recency<0.05 清除、高访问晋升深层）替代硬 TTL，Top-K 敏感（K=5 平衡最优、K=10 高而不稳）（C-12）。理论侧，CoALA（TMLR 2024）以模块化记忆+结构化动作空间+通用决策过程刻画语言 agent，signals/ledger、strategies YAML、context-pack 逐格对应情景记忆、语义+程序记忆与工作记忆（C-97）；Wang 等综述的 Profiling/Memory/Planning/Action 四模块为能力自检表正确出处（C-32）。经验结晶范式：ExpeL（AAAI-24）从自采轨迹提炼 insights、推理时召回且无需参数更新（C-100）；AWM 从历史轨迹归纳可复用 workflow 注入上下文，Mind2Web/WebArena 相对成功率高 24.6%/51.1%、跨域泛化 +8.9–14.0 点（C-102），支撑成功轨迹结晶为规约与策略库。

### 5.3 专有金融模型与通用模型的路线之争

BloombergGPT（50B，363B 金融 token+345B 通用 token 混训）权重从未开源（B-39）；EMNLP 2023 行业 track 基准显示二者互有胜负：GPT-4 在 FiQA 情感 88.11 超 BloombergGPT 75.07，NER 反被超过，专有金融模型无全面优势（B-42）。开源侧 FinGPT 走 LoRA 轻量适配（B-69）但 repo 最新模型停在 2023-11，生态重心已转向 agent 编排（C-48）。更根本的否证来自 NeurIPS 2024 Spotlight 消融：三个流行 LLM 时序预测法去掉 LLM 均不降精度、多数反而更好（C-45），LLM 不进数值预测管线有顶会背书。视觉模态：MM-DREX 消融显示烛台图视觉有正增益（去视觉 TR 25.75%→20.11%）但幅度有限且零成本（C-27）；MME-Finance 测得 GPT-4o 烛台图理解仅 58.32%，通用强者不等于金融图表强者（C-28），K 线图只可作辅助情报面、禁入裁决链。

### 5.4 回测口径与前视偏差：收益声称为何不可采信

单篇与复现审计：TradingAgents 收益声称仅基于 2024 年 1–3 月 AAPL/GOOGL/AMZN 三股（SR 最高 8.21），零佣金滑点、对照仅 B&H 与规则策略（C-51）；v1 模拟窗在 v4 起被整体改期而结果表逐字不变（C-06），作者亦自认该 SR 超出自设标尺（SR>3 即优秀）、归因于期间回撤稀少（C-07）。FINSABER（W. W. Li, H. Kim, M. Cucuringu, and T. Ma, "Can LLM-based Financial Investing Strategies Outperform the Market in Long Run?," KDD 2026 Datasets & Benchmarks Track, arXiv:2505.07078, 2026. [Online]. Available: https://arxiv.org/abs/2505.07078）把 FinMem/FinAgent 放入 20 年、100+ 标的扩展回测后原优势消失：FinMem 三组建负 Sharpe、无显著 alpha（p>0.34），B&H 显著占优（p 低至 3e-6）（C-49）；并诊断出 LLM 策略牛市过保守、熊市过激进的 regime 偏向与 FinMem 过度换手（佣金占比达 FinAgent 5–9 倍）（C-50）。领域级审计：ACM survey 的 14 篇实盘回测中位回测期仅 1.3 年、少计成本，却汇总出跑赢最强基线年化 15%–30% 的声称（C-34）；2026-05 审计式综述 19 篇主力中仅 2 篇报时间一致切分、1 篇有显式成本模型、0 篇达最高可复现档（C-35），其综述版另给出切分/成本/幸存者/执行保真四维审计轴（C-57）。

前视偏差机理与自检：Glasserman and Lin（arXiv:2309.17322, Journal of Financial Data Science, 2023. [Online]. Available: https://arxiv.org/abs/2309.17322）实证训练窗与回测窗重叠产生前视（模型记得新闻后走势）与公司常识干扰双偏差，匿名化标题反而更优（C-09）；A. Didisheim, M. Fraschini, and L. Somoza（"AI's predictable memory in financial analysis," Economics Letters, vol. 256, art. 112602, 2025. [Online]. Available: https://www.sciencedirect.com/science/article/pii/S0165176525004392）以无上下文复述历史收益构造 memorization proxy 量化污染（C-17）；B. T. Kelly 等（"Scaling Point-in-Time Language Models," NBER Working Paper 35247, 2026. [Online]. Available: https://www.nber.org/papers/w35247）证明无限制语料 LLM 必然嵌入未来信息、须 point-in-time 口径保时间有效（C-55）。TradingAgents repo 自身持续修补前视（FRED 按 vintage 取数、情绪源按窗口过滤、结算剔除决策日），但 issue #805 指出权重级未来知识无法靠日期约束消除（C-08）。基准与实盘侧证：StockBench（Y. Chen et al., "StockBench: Can LLM Agents Trade Stocks Profitably In Real-world Markets?," arXiv:2510.02209, 2026. [Online]. Available: https://arxiv.org/abs/2510.02209）去污染环境下多数 SOTA LLM agent 跑不赢 buy-and-hold、静态 QA 强不等于会交易（C-56）；Nof1 Alpha Arena 实盘赛（媒体评测）8 模型合计亏约 1/3、32 组仅 6 组盈利，创始人称 LLM 单独赚不了钱、需 harness 与数据平台（C-10）；2026 预印的 LLM 量化研究环 24 个战役仅 2 个过预注册门槛，Sharpe 约 3 的策略在一次性留出集崩至 0.26，其口号「the model proposes, and only trusted code decides」与本产品分工同构（C-39）。

### 5.5 意见边际、角色偏置与安全边界

LLM 意见有实证预测力但会衰减：GPT-4 无金融微调对新闻头条打分即显著预测股价反应与后续漂移（小盘股与负面新闻最强），收益随 LLM 普及而衰减（A-74）。3575 份 SEC 文件×12 个 LLM 实验显示，角色偏置主要发生在对同一证据的解读环节、两种缓解均只部分有效，证据抽取应保持中性层、角色只作用于意见层（C-41）。2026 agentic 量化综述指出预测能力强不必然转化为实盘绩效、多 agent 协同多止于简单聚合（C-46）；ACM survey 中 GPT-3.5 使用率反超 GPT-4、推理延迟使高频不可行（C-38），与本产品单本机 CLI 大脑+盘后形态一致。安全侧 FARSIGHT SoK 审计 15 个学术方案与 7 份开源码：无一描述绕过 LLM 的熔断、均无模型外止损或仓位限制；400 agent 仿真中一条假新闻每轮引发崩盘，模型外自动熔断+硬损失限额方可消除（C-36）。

### 对本产品的启示

- 借鉴 TradingAgents 结构化报告通信与五段流水线骨架，拒绝其 LLM 合成终审：聚合与最终信号必须由确定性 adjudicate 完成（C-01/C-05）。
- FinMem 分层记忆+衰减清理+访问晋升可映射主 Agent 记忆条目 schema 与台账清理，但画像切换只可单向收严（C-11/C-12/C-14）。
- 机制价值不靠论文背书（七版零消融、复现归零），必须靠自家 postmortem 台账前向自证（C-02/C-49）。
- 模拟盘评估钉死时间一致切分+显式佣金滑点+宽标的+长样本，预期对标 B&H 与回撤/Sortino，勿引论文年化数字（C-35/C-50/C-56）。
- 「models reason, software computes」是头部开源平台与本仓的共同收敛：LLM 只产意见，σ√h 预测带等数值全部确定性计算（C-45/C-47）。
- 熔断/止损必须外置于 LLM 的确定性层；后验记分只对信号日之后的真实未来取数即可免疫前视（C-36/C-09）。

## 第 6 章 通用 Agent 理论可迁移结论

本章从通用 Agent 领域提取可直接迁移到「诊股·盯盘·操作策略·模拟盘主 Agent」的结论，覆盖四条主线：推理范式与自纠错边界、多智能体辩论（MAD）正反证据、Anthropic 工程积木与 context engineering、harness 会话形态与记忆分层。四条主线指向同一工程图景：LLM 擅长对确定性事实作 acting 而非无反馈的长链自省，采样与辩论的增益只在确定性 verifier 存在时兑现，任务级短会话加外置状态文件接力是被官方文档与顶会论文双侧验证的 harness 形态。该图景与本产品「确定性脚本编排 + Claude Code 唯一大脑意见段 + adjudicate 裁决链」的既定取向互为印证。

### 6.1 推理范式：acting 优于自由推理，自纠错必须有 oracle

工具循环与自由推理的适用边界已被系统量化：ReAct 类范式在事实核验与决策型任务稳定占优，在纯推理任务反而退步，最佳形态是步数超限即切回纯推理的混合法，且其首要错误源是检索/取数失效而非推理本身（C-59）。反思与自纠错的全部增益依赖机器可核的外部反馈：Reflexion 的高分建立在自写单测与多轮重试上（C-60），无外部反馈的内在自纠错在全部基准一致掉分（C-61），TACL 综论进一步把「验证可靠」定为自纠错成立的唯一前提（C-66）。采样侧结论一致：覆盖率对数线性增长但兑现取决于 verifier（C-63），投票聚合在难 query 上增调用反而降准、最优调用数可由小样本标定（C-65），按难度自适应分配算力优于无差别 best-of-N（C-101）；思考量本身存在负边际（C-62）。

| 研究（出处/日期/URL） | 层级 | 结论与效应量 |
| :--- | :--- | :--- |
| ReAct，2023-03-10，arxiv.org/abs/2210.03629 | 同行评审 | 事实/决策任务占优（FEVER 60.9 vs CoT 56.3、ALFWorld 71% vs 37%）；纯推理 HotpotQA 反输（EM 27.4 vs 29.4），超 7 步切回 CoT 的混合法最佳（35.1）；错误源检索失效占 23%、幻觉 0%（CoT 56%）（C-59） |
| Reflexion，2023-03-20，arxiv.org/abs/2303.11366 | 同行评审 | HumanEval 91%（GPT-4 基线 80.1）依赖自写单测等机器可核反馈与至多 12 轮重试，非 LLM 自评式反思（C-60） |
| “LLMs Cannot Self-Correct Reasoning Yet”，2024-03-14，arxiv.org/abs/2310.01798 | 同行评审 | 无外部反馈自纠错全基准掉分：GPT-3.5 CSQA 75.8→38.1、GPT-4 GSM8K 95.5→89.0；更易把对改错，根因是 LLM 无法判断自身推理对错（C-61） |
| “When Can LLMs Actually Correct Their Own Mistakes”，TACL，2024-12-03，arxiv.org/abs/2406.01297 | 同行评审 | 内在自纠错总体不可靠，仅验证可靠（外部工具/oracle）时成立；部分历史正面证据源于评测方法缺陷（C-66） |
| “The Danger of Overthinking”，2025-02-12，arxiv.org/abs/2502.08235 | preprint | SWE-bench Verified 4018 条轨迹：overthinking 评分与成功率负相关，选低分解 +30% 性能、省 43% 成本；o1 高 effort 仅 +8.1pp 却 3.5 倍成本（实验仅限该基准）（C-62） |
| “Large Language Monkeys”，2024-07-31，arxiv.org/abs/2407.21787 | 同行评审 | 覆盖率随样本数近对数线性增长；有单测/检查器时直接转化为性能，无可靠 verifier 时投票类约 100 样本即平台（仅研究独立采样，不含序贯改进）（C-63） |
| “Are More LM Calls All You Need?”，2024-03-04，arxiv.org/abs/2403.02419 | 同行评审 | 投票类聚合非单调：易 query 增调用提升、难 query 下降；最优调用数可由小样本推出（C-65） |
| Snell 等 compute-optimal 推理，2024-08-06，arxiv.org/abs/2408.03314 | preprint | 按题目难度自适应分配算力：FLOP 等额下小模型可胜 14 倍大模型、比 best-of-N 提效 4 倍以上（前提：该题对模型本有非平凡成功率）（C-101） |

### 6.2 多智能体辩论：增益存疑，投票占大头

MAD 的原始正效应与系统性反证并存，反证侧证据更新且更成体系，核心分歧在「辩论轮本身是否贡献超出多次采样/投票的增量」。

| 研究（出处/日期/URL） | 层级 | 结论与效应量 |
| :--- | :--- | :--- |
| Du et al. 辩论原论文，ICML 2024，2023-05-23，arxiv.org/abs/2305.14325 | 同行评审 | 3 agent×2 轮：GSM8K 77.0→85.0、算术 67.0→81.8；但自反思在 MMLU 反跌至 57.7（低于单 agent）；作者自认辩论更贵，长辩论下模型只关注最近几轮发言（C-67） |
| Smit et al. “Should We Be Going MAD?”，ICML 2024（PMLR v235），2024-07-18，arxiv.org/abs/2311.17371 | 同行评审 | MAD 不能可靠胜过 self-consistency 等多次采样集成，且对超参高度敏感；调 agreement level 后部分 MAD 可反超，属调参问题而非原理失效（C-68） |
| Zhang et al. “Stop Overvaluing MAD”，2025-06-21，arxiv.org/abs/2502.08788 | preprint（立场文） | 5 方法×9 基准×4 模型：MAD 常不胜 CoT/self-consistency 且算力更多；模型异质性是通用解药（C-69） |
| Choi et al. “Debate or Vote?”，NeurIPS 2025 Spotlight，2025-10-23，arxiv.org/abs/2508.17536 | 同行评审 | 理论证明辩论轮不提升期望正确率（信念轨迹为鞅），增益大半来自多数投票；简单集成更强且更可靠（C-70） |
| Chen et al. “When and Why MAD Fails”，2026-07-14，arxiv.org/abs/2510.20963 | preprint | 竞争式辩论退化为 cheap-talk 博弈（发误导信息求胜），共识式辩论过滤有效分歧致过早一致；所提 ColMAD 修复未经独立复现（C-71） |
| Tran & Kiela “Single-Agent LLMs Outperform Multi-Agent Systems…”，2026-04-11，arxiv.org/abs/2604.02460 | preprint | 等思考 token 预算下单智能体可匹敌或超越 MAS；MAS 增益被额外测试时算力混淆（数据处理不等式论证）（C-73） |
| Motger et al. “Multi-Agent Debate Strategies: Survey, Taxonomy, and Challenges”，2026-07-28，arxiv.org/abs/2607.26212 | preprint | 141 项研究综述：MAD 默认配置（静态全连接/逐字交换/短期记忆/投票决议）沿袭惯例而非系统比较；成本感知基准是空白（C-74） |
| MAST 多 agent 失效分类学，2025-10-26，arxiv.org/abs/2503.13657 | preprint | 150 条人工细读+1600+ 标注轨迹提炼 14 种失效模式、归 3 类（系统设计/agent 间失配/任务验证），LLM 标注与人工一致性 kappa=0.88（C-96） |

金融旗舰系统的证据尤其要紧：TradingAgents 论文 v7 全文没有辩论/反思消融表，对辩论增益只有定性断言，主结果仅出自 2024-01-01 至 03-29 三只美股回测（AAPL CR 26.62%/SR 8.21，作者自认 SR 异常高源于窗口期回撤少），每次预测耗 11 次 LLM 调用加 20 余次工具调用（C-72）；其开源 repo 默认配置为 max_debate_rounds=1、max_risk_discuss_rounds=1，即多轮辩论在作者自己的默认形态中也不启用（C-03）。合并判断：若引入多空对抗，1 轮交叉质询是唯一有性价比的形态，加轮成本翻倍且无证据支撑；同时分歧显式化与「取更保守值」的机制必须保留——失效研究指出高风险点是共识吞掉少数派有效预警（C-71）。

### 6.3 Anthropic 六积木、context engineering 与工具面

官方把 workflows（预定义代码路径编排 LLM）与 agents（LLM 动态自管过程和工具使用）二分，选型原则是「找最简方案、只在需要时加复杂度」：workflows 换可预测性与一致性，agents 留给无法硬编码路径的开放问题，代价是成本、延迟与错误复合（Anthropic. Building Effective Agents, 2024-12-19. [Online]. Available: https://www.anthropic.com/research/building-effective-agents）（C-75）。按此定义，五段流水线属教科书式 workflow，主 Agent 对盯盘 T2 复盘等开放任务的接管才是 agent 段。六积木可逐一映射本产品：五段链=prompt chaining、双轨与 T0/T1/T2 事件分级=routing、批量每股出意见=parallelization（sectioning/voting 两变体）、主 Agent 编排=orchestrator-workers、postmortem 记分与画像升降档=evaluator-optimizer——升维路径在积木之内，无需发明新模式（C-76）。

context engineering 侧，官方实证 context rot（token 越多召回越差）并把上下文视为有限资源，三板斧为 compaction（近窗摘要重启，选留有损）、结构化笔记（写到窗外文件再按需拉回）、子代理隔离（净窗探数万 token 只回传 1,000–2,000 token 摘要）（Anthropic. Effective Context Engineering for AI Agents, 2025-09-29. [Online]. Available: https://www.anthropic.com/research/effective-context-engineering-for-ai-agents）（C-89）——有界 context-pack 即 JIT 策展，opinions/verdict 文件即结构化笔记外置。官方多 agent 生产系统的成本量级：agents 约为普通聊天 4 倍 token、multi-agent 约 15 倍；lead 计划须写外部 Memory 防 200k 窗口截断，子代理产物落文件系统以避免 agent 间「传话游戏」（C-78）。工具面规约：面向 agent 的工具要少而整合、返回语义字段而非 UUID、控制返回 token（Claude Code 默认截断 2.5 万），工具描述微调即可带来大幅性能提升（C-94）。治理判据：零例外规则必须交 harness（hooks/deny rules/managed settings）强制执行，CLAUDE.md 只承载模型可裁量的指引——「结果不依赖模型记得或决定什么」（C-81）。

### 6.4 会话形态与记忆分层：fresh context + 外置状态接力

官方与学术两侧对「会话怎么开、状态放哪里」已收敛出一致形态，证据汇总如下。

| 信源（出处/日期/URL） | 层级 | 会话与记忆结论 |
| :--- | :--- | :--- |
| Claude Code memory 文档，2026-11-06，code.claude.com/docs/en/memory | 官方 | 每会话 fresh context；跨会话靠 CLAUDE.md+auto memory（MEMORY.md 索引+主题文件，前 200 行/25KB 自动注入，超限报错强制重写索引）（C-79） |
| Claude Code best practices，2026-11-06，code.claude.com/docs/en/best-practices | 官方 | 1M 窗口+自动 compaction 使上下文耗尽罕见，但聚焦新会话仍更准更省；subagent 价值在并行/噪音隔离/独立评审而非省上下文，委派本身不提升质量、未见原推理的独立评审才有增益；SPEC 写好后应 fresh session 开工；headless `claude -p` 一次性运行即退出（CI/shell 循环形态），`--output-format json` 供程序解析（C-80、C-92、C-82） |
| Anthropic. Effective Harnesses for Long-Running Agents，2025-11-26，anthropic.com/research/effective-harnesses-for-long-running-agents | 官方 | 长程任务 compaction 不够，须任务级会话接力（初始化/续作两种 prompt）+git 提交+进度文件+带 passes 标志的特征 JSON 传递状态；防 one-shotting 与「假完工」两类失败（C-93） |
| “LLMs Get Lost in Multi-Turn Conversation”，2025-05-09，arxiv.org/abs/2505.06120 | preprint | 20 万+模拟对话：多轮较单轮平均掉 39%，主因不可靠性上升；走错方向后不恢复（C-88） |
| SWE-agent，NeurIPS 2024，2024-05-06，arxiv.org/abs/2405.15793 | 同行评审 | 以任务实例为会话单位：每实例新 episode+独立容器，episode 内 100 行窗口+最近 5 条观测裁剪，单实例预算约 4 美元（C-85） |
| Terminal-Bench 2.0，ICLR 2026，2026-01-17，arxiv.org/abs/2601.11868 | 同行评审 | 89 个终端任务各自独立容器+人写参考解+测试验证，任务级隔离是评测界默认形态；前沿 agent 成绩不足 65%（C-86） |
| Long-Horizon-Terminal-Bench，2026-07-09，arxiv.org/abs/2607.08964 | preprint | 46 个长程任务上 15 个前沿模型平均 pass@1 仅 4.3%（最强 15.2%），单任务平均 9.9M token、231 个 episode；长程须拆多 episode+确定性中间检查（C-87） |
| MemGPT，2024-02-12，arxiv.org/abs/2310.08560 | preprint | 借 OS 虚拟内存做分层上下文管理：主上下文 vs 外部上下文，LLM 经函数调用在层间搬数据，支持超窗文档分析与跨会话记忆（C-83） |
| Manus. Context Engineering for AI Agents，2025-07-18，manus.im/blog/Context-Engineering-for-AI-Agents-Lessons-from-Building-Manus | 官方 | 文件系统即终极上下文（无限、持久）；KV-cache 命中率是生产 agent 第一指标，稳定 prompt 前缀+append-only 上下文，缓存输入约便宜 10 倍（C-90） |
| Letta 团队 sleep-time compute，2025-04-17，arxiv.org/abs/2504.13171 | preprint | 睡眠期离线预计算可等精度省约 5 倍推理算力，或提精度 13%–18%；查询越可预测收益越大，多查询摊销再降单查询成本（C-84） |

金融域的三条记忆先例构成正反对照。TradingAgents 开源 repo 的记忆是 append-only Markdown 台账（逐 ticker/日期/评级记决策），5 交易日结算后由快模型产 2–4 句反思（引用原始收益与相对基准的 alpha）按 ticker 限量回注，回测走独立 log 不污染主记忆（C-04）；FinMem 训练阶段不执行交易，用次日复权收盘涨跌作 ground label 回灌记忆，测试期改用 M 日滚动累计收益观察以抑制单日噪声（C-18），其 backbone 消融显示记忆架构增益以强模型为前提——davinci-003 与 Llama2-70b 在动荡期退化为默认 Hold，Llama2 收益 −52.72%（C-20）；CLEF 2026 工作坊实测给交易 agent 加短期反思记忆一致恶化结果，机制是放大 recency bias 与市场噪声（C-64）。三者合并的迁移结论：结构性事实可沉淀为因子画像，「最近对错结论」不应回灌盘中重诊，经验学习应是结算后、限量、短反思的形态。

### 对本产品的启示

- 借鉴：把意见段定位为「对确定性取数事实的 acting」——ReAct 的首要错误源是检索失效（23%）而非推理，取数质量与回退链的优先级高于推理轮数（C-59）。
- 拒绝：盘中无 oracle 时禁用 LLM 自由反思与自我复核，风险覆写走机械判据、LLM 只补 rationale——无外部反馈的自纠错一致掉分，过度思考与成功率负相关（C-61/C-66/C-62）。
- 拒绝：不为「唯一大脑 Claude Code」增设同质多轮辩论——同质辩论是 MAD 最弱形态，确定性裁决聚合≈多数投票已占增益大头，辩论轮的准确率增量默认按零计；同时保留分歧显式化与「取更保守值」，防过早一致吞掉少数派预警（C-69/C-70/C-71）。
- 借鉴：架构沿六积木内的 workflow+orchestrator-workers 演进、最简方案起步；金融红线（只降不升、裁决链不可跳过改写）必须落 adjudicate.py 与 harness 硬门禁（hooks/deny rules），prompt 内红线只是软约束（C-76/C-75/C-81）。
- 借鉴：诊股每票每任务新开 headless 短会话、跨日状态走 ~/.vibe-stock/ SSOT 台账（即外部上下文层），长任务用会话接力+确定性中间检查防「假完工」——多轮长会话平均掉 39%，长程执行是公认瓶颈（C-79/C-88/C-87/C-93）。
- 注意：记忆分层落地为「结算后 postmortem 槽」——因子画像+按 ticker 限量 2–4 句短反思可借鉴，盘中重诊不回灌近期对错结论；批量与多 agent 预算按 15x token 量级预留，agent 间传文件引用而非转述（C-64/C-04/C-78）。

## 第 7 章 工程最佳实践：headless 编排/会话记忆/成本/可靠性

本章汇集把本机 Claude Code 当无人值守「大脑」复用的 D 维工程证据 44 条（全部核验为 confirmed），覆盖编排形态、会话与记忆、成本与限额、可靠性坑册四个侧面；结论一致：官方机制够用，但无人值守必须自建防御工事。

### 7.1 headless 编排形态：一次性进程与外置编排是主流

社区 harness 与中文实践同向选择「每任务一次性 `claude -p` 子进程+外置编排器」而非长驻通道，框架先例则给出正反两面参照。

| 对象 | 形态与要点 | 信源 |
| :--- | :--- | :--- |
| nanika harness | 每阶段全新 claude -p 子进程（prompt 文件传入、认证继承宿主安装态），CLI 响应自带 cache_read/cache_creation 字段可作成本探针（D-11） | 社区 |
| 中文多 agent 实践 | claude -p --worktree + stream-json 起隔离 worker；重试 3 次上限+指数退避+连续 3 次无产出或同错熔断（D-10） | 社区（掘金） |
| vibe-kanban（28.6k star，Apache-2.0） | Rust 后端+本地 Web UI 编排 10+ agent CLI，workspace 独立 branch/terminal；2026-04-10 官宣关停转社区维护，云依赖功能下线、本地 workspace 保留（D-68） | 仓库 |
| Ruflo（原 claude-flow，81.0k star，MIT） | 反例：内嵌 mods+约 406 工具的 stdio MCP server+init 注入约 27 hooks，加重上下文与冷启动（D-79） | 社区 |
| Anthropic 多 agent 研究系统 | lead 并行 3–5 subagent；token 用量约 15 倍于 chat、单独解释 80% 性能方差、复杂查询耗时最多降 90%（D-70） | 官方博客 |

### 7.2 会话生命周期：session_id 是硬通货，resume 有边界

CLI 会话语义：`--continue` 接最近会话、`--resume` 支持 ID/名称/转录绝对路径、`--fork-session` 复制出新 ID，转录按项目目录存 JSONL、默认 30 天清理（Anthropic. Sessions, 2026-11-06. https://code.claude.com/docs/en/sessions）（D-30）。headless `-p` 会话不进交互 picker 也不被 `--continue` 接续，续聊须从 JSON 输出捕获 session_id 再 `--resume`，可跨目录按 ID 恢复（Anthropic. Headless, 2026-11-06. https://code.claude.com/docs/en/headless）（D-31）。resume 只恢复对话/模型/agent/权限模式，`--mcp-config`、`--settings`、`--add-dir`、`--fallback-model` 须重传，崩溃时未完成 tool call 不重跑（D-32）；2.1.310 另有 `--session-id` 预指定 UUID 与 `--no-session-persistence`（仅 -p、免转录不可 resume），会话身份可由编排方确定性分配（D-65）。

坑位：`--resume` 依赖的 sessions-index.json 与磁盘 .jsonl 曾长期失同步（索引按 PID 键控、非干净退出不写索引），官方关为 not planned，复现者索引孤儿率最高 92%（社区）（D-37）；`--continue` 在 2.1.314 引入丢对话回归、2.1.318 修复（D-76）；runner 会话内嵌套 `claude -p` 曾共享宿主 session ID 写坏宿主 transcript，2.1.317 修复（D-81）。

### 7.3 上下文与记忆分层：文件态 SSOT 是官方背书的路线

compaction 后项目根 CLAUDE.md 与 auto memory 从磁盘重注入，skill 正文按 5000 tokens/条、25000 总额截断（保留头部、最旧先丢），path-scoped 规则与嵌套 CLAUDE.md 会被摘要掉（D-33）。官方分层共识：CLAUDE.md 存人写指令（建议 <200 行）、auto memory 存机器学习记忆（MEMORY.md 前 200 行/25KB 载入），但 CLAUDE.md 属上下文非强制配置，无条件拦截须用 PreToolUse hook（Anthropic. Memory, 2026-11-06. https://code.claude.com/docs/en/memory）（D-34），且主会话 auto memory 不注入 subagent（D-34）。Agent SDK 官方文档明示跨进程恢复别依赖 session resume，把结果捕获为应用态传入全新会话更稳健（D-35）；Anthropic 工程博客同向背书：结构化笔记（agentic memory，持久于上下文窗口之外）+子代理隔离大读只回传 1–2k tokens 摘要（D-40）。

auto-compact 不可作无人值守的可靠依赖：2.1.153–2.1.183 多版本复现「上下文到 100% 停摆、需手动 /compact」回归，社区以 CLAUDE_CODE_AUTO_COMPACT_WINDOW 收小阈值自救（社区）（D-38）；中文逆向研究（bundle 反推、非官方确认）给出 200K 窗口阈值约 83.5%（167k tokens）与 3 连败断路器口径（D-39）；2.1.310 已有官方 `--autocompact`（auto 或 100k–1M tokens）可显式设压缩窗口，无需依赖逆向阈值（D-66）。

![状态扩展数据流](../diagrams/main-agent/state-extension-dataflow/state-extension-dataflow.svg)

图 7-1 文件态 SSOT 结论的方案落点：既有状态与新增 `agent/` 唯一新写区的读写矩阵（方案文档 §11）。

### 7.4 成本与限额工程：订阅轨是配额制，预算闸是估算口径

价目锚点：Opus 5.5 输入 $4/输出 $20 per MTok、Sonnet 5.5 $2/$10、Haiku 5.5 $0.10/$0.50（prompt≤100k）、Batch 五折，粗估一次意见段（约 50–100k 输入+2k 输出、无缓存）$0.2–0.45（D-46）；prompt cache 写 5 分钟 TTL 1.25x、1 小时 2x，读默认 0.1x（Opus 5.5/Sonnet 5.5 仅 0.05x、Fable 5.1/Mythos 5.1 为 0.025x），最小 512 tokens、命中免费刷新、并行请求无法命中并发写缓存（Anthropic. Prompt caching, 2026-11-06. https://platform.claude.com/docs/en/build-with-claude/prompt-caching）（D-45）。订阅内主会话 cache 默认 1 小时 TTL、API key 5 分钟，断档超 TTL 后 resume 全量无缓存重算、/compact 在老会话恢复时最贵，缓存按机器+目录为域（官方 code.claude.com/docs/en/prompt-caching, 2026-11-06）（D-36）。

| 机制 | 口径 | 信源 |
| :--- | :--- | :--- |
| --max-budget-usd | 仅 headless print 模式生效；触顶停止剩余后台工作，json 输出含 total_cost_usd 与 per-model 明细，均为客户端估算（D-41、D-42、D-44） | 本机探针+官方文档 |
| 订阅轨预算语义 | Max OAuth 下零 API 计费仍按未公开的 API 等价估算触顶（D-43） | 仓库（#85400） |
| 配额耗尽切换 | 订阅配额中途耗尽即切 API pay-per-token 且 /cost 停止累计，未跟踪成本每会话约 $1–4（D-44） | 仓库（#70225） |
| 限额制度 | Pro/Max 为 5 小时会话限+每周限双轨、Projects 缓存重用计入更少（D-47）；2026-05-06 起 5h 速率限制翻倍并取消高峰限降（D-48） | 官方支持文档+公告 |
| 订阅成本量级 | Max 5x 每周约 140–280 小时 Sonnet 或 15–35 小时 Opus、$200/mo 档约 $120/天 API 等价，单位成本约 API 的 1/10–1/20（旧模型数字仅作量级）（D-49） | 社区（HN） |
| SDK 预算闸可靠性 | 预算顶在 subagent 运行中触发时父查询挂起、无 ResultMessage，per-agent maxTurns 亦不可靠，作者改用外层超时（D-50） | 仓库（sdk-python #1273） |
| 观测与省费旋钮 | OTEL token/cost 指标可按 skill.name 归因（导出变量不被子进程继承）；--exclude-dynamic-system-prompt-sections 提升 cache 复用；2.1.318 起后台 subagent shell 命令 3 分钟自动转后台防 cache 过期（D-67、D-69、D-75） | 官方+本机探针+CHANGELOG |

### 7.5 可靠性坑册：无人值守的失败模式与防御工事

| 坑位 | 现象与防御 | 信源 |
| :--- | :--- | :--- |
| 进程泄漏 | 2.1.255 无人值守跑完后 claude 进程不退出，24 小时泄漏 24 个进程、各耗 2–11% CPU；防御：超时杀进程树+单实例锁+泄漏巡检（D-08） | 仓库（#91642） |
| 版本回归 | 2.1.302 启动挂起连 --version 都无输出（2.1.299 正常），钉回旧版恢复；防御：升级前健康探针（D-09） | 仓库（#105149） |
| launchd 慢启动 | 拉起的 claude -p 一词问答实测约 143s（终端 3s），插件自更新+SessionStart hook 阻塞；--setting-sources project+空目录 WorkingDirectory 降至 2s（D-52） | 社区（#95689） |
| MCP/connector 膨胀 | 订阅登录态下一行健康检查实测 429,388 input tokens/次（claude.ai connectors 工具定义），--strict-mcp-config 降至 2,854（D-53） | 社区（#106413） |
| 版本目录锁 | 长驻交互会话持锁时同版本 headless 启动挂起且不自愈（日志标 NON-FATAL），需 SIGKILL；防御：错峰（D-57） | 社区（#91987） |
| OAuth 竞争 | 同账户 11 个 LaunchAgent 并发 headless 竞争 refresh token：桌面 App 被登出、headless 报 OAuth session expired；防御：错峰或串行化（D-71） | 社区（#98693） |
| 旗标漂移 | CLAUDE_CODE_MAX_SUBAGENTS_PER_SESSION 自 v2.1.224 成 no-op、MCP_DISCOVERY_CACHE 默认值 v2.1.238 前后翻转；防御：升级跑旗标 diff（D-59） | 官方 env-vars 文档 |

版本治理正解：`claude install` 可装指定版本、DISABLE_AUTOUPDATER=1 停后台自更新（手动 update 仍可），本机 versions/ 已共存 2.1.289/294/310 三版本可回滚（D-60）；从 2.1.310 升级应直接跳 2.1.318，避开 2.1.314–2.1.317 的 --continue 回归窗口，2.1.317/318 并带走「多插件 headless 高内存+慢启动」修复（本机 2.1.310 未含）（D-76、D-82）。沙箱兜底：官方 OS 级 sandbox（macOS Seatbelt/Linux bubblewrap）提供文件写白名单与网络 allowedDomains 白名单（默认空表即全禁外联），保护路径恒写禁、沙箱内 Bash 自动放行，但只覆盖 shell 命令、Read/MCP/hooks 在外（Anthropic. Sandboxing, 2026-11-06. https://code.claude.com/docs/en/sandboxing）（D-78）；观测旋钮另有 --include-hook-events（hook 全事件并入 stream-json）与 --debug 类别负向过滤（D-80）。

### 对本产品的启示

- 编排主线采「每任务一次性 claude -p 子进程+外置 Python 编排器+文件态应用状态」，拒绝内嵌 MCP/hooks 重编排与状态寄生于会话历史（D-11、D-35、D-79）。
- 会话身份由编排方确定性分配（--session-id）或每次捕获 session_id 落登记表并同存转录绝对路径兜底，续聊一律 --resume <id>、不用 --continue（D-31、D-37、D-65、D-76）。
- 红线类硬约束不得只写 CLAUDE.md（官方定位是上下文非强制配置），强制点必须落在确定性裁决链与 PreToolUse hook，关键规约句写 SKILL.md 头部防截断（D-33、D-34）。
- 无人值守 launchd 槽标配：--strict-mcp-config 空集、--setting-sources 收敛、外层 wall-clock 超时、单实例锁、泄漏巡检；同机交互会话与多槽并发一律错峰（D-08、D-52、D-53、D-57、D-71）。
- 部署即钉版本+DISABLE_AUTOUPDATER=1，升级前置 --version 健康探针与旗标面 diff，从 2.1.310 直接跳 2.1.318（D-09、D-59、D-60、D-76、D-82）。
- 成本治理双闸：--max-budget-usd（仅 print 模式、订阅轨按 API 等价口径设阈）+ OTEL 按 skill 归因记账；槽位间隔超 1 小时按槽新开会话比长驻 resume 更省（D-36、D-41、D-43、D-69）。

## 第 8 章 Claude Code 三通道集成矩阵与实测

本章在本机 claude CLI 2.1.310（原生 arm64 二进制，--help 全进程 boot 实测 50–70ms）上，对主 Agent「唯一 LLM 大脑」的三条候选集成通道（headless CLI、Agent SDK、claude mcp serve）的通道语义、结构化输出、预算闸、权限信任与版本漂移逐项实测对拍，官方口径以现行文档为准（Anthropic. Headless mode, as-of 2026-11-06. https://code.claude.com/docs/en/headless）（F-04）。总结论：CLI 与 SDK 驱动同一 agent loop，可分别作主通道与对照通道；mcp serve 只是工具桥、不承载推理；无人值守风险集中在退出码单判、结构化输出静默回退、预算闸越限与旗标面漂移。

![主 Agent Loop 六段时序](../diagrams/main-agent/agent-loop-sequence/agent-loop-sequence.svg)

图 8-1 CLI 主通道结论的运行时形态：触发→路由→一次性 CC 会话→断言器→落盘→后验（方案文档 §10）。

### 8.1 三通道定位：大脑通道与工具桥

Agent SDK 官方定位是「驱动同一 Claude Code 二进制的库」（Python/TS），继承内置工具、hooks、subagents、MCP、权限、会话与 skills；非 Python/TS 语言官方建议以 CLI 子进程（-p + json）驱动同一 loop（D-12）（Anthropic. Agent SDK overview, as-of 2026-11-06. https://code.claude.com/docs/en/agent-sdk/overview）。三通道并非同类项：CLI/SDK 把 Claude Code 当 agent loop（大脑），claude mcp serve 只把其工具暴露给外部 MCP 客户端、模型由客户端自备（F-01）。本机实测 mcp serve 的 tools/list 全量暴露 27 个 harness 工具、JSON 102928 字节（约 2.57 万 token 量级）（D-22）；其 tools/call 是无会话工具直通，LLM 推理须经 Agent 工具子会话绕达（D-23）；initialize 仅 0.28s，但 Agent 工具单次最小调用 6.4–9.5s、19668 tokens 且 cache 计数全 0，长驻只省进程启动不省 token（D-29）。该子命令未进官方 CLI reference，属无兼容承诺的未文档化接口（D-24）；社区包装 steipete/claude-code-mcp 反其道只暴露单工具 claude_code、每调 one-shot 子进程，印证「当大脑用单工具 one-shot 而非多工具直连」的社区共识（D-28）。

| 通道 | 本质 | 会话语义 | 认证面 | 主要风险 |
| :--- | :--- | :--- | :--- | :--- |
| headless CLI（claude -p） | agent loop 子进程，每轮一次 spawn | --resume/--fork-session 续话；--input-format stream-json 可单进程长驻多轮（F-40） | 继承订阅 OAuth | stream-json 截断与静默（D-05、D-06）、旗标面漂移（F-30） |
| Agent SDK | 同一二进制的 Python/TS 库 | ClaudeSDKClient 单连接多轮，interrupt/set_permission_mode 控制面（D-18） | Python 版自动寻本机 claude 并继承订阅凭证（D-14） | 捆绑 CLI 与本机版本漂移（D-17） |
| claude mcp serve | 工具桥，模型在客户端侧（F-01） | tools/call 无会话直通（D-23） | 继承宿主进程 | 未文档化（D-24）、EOF 后孤儿进程（D-25） |

### 8.2 headless CLI 主通道：退出码、信号与流协议

-p 退出码契约为「成功 0、失败非零、非法旗标先报 stderr」，但运行内失败（如缺认证）打印为 stdout 的 result，退出码不可单独判定业务成功，须以退出码加 result 信封双判据收口（D-01）。信号上 SIGTERM 使进程以 143 退出且不记录未完成 turn，SIGINT 才是结束当前轮的正道，被中断 turn 可在 resume 时以 CLAUDE_CODE_RESUME_INTERRUPTED_TURN=1 续跑（D-01、D-58）；turn 结束后 -p 仍可等待后台工作，默认 10 分钟 idle 封顶（D-03），但不等待 MCP 后台任务（F-08）。stream-json 是解析骨架：末行 result 定结局；首事件 system/init 带 capabilities 数组（官方明示以 feature-detect 替代版本字符串比较）与 mcp_servers/mcp_server_errors 数组，可作回归门禁（D-02、F-10）；system/api_retry 携带重试进度与错误类别枚举，盘中可实时观测（D-02）。编排可直接以 `/vibe-stock 600519` 形式 prompt 拉起 Skill（F-49）；迭代三角色 prompt 须显式 --system-prompt-snapshot off，否则 system prompt 首请求即定格、--resume 链上改词静默无效（F-43）。两个 open issue 须入册：#101641 下 stream-json 回合结束后约 2 秒即 exit 0、未写完的 stdout 直接丢弃（可致无 result 行甚至 mid-JSON 截断，完整回复在会话转写 JSONL），完成判据须校验 result 行并以转写对账（D-05）；#99194 长驻双向 stream-json 偶发 stdout 静默而转写仍追加，一次性进程加 resume 重建比长驻管道稳（D-06）。CHANGELOG 修复族示警：插件曾使 headless run 越过 --max-turns/--max-budget-usd 不退出、resume 后已批准工具调用曾双跑、磁盘满丢转写仍 exit 0（至 2.1.317 修复）（D-07、D-77）。社区信源 #103865 报告 headless 配齐 bypassPermissions 与 --permission-prompts none 仍间歇挂在无人能答的权限提示，须 watchdog 轮询 claude agents --json 的 waitingFor 字段兜底（D-72，社区信源）。成本面：默认模型单次冷 spawn 写 1h cache 49,407 tokens、计 $0.20（list 牌价估算），是每进程一轮架构的固定成本下界，高频 spawn 须评估 cache TTL 内复用或 --resume 续连（F-59）。

### 8.3 Agent SDK 对照通道：控制面与版本捆绑

SDK 与 CLI 共享同一 loop，「headless CLI 主通道 + Agent SDK 对照」的架构裁定天然可比（D-12）。SDK 独有进程内控制面：ClaudeSDKClient 支持 interrupt/set_model/set_permission_mode/get_context_usage 等原语与流式 prompt 注入，headless 子进程只能杀进程（D-18）；CLI 独有 --bare 与 --bg 后台会话族（agents/attach/logs/stop，--resume 可同 ID 后台续跑），M3 无人值守可评估原生 --bg 替代自管保活（D-63）。error_max_turns/max_budget_usd 中止后可提限 resume 恢复，是无人值守恢复的关键原语（D-13）。落地坑：Python SDK 自动寻本机 claude 并继承订阅 OAuth（TS 版需 setup-token，--bare 不读）（D-14、F-33）；两 SDK 均捆绑自有 CLI（Python 0.2.178 捆 2.1.318，几乎每 patch 即 bump），与本机 2.1.310 版本漂移，对照实验须经 cli_path 钉同一二进制（D-17、F-48）；对照还须显式对齐 system prompt（SDK v0.1.0 起默认最小提示词，需 preset claude_code 复刻）与 settings 继承（隔离靠 setting_sources=[]）（D-16）。HookMatcher 默认「失败即放行」，无人值守风控 hook 须显式 on_failure=block（D-74）。官方 demo 仓 simple-chatapp（React+Express+WebSocket 流式会话）是「本地 Web UI + 流式会话」形态的直接先例，但明示仅限本地开发（D-20）。计费上，2026-05-13 官宣、拟 06-15 生效的程序化用量（Agent SDK/claude -p 等）改走独立月度 credit 池（Pro $20、Max 5x $100、Max 20x $200，耗尽按 API 全价计费或暂停）一议（D-15，媒体评测信源）已被官方暂缓：Anthropic 帮助页载 2026-06-15「paused」，2026-10-07 版仍写订阅登录态下 SDK 与 claude -p「still draw from your subscription limits」，credit 仅适用于 Console API key 形态，页面称「for now, nothing has changed」，属暂缓而非取消，列政策观察项（Anthropic. Use the Claude Agent SDK with your Claude plan, 2026-11-06 复核. [Online]. Available: https://support.claude.com/en/articles/15036540-use-the-claude-agent-sdk-with-your-claude-plan）。D-15 原口径据此降权，不作预算判据。

### 8.4 结构化输出与预算闸

--json-schema 是意见段强类型收口的直接武器：本机 2.1.310 实测返回独立 structured_output 字段承载过 schema 校验的对象、enum 约束生效、退出码 0，机制为合成 StructuredOutput 工具调用，CLI 旗标与 SDK output_format 同源同机制（F-11）。schema 约束面两通道同构：按 draft-07 客户端校验，声明 2020-12 等新方言启动即拒（Pydantic model_json_schema() 默认 2020-12，必须转 draft-7 或剥离 $schema）；支持基本类型/enum/const/required/嵌套/$ref，format 仅作注记（F-12、F-06）；递归 $ref 在 CLI 层可用、比 API strict 层限制清单宽松，但稳妥仍用扁平 schema（F-20、F-13）。两个设防点：strict schema 推导失败会静默回退非严格模式，结果信封/stderr/--debug 均无信号，本地确定性校验不可省（F-14）；Opus 5.5 长 StructuredOutput（10–17KB）高发少一个右括号（27 次尝试 14 次无效），意见段应保持小 schema 短输出（F-16）。校验失败自动重试，超限报 error_max_structured_output_retries，subtype=success 但缺 structured_output 仍须视为失败；重试预算默认 5（F-15、F-54）。预算闸：--max-budget-usd 仅 print 模式生效，按客户端价格表估算而非账单，subagent 花费计入，达限报 error_max_budget_usd（F-17）；订阅 OAuth 登录态下闸同样生效，计量口径为 list 牌价估算而非订阅额度消耗，须以「单次调用估算乘次数」的软预算口径向用户呈现（F-19）。#100111 实测 $1 上限停于 $1.38（3/3 复现）：预算在调用返回计价后才检查，真实上限=cap+最贵单次调用，批量场景须在编排层再加发送前预检闸（F-18）；计价口径随版本漂移（2.1.296 调低 cache read 牌价），预算闸不能作唯一防线（F-35）。订阅下会话美元成本与账单无关，订阅轨审计留 token 数加等效美元即可（F-34）。

### 8.5 权限、信任与认证收敛

无人值守权限标准件：--permission-mode dontAsk 是预定义白名单的锁定模式（会提示的一律拒、allow 规则与只读命令仍跑、会话永不挂起），v2.1.302 起 -p 不指定模式以 Manual 起步（F-24）；--permission-prompts none（≥2.1.259）使本会拒绝的一律拒并告知模型勿重试，stream-json 以 permission_denials 记录全部拒绝，天然是审计流水（F-28）。第三态与挂起态：--permission-prompt-tool 把权限提示路由给指定 MCP 工具应答，与 SDK canUseTool 对偶（F-41）；PreToolUse hook 返回 deny 在包括 bypassPermissions 的一切权限模式下都拦截且先于权限模式检查执行，是裁决链不可绕过、门禁只收严的宿主侧抓手（F-56）；-p 专属第四决策值 defer 结束当前轮并保留 tool call 供宿主收集输入后 resume，模拟盘逐笔确认可走 defer 挂起等人工（F-57）。继承噪音治理：-p 默认无信任对话框地跑项目 hooks、直连 .mcp.json 服务器（F-22），收敛组合为 --strict-mcp-config（只用 --mcp-config 提供的服务器，≥2.1.246 连审批等待一并跳过）加按需注入（F-21、F-27）；--restricted 模式移除 Bash/代码执行/WebFetch、文件工具圈禁工作目录且不动订阅 OAuth，是意见段最小权限候选（F-26）；--safe-mode 一键禁 skills/hooks/MCP 但连 vibe-stock skill 一起禁（F-53）。两处静默失效须门禁核载：--mcp-config 坏项被静默跳过（以 mcp_server_errors 非空作门禁）（F-23），-p 下坏 settings 文件同样静默跳过、须 claude doctor 才能发现（F-61）。MCP 首轮等待：stdio 服务器等到连上为止（MCP_TIMEOUT 默认 30s），编排超时须大于该基线（F-03）。认证分叉是「复用订阅登录态」裁定的最大对撞点：--bare 为官方推荐的脚本/SDK 模式且官方预告将成为 -p 未来默认，但 bare 永不读订阅 OAuth/keychain、只认 ANTHROPIC_API_KEY 或 apiKeyHelper/云厂商自有凭证（F-02 weakened 修正口径），订阅主线暂禁 bare 并列入升级监控（D-04）。认证优先级共 7 级（云厂商>ANTHROPIC_AUTH_TOKEN>ANTHROPIC_API_KEY>apiKeyHelper>CLAUDE_CODE_OAUTH_TOKEN>profile>订阅 OAuth），-p 下 ANTHROPIC_API_KEY 存在即用、会静默脱离订阅计费，编排环境必须显式 unset 并启动时探针认证态（F-31）；.mcp.json 的 ${VAR} 展开对凭证变量一律读空串，是宿主侧既有的防外发防线（F-62）。

### 8.6 版本漂移与可观测性治理

版本漂移先例密集：2.1.311 起 stream-json 控制字符改 \uXXXX 转义、2.1.286 --bare 收紧、2.1.285 与 2.1.302 间 -p 默认 permission-mode 来回漂移（F-37）；本机实测 --permission-mode 枚举已无 default 但 default 仍是隐藏别名，升级必须做旗标面回归（--help 快照 diff 加非法枚举探针）（F-30）；mcp serve 另有 2.1.277 删 TaskOutput 致后台输出不可达、2.1.295 修复的 18 天回归窗（D-26），及 stdin EOF 后孤儿进程的 open issue（本机未复现）（D-25）。治理次序：先钉版本（autoUpdatesChannel=stable 约落后一周且跳过重大回归版、DISABLE_UPDATES 断全部更新路径、claude install 接受精确版本号）（F-44），再以 init.capabilities 特性探测替代版本号比较（F-10），升级前跑 CHANGELOG 扫描（F-37）。可观测面：~/.claude/projects 转录含 sessionId/version/usage token 级字段可作审计留痕，但默认 30 天自动清理，审计链必须当场落盘自己的 stream-json（F-38）；--session-id 预指定 UUID 会被精确回显，可按日/按股票派生 UUID 关联 decision log（F-60）；敏感 run 可 --no-session-persistence 关转录，与编排层自记审计分层互补（F-42）；2.1.318 起 -p JSON 结果带 credential_expires_at 且到期前 10 天告警，登录态到期检测要可编程化须升级 ≥2.1.318（D-73）；result 另暴露 subagent_stats.refused 拒绝计数可作观测面（D-64）；订阅登录下 1M 上下文需 usage credits，单请求超 200K tokens 触发有损自动压缩，证据包须守住 200K（F-50）。

### 对本产品的启示

- 通道定型：headless CLI 子进程为大脑主通道、Agent SDK 仅作对照，mcp serve 拒绝进入大脑链路（工具桥、约 2.6 万 token 固定开销且未文档化）；对照实验须 cli_path 钉同一本机二进制并显式对齐 system prompt 与 settings 继承，否则两通道输出不可比（F-01、D-12、D-22、D-24、D-17、D-16）。
- 完成判据三段式：退出码加 result 信封加 result 行存在（缺一不可），exit 0 不代表业务成功，并以会话转写 JSONL 对账兜底（D-01、D-05、D-06、D-77）。
- 意见段输出收口用 --json-schema 加本地确定性校验双层：schema 收敛 draft-07 扁平子集、success 缺 structured_output 视为失败；strict 静默回退无法自证，RiskGuard 前置的本地校验不可省（F-11、F-12、F-14、F-15）。
- 预算闸按「cap+最贵单次调用」的真实上限建模并叠加自记 token 与硬性次数闸：--max-budget-usd 是 list 牌价估算且事后计价可越限，订阅轨以 token 数加等效美元口径向用户呈现（F-17、F-18、F-19、F-34）。
- 无人值守权限标准件：dontAsk 加精确 allowlist 加 --permission-prompts none，PreToolUse hook deny 作裁决链不可绕过的宿主侧抓手，模拟盘逐笔确认走 defer 挂起等人工（F-24、F-28、F-56、F-57）。
- 版本治理先钉死再回归：stable 通道加精确版本 install 锁二进制，升级门禁=--help 快照 diff 加 init.capabilities 探测加 CHANGELOG 扫描；「-p 默认 --bare」是订阅 OAuth 主线的头号升级观察项（F-44、F-10、F-37、D-04）。

## 第 9 章 模拟盘与回测引擎设计基线

模拟盘（paper trading）的可信度取决于撮合口径的现实性：主流引擎在「限价触价是否成交」上公开分裂，而成交假设单独即可反转回测结论（E-06）。本章按撮合口径、本地化约束与费用栈、滑点、防前视、统计准入、在位形态六面给出设计基线，结论方向一致：撮合、费用、滑点、记账须显式建模并公示口径，默认取保守侧。

![模拟盘生命周期状态图](../diagrams/main-agent/paper-trading-lifecycle/paper-trading-lifecycle.svg)

图 9-1 模拟盘基线的生命周期落点：allocation 导入→三批限价建仓→holding→收盘复核→closed，成交写回经用户逐笔确认（方案文档 §12）。

### 9.1 撮合口径：穿价成交与悲观序

QuantConnect 官方成交模型规定限价买单须 bar 最低价严格低于限价（low<limit）才成交，成交价取 min(开盘价, 限价)，触价不成交、拒绝陈旧数据防前视（QuantConnect. Equity Model, 2026-11-06. https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/trade-fills/supported-models/equity-model）（E-01）；stop 单成交价取 max/min(开盘价, stop 价)±滑点，开盘跳空按更差价格成交，不保证按 stop 价成交（E-02）。Backtrader 把同 bar 收盘成交明示为「作弊」语义（cheat-on-close/open 开关）（Backtrader. Order Creation and Execution, 2023-04-19）（E-39、E-51、E-54）。TradingView 回测参数 backtest_fill_limits_assumption 默认 0 即触价成交，设 N 则要求价格穿越限价 N 个最小变动单位（TradingView. Pine Script Strategies, 2026-11-06）（E-04）；其 paper trading 官方明示零费用且不披露限价/止损成交规则（E-58），第三方拆解指其按屏显价零延迟成交、无限流动性假设或虚增胜率 20–30%（媒体评测）（B-32）。各引擎对照如下。

| 引擎/平台 | 限价成交判据 | 量约束与默认 | 口径倾向 |
| :--- | :--- | :--- | :--- |
| QuantConnect（E-01） | 严格穿价 low<limit，价=min(open,limit) | 预置模型假设完全成交（E-45） | 保守 |
| Backtrader（E-39） | 触价即成交，市价按次 bar 开盘 | 默认无量上限（E-51） | 乐观 |
| zipline（E-50） | bar 收盘价触发 | 固定 5bps+量上限 10%，已停更 | 乐观 |
| vnpy（E-40） | 触价即成交，价=min/max(委托,开盘) | 滑点每手固定值事后扣 | 乐观 |
| 米筐（E-08） | 当前 bar 收盘价（下一开盘可选）. 米筐. 回测文档, 2026-11-06. https://www.ricequant.com/doc/quant/backtest | 25% 量上限、滑点默认 0、涨停买单不成交 | 乐观默认 |
| TradingView 回测（E-04） | 默认触价即成交，N tick 穿越可调 | 无 | 默认乐观 |

效应量：触价即成交被 practitioner 方法学称为回测最常见谎言，同 bar 止盈止损先后不明时应假设止损先发生（悲观序），仅此一项可令年化摆动 ±240bps（媒体评测）（E-05）；同一 VRP 信号 2019–2026 仅改成交假设，SPY 总回报 +7.78%→+61.77%、Sharpe 0.23→1.12，成交口径可完全主导结论（媒体评测，自认未校准）（E-06）；时序上收盘价收盘前不可知，信号后首个可成交价是次 bar 开盘价，同收盘价成交属时序违规（媒体）（E-07）。

### 9.2 A 股/港股本地化：T+1、涨跌停与费用栈

开源引擎仅 rqalpha 内建 A 股 T+1：可卖=持仓-冻结未成交-当日买入（non_closable），日切清零次日转可卖（E-48、E-42）；qlib 内建涨跌停拒单（涨停禁买/跌停禁卖/停牌双向禁）与 100 股手数（E-41）。一字板社区实测：一字涨跌停标记不可成交后多因子回测年化从 40% 砍到不足 10%（单案例）；停牌三规则为不计收益、停牌期间禁卖、复牌按实际开盘价（社区）（E-26）；涨停应三态处理（未触及正常撮合/触及打开按比例+滑点/一字板不成交），且涨停价须按最小变动单位取整而非写 return>=0.1（社区）（E-09）。公司行动先例：rqalpha 先送转（Decimal 重算）再分红（应收按付息日入账），含退市返现与分档红利税（≤1月 20%、≤1年 10%、>1年免）（E-43）。

| 市场 | 费用项 | 现行口径 | 信源 |
| :--- | :--- | :--- | :--- |
| A 股 | 印花税 | 0.05% 卖出单边（2023-08-28 起，此前 0.1%） | 财政部、税务总局. 2023 年第 39 号公告, 2023-08-28. https://fgk.chinatax.gov.cn/zcfgk/c102416/c5211343/content.html（E-10） |
| A 股 | 过户费 | 0.001% 双边（2022-04-29 起，此前沪深 0.002%）（媒体） | 新华网转引中国结算通知（E-11） |
| A 股 | 佣金+规费 | 佣金上限 0.3% 最低 5 元/笔；经手费 0.00341%+证管费 0.002% 双边 | 国新证券. 证券交易佣金收取标准, 2026-11-06. https://www.crsec.com.cn/business/standard.html（E-12） |
| 港股 | 印花税 | 0.1% 双边、向上取整至 1 港元（2023-11-17 起，此前 0.13%） | HKEX. Transaction Fees, 2026-11-06. https://www.hkex.com.hk/Services/Rules-and-Forms-and-Fees/Fees/Securities-(Hong-Kong)/Trading/Transaction?sc_lang=en（E-13） |
| 港股 | 交易所费栈 | 交易费 0.00565%/边+SFC 0.0027%+AFRC 0.00015%+CCASS 0.002%（min 2 max 100 港元）；Investor Compensation Levy 2005-12-19 起暂停勿计 | HKEX. Transaction Fees, 2026-11-06（同上）（E-14） |
| 港股 | 经纪佣金 | 2003-04-01 起自由议价、普遍自设最低收费 | IFEC. Stock trading fees and charges, 2025-07. https://www.ifec.org.hk/web/en/investment/investment-products/stock/stock-trading/stock-trading-fees-and-charges.page（E-15） |

港股最小价位分档且两阶段调降（2025-08-04、2026-08-03，现行 0.25–10 港元档 0.005 港元），0.3 元仙股 1 tick≈167bp，固定 bps 滑点在该价位段失真（HKEX. Reduction of Minimum Spreads, 2026-08-03）（E-55）。竞价结构：上交所 9:15–9:25 开盘集合竞价、14:57–15:00 收盘集合竞价（社区）（E-53）；港交所开市竞价 9:00–9:30、收市竞价 16:00–16:10（社区）（E-52）——「次日开盘价成交」有竞价入口支撑，但港股 16:00 时价不等于收盘价，按收盘价记账须注明收市竞价可达性。

### 9.3 滑点模型：固定 bps 与量相依的分界

机构级标准形来自 Almgren 对花旗机构执行数据的拟合：临时冲击成本 ∝ σ·(参与率)^3/5（η=0.142±0.0062），95% 置信拒绝平方根模型，适用域限美股机构市价单（R. Almgren 等. Direct Estimation of Equity Market Impact, 2005-05-10. [Online]. Available: https://www.cis.upenn.edu/~mkearns/finread/costestim.pdf）（E-16）；A 股 172 亿条 TAQ tick 实证的冲击函数指数约 0.7 且跨股票近似常数（S. Han, L. Wu, Y. Cheng. Equity Market Impact Modeling: an Empirical Analysis for Chinese Market. arXiv:1610.08767, 2016-10. [Online]. Available: https://arxiv.org/abs/1610.08767）（E-17）。但散户口径下二者非主导：滑点特征重要性相对价差 52.47%、冲击仅 3.63%，flat 1–10bp 为常用简化，动态模型收益集中于机构大单与低流动性标的（社区）（E-18）。上界参照：hftbacktest 建模排队位置与双向延迟，但依赖 L2/L3 订单簿 tick，对本产品秒级快照不适用（E-61）；NautilusTrader 回测与实盘共用事件驱动核心、支持队列与概率成交，宜取其概念而非引入（E-60）。港股行情约束（本机探针）：午后开盘 75 秒时 qt.gtimg 快照时间戳仍停早市 11:59:59 且无五档，免费港股行情延迟至少 15 分钟，故限价成交判定须用行情自带时间戳并对延迟做保守惩罚（E-25）。

### 9.4 防前视与幸存者偏差

QuantConnect 研究指南的防前视三件套：动态 universe、point-in-time 数据、无 PIT 数据时退化为 reporting lag（QuantConnect. Research Guide, 2026-11-06）（E-20）；A 股 PIT 可用 Tushare 披露日期表（ann_date/actual_date/pre_date）构造，akshare 接口多无公告日（Tushare. disclosure_date 接口, 2026-11-06）（E-19）。前视偏差五类高频来源：财报滞后（季报 60–90 天/年报 90–180 天）、年初用年末指数名单、公司行动公告前数据、带处理延迟的盘中时间戳、宏观数据修正值（媒体）（E-21）。幸存者偏差效应量：以现存成分重建 NIFTY 小盘 250 回测 2016–2025，年化高估 4.94 个百分点、Sharpe 高估 0.097，成分年换手 82.5%（H. S. Ranse, "Survivorship Bias in Emerging Market Small-Cap Indices: Evidence from India's NIFTY Smallcap 250," arXiv:2603.19380, 2026. [Online]. Available: https://arxiv.org/abs/2603.19380）（E-22）；雪球 NASDAQ100 RSI 案例显示当前成分名单回测被隐形优化，解法为带进出日期的历史成分集（社区）（E-23）。与 LLM 大脑直接相关：Look-Ahead-Bench 以跨市场 regime 的 alpha decay 区分真预测与训练记忆，标准 LLM（Llama 3.1/DeepSeek 3.2）存在显著前视偏差（M. Benhenda. arXiv:2601.13770, 2026-01-20. [Online]. Available: https://arxiv.org/abs/2601.13770）（E-24）。复权一致性：前复权改写全历史序列、回测不可复现且隐含未来信息，经验法则回测用后复权、复权因子单源取（社区）（E-27）。

### 9.5 后验记分的统计准入

统计准入的学术底座是 DSR 族：Deflated Sharpe Ratio 把拒绝阈值设为 N 次独立试验下期望最大 SR，按样本长 T、偏度、峰度校正后输出真实 SR>0 的置信概率，并明言未控制搜索广度的回测 worthless，同文建议以 1/e 律控制试验数（先随机测约 37% 再取首个超越者），并与 Harvey-Liu 阈值互补双报（D. Bailey, M. López de Prado. The Deflated Sharpe Ratio. Journal of Portfolio Management 40(5), 2014. [Online]. Available: https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf）（E-28、E-29、E-37）。MinBTL 定理给出零真实 SR 下 N 配置最大期望 SR 随 N 增长与最短回测年数要求（D. Bailey 等. Pseudo-Mathematics and Financial Charlatanism. Notices of the AMS 61(5), 2014. [Online]. Available: https://www.davidhbailey.com/dhbpapers/backtest-pseudo.pdf）（E-34）。PSR/MinTRL 给出真实 SR 超阈值概率与按观测数计的最短战绩：月频+对冲基金型偏度/峰度需 4.99 年，比正态月频长 54%（D. Bailey, M. López de Prado. The Sharpe Ratio Efficient Frontier. Journal of Risk 15(2), 2012. [Online]. Available: https://www.davidhbailey.com/dhbpapers/sharpe-frontier.pdf）（E-30）。族比较须整族联合检验：White Reality Check 以平稳 bootstrap 检验「最优模型不优于基准」（H. White. A Reality Check for Data Snooping. Econometrica 68(5), 2000. [Online]. Available: https://users.ssc.wisc.edu/~bhansen/718/White2000.pdf）（E-31），SPA 为其学生化+再中心化改进、保守 p 值恒为上界（社区）（E-32）；CSCV 框架输出 PBO 并证明 hold-out 类手段在回测场景不可靠，保留全部配置收益矩阵即可计算（D. Bailey 等. The Probability of Backtest Overfitting. Journal of Computational Finance 20(4), 2017. [Online]. Available: https://www.davidhbailey.com/dhbpapers/backtest-prob.pdf）（E-33）。实现层：quantstrat 的 deflatedSharpe（R）从 audit 环境聚合试验数（E-35），quantstats 的 smart_sharpe 按 √(1+2Σρ) 惩罚自相关（E-57），Ledoit-Wolf 稳健 SR 检验补两策略 SR 差的成对检验空位且官方配发 R/Matlab 代码（O. Ledoit, M. Wolf. Robust performance hypothesis testing with the Sharpe ratio. Journal of Empirical Finance 15:850–859, 2008. [Online]. Available: https://www.econ.uzh.ch/en/people/faculty/wolf/publications.html）（E-59）。实操警示：五输入须同频，年化 SR 混用 per-bar 样本长虚增约 √252 倍；DSR 不修前视、幸存者与成本口径（社区）（E-36）。

### 9.6 在位模拟盘形态与记账层先例

ai-hedge-fund（virattt，64.5k stars，MIT）仅支持回测与 paper trading：成交前强制人工确认、会话记入 hash-chained ledger、声明仅供教育研究禁止实盘，即「模拟盘+逐笔确认+防篡改台账+免责」先例（A-65）。在位竞品同花顺模拟炒股免费、自述与真实行情实时同步、多档虚拟资金，撮合与费率细则未公开、应保守对齐（同花顺. 模拟炒股平台, 2026-11-06. https://moni.10jqka.com.cn/）（E-63）。API 型 paper 引擎基线：Alpaca 限价单触对手方 NBBO 最优价即成交、不与挂单量核对、可成交单 10% 概率随机部分成交、不模拟分红（Alpaca Markets. Paper Trading, 2026-11-06. https://docs.alpaca.markets/docs/paper-trading）（E-56）；IBKR 模拟账户以真实市场条件运行全功能交易，官方声明存在固有执行限制（E-46）。架构先例：QuantConnect 把 fill/slippage/fee/buying-power/settlement 拆为按证券粒度可替换模型、回测与实盘共用同一 Reality Modeling 层，默认模型明示假设高流动性资产（QuantConnect. Reality Modeling Key Concepts, 2026-11-06. https://www.quantconnect.com/docs/v2/writing-algorithms/reality-modeling/key-concepts）（B-56、E-49）。记账层参照：vectorbt 逐 bar 向量化、无排队与部分成交，适合批量筛选不适合逐单记账（vectorbt. Portfolio API, 2026-11-06）（E-44）；Ghostfolio 事件枚举仅 BUY/SELL/DIVIDEND/FEE/INTEREST/LIABILITY 六类、无送转概念（E-47）；Portfolio Performance 以 TTWROR 与 IRR 双口径算绩效、purchases/sales/taxes/fees 四类交易事件、数据 XML 本地存储（Portfolio Performance. 官网, 2026-11-06）（E-64）。

### 对本产品的启示

- 限价撮合采穿价保守口径（low<limit、价=min(open,limit)，止损单 max/min(open,stop)，同 bar 多触发按止损先发生的悲观序），tick 穿越数为可调旋钮、默认不小于 1 tick（E-01/E-02/E-05/E-04）。
- A 股 T+1 照 rqalpha 模型自建（可卖=持仓-冻结-当日买入、日切清零），涨跌停三态、一字板不可成交、停牌冻结、涨停价最小变动单位取整全部内置，引擎移植解决不了本地化缺口（E-42/E-48/E-09/E-26/E-41）。
- 费用栈按市场分段常量建模：A 股卖出 5bp 印花税+双边 0.1bp 过户费+最低 5 元佣金，港股双边 10bp 印花税+费栈+最小价位分档，佣金留用户配置位，跨生效日回测分段（E-10/E-11/E-12/E-13/E-14/E-15/E-55）。
- 散户小单滑点以「价差+保守固定 bps（5–10bp）」起步，量相依冲击（Almgren 3/5 幂律、A 股指数 0.7）留作大额/低流动性升级项；港股成交判定吃行情自带时间戳并对延迟做保守惩罚（E-18/E-16/E-17/E-25）。
- 成分快照回测系统性高估收益（+4.94pp 量级），成分精选只做前向模拟不做历史回溯收益宣称；财报因子以 ann_date 对齐、无 PIT 加 60–180 天滞后，价格库后复权单源存档（E-22/E-23/E-19/E-21/E-27）。
- 后验记分保持确定性脚本（LLM 重放历史窗口有前视污染），DSR 准入线以策略 YAML 版本史登记试验数 N，战绩短于 MinTRL 只标「样本不足」不升档，族比较用整族 bootstrap（E-24/E-28/E-30/E-31）。

## 第 10 章 安全合规与红线映射

本章把 54 条 findings 的法域锚点、执法回流与免责口径映射到四功能与 13 条红线；总体判断：单用户本机自用定性下四功能（诊股/盯盘/操作策略/模拟盘）均无法规增量禁止项，唯一绝对禁区是对接真实交易通道（G-10），措辞侧最大风险是 AI washing 与变相投顾（G-11、A-40）。

### 10.1 境内法域锚点：自用定性划出的合规空间

牌照边界由三层法源钉死：《证券法》(2019) 第 160 条要求证券投资咨询业务经证监会核准、第 120 条禁止任何单位与个人从事证券经纪（G-01），第 161 条另禁咨询机构代理委托人从事证券投资与分享收益（社区：法条镜像）（G-22）；《证券、期货投资咨询管理暂行办法》第 2 条以「有偿+为客户」定义咨询业务，自用无客户无收费不落入监管，对外收费即触第 32 条（G-03）；证监会公告〔2012〕40 号把荐股类软件纳入投顾资质监管（G-05，仅目录级核实，原文未见在线全文）。生成式 AI 侧，未向境内公众提供服务者不适用《生成式人工智能服务管理暂行办法》，2025 年标识办法同构（国家网信办等. 生成式人工智能服务管理暂行办法, 2023-07-10. https://www.cac.gov.cn/2023-07/13/c_1690898327029107.htm）（G-02），对公众服务则走备案轨（问财 HithinkGPT 为首个过备案的金融对话大模型，媒体）（A-10）。数据侧，《个人信息保护法》第 28 条把金融账户列为敏感个人信息（G-04），附则第 72 条个人/家庭事务豁免使本地持仓自用免义务（媒体：DigiChina 译本）（G-30）。港股同构：SFO 第 4 类受规管活动「就证券提供意见」以在港经营业务为触发，本机自用不触发（G-28）。数据源 akshare 声明仅供学术研究、不构成投资建议，自用属条款灰区（G-27）。

### 10.2 境内执法回流：越界荐股案例与 AI 骗局话术

监管实操口径：上海证监局 2025-02-13 对九方云责令改正，认定未登记投顾的员工提供投资建议、营销宣传误导（A-39）；2026-02-09 升级为暂停新增客户三个月，认定直播营销虚假不实等四项违规，明令不得以「投教」名义变相开展投资咨询（A-40）。要点：出建议者须有资质，「投教」变相荐股同样被究责；媒体另披露投资者缴 25800 元购九方服务亏损维权（媒体）（A-61）。江苏证监局风险提示点名以「AI选股」「大数据诊股」「量化交易」概念包装的非法服务，要求核验持牌名录（A-58）。新华社揭露 AI 荐股造假三件套：P 图收益曲线、托晒高收益截图、向不同人荐不同股只晒涨例（媒体）（A-59）；21财经起底「AI量化」资金盘：宣称月收益 150%、后台改数字、五级拉新、资金不进三方存管（媒体）（A-63）。持牌侧范式是资质亮牌：九方挂投资咨询许可证 ZX0023（A-38），同花顺页脚挂「证券投资咨询服务提供：浙江同花顺云软件 ZX0050」（G-08），益盟以 10 余名投顾执业编号亮牌（A-75）；行业横评口径「候选/参考而非买卖指令、决策权归用户」（社区，投顾监管框架表述系转述待核）（A-18）。

### 10.3 美国监管口径：AI washing、内容责任与执法周期

SEC 2024-03-18 对投顾 Delphia 与 Global Predictions 作出 AI washing 执法，事由为虚称「first regulated AI financial advisor」等 AI 能力，合计罚 40 万美元（U.S. SEC. Press Release 2024-36, 2024-03-18. https://www.sec.gov/newsroom/press-releases/2024-36）（G-11），Gensler 定调「说做了什么就真做什么」（B-48）。「AI 自主度」夸大亦被究：Presto 宣称 AI 消除人工接单、实际依赖海外坐席，2025-01 和解认定虚假陈述（媒体：律所分析）（B-49）；FTC Operation AI Comply 后 2025 年再立 12 起以上（媒体）（B-50）。展示纪律先例：SEC 2018-12-21 首罚 robo-adviser——Wealthfront（宣称全程监控税损收割，实际 31% 账户触发 wash sale）与 Hedgeable（不足 4% 账户构造绩效对比）（G-12）。FINRA 24-09 定调技术中立：Rule 2210 内容标准不因内容由人或 AI 工具生成而豁免，内嵌第三方 AI 不豁免监督责任（FINRA. Regulatory Notice 24-09, 2024-06-27. https://www.finra.org/rules-guidance/notices/24-09）（G-13）。SEC 检查局 2026 优先级公告已不提 AI（G-14），但规则与先例仍在，红线按规则常态设计。

### 10.4 免责措辞库：持牌与不持牌厂商句式对比

| 对象 | 免责定位与关键句 | 信源 |
| :--- | :--- | :--- |
| TradingView | 教育娱乐目的+非投资建议+假设业绩+AI 输出免责（G-07、G-19） | 官方条款 |
| Global Predictions | 被罚后整改：LLM 产出 may have bias+AI 仅研究用途+用户复核前置（G-23） | 官方披露页 |
| 富途牛牛AI | 第三方模型生成+不代表平台立场+不构成建议+风险自担四段式（A-27） | 官方帮助页 |
| 九方智投（免费工具层） | 工具信号仅供参考、不构成买卖指令、投顾服务不承诺收益（媒体）（A-37） | 媒体拆解 |
| 东方财富期货（条件单） | 预警仅供参考+不保证成交价+故障损失自担（A-52） | 行业协议 |
| Kavout | 非投顾否认+非买卖建议+绩效假设性三段式，缺 AI 归责句（G-15） | 官方免责页 |
| Trade Ideas | 「Trade Ideas is a publisher」+「Results are not typical」（G-21） | 官网披露 |
| TrendSpider | 全大写 NOT INVESTMENT ADVICE+回测假设无滑点+告警不应完全依赖（G-20） | 官方条款 |
| QuantConnect | 非投顾非券商+AI 生成内容用户复核全责（G-26） | 官方条款 |
| FinRL（开源） | 学术目的+非财务建议+用户自责+咨询专业人士四件套（G-32） | 仓库 README |

国内侧，媒体横评引述问财口径「AI提供的是分析和建议，不是投资建议」（A-08），社区实测问财直接给出个股建议、东财妙想仅作参考筛选（社区）（A-05），头部产品措辞激进程度分化明显。共性：教育/出版定位+非建议否认+假设业绩声明是最大公约数（Danelfin 商店页同口径，商店页）（B-20），AI 归责句（谁生成、可能偏差、须谁复核）仅少数补齐（G-23），是本产品可补位的措辞空档。

### 10.5 平台条款与结构安全位：Anthropic 约束与通道隔离

最贴近本产品的是模型条款：Anthropic AUP 把「个性化买入/卖出/持有/配置建议」列为 High-risk AI Recommendation，须合格人员实质复核并告知接收者 AI 参与，固定规则算法执行豁免（G-24）——本产品 opinions 段由 Claude Code 生成即命中该定义，报告须标注 AI 生成、用户复核即合格人员复核，确定性裁决链恰落在豁免内。消费者条款另禁共享账户登录态与向他人开放账户，「单用户本机+订阅 OAuth」是唯一合规形态，共用面板即违约，多用户化先切 API/Commercial 通道（G-29）。模拟盘锚：同花顺把模拟炒股定性为免费投教练习、虚拟资金+真实行情（G-09）；Alpaca paper trading 以独立端点与不同 API key 实现「订单永不路由真实交易所」，明示不模拟滑点（G-31），我方限价+滑点口径严于该基线。Composer 的自动执行由持牌券商 Composer Securities LLC 承载（G-25），反证永不接执行通道是结构安全位而非妥协；Ghostfolio 自述 personal use、首用户即 ADMIN，单管理员模式可借鉴（G-33）。

### 对本产品的启示

- 借鉴：把「单用户本机自用、永不对外、永不收费」写成显式规约，同时避开投顾许可、生成式 AI 备案与 PIPL 义务（G-03、G-02、G-30、G-28）。
- 拒绝：任何对接真实交易通道的形态（委托报文、券商 API 直连、一键转实盘），模拟盘与实盘双凭据双通道物理隔离（G-01、G-22、G-31）。
- 借鉴：措辞只描述真实机制，把「LLM 只产意见、裁决为确定性脚本」写成公开可核分工说明，即满足反 AI washing 的「说做什么就真做什么」标尺（G-11、B-48、G-24）。
- 借鉴：报告与建议卡免责段采四件套——非投顾定位+不构成投资建议+模拟绩效假设性+AI 生成标注与用户复核前置，并补齐竞品普遍缺失的 AI 归责句（G-19、G-23、A-27、G-26）。
- 注意：保本、收益保障、胜率承诺、精准预测、晒单战绩列入话术黑名单，直接进文案审查与 negative prompt（A-59、A-63、A-58）。
- 注意：后验战绩全样本登记、禁止挑样对比，模拟绩效展示标注假设性；多用户化任何一步先过 Anthropic ToS 与投顾监管双重评估（G-12、G-29）。

## 第 11 章 定价与产品化

本章回答两个问题：同类诊股/盯盘/AI 投研工具以什么价格与计费单位收费，以及「Claude Code 唯一大脑」形态下本产品的真实成本与产品化边界。国际个人付费档年成本带 US$204–2,736/年且 AI 能力普遍置顶档，国内高客单投顾与免费锚并存，而订阅复用路线下单股诊股的 LLM 边际成本仅美分级（H-08, A-55, H-21）。

### 11.1 国际 SaaS 分档定价带

| 对象 | 定价 | 档差与计费口径 | 信源 |
| :--- | :--- | :--- | :--- |
| TradingView | Basic 免费；四档 S$16.65–259.99/月 | 告警 3→1,000 等配额分档；paper trading 免费档即含 | 官方（H-01, H-11） |
| Trade Ideas | Free 延迟档/Standard $127/Premium $254/月，年付 $89/$178 | Holly AI 信号、回测、自动交易仅 Premium | 官方（H-09） |
| TrendSpider | 四档 $59–349/月，无免费档 | 功能全开，按警报 10→400 与回测深度分档 | 官方（H-10） |
| Danelfin | Free 10 报告/月；Plus $25/Pro $70/月 | 2023 评测价，官方页现 403 现价未核实 | 媒体评测（H-04） |
| Composer | Starter 免费/Advanced $10/Pro $32/月 | 按可自动化策略数与节点数分档 | 官方（H-29） |
| Koyfin | Plus $39/Premium $79/Advisor $209–299/月 | 个人档与投顾席位双线 | 官方（H-30） |
| stockanalysis.com | Pro $9.99/月、$79/年 | 免费层月活 500 万+ | 官方（H-40） |
| LuxAlgo | 免费层+四档 $24.99–119.99/月 | AI Ultra 为最贵档 | 官方（H-43） |

个人全栈订阅合成年成本带 $204–2,736/年，均 per-user 单席位（H-08）；数据工具主流价位仅 $79–120/年，AI 溢价须在数据工具价之上另立说服链（H-40）。LLM 按条计费有成熟先例：TrendSpider Sidekick 25 条免费、$49/100 条、$349/1,000 条（约 $0.35–0.49/条）（H-10）。该品类免费漏斗自报上探 1 亿用户，但转化靠图表/告警配额而非 AI 本身（H-34）；券商 moomoo 无 SaaS 订阅档，0 佣金+保证金利差变现、AI 当获客成本（H-05）；托管型 Wealthfront 0.25%/年与 Betterment $5/月起步是另一付费心智锚，本产品不托管，只能对齐 SaaS 月费而非 AUM 费率（H-32, H-33）。

### 11.2 国内付费锚：高客单与免费锚并存

高客单已验证：银河财富星 AI 投顾 30 天 2,888–3,888 元、中信建投蜻蜓点金 2,000 元/月，专家共识仍处「辅助工具」阶段（媒体评测）（A-55）；九方智投官网在售股道智航 32,800 元/半年（约 6,560 元/月）（H-28），其付费矩阵横跨 9,988–139,800 元/半年（媒体评测）（A-44）。另一极是免费锚：问财与东方财富妙想官网均无 C 端公开定价，妙想域名已收敛为机构向 Choice 终端落地页（H-06, H-07）；问财曾被报道设「进阶-专业-企业」付费分层、每日 200 句免费提问（社区信源，文中经营数字无出处仅作线索）（A-21）。国内个人量化的真实付费形态是数据权限年费制：Tushare Pro 注册送 100 分、核心接口 2,000 分门槛、港股日线另收 1,000 元（H-39）；同花顺 Level-2 与 Choice 个人版价目未见公开证据（H-35）。

### 11.3 local-first 与编排层变现先例

投资工具侧，Ghostfolio 以 AGPL-3.0 开源+Docker 自托管（9.7k stars）+官方 Premium 云托管变现，是 open-core 双轨最成熟先例（H-12）；Portfolio Performance 纯本地 EPL-1.0 自 2012 年社区维护至今，证明无营收亦能长跑（H-13）；OpenBB 转型「本地开源引擎+付费企业 Workspace UI」（H-14）。通用工具分层范式：Obsidian 本地个人免费、Sync/Publish/商用收费（H-42）；Raycast 本地 App 免费+AI 订阅 $10/月含 500 credits 与 BYOK（H-31）；LM Studio 本地免费+云订阅 $20/$100（H-38）；Docker Desktop 个人免费、团队按席位（H-45）。大脑层本身无付费先例：Jan 完全免费开源、7.3M+ 下载（H-16）；「编排层开源+用户自带订阅」已被 Happy（MIT，24k stars）与 Cline（零订阅+按量推理或 BYOK）跑通（H-36, H-37）。风险先例：Open WebUI 2025-04 改品牌保留 license（≤50 终端用户豁免），复用开源 AI UI 须查条款（H-44）；Humane AI Pin 服务器关停后设备近乎不可用、云端数据被删，是本地形态抗厂商关停的最硬反例（社区信源）（H-15）。

### 11.4 Claude 成本基线与单次诊股成本

订阅轨：四档 Free/Pro $20/Max $100/Ultra $200 月费，Claude Code 含于所有付费档并与网页端共享 5 小时+周用量池（Anthropic. Claude pricing, as of 2026-11-06. https://claude.com/pricing）（H-19）；API 轨：Haiku 5.5 $0.10/$0.50、Sonnet 5.5 $2/$10、Opus 5.5 $4/$20 每 MTok 输入/输出，批处理五折（H-20）。官方成本基线：企业部署平均约 $13/开发者/活跃日、$150–250/开发者/月，90% 用户低于 $30/活跃日（Anthropic. Claude Code costs, as of 2026-11-06. https://code.claude.com/docs/en/costs）（H-18）。本机探针：单股诊股约 12KB pack+26KB 策略库输入、5KB 输出，API 等价 $0.002（Haiku）至 $0.092（Opus）/股，日 10 股次月约 $10–30，与 Pro 档同量级（token 按混合中英估算非 tokenizer 实测）（H-21）；headless 最小调用每次仍有约 2.8 万 token 固定开销（input 28,464），高频子进程须以 --resume 或常驻会话摊薄（H-41）。重度警示：一次项目级会话 API 等价 $149.25 在 Max $200/月订阅内完成（社区信源）（H-22）；计价趋势上 Anthropic Enterprise 改 $20/席+API 用量、OpenAI Codex 弃按条改按 token，per-message 计费在退场（社区信源）（H-23）；2026-04 Anthropic 曾静默改 pricing 页又快速回滚，订阅权益边界可被单方变动（社区信源）（H-27）。

### 对本产品的启示

- 订阅复用经济成立：单股裸 token 成本美分级（H-21 口径日 10 股月约 $10–30）；叠加每次 spawn 固定开销（约 $0.20，H-41）后全成本约 $0.3–0.65/次，单只每交易日诊一次月约 $6.5–14 API 等价、随实盘只数线性放大（推导估算），须以 --resume 摊薄并核对订阅档配额，API 只作溢出与 M3 无人值守的计费兜底（H-19, H-21, H-41）。
- 商业化落点在编排/数据/裁决层而非大脑层：大脑层免费是行业默认，Ghostfolio「本地免费+云增值」与 Raycast「App 免费+AI credits+BYOK」是可抄形态（H-16, H-12, H-31）。
- 模拟盘不作收费点：TradingView 把 paper trading 放免费档获客（H-11）；AI 能力在国际先例中一律置顶档，对外成本叙事可对标 $178–254/月的 Holly 档（H-09）。
- M3 预算闸以 USD 建模：官方基线 $150–250/月与示例 $0.55/次可作 --max-budget-usd 阈值锚，配额口径可参照 Sidekick 约 $0.35–0.49/条（H-18, H-10）。
- 批量场景防 5h 用量池击穿：单次会话可烧掉月费 3/4，须控 pack 尺寸与子代理数、小任务下放 Haiku，并以会话复用摊薄固定开销（H-22, H-41）。
- LLM 通道抽象为可切换：订阅权益可被厂商单方调整，保留订阅 OAuth 与 API key 双通道兜底，勿硬绑单一计费形态（H-27）。

## 第 12 章 本地 Web 应用架构

本章回答 MVP 形态裁定（Python Web 后端+本地前端面板）下的四个架构事实：UI 用什么壳、数据怎么流、进程谁守护、本机服务怎么自保。60 条 findings 全部核验通过且指向一致：浏览器直连本地 Python 服务成本最低、与 Python 主线摩擦最小；180 秒级 tick 下轮询/SSE 足够；现有 launchd 体系可直接延伸，无需第二套调度器。

### 12.1 形态选型：桌面壳出局，浏览器 tab 是最短路径

Electron 官方进程模型要求 main+renderer 双进程常驻，每开一个 BrowserWindow 再新增一个携 Chromium 渲染栈的 renderer，Python 后端还需外挂子进程（I-01）；本机实测 VS Code 33 个 Helper 进程 RSS 约 2.7GB、Slack 6 进程 765MB（重复计共享页，实耗更低）（I-42），单用户本机面板走此路线内存与打包体量最高、进程链最长。Tauri 虽以系统原生渲染器把包体压到 600KB 级，但打包 Python 后端须走 externalBin sidecar：pyinstaller 产物按 target-triple 逐架构备齐、经 shell 插件 spawn+stdout 通信（I-02），引入 Rust 构建链与跨架构二进制管理成本。对照组是浏览器直连：FastAPI 同进程经 StaticFiles/app.frontend() 直接托管前端（含 client-side routing），uvicorn 单进程一个端口即可服务，无跨语言 IPC、无桌面壳打包（I-03）。纯 Python 路线上，NiceGUI（MIT，16.3k★，FastAPI+Vue/Quasar 底座、内置周期 timer）可作 MVP 免前端构建链的起步选项（I-40）；要独立窗口时 pywebview（BSD-3，原生 webview 开窗、可直指本地服务 URL）是 tab 与 Tauri 间的轻选项（I-41）。弃坑反面教材：pydantic/FastUI 官宣项目 inactive（I-56），头部自托管财务面板 Maybe Finance 亦已停止维护（I-55），UI 层不应押注非活跃的小众抽象层。

### 12.2 开源面板先例：只借形态与接口切面

| 对象 | 形态与技术栈 | 数据面 | AI 接口 | 借鉴边界 |
| :--- | :--- | :--- | :--- | :--- |
| Ghostfolio | NestJS+Angular+Prisma+PostgreSQL+Redis，Docker 自托管 PWA，9.7k★活跃（I-12） | 伴跑 Postgres+Redis 两服务 | Bearer REST 之外提供实验性 MCP server，AI 客户端可读组合、导活动、改现金余额（I-13） | AGPL-3.0 传染，组件不可搬；「AI 可读写组合」一等接口切面可抄 |
| Portfolio Performance | Java/Eclipse RCP 桌面，EPL-1.0（I-05） | 单个 .portfolio 文件：XML/Protobuf+zip+可选 AES-128/256（I-14） | 无 | 「单文件+口令加密」最小落盘先例；报告两族信息架构（Performance 六节+Statement of Assets）可对齐报告分级（I-15） |
| OpenBB | Python 3.11–3.14 平台，openbb-api 起 FastAPI@127.0.0.1:6900 供 CLI/Workspace/Excel/MCP 消费（I-16） | — | 本地 REST 供多前端与 MCP | 75.1k★验证「本地 Python REST+可插拔前端」；license 字段 NOASSERTION，只借架构勿依赖其 UI |
| Jesse | Python 3.11+FastAPI/uvicorn+Postgres+timeloop，MIT（I-17） | Postgres | 内置本地 MCP server 接 AI 助手，支持 paper trading 多账户 | 同构度最高先例：Python Web 面板+paper trading+MCP 供 AI 调用 |
| rotki | Python 后端，桌面包+Docker 双形态，AGPLv3（I-43） | 本机 SQLCipher 加密库 | 本地 MCP server | Python+本地加密库+双形态+MCP 完整分层可对标 |
| Wealthfolio | Tauri+Rust+SQLite(SQLCipher)+React/Recharts，一条命令以本地 Axum 起 Web UI（I-18） | SQLite 可加密 | 自带 MCP AI 助手 | 「桌面壳与本地 Web 同底座」双模与 SQLite+SQLCipher 现成模式 |
| Fava | Flask+cheroot，pip 安装后一条命令起 localhost:5000（I-49） | Beancount 文件账本即 SSOT | 无 | 与「面板读台账」最同构：文件 SSOT+单命令本地面板，服务端渲染即够 |
| InStock | Python 3.11+MySQL+自研 Web(localhost:9988)+Docker（I-54） | MySQL | 无 | 验证 A 股本地面板可行；其自动交易与明文账密正踩红线，代码不可借鉴 |

生态面：awesome-selfhosted 金融类目成建制的自托管投资面板仅 Ghostfolio 一家，其余多为记账/预算工具（I-19，社区信源）；AlternativeTo 上 Ghostfolio 替代榜前列是 Wealthfolio（35 赞）与 Portfolio Performance（13 赞）两个本地/桌面应用，且有用户嫌 PP 太 technical（I-20，社区信源）。成熟先例极少，本产品不必对齐大而全面板，可专注诊股/盯盘/模拟盘差异化，UI 起步应轻交互、少专业术语。

### 12.3 实时通道与通知：轮询/SSE 即够，告警留在服务端

现有盯盘已零推送依赖：watch.py 自研 while True+time.sleep 循环（按市场 next_due 退避）+osascript 本地通知+monitor 台账落盘，面板读台账即可渲染，通知独立于 UI（I-09）。SSE 是纯 HTTP 的单向 server→client 流，EventSource 内置断线自动重连与 Last-Event-ID 续传；限制是非 HTTP/2 下每浏览器每域名并发仅 6 条（Chrome/Firefox 均 wontfix），localhost 单页一条连接不受影响（I-21，MDN. Using server-sent events, 2026-09-03. https://developer.mozilla.org/en-US/docs/Web/API/Server-sent_events/Using_server-sent_events）。工程实践侧，多数 Web 应用以单向读为主，SSE 与 WebSocket 同效且成本低得多（I-22，媒体/厂商技术博客信源）；sse-starlette 为 FastAPI 提供生产级 EventSourceResponse，默认 15s ping 保活，已知坑集中在 nginx/CDN 代理层而 localhost 无此层（I-27）。轮询路径更简：htmx 官方把 hx-trigger="every Ns" 轮询作为内建核心机制（286 状态码可叫停），SSE 与 WS 反而是扩展支持（I-23），180s 级 tick 用纯 GET 轮询即有近实时观感。WebSocket 先例恰是反证：freqtrade 本地 API 以 REST 为主、另设 WS 端点订阅秒级成交广播（I-26），本产品 tick 频率约其 1/180 且回传走普通 POST，WS 双向能力是纯开销。文件事件桥用 watchfiles 盯台账目录变更触发 SSE，与盯盘进程零耦合（I-45）。告警可靠性受平台约束：Chrome 可整体冻结后台标签页（frozen 态下 JS 定时器与 fetch 回调停止），Web UI 不能承担告警职责（I-48）。可靠通道在服务端：AppleScript display notification 可从任意脚本进程向 Notification Center 投递（I-24）；terminal-notifier（7.4k★）证明 CLI 后台进程投递 macOS 通知成熟，硬约束是必须 GUI 登录会话、SSH/root daemon 不可投递，调度须用 LaunchAgent 而非 root LaunchDaemon（I-25）。localhost 属 potentially trustworthy origin，前台可调浏览器 Notifications 作补充，但程序化通知正被收紧（I-51）。

### 12.4 进程守护与并发：沿用 launchd，不引第二套调度器

本仓三套 LaunchAgent 已是完整守护体系：monitor 用 KeepAlive{Crashed,AfterInitialDemand}+交易时段 30min 补拉槽+ThrottleInterval 60，一次性槽（outlook/postmortem）跑完即退（I-10）；launchctl 实测 monitor 在跑、调度全靠日历槽位、RunAtLoad=false（I-36），故 Web 后端不应复制调度，只做展示+手动触发并尊重 watch.lock 与取数串行锁。launchd 细节决定守护写法：RunAtLoad 官方建议避免、日历触发睡眠错过时唤醒后合并补发（I-35）；WatchPaths 被官方标注 highly discouraged（race-prone 可能漏事件），台账文件触发处理走进程内 watchfiles 而非 launchd（I-52）；job 退出默认连坐杀同 process group 残留子进程，守护重启会杀掉在跑的 claude 子进程，须显式裁定 AbandonProcessGroup（I-57）；未设 ProcessType 时系统施加轻度 CPU/IO 节流，本仓三份 plist 均未设（I-58）；停 job 先 SIGTERM、超 ExitTimeOut 即 SIGKILL（I-59）；KeepAlive.NetworkState 已不再实现，断网感知放代码层（I-60）；交易时段可用 caffeinate -i 防 idle sleep，但电池+合盖不可靠，须保留收盘兜底（I-50）。进程内调度：APScheduler 4.x 标注 pre-release 勿用于生产、稳定线 3.x（I-11），官方 FAQ 明示多进程共享 job store 会重复执行（I-31）；fastapi-utilities 的 repeat_every/repeat_at 是最轻进程内先例，但多 worker 无去重保护（I-39）。FastAPI 官方口径：重后台计算才需 Celery+RabbitMQ/Redis（本场景过度设计），小任务用 BackgroundTasks（I-32）；启停统一挂 lifespan（on_event 已 deprecated）（I-33）；阻塞 I/O 端点声明为 def 走线程池，防拖死事件循环（I-38）。uvicorn --workers 默认 1，本地面板固定单 worker 即规避调度重复（I-34）；uvicorn.workers 已弃用，单进程裸跑即可（I-61）；--timeout-graceful-shutdown 须设在 launchd ExitTimeOut 窗口内，给在途诊股任务留收尾（I-34、I-59）。子进程纪律：asyncio 子进程对象被 GC 时仍在跑的子进程会被杀、wait() 无超时须配 wait_for，claude CLI 子进程须长期持引用、超时用 asyncio.wait_for 包裹（I-37）。存储并发：SQLite WAL 读写互不阻塞（多读者+单写者），限制是仅同机文件、长读事务阻塞 checkpoint（I-44）；保持 JSON 台账则维持原子替换+只追加纪律。

### 12.5 安全面：localhost 服务不等于免疫

DNS rebinding 可让远程网页绕过同源策略读写绑定 localhost/内网的本机服务，Host 头校验是标准防御（I-46，媒体信源），本地无鉴权 API 仅绑 127.0.0.1 并不安全。现成旋钮是 Starlette TrustedHostMiddleware：校验 Host 头、不符回 400，但默认放行所有 Host，上线须显式设 allowed_hosts=['localhost','127.0.0.1']；uvicorn 默认只绑 127.0.0.1（I-47）。

### 对本产品的启示

- 形态钉死「浏览器 tab 直连本地 FastAPI」：StaticFiles/app.frontend() 同进程托管前端、单 worker 裸跑 uvicorn，MVP 可用 NiceGUI 纯 Python 起步，独立窗口留给 pywebview，桌面壳与强制前端构建链不进方案（I-03、I-40、I-41、I-01、I-02）。
- 拒绝第二套调度器与重型件：沿用现有 launchd 槽位+自研 loop，Web 后端只做展示+手动触发并尊重 watch.lock 与取数串行锁，进程内周期任务锁死单 worker，Celery/APScheduler 不引入（I-36、I-39、I-34、I-32、I-11）。
- 实时通道按「htmx 轮询起步、必要时 SSE（sse-starlette+watchfiles 盯台账目录）」排布，WebSocket 不进方案（I-23、I-27、I-45、I-26）。
- 告警主通道永久留在服务端 osascript（LaunchAgent 用户会话拉起），Web 面板只做前台展示、浏览器通知仅作前台补充，因为后台标签页会被冻结且程序化通知正被收紧（I-24、I-25、I-48、I-51）。
- 子进程与守护联动三件事：claude 子进程长期持引用防 GC 误杀并以 wait_for 设超时、uvicorn 优雅关停窗口须小于 launchd ExitTimeOut、显式裁定 AbandonProcessGroup 是否保留在跑会话（I-37、I-34、I-59、I-57）。
- 安全面与数据面：绑 127.0.0.1 之上必须加 TrustedHostMiddleware allowed_hosts 白名单防 DNS rebinding；数据优先单文件/SQLite(WAL) 最小落盘；AGPL 竞品只借形态与 MCP 接口切面、代码一行不搬（I-46、I-47、I-44、I-14、I-13、I-12）。

## 第 13 章 反证与失败模式清单

本章不新增证据，只做证据质量清点：全量 646 条 findings 中按 verdict 强制归集到本章的 65 条——confirmed 反证类 2 条、weakened 4 条、unverifiable 13 条、gap_fill_unverified 46 条——按失败模式分簇清点，并给出方案文档引用时的降权纪律。三条主线：国内竞品事实面的横评信源集中度已量化；一条学术锚点 arXiv ID 引用有误；模拟盘「盘中限价+滑点」裁定在港股标的与滑点标定两处仍被未核验证据阻塞。

### 13.1 证据构成自审计与引用勘误（confirmed 2 条）

国内竞品专题 11 条证据中官方信源仅 1 条（东财组合功能页）、应用商店 1 条、署名媒体 2 条，其余 7 条为社区/自媒体横评，其中 4 条出自利益相关方「财搭子」官方账号且横评自标 AI 生成，竞品功能事实多靠横评拼图（A-22，信源层级：媒体/社区统计自评）。因此前章引用的国内竞品功能口径在官方文档直采补齐前只能按横评降权使用（A-22）。

引用勘误一条：grounding 学术锚点所引 FinAgent 的 arXiv:2402.18488 实为表示论数学论文 Jun Yang. Von Neumann Dimensions and Trace Formulas II. arXiv preprint arXiv:2402.18488, 2024. [Online]. Available: https://arxiv.org/abs/2402.18488，无任何金融 agent 内容（B-66）；FinAgent 真实载体为 arXiv 2402.18485（C-22 所引 html 版本页，weakened：该条转述中「OHLCV」应为 OHLC+adj_close，论文全文无成交量字段）。最终报告与方案文档引用 FinAgent 前必须统一改用 2402.18485 并重核（B-66）。

### 13.2 weakened：主干成立、细节须改写的四条

| 条目 | 对象 | 成立主干 | 须修正点 |
| :--- | :--- | :--- | :--- |
| C-22 | FinAgent 架构 | 三模态输入、MACD/KDJ&RSI/均值回归工具面、GPT-4 backbone 均逐字核实 | 数值输入应写 OHLC+adj_close，不含成交量（原文 volume 零处出现） |
| D-56 | 本机 MCP 冷启动 | 约 30s 全量连接批、4 个 server 连接失败（3 个 bigmodel 协议错+1 个 ECONNREFUSED）复现 | 「约 20 个 claude.ai connector 待认证」低估为实测 58 个，现状比原陈述更重 |
| E-62 | Backtrader 维护活性 | 未归档但实质停更成立 | open_issues_count=64 实为 issue+PR 合计且全部是 PR（open issue 为 0）；master 最后 commit 2023-04-19，主干停更像 42.6 个月而非 27 个月 |
| F-02 | claude CLI --bare | 官方推荐脚本/SDK 用 --bare 且将成为 -p 未来默认、不读订阅 OAuth/keychain 属实 | 「只认 ANTHROPIC_API_KEY」过窄：apiKeyHelper 与 Bedrock/Vertex/Foundry 自有凭证在 bare 模式照常可用 |

四条共同形态是「方向对、数字或枚举过窄」：引用时以本章修正口径为准，主干结论不受影响（C-22、D-56、E-62、F-02 均为 weakened：细节见上表）。

### 13.3 unverifiable：13 条不可核验断言与四类失败模式

| 失败模式 | 条目 | 内容与注记 |
| :--- | :--- | :--- |
| 官网反爬 403 | B-11/B-12/B-13/B-15/B-16/B-17、H-24 | Danelfin 全部能力与定价口径（约 1 万特征、AI Score 概率映射、分数桶回测、Audit 面板、三层可解释、月度前瞻披露、$22–134/月定价）官网两次尝试均 403 不可现场核验；其中 B-12 概率映射经页面原文、Help Center、对照图三层互证，属高置信线索（均未核验） |
| 社区平台域级拦截 | B-10、B-19 | Reddit 对 Holly 的分裂评价与 30 天实测 Danelfin 55 只选股仅 18% 跑赢基准的小样本反差，原帖均不可达，仅搜索摘要为证（均未核验，信源层级：社区） |
| 死链/页面下线 | A-54、A-60、I-53 | 同花顺 FAQ 频控页 404（三家竞品预警频控均无公开文档）、九方智投黑猫投诉单已不可见（触碰红线 1 的责任域线索，信源层级：社区）、Streamlit fragment 源码路径随仓库重构 404（均未核验） |
| 付费墙 | C-37 | ACM ICAIF 2025 第二份投资管理 LLM agent 综述被 Cloudflare 拦截，题名与会议仅获双重佐证（未核验） |

清点结论：unverifiable 集中暴露两类结构性风险——头部零售 AI 投研厂商官网普遍反爬导致能力口径不可复核（B-11~B-17），以及第三方小样本实测与官方宣称可差一个量级（B-19，未核验，社区）：对外披露任何绩效对比时必须区分官方回测与第三方实测。

### 13.4 gap_fill_unverified：46 条补洞证据的主题清点

46 条 gap_fill 均为填补证据缺口新采、未经第二轮核验的条目，方案文档只可作线索、不可作判据（本节全部未核验）。

| 主题簇 | 条目 | 核心内容 |
| :--- | :--- | :--- |
| 竞品官方口径直采 | A-77/A-78/A-79/A-82、A-80/A-81 | 经 App Store Lookup API 直采厂商自写描述：同花顺盯盘三类事件口径、东财描述无「预警/盯盘」字样、问财自然语言转量化条件、头部产品仅「投资有风险」级提示；监管侧补生成式 AI 办法第 23 条与证监会非法荐股/AI 金融陷阱警示 |
| 中线学术锚 | A-83~A-88 | 动量 3–12 月有效、分析师推荐非对称漂移、季度共识变化、BXM covered call、按需再平衡等 peer_reviewed 引文，补洞未复核 |
| 模拟盘撮合与滑点 | E-65~E-81 | 免费 A 股快照五档（腾讯/新浪/东财）与 1 分钟分时、港股通道延迟分叉与无盘口、引擎撮合语义与滑点默认值 |
| 合规灰色面 | G-34~G-38 | qt.gtimg 无鉴权无条款、腾讯服务协议 4.1 个人非商业/4.5 第三方软件、akshare 同源先例、腾讯云无官方行情 API、宿主页 301 退役无 SLA |
| 国内定价锚 | H-46~H-50 | 同花顺 Level-2 年 88 元、诊股类内购 6–138 元/月、妙想 301 收编进 Choice、Choice 询价制无公开价目、问财免费无 IAP 区块 |
| 离机触达 | I-62~I-68 | LAN HTTP 非 secure context、iOS Web Push 走云推送与红线 7 冲突、macOS 防火墙弹窗、本机电源/防火墙探针、caffeinate 防睡死、Tailscale 密文中继、锁屏挂起综合推导 |

三个必须显式登记的失败模式：其一，同一引擎文档与源码在「触价是否成交」上不一致——Backtrader 源码 bbroker 为 plimit>=plow 含等号即成交（E-69），官方文档却写严格穿价 low<limit（E-78），采引任何撮合语义前必须以源码复验。其二，港股标的阻塞：已裁定口径隐含秒级连续行情假设，但免费港股行情按通道分叉——普通 q=hk 通道滞后约 15 分钟且无盘口，r_hk 与东财时戳同步但五档区全 0——港股标的存在盘中行情延迟、阻塞面明确，快照新鲜度门禁未过闸前不得按盘中口径撮合（E-67、E-76、E-77）。其三，滑点数值标定无锚：LEAN 默认 NullSlippageModel 零滑点、VolumeShareSlippage 小单冲击封顶 0.625bp、MarketImpact 参数官方自认源自 Almgren 2005 约两十年前标定，引擎默认域全部不可直接复用，散户小单滑点须以半价差+最小 tick 自行标定并在规约登记数值依据（E-73、E-72、E-74、E-75）。

另两条结构性缺口属「未见公开证据」而非证据不足：三家竞品预警推送频控均无公开官方文档，本产品盯盘频控/静默窗口须自定口径（A-54，未核验）；用户离开 Mac 后的告警触达在红线 7 禁云推送下面临 iOS 锁屏挂起与 secure context 双重边界，可行形态收敛为面板常驻拉取式主动查看（I-62、I-63、I-68，均未核验）。

### 对本产品的启示

- 方案文档引用国内竞品功能事实时统一标注「利益相关方横评、官方信源占比 1/11」的降权说明，优先走 App Store Lookup API 官方直采通道补证（A-22、A-77~A-79）。
- 引用 FinAgent 一律改用 arXiv 2402.18485 并重核，IEEE 参考文献链禁止沿用 2402.18488（B-66、C-22）。
- 四条 weakened 按本章修正口径登记：MCP 待认证计 58 个、Backtrader 主干停更计 42.6 个月、bare 认证写全 apiKeyHelper/云厂商枚举、FinAgent 数据面写 OHLC+adj_close（C-22、D-56、E-62、F-02）。
- 模拟盘撮合采严格穿价+快照新鲜度门禁语义（LEAN 先例），弃用 bar 级触价即成交；滑点不得沿用任何引擎默认值，数值依据进规约登记（E-69~E-75、E-78~E-81，未核验、作设计线索）。
- 港股标的在时戳门禁过闸前一律回落收盘复核成交，与 watch.py 180s/轮 r_hk 快照及 T2 逐笔确认 SSOT 对齐（E-76、E-77、E-80）。
- 离机触达按「主动查看」设计预期：面板做 WebSocket/SSE 刷新+打开即全量回放，文档明示锁屏不保证送达，不做任何云推送例外（I-63、I-68）。

## 第 14 章 与 vibe-stock 生态映射表

四大能力域对既有调用面的复用映射与净新增面（编排面事实来源：SKILL.md / references 06·07·09·10·11 / batch 契约只读探查，2026-11-06；本章「红线 N」裸编号与方案文档 §6 的 R1–R13 一一对应）：

| 能力域 | 既有复用件（零改动） | 净新增组件 | 红线落点 |
| :--- | :--- | :--- | :--- |
| 诊股 | 五段流水线（fetch→prepare→LLM 意见段→adjudicate 双轨→report）、addon 三道门（10）、战术仓读出（11）、走势参考（09） | 意图路由表、CCClient 会话编排、面板诊股工作台、decision log 登记 | 红线 3（裁决链不可改写）：LLM 仍只产 opinions/risk，聚合一律 verdict.json |
| 盯盘 | watch.py 三级事件语义（T0 已实施；T1/T2 规约预留）、launchd monitor 槽（09:15+补拉+兜底）、收盘复核 day-summary、t2_pending_fill 推演事件 | T1 自动刷新接线（零 LLM）、T2 建议卡编排（重放意见+机械覆写 risk+原命令重裁决）、面板事件页与复核入口 | 红线 7/8（只提示不执行、永不写 signals.json）；只降不升三重锚（07） |
| 操作策略 | signals/ledger 最新信号投影、04 持仓者五档、09 outlook 日表、07 操作复核节、postmortem 18:05 槽 | 盘前晨报与盘后复盘行动项卡（事件归并+待办确认状态）、面板后验战绩页 | 红线 1（不构成投资建议）：行动项为「复核」措辞非指令；免责尾注单点注入 |
| 模拟盘 | 06 Stage D 三段建仓三价纪律、07 sim-portfolio.json P3 schema（已钉死）、t2_pending_fill 事件源、postmortem 记分 | paper 引擎（穿价撮合+费用栈+T+1+涨跌停三态+公司行动+滑点静态表）、record_fill 逐笔确认流、权益曲线 | 新增红线 NR-2（永不接真实下单接口）；T2 写回经用户逐笔确认（07） |

主 Agent 编排层对既有件的总原则：**并存收编、不替代重写**——launchd 三槽（monitor 09:15 / outlook 17:35 / postmortem 18:05）原样保留，主 Agent 只消费其台账产物并承接 07 规约预留的 T1/T2 升级位；`~/.vibe-stock/` 既有 SSOT 的写者不变（signals.json 仍只由 report 写、ledger 仍只由 postmortem 写），主 Agent 唯一新写区是 `agent/` 命名空间与 sim-portfolio.json。数据缺口两处已识别：港股盘中时戳新鲜度未过闸前 T2 限价批回落收盘复核成交（E-76/E-77，未核验）；盯盘频控无竞品公开口径可对标、须自定（A-54，未核验）。

## 附录 拒绝引入清单

以下 18 项为设计级拒绝（引用锚为第 2–13 章 findings，只增不删）：

1. 照搬 TradingAgents 多 agent 辩论机制与 LLM 合成终审——论文七版零消融、辩论增益大半是投票、终审必须确定性 adjudicate（C-02/C-05/C-70/C-72）。
2. 引入 FinMem 式收益声称与双向画像切换——扩展回测优势归零且违反只降不升红线（C-14/C-49）。
3. 盘中无 oracle 的 LLM 自由反思与自我复核——无外部反馈自纠错一致掉分、金融域反思记忆放大 recency bias（C-61/C-66/C-64）。
4. `claude mcp serve` 作为大脑通道——工具桥非大脑、约 2.6 万 token 固定开销、未文档化且有 EOF 孤儿进程 open issue（F-01/D-22/D-24/D-25）。
5. `--bare` 认证模式——永不读订阅 OAuth 与主线正面冲突，列头号升级观察项（F-29/D-04）。
6. 常驻双向 stream-json 长管道——截断与静默丢 result 两个 open issue，一次性进程+`--resume` 更稳（D-05/D-06）。
7. auto-compact 作为无人值守依赖——多版本回归先例，显式 `--autocompact` 与 wall-clock 超时代替（D-38/D-66）。
8. 任何第三方推送通道（IM/webhook/云推送/浏览器 Web Push）——红线 7 无条件禁；iOS Web Push 属云推送通道（I-63）。
9. 真实下单接口、券商 API 直连、一键转实盘——红线 1 与 G-01/G-22/G-31；Alpaca 双凭据双端点物理隔离为对标形态。
10. Electron/Tauri 桌面壳进 M1——进程链与打包链代价最高路径；Tauri 壳留 M2 门口以使用数据评审、不过则退化 pywebview 轻窗（I-01/I-02/I-42）。
11. APScheduler 4.x、Celery、第二套调度器——4.x 未出 pre-release、多进程 job store 重复执行、本场景重队列过度设计（I-11/I-31/I-32）。
12. 引擎默认滑点值与 bar 级触价即成交口径——LEAN 默认零滑点、VolumeShare 小单封顶 0.625bp、MarketImpact 参数两十年前标定；Backtrader 触价口径经源码终裁确认乐观（E-69/E-78 主循环终裁；E-70~E-75 仍未核验、仅作设计线索）。
13. TradingView 式零滑点零费用模拟成交——无限流动性假设虚增胜率 20–30% 的反面教材（B-32/E-58）。
14. 历史成分回溯收益宣称——幸存者偏差年化高估约 4.94pp，成分精选只做前向模拟（E-22/E-23）。
15. LLM 重放历史窗口做后验记分——训练窗重叠前视污染；postmortem 保持确定性脚本（E-24/C-09）。
16. 共用面板与多用户化——Anthropic 消费条款禁共享登录态，任何多用户步骤先过 ToS 与投顾监管双重评估（G-29）。
17. 保本、收益保障、胜率承诺、精准预测、晒单战绩类话术——AI washing 与非法荐股执法集中区，入文案审查黑名单（A-59/A-63/G-12/G-11）。
18. 内嵌重 MCP/hooks 的编排框架——Ruflo 式 406 工具+27 hooks 加重上下文与冷启动（D-79）。

## 数据与核验状态

- findings 总量 646（A 88 / B 73 / C 103 / D 82 / E 81 / F 63 / G 38 / H 50 / I 68）；核验分布：confirmed 583、weakened 4、unverifiable 13、gap_fill_unverified 46、panel 证伪 0；语义归并后有效主张 575 条。
- 信源层级分布：official 266、repo 96、preprint 56、media 52、community 51、local_probe 48、peer_reviewed 46、regulatory 19、app_store 12；国内竞品专题官方信源占比 1/11 的集中度风险已在第 13 章登记。
- 冲突台账 20 对：并读 11、降权 7、open_question 1（妙想「自动跟踪并执行」的执行边界与行业「候选/参考」合规口径相抵，A-15 vs A-18，如实披露待官方文档直采定谳）、主循环源码终裁 1（Backtrader 撮合边界 E-69 vs E-78：拉 mementum/backtrader master 源码终裁为触价即成交、含相等，引擎间口径分歧坐实）；qt.gtimg 港股时戳新鲜度一对（E-25 vs E-76）台账处置为并读（「r_hk 通道与旧快照字段之别」假说与重探定谳要求记于 note，E-76 未核验），港股标的的 T2 限价批在重探定谳前一律回落收盘复核成交。
- 全部竞品功能口径以各 finding 的 as_of 日期为准（信源内容日期非抓取日）；调研执行日 2026-11-06。
- 语料与过程台账：`.temp/wf-mainagent/`（r1 全量语料与 digest、r2 归并/章节映射/冲突台账、r3 章节草稿与方案候选、grounding 背景锚），gitignore 内不入库；本报告正文每条结论的 finding_id 可在该语料中回溯原文与信源。

*本报告仅供学习研究，不构成投资建议。*
