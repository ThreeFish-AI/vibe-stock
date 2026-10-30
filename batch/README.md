# batch/ · 批量诊股参考实现

口径以 [references/06-batch-scan.md](../references/06-batch-scan.md) 为准
（SSOT），本目录是其参考实现脚本。变量：`$SK` = skill 根目录（本仓 clone 或
`~/.claude/skills/vibe-stock`）；`$SCAN` = 批量运行根目录，形如
`~/.vibe-stock/reports/_scans/<date>-<pool>`（如 `…/2026-11-02-hs300`）。

## 文件清单

| 脚本 | Stage | 职责 |
| :--- | :--- | :--- |
| stage_a.py | A | 机械粗筛（bulk 四源+回退链、复合分、硬过滤、行业帽选 N） |
| scan_prepare.py | B | 取数串行驱动（波次+健康门+retry）；`--register` 登记 shortlist |
| wf_opinions.mjs | B | 意见层并行编排（宿主 Workflow 脚本，每股一 agent 出意见+risk+本地裁决） |
| midtier.py | B/C | 中 tier 汇总 SSOT（midtier.jsonl）+ 门限筛 G1–G5 + R_sel 排序 |
| digest.py | C | 深评输入摘要（stdout 按需派生，不落盘；核验/lens agent 统一读面） |
| wf_deepdive.mjs | C | 对抗核验 + 三 lens 独立评审 + 确定性合分（宿主 Workflow 脚本） |
| portfolio.py | D | 手数贴合 + 三段建仓 + 三价纪律 + 一致性校验 |
| render_index.py | — | 主报告 index.md 渲染（数字全部从 SSOT 派生，勿手改产物） |

`wf_*.mjs` 是宿主工作流脚本形态（phase/agent/parallel/pipeline/log/args 全局，
文件头注释写明参数化路径——`scan_root`/`skill_dir`（及 `codes`/`shortlist`）
必填且必须为**绝对路径**：宿主脚本面无 Node/process API，`~` 展开由宿主在
调用前完成）；不支持该形态的宿主按 [06](../references/06-batch-scan.md) 的
「宿主子代理能力」门槛降级为逐股串行。

## 端到端命令序

```bash
# Stage A 粗筛（300→30；--pool hs300 --budget/--top-n/--max-price 可调）
uv run --no-project --with 'akshare==1.20.*' --with efinance \
  $SK/batch/stage_a.py --pool hs300 --scan-root $SCAN --skill-scripts $SK/scripts

# Stage B 取数（必须串行：fetch_state.json 整体写竞态）→ 意见层（宿主
# Workflow 跑 wf_opinions.mjs，或逐股按 SKILL.md 工作流手工产意见+裁决）
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
  $SK/batch/scan_prepare.py --scan-root $SCAN --skill-dir $SK

# Stage C 门限筛+排序（聚合分按 06 复算，与 adjudicate.aggregate() 同式）→
# 深评（宿主 Workflow 跑 wf_deepdive.mjs，产物落 stageC/ranking.json）→ 登记
uv run --no-project $SK/batch/midtier.py --scan-root $SCAN --skill-scripts $SK/scripts
uv run --no-project $SK/batch/scan_prepare.py --scan-root $SCAN --skill-dir $SK --register

# Stage D 组合 + 主报告渲染
uv run --no-project $SK/batch/portfolio.py --scan-root $SCAN --budget 100000
uv run --no-project $SK/batch/render_index.py --scan-root $SCAN --pool hs300
```

复盘：`uv run --no-project --with 'akshare==1.20.*' --with efinance --with
yfinance $SK/scripts/postmortem.py`（skill 自带，见
[references/05](../references/05-postmortem.md)）。

## 口径关系

- 批量层只做编排，单股裁决链（opinions/risk → adjudicate → verdict）零改动；
  版本要求 ≥0.0.6（聚合分语义修复后直接消费管线口径）。
- 门限档、降级惩罚、R_sel/合分权重、仓位带与三价纪律的数值与取舍理由见
  [06](../references/06-batch-scan.md) 各节；脚本参数
  （--g1-steps/--min-pass/--w-min/--w-max/--industry-cap 等）是其可调面，
  改参数不改规约语义。
- 深评摘要 `digest.py` 与主报告 `render_index.py` 不写运行日志类 json；各
  产物文件的唯一事实源地位与「勿手改」纪律见
  [06「产物 SSOT 布局」](../references/06-batch-scan.md)。
- 本目录属参考实现，不设 `--selftest` 门禁：改动以 scripts/ 四件 selftest
  全绿（AGENTS.md 测试口径）+ `py_compile`/`node --check` 语法冒烟 + 06
  口径复核为准。
