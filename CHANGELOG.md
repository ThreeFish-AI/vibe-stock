# Changelog

本文件只登记版本级变化；条目遵循 Keep a Changelog、[SemVer 2.0.0](https://semver.org/lang/zh-CN/)。

> 版本序列说明（2026-10-30 起）：项目未到稳定发布，版本号统一回归 **0.0.x** patch 序列；存量 0.1.0–0.2.1 六版已按发布顺序一一重编号为 0.0.1–0.0.6，合并时又把并行合入的 0.2.2/0.2.3 两版重编号为 0.0.7/0.0.8（仅改 header，条目正文维持原样），此后默认只升 0.0.x patch，minor（0.1.0）预留给语义级变更。

## [0.0.30] - 2026-11-08

### Added

- **agent: 前缀独立画像（07 L118 预留位落地；主 Agent decision log 的 T2 建议卡后验记分）**：新增 [scripts/agent_postmortem.py](scripts/agent_postmortem.py)——只读 `~/.vibe-stock/agent/decisions.jsonl`（写者=[stock-trading-agent](https://github.com/ThreeFish-AI/stock-trading-agent) 主 Agent）的 `advice_card_written` 决策行，T+1/3/5 收盘 ±2% 同式判定（**import postmortem.score/NEUTRAL_BAND 禁复制**，06「聚合分复算逐字同步」同类纪律）；I-016 到期收盘门同判（末根盘中未完成不评、收盘后补评）；非交易日登记回退最近一根日 K（与 postmortem 非交易日信号同判）；独立台账 `ledger.agent.json`（沿 monitor: 前缀先例不进 ledger.json/ledger.position.json；归因子 `agent:<final_signal>` 五词；evaluated 索引幂等防重评）；signal_to_action 为 score() 的 SCORABLE 家族语义最小桥（bull/bear，hold 只观察——非复制 ACTION_OF）。运行形态：手动或与 18:05 postmortem 槽串联（plist 串联命令登记于脚本 docstring，暂不装独立槽）；advice_refused 风险提示类方向语义不同构（避开回撤即有效），攒样本后经 RSI 评审再入回路（07 P3 先例同款留位）。selftest 四例（信号桥/到期窗含 I-016 门/decisions 坏行容错/score 同式 import 契约）全绿；真实干跑（无到期卡）如实「无新到期 horizon」不空写台账。

## [0.0.29] - 2026-11-07

### Changed

- **主 Agent 文档族整体迁出至产品仓 [ThreeFish-AI/stock-trading-agent](https://github.com/ThreeFish-AI/stock-trading-agent)（0.0.28 引入的四组，本仓回归机制 SSOT）**：用户裁定（2026-11-07）产品实施成果沉淀独立仓、机制成果仍沉淀本仓，两仓 SSOT 边界——本仓 = 诊股 Skill 机制事实源（SKILL.md + references/01–11 + strategies/ + scripts/ + batch/），新仓 = 产品实施事实源（调研/方案/架构图/原型/实施规约 docs/specs/代码/NR-1~NR-5 产品红线全文）；跨仓引用一律 GitHub 绝对 URL。四组迁出件（docs/research/main-agent.md、docs/research/main-agent-proposal.md、docs/diagrams/main-agent/ 四件套×4、docs/prototypes/main-agent/ 四页原型）在新仓保持原相对布局（同仓链接零断链）；proposal 内两条 references 相对链接改本仓绝对 URL、§17 规约落位改判新仓 docs/specs/（12-orchestration/13-paper 随其实施 PR 建，本仓不建、SKILL 判表不同步）；新仓侧原型 A 股代码改显式假码（309866/609234/609789/309517/009567，经 A 股代码全集断言不在场）并按原口径重截 4 张 PNG。本仓指针同步：README「Stock Trading Agent」节链接改新仓绝对 URL、knowledge-map 四行收敛为一行外仓指针、references/07 sim 组合节「方案 §12」措辞标注外仓并补 sim-portfolio.json 写者归属让渡（实施写者=新仓 paper 引擎）；[0.0.28] 条目内 4 条文档链接同步改为新仓绝对 URL（活导航，其余字节不动，特此登记）。SKILL.md version 升 0.0.29；机制与门禁零改动（六件 selftest 口径不变）。

### Removed

- docs/research/main-agent.md、docs/research/main-agent-proposal.md、docs/diagrams/main-agent/（16 文件）、docs/prototypes/main-agent/（8 文件）——迁出非删除，内容于新仓存续（见上）；docs/research/midterm-strategies.md（0.0.16 中线机制调研）留仓不动。

## [0.0.28] - 2026-11-06

### Added

- **主 Agent（Claude Code 唯一大脑）前期调研与方案（纯文档+图，零代码；产品正式定名 Stock Trading Agent，2026-11-07 用户裁定，D1 落定）**：新增 [docs/research/main-agent.md](https://github.com/ThreeFish-AI/stock-trading-agent/blob/main/docs/research/main-agent.md) 调研报告（159-agent 三段流水线产出：9 维 47 finder 扇出+loop-until-dry+可达性/事实抽查/对抗 skeptic/3 lens panel+双 lens 查漏 → 语义归并/章节聚类/冲突台账收敛 → 12 章成文+3 方案候选×3 lens 评审；646 条 findings，confirmed 583/weakened 4/unverifiable 13/补漏未核验 46/证伪 0，每条挂 finding_id，仅作者本机语料可回溯、语料不入库；含 14 章生态映射表与 18 项拒绝引入清单）与 [docs/research/main-agent-proposal.md](https://github.com/ThreeFish-AI/stock-trading-agent/blob/main/docs/research/main-agent-proposal.md) 产品与技术方案（四项用户裁定内比选：A FastAPI 单体骨架 + B 合规架构与模拟盘 M1 落地 + C 边界纪律嫁接；红线继承 13 条编号锚定+新增 NR-1~NR-5；M1 Web 面板+paper v1 → M2 T2 建议卡全链+paper 全量 → M3 无人值守预算闸默认关；launchd 三槽并存收编不替代；CCClient 契约/Loop 六段/agent/ 状态扩展/模拟盘三批建仓与穿价撮合口径/风险地图 R-01~R-13/决策点 D1~D8 待批）。配套四张架构图 archify A 档入库 [docs/diagrams/main-agent/](https://github.com/ThreeFish-AI/stock-trading-agent/tree/main/docs/diagrams/main-agent)（main-architecture/agent-loop-sequence/state-extension-dataflow/paper-trading-lifecycle 四件套+visual-check 回执，回执内路径已脱敏为仓库相对路径；delivery.json 因 Archify 契约绑定本机绝对路径不入库、已 gitignore），SVG 分别嵌入方案 §8/§10/§11/§12 与调研报告第 1/7/8/9 章；四页产品原型（自包含 HTML+整页 PNG，全合成数据+免责页脚）入库 [docs/prototypes/main-agent/](https://github.com/ThreeFish-AI/stock-trading-agent/tree/main/docs/prototypes/main-agent) 并嵌入方案上篇 §2 借图展开（图 2-1～2-4）。SKILL.md version 升 0.0.28、README 增「主 Agent（规划中）」节、knowledge-map 增四行指针；[references/07-monitor.md](references/07-monitor.md)「sim 组合 SSOT」补钉批状态机与仓位状态推导（任一批成交即 holding、所有存在的批均 expired 为建仓失败（拆出 T3 批的多手仓位因 T3 补足不会因到期而失败；成交请求被驳回或未确认时批保持 pending、不产生状态迁移）、展示标签不回写 status）与 T1 跳空回落口径（跳空 >+2% 转限价 = 信号日收盘 ×1.02、5 日 GTC，未穿价置 expired；成交判据取严格穿价 `low < limit`，07 新增「成交判据与提示判据分两把尺」条钉死与提示口径 `low ≤ entry_ref`（含收盘终判「T2 触价坐实」，只表示触价、非成交确认）的差异；暂定 estimated，仅规约文本、实施随 P3；P2 建议卡落位 `monitor/advice/` 补钉写者：T2 会话经断言器放行后原子写入、`watch.py` 不产卡），[references/06-batch-scan.md](references/06-batch-scan.md) Stage D 增指针；机制与门禁零改动（六件 selftest 口径不变）。

## [0.0.27] - 2026-11-05

### Added

- **高抛低吸战术仓执行规约（references/11，纯文档，零代码）**：高抛低吸的信号早已有 swing_band（中线 regime 门控）与 box_oscillation（短线），缺的是执行层——用户在底仓之外开战术仓时事前写死什么。11 定义：①价区来源二选一并声明（system_band 取 box_60d 箱体快照并按 swing_band 的 15/90 位置线换算、下沿只许上移不许下移；user_conviction 用固定价格且强制越权声明）；②底仓/战术仓分账（回补 ≤ 已高抛未回补，战术仓 ≤30% 沿 swing_band 卫星仓，成交 note 标 `sleeve=tactical` 并披露与 10 状态机/包络的耦合）；③高抛腿与回补纪律（回补价 ≤ 高抛价 ×（1−3×往返成本），不追高回补，不做网格）；④低吸五门（事件/归因/基本面/价区/确认，缺证据一律算不过，确认借 10 三段确认制）；⑤仓位算术（股数 = 预算÷(2×风险)，2× 为跳空穿越口径，标防御性设定·estimated）与失效位、20 交易日时间止损；⑥越权声明（硬越权默认禁：风险角色 veto、A-1 解禁临近、五门不过；软越权须事前逐条声明）；⑦记分与证据强度如实；⑧预案文件契约（本机 `~/.vibe-stock/playbook/`、不入仓，公开仓零个人参数）与 Agent 读出约定（只陈述事实，不给档位、不改 verdict、不落 reports/monitor/signals）。附空白模板与合成示例。SKILL.md 判表/头部规约列表/description 触发语/version、PIPELINE/README/AGENTS 目录速查/knowledge-map 指针同步；04 portfolio.json 契约表 operations 补可选键 `note`（自由文本人工备注，仓内不消费，契约其余语义不变）。
- 设计取舍：不新增策略 YAML、不造第二套价位 SSOT；不新增读取预案的代码（战术仓无系统消费方，读本机文件只增敏感面与门禁义务）；股数算术若干跑暴露错误再另开纯函数 + selftest。

### Changed

- **作用域澄清（非放宽）**：06 持有期纪律「止盈后资金留存不追补」坑位追加一句——管主账与批量组合，战术仓另账见 11；07 操作复核节追加一句——复核行按系统台账生成、不识别战术仓预案；10 定位节追加边界句；08 带宽纪律坑位追加执行层指针。06/07/08/10 的判据与门槛逐字不变，scripts/、batch/、strategies/ 零改动，六件 selftest 口径不变。

## [0.0.26] - 2026-11-05

### Changed

- **全仓 Markdown「一段一行」合规化（纯排版，零语义变化）**：按《Markdown Source Layout Specifications》（一段一行，句内句间禁手动折行；显示行宽交 Renderer 软折行）将 18 篇 markdown 文档（CHANGELOG、SKILL、README、evals/batch/batch-monitor/strategies README、references 十一篇含 PIPELINE）约 1465 处段内手动折行并回单行；判据为规约 awk 检测器对全部 tracked md exit 0；折点空格按仓内存活文本实测惯例还原（汉字↔字母数字/`code`/`[链接]`/数学符号加盘古之白空格，链式 `a/b`、全角标点两侧直连），并修正 24 处折行吃掉的语义空格（命令参数 `--with efinance $T/…`、`--evidence .vs/…`、`gui/$(id -u) "$PL"`、元组 `horizon, regime`、schema 键值 `leg: T1_open`、`·`/`→`/`+` 分隔符等）；`git show`+工作树去空白逐字节比对全量一致，零内容增删。

## [0.0.25] - 2026-11-05

### Added

- **盯盘「事件 → 操作」族（四路深读 + Plan 代理钉实现细节；用户两项裁定 2026-11-05：A=通知面允许「××复核」短语（修订 0.0.15 通知口径零短语句与 0.0.24 盘中携带「只报事实」句，仍禁减仓/离场/加仓等指令词，沿 07 波段带「低吸/高抛复核」预钉先例）；B=范围全上、T2 本期只钉规约实施另开 PR）**：① **事件级复核短语（I-027）**：rules `_REVIEW_HINT` 表 + `_emit` 单点注入 `ev.review`（随台账落全量含被压制行，P3 monitor: 画像可消费）；watch fmt_facts 尾拼 `·XX复核`（止盈/止损/消息面/T2成交/均线/跟踪止损/低吸/高抛/波段结束复核），运维类零短语（selftest 负断言钉）；**排版修复**：「触及目标价1 9.43」标签序号与数值连读歧义（用户误读为 19.43）改「触及目标价1=9.43」等号钉住归属。② **P2 机械判据族落地（I-028）**：ma20_break（price<ma20×0.98 降档 medium，episode 复位再报）、trailing_armed/trailing_exit（+15% 武装跨日态、退出只认先前武装态；armed/high 住 state 顶层 trailing 键跨日保留——日归零会隔日漏报；facts 禁落成本派生量）、band_lo_touch/band_hi_touch/band_trail_break（position 波段带三键独立行键并行投影，与 default 三价不互覆；收盘 trail_ref 直判）；**前置门数据通道自建**：technical 无既有缓存可复用（derive_technical 只落临时 workdir）——当日预热（FetchLock+账本）拉 universe 日 K 落 `monitor/technical-cache.json`（全派生量脱敏），重试 ≤3 耗尽出一次性 data_stale 事件、判据当日禁用（不虚构判据）；成本/数量运行期注入（annotate_runtime 内存态、磁盘产物零污染，sim 每股成本=allocation 配置日价 cost≡lots×100×price 实证）。③ **收盘操作复核节（I-027）**：day-summary 新增「## 操作复核」——当日价位类事件 × 既有纪律映射确定性投影（06 三价「+15% 后改 trailing/资金留存不追补」、持有期、波段带纪律参考线注记）+ 04 持仓者五档投影（signals 最新 action 机械映射 `_TIER_TEXT`，只投影不重裁决、以报告原文为准）+ 权重分桶提示（A/港本桶末轮市值分母、>16% → 次日减至 ≤14%、fx 不进判定、单票桶跳过、只落百分比）；收盘终判新分支（MA20/trailing_exit 完整根现算勿复用盘中 estimated、band 两键坐实/收回）；收盘复核完成运维通知一条（事实级）。④ **T2 规约钉死（I-029，零代码）**：07 升级链补事件升级三级语义表（T0 事实/T1 轻量刷新/T2 会话内局部重诊）、P2 建议卡产物契约（schema monitor-advice/1、落位 monitor/advice/<date>/<code>.md、脱敏边界：T+1 可卖份额原值/距成本涨幅/武装线值不落 monitor/ 产物）、T2 会话触发入口手动先行（exit 2 自动接管后置 0.0.26+）；指数 MA60 实施形态钉死（--close 经 fetch_index 现取、as_of≠今日不判定）。
- 盯盘回归门禁：rules selftest 36→57 checks、watch 42→74 checks（新增复核短语文案钉、运维类负断言、波段带投影、注入零落盘、tech 前置门、终判新分支、操作复核/权重渲染、trailing 跨日保留；判据只收严）；07 回归门禁句文档数同步（历史 36/42 与运行数漂移一并修正）。
- **合入前 code-reviewer 评审修复（P1×2 + P2 族）**：band_trail_break 落盘后零可见面（复核覆盖集与终判集 PRICE_RULES 分立、补波段结束复核行）；次日盯盘重点按 rule 出摘要词（ma20_break 不再误渲染为止损击穿）；band_trail_break 台账幂等去重（--close 重跑不重复追加）；trailing high 收盘归并取数集扩至全部有成本票（data_stale 日不丢当日 high）；预热锁竞争让路不计次；权重分桶限实盘（sim 推演盘不混桶、不稀释实盘权重）。
- **合入前 code-reviewer 第二轮评审修复（P1×1 + P2×3）**：trailing high 累积纳入快照当日高点（rules init/max 与 close bar high 归并同口径——只用 price 会漏开盘竞价/快照间隙脉冲，低估「盘中高点」事实并延迟武装，8b fixture 补显式 high 钉）；收盘终判 0.98 字面量改引 rules DEFAULT_CFG `ma20_break_ratio`（盘中触发与收盘终判同一把尺）；tech_cache_fresh 生产零消费死代码删除（当日性门以 warmup 内联逐票判定为 SSOT，watch checks 76→74）；07 门禁句 75→74 再同步。

### Changed

- **规约句修订**：07 通知口径句（0.0.15 无条件全局规则层）按用户 2026-11-05 裁定改写（允许事件级「××复核」短语、指令词仍禁）；09 盘中携带句、07 走势参考携带括号句同步；07 分期表 P2 标「部分实施」；SKILL.md description/判表/version、README 盯盘节同步；AGENTS.md 测试段核对无涉（本就无数值/版本指针）。

## [0.0.24] - 2026-11-05

### Added

- **走势参考机制查漏补缺**（18-agent 五维度审查 + 对抗复核 24 条发现定案；用户四项裁定：P0 部署立即修 / postmortem 独立槽 / 中期锚可见化+登记评审 / 盘中携带补显式句）：① **postmortem 收盘评估槽（I-022，经验面数据链断点修复）**：新模板 `batch/postmortem/com.threefish.vibestock.postmortem.plist`（周一至五 18:05，错峰 outlook 槽 30min——0.0.24 起该槽为 collect+自动校准双窗约 8–14 分钟、postmortem 不走 FetchLock，时段分离按双窗上界校核）——signals 全库 105 条零 evaluated、69 条 pending 大量到期无人评估的空转形态实证（经验面 21/21 空桶根因）；05 新增「收盘后评估节奏」节与「两把尺分立」双向指针句。② **--daily 自动接校准（I-022 后半）**：收盘批量成功后默认自动 --calibrate（--no-calibrate 跳过；--stock 不触发）——校准台账不再依赖手动增厚，launchd 17:35 槽零改动生效；--calibrate 对「历史卡有、latest_cards 10 日窗无」的退册/断档股补 warn（此前静默缺样本）。③ **三道防线收编进 scripts/outlook.py（I-023）**：墙钟门 close_gate_open（17,10 单源常量，编排层禁内联）、末根未完成过滤 final_bars、校准真实增量计数 count_new_samples——此前住无 selftest 的 batch 编排层、回归无门禁可拦；outlook selftest 新增钉：墙钟门边界双态/末根过滤接线/增量计数幂等 0/触及概率对称（规约声称对称/单调、此前只有单调）。④ **弃权可见化与锚来源标注（I-025）**：position 无锚卡在 pack/4c 出固定注记行（「锚：弃权——…禁现算充锚」——此前只以锚行结构性缺失静默呈现）；allocation 回退锚行注「（allocation）」来源（sim 股三价禁被读成登记信号价位）；--stock 宇宙外股明确提示重派生（I-024，此前误报「当日卡齐备（0 只）」）。⑤ **规约/指针同步包（I-026）**：09/03 红线句「RiskGuard 接入留待单独评审」与 P3 已落地矛盾收口（LLM 判据 ②-8 已落地、机械布尔仍随 07 P2/RSI 合流）；01/PIPELINE 熔断簇 16→20 指针化（SSOT=fetch.py CLUSTERS）；PIPELINE akshare 升版四件→六件、①段市场级共享枚举修正（fx 港股专属非共享、margin 漏标）；09 补 allocation 回退锚登记/--stock/--calibrate 命令族/盘中决策携带显式句（07 P2 升级链同款）；ERP 250 日接管标注「实现待满窗前落地」（daily_ready 死端旗标，ETA 2027-10）；09 分期表新增中期锚覆盖增强再评审项（用户裁定：default 三价/250 日高低点充锚与「禁现算」裁定的关系是评审核心）；07 P4 补事件流→outlook 经验面消费指针与 watch 宇宙退休前瞻。
- **部署修复（I-021，非代码）**：launchd 调度路径技能目录 clone 滞后 main 十提交（0.0.18）实证修复——已 pull 至最新并 --render 重渲 11-04 日表（市场级五块实数自 jsonl 卡恢复）、--calibrate 重渲 calibration.md（qfq/重叠坑位披露补齐）；09 launchd 行新增「部署同步纪律」句。
- 版本依据：机制补缺四件 + 文档同步族，零裁决链变更，按 0.0.x patch。

## [0.0.23] - 2026-11-04

### Fixed

- **四项正确性缺陷修复（I-016~I-019，全部收严型，源自 02513 波段复盘取证）**：
  - **I-016 后验到期收盘门**（[postmortem.py](scripts/postmortem.py)）：到期 horizon 落日 K 序列末根且末根=当日盘中未完成 K 线（`fetch.session_phase` 的 `last_bar_partial` 判据，`now` 可注入）时不再评估、保持 pending，收盘后下一次运行补评——此前盘中跑 postmortem 会用盘中价把到期 horizon 误判成命中/未命中（伪命中已落盘不回改，存量回改需人工评审）；[05](references/05-postmortem.md)「价格口径」删与「复权基准」矛盾的「沿用登记价」句，基准统一为同复权信号日收盘。
  - **I-017 南向两层口径**（[fetch.py](scripts/fetch.py) `fetch_moneyflow_hk`）：东方财富持股变动日 D 对应成交日 D−2（港股 T+2 交收，港交所日成交 6 组样本验证）——note 与 `summary.chg_trade_lag_note` 写明「披露 T-1、成交 D−2」，字段名沿用；[diagnose](scripts/diagnose.py) 渲染由「当日净增持」改「持股日净增持（对应 D−2 成交）」，01/PIPELINE/README 指针同步——此前下跌日会把两天前的净买入读成「当日南向逆势承接」。
  - **I-018 box_60d 前窗口**（[fetch.py](scripts/fetch.py) `derive_technical`）：箱体改取不含当日的前 60 根（不足 20 根不出），pos_pct 不截断（跌破前箱底为负、突破上沿 >100，越界即信息）——含当日口径下任何新低日 box.lo==当日最低，「精确触箱底」成同义反复；存量报告 pos/width 不回改。
  - **I-019 中线波段带单位**（[diagnose.py](scripts/diagnose.py) `_mid_key_levels`）：g 为收益率却被当价差直接 `price∓g` 加减（带宽塌缩不足 1 港元），改为 `price×(1∓g)` 后与 60 日高低点钳制；selftest 由同公式断言重写为独立手算钉值 + 破坏性实验（回退价差口径必红）。
  - 六件 selftest 全绿（adjudicate 60 / diagnose 20 / postmortem 5（新增到期收盘门 g1–g4）/ lens / addon / outlook），Issue 档案见 [docs/.agents/issue.md](docs/.agents/issue.md) I-016~I-019。

## [0.0.22] - 2026-11-04

### Added

- 持仓股加仓决策轨（add-on track，[references/10-add-on.md](references/10-add-on.md)）：在册持仓的日诊不再只有持有/卖出两态——report 段自动跑 `scripts/addon.py` 确定性加仓门，回答「该不该加、加多少、什么价位、加错怎么撤销」。
  - **门 1 资格冻结/解冻**（只冻不升格，与 RiskGuard 只降不升对称）：短线/中线卖族、风险角色 veto/downgrade、A-1~A-5 风险链确定性判据（临近解禁→08 ①-3、估值极端分位→08 ②-4、EPS 90 日下修、两年翻倍警戒→08 ②-7 收严实现、当期亏损）；缺证据口径：not_supported/字段未接入 skip 不冻结（A-3 接入后收严为缺席即冻结、A-5 在 fetch 暴露多期后收严为连续 3 期——收严路径预留）。
  - **门 2 触发**（策略买点在场）：顺势轨（多头排列 + bull_trend/shrink_pullback 买点 + 回踩在场 ≥3% 或 ≤ma10×1.02 + rsi<78 + 不超 ma20+10%，恰 +10% 即拦）与逆势窄门（quality_value 买点 + lens「有支撑」置信 ≥medium + 现价<ma20 + 零风险链）；idle 触发前过 addon 自身置信门（confidence ≥0.5，与 default 轨同源口径；不要求 executable——hold 日加仓是设计内形态，低置信日不出买入侧建议）；「摊薄成本/跌多了/回本」列为禁用理由；「等回踩」变体仅在唯一缺失条件是回踩时成立（破位/买点缺席落普通持有并列出全部 blockers）。
  - **门 3 三段确认制**：首加 = 一批的 1/2（顺势一批 ≤现仓 1/3、逆势 ≤1/6，100 股取整；半批不足 1 手不拆批不加——顺势现仓 <600、逆势 <1200 不加）→ T+3 确认窗（信号日**后**前 3 根收盘，守住 add_ref×0.97 且不创新低确认加剩余并给出剩余手数，窗内任一收盘破线/创新低即撤销、可提前）→ 确认加成交（信号日后第 2 笔 buy，按笔计）进入冷却：同票 60 日 ≤2 次，冷却只拦新登记、不拦在途复核；add_ref 顺势=均线带上沿但不高于触发时现价（深回踩以现价为锚，防确认线高于成交价自噬撤销）、逆势=触发时价（与登记价同口径）；包络：加仓后浮亏 ≥15% 禁再加（汇率红线内，跨币种权重线 P2）。执行态从 portfolio.json operations + signals 推导，不新增状态文件；快照模式登记的 addon 信号不进实盘状态机（索引 live 过滤同口径）。
  - 报告持仓者分支扩**五档**（可加仓/持有·含等回踩变体/持有观察/减仓/离场）+「### 加仓评估（addon）」节逐门可溯源；首加建议登记 addon 信号（profile=addon、action=add_on、family=bull、T+1/3/5/10 ±2% 带按 bull 记分进 ledger.json——加仓建议也要被市场打分；个股时间线索引收 addon 行，总览最新/计数仍只算 default 轨）。
  - 新增 `scripts/addon.py --selftest`（冻结族/缺证据 skip/触发族/手数取整/三段状态机/冷却不吞在途复核/确认加终态/置信门/包络/破坏性实验），纳入 scripts/ 提交前置（本轨四件扩五件；outlook 主线并轨后为六件，门禁只收严）；diagnose 增加仓轨集成钉（含快照信号不进状态机）、postmortem 增 add_on 记分钉。
  - portfolio.json 契约（[04](references/04-report.md)）增补 `operations` 成交流水子表（元素键 code/action/time，09 三段状态机的执行事实输入）——仓内消费的顶层键由「仅 holdings」扩为「holdings + operations」，手维登记格式落 04 单一事实源；[05](references/05-postmortem.md) 期限轨/动作九态/台账口径同步 addon 轨（与 default 同账本 ledger.json、delta 分桶不串样本）。
- 用户裁定记录：加仓哲学=顺势+逆势窄门；节奏=三段确认制（2026-11-04）。

### Changed

- **红线显式修订（minor 级语义面）**：[03]「透镜不进裁决」增显式例外——lens「有支撑（置信 ≥medium）」可作 09 门 2 逆势窄门的资格输入（裁决链外确定性资格门不属「裁决环节」），其余场景透镜输出仍不进任何判定。
- `postmortem.py`：SCORABLE 增 `add_on→bull`；delta_map 增 addon 轨（台账归 ledger.json 与 default 同账本）；`archive.HORIZONS_OF` 增 `addon:(1,3,5,10)`；个股时间线索引表收 addon 行（default+addon 同表，T+1/3/5/10 同列）。
- SKILL.md（description/判表加行；version 与门禁件数随主线并轨顺延）、PIPELINE.md（回归清单）、README（能力节+文档指针）、AGENTS.md（目录表/测试节）、evals/README.md 同步指针，无第二事实源。

### Fixed（合入前二次评审修复，I-020）

- **I-020（P0）**：逆势窄门读错裁决轨——`value_trigger` 从 default 轨 verdict 找 `strategy:quality_value` 买点，而 quality_value 是 `profile: position` 策略（意见只进 `verdict.position.json` → pverdict），逆势轨生产永不触发且被「契约下不可能的 fixture」掩盖。改读 pverdict（缺席时显式 blocker「无中线裁决」）；selftest fixture 改合法形态 + 双回归钉（default 轨读到不开门 / pverdict 缺席不开门）；diagnose T11e 增逆势集成钉（verdict.position.json + lens 有支撑 → 「可加仓（逆势窄门）」+ add_ref=触发时价登记）。
- 评审随修（P2 族）：冷却文案硬编码计数改实数；首加「整批上限的一半」在取整时不实——改披露半批原值与取整值；`diagnose` rationale 兜底 `or ""` 括号优先级修复；`CONF_GATE` 改 import `adjudicate.CONFIDENCE_GATE`（口径 SSOT 单源）；09→10 改号残留批量清理（10-add-on H1、README 标题、**报告可见文案**「加仓资格冻结（09→10）」、注释族、05 引用）；SKILL 判表挤行拆回、PIPELINE 代码围栏闭合修复；在途未成交文案与机制对齐（不自动过期、挂至后验收口）并写入 10 规约；「20 日高回撤」措辞对齐实现（最高收盘口径）与「skip 解冻」坑位入 10 规约；issue.md I-011 详情内残留 I-010 编号修正。

## [0.0.21] - 2026-11-04

### Added

- 走势参考 P3 两件（09 分期表收官；RiskGuard 接入经用户「继续 P3」指令完成评审授权——判据只收严方向）：① 08 ②族新增判据 ②-8「市场级杠杆拥挤」（0.0.21）：margin 块 70 日分位
  >90 且 Δ5d >+2% 且个股级拥挤键并发（turnover_pctile_250>80 或 limit_up_count_20d≥2）→ 风险角色 downgrade（medium，rationale 引用数值）——走既有 risk.json 通道只降不升；市场级形态单独出现不独立降档；阈值属首版防御性设定非实证结论，放宽须评审。② 预测带自校准后验：`outlook_daily --calibrate`——历史卡 × 锚 × horizon 触及概率 vs 实际触及（方向按卡日收盘定：上方锚看上穿/下方锚看回落——双向或判对上方锚恒真的缺陷已修并有钉；不满整窗不记防右删），样本幂等台账 `~/.vibe-stock/outlook-calibration.jsonl`（坏行/标量行自愈）、`outlook/calibration.md` 分桶校准表（桶 n<30 标不足）；信息面披露不进裁决/台账/不改预测带公式。首跑 34 样本落地（低 p 桶实际 3.8% vs 预测 2.8%，量级吻合）。outlook selftest 新增校准钉（触及判定四态/样本流/分桶/幂等合并/坏行自愈）。
- 版本依据：一条 LLM 判据（只降不升方向）+ 信息面后验，按 0.0.x patch。

### Fixed（合入前二次评审修复，I-014/I-015）

- **I-014**：`--calibrate` 无墙钟门/末根未完成过滤——盘中手跑会把未定型末根 K 永久钉成错误样本（台账幂等键永不重判；--daily 侧本有 (17,10) 硬门）。修复：墙钟门同 --daily（--force 可越过）+ 根本防线 `session_phase` 末根未完成过滤（判窗只用已定型 K，--force 越过时过滤仍生效）。
- **I-015**：校准台账与样本面三处——①qfq 重基准偏置无防御：bars 全链 adjust=qfq，除权除息后旧锚（卡时点绝对价）vs 新序列系统性偏（上方锚触及被压低/下方抬高）——卡 price 与序列卡日收盘偏离 >0.5% 整卡丢样本（outlook selftest 钉：×0.8 重定价丢/×1.004 噪声不丢），calibration.md 口径行披露该偏置与「样本跨日重叠相关、n 非独立样本数」；②`merge_calibration` 坏行自愈只覆盖非 JSON/标量行，类型损坏行（h 非整数/缺键）是毒丸且崩点在台账写回之后（永不自愈）——载入 schema 校验（`_valid_cal_row`），重写时自愈清除；③「新增样本 N」按满窗计算数虚报（重跑零增也打印满数）——改按本运行 judged_at 戳计真实增量。
- 随附：删死常量 `CALIBRATION_LEDGER`（无引用且绑全局 STATE_DIR 易误用）；幂等键不含锚值的取舍在 merge docstring 显式化。

## [0.0.20] - 2026-11-04

### Added

- 走势参考 P2 两件（[09](references/09-outlook.md) 分期表）：① day-summary 附件：close_pass 渲染「走势参考（上一张收盘卡 · <date>）」指针节——由 close_pass 自身消费 outlook jsonl 重算（幂等；外挂追加会被重渲冲掉的问题形态不存在）；全文指针 + 市场级摘要行 + 零权重尾注；当日卡 17:35 才出、收盘复核只见 <today 卡（语义钉）；watch selftest 新增 5 checks（31→36：无目录不出节/有卡出节/市场级行/零权重尾注/当日卡不进附件）。② launchd 17:35 独立槽模板 `batch/outlook/com.threefish.vibestock.outlook.plist`（周一至五单槽每日批量、与 16:15 兜底槽错峰 80min、一次性命令无 KeepAlive 失败次日自愈、RunAtLoad=false、节假日误拉一次无害——无交易日历取舍同 07 P4；plistlib 解析钉含 --daily 参数与五槽 17:35 形态）。
- 版本依据：编排面与模板新增（脚本核心件零改动），按 0.0.x patch 升版。

### Fixed（合入前二次评审修复，I-014/I-015）

- 0.0.20 原条目宣称的「plistlib 解析钉」此前不存在（模板本身合法但无钉，漂移无门禁可拦）——补真钉进 watch selftest（--daily 尾参/无 KeepAlive/RunAtLoad=False/周一至五单槽 17:35/与 monitor 最晚槽错峰 ≥60min）；`_outlook_digest` 硬编码 `~/.vibe-stock` 路径与「21 只」字样改由 `state_dir` 派生（--state-dir 下指错路）；digest 市场级行渲染补 `_d` 缺数兜底（I-012 同律，残块缺键不渗 None%）；selftest `mkdtemp` 泄漏改 `TemporaryDirectory`（watch 36→42 checks）。
- 07 回归门禁行 watch checks 口径同步（31→42）与 day-summary 附件节登记。

## [0.0.19] - 2026-11-04

### Added

- 市场级情绪五块 + 指数日 K 链共享件一次全落（用户 2026-11-04 裁定 5；[09](references/09-outlook.md) 分期表 v2）：fetch.py 新增五个零权重扩展块——margin 两融余额（dc `RPTA_RZRQ_LSHJ` 直连主源·全市场·元·单次 70 日，金十转发回退·沪深两所合计差北交所 ~0.33% 如实披露；backlog 原报表名 RPT_RZRQ_LSHJ 已失效——改名多一个 A）、index 指数基准（HS300/ALLA/HSI 快照 + MA60 + 距 MA60%；腾讯主源→新浪回退、HSI yf→新浪港股；坑位钉死：腾讯指数 amount 列实为量手非额、000985 新浪断更 2016、yf MultiIndex 单列 DataFrame 陷阱、当日行 Volume=0）、turnover_pctile 全A换手分位（000985 量滚动 250 日分位——成交活跃度代理，东财换手率列补测后升级）、erp（月频乐咕沪深300 滚动 PE×东财 10Y，ERP=1/PE−y10，5 年月频分位；日频中证官网 000300 P/E2 增量台账 `~/.vibe-stock/erp_pe_daily.jsonl`，满 250 日出日频分位——裁定 7 的经验积累载体）、margin_accounts 两融账户参与度（日频·户；裁定 6：原「新开户」上游 2023-09 停更的替代口径，不冒充新开户）。
- 市场维度共享取数：fetch 层 `_MKT_CACHE` 同进程一次取数（单诊 +2~6 HTTP、批量 +8~14）；batch/outlook_daily.py build_evidence 注入五块；簇 16→20（jin10/sina_idx/legulegu/csindex 新增，dc-margin/dc-bond/em-mkt-account 归 em_datacenter、tx-idx 归 qq）。
- 消费面：卡片 emotion.market 五块投影（全缺 abstained）+ pack「市场级情绪」行；日表「市场级情绪」节出实数；diagnose render_ext_blocks 五节有界渲染（EXT_PACK_BUDGET 2–5 行）+ 截断 heads 五节头；adjudicate EXT_BLOCKS 镜像加宽；diagnose selftest 簇数钉 16→20 与 hk 能力钉集合扩容。
- 指针：01 扩展块表 +5 行与 backlog 两融转正（东财指数换手率列补测位）；08 Phase 5 预留节指针化（市场级已实施、指数链就绪、超额收益带实施随期别）；07 P3 指数链就绪句；09 分期表 v2 ✅；SKILL（0.0.19+description 十五块）/PIPELINE（21 块）/README 块数口径同步。
- 版本依据：纯信息面扩展块（零权重、裁决链零改动），按 0.0.x patch 升版。

### Fixed（0.0.19 合入前独立盲审修复）

- C1：erp partial「仅日频积累、无数值键」形态（月频链失败——五新源常态路径）曾把 `ERP None%` 字面量渗进 pack 与日表——投影处按数值键收口（erp 无 erp_pct 不入卡），破坏性实验钉进 outlook selftest（全 pack 禁 None 字面量）。
- W1：`_MKT_CACHE` 只缓存成功数据——fetch_failed 不入缓存（首股瞬态失败曾固化成全批 21 股终局、绕过熔断器「连续 3 败」阈值；重试节流由既有冷却承担）。
- W2：HSI 新浪回退补 `>=60` 序列守卫（与 yf 主源对称，短序列不出 ma60=None 快照、日表不出「距 MA60 None%」）。
- S1/S4：ERP 台账合法 JSON 标量行（非 dict）按坏行自愈跳过；margin docstring「行内自校验」措辞改为口径声明（未做数值校验不虚称）。
- W3/S2 声明为既定取舍并写入 09 并发节：ERP 台账 last-writer-wins（增量 20 日重叠、次日自愈）；跨进程无市场级缓存（06 批量 subprocess 形态每股全价，后续按当日 jsonl 缓存收口）。

### Fixed（0.0.19 合入前二次评审修复，I-011~I-013）

- I-011：margin 取数链两个崩点/渗点——①金十回退「HTTP 成功但零配对行/行数不足」曾落到 `vals[-1]` 抛 IndexError 崩整条诊股链，补 ≥21 行守卫返回 fetch_failed；②主源「行数不足（1–20 行）」的 raise 被吞后回退条件 `not series` 永不成立，曾以 available·`source=None` 渗透 pack 头、note 错标且给 em_datacenter 记假败——回退条件改 `src is None`，行数不足不记源败（diagnose selftest 钉：回退介入·不渗透·不记假败）。
- I-012：C1 渲染收口补第二道——投影端滤 None 键只堵了入卡侧，渲染端裸 `%s` 仍会把残块的缺键打出 `None%`/`0.00%` 字面量（margin_accounts 6–20 行、历史短序列残卡等形态）；pack 市场级行与日表市场级节渲染端统一 None→「—」（outlook selftest C1 扩展钉：margin 缺键 fixture 禁 None 字面量）；A 股 HS300/ALLA 补 ≥60 行守卫与 HSI 对称（短序列入 fails 披露，不出「距 MA60 None%」）。
- I-013：index/erp 链三处守卫与归因——HSI 短序列补入 `fails`（此前块可 available 却零披露）；HSI 新浪回退失败归因误用外层 yf 异常变量（`e`→`e2`）；csindex 空响应早退曾把已满 250 日的 ERP 台账打回「进行中」——空响应按「无增量」处理、台账现状原样返回；HS300 新浪回退结果同入 `_MKT_CACHE`（tx 失效时批量不被每股重打）；`_index_snapshot` 空序列守卫（防 IndexError 被 caller 误记 qq 簇假败）。
- 随附口径收口（不改行为）：03-synthesis「现十块」→十五块；09 裁定引文四块括注（裁定 6 增补后为五块）；01 index 行 HK 消歧（本块对 hk not_supported）；EXT_PACK_BUDGET 四新键注释为口径陈列；CLUSTERS 注释 em_datacenter 失败面加宽取舍。
- 源验证：三份探针实测报告（两融/指数+ERP/新开户，含字段逐字记录、交叉验证与失败形态）存 `.context/probe-*.md` 并摘录进 PR 描述；五块联网实跑冒烟全通（margin 22988.6 亿与三所加总闭合、ERP 6.2%=1/12.8−1.61%、HS300/ALLA 当日 K、HSI 修复后入列）。

## [0.0.18] - 2026-11-04

### Added

- 在册股短/中期走势参考机制（用户 2026-11-04 五项裁定：生成时机=收盘批量+决策现算混合、覆盖=全在册 universe 21 只、情绪面含市场级块、权限=零权重纯参考、市场级四块一次全落——后者随 0.0.19 落地）：新增 `references/09-outlook.md`（机制 SSOT）、`scripts/outlook.py`（第五件硬门禁纯函数件：双轨 σ√h 预测带 + first-passage 触及概率（复用 lens/realized_vol/HORIZONS_OF/MIN_SAMPLES，import 禁复制）、个股级情绪键与资金流投影、每股×轨×horizon 经验计数桶（observed 不入桶、n<MIN_SAMPLES 标不足）、与前卡确定性日差连向、实盘股用户锚脱敏投影（operations 只读 time/code/action/price，quantity/cost_price/成本派生涨幅绝不落盘，负断言钉））、`batch/outlook_daily.py`（非门禁编排：universe import watch、FetchLock 单窗 + 股间 8–12s 退避、收盘卡幂等 upsert 入 `~/.vibe-stock/outlook/<date>.jsonl`、`<date>.md` 全集日表；盘中卡拒写、当日已卡幂等跳过）。
- 诊股注入（diagnose.py）：prepare 恒现算落 `.vs/outlook.json`（失败/弃权/快照即清除残留卡，lens 清理同款不变式）；context-pack 新增「走势参考（零权重）」节并**置于扩展块之前**（超预算时扩展节先截、本节存活，截断序 selftest 钉）；报告新增 4c「短/中期走势参考（零权重 · 不进裁决）」条件节（band/beta/零权重三声明；身份软校验不符只跳节+warn——与裁决事实面身份 exit 2 的分级依据）。
- 两把尺分立与零权重执法面：band_note 逐字钉（预测带≠后验判定带：default ±2% 固定带、position σ√h 仅 T+60 记分——判定带 SSOT 仍在 postmortem，卡片只引用）；outlook selftest E4 同构钉（evidence 挂卡不扰动 evidence_cap）；03「透镜不进裁决」节 outlook 并列句共用同一执法面。
- 门禁升格：scripts/ 四件 → **五件**（`outlook.py --selftest` 提交前置；AGENTS 测试节/目录表、evals/README、PIPELINE 回归块、README 四处同步 + SKILL 判表命令入口；monitor 两件的「非阻塞第五条」措辞改「非阻塞旁路门禁」防与第五件硬门禁撞名）；指针全套同步（SKILL frontmatter 0.0.18+description+判表+工作流注释、PIPELINE 头部/② 段/命令速查、README、AGENTS、knowledge-map、04 4c 条目与 portfolio 契约表 operations 消费行）。
- 版本依据：信息面新增机制 + 门禁收严（四件→五件），裁决链与后验零改动，按 0.0.x patch 升版。

### Fixed（0.0.18 合入前独立盲审 22 项全修）

- 严重三项：S1 selftest fixture 与真实持仓零重合改为**动态负断言**（两侧 `_norm_code` 归一、覆盖 holdings∪operations 全量码，不再假设码段永真；hk fixture 换合成段并构造 4/5 位真互通用例）；S2 `persist_card` 落盘前剥离 `user_anchor`（实盘操作价/成本派生 move_pct 绝不入全局时序——只住 workdir 现算卡，存量卡已清洗重写，selftest 钉）；S3 满卡 17 行超 pack 截界致零权重声明被截（改为截内容不截声明、报告侧按内容过滤，破坏性实验钉）。
- 较严重六项：M1 `_streak` None 改真断链（中段缺值掐断历史，不桥接）；M2 批量取数 now 每股现取（冷却/熔断/时段判定不吃批次开头陈旧值）；M3 熔断账本落盘移入 finally + 出卡计算并入 try（异常/Ctrl-C 不丢账本）；M4/L8 新增 **<17:10 墙钟门**（代码闸：收盘竞价定型窗内早跑会把未定型 K 钉成当日卡且幂等键当日不再重取——「≥17:10」时点纪律落成代码，--force 可越过）；M5 signals 快照合成信号不入经验桶/不作锚（archive 索引同口径）；M6 门禁登记口径修正为四处（SKILL 判表只登记命令入口）+ batch/README、07「四件」→「五件」存量指针同步 + monitor「非阻塞第五条」改「非阻塞旁路门禁」防撞名。
- 一般项：anchors_source 三态精确化（无有效键=abstained）· σ 退化链删不可达的 rv120 中间档（注释同步「宁宽勿窄」）· 预测带下沿夹 0（极端波动）· first-passage 高估注记随 pack σ 行输出 · `--daily`/`--stock` 显式旗标（裸跑不触发 ~84 HTTP）+ 抖动改 random.uniform · 锁竞争独立计数不入「盘中拒写」· jsonl 坏行统一跳过 + tmp 补 fsync · prepare 日 K 全链失败早退同清残留卡 · 经验桶 n 含 neutral 与台账 MIN_SAMPLES 只数 decisive 的口径差异在 09 显式声明 · pack 预算挤占记为已知取舍 · operations 读入按 time 排序防乱序登记 · prepare selftest 用例 STATE_DIR 重定向临时目录（门禁封闭不触真实状态文件）。
