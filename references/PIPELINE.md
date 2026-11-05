# PIPELINE · 五段流水线与命令速查

路径变量（唯一定义处）：`$T` = skill 根（SKILL.md 所在目录；Claude Code 下即 `${CLAUDE_SKILL_DIR}`）；`$W` = 本次诊股工作区（默认 `.vs/`）；状态目录 `~/.vibe-stock/`（signals.json / ledger.json / fetch_state.json / reports/<code>.<market>/ 单日多版本与时间线索引——布局见 [04](04-report.md)，不入仓）。本文件只覆盖单股五段流水线；多股批量（指数成分精选/筛 N/资金配置）走 [06-batch-scan](06-batch-scan.md) 子技能（`batch/` 参考实现，命令序见 [batch/README](../batch/README.md)）；在册股票盘中盯盘/收盘复核走 [07-monitor](07-monitor.md) 盯盘子技能（`batch/monitor/` 参考实现）；中线（1–6 个月）因子口径与只降不升风险判据族见 [08-midterm](08-midterm.md)；持仓股加仓决策轨（三道门 + 三段确认制）见 [10-add-on](10-add-on.md)；在册股短/中期走势参考（零权重卡与收盘批量）见 [09-outlook](09-outlook.md)；持仓股高抛低吸战术仓（用户裁量层预案，不进裁决链）见 [11-tactical-swing](11-tactical-swing.md)。

```text
① 取证据      fetch.py（多源回退+熔断冷却+八态+质量分；21 块=核心六块
              （计分）+扩展十五块（资金流/公告/研报/预告/解禁/股东户数/大盘/
              行业/估值/两融/指数基准/全A换手分位/ERP/两融账户参与度/汇率，
              零权重；其中两融/指数基准/全A换手分位/ERP/两融账户参与度五块
              市场级共享一次取数——汇率为港股链专属非共享）；A 股全链实测
              ~17s/17 次 HTTP）
              技术节另含 mid_term 中线因子三行——1–6 个月口径，判据见 08
② 拼上下文    diagnose.py prepare → context-pack.md（有界证据包+哨兵+置信帽+
              盘中警示行；--cost 时另附基本面锚节——取数时段口径见
              [01 · 盘中口径](01-evidence.md#盘中口径未完成-k-线)；走势参考卡
              outlook.json 恒现算注入「走势参考（零权重）」节（[09](09-outlook.md)））
③ 能力自检    市场支持表与新鲜度体现在八态本身（not_supported/missing 即答案）
④ 多角色+策略  LLM 按 SKILL.md 读 context-pack 与 strategies/*.yaml 产意见
              （双轨：短线 opinions.json + 中线 opinions.position.json +
              risk.json 两轨共用）→ adjudicate.py 验票/聚合/分歧
⑤ 裁决出报告   adjudicate.py RiskGuard 双轨各跑一次 → diagnose.py report →
              报告+双轨信号登记
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

# ④ LLM 产意见（SKILL.md 工作流，双轨）：读 .vs/context-pack.md +
#    $T/strategies/*.yaml——短线轨（无 profile 字段策略）写 .vs/opinions.json；
#    中线轨（profile: position 五策略）写 .vs/opinions.position.json；
#    风险角色两轨共用 .vs/risk.json，然后各跑一次（裁决器零改动）：
uv run --no-project $T/scripts/adjudicate.py \
  --opinions .vs/opinions.json --risk .vs/risk.json --evidence .vs/evidence.json \
  [--ledger ~/.vibe-stock/ledger.json] --out .vs/verdict.json
uv run --no-project $T/scripts/adjudicate.py \
  --opinions .vs/opinions.position.json --risk .vs/risk.json \
  --evidence .vs/evidence.json \
  --ledger ~/.vibe-stock/ledger.position.json --out .vs/verdict.position.json

# ⑤ 报告 + 信号登记（--cost 触发的透镜在 ①+② 段说明；本段只出报告；
#    workdir 有 verdict.position.json 时另渲染「中线裁决」节并二登记
#    profile=position 信号——无则单轨，行为与历史一致）
uv run --no-project $T/scripts/diagnose.py report --stock hk01810 --workdir .vs

# 存量平铺报告迁入分级布局（一次性；默认 dry-run，确认后加 --apply）
uv run --no-project $T/scripts/diagnose.py migrate-reports [--apply]

# 后验（隔若干交易日；两轨同评：default ±2% 带 / position σ√h 带仅 T+60 记分，
#     台账 ledger.json 与 ledger.position.json 分文件）
uv run --no-project --with 'akshare==1.20.*' --with yfinance --with efinance \
  $T/scripts/postmortem.py --stock 600519

# 在册股走势参考收盘批量（≥17:10；幂等：当日已卡跳过；--render 零取数重渲
#     日表；--stock <code> 单股刷新；--daily 成功后自动接 --calibrate 校准
#     （--no-calibrate 跳过）；并发与预算纪律见 09——FetchLock 单窗、盯盘期间不跑）
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
  python $T/batch/outlook_daily.py --daily [--force]

# 信号后验收盘评估（launchd 18:05 槽同款；evaluated 是经验面/绩效因子唯一
#     数据源——节奏与预算见 05「收盘后评估节奏」）
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
  $T/scripts/postmortem.py

# 回归（改 scripts/ 后必须全绿）
uv run --no-project $T/scripts/adjudicate.py --selftest
uv run --no-project $T/scripts/diagnose.py --selftest
uv run --no-project $T/scripts/postmortem.py --selftest
uv run --no-project $T/scripts/lens.py --selftest
uv run --no-project $T/scripts/addon.py --selftest
uv run --no-project $T/scripts/outlook.py --selftest
```

## akshare 版本纪律

命令面统一锁 `akshare==1.20.*`（minor 锁：拿补丁修复、不吃破坏性迁移——上游小版本内即发生接口文件迁移与列名随年份动态生成，2026-10 实证）。升版流程：①探活候选版本四源（日K/新闻/财务/板块）；②scripts 六件 selftest 全绿；③ CHANGELOG 记录并同步本文件锁版本。

## 港股速查

代码形态 `hk00700` / `0700.HK` / `00700` 统一归一 5 位（`00700`，报告目录 `00700.hk`）；Yahoo 侧再转 4 位（0700.HK）。已接入：fundamentals（东财 HKF10→yf，质量分 85 good）、valuation（em-hk-ind 具名列快照+baidu 5 年分位）、research（etnet→yf 双源：逐券商目标价/EPS/评级 + 90 日 EPS 修正方向）、notices（em-notice ann_type=H 单源，盈警/回购分型）、moneyflow（南向持股：披露 T-1、持股变动对应成交 D-2，口径见 [01](01-evidence.md)）、news（qq_news 单源）、market（港股指数）。仍 not_supported：chip/forecast/unlock/holder/industry（港股无对应披露形态，见 01 backlog）。港股全链约 +12 次 HTTP（20 簇之 etnet 为港股唯一新簇）。fx 块取 HKD/CNY 入 pack 与 report 情报面（人民币敞口；汇率不进信号判定与策略 YAML）；postmortem 加 `--cny` 可对 hk 信号附人民币口径展示（判定与归因仍港币，见 [05](05-postmortem.md)）。
