# 07 · 盯盘子技能：在册股票盘中监控（SSOT）

定位：五段流水线（[01](01-evidence.md)–[05](05-postmortem.md)）与批量编排
（[06](06-batch-scan.md)）之上的**监控编排层**——盘中价格面轮询、确定性触发
规则、本地事实告警、收盘复核；不触碰单股裁决链。参考实现在
[batch/monitor/](../batch/monitor/)（口径以本文件为准）。版本要求 ≥0.0.15。

## 定位与边界（无条件全局规则：监控层只提示不执行）

- **只提示不执行**：监控只产「事实事件 +（P2 起）建议卡」，无任何交易接口；
  实际成交永远由用户手动完成。任何「触发即执行/写回即成交」形态一律禁止。
- **本地告警边界**（SKILL.md 边界修订，用户 2026-11-02 裁定）：盘中本地价位
  监控与本地告警（osascript 通知/stdout/落盘）允许；**禁止接入第三方推送
  通道**（IM/webhook/云推送）、禁止任何自动交易执行。
- **永不写 signals.json**：当日信号登记唯一归当晚全诊 report（同 06「中
  tier 不登记」纪律，防 I-004 同日重复登记污染八元组去重与对立失效向量）。
  盘中事件台账 `monitor:` 前缀独立归因，不进 ledger.json（P3 独立画像）。
- **盘中结论以收盘复核为准**：全部通知/事件/日报带「待收盘复核」口径；
  量能判据消费外推值时标 estimated（[01 · 盘中口径](01-evidence.md)）。
- **监控层不触碰裁决链**：意见/风险/聚合/RiskGuard 各环零改动；P2 起局部
  重诊 100% 复用 adjudicate 原命令（只降不升三重锚见「升级链（P2 预留）」）。

## 宇宙层

- 宇宙 = 实盘持仓（`~/.vibe-stock/portfolio.json`，经 `archive.load_portfolio`
  契约加载）∪ 模拟配置（最新 `_scans/*/portfolio/allocation.json` rows——
  「最新」= 目录名日期最大且 rows 非空）∪ 信号观察票（signals.json 有最新
  信号的 codes）。kind 标注 real / sim / watch，排序实盘优先。
- **脱敏（无条件全局规则：敏感信息零落盘红线）**：`monitor/universe.json` 只投影阈值与派生量
  （stop/target1/entry_ref/limit_pct），成本与数量**绝不落盘**——运行期现算
  现用；台账只落 `high_since_entry` 与距线百分比（P2 trailing）。selftest
  fixture 一律合成标的与虚构数值，并带「fixture 与真实 portfolio.json 零重合」
  负断言（坑位：脱敏断言只查产物不查输入时，真实持仓会经测试数据入公开仓）。
- 价位锚 SSOT：优先 signals.json 组内最新 `key_levels`；模拟股无信号时回退
  allocation 三价常量并标 `levels_source`；两者皆缺 → 该股降级为仅 ±%/触板
  监控并显式告警（不静默失效）。
- 价位锚分轨（0.0.16 起）：锚只取 **default 轨**信号的 key_levels
  （`latest_signals` 按 profile 过滤）——position 轨的波段带三键
  （band_lo/band_hi/trail_ref）语义不同，混入会覆盖短线止损/目标锚；
  波段带锚的带内状态规则见下「升级链」P2 补充。
- 触板限幅（已知简化）：创业/科创 20%、北交 30%、主板 10%、主板 ST 减半；
  创业/科创 ST 不减半。涨停价精确计算有四舍五入坑，判定一律用近触板
  （限幅 − 0.3pp）。

## 数据面

- **主源**：qt.gtimg 批量全量快照（30 码/批）。A 股 `v_shXXXXXX`（量纲：
  主板/创业/北交 量=手、科创 688 量=股，额=万）；港股 `v_r_hkXXXXX`（响应变量
  名带 `v_` 前缀、时间戳 `YYYY/MM/DD HH:MM:SS` 格式——2026-11-02 实测钉住；
  港股量纲未钉，不消费量能）。指数紧凑快照（s_ 前缀）各 1 次/轮入 ticks 台账。
  **量能判据禁用跨源量比**（量纲按板块/市场分裂：主板-创业-北交为手、科创
  688 为股，错向偏差 100 倍——P2 量能确认用换手率比 f[38]÷缓存 5 日均换手率，
  两端百分比无单位坑）。
- **结构自洽校验（无条件全局规则：不静默信任位序）**：涨跌额==价差、
  low≤{price,open}≤high、A 股 vwap∈[low,high]±2%（港股量纲未钉不验）；
  校验不过整行弃；弃行/缺行的票出一次性 `source_dropped` 事件并通知（不静默
  失明）。现价 ≤0、非法时间戳只弃该行/置空，不连坐整批——qt 是无官方契约的
  网页接口，位序随版本漂移。
- **港股源验证与抽检**（P1 只作标注，不改变盘中取数源）：`--verify-hk`
  （16:10 后才跑，末根=收盘价、残余差即纯延迟）单时点对照 r_hk 快照 × 新浪
  rt_hk（带 Referer）× 日 K 收盘，偏差 ≤0.3% 记 `mode=r_hk` 否则
  `bars_fallback`，结论持久化 `state.hk_source`；每日 `--close` 对全部在盯港股
  （不论有无事件）以收盘价抽检末轮快照，阈值 0.5%（末轮距收盘竞价有缓冲），
  结论入 `hk_source.daily_check` 与日报「源健康」节。多时点转正源属 P2。**s_ 紧凑快照禁作港股价格源**（实测量滞后 2.3%、f[4] 为涨跌额、
  无高低价与时间戳）。
- **延迟口径**（用户 2026-11-02 裁定）：港股快照延迟 >15min 时接受「延迟
  盯盘」，通知文案加「(延迟行情)」前缀如实标注 + 一次性 hk_delayed 事件，
  不静默。坑位：午休（12:00–13:00）时间戳停在 12:00，延迟判定豁免午休窗、
  并排除已挂起（停牌）票，否则每日必误报一次并耗掉一次性标志。
- **频率与预算**：默认 180s/轮（可配 120–300s）；按市场独立计时（`next_due`，
  一个市场退避不拖慢另一个）。全生命周期 9:30–16:00 ≈130 轮：9:30–15:00 两市
  各 2 次（批量+指数）、15:00–16:00 仅港股 2 次，合计 ≈480 请求/日，另加
  --close 事件股与港股日 K——与一次全诊（357 次）同量级，如实计入。斜率类检测（P3）用事件驱动加密采样（首触后 10min 内 60s，
  增量 ≤10 次/股），不全局提频。
- **熔断隔离（无条件全局规则：盯盘不耗诊股额度）**：轮询失败只计本地退避
  （180→540→600 封顶，跨日归零），不写共享 `fetch_state.json` 熔断账本；仅
  `--close`/`--verify-hk` 拉日 K 时经全局锁 `fetch_state.lock` 写账本。两把锁
  均为 flock 咨询锁：持有进程退出即由内核释放，不支持抢占存活持有者，取数锁
  竞争 120s 超时即挂起并告警（不静默跳过）；watch 单实例锁
  `monitor/watch.lock` 防 launchd 双开。坑位：全诊 prepare 不识别全局锁，
  「盯盘期间不跑全诊」仍是使用纪律（I-005 教训），P4 RSI 评审决定是否统一
  锁入口。

## 触发规则（P1 已实施；确定性纯函数，离线可测）

| 规则 | 条件 → 动作 | 口径依据 |
| --- | --- | --- |
| stop_break / confirmed | price < stop 首触即报；连续 2 轮确认（mech_risk downgrade=high） | key_levels.stop；06 三价纪律 |
| 加深穿透 | 击穿较上次报文加深 ≥2% → 穿透冷却再报（升级事实优先于重复计数） | 防冷却期静默深跌 |
| whipsaw | 曾击穿且收回 → 事件挂「待收盘终判」；收回后再破/再确认属事实反转，穿透冷却必投递 | 01 盘中口径；通知面最新状态不得停在「已收回」 |
| target_hit | price ≥ target1 越线首报；回落到线下后再越线才再报（episode，不靠冷却过期重报） | key_levels.target1=hi20 |
| abnormal_move | \|chg\| ≥5%（A）/8%（港，可配）连续 2 轮首报，回到阈值内才复位（episode）；开盘静默窗（开盘 10min 内）只记不发 | 双轮消抖防毛刺 |
| gap_open | 首轮 \|open/prev−1\| ≥ 阈值 → 一次性（免冷却、不复升级） | 跳空是常态不是异动 |
| limit_hit | 近触板（限幅−0.3pp），当日每方向一次 | 见宇宙层触板简化 |
| t2_pending_fill | sim 股 low ≤ entry_ref → 推演成交 min(open, entry_ref)，**只推演不写回** | T2 GTC 纪律；写回属 P3 sim SSOT |
| frozen / resumed / gap_move | 价量连续 5 轮不变 → 挂起该票；复牌差异 ≥3% 提醒；当日再冻结只留痕不通知 | 停牌检测；午休冻结豁免且轮次清零（cn 11:30–13:00、hk 12:00–13:00） |
| market_halted / market_resumed | 当轮全组快照最大日期 ≠ 今日 → 该市场停轮；出现今日时间戳即解除 | 休市工作日静态快照防线（单票停牌的陈旧时间戳交给冻结检测，不误杀全市场） |
| hk_delayed / source_dropped / storm_digest | 见数据面延迟口径 / 缺行口径 / 风暴闸 | 如实标注 |

- **抑制链（全部留痕 suppress_reason）**：同股同规则 30min 冷却 → 单股日
  通知上限（默认 6）→ 组合风暴闸（10min 窗口 ≥8 条 → 压制，窗口滚动后补一条
  带股票代码的聚合摘要，无新事件也补发）。**带 mech_risk 的风险事实（止损
  确认/加深）豁免日上限与风暴闸**（无条件全局规则：系统性下跌日正是风暴闸
  最易触发、止损最密集之时，风险事实不得被信息类事件挤掉）。事件台账
  append-only 记全量（含被压制事件），通知只是投递面。
- **通知口径（无条件全局规则：不构成投资建议红线，通知面不承载指令）**：
  只报事实（股票/事件/价位/百分比/距离），零成本绝对值、零指令性建议（「减
  仓」「离场」等指令词一律进 P2 建议卡并带免责尾注）；全部通知（含运维类：
  锁竞争、进程异常、源缺行）尾注统一「待收盘复核·非投资建议」，由 notify()
  单点追加。

## 收盘复核（--close）

- 时点 15:10（A）/16:10（港）——给盘后定价与港股收盘竞价留缓冲；手动 `--close`
  与 `--loop` 同一把时点门，未到点拒跑（坑位：盘中拉到的日 K 末根是盘中价，
  终判与源抽检都会错判且 close_done 会固化错误结论——2026-11-02 15:43 手动
  实测误报源偏差）。
- 事件股 + 全部在盯港股重拉日 K（fetch_daily_bars 整链复用）→ 终判：止损确认（close<stop）/
  whipsaw 坐实（low<stop≤close）/撤回；目标1 站上/回落；T2 触价坐实。末根
  日期 ≠ 今日 → 该股「挂起次日补判」（不拿昨日根错判）。
- `monitor/day-summary/<date>.md` 是派生视图（events/ticks 台账是事实源），
  幂等重渲（当日无事件也出，覆盖区间可审计），含盯盘覆盖区间（首末 tick +
  缺口：相邻 tick 间隔 >2×interval 且不在午休窗）、次日盯盘重点（未处理机械
  降档事件）、固定免责尾注。`close_done` 按日归零（跨日继承会让次日起收盘
  复核静默跳过）。
- 港股源每日抽检随 --close 执行（见数据面）。锁竞争失败 → 显式告警挂起
  重跑，不静默跳过。

## 宿主形态（launchd，用户裁定 P1 即上）

- LaunchAgent 模板随仓交付（`batch/monitor/com.threefish.vibestock.monitor.plist`，
  安装命令见 [batch/monitor/README](../batch/monitor/README.md)）：
  StartCalendarInterval 周一至周五 09:15 主槽拉起 `--loop`（叠加
  交易时段补拉槽与 16:15 盘后兜底槽，语义见下条，I-009）；`KeepAlive.Crashed`
  只认信号级崩溃（launchd.plist(5)），故 watch.py 把 `--loop` 的 Python 未捕获
  异常转为通知 + SIGABRT 才能自愈；正常收口 exit 0、重复实例 exit 3、P2 会话
  接管 exit 2 均不重拉（防「触发-退出-拉起」空转循环）；`AfterInitialDemand`
  防 bootstrap 时投机拉起；StandardOut/ErrorPath 落 `monitor/logs/`。坑位：
  launchd 不继承 shell PATH（默认 /usr/bin:/bin:/usr/sbin:/sbin），模板用
  `__UV_PATH__` 绝对路径占位；launchd 不建日志父目录（安装命令先 mkdir，
  watch.py 入口亦自建）。
- **补拉槽语义（I-009）**：条件——工作日 09:15 主槽之后系统重启/开机/
  重新登录/进程被非崩溃信号杀死时，launchd 对关机/重启期间错过的日历触发
  **不补发**（launchd.plist(5) 只承诺睡眠期间错过的触发在唤醒时合并补发一次），
  仅 09:15 单槽的旧模板当日不再拉起、直至手动 kickstart；做法——模板保留
  09:15 主槽，叠加周一至周五交易时段补拉槽（09:45–11:45、13:15–15:45 各每
  30min 一槽，相邻槽交易盲窗 ≤30min；11:45 槽为覆盖港股早盘尾段而设，两市
  共同休市窗 12:00–13:00 零槽）与 16:15 盘后兜底槽（进程在收盘复核前死亡时
  `close_done` 未置，16:15 重拉即补跑 `--close`；已置则立即 exit 0，幂等无
  副作用）；`RunAtLoad` 维持 false、`AfterInitialDemand` 维持 true——补拉只靠
  日历槽、不靠投机拉起（I-008 初衷与 launchd.plist(5) 对 RunAtLoad 的告诫均
  不回退）；watch.py 运行时零改动（任意时刻拉起自洽：盘前等待、日期守卫停轮、
  收口即退），watch.py selftest 以 plistlib 解析模板钉死全部关键属性。已知
  坑位：① 槽位落在进程运行期间会被 launchd **直接丢弃**——不并发第二实例、
  进程退出后也不排队补拉（2026-11-03 本机探针实测：双日历槽 + 150s 常驻
  进程，运行期间槽位被丢、runs 不增；与 launchd.plist(5) StartInterval 的
  missed-firing 语义同构）——故正常运行日补拉槽零开销、无 watch.lock exit 3
  风暴，单实例锁仅作兜底；② 槽位按系统本地时区触发，沿用 09:15 主槽
  「机器时区 = Asia/Shanghai」的既有假设，机器时区非 UTC+8 时先改系统时区；
  ③ 当日彻底停盯盘不能只 kill 进程（会被下一补拉槽重新拉起——交易盲窗
  ≤30min，午休跨槽至 13:15），须
  `launchctl bootout` 卸载作业；④ P2 会话接管（exit 2）落地时须重估补拉槽
  与「launchd 拉起 `--once` 补轮」的协调——接管期间 `--loop` 重拉会破坏
  「触发即退出交还会话」语义。
- `--loop` 生命周期：盘前等待 → 按 `session_phase` 逐市场门控轮询（A/港独立，
  交叉窗口 11:30–12:00 / 15:00–16:00 各自正确）→ 15:10/16:10 后自动跑一次
  --close → exit 0。节假日误拉起由日期守卫停轮兜底（P4 交易日历前不依赖人）。
- 运行时统一 `uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance`（--close 拉日 K
  需要回退链全部依赖——港股链 ak-em→yf，缺 yfinance 时东财限流即单源全挂，
  2026-11-02 实测；裸 python3 缺 CA 证书会 SSL 失败——2026-11-02 实测坑位）。
- 会话不在场时监控照常（通知+台账）；P2 起 T2 升级默认「会话在场接管」形态，
  watch 触发即退出（exit 2）交还会话，无人值守自动拉起 LLM 属 M3 且须用户
  显式开启预算闸。

## 产物 SSOT 布局（`~/.vibe-stock/monitor/`）

```text
universe.json            盯盘宇宙（当日派生，脱敏；跨日自动重派生）
state.json               运行时状态（rules 去抖/冷却/风暴闸 + 源退避 + hk_source，
                         日期变更整体归零；原子写）
ticks/<date>.jsonl       逐轮快照台账（行情时刻 + 本地时刻双时间戳）
events/<date>.jsonl      事件台账（append-only，含被压制事件与原因）
day-summary/<date>.md    收盘日报（派生视图，幂等重渲）
logs/                    launchd stdout/stderr
watch.lock / ../fetch_state.lock   单实例锁 / 全局取数锁
```

## 升级链（P2 预留——规约先钉死，实施走后续 PR）

- T1 轻量刷新：触发股重拉日 K → derive_technical 重算 → snapshot 通道拼新
  evidence → `prepare --evidence` 直入出新 context-pack（五段流水线零改动）。
- T2 局部重诊（会话内）：重放该股全部过门 opinions + 按触发事实覆写
  risk.json（机械布尔预写，LLM 只补 rationale）；证据剧变才重产全意见 →
  adjudicate 原命令重裁决 → 建议卡（候选动作 + 与上一裁决差异 + T+1 可卖
  份额 + 免责尾注）。
- **只降不升三重锚（无条件全局规则：RiskGuard 只降不升红线延伸到盘中重裁决全链）**：① 同批意见结构性单调（RiskGuard
  LADDER 单向）；② 机械 risk 布尔与 LLM risk 的合并落代码取更保守值（随
  RSI-20261102-01 修法经 RSI PR 进 scripts/，合入前覆写判据表只是显式登记
  的会话约束）；③ 盘中终版不得比该股最近一次已登记信号（LADDER 序）更激
  进，违例拒出建议卡、降级为纯事实通报——堵死重产意见后 hold→buy 的变相
  升级通道。
- 意见保鲜机械门：opinions 带数据日戳；意见数据日 ≠ 今日 强制重产；有效
  意见 <2 回退全意见重产（insufficient 铁律）。
- 监控不空窗：会话接管重诊期间由 launchd 拉起 `--once` 补轮；每日 T2 重诊
  ≤5 票、实盘优先、超额降级 T0+收盘终判留痕。
- 机械降档判据单权威：代码判据（RSI PR）合入当版，本文件覆写表即改指针。
- P2 规则预钉（前置门：缓存 technical 数据日 == 今日，否则当日禁用 + data_stale
  告警）：ma20_break（price < ma20×0.98 → 注入 downgrade=medium）、trailing
  （high_since_entry ≥ 成本×1.15 武装、武装后破 ma20 → trailing_exit 收盘终判）、
  HS300/HSI 收盘破 MA60 → 全组合降档评估提示。
- P2 波段带带内状态（0.0.16 规约先行，实施随 P2）：position 轨信号
  `key_levels` 的 band_lo/band_hi/trail_ref 三键作监控锚——band_lo 触发
  「低吸复核」提示、band_hi 触发「高抛复核」提示、收盘破 trail_ref 提示
  「波段结束复核」；只发本地事实告警（尾注免责与既有事件同），不执行、
  不写 signals.json；锚选取与 default 三价并行不互覆（上文「价位锚分轨」）。
- **权重提示分桶不折算**（用户 2026-11-02 裁定）：条件——P2 单仓权重 >16%
  「次日减至 ≤14%」提示；做法——A 股桶（CNY）与港股桶（HKD）各自以本桶市值为
  分母算 16% 线，不做 HKD/CNY 折算，fx 不进判定（SKILL 红线 4）；坑位——跨币种
  合并算权重会把汇率带进判定；16%/14% 持有期漂移锚与 06 建仓带 14.5% 是两把尺。

## sim 组合 SSOT（P3 预留——用户裁定「一并建」，schema 先钉死）

`~/.vibe-stock/sim-portfolio.json`：`{version, updated_at, budget, cash,
positions:[{code, market, lots, avg_cost, status: holding|pending_open|closed,
stop, entry_ref, target1, trailing_armed, high_since_entry, tranches:[{leg:
T1_open|T2_limit|T3_trigger, lots, status: pending|filled|expired, ref_price,
filled_price, filled_at}]}], operations:[{code, side, lots, price, ts, tranche_ref}]}`
——T2 触价写回经用户逐笔确认，成交价 min(open, entry_ref)，时间精确到秒
（+08:00）；台账事件 t2_pending_fill 是其唯一盘中来源。实施走 P3 PR。

## 后验（P3 预留）

事件按 `monitor:` 前缀独立画像：T+1/3/5 收盘 ±2% 同式判定 **import**
`scripts/postmortem.py` 的 score/常量（禁复制实现——06「聚合分复算逐字同步」
同类教训）；风险提示类方向语义单独定义（提示后 N 日最大回撤避开 X% 即有效，
与信号 hit/miss 不同构），攒样本后经 RSI 评审钉死再并入 ledger 回路。
whipsaw 路径判据用日 K high/low（tick 缺口不影响判定）。

## 分期

| 期 | 内容 | 状态 |
| --- | --- | --- |
| P0 | SKILL.md 边界修订（本文件 + 判表 + 指针同步） | ✅ 0.0.15 |
| P1 | watch.py（universe/once/loop/close/verify-hk）+ rules.py + launchd 模板 + selftest | ✅ 0.0.15 |
| P2 | T1/T2 升级链、建议卡、意见保鲜门、record_fill --validate 常驻 | 预留 |
| P3 | record_fill 写回、sim SSOT 实施、review_events、HS300 MA60 自动取数 | 预留 |
| P4 | 机械降档判据进 scripts/（RSI-20261102-01 修法合流）、事件并入 ledger/postmortem、交易日历 | RSI 评审 |

## 回归门禁

`batch/monitor/rules.py --selftest`（36 checks）与 `watch.py --selftest`
（31 checks，含 launchd 模板回归钉与 position 轨 profile 过滤钉）（离线合成 fixture，零网络）是盯盘件的回归底线：改 `batch/monitor/` 后必须全绿；非
scripts/ 六件硬门禁成员（AGENTS.md 测试段非阻塞旁路门禁），P4 机械判据合流
scripts/ 后归六件 selftest 接管。判据只许收严（门禁只收严红线）。
