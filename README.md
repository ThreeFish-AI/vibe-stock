# vibe-stock

诊股 Skill：给一只 A 股 / 港股，产出带证据状态、分歧摘要与单向风险裁决的
专业决策报告。机制蓝本取自开源项目 [daily_stock_analysis](https://github.com/ZhuLinsen/daily_stock_analysis)
（MIT，下称 DSA）并经精读提炼（见 negentropy 仓 `docs/research/agent-harness/178`）。

## 它从 DSA 学到了什么

| DSA 机制 | vibe-stock 落地 |
| --- | --- |
| 八态证据状态（缺什么写什么） | `fetch.py` 逐块标注，报告可见 |
| 六块质量分 + 核心块降级禁高置信 | `fetch.py` quality + `adjudicate.py` 置信帽 |
| 多源回退链 + 熔断 + 冷却 | `fetch.py`（状态持久化） |
| 外部摘要不可信哨兵（防注入） | `context-pack.md` `<untrusted_external>` 包裹新闻 |
| 信号资格分选（五标准信号，无效进诊断） | `adjudicate.py partition` |
| 绩效因子后验反馈（Beta 收缩、钳制） | `postmortem.py` + `ledger.json` |
| 分歧显式化（三桶 + 冲突分级） | `adjudicate.py aggregate/disagreement` |
| RiskGuard 只降不升 | `adjudicate.py risk_guard`（veto/单向降档/永不升级） |
| 决策信号九态 + 对立失效 + 后验 | `diagnose.py register_signal` + `postmortem.py` |
| 策略 YAML 说明书（策略即数据） | `strategies/` 十五策略（十短线 default + 五中线 position）+ 自定义扩展位 |
| 扩展证据块 | 十块零权重情报面（资金流/公告/研报/预告/解禁/股东户数/大盘/行业/估值/汇率）不进质量分；簇级熔断（fx 汇率为港股专属块） |

## 港股覆盖

财务（东财 HKF10→yfinance）、估值（具名列快照+百度 5 年分位+分位表）、研报
共识（ETNet→yfinance 双源：逐券商目标价/EPS/评级、90 日 EPS 修正方向）、公告
（东财 ann_type=H，盈警/回购分型）、南向持股（披露 T-1、持股变动对应成交
D-2 口径）均已接入免 key
公开源；chip/forecast/unlock/holder/industry 为港股能力边界（无对应披露形态），
如实标 not_supported。

## 基本面锚（--cost）

`prepare --cost <持仓成本>` 触发与短线信号正交的目标可达性透镜（scripts/lens.py
纯函数）：参考价隐含 PE 与 5 年分位（免汇率比值法）、券商共识目标价位置/离散度/
≥参考价家数、EPS 90 日修正方向、12 个月波动触及概率——三档结论（支撑不足/中性/
有支撑）只作中长期参考：不进裁决聚合、不进置信帽、不进 T+1/3/5/10 后验；
极端高估只作为风险角色 downgrade 线索（只降不升）。

## 快速开始

```bash
# 安装（Claude Code）：软链本仓到 skills 目录
ln -s <clone 路径> ~/.claude/skills/vibe-stock

# CLI 直用（不依赖宿主）：
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
  scripts/diagnose.py prepare --stock 600519 --workdir .vs
# 中段：按 SKILL.md 工作流产意见（opinions.json / risk.json）
uv run --no-project scripts/adjudicate.py --opinions .vs/opinions.json \
  --risk .vs/risk.json --evidence .vs/evidence.json --out .vs/verdict.json
uv run --no-project scripts/diagnose.py report --stock 600519 --workdir .vs
```

## 中线双轨（08 规约，0.0.16 起）

1–6 个月操作周期与短线并行成轨（默认双轨）：

- **证据面**：`technical.mid_term` 纯函数派生中线因子（跳月动量、已实现波动、
  最大回撤、长均线、方差比 VR(63)、涨停计数、异常换手——A 股月度反转强于
  动量、换手是最强情绪信号等 A/HK 实证口径），随每份 context-pack 透出。
- **方向票**：五个 `profile: position` 策略（质量价值 / 预期修正 / 国策分层 /
  翻身催化 / 波段带，置信帽 0.65）出 opinions.position.json，adjudicate 零改动
  第二跑（`--ledger ledger.position.json` 绩效不串轨），报告出「中线裁决」节
  与波段带三键（band_lo/band_hi/trail_ref）。
- **风险面**：利好出尽 / 主题拥挤与 AI 情绪 / 制度与政策三族判据走风险角色
  risk.json **只降不升**，两轨共用。
- **自校准**：T+20/60/120 后验（σ√h 判定带，仅 T+60 记分，台账分文件）；
  对立失效与同日重跑去重均按 profile 隔离。
- 调研依据（IEEE 引文与效应量、拒绝引入清单）见
  [docs/research/midterm-strategies.md](docs/research/midterm-strategies.md) 与
  [references/08-midterm.md](references/08-midterm.md)。

## 持仓加仓决策轨（09）

对 portfolio.json 在册持仓，report 段自动跑 `scripts/addon.py` 确定性加仓门：
**三道门**（资格只冻不升格：短线/中线卖族、风险角色降档、A-1~A-5 风险链
确定性判据 → 策略买点触发：顺势回踩主轨 + 逆势窄门「quality_value+基本面锚
支撑+零风险链」→ 三段确认制手数：首加 1/2 批 → T+3 确认/撤销 → 60 日限频
与浮亏包络）。报告持仓者分支五档（可加仓/持有·含等回踩变体/持有观察/
减仓/离场）+「加仓
评估」节逐门可溯源；首加建议登记 addon 信号（T+1/3/5/10 后验按 bull 记
分——加仓建议也要被市场打分）。规约见
[references/09-add-on.md](references/09-add-on.md)。

## 盘中盯盘（07 子技能）

对在册股票（实盘持仓 + 模拟配置 + 观察票）做盘中价格面轮询：确定性规则锚定
每日报告的止损/目标/参考买点三价位，击穿/收回/触目标/异动/触板/停牌等事件
落台账并发本地事实通知，15:10/16:10 收盘复核终判后出日报；launchd 每个交易日
09:15 主槽自动拉起，交易时段内每 30min 补拉槽兜底（重启/开机/被杀后由
下一补拉槽恢复，交易盲窗 ≤30min；收盘复核由 16:15 盘后槽兜底）。边界：
只发本地事实告警，不接第三方推送、不执行任何交易，盘中
结论以收盘复核为准，当日信号登记仍归每晚全诊。见
[references/07-monitor.md](references/07-monitor.md) 与
[batch/monitor/](batch/monitor/)。

文档：[SKILL.md](SKILL.md)（路由壳）→ [references/](references/)（九篇规约 +
PIPELINE）→ [batch/](batch/)（批量子技能参考实现）→
[batch/monitor/](batch/monitor/)（盯盘参考实现）→ [strategies/](strategies/)
（策略库）。回归：`scripts/*.py --selftest` 五件全绿（硬门禁）+
`batch/monitor/*.py --selftest` 两件全绿（非阻塞第六条）。

## 免责

本项目输出仅供学习与研究参考，不构成投资建议；不下单、不保证收益。

## License

MIT（策略库结构与判据形态借鉴 DSA 的 MIT 实现，口径已按本项目证据模型重写）。
