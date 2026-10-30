# PIPELINE · 五段流水线与命令速查

路径变量（唯一定义处）：`$T` = skill 根（SKILL.md 所在目录；Claude Code 下即
`${CLAUDE_SKILL_DIR}`）；`$W` = 本次诊股工作区（默认 `.vs/`）；状态目录
`~/.vibe-stock/`（signals.json / ledger.json / fetch_state.json /
reports/<code>.<market>/ 单日多版本与时间线索引——布局见 [04](04-report.md)，不入仓）。
本文件只覆盖单股五段流水线；多股批量（指数成分精选/筛 N/资金配置）走
[06-batch-scan](06-batch-scan.md) 子技能（`batch/` 参考实现，命令序见
[batch/README](../batch/README.md)）。

```text
① 取证据      fetch.py（多源回退+熔断冷却+八态+质量分；16 块=核心六块
              （计分）+扩展十块（资金流/公告/研报/预告/解禁/股东户数/大盘/
              行业/估值/汇率，零权重）；A 股全链实测 ~17s/17 次 HTTP）
② 拼上下文    diagnose.py prepare → context-pack.md（有界证据包+哨兵+置信帽+
              盘中警示行；--cost 时另附基本面锚节——取数时段口径见
              [01 · 盘中口径](01-evidence.md#盘中口径未完成-k-线)）
③ 能力自检    市场支持表与新鲜度体现在八态本身（not_supported/missing 即答案）
④ 多角色+策略  LLM 按 SKILL.md 读 context-pack 与 strategies/*.yaml 产意见
              （opinions.json + risk.json）→ adjudicate.py 验票/聚合/分歧
⑤ 裁决出报告   adjudicate.py RiskGuard → diagnose.py report → 报告+信号登记
```

## 命令速查

```bash
# ①+② 取证据并生成上下文包（联网）
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
  $T/scripts/fetch.py --stock 600519 --out .vs/evidence.json
uv run --no-project $T/scripts/diagnose.py prepare --stock 600519 --workdir .vs --evidence .vs/evidence.json
#   快照模式（零依赖零网络）
uv run --no-project $T/scripts/diagnose.py prepare --stock 600519 --workdir .vs --snapshot-dir <dir>
#   --cost <持仓成本>（可选，随任一 prepare 形态）：另落 lens.json——pack 增
#    「基本面锚」节、报告增「目标可达性」节（不进裁决/不进后验，见
#    03「基本面锚（透镜）不进裁决」）

# ④ LLM 产意见（SKILL.md 工作流）：读 .vs/context-pack.md + $T/strategies/*.yaml
#    → 写 .vs/opinions.json 与 .vs/risk.json，然后：
uv run --no-project $T/scripts/adjudicate.py \
  --opinions .vs/opinions.json --risk .vs/risk.json --evidence .vs/evidence.json \
  [--ledger ~/.vibe-stock/ledger.json] --out .vs/verdict.json

# ⑤ 报告 + 信号登记（--cost 触发的透镜在 ①+② 段说明；本段只出报告）
uv run --no-project $T/scripts/diagnose.py report --stock hk01810 --workdir .vs

# 存量平铺报告迁入分级布局（一次性；默认 dry-run，确认后加 --apply）
uv run --no-project $T/scripts/diagnose.py migrate-reports [--apply]

# 后验（隔若干交易日）
uv run --no-project --with 'akshare==1.20.*' --with yfinance --with efinance \
  $T/scripts/postmortem.py --stock 600519

# 回归（改 scripts/ 后必须全绿）
uv run --no-project $T/scripts/adjudicate.py --selftest
uv run --no-project $T/scripts/diagnose.py --selftest
uv run --no-project $T/scripts/postmortem.py --selftest
uv run --no-project $T/scripts/lens.py --selftest
```

## akshare 版本纪律

命令面统一锁 `akshare==1.20.*`（minor 锁：拿补丁修复、不吃破坏性迁移——
上游小版本内即发生接口文件迁移与列名随年份动态生成，2026-10 实证）。升版
流程：①探活候选版本四源（日K/新闻/财务/板块）；②四 selftest 全绿；③
CHANGELOG 记录并同步本文件锁版本。

## 港股速查

代码形态 `hk00700` / `0700.HK` / `00700` 统一归一 5 位（`00700`，报告目录
`00700.hk`）；Yahoo 侧再转 4 位（0700.HK）。已接入：
fundamentals（东财 HKF10→yf，质量分 85 good）、valuation（em-hk-ind 具名列
快照+baidu 5 年分位）、research（etnet→yf 双源：逐券商目标价/EPS/评级 +
90 日 EPS 修正方向）、notices（em-notice ann_type=H 单源，盈警/回购分型）、
moneyflow（南向持股 T-1 披露）、news（qq_news 单源）、market（港股指数）。
仍 not_supported：chip/forecast/unlock/holder/industry（港股无对应披露形态，
见 01 backlog）。港股全链约 +12 次 HTTP（16 簇之 etnet 为港股唯一新簇）。
fx 块取 HKD/CNY 入 pack 与 report 情报面（人民币敞口；汇率不进信号判定与
策略 YAML）；postmortem 加 `--cny` 可对 hk 信号附人民币口径展示（判定与
归因仍港币，见 [05](05-postmortem.md)）。
