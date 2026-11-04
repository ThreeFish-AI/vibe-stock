<!-- markdownlint-disable MD033 MD051 -->
# Issue 处理档案

> 已处理 Issue 的摘要索引，便于同类问题跨上下文处理；同一 Issue 只在原条目增量更新。

| ID | 标题 | 状态 | 完成时间 | 详情 |
| :--- | :--- | :--- | :--- | :--- |
| I-001 | 同日重跑覆盖报告致信号→报告指针失真：改单日多版本文件 | ✅ 已完成 | 2026-10-30 | [详情](#I-001) |
| I-002 | 港股代码归一不一致致同一标的身份分裂：统一补 5 位 | ✅ 已完成 | 2026-10-30 | [详情](#I-002) |
| I-003 | signals.json 解析失败被静默当空、下次 report 覆盖历史：严格加载 + 原子写 | ✅ 已完成 | 2026-10-30 | [详情](#I-003) |
| I-004 | 同日重跑重复登记信号（八元组去重缺失）——0.0.16 以同 report_id superseded 落地 | ✅ 已完成 | 2026-11-03 | [详情](#I-004) |
| I-005 | 状态文件健壮性缺口：signals 无锁、ledger 损坏被清空、market="?" 信号使 postmortem 崩溃 | 🔄 进行中 | — | [详情](#I-005) |
| I-006 | 总览持仓合并契约与真实 portfolio.json v2 结构脱节：loader 归一 holdings 列表 | ✅ 已完成 | 2026-11-02 | [详情](#I-006) |
| I-007 | 盯盘 P1 selftest fixture 写入真实持仓（公开仓）：换合成标的 + 零重合负断言 | ✅ 已完成 | 2026-11-02 | [详情](#I-007) |
| I-008 | 盯盘 launchd 模板拉不起、异常不自愈、跨日 close_done 残留：绝对路径 + SIGABRT + 按日归零 | ✅ 已完成 | 2026-11-02 | [详情](#I-008) |
| I-009 | 盯盘 launchd 模板仅 09:15 单槽，重启/开机后当日不再拉起：交易时段补拉槽 + 16:15 盘后兜底 | ✅ 已完成 | 2026-11-03 | [详情](#I-009) |
| I-010 | 走势参考日表按卡片交易日单文件读取，盘后源末根时差致同批次漏股：每股最新卡跨日合并 + 幂等按批次运行日 | ✅ 已完成 | 2026-11-04 | [详情](#I-010) |
| I-011 | margin 取数链两缺陷——金十回退零配对行崩链、主源行数不足不触发回退致 source=None 渗透 | ✅ 已完成 | 2026-11-04 | [详情](#I-011) |
| I-012 | C1 渲染收口缺第二道：残块缺键经渲染端裸 %s 打出 None%/0.00% 字面量；A 股指数无 ≥60 行守卫 | ✅ 已完成 | 2026-11-04 | [详情](#I-012) |
| I-013 | index/erp 链守卫与归因三处：HSI 短序列零披露、新浪回退失败归因用错异常变量、csindex 空响应打回满仓台账 | ✅ 已完成 | 2026-11-04 | [详情](#I-013) |
| I-014 | --calibrate 无墙钟门/末根未完成过滤：盘中手跑把未定型末根 K 永久钉成错误样本 | ✅ 已完成 | 2026-11-04 | [详情](#I-014) |
| I-015 | 校准台账与样本面三处：qfq 重基准偏置无防御、类型损坏行毒丸崩在写回后、「新增样本」计数虚报 | ✅ 已完成 | 2026-11-04 | [详情](#I-015) |
| I-016 | 后验评估消费盘中未完成日 K，到期 horizon 被盘中价误判命中；05 基准口径前后矛盾 | ✅ 已完成 | 2026-11-04 | [详情](#I-016) |
| I-017 | 港股南向持股变动（T+2 交收）被标为当日净买入，money_flow 把 D−2 成交读成当日背离 | ✅ 已完成 | 2026-11-04 | [详情](#I-017) |
| I-018 | box_60d 含当日 K 线，新低日「精确触箱底」是同义反复，被当作支撑验证 | ✅ 已完成 | 2026-11-04 | [详情](#I-018) |
| I-019 | 中线波段带 g 为收益率却按价差加减，带宽塌缩到不足 1 港元，selftest 同公式测不出 | ✅ 已完成 | 2026-11-04 | [详情](#I-019) |
| I-020 | 逆势窄门读错裁决轨：quality_value 买点从 default 轨取，生产永不触发且被非法 fixture 掩盖 | ✅ 已完成 | 2026-11-04 | [详情](#I-020) |


<a id="I-001"></a>

## I-001：同日重跑覆盖报告致信号→报告指针失真

- **问题描述**：601888 在 2026-10-28 跑了 3 次 report，`reports/601888-2026-10-28.md` 被覆盖两次，signals #3/#4/#5 指向同一文件，前两次的报告内容丢失。
- **表因根因**：`cmd_report` 以 `<code>-<date>.md` 为固定文件名 `open(path, "w")` 直写；signals.json 只追加，两者语义不对齐。
- **处理方式**：新增 [archive.py](../../scripts/archive.py)，报告改为 `reports/<code>.<market>/<date>.md` 单日多版本（同日追加 `vN`，未变节写「同 vK。」）；信号新增 `report_version`；`migrate-reports` 迁移存量，按文件 mtime 与 `created_at` 同刻认领内容版，其余标 `report_lost`。规则见 [04-report](../../references/04-report.md)「落盘与跟踪」。
- **后续防范**：`diagnose.py --selftest` 钉住同日两版、链式去重、迁移 dry-run/CAS/崩溃收敛；破坏性实验（改回覆盖写）必红。
- **注意事项**：#3/#4 的报告在修复前已被覆盖，不可恢复；定位报告只认 `report_path` + `report_version`，不要从 `report_id` 拼路径。

<a id="I-002"></a>

## I-002：港股代码归一不一致致同一标的身份分裂

- **问题描述**：`0700.HK` / `hk0700` 归一成 `0700`，`hk00700` / `00700` 归一成 `00700`，同一只腾讯会落两个报告目录、两组信号，对立失效也互不可见。
- **表因根因**：[fetch.py](../../scripts/fetch.py) `detect_market` 港股分支原样返回 4–5 位捕获组；下游 `yf_ticker` 各自补 4 位掩盖了问题，`_news_via_qq` 拼出 `hk0700` 实际取不到数。
- **处理方式**：港股分支统一 `zfill(5)`；`fetch.meta_stock_code`（0.2.2 起，`diagnose.stock_code` 为其诊断侧封装、adjudicate 同源消费）作为报告/信号代码身份唯一推导处，吸收旧 evidence 里的 4 位码。
- **后续防范**：selftest 断言各输入形态→`00700`、规范码是不动点且定宽（cn 6 / hk 5）。
- **注意事项**：其他安装若已存在 4 位港码的信号，不自动改写身份字段，`migrate-reports` 只告警，这类信号不进索引；对立失效比对已按读时归一（补 5 位），旧信号与新信号互通；report 身份闸门另绑定 verdict `stock_code`（0.2.2 起裁决产出携带）。

<a id="I-003"></a>

## I-003：signals.json 解析失败被静默当空

- **问题描述**：signals.json 一旦损坏（半写、手改出错），下次 report 会把它当 `[]`，追加一条后写回，历史信号全部丢失。
- **表因根因**：`diagnose.load_json` 吞掉所有异常返回默认值，register_signal 以此读改写。
- **处理方式**：`archive.load_signals` 严格加载（缺文件 = `[]`，解析失败抛错）；写入改 tmp + fsync + `os.replace`；`cmd_report` 写盘前先预检，失败 exit 2 且零写入。
- **后续防范**：selftest 断言损坏时 report 返回 2、signals.json 字节不变、不产生孤儿版本。
- **注意事项**：postmortem 的 `_load` 仍是宽松加载，见 I-005。

<a id="I-004"></a>

## I-004：八元组去重未实现

- **问题描述**：[05-postmortem](../../references/05-postmortem.md) 曾声明信号按 (report_id, source_type, market, code, profile, action, horizon, regime) 去重，实现只追加；同日重跑会登记多条同向信号，buy/sell 族后验时同一意见源被重复归因，绩效因子失真。
- **表因根因**：`register_signal` 未实现去重；0.2.2 前 diagnose.py docstring 还写着「八元组去重」，已改为如实描述。
- **处理方式**：2026-11-03 已落地（0.0.16）：`register_signal` 对同股、同 profile、同 `report_id` 的旧 pending 信号标 `superseded`（同日重跑以最新版为准，不再双计样本），对立失效一并按 profile 隔离；05 规约「superseded（I-004 落地）」与 diagnose selftest 已同步。
- **后续防范**：实现时须同步 05 规约与 selftest，且只许收严（不得让重复样本抬高绩效因子）——已按此执行。
- **注意事项**：superseded 保持未评估形态（区别于 invalidated/evaluated）；当前现网同日多信号均为 watch（只观察不记分）。

<a id="I-005"></a>

## I-005：状态文件健壮性缺口

- **问题描述**：① signals.json 读改写无文件锁，report 与 postmortem 并发可能丢更新；② postmortem `_load(LEDGER, {})` 吞解析异常，损坏时会用本次增量覆盖整本台账；③ 快照模式登记的 market="?" 信号进入 postmortem 后，`fetch_daily_bars` 取 `CHAINS["?"]` 抛 KeyError。
- **表因根因**：状态层没有统一的加载/写入/锁约定，各脚本各自读写 JSON。
- **处理方式**：部分落地（0.0.16，2026-11-03）：③ market 守卫跳过（非 cn/hk 保持 pending）此前已生效；signals.json 严格加载（损坏中止退出、不覆盖）与全状态文件原子写（`ar.write_json_atomic`）已落地。①并发文件锁与②台账损坏被增量覆盖仍未修——台账仍宽松加载，损坏当空后下次有增量会整体覆盖写回（postmortem.run 注释已如实标注清零风险）。
- **后续防范**：统一到 [archive.py](../../scripts/archive.py) 的严格加载 + 原子写；postmortem 跳过非 cn/hk 信号。
- **注意事项**：迁移期间勿并发跑 report / postmortem；②修复前勿在台账损坏状态下跑可记分 postmortem。

<a id="I-006"></a>

## I-006：总览持仓合并契约与真实 portfolio.json v2 结构脱节

- **问题描述**：PR #15 初版 `load_portfolio` 按自设扁平契约（`<code>.<market>` → {qty, cost}）整 dict 返回，而真实 `~/.vibe-stock/portfolio.json` 为 v2 结构（持仓在 `holdings` 列表，元素 `{code, market, quantity, cost_price, …}`）——顶层取键恒 None，总览持仓两列对 7 只实盘持仓全部渲染 —，特性静默失效。
- **表因根因**：契约按假设自设，未对照真实 SSOT 文件验证；`isinstance(data, dict)` 校验放过 v2 顶层对象。
- **处理方式**：Review 阶段实测复现后修复（fbddf3a）——loader 归一 v2 `holdings` → `<code>.<market>` → {qty, cost}，缺失/损坏/非对象/无 holdings/空表一律回 {}，元素脏值跳过；04/CHANGELOG 契约句同步；selftest 增 v2 形状/空表/脏元素/集成直通钉与 NaN/Infinity 降级钉。
- **后续防范**：消费用户手维状态文件的改动，合入前必须对真实文件实测（schema 探查 + 端到端渲染），不能只按自设 fixture 验证。已机制化（0.0.14）：契约定义、漂移 `warn:` 可观测与合入前实测规约见 [04 · portfolio.json 契约](../../references/04-report.md#portfoliojson-契约)，selftest 钉在 `diagnose.py` T11d 与 `postmortem.py` 持仓契约段。
- **同类问题影响**：其余读 `~/.vibe-stock/` 的入口（names.json）由 report 写穿维护、形状自控，不受影响。
- **注意事项**：`portfolio.json` 属用户手维 SSOT，只读合并、永不写回；空表视同缺失（清仓收起持仓两列）。

<a id="I-007"></a>

## I-007：盯盘 P1 selftest fixture 写入真实持仓（公开仓）

- **问题描述**：`batch/monitor/watch.py` 初版 selftest 的宇宙派生 fixture 直接用了用户实盘两只持仓的真实代码、数量与成本，rules.py 用例沿用真实止损/目标价；仓库为 PUBLIC，提交即泄露。
- **表因根因**：脱敏断言只检查产物（universe.json 无成本字段），不检查测试输入本身；编写 fixture 时顺手取了会话上下文里的真实数值。
- **处理方式**：提交前对抗评审拦下（未进入正式提交历史）——全部 fixture 换成合成号段与虚构数值（600001/00001 @10.00 等），新增「fixture 与真实 portfolio.json 零重合」负断言（文件缺失跳过），提交前对新增/改动行做真实代码与成本的全量扫描。
- **后续防范**：规约句落 [07 · 宇宙层](../../references/07-monitor.md#宇宙层) 脱敏条（fixture 一律合成标的 + 负断言）；README/CHANGELOG 不写实盘只数等可推断持仓的数字。
- **同类问题影响**：scripts/ 既有 fixture 使用 evals 合成快照，不受影响；凡新增读 `~/.vibe-stock/portfolio.json` 的测试均适用本条。
- **注意事项**：git 历史一旦含真实值需改写历史并轮换——本次未提交即修复，无需处理。

<a id="I-008"></a>

## I-008：盯盘 launchd 模板拉不起、异常不自愈、跨日 close_done 残留

- **问题描述**：① plist 用 `/usr/bin/env uv`，launchd 默认 PATH 不含 `~/.local/bin`，exit 127；② `KeepAlive.Crashed` 只认信号崩溃，Python 未捕获异常 exit 1 不重拉；③ `close_done`/`src_fail` 跨日继承，次日起收盘复核静默跳过；④ `fetch_daily_bars` 传 datetime 而非 int epoch 且未解包四元组，`--close` 全部挂起；⑤ `--close` 港股回退链缺 yfinance 依赖，东财限流即单源全挂。
- **表因根因**：launchd 语义与 shell 环境差异未实机核对；外部函数契约凭印象调用；日粒度状态只重置了 rules 子树。
- **处理方式**：plist 改 `__UV_PATH__` 绝对路径占位 + `AfterInitialDemand` + README sed 安装命令（实测零残留占位、plutil OK）；`--loop` 未捕获异常 → 通知 + `os.abort()`（SIGABRT）；`ensure_state` 按日期归零 close_done/src_fail/next_due；`fetch_daily_bars(..., int(now.timestamp()))` 四元组解包；运行时统一 `--with akshare --with efinance --with yfinance`；`--close` 加收盘时点门。selftest 增跨日归零钉。
- **后续防范**：07「宿主形态」与「收盘复核」节写入全部坑位；调用 scripts/ 函数一律对照其 docstring 与既有调用点（fetch.py:1943、postmortem.py:186）。
- **同类问题影响**：P2 会话接管 exit 2 同受 Crashed 语义约束（不重拉为预期）。
- **注意事项**：launchd 首次投递通知会触发 macOS 授权弹窗，需用户手动允许。

<a id="I-009"></a>

## I-009：盯盘 launchd 模板仅 09:15 单槽，重启/开机后当日不再拉起

- **问题描述**：LaunchAgent 模板 StartCalendarInterval 仅周一至周五 09:15 单槽、RunAtLoad=false；工作日 09:15 后系统重启/开机/重新登录，LaunchAgent 重新加载后当日已无日历槽，盯盘不再拉起直至手动 kickstart。launchd.plist(5) 只承诺睡眠期间错过的日历触发在唤醒时合并补发一次，关机/重启期间错过的不补发。脱敏实测时间线（2026-11-03）：09:15 触发时机器睡眠 → 09:30 唤醒合并补发拉起 → 09:39 首轮跑完 → 09:41 系统重启进程被杀 → 当日未再拉起 → 10:52 手动 kickstart 补拉，盲窗约 73 min；盲窗内一只在盯股盘中最低价击穿止损线而未出事件（补拉时现价已回到线上；若当日此后再度触发出事件，收盘复核重拉的日 K low 仍可坐实盘中击穿）。
- **表因根因**：模板只设开盘前单个日历槽，未覆盖「进程当日中断后如何再拉起」；launchd 的「睡眠唤醒合并补发」与「重启不补发」两类语义被当成同一类（I-008 修的是拉不起/不自愈，未覆盖当日中断后再拉起）。
- **处理方式**：模板保留 09:15 主槽，叠加周一至周五交易时段补拉槽（09:45–11:45、13:15–15:45 各每 30min，相邻槽交易盲窗 ≤30min，覆盖 A 股与港股交易时段，两市共同休市窗零槽）与 16:15 盘后兜底槽（`close_done` 未置则重拉补跑 `--close`，已置则立即 exit 0）；RunAtLoad=false 与 AfterInitialDemand=true 维持不变（不回退 I-008 防投机拉起初衷，launchd.plist(5) 对 RunAtLoad 亦有告诫）；watch.py 运行时零改动（任意时刻拉起自洽，watch.lock 防双开）；`watch.py --selftest` 增 launchd 模板回归钉 8 项（22→30 checks，plistlib 解析兼钉模板标准 XML 合法——旧模板注释含非法连续连字符，plutil 容忍但 plistlib 拒解析，已一并修复）；07「宿主形态」补拉槽语义与四坑位、batch/monitor/README 迁移提示同步。
- **后续防范**：改 launchd 模板须同步 07「宿主形态」语义与 watch.py selftest 模板钉（槽位变更必须过钉）；宿主（launchd）语义以 man page 与探针实测为准，不凭印象（I-008 同律）。
- **同类问题影响**：P2 会话接管（exit 2）落地时须重估补拉槽与「launchd 拉起 `--once` 补轮」的协调（接管期间 `--loop` 被补拉槽重拉会破坏交还会话语义）；任何「单时点日历槽 + 长驻进程」形态的宿主部署同受「重启不补发」约束。
- **注意事项**：① 当日彻底停盯盘不能只 kill 进程（会被下一补拉槽重新拉起——交易盲窗 ≤30min，午休跨槽至 13:15），须 `launchctl bootout` 卸载；② 已装单槽旧模板升级须 bootout 后按新模板重装，盘中执行会杀掉在跑进程，建议收盘后操作；③ 槽位按系统本地时区触发（沿用 09:15 主槽的 Asia/Shanghai 假设）；④ 进程运行期间槽位被 launchd 直接丢弃（不并发、退出后不排队——2026-11-03 探针实测），正常运行日补拉槽零开销。

<a id="I-010"></a>

## I-010：走势参考日表按卡片交易日单文件读取，盘后源末根时差致同批次漏股

- **问题描述**：0.0.18 首次真实收盘批量（2026-11-04 16:30，21 只在册股全部出卡）后，全集日表只渲染出 9 只；另 12 只的卡落在 `outlook/2026-11-03.jsonl`。
- **表因根因**：卡片 `date` 取末根日 K 交易日（与 signal.date 同口径，设计正确），全局时序按该日期分文件；但盘后各数据源更新有时差——A 股 em/qq 链 16:30 时末根仍是前一交易日，港股与部分 A 股源已出当日 K——同一批次被拆进两个日文件。渲染与幂等判断按「最新一个日文件」单文件读取，漏掉另一文件里的股；幂等若按卡片交易日判断，还会让当日已跑但末根滞后的股每次重跑都重新取数。
- **处理方式**：`outlook.latest_cards`（跨最近 10 个日文件、每股取最新一张）作为日表与幂等的统一读面；幂等改按卡片 `persisted_at` 的批次运行日（墙钟）判断；日表文件名=批次运行日，新增「交易日」列如实披露时差，在册却无卡的股以「缺卡」行列出；元组键 (market, code) 防 cn:002513 与 hk:02513 撞键。outlook selftest 新增跨日合并钉；同时修源侧 float32 噪声（yf 港股价 8.2600002…）——卡片价格取 3 位。
- **后续防范**：凡「按交易日分文件 + 跨股批量」的派生视图，读面一律按实体取最新、不按单日文件；幂等键用批次运行日，不用数据日。
- **同类问题影响**：monitor day-summary 的「末根日 K 未出或非当日，次日补判」是同一时差在收盘复核侧的表现（07 已按挂起次日补判处理）；后续版本市场级块（两融 T+1 披露）的 stale 判据同样不能按墙钟日硬比。
- **处理注意事项**：16:30 前后跑批量时 A 股卡大概率仍是前一交易日数据——09 规约的「≥17:10」时点纪律即为此设；早跑不是错误，日表交易日列会如实暴露。


<a id="I-011"></a>

## I-011：margin 取数链两缺陷——金十回退零配对行崩链、主源行数不足不触发回退致 source=None 渗透

- **问题描述**：①金十回退「HTTP 成功但零配对行/行数不足」（列名漂移使 `_fnum` 全归 None、或沪深两表日期零交集的常见形态）落到 `vals[-1]` 抛 IndexError，异常穿出 `fetch()` 使 evidence.json 不产出、单次诊股整跑失败（五块中唯一未守卫的空序列崩点）；②主源返回 1–20 有效行时 `raise ValueError("主源行数不足")` 被自身 except 吞掉，回退条件 `if not series`（series 非空）永不成立——以 `available·source=None` 返回，pack 头渲染成「两融（available，None）」、note 三目错标成金十口径、且给共享簇 em_datacenter 记一笔假失败，该残块还被 `_MKT_CACHE` 固化。
- **表因根因**：回退触发条件写成「序列为空」而非「主源未产出可用序列」——「行数不足」与「取数异常」两种主源不可用形态只处理了后者；回退块成功记账后未对「成功但形状不可用」设防。
- **处理方式**：回退条件改 `if src is None`（主源异常与行数不足都走金十；主源残行是三所口径、不得与金十两所行混序，回退前清空）；行数不足不再 raise、不记源败（HTTP 实际成功，形状问题非源故障）；金十回退补 ≥21 行守卫（与主源同口径），不足返回 fetch_failed 如实披露行数。diagnose selftest 增钉：主源 10 行 + jin10 熔断预置 → fetch_failed（非 available·source=None）、em_datacenter 零假败；钉内置 akshare stub 防真装环境入网。
- **后续防范**：回退链的触发条件一律锚「主源是否产出可用结果（src/哨兵）」，不锚「序列是否为空」——「部分成功」是最易漏的第三态；回退成功记账与形状校验必须分离（先验形状、后记账或按形状分支）。
- **同类问题影响**：任何「主源行数门槛 + 回退」结构的取数块同受此形态影响（margin_accounts 的 `<6` raise 走的是整体 fetch_failed 通道，无此问题）；EXT 块的 source 字段会直接进 pack 头渲染，None 值必须在取数层堵死。
- **处理注意事项**：金十回退现在对「成功但 <21 行」也返回 fetch_failed（此前短序列曾以 available+缺键渗出，配合 I-012 渲染端兜底双保险）；`_MKT_CACHE` 对 fetch_failed 不缓存，批量下每股重试、最坏多付 HTTP 属既有取舍。

<a id="I-012"></a>

## I-012：C1 渲染收口缺第二道——残块缺键经渲染端裸 %s 打出 None%/0.00% 字面量；A 股指数无 ≥60 行守卫

- **问题描述**：C1 修复（erp partial 无数值键不入卡）只堵了投影侧——投影端按值滤 None 键后，渲染端 `mg.get("chg_5d_pct")` 等裸 `%s` 回填仍会把「被滤掉的键」渲染成 `Δ5d None%`（pack 市场级行、日表市场级节）；diagnose 侧 `_nz` 兜底则渲染成「距 MA60 0.00%」——无 MA60 被显示成贴线，误导。可达形态：margin 金十回退短序列（修复前）、margin_accounts 6–20 行（traders_chg_20d_pct=None）、A 股指数 `_cn` 路径短于 60 行（W2 守卫只给了 HSI 两处）。
- **表因根因**：投影端滤键与渲染端取键两道工序对「键缺席」的处理不对齐——滤键防的是入卡，没防渲染；守卫只按「当时实测到的源形态」打点（HSI yf 短序列），没有对齐到同构路径（A 股 tx/新浪）。
- **处理方式**：渲染端统一 `_d`（None→「—」）——outlook.py `render_pack_block` 市场级行、batch/outlook_daily.py 日表市场级节全部数值位；A 股 `_cn` 与 ALLA 补 ≥60 行守卫（短序列入 fails 披露、不出快照，与 HSI 对称）；outlook selftest C1 扩展钉：margin 缺变动/分位键 fixture → 市场级行含「—」且全 pack 禁 None 字面量。
- **后续防范**：「投影滤键」与「渲染取键」必须成对设计——凡投影端可能滤键的字段，渲染端一律走缺数兜底（`_d`/`_nd` 家族），selftest 的 None 字面量禁令要覆盖到每一种残块 fixture，不只 erp。
- **同类问题影响**：所有经 `_mkt_keys` 投影的块（五块全量）在任何「部分键缺失」形态下同受影响；后续新增市场级块时渲染端兜底与守卫为必做项。
- **处理注意事项**：「—」是信息面缺数披露口径（与 `_nd` 一致），不是错误；日表消费者（人）读「—」应理解为该键本批不可用。

<a id="I-013"></a>

## I-013：index/erp 链守卫与归因三处——HSI 短序列零披露、新浪回退失败归因用错异常变量、csindex 空响应打回满仓台账

- **问题描述**：①HSI yf/新浪回退「成功但 <60 行」时既不出快照也不入 `fails`——块可标 available/partial 却对 HSI 缺席零披露，消费方无从区分「源挂」与「序列短」；②HSI 新浪回退失败归因 `fails.append("HSI:%s" % type(e).__name__)` 用外层 yf 的 `e` 而非内层 `e2`，新浪失败被错标成 yf 异常类型；③ERP 日频台账 `_daily_accum` 在 csindex 返回 0 有效行时早退 `return None`——台账已积累满 250 日后，一次临时空响应/字段漂移就把 `daily_ready` 打回 False（「进行中」），与「满 250 日接管」语义相反。
- **表因根因**：①短序列被当作「静默跳过」而非「部分失败」——fails 只收异常不收形状；②双层 try 的异常变量名在重构中失配；③「无增量」与「台账清零」两种语义被同一个 `return None` 压缩——早退路径没读台账。
- **处理方式**：①HSI 两条链短序列均 `fails.append("HSI:short_series(%d)")`（A 股 `_cn`/ALLA 同款，见 I-012）；②归因改 `type(e2).__name__`；③`_daily_accum` 把台账读取提到空响应判断之前，`new_rows` 为空时返回 `len(ledger)`（无增量≠台账清零，不重写文件）。
- **后续防范**：「部分成功」的每一形态（短序列、空增量、部分指数缺席）都要进 fails/note 披露面，静默跳过=信息丢失；双层回退 try 块的异常变量命名强制外层 e/内层 e2 并在归因处复查；早退 return 的值域要覆盖「现状不变」语义（None 会向下游传播成布尔翻转）。
- **同类问题影响**：`_daily_accum` 的空响应路径同时服务 ERP 台账的 daily_ready 门——任何「增量源临时空回」都会走此路径，修复后一律保持台账现状；HS300 新浪回退此前不入 `_MKT_CACHE`（tx 失效时批量每股重打新浪，本次一并入缓存 `idx_<sym>_sina`）。
- **处理注意事项**：csindex 空响应现在不重写台账文件（只读返回），`os.replace` 原子写只在有增量时发生；`_index_snapshot` 另补空序列守卫（返回 None），防 IndexError 被 caller 误记 qq 簇假败。

<a id="I-014"></a>

## I-014：--calibrate 无墙钟门/末根未完成过滤——盘中手跑把未定型末根 K 永久钉成错误样本

- **问题描述**：`outlook_daily --calibrate` 直接 `fetch_daily_bars` 后判触及，无 `--daily` 侧已有的 (17,10) 墙钟门；`touch_judgment` 的 `len(after) >= h` 判窗不区分末根是否定型——盘中运行时末根是当日未完成 K（fetch 链不滤），若卡恰在 h−1 个完整交易日前，窗口以半根 K 收口、`touched=False` 入台账；台账按键幂等去重**永不重判**（merge 见键即跳），错误样本永久固化。
- **表因根因**：同一「未定型 K 钉死」风险在 --daily 侧由 I-010/M4/L8 一并堵死（墙钟门），calibrate 新增时未复用同款门；且「满窗」语义只数根数、不看末根完整性——墙钟门是时点防线，末根过滤才是形态防线，缺一即漏盘中路径。
- **处理方式**：`calibrate()` 复用 (17,10) 墙钟门（--force 可越过，越过提示自担）+ 根本防线 `session_phase(market, bars[-1]["date"])["last_bar_partial"]` 末根未完成过滤（判窗只用已定型 K——--force 越过墙钟门时过滤仍生效，双防线独立）。
- **后续防范**：任何「判触及/判收盘/终判」类消费日 K 的新入口，必须同时过墙钟门与末根完整性两道防线（07 --close 与 09 --daily/--calibrate 三入口同律）；幂等台账「永不重判」的设计把上游一次性错误放大成永久错误——入口防御优先级高于台账修复。
- **同类问题影响**：postmortem 到期收盘门（I-011，PR #20 轨）是同一「末根未完成」家族在信号后验侧的表现；后续新增台账类后验入口同受此约束。
- **处理注意事项**：墙钟门按 `_now()` 墙钟（UTC+8）判 (17,10)，与 --daily 同参；末根过滤用 fetch 层既有 `session_phase` 纯函数（无节假日日历坑位同 01）。

<a id="I-015"></a>

## I-015：校准台账与样本面三处——qfq 重基准偏置无防御、类型损坏行毒丸崩在写回后、「新增样本」计数虚报

- **问题描述**：①校准以当前 qfq 日 K 序列判历史卡的绝对价锚——除权除息后整条历史序列重定价，旧锚 vs 新序列的触及判定系统性偏（上方锚触及被压低/下方被抬高），无检测无披露（09「再评审」行自己把 qfq 重基准列为否决理由，校准却引入同类风险）；②`merge_calibration` 坏行自愈只覆盖非 JSON 行/非 dict 行——`{"h":"x"}` 类合法 JSON 类型损坏行让 sort 的 `int("x")` 抛 ValueError、缺 p 键行让 buckets 抛 KeyError，且崩点在台账写回之后：毒丸行一旦入库，此后每次 --calibrate 必崩、永不自愈；③运行尾打「新增样本 %d」按 `len(samples)`（本次满窗计算数）虚报——幂等重跑零增也打印满数。
- **表因根因**：①锚的「价」语义在卡时点与判定时点之间静默漂移（qfq 序列是移动基准）；②「坏行」定义按 JSON 语法层而非 schema 层，语法合法类型错误落进了消费面；③「计算出的样本」与「新入账的样本」两个概念共用了一个计数。
- **处理方式**：①`calibration_samples` 加 qfq 重基准防御：卡 `price` 与序列在卡日收盘的偏离 `>0.5%` 判重基准、整卡丢样本（偏置样本比缺样本更坏；≤0.5% 属正常价差噪声不丢），calibration.md 口径行披露该偏置与「样本跨日重叠相关、n 非独立样本数」；②新增 `_valid_cal_row` schema 校验（date/market/code/track/anchor 字符串、h 整数、p 数值、touched 布尔），载入即滤、重写时自愈清除，sort/buckets 只见合格行；③新增计数改按本运行 `judged_at` 戳计真实增量（幂等键命中者不重打戳）。outlook selftest 钉：×0.8 重定价整卡丢 / ×1.004 噪声不丢 / 类型损坏行载入即滤。
- **后续防范**：台账「自愈」必须按消费面 schema 定义坏行（语法层合法≠类型安全），且校验要在写回前——崩在写回后的毒丸无自愈路径；绝对价锚 × 复权序列的任何组合都要先过重基准检测（检测基准：两个时点同日收盘的比值）。
- **同类问题影响**：erp_pe_daily.jsonl 与 outlook 卡片 jsonl 的坏行口径仍是语法层（值域天然安全无 int()/[] 消费面，暂不扩）；后续任何带数值消费面的 jsonl 台账，schema 校验为必做项。
- **处理注意事项**：重基准阈值 0.5% 为防御性首版（正常价差噪声 <0.5%、除权除息通常 ≥数个百分点），调整属口径变更须评审；幂等键不含锚值——同键 --force 重跑锚值更新保留首判样本（merge docstring 已显式化该取舍）。

<a id="I-016"></a>

## I-016：后验评估消费盘中未完成日 K，到期 horizon 被盘中价误判命中；05 基准口径前后矛盾

- **问题描述**：2026-11-04 盘中（10:58）跑 postmortem，一只港股的 sell 信号 T+3 恰在当日到期，评估用了当日未完成 K 线的盘中价 433.2，记为「−10.4% 命中」；当日真实收盘 484.2，相对基准 +0.12%，应为中性。同一信号的 T+1 旧 entry 无 `base` 键，沿用登记价 495.4 得「−3.0% 命中」，按现行复权基准应为 −0.66% 中性。两条伪命中都在强化看空来源的战绩。
- **表因根因**：`evaluate_signals` 只判 `j >= len(closes)`（未到期），不判末根 K 线是否已收盘（[postmortem.py](../../scripts/postmortem.py) 到期分支）；已落盘结果不重评，错误永久留在台账。规约层 [05](../../references/05-postmortem.md)「复权基准」写基准=同复权 `closes[i]`，「价格口径」又写「后验基准沿用登记价原样」，两处矛盾，代码按前者执行。
- **处理方式**：已修复（收严型，只减少评估不放宽判据）：[postmortem.py](../../scripts/postmortem.py) `evaluate_signals` 增末位可注入参数 `now=None`（既有调用方不受影响），每信号经 `fetch.session_phase(market, dates[-1], now)` 取 `last_bar_partial`，到期分支增守卫——horizon 落末根且末根=当日盘中未完成 K 线时不评估、保持 pending，收盘后下一次运行补评（周末/节假日自然收盘态放行；未知市场判 None 维持原行为）；[05](../../references/05-postmortem.md)「价格口径」节删与「复权基准」矛盾的「沿用登记价原样」句、统一为同复权信号日收盘基准（存量旧 entry 无 `base` 键时回落登记价），并新增「到期收盘门（I-016）」规约句；selftest 增 g1–g4 四钉（盘中不评 / 收盘后补评 / 周末补评 / monkeypatch 旁路 session_phase 必误评的破坏性实验）。存量伪命中条目是否回改仍需人工评审（05 维持已评估不回改）。
- **后续防范**：postmortem selftest 增「末根为盘中 K 线时到期 horizon 不评估」的钉；破坏性实验（去掉收盘判定）必红。
- **同类问题影响**：addon 轨与 position 轨共用同一到期分支；任何在盘中触发的 postmortem（盯盘收盘复核前、诊股前置全量 postmortem）都会命中。
- **注意事项**：台账样本 <30 时绩效因子仍为中性 1.0，误记暂未改变权重；样本跨过 30 后误记会直接进入绩效因子。

<a id="I-017"></a>

## I-017：港股南向持股变动（T+2 交收）被标为当日净买入，money_flow 把 D−2 成交读成当日背离

- **问题描述**：东方财富 `RPT_MUTUAL_STOCK_HOLDRANKS` 的 D 日持股变动对应的是 D−2 日的南向成交（T+2 交收）。用港交所每日南向成交统计（`data_tab_daily_YYYYMMDDe.js`）按当日 VWAP 换算股数与持股变动逐日比对，6 组样本全部对上 D−2。系统把该字段当作当日净买入，导致一次复盘中「下跌日南向逆势净买、背离」的结论实为两天前上涨日的成交；按成交日口径，那轮下跌最后一天南向是净卖出。
- **表因根因**：[fetch.py](../../scripts/fetch.py) `fetch_moneyflow_hk` 把 `HOLD_SHARES_CHANGE` / `ADD_MARKET_CAP` 落为 `net_buy_shares_1d` / `net_buy_amount_1d_hkd`，并注「T-1 披露口径」——混淆了披露时点与成交日。
- **处理方式**：已修复（口径标注型，字段名 `net_buy_shares_1d`/`net_buy_amount_1d_hkd` 沿用不改名——下游渲染在用）：[fetch.py](../../scripts/fetch.py) note 改「南向两层口径：披露 T-1；持股变动对应成交 D-2（T+2 交收，非当日净买入）」、summary 增 `chg_trade_lag_note` 键、docstring 增口径二段；[diagnose.py](../../scripts/diagnose.py) 渲染改「持股日净增持 …（对应 D-2 成交，净额 … 亿 HKD）」、pack 港股口径行同步两层；[01](../../references/01-evidence.md) moneyflow 行与「南向两层口径」bullet 同步；selftest 钉新 note 与 D-2 渲染行、旧「当日净增持」措辞缺席必红。全仓 grep 该字段仅 diagnose 渲染一处消费、策略与裁决器无「当日净买入」判据，误读路径已在 fetch note / summary 键 / 渲染措辞 / 01 规约四层关闭。
- **后续防范**：fetch selftest 钉字段语义（持股变动日 ≠ 成交日）；改扩展块字段命名须同步 01 证据规约。
- **同类问题影响**：中线 `hold_pct_chg_20d/60d` 是持股比差值，不受日期错位影响结论方向，但窗口边界同样滞后 2 个交易日；A 股北向若接同类端点需同查。
- **注意事项**：港交所文件只含当日南向前十大成交股，未进前十的标的拿不到成交日数据，只能用持股变动倒推。

<a id="I-018"></a>

## I-018：box_60d 含当日 K 线，新低日「精确触箱底」是同义反复，被当作支撑验证

- **问题描述**：一只港股在 11-04 盘中跌到 421 后反弹，报告与策略意见写「421 精确触 60 日箱底、箱底支撑首次验证」。实际此前 60 日最低价是 434（前一日），421 是跌破前低 3.0% 后的反弹。
- **表因根因**：[fetch.py](../../scripts/fetch.py) `derive_technical` 的箱体窗口 `w = bars[-60:]` 包含当日（含未完成）K 线，任何新低日的 `box.lo` 都等于当日最低价，`pos_pct` 贴 0。
- **处理方式**：已修复（收严型）：[fetch.py](../../scripts/fetch.py) `derive_technical` 箱体窗口改前窗口 `bars[:-1][-60:]`（前窗不足 20 根不出——出箱门槛变为总根数 ≥21），hi/lo/width_pct 全按前窗口，pos_pct 按现价对前窗口 hi/lo 计算且不截断（跌破 <0、突破 >100，越界即信息）；新增 docstring；[diagnose.py](../../scripts/diagnose.py) 渲染括号说明同步；[01](../../references/01-evidence.md) 增「box_60d 前窗口口径」规约句与 technical 表行注记；selftest 改四键精确钉值（独立手算）+ 突破钉（末根收 15.5 → pos>100，含当日口径必红）。策略 YAML（box_oscillation/swing_band/volume_breakout）判据文字未注窗口口径，语义自洽、留后续防范项。
- **后续防范**：fetch selftest 钉「新低日 box.lo 取前窗口」；策略 YAML 中引用箱底支撑的判据须注明窗口口径。
- **同类问题影响**：`hi52/lo52`、`pct_from_52w_low` 同样含当日，创新高/新低日的距离为 0；volume_breakout 的「创 20 日新高」用 `prev19` 前窗口，口径不一致。
- **注意事项**：改窗口会改变历史报告中 `width_pct` / `pos_pct` 的可比性，不回改存量报告。

<a id="I-019"></a>

## I-019：中线波段带 g 为收益率却按价差加减，带宽塌缩到不足 1 港元，selftest 同公式测不出

- **问题描述**：中线裁决「波段带」三个版本输出 433.4/433.97、481.42/482.58、489.22/490.38，带宽约 0.6 港元，对一只日 σ 约 6% 的股票毫无操作意义。
- **表因根因**：[diagnose.py](../../scripts/diagnose.py) `_mid_key_levels` 中 `g = max(2σ_d√21, 3×往返成本)` 是收益率（此例约 0.57），却以 `price − g` / `price + g` 当价差加减；[08](../../references/08-midterm.md) 明写 g 是收益率口径。对应 selftest 用同一公式断言，测不出。
- **处理方式**：已修复：[diagnose.py](../../scripts/diagnose.py) `_mid_key_levels` 改 `band_lo=max(lo60, price×(1−g))`、`band_hi=min(hi60, price×(1+g))`——g 为收益率按乘法取价差后钳制 60 日高低点（σ_d 大时整带被钳属预期，成本下限仅极低波动票生效），docstring 同步；selftest 弃「同公式算 want」，改 A（高波动 σ 支路整带被 60 日高低点钳制）/B（成本下限 0.0045 双侧不钳）两场景独立手算字面量钉值 + 两条价差口径反事实必红；[08](../../references/08-midterm.md)/[04](../../references/04-report.md) 无 band 价差语义句（08 已按收益率表述 g），无需改。
- **后续防范**：涉及收益率与价格混算的派生价位，selftest 期望值必须独立计算，不得复用被测公式。
- **同类问题影响**：signals.json 中 position 轨信号的 `key_levels.band_lo/band_hi` 全部受影响（仅展示，不进后验判定带）；盯盘若消费该价位会产生贴价误告警。
- **注意事项**：修复后带宽会显著变宽（σ_d 6% 时 g 约 0.55），可能整体被 60 日高低点钳制，属预期。

<a id="I-020"></a>

## I-020：逆势窄门读错裁决轨——quality_value 买点从 default 轨 verdict 取，生产永不触发

- **问题描述**：`addon.value_trigger` 从 **default（短线）轨 verdict** 的 `valid_opinions` 找 `strategy:quality_value` 买点，但 `quality_value` 是 `profile: position` 策略——diagnose prepare 契约下其意见只进 `opinions.position.json` → **pverdict**。default 轨 verdict 永不含 quality_value → 门 2 逆势窄门 blocker「quality_value 无买点意见」恒在，逆势轨成不可达死代码；selftest fixture 把 quality_value 塞进 default verdict（契约下不可能的形态）恰好掩盖缺陷，diagnose 集成钉 T11e 也只测顺势与冻结两形态。
- **表因根因**：双轨架构（0.0.16）下「策略→轨」的路由先于本轨（0.0.19 分支）开发，value_trigger 按策略名直觉取了 default verdict；fixture 手搓 valid_opinions 未按 prepare 契约校验轨归属。
- **处理方式**：`value_trigger(evidence, pverdict, lens)` 改读中线轨裁决（pverdict 缺席时显式 blocker「无中线裁决」，门不开、保守方向）；selftest fixture 改合法形态（quality_value 进 pverdict）+ 两条回归钉（default 轨读到 quality_value 不开门；pverdict 缺席 blocker）；diagnose T11e 增逆势集成钉（verdict.position.json + lens 有支撑 + 现价<ma20 → 「**可加仓**（逆势窄门）」+ add_ref=触发时价登记）。
- **后续防范**：任何按策略名取意见的门，fixture 与实现都要显式声明轨归属（default/position）；手搓 verdict fixture 里的 `strategy:*` 意见须与 strategies/*.yaml 的 profile 字段一致——「契约下不可能的 fixture」是最隐蔽的掩蔽源。双轨消费新增点上线前，用真实 prepare 产物（opinions.position.json）做一次集成钉。
- **同类问题影响**：门 1 的 pverdict 消费（中线卖族冻结）实现正确不受影响；逆势窄门此前从未在生产触发过，无存量错误建议（失败方向保守）。
- **处理注意事项**：逆势窄门现在要求「有中线裁决」——单轨日（无 verdict.position.json）逆势轨天然关闭、报告落「无中线裁决（pverdict 缺席）」blocker，属设计内保守形态。
