# 09 · 在册股短/中期走势参考（outlook · SSOT）

定位：从每日跟踪积累的数据经验，为每只在册股产出**零权重**走势参考卡
（数学 × 情绪 × 经验三面），供每次操作决策作参考——用户 2026-11-04 五项
裁定（生成时机=收盘批量+决策现算混合、覆盖=全在册 universe 21 只、情绪面
含市场级块、权限=零权重纯参考、市场级四块一次全落——裁定 6 增补两融账户
参与度替代口径后为五块）是本机制的边界依据。
实现：[scripts/outlook.py](../scripts/outlook.py)（六件硬门禁之一，纯函数件）+
[batch/outlook_daily.py](../batch/outlook_daily.py)（非门禁编排）；注入点在
[diagnose.py](../scripts/diagnose.py)（prepare 现算 / context-pack / 报告 4c）。

## 权限与红线（无条件全局规则）

- **零权重**（裁定 4）：不进裁决聚合/置信帽/两轨后验记分/RiskGuard/策略
  YAML；进 context-pack（信息面，与 mid_term 同地位——LLM 可引用其数字作
  rationale 素材）与报告 4c 条件节。RiskGuard 接入**已评审落地**（0.0.21，
  分期表 P3 判据 ②-8——LLM 判据走 risk.json 通道只降不升，零权重红线不破：
  消费的是市场级数据块而非本卡）；机械布尔降档合并仍随 07 P2/RSI 合流评审
  （selftest E4 同构钉：evidence 挂 outlook 键不扰动 evidence_cap）。
- **两把尺分立**（无条件全局规则）：预测带（零漂移 ±σ_d×√h）只描述价格
  分布量级，判定带口径 SSOT 在 [05](05-postmortem.md)（default 恒 ±2%、
  position σ√h 仅 T+60 记分）——卡片只引用不复算，band_note 逐字钉。
- **脱敏**（无条件全局规则）：portfolio.json operations 只投影
  time/action/price 与其后公开行情涨跌%（[04](04-report.md) 契约表消费行）；
  quantity/cost_price/成本派生涨幅绝不消费绝不落盘（selftest 负断言钉）；
  现价距波段带 band_hi 百分比是纯事实呈现（获利了结风险对齐用户偏好），
  零指令；浮盈等需成本的敏感维度仍由手维 portfolio.md 承担。

## 卡片三面口径

- **数学面**（零新常量零新算法，import 禁复制）：期限=双轨同构
  （[archive.HORIZONS_OF](../scripts/archive.py)：default=T+1/3/5/10 短期、
  position=T+20/60/120 中期）；σ_d 退化链 rv60→2% 兜底（`fetch.realized_vol` SSOT；rv60 不足时 rv120 的
  ≥60 门槛必不满足，中间档事实不可达不设；兜底 2% 日波动宁宽勿窄——宽于
  postmortem 退化带 2%×√(h/10) 的隐含 σ_d≈0.63%，预测带是参考量级不是
  判定带）；触及
  概率封装 `lens.touch_probability`（first-passage 连续监测口径：离散日
  监测约高估 2–4pp、短窗 T+1/T+3 更甚——pack σ 行一次性注记「参考上限」，
  不修值）；锚按轨取 signals key_levels——default 三价
  /position 波段带三键各取各轨（[07](07-monitor.md)「价位锚分轨」同口径），
  **无 position 信号的股中档锚 abstain，禁现算波段带充锚**；default 轨无信号
  时回退 allocation 三价（levels_source=allocation 的 sim 股，[07](07-monitor.md)
  同款回退——pack 锚行注「弃权/回退」来源，禁把 allocation 三价读成登记信号
  价位）；趋势面=mid_term
  因子原样投影 + 与前卡**确定性日差**（「rv60 三连降」类纯派生事实），
  不造 regime 标签（策略语义在 YAML，代码复制即第二事实源）。
- **情绪面**：个股级零新增取数（mid_term 情绪键 + moneyflow summary 扩行；
  港股降级南向+量能代理「力度弱一档」按 [08](08-midterm.md) 原文）；市场级
  五块（0.0.19 已落地，[01](01-evidence.md) 扩展块表）：margin 两融余额、
  index 指数基准（HS300/ALLA/HSI 快照+MA60）、turnover_pctile 全A换手分位
  （成交活跃度代理）、erp（月频主口径+日频增量台账
  `~/.vibe-stock/erp_pe_daily.jsonl`——裁定 7 的经验积累载体，满 250 日出
  日频分位）、margin_accounts 两融账户参与度（裁定 6：原新开户上游停更的
  替代口径，不冒充新开户）。市场维度共享数据经 fetch 层 `_MKT_CACHE` 同进程
  一次取数；卡片市场级节全缺时 abstained。
- **经验面**：signals.json evaluated 的 per code×profile×horizon 计数桶
  {n, hit, miss, neutral}（只数 postmortem 落账的 outcome，observed 不入桶
  ——05 口径）；n < `postmortem.MIN_SAMPLES`(10) 标 sample_insufficient——
  描述性统计非绩效因子，永不进聚合与台账。口径差异显式声明：本桶 n=hit+
  miss+neutral（含 neutral）且阈值常量仅借用 MIN_SAMPLES 作「不足」标注；
  台账侧 MIN_SAMPLES 只作用于 decisive（hit+miss）——两把尺不得混读。
  数据源节奏（0.0.24 · I-022）：evaluated 由 postmortem 收盘评估槽产出
  （[05](05-postmortem.md)「收盘后评估节奏」）——无评估运行则经验面恒空
  （实测 69 条 pending 到期零评估的空转形态）。

## 写拓扑与生成节奏（无条件全局规则：唯一写者）

- **全局时序 `~/.vibe-stock/outlook/<date>.jsonl`（每股每日一行、按
  (market,code) 同日幂等 upsert、tmp+replace 原子替换）唯一写者=
  batch 侧批量命令**；诊股 prepare 恒现算只落 workdir（.vs/outlook.json，
  lens 同款），失败/弃权/快照形态即清除残留卡（防旧卡数字拼进新证据，
  lens 清理同款不变式，diagnose selftest 钉）。
- **盘中卡不入全局时序**：persist_card 对 price_kind=intraday 前置拒写
  （末根未完成 K 线污染日序）；卡片 date=末根日 K 交易日（与 signal.date
  同口径）。
- **收盘批量**：`--daily [--force] [--no-calibrate]`（[batch/outlook_daily.py](../batch/outlook_daily.py)）
  宇宙=watch.load_universe（在册 21 只 SSOT 投影，禁复制）；当日已卡非
  --force 跳过取数（幂等）；`--render` 零取数重渲日表；`--stock <code>`
  单股刷新（宇宙外股明确提示先 `watch --print-universe` 重派生——宇宙当日
  派生一次后缓存，盘中新入册股当日不在其中，I-024）；`--calibrate` 单独跑
  校准。**自动校准（0.0.24 · I-022）**：--daily 成功后默认自动接 --calibrate
  （幂等台账无损失，launchd 17:35 槽零改动获得校准增厚；--no-calibrate 跳过；
  --stock 单股不触发）；历史卡全集有、latest_cards（10 日窗）无的股打
  warn——其历史卡校准样本缺席须可观测（退册/断档>10 日）。
- **跨日读面**（条件：盘后各源末根更新有时差——A 股链常滞后、港股已出；
  做法：日表与幂等一律经 `outlook.latest_cards` 每股取最新一张卡（跨最近
  10 个日文件），幂等按卡片 `persisted_at` 的批次运行日判断，日表带「交易
  日」列如实披露、在册无卡列「缺卡」行；坑位：按单个日文件读会让同批次
  漏股、按卡片交易日判幂等会让末根滞后股每次重取——
  [I-010](../docs/.agents/issue.md#I-010) 实跑实证）。
- **时点墙钟门（无条件前置，代码闸非使用纪律）**：<17:10 拒跑（--force 越
  过）——收盘竞价定型窗（A 15:00–15:10、港 16:00–16:08）内源末根未定型，
  早跑会把未定型收盘价钉成当日卡且幂等键让当日不再重取。谓词 SSOT=
  `outlook.close_gate_open`（0.0.24 起，I-023 收编——编排层禁内联 (17,10)
  字面量）；末根未完成过滤谓词同款收编为 `outlook.final_bars`、校准真实
  增量计数为 `outlook.count_new_samples`——三道防线均住硬门禁件
  scripts/outlook.py（六件之一）内、
  有 selftest 钉（batch 编排层无门禁，防线住编排层则回归无门禁可拦）。
- **并发与预算**：FetchLock 单窗（close_pass 同款，120s 超时挂起+告警重跑，
  锁竞争独立计数不入「盘中拒写」）；股间退避 8–12s（random.uniform，[06]
  (06-batch-scan.md) 串行+抖动纪律；退避在锁窗内串行执行，锁持有约 4–7
  分钟——错峰 ≥17:10 与 close_pass 无重叠窗）；**市场级五块缓存语义**：
  `_MKT_CACHE` 同进程只缓存成功数据（fetch_failed 不固化，熔断器
  「连续 3 败」阈值不被绕过）；**跨进程无缓存**（06 批量 subprocess 形态
  下每股全价、N 股付 N×五块 HTTP——已知取舍，后续按当日 jsonl 缓存收口）；
  **ERP 日频台账 last-writer-wins**（诊股不持 FetchLock，双终端并发后写者
  覆盖前写者当日增量——增量窗 20 日高度重叠、次日自愈，接受为既定取舍）；
  预算
  ≈21 条日 K 链（回退全触发上界 ~84 HTTP）+ moneyflow 每股 1 条——正经
  消耗诊股额度（写熔断账本，不走盯盘本地退避）；**时点 ≥17:10**（避开
  16:15 盘后兜底槽）；「盯盘期间不跑 outlook 批次」（[07](07-monitor.md)
  I-005 延伸句）。日表 `outlook/<date>.md` 为派生视图（幂等重渲、当日无
  事件也出），免责尾注与 day-summary 同款纪律。
- **stale 判定**：决策侧数学面恒现算不受缓存牵制；stale 只作用于日表行
  与「上一张收盘卡片」展示的时差披露（卡片 date ≠ 最近已完成交易日）。

## 消费面

- **context-pack**：「## 走势参考（零权重，不进裁决）」节，**置于
  render_ext_blocks 之前**——pack 超 PACK_CHAR_CAP 时整截的是扩展节、本节
  存活（截断序钉在 diagnose selftest）；有界 ≤16 行（满卡截内容不截零权重
  声明，破坏性实验钉）；abstained 如实一行；position 锚弃权出固定注记行
  （「锚：弃权——无可用 position 锚…禁现算充锚」——弃权事实可见化 0.0.24，
  不得以锚行结构性缺失静默呈现，计入 16 行预算）、allocation 回退锚行注
  来源（禁读成登记信号价位）。已知取舍：本节 ~1.5–2.5k 字符
  计入 PACK_CHAR_CAP，临界 pack 会加速扩展节整截——零权重参考与十扩展情报
  块同预算竞争，超限先截扩展节是既定截断序，不另设独立预算。
- **报告 4c**：「## 短/中期走势参考（零权重 · 不进裁决）」条件节（04
  结构表），band/beta/零权重三声明齐全；弃权注记/锚来源标注随 pack 同款
  （0.0.24）；卡片身份与证据不符只跳节+warn
  （零权重软校验——与 evidence/verdict 身份 exit 2 的分级依据：裁决事实面
  防串目录 vs 信息面可观测即可）。
- **日表**：outlook/<date>.md 全在册 21 只（real→sim→watch 排序），唯一
  原生覆盖在册全集的可读面；零指令、脱敏、「收盘后参考·非投资建议」尾注。
- **盘中决策携带（0.0.24 显式句，0.0.24 四项裁定之 4）**：07 P2 升级链的 T1
  context-pack / P2 建议卡**必含**走势参考节（prepare 恒现算出卡承载）；
  snapshot 通道（fetch 快照兜底形态）不得阻断出卡——盘中告警通知面仍只报
  事实+待收盘复核（07 通知面钉），决策支持内容按 07 路由到 P2 建议卡。

## 分期表

| 期 | 内容 | 状态 |
| :--- | :--- | :--- |
| v1（0.0.18） | 卡片三面 + prepare/pack/4c 注入 + 收盘批量与日表 + 市场级节 abstain 占位 | ✅ |
| v2（0.0.19） | 市场级五块 + 指数日 K 链共享件一次全落（裁定 5）：fetch margin/index/turnover_pctile/erp/margin_accounts 块全套（簇 16→20：jin10/sina_idx/legulegu/csindex 新增）+ 01 表行与 backlog 状态 + 08 Phase 5 预留节指针化 + 07 P3 指数链就绪句 + 卡片市场级节出实数。源实测后用户 2026-11-04 补充裁定：① 新开户上游停更 → 改接两融账户参与度（margin_accounts，户口径）；② ERP → 月频（乐咕×10Y）立即可用 + 中证官网 P/E2 日频增量落盘 `erp_pe_daily.jsonl`，满 250 日接管 | ✅ |
| P2 | **day-summary 附件（0.0.20 已落地）**：close_pass 渲染「走势参考（上一张收盘卡 · <date>）」节——由 close_pass 自身消费 outlook jsonl 重算（幂等，外挂追加会被重渲冲掉的问题不存在）；当日卡 17:35 才出、收盘复核只见 <today 卡（语义钉）；无卡/无目录不出节 | ✅ |
| P2 | **launchd 17:35 独立槽（0.0.20 已落地）**：模板 `batch/outlook/com.threefish.vibestock.outlook.plist`（周一至五 17:35 单槽每日批量；与 16:15 兜底槽错峰 80min；一次性命令无 KeepAlive、失败次日自愈；节假日误拉一次无害——无交易日历取舍同 07 P4；RunAtLoad=false 不投机拉起）。安装三步见模板注释（占位替换/建日志目录/bootstrap）。**部署同步纪律（I-021 实证）**：plist 指向技能目录 clone——PR 合入 main 后须 `git pull` 同步该 clone，否则调度路径持续跑旧版（0.0.18 滞后 0.0.21 十提交的日表回退/ERP 积累停摆实证） | ✅ |
| P3 | **RiskGuard 接入（0.0.21 已评审落地）**：形态=08 ②族新增判据②-8「市场级杠杆拥挤」（margin 块 70 日分位 >90 且 Δ5d >+2% **且**个股级拥挤键并发 → 风险角色 downgrade·medium）——走既有 risk.json 通道、只降不升、LLM 判据非机械布尔（机械布尔合并仍随 07 P2/RSI 合流）；阈值属首版防御性设定，放宽须评审 | ✅ |
| P3 | **预测带自校准后验（0.0.21 已落地）**：`--calibrate` 子命令——历史卡 × 锚 × horizon 的触及概率 vs 实际触及（方向按卡日收盘定、不满窗不记右删防护），样本幂等台账 `outlook-calibration.jsonl`、渲染 `outlook/calibration.md` 分桶校准表（桶 n<30 标不足）；信息面披露——不进裁决/台账/不改预测带公式 | ✅ |
| v3（0.0.24） | **查漏补缺四件（I-021~I-026）**：① postmortem 收盘评估槽（经验面数据链断点——evaluated 无运行机制则经验面/绩效因子恒空）；② --daily 自动接校准（台账不再手动增厚）；③ 三道防线收编进 scripts/outlook.py（close_gate_open/final_bars/count_new_samples，I-023）；④ 弃权可见化 + allocation 锚来源标注 + --stock 宇宙外提示（I-024/I-025） | ✅ |
| 再评审 | bars 台账（按日持久化 OHLCV）：**已显式否决**——全部现行因子在 250 根在线窗内，台账引入 qfq 重基准/无锁双写/未完成 K 线三重新风险；出现 >250 根窗真实消费方再评审（01 backlog「长周期 theses 台账」条目同源） | 否决 |
| 再评审 | **中期锚覆盖增强**（用户 2026-11-04 裁定「可见化+登记评审项」）：现状 position 锚仅持仓股有（7/21）——候选=default 三价锚延伸至中期轨 / 250 日高低点作参考锚；与「禁现算充锚」裁定的关系（登记信号 SSOT 原则）是评审核心，放宽须人工评审 | 预留 |
| 再评审 | **ERP 日频分位接管实现**：daily_ready 旗标满 250 日（ETA ~2027-10）须有消费实现（日频分位计算+主口径切换），当前为纯声明无代码路径（I-026 登记）——满窗前落地 | 预留 |

## 回归门禁

`uv run --no-project scripts/outlook.py --selftest` 是六件硬门禁之一
（四处登记：AGENTS.md 测试节与目录表、evals/README、PIPELINE 回归块、
README 回归行；SKILL 判表只登记命令入口不承载门禁语义），提交前置与既有
五件同级；判据只收严。核心钉：预测带数学（带宽 ∝√h
单调、lo<price<hi）· 触及概率复用 lens（对称/单调——对称钉 0.0.24 补）·
锚按轨（无 position 信号 abstain、禁现算充锚、allocation 回退标注来源）·
港股 5 位读时归一 · 经验计数（observed 不入桶、
MIN_SAMPLES import 自 postmortem 防第二常量）· 日差连向（None 断链）·
脱敏负断言（产物无 quantity/cost_price/金额/成本派生键）· 弃权如实
（含 position 弃权注记进 pack/4c）·
upsert 幂等 + 盘中拒写 · 墙钟门边界双态 + 末根过滤 + 校准真实增量
（0.0.24 收编钉，I-023）· E4 同构零权重钉（evidence 挂卡不扰动
evidence_cap）
· 确定性。diagnose selftest 另钉：pack 节 + 截断序存活 · 报告 4c 三声明 ·
无卡/弃权如实 · 身份软跳 · prepare 落卡/快照清残留。
