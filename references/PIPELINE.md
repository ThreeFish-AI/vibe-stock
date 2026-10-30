# PIPELINE · 五段流水线与命令速查

路径变量（唯一定义处）：`$T` = skill 根（SKILL.md 所在目录；Claude Code 下即
`${CLAUDE_SKILL_DIR}`）；`$W` = 本次诊股工作区（默认 `.vs/`）；状态目录
`~/.vibe-stock/`（signals.json / ledger.json / reports/ / fetch_state.json，
不入仓）。

```text
① 取证据      fetch.py（多源回退+熔断冷却+八态+质量分；15 块=核心六块
              （计分）+扩展九块（资金流/公告/研报/预告/解禁/股东户数/大盘/
              行业/估值，零权重）；A 股全链实测 ~17s/17 次 HTTP）
② 拼上下文    diagnose.py prepare → context-pack.md（有界证据包+哨兵+置信帽+
              盘中警示行——取数时段口径见
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

# ④ LLM 产意见（SKILL.md 工作流）：读 .vs/context-pack.md + $T/strategies/*.yaml
#    → 写 .vs/opinions.json 与 .vs/risk.json，然后：
uv run --no-project $T/scripts/adjudicate.py \
  --opinions .vs/opinions.json --risk .vs/risk.json --evidence .vs/evidence.json \
  [--ledger ~/.vibe-stock/ledger.json] --out .vs/verdict.json

# ⑤ 报告 + 信号登记
uv run --no-project $T/scripts/diagnose.py report --stock 600519 --workdir .vs

# 后验（隔若干交易日）
uv run --no-project --with 'akshare==1.20.*' --with yfinance --with efinance \
  $T/scripts/postmortem.py --stock 600519

# 回归（改 scripts/ 后必须全绿）
uv run --no-project $T/scripts/adjudicate.py --selftest
uv run --no-project $T/scripts/diagnose.py --selftest
uv run --no-project $T/scripts/postmortem.py --selftest
```

## akshare 版本纪律

命令面统一锁 `akshare==1.20.*`（minor 锁：拿补丁修复、不吃破坏性迁移——
上游小版本内即发生接口文件迁移与列名随年份动态生成，2026-10 实证）。升版
流程：①探活候选版本四源（日K/新闻/财务/板块）；②三 selftest 全绿；③
CHANGELOG 记录并同步本文件锁版本。

## 港股速查

代码形态 `hk00700` / `0700.HK`；Yahoo 侧自动归一 4 位（0700.HK）。news 走
qq_news 单源；fundamentals（港股经东财 HKF10 接入）/chip 与扩展块（除
market 港股指数）对港股为 not_supported，报告与质量分如实反映。
