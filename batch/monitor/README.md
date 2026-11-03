# batch/monitor · 盯盘参考实现（P1）

口径以 [references/07-monitor.md](../../references/07-monitor.md) 为准（本目录是
参考实现）。边界：只提示不执行；本地告警、禁第三方推送通道；永不写
signals.json；盘中结论以收盘复核为准。

## 快速开始（sk = skill 根目录）

```bash
# 盯盘宇宙（脱敏派生：实盘持仓 + 模拟配置 + 观察票，价锚取 signals.key_levels）
uv run --no-project <sk>/batch/monitor/watch.py --print-universe

# 手动单轮（调试；--no-notify 不发系统通知）
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance <sk>/batch/monitor/watch.py --once --no-notify

# 常驻：盘前等待 → 盘中轮询（180s）→ 15:10/16:10 收盘复核 → 退出
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance <sk>/batch/monitor/watch.py --loop

# 收盘复核（幂等重渲 day-summary）/ 港股源验证（16:10 后）
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance <sk>/batch/monitor/watch.py --close
uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance <sk>/batch/monitor/watch.py --verify-hk

# 离线回归（零网络；改本目录后必须全绿）
uv run --no-project <sk>/batch/monitor/rules.py --selftest
uv run --no-project <sk>/batch/monitor/watch.py --selftest
```

产物落 `~/.vibe-stock/monitor/`（universe/state/ticks/events/day-summary/
logs——布局见 07「产物 SSOT 布局」）。

## launchd 常驻（P1 即上，用户裁定）

```bash
SK=<本仓 clone 绝对路径>
PL=~/Library/LaunchAgents/com.threefish.vibestock.monitor.plist
mkdir -p ~/.vibe-stock/monitor/logs          # launchd 不建日志父目录
sed -e "s|__UV_PATH__|$(command -v uv)|" -e "s|__SK_PATH__|$SK|" \
    -e "s|__HOME__|$HOME|g" "$SK/batch/monitor/com.threefish.vibestock.monitor.plist" > "$PL"
plutil -lint "$PL" && launchctl bootstrap gui/$(id -u) "$PL"
# 卸载：launchctl bootout gui/$(id -u) "$PL"
```

语义（详见 07「宿主形态」）：周一至周五 09:15 主槽拉起 `--loop`，交易时段
补拉槽（09:45–11:45、13:15–15:45 各每 30min）+ 16:15 盘后兜底槽——重启/开机/
被杀后最迟 30min 由下一槽补拉，收盘复核未收口则盘后槽补跑；KeepAlive 只认
信号级崩溃，watch.py 把未捕获异常转 SIGABRT 才能自愈；正常收口 exit 0 不重拉；
节假日误拉起由快照日期守卫停轮兜底。首次通知会触发 macOS 通知授权弹窗。
坑位：进程在跑时槽位被 launchd 直接丢弃（不并发不排队，2026-11-03 探针实测）；
当日彻底停盯盘须 `launchctl bootout`（只 kill 进程会在 ≤30min 内被下一槽拉起）。

已装旧模板（仅 09:15 单槽）升级到补拉槽版：先 `launchctl bootout gui/$(id -u)
"$PL"` 卸载旧作业，再按上方 sed 重渲染安装——bootout 会杀掉在跑的盯盘进程
（属预期；下一补拉槽才会拉起），盘中执行等于主动开一个盲窗，建议收盘后操作。

## 文件

| 文件 | 职责 |
| --- | --- |
| watch.py | 宇宙派生 / 价格面轮询（qt 批量 + r_hk） / 通知 / 收盘复核 / 港股源验证 / selftest |
| rules.py | 触发规则引擎（确定性纯函数：价位类规则 + 去抖/冷却/风暴闸/静默窗）+ selftest |
| com.threefish.vibestock.monitor.plist | LaunchAgent 模板（三类占位，按上方 sed 替换） |

坑位速查：裸 python3 缺 CA 证书会 SSL 失败，一律 uv 运行；launchd 不继承
shell PATH，模板用 uv 绝对路径；港股响应变量名 `v_r_hkXXXXX`、时间戳
`YYYY/MM/DD HH:MM:SS`（2026-11-02 实测）；科创 688 量纲为股；量能禁用跨源量
比；盯盘轮询不写 fetch_state 熔断账本（本地退避），仅 --close/--verify-hk
经全局锁写账本；selftest fixture 一律合成标的（红线：零真实持仓入仓）。
