# 04 · 决策报告（模板与渲染口径）

渲染实现：[scripts/diagnose.py](../scripts/diagnose.py) `render_report`
（结构以实现为准，本文件讲规则）；落盘与索引：[scripts/archive.py](../scripts/archive.py)，
布局见下文「落盘与跟踪」（本文件是布局规则唯一定义处）。

## 结构（结论先行）

1. **结论**：最终信号 + 置信 + 共识等级 + 可执行与否 + 一句理由摘要 +
   完整裁决链（聚合初判 → RiskGuard 各步 → 置信帽）+ 分歧概览 + 意见分布。
   理由摘要支撑终裁信号（RiskGuard 与置信帽之后的 final）。条件：结论句挂
   理由时；做法：终裁≠初判且由 RiskGuard 改判 → 优先挂 risk.json.rationale 摘要
   并注明「初判 X 经 RiskGuard 改判为 Y」；否则取与终裁同信号（其次同方向族）的
   最高置信意见 rationale，置信帽压档（strong_*→buy/sell）时径取同方向族；都
   没有则不挂（不硬凑）；坑位：按聚合初判选理由会在 RiskGuard 改判后挂出与终裁
   反向的意见（sell 结论配 hold 理由）。
2. **证据状态**：全部块状态/来源表（核心六块标权重、扩展九块标 0 分）——
   缺失可见落在产品面；forecast/unlock 有数据时附「近期事件」（披露日历/
   解禁批次）。
3. **关键价位**：现价 / 20 日高低 / MA20 / 参考买点 / 止损 / 目标。盘中取数时
   现价注明「（盘中价）」，取数时段口径见 [01 · 盘中口径](01-evidence.md#盘中口径未完成-k-线)。
4. **风险与利好**：逐条挂反对意见与支持意见的 rationale（有据可查）。条件：
   `report` 渲染（读 workdir 的 opinions.json 与 risk.json）；做法：风险栏=卖出族
   意见 + 风险角色 risk.json.rationale（标注 veto/downgrade 触发态），利好栏=买入族
   意见，逐条带 source 与 signal/置信，空栏如实写「（无登记）」；rationale 的 SSOT
   是 opinions.json（verdict.valid_opinions 只存四键），按 source 接回且只挂过验票
   门的意见（`partition` 同一判据）；坑位：按 source 集合朴素过滤会把同 source
   表外写法意见的 rationale 混挂进来。
5. **操作建议**：空仓者与持仓者分开、按最终信号给纪律性动作（不追高/止损位）。
6. **检查清单**：核心证据齐备 / 无高严重度分歧 / 置信 ≥0.5 / 未偏离 MA20 过远
   ——未通过项如实打叉，检查没过照样出报告，但结论停在保守档。
7. **附**：各意见（含绩效因子加权，附 rationale 原文）与诊断记录。
8. **免责段**（无条件全局规则：金融用途安全边界）——固定文案见 DISCLAIMER，
   任何报告不得省略。

## 规约

- 每个判断可溯源：结论句引用意见 rationale，意见引用证据块数值。RiskGuard
  改判时结论句引用 risk.json.rationale（选取规则见上文结构第 1 条）。
- 报告不复述哨兵原文；新闻只以事实转述进风险/利好。rationale 是 LLM 产出、
  可入报告，入报告前剥哨兵标记、尖括号/方括号/反引号转全角并折成单行——
  方括号全角化掐断 markdown 链接/图片注入；附录诊断行的 source/原始输出同为
  LLM 产出，走同一通道处置（报告任何位置不复述哨兵原文）。证据块 note 同为
  多行风险源：入报告表前折单行——多行会拆坏表格，也可能伪造单日文件的
  版本/节头。
- 可执行门槛：buy 族登记为可执行建议须置信 ≥0.5（CONFIDENCE_GATE），
   否则降为 watch 并注明。

## 落盘与跟踪

```text
~/.vibe-stock/reports/
├── index.md                 多股总览（派生视图）
├── 600519.cn/               A 股 6 位 / 港股 5 位（00700.hk）
│   ├── index.md             单股时间线（派生视图）
│   └── 2026-10-30.md        一股一日一文件，内含当日 v1…vN
├── _snapshot/<code>/        快照模式（market="?"），不建索引
└── _legacy/                 migrate-reports 归档的旧平铺文件（不删）
```

- **单日多版本**（适用：每次 `diagnose.py report`）：做法——追加进
  `<code>.<market>/<date>.md`（date = 生成日墙钟，与版本时刻、信号 `created_at`
  同取一次 now），版本头 `## vN · HH:MM:SS`、节头 `### `；标题与免责段全文各一次；
  某节与上一个有内容版本逐字相同写 `同 vK。`（K = 该内容连续未变区间的首版，
  中间变过即重新计），节缺失即本版无此节；迁移还原的丢失版正文为 `（报告已被覆盖，无法恢复）`。
  坑位：定位某条信号的报告只认 `report_path` + `report_version`，不要从
  `report_id`（日级分组键）拼路径；文件名日期是生成日、后验基准是 `signal.date`
  （交易日），周末/盘前运行二者可不同。
- **身份闸门**（适用：report 写盘前）：做法——证据身份（`stock_code`：港股统一
  5 位）须与 `--stock` 归一后一致，代码须合规范形态，signals.json 须可解析，任一
  不符 exit 2 且零写入。坑位：`.vs/` 残留上一只票的证据是最常见触发。
- **时间线索引**（适用：report / postmortem 之后）：做法——`index.md` 由
  signals.json 整体重建（只覆盖 cn/hk），总览表列股票、股票名称、最新日期、
  最新信号→动作、置信、诊断次数与 pending，单股表新→旧列版本、信号→动作、
  置信、登记价、状态与 T+1/3/5/10 涨跌及判定；内容未变不重写。坑位：索引是
  派生视图，手改会在下次重建时丢失；信号与后验的事实源始终是 signals.json；
  股票名称取自信号的 `stock_name`（quote 块行情面数据，A 股 qt 全量快照 / 港股
  qt 紧凑快照，取数失败如实缺省 `—`），组内取最新非空值。
- **存量迁移**（适用：0.2.1 及以前的平铺 `<code>-<date>.md`；须在升级后首次
  report 之前执行，否则当日新报告会让旧平铺文件被判 conflict 需人工处理）：做法——
  `diagnose.py migrate-reports` 默认 dry-run；`--apply` 依次写单日文件 → CAS 校验后
  备份 `signals.json.bak-<ts>` 并改写 `report_path`/`report_version`（丢失版加
  `report_lost: true`）→ 原文件移入 `_legacy/` → 重建索引；按 `report_id` 认领信号，
  与文件 mtime 同刻（≤2s）的最后一条为内容版。坑位：迁移期间勿并发跑 report /
  postmortem（signals.json 无锁，CAS 只能发现不能合并）；目标已存在且内容不同、
  或平铺文件无可解析 `## ` 节头（非本工具产物/截断）均记 conflict 原样跳过，
  需人工处理；mtime 漂移（备份恢复/编辑器重存）时回退按最后
  运行归属内容版并列 anomaly，缺可用 created_at 的信号跳过认领不改写；回退按
  .bak 逐 signal_id 恢复，勿整文件覆盖。
