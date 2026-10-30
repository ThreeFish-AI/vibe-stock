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
