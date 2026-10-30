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
| 决策信号八态 + 对立失效 + 后验 | `diagnose.py register_signal` + `postmortem.py` |
| 策略 YAML 说明书（策略即数据） | `strategies/` 十策略 + 自定义扩展位 |
| 扩展证据块 | 十块零权重情报面（资金流/公告/研报/预告/解禁/股东户数/大盘/行业/估值/汇率）不进质量分；簇级熔断（fx 汇率为港股专属块） |

## 港股覆盖

财务（东财 HKF10→yfinance）、估值（具名列快照+百度 5 年分位+分位表）、研报
共识（ETNet→yfinance 双源：逐券商目标价/EPS/评级、90 日 EPS 修正方向）、公告
（东财 ann_type=H，盈警/回购分型）、南向持股（T-1 披露口径）均已接入免 key
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

文档：[SKILL.md](SKILL.md)（路由壳）→ [references/](references/)（六篇规约 +
PIPELINE）→ [batch/](batch/)（批量子技能参考实现）→ [strategies/](strategies/)
（策略库）。回归：
`scripts/*.py --selftest` 四件全绿。

## 免责

本项目输出仅供学习与研究参考，不构成投资建议；不下单、不保证收益。

## License

MIT（策略库结构与判据形态借鉴 DSA 的 MIT 实现，口径已按本项目证据模型重写）。
