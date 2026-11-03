<!-- markdownlint-disable MD033 MD051 -->
# Issue 处理档案

> 已处理 Issue 的摘要索引，便于同类问题跨上下文处理；同一 Issue 只在原条目增量更新。

| ID | 标题 | 状态 | 完成时间 | 详情 |
| :--- | :--- | :--- | :--- | :--- |
| I-001 | 同日重跑覆盖报告致信号→报告指针失真：改单日多版本文件 | ✅ 已完成 | 2026-10-30 | [详情](#I-001) |
| I-002 | 港股代码归一不一致致同一标的身份分裂：统一补 5 位 | ✅ 已完成 | 2026-10-30 | [详情](#I-002) |
| I-003 | signals.json 解析失败被静默当空、下次 report 覆盖历史：严格加载 + 原子写 | ✅ 已完成 | 2026-10-30 | [详情](#I-003) |
| I-004 | 05 规约「八元组去重」未实现，同日重跑重复登记信号与归因 | ⏸ 暂不处理 | — | [详情](#I-004) |
| I-005 | 状态文件健壮性缺口：signals 无锁、ledger 损坏被清空、market="?" 信号使 postmortem 崩溃 | ⏸ 暂不处理 | — | [详情](#I-005) |
| I-006 | 总览持仓合并契约与真实 portfolio.json v2 结构脱节：loader 归一 holdings 列表 | ✅ 已完成 | 2026-11-02 | [详情](#I-006) |
| I-007 | 盯盘 P1 selftest fixture 写入真实持仓（公开仓）：换合成标的 + 零重合负断言 | ✅ 已完成 | 2026-11-02 | [详情](#I-007) |
| I-008 | 盯盘 launchd 模板拉不起、异常不自愈、跨日 close_done 残留：绝对路径 + SIGABRT + 按日归零 | ✅ 已完成 | 2026-11-02 | [详情](#I-008) |
| I-009 | 盯盘 launchd 模板仅 09:15 单槽，重启/开机后当日不再拉起：交易时段补拉槽 + 16:15 盘后兜底 | ✅ 已完成 | 2026-11-03 | [详情](#I-009) |

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

- **问题描述**：[05-postmortem](../../references/05-postmortem.md) 声明信号按 (report_id, source_type, market, code, profile, action, horizon, regime) 去重，实现只追加；同日重跑会登记多条同向信号，buy/sell 族后验时同一意见源被重复归因，绩效因子失真。
- **表因根因**：`register_signal` 未实现去重；0.2.2 前 diagnose.py docstring 还写着「八元组去重」，已改为如实描述。
- **处理方式**：暂不处理。0.2.2 保留日级 `report_id` 作为后续去重或 superseded 语义的挂点，[05](../../references/05-postmortem.md) 已改口为「去重未实现」如实描述。
- **后续防范**：实现时须同步 05 规约与 selftest，且只许收严（不得让重复样本抬高绩效因子）。
- **注意事项**：当前现网同日多信号均为 watch（只观察不记分），尚未污染 ledger。

<a id="I-005"></a>

## I-005：状态文件健壮性缺口

- **问题描述**：① signals.json 读改写无文件锁，report 与 postmortem 并发可能丢更新；② postmortem `_load(LEDGER, {})` 吞解析异常，损坏时会用本次增量覆盖整本台账；③ 快照模式登记的 market="?" 信号进入 postmortem 后，`fetch_daily_bars` 取 `CHAINS["?"]` 抛 KeyError。
- **表因根因**：状态层没有统一的加载/写入/锁约定，各脚本各自读写 JSON。
- **处理方式**：暂不处理。迁移侧用 CAS 发现并发改动，report 侧已改严格加载。
- **后续防范**：统一到 [archive.py](../../scripts/archive.py) 的严格加载 + 原子写；postmortem 跳过非 cn/hk 信号。
- **注意事项**：迁移期间勿并发跑 report / postmortem。

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

