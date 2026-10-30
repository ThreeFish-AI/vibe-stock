// wf_deepdive.mjs — Stage C 深评编排：对抗核验 + 三 lens 独立评审 + 确定性最终排名
// （批量子技能参考实现，references/06-batch-scan.md）。
//
// 宿主工作流脚本形态：在宿主 Workflow 工具（JS 脚本 API：phase/agent/parallel/
// pipeline/log 全局函数、args 为运行入参对象、export const meta 声明元信息）中
// 运行。路径全部参数化：args.scan_root（批量运行根目录）、args.skill_dir
//（skill 根目录，digest 命令用）、args.shortlist（midtier 入选表：
// [{code, name, industry, score}]）。
//
// 运行入参示例：{ scan_root: '~/.vibe-stock/reports/_scans/<date>-<pool>',
//                   skill_dir: '~/.claude/skills/vibe-stock',
//                   shortlist: [{code:'600519', name:'...', industry:'...', score:3.4}, ...] }
export const meta = {
  name: 'vibe-stock-deepdive',
  description: 'shortlist 对抗核验 + 三 lens 独立评审 + 确定性最终排名',
  phases: [
    { title: 'Verify', detail: '每股一对抗核验 agent，只做反驳' },
    { title: 'Judge', detail: '价值红利 / 成长景气 / 风险调整 三 lens 独立打分' },
    { title: 'Synthesize', detail: '确定性合分 + 叙事理由生成' },
  ],
}
const S = args.scan_root?.replace(/^~/, process.env.HOME || '~')
  || `${process.env.HOME}/.vibe-stock/reports/_scans/scan-latest`
const T = args.skill_dir?.replace(/^~/, process.env.HOME || '~')
  || `${process.env.HOME}/.claude/skills/vibe-stock`
const digestCmd = (code) => `uv run --no-project ${T}/batch/digest.py --scan-root ${S} ${code}`

const VERIFY = {
  type: 'object',
  properties: {
    code: { type: 'string' },
    refute_confidence: { type: 'number' },
    falsifiers: { type: 'array', items: { type: 'string' } },
    hard_falsified: { type: 'boolean' },
    verdict_uphold: { type: 'boolean' },
    websearch_used: { type: 'boolean' },
    notes: { type: 'string' },
  },
  required: ['code', 'refute_confidence', 'falsifiers', 'hard_falsified', 'verdict_uphold'],
}
const JUDGE = {
  type: 'object',
  properties: {
    lens: { type: 'string' },
    scores: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          code: { type: 'string' },
          s: { type: 'number' },
          subs: { type: 'string' },
        },
        required: ['code', 's', 'subs'],
      },
    },
  },
  required: ['lens', 'scores'],
}

const verifyPrompt = (t) => `你是 vibe-stock 批量诊断的对抗核验代理，负责证伪「${t.code} ${t.name}」的买入论点。只做反驳，不做辩护。

先用 Bash 运行 \`${digestCmd(t.code)}\` 读取证据摘要（stdout JSON；SSOT：score 为 ≥0.2.1 管线聚合分复算，initial/final 为管线初判与终裁）。逐项排查可证伪证据：
1. 解禁：ext_blocks_truncated.unlock 的 upcoming 批次日期与规模占流通市值比；
2. 业绩雷：forecast 预告是否预亏/大幅下修；financials.np_yoy 与 rev_yoy 是否背离；
3. 估值极端：valuation.pe_percentile_5y / pb_percentile_5y 是否处于 5 年高位；
4. 技术破位：price 与 lo20/ma20 位置、tech.rsi14 超买、pct_from_52w_high 追高风险；
5. 单源依赖与证据缺口：core_states、ext 块 fetch_failed/degraded 情况；
6. 行业景气背离：industry 块与新闻面是否与个股逻辑矛盾；
7. top_bear_rationales 中置信最高的空头理由是否成立。

允许用 WebSearch 兜底核验公开事实（解禁公告/业绩预告），但 rationale 必须标注「web-search 兜底」且不得引用无出处数字；核验失败按证据缺失处理，不脑补。
输出：refute_confidence（0-1，你对该股不应入选的信心）、falsifiers（具体证伪点列表，每条含数值依据）、hard_falsified（是否发现硬证伪：确认预亏/立案/超大比例解禁等）、verdict_uphold（原判是否站得住）、websearch_used、notes。`

phase('Verify')
const verifies = await parallel(args.shortlist.map((t) => () =>
  agent(verifyPrompt(t), { label: `verify:${t.code}`, phase: 'Verify', schema: VERIFY })))
const vmap = {}
for (const v of verifies.filter(Boolean)) vmap[v.code] = v
log(`verifier 完成 ${Object.keys(vmap).length}/${args.shortlist.length}；硬证伪：${Object.values(vmap).filter((v) => v.hard_falsified).map((v) => v.code).join(',') || '无'}`)

const lensDefs = [
  { key: 'value', name: '价值红利', rule: 'PE/PB 5 年分位 30% + 股息率 25% + ROE 水平与稳定 25% + 现金流（每股经营现金流/价）20%' },
  { key: 'growth', name: '成长景气', rule: '净利/营收增速 35% + 行业景气（industry 块+板块）25% + 事件催化（forecast/notices/research）25% + 技术趋势 15%' },
  { key: 'risk', name: '风险调整', rule: '止损空间（1−stop/price，stop=0.95×price 或 0.99×lo20 取紧）25% + 20 日波动与回撤 25% + 冲突等级与 severity 20% + 解禁/减持事件 15% + 证据缺口 15%' },
]
const judgePrompt = (lens) => `你是 vibe-stock 深评的独立评审（lens：${lens.name}）。对下列 ${args.shortlist.length} 只候选股逐一打分 s∈[0,10]（一位小数），评分维度与权重：${lens.rule}。

逐个用 Bash 运行以下命令读取证据摘要（stdout JSON）：
${args.shortlist.map((t) => `- ${t.code} ${t.name}: \`${digestCmd(t.code)}\``).join('\n')}

要求：subs 必须给出各维度子分与关键数值（如 "PE分位 32%→8.2；股息率 4.1%→7.5；…"）；只用 digest 内数值，缺数据的维度按中性 5 分并注明缺失；不同股票间保持同一把尺子。禁止网络搜索。`
phase('Judge')
const judges = await parallel(lensDefs.map((lens) => () =>
  agent(judgePrompt(lens), { label: `judge:${lens.key}`, phase: 'Judge', schema: JUDGE })))
const lensScores = {}
for (const j of judges.filter(Boolean)) {
  lensScores[j.lens] = {}
  for (const sc of j.scores) lensScores[j.lens][sc.code] = { s: sc.s, subs: sc.subs }
}
log(`judge 完成 ${Object.keys(lensScores).length}/3 lens`)

// ---- 确定性合分（无自由裁量）----
const rank = []
for (const t of args.shortlist) {
  const cs = t.score ?? 2.5
  let sSum = 0, n = 0
  for (const lens of Object.keys(lensScores)) {
    const e = lensScores[lens][t.code]
    if (e) { sSum += e.s; n += 1 }
  }
  const lensAvg = n ? sSum / n : 5
  const v = vmap[t.code]
  let penalty = 1
  if (v && v.refute_confidence >= 0.7) penalty = 0.85
  const final_score = penalty * (0.30 * (cs - 1) / 4 + 0.70 * lensAvg / 10)
  rank.push({ code: t.code, name: t.name, industry: t.industry, score: cs,
    lensAvg: Math.round(lensAvg * 100) / 100, penalty, final_score: Math.round(final_score * 1000) / 1000,
    refuted: v ? v.refute_confidence : null, hard_falsified: v ? v.hard_falsified : null })
}
rank.sort((a, b) => b.final_score - a.final_score || b.score - a.score)

phase('Synthesize')
const NARR = {
  type: 'object',
  properties: {
    narratives: {
      type: 'array',
      items: {
        type: 'object',
        properties: { code: { type: 'string' }, why: { type: 'string' } },
        required: ['code', 'why'],
      },
    },
  },
  required: ['narratives'],
}
const narr = await agent(`以下是 vibe-stock 批量诊断的最终投资价值排名（确定性公式合成，不得改分）。为每只写 80-150 字的「为何值此名次」，必须引用各 lens 子分与意见 rationale 中的具体数值/事件（用 \`${digestCmd('<code>')}\` 读摘要，并读 ${S}/vs/<code>/opinions.json——意见 rationale 是 SSOT）。

排名（JSON）：${JSON.stringify(rank.map((r, i) => ({ rank: i + 1, ...r })))}
lens 明细：${JSON.stringify(lensScores)}
核验结论：${JSON.stringify(Object.fromEntries(Object.entries(vmap).map(([k, v]) => [k, { refute_confidence: v.refute_confidence, falsifiers: v.falsifiers.slice(0, 3) }])))}
输出 narratives 数组，每项 {code, why}，覆盖全部 ${rank.length} 只。中文，像资深分析师对同事说话，删掉套话。`, { label: 'narratives', phase: 'Synthesize', schema: NARR })
const narrMap = {}
if (narr) for (const n of narr.narratives) narrMap[n.code] = n.why

return {
  ranking: rank.map((r, i) => ({ rank: i + 1, ...r, why: narrMap[r.code] || '' })),
  lensScores,
  verifiers: vmap,
}
