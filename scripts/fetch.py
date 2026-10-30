#!/usr/bin/env python3
"""fetch.py · vibe-stock 证据取数层（蓝本：DSA data_provider 多源回退链）。

机制（与 references/01-evidence.md 同源）：
  - 市场分流：A 股链 em_quote(akshare→efinance 簇内次选)→qq(腾讯 qfq)→yfinance
    （腾讯源不含北交所 43/83/87/92 号段，显式拒绝落 yf .BJ 兜底）；港股链
    em_quote(akshare)→yfinance。
  - 回退链逐源尝试；任一成功即继续，状态标 available/fallback。
  - 熔断：按上游服务簇（非库名）计账，单簇连续 3 次失败停 300s（半开放行单次
    探测）；连接失败冷却 15s。状态持久化在 ~/.vibe-stock/fetch_state.json
    （真实时钟，秒）；旧库名键自然过期，不迁移不删除。
  - 八态标注：每个数据块独立标 available/missing/not_supported/fallback/stale/
    estimated/partial/fetch_failed——缺什么写什么，绝不静默消失。
  - 技术指标（MA/RSI/MACD/量比等）由日 K 纯标准库推导，不依赖三方库。
  - 快照模式：--snapshot-dir 提供预置 JSON（无网兜底），状态按文件声明或 estimated。

用法（联网全量）：
  uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
      scripts/fetch.py --stock 600519 --out evidence.json
  uv run --no-project --with 'akshare==1.20.*' --with efinance --with yfinance \
      scripts/fetch.py --stock hk00700 --out evidence.json
快照模式（零依赖）：
  uv run --no-project scripts/fetch.py --stock 600519 \
      --snapshot-dir evals/fixture/snapshot --out evidence.json
"""
import argparse
import datetime as dt
import json
import os
import re
import sys
import time

STATE_DIR = os.path.expanduser("~/.vibe-stock")
FETCH_STATE = os.path.join(STATE_DIR, "fetch_state.json")

BREAKER_FAILS, BREAKER_COOLDOWN = 3, 300
CONN_COOLDOWN = 15
BARS_WINDOW = 250
STALE_DAYS = {"quote": 1, "daily_bars": 5, "news": 3, "fundamentals": 120,
              "chip": 5, "moneyflow": 10, "notices": 1, "research": 30,
              "forecast": 1, "unlock": 1, "holder": 7, "market": 1,
              "industry": 1, "valuation": 1}  # 声明式口径（过期判级参照；
              # moneyflow 为自然日口径且被 fetch_moneyflow 新鲜度门消费）

# 上游服务簇（熔断/冷却计账粒度）：同簇共享故障域，键为取数源名、值为簇名。
# 簇判定规则：簇=主机/服务族粒度的故障域——同厂商不同服务族分簇（东财先例：
# push2* 行情死而 datacenter/np-anotice/reportapi 同期活，2026-10-28 实证），
# 同子域多端点合簇（vip.stock.finance.sina.com.cn 三源共担）。
CLUSTERS = {
    "ak-em": "em_quote",     # 东财行情簇 · akshare 日K
    "ef-em": "em_quote",     # 东财行情簇 · efinance 日K（簇内次选，同端点冗余）
    "em-chip": "em_quote",   # 东财行情簇 · 筹码（0.2.0 起仅作 derive 无股本时的回退位）
    "em-search": "em_search",  # 东财搜索簇 · 逐股新闻（独立于行情簇）
    "sina-fin": "sina",      # 新浪簇 · 财务指标（money.finance F10，链末）
    "ths-fin": "ths",        # 同花顺簇 · 财务摘要（回退）
    "qq-tx": "qq",           # 腾讯行情簇 · qfq 日K（web.ifzq.gtimg.cn 主机）
    "yf": "yf",              # Yahoo Finance
    # —— 0.2.0 扩容（六簇 → 十五簇）——
    "em-fin": "em_datacenter",  # 东财数据中心簇 · 财务主指标（datacenter*/securities/api）
    "em-notice": "em_notice",   # 东财公告簇 · np-anotice-stock 子域
    "cninfo-disc": "cninfo",    # 巨潮簇 · 公告权威回退（www.cninfo.com.cn）
    "em-report": "em_report",   # 东财研报簇 · reportapi 子域
    "dc-respredict": "em_datacenter",   # 评级共识+目标价（datacenter-web 直连）
    "dc-forecast": "em_datacenter",     # 业绩预告+披露日历（同簇两条 reportName）
    "dc-unlock": "em_datacenter",       # 解禁批次
    "sina-flow": "sina_flow",   # 新浪行情流量簇 · 资金流/个股资讯/申万归属（vip.stock 子域）
    "sina-news": "sina_flow",   # 新闻第三源（同子域，共担熔断）
    "sina-industry": "sina_flow",  # 申万行业归属（同子域）
    "qt-snap": "qt",            # 腾讯快照簇 · qt.gtimg.cn 主机（与 qq 日K 主机粒度分簇）
    "qq-news": "qq_news",       # 腾讯资讯簇 · proxy.finance.qq.com 主机
    "baidu-val": "baidu_gushitong",  # 百度股市通 · 历史估值序列
    "emweb-holder": "emweb",     # 东财 F10 簇 · 股东户数（emweb.securities 子域；
                                 #  RPT_HOLDERNUM_DET 数据集实测停在 2022，弃用）
}

CHAINS = {
    "cn": ["ak-em", "ef-em", "qq-tx", "yf"],
    "hk": ["ak-em", "yf"],
}


# ---------------------------------------------------------------- 市场与代码

def detect_market(symbol):
    s = symbol.strip().lower()
    if re.fullmatch(r"0\d{6}", s):  # 7 位前导零 A 股导出形态（沪/深均可能）剥一个 0 再分流
        s = s[1:]
    if re.fullmatch(r"(sh|sz|bj)?\d{6}", s):
        return "cn", re.sub(r"^(sh|sz|bj)", "", s)
    m = re.fullmatch(r"(?:hk)?(\d{4,5})(?:\.hk)?", s)
    if m:  # 港股统一 5 位（0700.HK→00700）：报告目录与信号身份只认一个形态
        return "hk", m.group(1).zfill(5)
    raise SystemExit("无法识别市场，示例：600519 / 0601888 / sz000001 / bj830799 / hk00700 / 0700.HK")


def cn_exchange(code):
    """A 股交易所分流（唯一判定处）：北交所 43/83/87/92 号段，沪 6/9(B 股
    900)/5，其余深。腾讯源与 Yahoo 后缀共用，勿各写一份前缀规则。"""
    if code.startswith(("43", "83", "87", "92")):
        return "bj"
    return "sh" if code.startswith(("6", "9", "5")) else "sz"


class NotSupportedSymbol(ValueError):
    """源不覆盖该标的（如腾讯源无北交所行情）——确定性能力边界拒绝，
    非源健康故障：链上按 not_supported 记轨迹，不计熔断、不连坐他股。"""


def yf_ticker(market, code):
    if market == "hk":
        return str(int(code)).zfill(4) + ".HK"  # Yahoo 港码 4 位：00700→0700.HK
    return code + {"bj": ".BJ", "sh": ".SS", "sz": ".SZ"}[cn_exchange(code)]


# ---------------------------------------------------------------- 熔断与冷却（持久化）

def load_fetch_state():
    try:
        with open(FETCH_STATE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"breakers": {}, "cooldowns": {}}


def save_fetch_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    with open(FETCH_STATE, "w", encoding="utf-8") as f:
        json.dump(st, f, ensure_ascii=False, indent=1)


def source_allowed(st, name, now):
    br = st["breakers"].get(name, {})
    if br.get("open_until", 0) > now:
        return False, "skipped_open"
    if st["cooldowns"].get(name, 0) > now:
        return False, "skipped_cooldown"
    return True, ""


def record(st, name, ok, err, now):
    br = st["breakers"].setdefault(name, {"fails": 0, "open_until": 0})
    if ok:
        br["fails"], br["open_until"] = 0, 0
        st["cooldowns"].pop(name, None)
        return
    if "connection" in err or "timeout" in err.lower():
        st["cooldowns"][name] = now + CONN_COOLDOWN
    br["fails"] += 1
    if br["fails"] >= BREAKER_FAILS:
        br["open_until"] = now + BREAKER_COOLDOWN


# ---------------------------------------------------------------- 各源取数（懒加载）

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"


def _http_text(url, headers=None, timeout=10):
    """直连取文本（urllib 标准库，零新增三方依赖）。GBK/UTF-8 自适应：
    qt.gtimg 与新浪 F10 页面为 GBK——先按 UTF-8 严格解码，失败回落 GBK。"""
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        raw = r.read()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        return raw.decode("gbk", "replace")


def _parse_qt_full(text):
    """qt.gtimg 全量快照解析（q=sh601888，~分隔 88 字段，GBK）。
    位序 2026-10-28 实测钉住（0 基）：1=名称 3=现价 4=昨收 5=今开 6=成交量(手)
    37=成交额(万) 38=换手率% 39=PE(TTM) 44=流通市值(亿) 45=总市值(亿) 46=PB
    56=股息字段(实测非 DPS，须与 64 互验) 64=股息率TTM(%) 72=流通股本 73=总股本。
    位序漂移防护（无条件全局规则：qt 无官方文档、字段序随版本漂移）：流通股本
    双路推导交叉校验——市值/现价 与 成交量(手→股)/换手率 相对误差 >2% 即弃
    股本字段（chip 自算随之降级）；DPS 与 股息率×现价/100 相对误差 >50% 或
    不可验即弃（600519 实测位 56=0.03 vs 真实 ~52，照信即自相矛盾落盘），
    绝不硬编码信任单一位序。"""
    body = text[text.index('"') + 1:text.rindex('"')]
    f = body.split("~")
    if len(f) < 65:
        # 最高消费位序 64；无效/不覆盖代码 qt 返回 none_match 短 body（无 ~
        # 字段序），按能力边界拒绝而非源故障（不计熔断，同北交所腾讯先例）
        raise NotSupportedSymbol("qt 快照字段数异常（%d）" % len(f))

    def num(i):
        try:
            return float(f[i])
        except Exception:
            return None

    price, float_mv, turnover, vol = num(3), num(44), num(38), num(6)
    float_shares = None
    if price and float_mv and turnover and vol:
        by_mv = float_mv * 1e8 / price
        by_vol = vol * 100 / (turnover / 100) if turnover > 0 else None
        if by_vol and abs(by_mv - by_vol) / by_mv <= 0.02:
            float_shares = round((by_mv + by_vol) / 2)
    dps, dy = num(56), num(64)
    if dps is not None:
        implied = dy * price / 100 if dy is not None and price is not None else None
        if implied is None or implied <= 0 or abs(dps - implied) > 0.5 * implied:
            dps = None  # 位 56 与股息率矛盾或不可验：弃字段不虚构
    return {"name": f[1], "price": price, "prev_close": num(4), "open": num(5),
            "volume_hand": vol, "amount_wan": num(37), "turnover_pct": turnover,
            "pe_ttm": num(39), "float_mv_yi": float_mv, "total_mv_yi": num(45),
            "pb": num(46), "dps_ttm": dps, "dividend_yield_ttm": dy,
            "float_shares": float_shares}


def _parse_qt_s(text):
    """qt.gtimg 紧凑快照解析（q=s_sh601888,...，GBK）：1=名称 3=点位 5=涨跌幅%。"""
    out = []
    for line in text.split(";"):
        line = line.strip()
        if '"' not in line:
            continue
        body = line[line.index('"') + 1:line.rindex('"')]
        f = body.split("~")
        try:
            out.append({"name": f[1], "price": float(f[3]),
                        "change_pct": float(f[5])})
        except (IndexError, ValueError):
            continue
    return out


def _qt_batch(market, code, st, now):
    """qt 簇取齐快照数据：个股全量（quote 叠加/估值/股本消费，仅 A 股——港股
    全量快照位序未验证，0.2.0 不取）+ 指数紧凑（market 消费）。
    qt 簇熔断/失败返回 (None, None)，各消费方自行降级。"""
    ok, why = source_allowed(st, CLUSTERS["qt-snap"], now)
    if not ok:
        return None, None
    try:
        full = None
        if market == "cn":
            sym = cn_exchange(code) + code
            try:
                full = _parse_qt_full(_http_text("https://qt.gtimg.cn/q=" + sym))
            except NotSupportedSymbol:
                # 标的不在 qt 覆盖：能力边界拒绝非源故障，不计熔断（quote 叠加/
                # 股本/估值消费方自行降级），指数快照照取
                pass
        idx = ("s_sh000001,s_sz399001,s_sz399006,s_sh000300,s_sh000688"
               if market == "cn" else "s_hkHSI,s_hkHSCEI")
        indices = _parse_qt_s(_http_text("https://qt.gtimg.cn/q=" + idx))
        record(st, CLUSTERS["qt-snap"], True, "", now)
        return full, indices
    except Exception as e:
        record(st, CLUSTERS["qt-snap"], False, str(e), now)
        return None, None


def _sina_json(text):
    """新浪 json_v2 容错解析：返回值可为裸键 JSON 数组（无引号键），标准
    json 失败时对键名补引号重试。"""
    try:
        return json.loads(text)
    except Exception:
        return json.loads(re.sub(r"([{,]\s*)([A-Za-z_]\w*)\s*:", r'\1"\2":', text))


def _daily_via_akshare(market, code):
    import akshare as ak  # noqa: 延迟导入，缺库不致命
    df = (ak.stock_zh_a_hist(symbol=code, period="daily", adjust="qfq")
          if market == "cn" else
          ak.stock_hk_hist(symbol=code.zfill(5), period="daily", adjust="qfq"))
    return [{"date": str(r["日期"]), "open": float(r["开盘"]), "high": float(r["最高"]),
             "low": float(r["最低"]), "close": float(r["收盘"]),
             "volume": float(r["成交量"])} for _, r in df.tail(BARS_WINDOW).iterrows()]


def _daily_via_efinance(market, code):
    import efinance as ef
    df = ef.stock.get_quote_history(code)
    key = {"日期": "date", "开盘": "open", "最高": "high", "最低": "low",
           "收盘": "close", "成交量": "volume"}
    rows = []
    for _, r in df.tail(BARS_WINDOW).iterrows():
        row = {}
        for cn, en in key.items():
            if cn in r:
                row[en] = str(r[cn]) if en == "date" else float(r[cn])
        rows.append(row)
    return rows


def _daily_via_tencent(market, code):
    """腾讯行情簇（proxy.finance.qq.com）：qfq 日K，与东财行情簇独立故障域。

    新浪 stock_zh_a_daily 实测不复权，禁入链（不复权数据不得混入 qfq 链）。
    volume 列要求 akshare ≥2025-10 版；单位为股（em 系源为手）——0.2.0 起
    被 derive_chip（绝对量换手）与 pack OHLCV 原值渲染消费，单位口径以
    01-evidence chip 规约句为 SSOT（判错方向会把换手率放大百倍）。
    """
    pfx = cn_exchange(code)
    if pfx == "bj":
        # 2026-10-28 实测：腾讯端点 bj 前缀被拒、误挂 sz 亦无数据——显式拒绝
        # （置于 import 之前，零依赖环境可测）；链上由 yf(.BJ，暂无数据则
        # 如实 fetch_failed) 兜底，不静默错挂。
        raise NotSupportedSymbol("北交所无腾讯行情数据")
    import akshare as ak  # noqa: 延迟导入，缺库不致命
    start = (dt.date.today() - dt.timedelta(days=600)).strftime("%Y%m%d")
    end = dt.date.today().strftime("%Y%m%d")
    df = ak.stock_zh_a_hist_tx(symbol=pfx + code, start_date=start,
                               end_date=end, adjust="qfq")
    return [{"date": str(r["date"]), "open": float(r["open"]), "high": float(r["high"]),
             "low": float(r["low"]), "close": float(r["close"]),
             "volume": float(r["volume"])} for _, r in df.tail(BARS_WINDOW).iterrows()]


def _daily_via_yfinance(market, code):
    import yfinance
    tk = yfinance.Ticker(yf_ticker(market, code))
    df = tk.history(period="1y")
    return [{"date": str(i.date()), "open": float(r.Open), "high": float(r.High),
             "low": float(r.Low), "close": float(r.Close),
             "volume": float(r.Volume)} for i, r in df.tail(BARS_WINDOW).iterrows()]


DAILY_FETCHERS = {"ak-em": _daily_via_akshare,
                  "ef-em": _daily_via_efinance,
                  "qq-tx": _daily_via_tencent,
                  "yf": _daily_via_yfinance}


def fetch_daily_bars(market, code, st, now):
    """回退链取日 K。返回 (rows, state, source, tried)。全链失败 → fetch_failed。"""
    tried = []
    for name in CHAINS[market]:
        cluster = CLUSTERS[name]
        ok, why = source_allowed(st, cluster, now)
        if not ok:
            tried.append((name, why))
            continue
        try:
            rows = DAILY_FETCHERS[name](market, code)
            if not rows:
                raise ValueError("empty bars")
            record(st, cluster, True, "", now)
            # 备选源取到即 fallback（01-evidence 八态口径）：先行源被熔断/冷却
            # 跳过或失败，都如实压低状态，不因 skip 不计败而虚标 available。
            state = "available" if not tried else "fallback"
            return rows, state, name, tried
        except ImportError as e:
            tried.append((name, "import_missing"))  # 缺库不记熔断（环境问题非源问题）
        except NotSupportedSymbol:
            # 源不覆盖该标的不记熔断（标的问题非源健康问题，重试永不成功）
            tried.append((name, "not_supported"))
        except Exception as e:
            record(st, cluster, False, str(e), now)
            tried.append((name, "fail: %s" % type(e).__name__))
    return [], "fetch_failed", "", tried


# 派生块（从日 K 推导，零三方依赖）
def derive_quote(bars):
    last = bars[-1]
    prev = bars[-2]["close"] if len(bars) > 1 else last["close"]
    return {"price": last["close"], "prev_close": prev,
            "change_pct": round((last["close"] / prev - 1) * 100, 2),
            "date": last["date"]}


def _ma(closes, n):
    return round(sum(closes[-n:]) / n, 3) if len(closes) >= n else None


def _rsi(closes, n=14):
    if len(closes) < n + 1:
        return None
    gains = losses = 0.0
    for a, b in zip(closes[-(n + 1):-1], closes[-n:]):
        d = b - a
        gains, losses = gains + max(d, 0), losses + max(-d, 0)
    if gains + losses == 0:
        return 50.0
    return round(100 * gains / (gains + losses), 2)


def _macd(closes, fast=12, slow=26, signal=9):
    if len(closes) < slow + signal:
        return None
    dif = [f - s for f, s in zip(_ema_series(closes, fast), _ema_series(closes, slow))]
    dea = _ema_series(dif, signal)
    hist = [(d - e) * 2 for d, e in zip(dif, dea)]
    return {"dif": round(dif[-1], 3), "dea": round(dea[-1], 3),
            "macd": round(hist[-1], 3), "hist_prev": round(hist[-2], 3),
            "hist_rising": bool(hist[-1] > hist[-2])}  # 柱体放大判据（bull_trend）


def _ema_series(vals, n):
    out, k = [], 2 / (n + 1)
    e = vals[0]
    for v in vals:
        e = v * k + e * (1 - k)
        out.append(e)
    return out


def _bar_pattern(bar):
    """单根 K 线形态摘要：阴阳/实体占比/上下影线占比（high==low 一字板全 0）。"""
    o, c, hi, lo = bar["open"], bar["close"], bar["high"], bar["low"]
    span = hi - lo
    if span <= 0:
        return {"yang": bool(c >= o), "body_pct": 0.0, "lower_shadow_pct": 0.0,
                "upper_shadow_pct": 0.0}
    return {"yang": bool(c >= o),
            "body_pct": round(abs(c - o) / span * 100, 1),
            "lower_shadow_pct": round((min(o, c) - lo) / span * 100, 1),
            "upper_shadow_pct": round((hi - max(o, c)) / span * 100, 1)}


def derive_technical(bars):
    closes = [b["close"] for b in bars]
    vols = [b["volume"] for b in bars]
    hi52 = max(b["high"] for b in bars)
    lo52 = min(b["low"] for b in bars)
    prev19 = closes[-20:-1] if len(closes) >= 20 else closes[:-1]
    # 60 日箱体（不足 20 根不出，pos_pct=现价在箱体区间位置 0~100）
    box = None
    if len(bars) >= 20:
        w = bars[-60:]
        bhi, blo = max(b["high"] for b in w), min(b["low"] for b in w)
        if bhi > blo:
            box = {"hi": round(bhi, 3), "lo": round(blo, 3),
                   "width_pct": round((bhi / blo - 1) * 100, 2),
                   "pos_pct": round((closes[-1] - blo) / (bhi - blo) * 100, 1)}
    # 近 10 日量比序列（当日量/前 5 日均量）：缩量/放量演化可见（box/bottom 判据）
    vol_series = None
    if len(vols) >= 15:
        vol_series = [round(vols[i] / (sum(vols[i - 5:i]) / 5 + 1e-9), 2)
                      for i in range(len(vols) - 10, len(vols))]
    up_days = 0
    for a, b in zip(reversed(closes[:-1]), reversed(closes[1:])):
        if b > a:
            up_days += 1
        else:
            break
    return {
        "ma5": _ma(closes, 5), "ma10": _ma(closes, 10), "ma20": _ma(closes, 20),
        "ma60": _ma(closes, 60), "rsi14": _rsi(closes), "macd": _macd(closes),
        "vol_ratio_5": round(vols[-1] / (sum(vols[-6:-1]) / 5 + 1e-9), 2),
        "pct_from_52w_high": round((closes[-1] / hi52 - 1) * 100, 2),
        "pct_from_52w_low": round((closes[-1] / lo52 - 1) * 100, 2),
        "bars_count": len(bars),
        "new_high_20d": bool(prev19 and closes[-1] >= max(prev19)),
        "new_low_20d": bool(prev19 and closes[-1] <= min(prev19)),
        "consecutive_up_days": up_days,
        "box_60d": box, "vol_series_10": vol_series,
        "last_bar_pattern": _bar_pattern(bars[-1]),
    }


# ---------------------------------------------------------------- 新闻（三簇链 + 港股解锁）

def _news_via_em(code):
    """东财搜索簇（主源，经 akshare）：标题+内容摘要。"""
    import akshare as ak
    df = ak.stock_news_em(symbol=code)
    items = [{"title": str(r["新闻标题"]), "content": str(r["新闻内容"])[:200],
              "time": str(r["发布时间"])} for _, r in df.head(10).iterrows()]
    if not items:
        raise ValueError("empty news")
    return items


def _news_via_qq(market, code):
    """腾讯资讯簇（直连 proxy.finance.qq.com，A+港通吃——港股唯一源）：
    data.data[] 含 time/title/src/summary；混有自媒体条目，靠 src 字段如实透出。"""
    sym = ("hk" + code if market == "hk"
           else cn_exchange(code) + code)
    text = _http_text("https://proxy.finance.qq.com/ifzqgtimg/appstock/"
                      "news/info/search?page=1&symbol=%s&n=20&type=2" % sym)
    arr = (json.loads(text).get("data") or {}).get("data") or []
    items = [{"title": str(a.get("title", "")), "content": str(
        a.get("summary", ""))[:150], "time": str(a.get("time", "")),
        "src": str(a.get("src", ""))} for a in arr if a.get("title")]
    if not items:
        # 标的级无覆盖（小市值/次新常态）非源故障——能力边界拒绝不计熔断，
        # 不打死港股唯一 news 源（qq_news 单源簇）
        raise NotSupportedSymbol("qq 无该标的新闻覆盖")
    return items[:10]


def _news_via_sina(code):
    """新浪流量簇（直连 F10 个股资讯页，GB2312 HTML，标题级末位回退）：
    无内容摘要无来源名，仅 A 股；页面含弱相关条目，如实进包由意见层甄别。"""
    sym = cn_exchange(code) + code
    text = _http_text("https://vip.stock.finance.sina.com.cn/corp/go.php/"
                      "vCB_AllNewsStock/symbol/%s.phtml" % sym)
    rows = re.findall(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*<a[^>]*href=\"([^\"]+)\"[^>]*>([^<]+)</a>",
        text)
    items = [{"title": t.strip(), "content": "", "time": tm, "url": u}
             for tm, u, t in rows]
    if not items:
        raise NotSupportedSymbol("sina 资讯页无该标的条目")  # 同 qq：不计熔断
    return items[:10]


NEWS_FETCHERS = {"em-search": _news_via_em, "qq-news": _news_via_qq,
                 "sina-news": _news_via_sina}
NEWS_CHAINS = {"cn": ["em-search", "qq-news", "sina-news"], "hk": ["qq-news"]}


def fetch_news(market, code, st, now):
    """新闻块：A 股三簇链 em_search→qq_news→sina_flow（异厂商互备）；
    港股 qq-news 单源（0.2.0 解除 not_supported）。"""
    tried = []
    for name in NEWS_CHAINS[market]:
        cluster = CLUSTERS[name]
        ok, why = source_allowed(st, cluster, now)
        if not ok:
            tried.append((name, why))
            continue
        try:
            items = (NEWS_FETCHERS[name](code) if name != "qq-news"
                     else NEWS_FETCHERS[name](market, code))
            record(st, cluster, True, "", now)
            state = "available" if not tried else "fallback"
            return {"state": state, "source": name, "items": items, "tried": tried}
        except NotSupportedSymbol:
            # 标的级无覆盖：能力边界拒绝非源故障，不计熔断不连坐他股
            # （同 qt none_match；终态仍如实 fetch_failed——news 为有权重核心
            # 块，「空=available」属质量分语义变更，0.3.0 级决策不在此改）
            tried.append((name, "not_supported"))
        except ImportError:
            tried.append((name, "import_missing"))  # 缺库不记熔断（环境问题非源问题）
        except Exception as e:
            record(st, cluster, False, str(e), now)
            tried.append((name, "fail: %s" % type(e).__name__))
    return {"state": "fetch_failed", "source": "", "note": "all_failed", "tried": tried}


def _fund_via_em(code):
    """东财数据中心簇（0.2.0 链首，经 akshare）：一表全含——四概念键对齐既有
    口径，另带扩展键（毛利率/净利率/ROIC/归母净利同比，近 4 报告期）。
    列名为接口 raw 英文列（REPORT_DATE/EPSJB/ROEJQ/…），最新期在前。
    SECUCODE 后缀按 cn_exchange 唯一判定处映射（bj→.BJ/sh→.SH/sz→.SZ）。"""
    import akshare as ak
    suf = {"sh": ".SH", "sz": ".SZ", "bj": ".BJ"}[cn_exchange(code)]
    df = ak.stock_financial_analysis_indicator_em(symbol=code + suf,
                                                  indicator="按报告期")
    out = {}
    for _, row in df.head(4).iterrows():
        period = str(row.get("REPORT_DATE", ""))[:10]
        out[period] = {
            "报告期": period,
            "每股收益(元)": _num(row.get("EPSJB")),
            "净资产收益率(%)": _num(row.get("ROEJQ")),
            "主营业务收入增长率(%)": _num(row.get("TOTALOPERATEREVETZ")),
            "资产负债率(%)": _num(row.get("ZCFZL")),
            "毛利率(%)": _num(row.get("XSMLL")),
            "净利率(%)": _num(row.get("XSJLL")),
            "ROIC(%)": _num(row.get("ROIC")),
            "归母净利润同比(%)": _num(row.get("PARENTNETPROFITTZ")),
            "归母净利润(亿元)": (lambda v: None if v is None else round(v / 1e8, 2))(
                _num(row.get("PARENTNETPROFIT")))}
    return out  # {报告期: 指标 dict}，近 4 期；消费方取最新期为 data 主值


def _fund_via_sina(code):
    """新浪簇财务指标（链末交叉源）：值为 float，概念键四项。
    键名修正（原「每股收益(元)」接口列集不存在恒 None，实为「摊薄每股收益(元)」）；
    毛利率 2025 起新浪停更恒 NaN，此源禁取毛利率。"""
    import akshare as ak
    df = ak.stock_financial_analysis_indicator(symbol=code, start_year="2024")
    row = df.iloc[-1] if len(df) else {}
    keys = ["净资产收益率(%)", "摊薄每股收益(元)", "主营业务收入增长率(%)",
            "资产负债率(%)"]
    return {("每股收益(元)" if k == "摊薄每股收益(元)" else k):
            (None if k not in row else _num(row[k])) for k in keys}


def _fund_via_ths(code):
    """同花顺簇财务摘要（回退）：值为带 %/亿 的字符串，概念映射到与新浪源同名键。"""
    import akshare as ak
    df = ak.stock_financial_abstract_ths(symbol=code, indicator="按报告期")
    row = df.iloc[-1] if len(df) else {}
    mapping = {"净资产收益率(%)": "净资产收益率", "每股收益(元)": "基本每股收益",
               "主营业务收入增长率(%)": "营业总收入同比增长率",
               "资产负债率(%)": "资产负债率", "毛利率(%)": "销售毛利率"}
    return {k: (None if c not in row else _num(row[c])) for k, c in mapping.items()}


FUNDAMENTALS_FETCHERS = {"em-fin": _fund_via_em, "sina-fin": _fund_via_sina,
                         "ths-fin": _fund_via_ths}


def fetch_fundamentals(market, code, st, now):
    """财务指标：em_datacenter → sina → ths（簇级计账，任一簇熔断不牵连另一簇）。
    em-fin 返回 {报告期: 指标}，主值取最新期、近 4 期入 history（pack 渲染用）。"""
    if market == "hk":
        return {"state": "not_supported", "source": "",
                "note": "港股财务指标 v1 未接入"}
    tried = []
    for name in FUNDAMENTALS_FETCHERS:
        cluster = CLUSTERS[name]
        ok, why = source_allowed(st, cluster, now)
        if not ok:
            tried.append((name, why))
            continue
        try:
            data = FUNDAMENTALS_FETCHERS[name](code)
            history = None
            if data and all(isinstance(v, dict) for v in data.values()):
                history, data = data, data[max(data)]
            # NaN（"--" 占位）归一 None：pack 渲染与 history 均不落 NaN 字面量
            data = _fin_dict(data)
            if history:
                history = {p: _fin_dict(h) for p, h in history.items()}
            # v == v 滤 NaN：_num("--")→nan 非 None，全占位不算成功（勿重置簇
            # 计数）。只验数值（em-fin 各期含「报告期」字符串键，any() 对字符串
            # 恒 True 会放行全空指标）
            if not any(isinstance(v, float) and v == v for v in data.values()):
                raise ValueError("empty fundamentals")
            record(st, cluster, True, "", now)
            state = "available" if not tried else "fallback"
            blk = {"state": state, "source": name, "data": data, "tried": tried}
            if history:
                blk["history"] = history
            return blk
        except ImportError:
            tried.append((name, "import_missing"))  # 缺库不记熔断（环境问题非源问题）
        except Exception as e:
            record(st, cluster, False, str(e), now)
            tried.append((name, "fail: %s" % type(e).__name__))
    return {"state": "fetch_failed", "source": "", "note": "all_failed", "tried": tried}


def _num(v):
    try:
        return float(str(v).replace(",", "").replace("%", "").replace("--", "nan"))
    except Exception:
        return None


def _fnum(v):
    """_num 有限值版：NaN（东财/新浪 "--" 占位经 _num 的常态）归 None——
    缺数不虚构，也不让 nan 字面量流进下游换算与 pack。"""
    x = _num(v)
    return None if isinstance(x, float) and x != x else x


def _fin_dict(d):
    """dict 值域 NaN→None（同 _fnum 语义的整表归一）。"""
    return {k: (None if isinstance(v, float) and v != v else v)
            for k, v in d.items()}


def derive_chip(bars, float_shares, bars_source=""):
    """筹码分布本地自算（CYQ 三角分布换手衰减，与 akshare stock_cyq_em 同算法，
    输出列名与官方接口全同）。状态由调用方标 estimated。
    坑位：①volume 单位陷阱——ak-em/ef-em 系源为手（×100），qq-tx/yf 为股，
    按 bars_source 判定归一；②历史换手率以当前流通股本回溯，增发/解禁/回购期
    误差放大；③一字板（high==low）单点全量堆积。"""
    if not bars or not float_shares:
        return None
    # volume 单位陷阱：ak-em/ef-em 为手（×100），qq-tx/yf 为股（不换算）——
    # 判错方向会把换手率放大百倍、每日全换手冲掉全部历史筹码
    unit = 100 if any(s in (bars_source or "") for s in ("ak-em", "ef-em")) else 1
    dist = {}
    for bar in bars:  # 全窗口参与（250 根）：裁窗会切掉高位筹码档使 90 成本区间失真
        h = min(bar["volume"] * unit / float_shares, 1.0)
        lo, hi = bar["low"], bar["high"]
        avg = (bar["open"] + bar["high"] + bar["low"] + bar["close"]) / 4
        for k in dist:  # 旧筹码按当日换手率衰减
            dist[k] *= (1 - h)
        if hi <= lo:  # 一字板：单价位全量
            key = round(avg, 2)
            dist[key] = dist.get(key, 0) + h
        else:  # 当日筹码以均价为顶点摊入 [low, high] 三角分布
            steps = max(2, int(round((hi - lo) / 0.01)))
            peak = max(avg - lo, hi - avg) or 1e-9
            ws = []
            for i in range(steps):
                p = lo + (hi - lo) * (i + 0.5) / steps
                w = max(0.0, 1 - abs(p - avg) / peak)
                if w > 0:
                    ws.append((round(p, 2), w))
            wsum = sum(w for _, w in ws)
            if wsum > 0:
                for p, w in ws:
                    dist[p] = dist.get(p, 0) + h * w / wsum
    total = sum(dist.values())
    if total <= 0:
        return None
    for k in [k for k, v in dist.items() if v < total * 1e-7]:  # 剪趋零档
        del dist[k]
    prices = sorted(dist)
    close = bars[-1]["close"]
    profit = sum(w for p, w in dist.items() if p <= close) / total
    avg_cost = sum(p * w for p, w in dist.items()) / total

    def band(frac):  # frac 成本区间（对称去尾）+ 集中度=(高-低)/(高+低)
        tail = (1 - frac) / 2 * total
        acc, lo_p = 0.0, prices[0]
        for p in prices:
            acc += dist[p]
            if acc >= tail:
                lo_p = p
                break
        acc, hi_p = 0.0, prices[-1]
        for p in reversed(prices):
            acc += dist[p]
            if acc >= tail:
                hi_p = p
                break
        return lo_p, hi_p

    lo90, hi90 = band(0.9)
    lo70, hi70 = band(0.7)
    return {"获利比例": round(profit, 4), "平均成本": round(avg_cost, 2),
            "90成本-低": round(lo90, 2), "90成本-高": round(hi90, 2),
            "90集中度": round((hi90 - lo90) / (hi90 + lo90), 4),
            "70成本-低": round(lo70, 2), "70成本-高": round(hi70, 2),
            "70集中度": round((hi70 - lo70) / (hi70 + lo70), 4)}


def fetch_chip(market, code, st, now, bars=None, float_shares=None,
               bars_source=""):
    """筹码分布（0.2.0 derive 优先）：本地自算（日K+qt 流通股本）→ estimated；
    无输入或自算失败时探 em-chip 官方接口（em_quote 簇复活位）→ available；
    港股 not_supported（能力差异摆到明面上）。"""
    if market == "hk":
        return {"state": "not_supported", "source": "",
                "note": "筹码数据仅 A 股"}
    if bars and float_shares:
        data = derive_chip(bars, float_shares, bars_source)
        if data:
            return {"state": "estimated", "source": "derived:qt", "data": data,
                    "note": "本地自算（CYQ 三角分布换手衰减），历史换手按当前"
                            "流通股本回溯"}
    cluster = CLUSTERS["em-chip"]
    ok, why = source_allowed(st, cluster, now)
    if not ok:
        return {"state": "fetch_failed", "source": "em-chip", "note": why}
    try:
        import akshare as ak
        df = ak.stock_cyq_em(symbol=code, adjust="qfq")
        row = df.iloc[-1] if len(df) else {}
        keys = ["获利比例", "平均成本", "90成本-低", "90成本-高"]
        data = {k: (None if k not in row else _fnum(row[k])) for k in keys}
        # 与 fundamentals 同式守卫：全空/NaN 占位不算成功，不重置簇计数
        if not any(v is not None and v == v for v in data.values()):
            raise ValueError("empty chip")
        record(st, cluster, True, "", now)
        return {"state": "available", "source": "em-chip", "data": data}
    except ImportError:
        return {"state": "fetch_failed", "source": "em-chip", "note": "import_missing"}
    except Exception as e:
        record(st, cluster, False, str(e), now)
        return {"state": "fetch_failed", "source": "em-chip",
                "note": type(e).__name__}


# ---------------------------------------------------------------- 扩展证据块（0.2.0 · 九块零权重）

_DC = "https://datacenter-web.eastmoney.com/api/data/v1/get"


def _dc_rows(report_name, code, st, now, src_key, page_size=20, sort=""):
    """东财数据中心直连通用壳：reportName+SECURITY_CODE 过滤，返回 rows 或抛错。"""
    cluster = CLUSTERS[src_key]
    ok, why = source_allowed(st, cluster, now)
    if not ok:
        raise _Skip(why)
    import urllib.parse
    url = ("%s?reportName=%s&columns=ALL&filter=%s&pageNumber=1&pageSize=%d%s"
           % (_DC, report_name, urllib.parse.quote('(SECURITY_CODE="%s")' % code),
              page_size, sort))
    data = json.loads(_http_text(url))
    if data.get("success") is False:
        # 零行结果东财返回 success=false+「返回数据为空」(code 9201)——空是
        # 标的级事实非源故障（forecast/unlock「空=available」语义）：计成功
        # 不熔断；其余 success=false（真 API 错）照旧抛错由调用方记败。
        if "返回数据为空" in str(data.get("message", "")) or data.get("code") == 9201:
            record(st, cluster, True, "", now)
            return []
        raise ValueError("dc fail: %s" % data.get("message", ""))
    rows = (data.get("result") or {}).get("data") or []
    record(st, cluster, True, "", now)
    return rows


class _Skip(Exception):
    """簇熔断/冷却跳过（不计失败，透传 skip 原因）。"""


def _ext_fail(name, e):
    if isinstance(e, _Skip):
        return {"state": "fetch_failed", "source": name, "note": str(e)}
    return {"state": "fetch_failed", "source": name,
            "note": type(e).__name__}


def fetch_moneyflow(market, code, st, now):
    """扩展块·资金流：新浪流量簇直连 60 日四档净额（主力净额=r0_net+r1_net 自算，
    四档和=netamount 数值自洽校验防口径漂移）。东财族绑死 em_quote 死簇不入链、
    同花顺全市场扫描 105 页 28s 不入链（调用预算红线）。港 not_supported。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    try:
        cluster = CLUSTERS["sina-flow"]
        ok, why = source_allowed(st, cluster, now)
        if not ok:
            raise _Skip(why)
        sym = cn_exchange(code) + code
        text = _http_text(
            "https://vip.stock.finance.sina.com.cn/quotes_service/api/"
            "json_v2.php/MoneyFlow.ssl_qsfx_lscjfb?page=1&num=60&sort=opendate"
            "&asc=0&daima=" + sym)
        rows = _sina_json(text)
        days = []
        for r in rows:
            try:
                net = _fnum(r.get("netamount"))
                parts = sum(_fnum(r.get(k)) or 0 for k in
                            ("r0_net", "r1_net", "r2_net", "r3_net"))
                if net is None or abs(parts - net) / max(abs(net), 1) > 0.01:
                    raise ValueError("netamount mismatch")
                days.append({
                    "date": r["opendate"], "close": _fnum(r.get("trade")),
                    "change_pct": round((_fnum(r.get("changeratio")) or 0) * 100, 2),
                    "turnover_pct": round((_fnum(r.get("turnover")) or 0) / 100, 2),
                    "main_net_yi": round(((_fnum(r.get("r0_net")) or 0)
                                          + (_fnum(r.get("r1_net")) or 0)) / 1e8, 4),
                    "super_net_yi": round((_fnum(r.get("r0_net")) or 0) / 1e8, 4),
                    "big_net_yi": round((_fnum(r.get("r1_net")) or 0) / 1e8, 4)})
            except KeyError:
                continue
        if not days:
            raise ValueError("empty moneyflow")
        record(st, cluster, True, "", now)
        # 新鲜度门（无条件全局规则：不虚构数据）：新浪对北交所/长期停牌标的
        # 返回陈旧或全零尾部序列（bj830799 实测全零止于 2025-05-07、
        # bj832566 真值止于 2025-09-30），不得当 available 的「今日」事实进包。
        # 阈值单一事实源＝STALE_DAYS["moneyflow"]（10 自然日容纳周末+长假，
        # 勿在调用点另写魔数）；全零序列=源对该标的无覆盖。
        newest = days[0]["date"]
        all_zero = all(abs(d["main_net_yi"]) < 1e-9 for d in days)
        try:
            age = (dt.date.today() - dt.date.fromisoformat(newest)).days
        except ValueError:
            age = None
        if all_zero:
            return {"state": "not_supported", "source": "sina-flow",
                    "note": "新浪资金流对该标的仅全零序列，无有效覆盖，不虚构数据"}
        if age is None or age > STALE_DAYS["moneyflow"]:
            return {"state": "stale", "source": "sina-flow",
                    "note": "资金流序列止于 %s（距今 %s 天），不按最新事实采信"
                            % (newest, "未知" if age is None else age)}
        nets = [d["main_net_yi"] for d in days]
        streak = 0
        for n in nets:
            if abs(n) < 1e-9:
                break
            if streak == 0 or (n > 0) == (nets[0] > 0):
                streak += 1
            else:
                break
        summary = {"main_net_yi": nets[0],
                   "main_net_3d_yi": round(sum(nets[:3]), 4),
                   "main_net_5d_yi": round(sum(nets[:5]), 4),
                   "main_net_10d_yi": round(sum(nets[:10]), 4),
                   "main_streak_days": streak,
                   "streak_direction": ("inflow" if nets[0] > 0 else "outflow")}
        return {"state": "available", "source": "sina-flow", "days": days,
                "summary": summary, "note": "主力净额=超大单+大单（新浪口径）"}
    except Exception as e:
        if not isinstance(e, _Skip):
            record(st, CLUSTERS["sina-flow"], False, str(e), now)
        return _ext_fail("sina-flow", e)


def _notices_via_em(code):
    import akshare as ak
    end = dt.date.today()
    begin = end - dt.timedelta(days=90)
    df = ak.stock_individual_notice_report(
        security=code, symbol="全部",
        begin_date=begin.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
    return [{"date": str(r["公告日期"])[:10], "type": str(r["公告类型"]),
             "title": str(r["公告标题"]), "url": str(r["网址"])}
            for _, r in df.head(30).iterrows()]


def _notices_via_cninfo(code):
    import akshare as ak
    end = dt.date.today()
    begin = end - dt.timedelta(days=90)
    df = ak.stock_zh_a_disclosure_report_cninfo(
        symbol=code, market="沪深京", keyword="", category="",
        start_date=begin.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
    return [{"date": str(r["公告时间"])[:10], "type": "巨潮披露",
             "title": str(r["公告标题"]), "url": str(r["公告链接"])}
            for _, r in df.head(30).iterrows()]


def fetch_notices(market, code, st, now):
    """扩展块·公告：em_notice 簇（8 类枚举）→ cninfo 簇（监管权威回退），
    近 90 天 ≤30 条；双源覆盖面不同（东财含 H 股镜像），条数差异属正常。
    空结果语义（与 forecast/research 同钉）：90 天无公告是标的级事实非源故障
    ——单源空不记熔断、换下一源交叉验证，双源皆空=available 空列表；任一源
    硬失败则按回退链语义如实 fetch_failed（无法确认「无公告」事实）。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    tried = []
    emptied = []
    for name, fn in (("em-notice", _notices_via_em),
                     ("cninfo-disc", _notices_via_cninfo)):
        cluster = CLUSTERS[name]
        try:
            ok, why = source_allowed(st, cluster, now)
            if not ok:
                raise _Skip(why)
            items = fn(code)
            if not items:
                # 空不记败不计熔断，换源交叉；tried 逐源穷尽（同 news/
                # fundamentals 口径）——「主源空」是排障关键线索（如上游
                # 接口列名变更恒空），不得从审计轨迹中丢失
                emptied.append(name)
                tried.append((name, "empty"))
                continue
            record(st, cluster, True, "", now)
            state = "available" if not tried else "fallback"
            return {"state": state, "source": name, "items": items, "tried": tried}
        except _Skip as e:
            tried.append((name, str(e)))
        except ImportError:
            tried.append((name, "import_missing"))
        except Exception as e:
            record(st, cluster, False, str(e), now)
            tried.append((name, "fail: %s" % type(e).__name__))
    if len(emptied) == 2:  # 双源皆空=事实：无公告非缺失（同 research 双空语义）
        return {"state": "available", "source": "+".join(emptied), "items": [],
                "note": "近 90 天无公告（双源皆空是事实，非数据缺失）",
                "tried": tried}
    return {"state": "fetch_failed", "source": "", "note": "all_failed", "tried": tried}


def _research_list(code):
    import akshare as ak
    df = ak.stock_research_report_em(symbol=code)  # 全历史最新在前
    cutoff = (dt.date.today() - dt.timedelta(days=180)).isoformat()
    out = []
    for _, r in df.iterrows():
        d = str(r.get("日期", ""))[:10]
        if d >= cutoff:
            out.append({"date": d, "org": str(r.get("机构", "")),
                        "rating": str(r.get("东财评级", "")),
                        "title": str(r.get("报告名称", ""))})
        if len(out) >= 15:
            break
    return out


def fetch_research(market, code, st, now):
    """扩展块·研报与评级：em_report 簇逐篇列表 + datacenter 直连评级共识与
    机构目标价（RPT_WEB_RESPREDICT——akshare 封装丢弃目标价列，必须直连）。
    单边失败标 partial 不谎报全成。港 not_supported。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    blk = {"state": "fetch_failed", "source": "", "note": "all_failed"}
    reports, consensus, fails = None, None, []
    try:
        ok, why = source_allowed(st, CLUSTERS["em-report"], now)
        if not ok:
            raise _Skip(why)
        # 空列表=近 180 天无机构覆盖（标的级事实非源故障，不 raise 不计熔断
        # ——与 consensus 零行同语义；小盘/次新常见形态）
        reports = _research_list(code)
        record(st, CLUSTERS["em-report"], True, "", now)
    except _Skip as e:
        fails.append("em-report:%s" % e)
    except ImportError:
        fails.append("em-report:import_missing")
    except Exception as e:
        record(st, CLUSTERS["em-report"], False, str(e), now)
        fails.append("em-report:%s" % type(e).__name__)
    try:
        rows = _dc_rows("RPT_WEB_RESPREDICT", code, st, now, "dc-respredict")
        if rows:  # 零行=无机构覆盖（事实非失败，_dc_rows 已按空语义计成功）
            r = rows[0]
            consensus = {"org_num": r.get("RATING_ORG_NUM"),
                         "buy": r.get("RATING_BUY_NUM"), "add": r.get("RATING_ADD_NUM"),
                         "neutral": r.get("RATING_NEUTRAL_NUM"),
                         "reduce": r.get("RATING_REDUCE_NUM"),
                         "target_min": r.get("DEC_AIMPRICEMIN"),
                         "target_max": r.get("DEC_AIMPRICEMAX")}
    except Exception as e:
        if not isinstance(e, _Skip):  # 计账对称：真实失败记败（同簇其余调用点皆然）
            record(st, CLUSTERS["dc-respredict"], False, str(e), now)
        fails.append("dc-respredict:%s" % (str(e) if isinstance(e, _Skip)
                                           else type(e).__name__))
    if reports or consensus:
        blk = {"state": "partial" if fails else "available",
               "source": "em-report+dc-respredict",
               "reports": (reports or [])[:15], "consensus": consensus}
        if fails:
            blk["note"] = "部分失败：%s" % ";".join(fails)
    elif not fails:
        # 双空=无机构覆盖（事实非缺失），与 forecast 空=available 同语义
        blk = {"state": "available", "source": "em-report+dc-respredict",
               "reports": [], "consensus": None,
               "note": "近 180 天无研报覆盖与评级共识（无覆盖是事实，非数据缺失）"}
    return blk


def fetch_forecast(market, code, st, now):
    """扩展块·业绩预告+披露日历（datacenter 直连两条 reportName）。
    语义（无条件全局规则）：空结果=available 且字段 null——「无预告」是事实
    不是失败；只有网络/解析失败才 fetch_failed。港 not_supported。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    try:
        # NOTICE_DATE 降序（无条件全局规则）：该数据集默认升序且只取第 1 页——
        # 不带 sort 时历史预告 ≥20 条的股票最新预告落在后页读不到、窗口内多条
        # 时取到最旧一条（601127/600893 实测），必须显式降序取最新在前。
        rows = _dc_rows("RPT_PUBLIC_OP_NEWPREDICT", code, st, now, "dc-forecast",
                        sort="&sortColumns=NOTICE_DATE&sortTypes=-1")
        pf = None
        # 预告时效（无条件全局规则）：陈旧预告（>18 个月）视同无预告——大盘蓝筹
        # 常年不发预告，残留在库的多年前预告进包只有误导。PREDICT_AMT 单位万元。
        cutoff = (dt.date.today() - dt.timedelta(days=550)).isoformat()
        for r in rows or []:
            nd = str(r.get("NOTICE_DATE", ""))[:10]
            if nd >= cutoff:
                pf = {"report_date": str(r.get("REPORT_DATE", ""))[:10],
                      "predict_type": r.get("PREDICT_TYPE"),
                      "content": str(r.get("PREDICT_CONTENT", ""))[:120],
                      "amt_lower_yi": (lambda v: None if v is None else round(v / 1e4, 2))(
                          _fnum(r.get("PREDICT_AMT_LOWER"))),
                      "amt_upper_yi": (lambda v: None if v is None else round(v / 1e4, 2))(
                          _fnum(r.get("PREDICT_AMT_UPPER"))),
                      "ratio_lower_pct": _fnum(r.get("PREDICT_RATIO_LOWER")),
                      "ratio_upper_pct": _fnum(r.get("PREDICT_RATIO_UPPER")),
                      "notice_date": nd}
                break
        rows2 = _dc_rows("RPT_PUBLIC_BS_APPOIN", code, st, now, "dc-forecast",
                         sort="&sortColumns=FIRST_APPOINT_DATE&sortTypes=-1")
        nd = None
        today = dt.date.today().isoformat()
        if rows2:  # 降序表：下一次=最早的未来披露（末位未来行）；无未来取首行
            fut = [r for r in rows2
                   if str(r.get("FIRST_APPOINT_DATE", ""))[:10] >= today]
            r = fut[-1] if fut else rows2[0]
            nd = {"report_date": str(r.get("REPORT_DATE", ""))[:10],
                  "appoint_date": str(r.get("FIRST_APPOINT_DATE", ""))[:10],
                  "actual_date": str(r.get("ACTUAL_PUBLISH_DATE") or "")[:10] or None}
        return {"state": "available", "source": "dc-forecast",
                "performance_forecast": pf, "next_disclosure": nd}
    except Exception as e:
        if not isinstance(e, _Skip):
            record(st, CLUSTERS["dc-forecast"], False, str(e), now)
        return _ext_fail("dc-forecast", e)


def fetch_unlock(market, code, st, now):
    """扩展块·限售解禁（RPT_LIFT_STAGE，列名 2026-10-28 探针实测）：
    未来批次全列+过往近 24 月 ≤5 条。空 upcoming 是事实非失败。港 not_supported。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    try:
        rows = _dc_rows("RPT_LIFT_STAGE", code, st, now, "dc-unlock",
                        page_size=50,
                        sort="&sortColumns=FREE_DATE&sortTypes=-1")
        today = dt.date.today()
        cutoff = (today - dt.timedelta(days=730)).isoformat()
        upcoming, past = [], []
        for r in rows or []:
            item = {"date": str(r.get("FREE_DATE", ""))[:10],
                    "shares": r.get("FREE_SHARES"),
                    "ratio_pct": _fnum(r.get("FREE_RATIO")),
                    "type": str(r.get("FREE_SHARES_TYPE", ""))}
            if item["date"] >= today.isoformat():
                upcoming.append(item)
            elif item["date"] >= cutoff and len(past) < 5:
                past.append(item)
        # 降序取数后 upcoming 为从远到近——按日期升序输出，消费方（pack/报告）
        # 取头部即最近批次（近期解禁才是风险线索，002281 实测最远批 2030 年）。
        upcoming.sort(key=lambda u: u["date"])
        return {"state": "available", "source": "dc-unlock",
                "upcoming": upcoming, "past": past}
    except Exception as e:
        if not isinstance(e, _Skip):
            record(st, CLUSTERS["dc-unlock"], False, str(e), now)
        return _ext_fail("dc-unlock", e)


def fetch_holder(market, code, st, now):
    """扩展块·股东户数（emweb F10 gdrs，季度披露，近 8 期）：户数环比是官方口径
    的筹码集中/分散信号。坑位：datacenter 侧 RPT_HOLDERNUM_DET 数据集停在
    2022（服务端排序亦不生效），股东户数事实源在 emweb F10。港 not_supported。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    try:
        cluster = CLUSTERS["emweb-holder"]
        ok, why = source_allowed(st, cluster, now)
        if not ok:
            raise _Skip(why)
        suf = {"sh": "SH", "sz": "SZ", "bj": "BJ"}[cn_exchange(code)]
        data = json.loads(_http_text(
            "https://emweb.securities.eastmoney.com/PC_HSF10/"
            "ShareholderResearch/PageAjax?code=%s%s" % (suf, code)))
        rows = data.get("gdrs") or []
        if not rows:
            raise ValueError("empty gdrs")
        record(st, cluster, True, "", now)
        records = [{"date": str(r.get("END_DATE", ""))[:10],
                    "holder_num": r.get("HOLDER_TOTAL_NUM"),
                    "pct_change": _fnum(r.get("TOTAL_NUM_RATIO")),
                    "avg_mktcap": _fnum(r.get("AVG_MARKET_CAP"))}
                   for r in rows[:8] if r.get("END_DATE")]
        return {"state": "available", "source": "emweb-holder", "records": records}
    except Exception as e:
        if not isinstance(e, _Skip):
            record(st, CLUSTERS["emweb-holder"], False, str(e), now)
        return _ext_fail("emweb-holder", e)


def market_block(qt_indices):
    """扩展块·大盘指数：_qt_batch 已取的紧凑快照直接复用（零额外调用）。"""
    if qt_indices:
        return {"state": "available", "source": "qt-snap", "indices": qt_indices}
    return {"state": "fetch_failed", "source": "qt-snap", "note": "qt 簇不可用"}


def _sw_industry_via_sina(code):
    text = _http_text("https://vip.stock.finance.sina.com.cn/corp/go.php/"
                      "vCI_CorpOtherInfo/stockid/%s/menu_num/2.phtml" % code)
    m = re.search(r"所属行业板块</td>.*?<td[^>]*>([^<]+)</td>\s*<td[^>]*><a",
                  text, re.S)
    if not m:
        # 标的无该字段（如金融股/次新）是标的级事实——不计入 sina_flow 共享簇
        # 熔断（同簇 moneyflow/news 回退位不得被连坐）
        raise NotSupportedSymbol("无所属行业板块字段")
    return m.group(1).strip()


def _match_board(sw_name, df):
    """申万行业名 → 同花顺板块名匹配：核心词子串包含优先（『旅游』⊂『旅游及
    酒店』），字符二元组 Jaccard ≥0.4 兜底；三套行业口径（申万/东财/同花顺）
    不可混用排名数字，匹配置信不足宁缺。"""
    def core(s):
        return re.sub(r"[（(].*?[)）]|I{1,3}|Ⅱ|Ⅲ|综合|（申万）", "", str(s)).strip()
    c = core(sw_name)
    if not c:
        return None, 0.0
    for _, row in df.iterrows():
        name = core(row["板块"])
        if name and (c in name or name in c):  # 双向子串（空串免疫）
            return row, 0.9
    def grams(s):
        s = core(s)
        return {s[i:i + 2] for i in range(len(s) - 1)} | ({s} if len(s) > 2 else set())
    g = grams(sw_name)
    best, score = None, 0.0
    for _, row in df.iterrows():
        gb = grams(row["板块"])
        if g and gb:
            j = len(g & gb) / len(g | gb)
            if j > score:
                best, score = row, j
    return (best, score) if score >= 0.4 else (None, score)


def fetch_industry(market, code, st, now):
    """扩展块·行业板块：申万归属（sina_flow 直连 GBK F10）+ 同花顺 90 板块表
    （涨跌排名/净流入）。申万↔ths 名模糊匹配不足置信 → 只给归属不带板块统计
    （taxonomy_note 标注口径）。ths 全表一次调用（单页）在预算内。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    blk = {"state": "fetch_failed", "source": "", "note": "all_failed"}
    sw, board, note = None, None, []
    try:
        ok, why = source_allowed(st, CLUSTERS["sina-industry"], now)
        if not ok:
            raise _Skip(why)
        sw = _sw_industry_via_sina(code)
        record(st, CLUSTERS["sina-industry"], True, "", now)
    except _Skip as e:
        note.append("sina-industry:%s" % e)
    except NotSupportedSymbol:
        note.append("sina-industry:not_supported")  # 标的级空缺不计熔断
    except Exception as e:
        record(st, CLUSTERS["sina-industry"], False, str(e), now)
        note.append("sina-industry:%s" % type(e).__name__)
    try:
        ok, why = source_allowed(st, CLUSTERS["ths-fin"], now)
        if not ok:
            raise _Skip(why)
        import akshare as ak
        df = ak.stock_board_industry_summary_ths()
        board_row, score = _match_board(sw, df) if sw else (None, 0)
        board = None
        if board_row is not None:
            board = {"name": str(board_row["板块"]),
                     "rank": int(board_row["序号"]), "total": len(df),
                     "change_pct": _fnum(board_row["涨跌幅"]),
                     "net_inflow_yi": _fnum(board_row["净流入"]),
                     "top": str(board_row["领涨股"]),
                     "top_change_pct": _fnum(board_row["领涨股-涨跌幅"])}
            note.append("匹配置信 %.2f（申万『%s』↔同花顺『%s』）"
                        % (score, sw, board["name"]))
        elif sw:
            note.append("申万『%s』与同花顺板块匹配置信不足，只给归属" % sw)
        else:
            # sw 本身缺失（sina 路失败/熔断）：陈述事实，不落 None 字面量
            note.append("申万归属缺失（sina 路未取到），无板块匹配输入")
        record(st, CLUSTERS["ths-fin"], True, "", now)
    except _Skip as e:
        note.append("ths-board:%s" % e)
    except ImportError:
        note.append("ths-board:import_missing")
    except Exception as e:
        record(st, CLUSTERS["ths-fin"], False, str(e), now)
        note.append("ths-board:%s" % type(e).__name__)
    if sw or board:
        blk = {"state": ("partial" if len(note) > 1 or not board else "available"),
               "source": "sina-industry+ths-board", "industry_sw": sw,
               "board_ths": board, "taxonomy_note": "行业口径：申万（新浪 F10）"
               "+同花顺二级板块；两口径排名不可混用"}
        if note:
            blk["note"] = "；".join(note)
    elif note:
        # 双路全失败：逐源失败明细一并带回（缺什么写什么，与 news/notices
        # 的 tried 口径一致），不泛化成 all_failed
        blk["note"] = "；".join(note)
    return blk


def _baidu_percentile(code, indicator):
    """百度股市通历史估值序列（近五年）→ 当前值百分位 + 序列尾 5 点。"""
    import akshare as ak
    df = ak.stock_zh_valuation_baidu(symbol=code, indicator=indicator,
                                     period="近五年")
    vals = [_fnum(v) for v in df["value"]]  # "--"→NaN 归 None：不虚构 0.0 分位
    dates = [str(d) for d in df["date"]]
    if not vals or vals[-1] is None:
        raise ValueError("empty %s" % indicator)
    cur = vals[-1]
    below = sum(1 for v in vals if v is not None and v <= cur)
    pct = round(100.0 * below / len([v for v in vals if v is not None]), 1)
    tail = [{"date": dates[i], "value": vals[i]}
            for i in range(max(0, len(vals) - 5), len(vals))]
    return pct, tail


def fetch_valuation(market, code, st, now, qt_full):
    """扩展块·估值：A 路=qt 快照（PE-TTM/PB/市值/股息率，双路校验后的字段），
    B 路=百度股市通近五年历史分位（增强）。A 缺 B 在 → fallback；单路缺失如实
    记 note 不谎报。港 not_supported（qt 港股字段位序未验证）。"""
    if market == "hk":
        return {"state": "not_supported", "source": "", "note": "A 股专属"}
    a = None
    # A 路门槛=任一字段在即采信（亏损股 pe_ttm 为空，但 PB/市值/股息率可得，
    # 双字段与门槛会连坐丢弃全部可得字段；缺失字段如实留 None）
    if qt_full and any(qt_full.get(k) is not None for k in
                       ("pe_ttm", "pb", "total_mv_yi", "float_mv_yi",
                        "dividend_yield_ttm", "dps_ttm")):
        a = {"pe_ttm": qt_full.get("pe_ttm"), "pb": qt_full.get("pb"),
             "mktcap_total_yi": qt_full.get("total_mv_yi"),
             "mktcap_float_yi": qt_full.get("float_mv_yi"),
             "dividend_yield_ttm": qt_full.get("dividend_yield_ttm"),
             "dps_ttm": qt_full.get("dps_ttm")}
    pe_pct = pb_pct = None
    tail = []
    try:
        ok, why = source_allowed(st, CLUSTERS["baidu-val"], now)
        if not ok:
            raise _Skip(why)
        # 两指标各自独立 try：PE 空序列（亏损股常态）是标的级事实非源故障，
        # 吞掉后继续取 PB——串行耦合会把「单指标无数据」误记整簇源故障并
        # 连坐后续股票；真网络/解析错误仍上抛记败。
        try:
            pe_pct, tail = _baidu_percentile(code, "市盈率(TTM)")
        except ValueError:
            pass
        try:
            pb_pct, _t = _baidu_percentile(code, "市净率")
        except ValueError:
            pass
        record(st, CLUSTERS["baidu-val"], True, "", now)
    except _Skip:
        pass
    except ImportError:
        pass
    except Exception as e:
        record(st, CLUSTERS["baidu-val"], False, str(e), now)
    if a and (pe_pct is not None or pb_pct is not None):
        blk = {"state": "available", "source": "qt-snap+baidu-val", **a,
               "pe_percentile_5y": pe_pct, "pb_percentile_5y": pb_pct,
               "pe_series_tail": tail}
        if pe_pct is None or pb_pct is None:  # 半失败如实记 note 不谎报（docstring）
            # 措辞不臆断成因：空序列（标的无数据）与网络失败同走此路径
            blk["note"] = "历史分位部分缺失（%s序列无数据或获取失败）" % (
                "市盈率" if pe_pct is None else "市净率")
        return blk
    if a:
        return {"state": "available", "source": "qt-snap", **a,
                "note": "历史分位缺失（baidu 序列无数据或源不可用）"}
    if pe_pct is not None or pb_pct is not None:
        return {"state": "fallback", "source": "baidu-val",
                "pe_percentile_5y": pe_pct, "pb_percentile_5y": pb_pct,
                "note": "qt 快照缺失，仅历史分位"}
    return {"state": "fetch_failed", "source": "",
            "note": "qt 与 baidu 均不可用（或 qt 双路校验弃字段）"}




BLOCK_WEIGHTS = [("quote", 25), ("daily_bars", 25), ("technical", 25),
                 ("news", 10), ("fundamentals", 10), ("chip", 5)]
# 扩展块：不进 BLOCK_WEIGHTS 质量分（信息面不是裁决面——置信帽只反映核心行情
# 链可用性，与情报丰富度正交），可见性由八态状态行与策略 required_evidence 承担。
# 快照模式文件可选、缺省 missing。某块要进权重属 0.3.0 级语义变更（golden 重建）。
EXT_BLOCKS = ["moneyflow", "notices", "research", "forecast", "unlock",
              "holder", "market", "industry", "valuation"]
ALL_BLOCKS = [n for n, _ in BLOCK_WEIGHTS] + EXT_BLOCKS
STATE_SCORE = {"available": 100, "fallback": 85, "partial": 70, "stale": 60,
               "estimated": 55, "missing": 30, "not_supported": 30, "fetch_failed": 25}
CORE_BLOCKS = {"quote", "daily_bars", "technical"}


def quality(blocks):
    score = sum(STATE_SCORE.get(blocks.get(n, {}).get("state", "missing"), 0) * w
                for n, w in BLOCK_WEIGHTS) // 100
    tier = ("good" if score >= 85 else "usable" if score >= 70
            else "limited" if score >= 55 else "poor")
    core_degraded = any(blocks.get(n, {}).get("state", "missing")
                        not in ("available", "fallback") for n in CORE_BLOCKS)
    return {"score": score, "tier": tier,
            "confidence_cap": "low" if core_degraded else "high"}


# ---------------------------------------------------------------- 快照模式

def snapshot_blocks(snapshot_dir):
    blocks = {}
    for name in ALL_BLOCKS:  # 扩展块快照文件可选，缺省 missing 如实标注
        path = os.path.join(snapshot_dir, name + ".json")
        if not os.path.exists(path):
            blocks[name] = {"state": "missing", "source": "snapshot",
                            "note": "快照目录未提供"}
            continue
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
            state = payload.pop("state", "estimated")
            blocks[name] = {"state": state, "source": "snapshot", **payload}
        except Exception as e:
            blocks[name] = {"state": "partial", "source": "snapshot",
                            "note": "快照解析失败: %s" % type(e).__name__}
    return blocks


# ---------------------------------------------------------------- 主流程

def fetch(symbol, snapshot_dir=None):
    now = int(time.time())
    if snapshot_dir:
        blocks = snapshot_blocks(snapshot_dir)
        meta = {"symbol": symbol, "snapshot": True}
    else:
        market, code = detect_market(symbol)
        st = load_fetch_state()
        bars, bars_state, bars_src, tried = fetch_daily_bars(market, code, st, now)
        qt_full, qt_indices = _qt_batch(market, code, st, now)
        save_fetch_state(st)
        blocks = {"daily_bars": {"state": bars_state, "source": bars_src,
                                 "tried": tried,
                                 "bars": bars[-BARS_WINDOW:]}}
        if bars:
            q = derive_quote(bars)
            src_note = ""
            if qt_full and qt_full.get("price"):  # qt 实时叠加（A股盘中新鲜度）
                if abs(qt_full["price"] / q["price"] - 1) > 0.05:
                    src_note = "实时价 %s 与日K收盘 %s 偏差>5%%" % (
                        qt_full["price"], q["price"])
                q = {**q, "price": qt_full["price"],
                     "turnover_pct": qt_full.get("turnover_pct")}
                # date 同刻：叠加后 price/prev_close/change_pct 均为今日实时
                # 口径，date 留日 K 末根（昨日）会形成「昨日日期 × 今日实时价」
                # 混合时点——qt 快照无独立交易日字段，按取数当日计。
                q["date"] = dt.date.today().isoformat()
                # 同刻配对：集合竞价/日K滞后窗口里日 K 末根仍是昨日，若只叠
                # price 会形成「今日实时价 × 昨日涨跌幅」混合时点——qt 昨收与
                # 实时价同源同时刻，一并采信并重算涨幅（昨收>0 才采信防位序漂移）。
                qtpc = qt_full.get("prev_close")
                if qtpc and qtpc > 0:
                    q["prev_close"] = qtpc
                    q["change_pct"] = round(
                        (qt_full["price"] / qtpc - 1) * 100, 2)
            qsrc = "derived:%s+qt" % bars_src if qt_full and qt_full.get(
                "price") else "derived:" + bars_src
            if src_note:
                q["note"] = src_note
            blocks["quote"] = {"state": ("available" if bars_state == "available"
                                         else bars_state), "source": qsrc, **q}
            blocks["technical"] = {"state": ("available" if bars_state == "available"
                                             else bars_state),
                                   "source": "derived", **derive_technical(bars)}
        else:
            blocks["quote"] = {"state": "missing", "source": "",
                               "note": "日 K 缺失，报价无从而来"}
            blocks["technical"] = {"state": "missing", "source": "",
                                   "note": "日 K 缺失，指标无从而来"}
        blocks["news"] = fetch_news(market, code, st, now)
        blocks["fundamentals"] = fetch_fundamentals(market, code, st, now)
        blocks["chip"] = fetch_chip(market, code, st, now, bars=bars,
                                    float_shares=(qt_full or {}).get("float_shares"),
                                    bars_source=bars_src)
        # 扩展九块（零权重）：顺序执行预算 ~17 次 HTTP、15–25s；失败如实八态标注
        blocks["moneyflow"] = fetch_moneyflow(market, code, st, now)
        blocks["notices"] = fetch_notices(market, code, st, now)
        blocks["research"] = fetch_research(market, code, st, now)
        blocks["forecast"] = fetch_forecast(market, code, st, now)
        blocks["unlock"] = fetch_unlock(market, code, st, now)
        blocks["holder"] = fetch_holder(market, code, st, now)
        blocks["market"] = market_block(qt_indices)
        blocks["industry"] = fetch_industry(market, code, st, now)
        blocks["valuation"] = fetch_valuation(market, code, st, now, qt_full)
        save_fetch_state(st)
        market_meta = {"symbol": symbol, "market": market, "code": code,
                       "tried": tried}
        meta = market_meta
    if blocks.get("daily_bars", {}).get("bars"):
        bars = blocks["daily_bars"]["bars"]
        bars_state = blocks["daily_bars"].get("state", "estimated")
        for name in ("technical",):
            if blocks.get(name, {}).get("state") in (None, "missing"):
                blocks[name] = {"state": bars_state, "source": "derived",
                                **derive_technical(bars)}
            else:
                blocks[name] = {**blocks.get(name, {}),
                                **derive_technical(bars)}
        if blocks.get("quote", {}).get("state") in (None, "missing"):
            blocks["quote"] = {"state": bars_state, "source": "derived:" +
                               blocks["daily_bars"].get("source", ""),
                               **derive_quote(bars)}
    evidence = {"meta": meta, "fetched_at": dt.datetime.now().isoformat(
        timespec="seconds"), "blocks": blocks, "quality": quality(blocks)}
    return evidence


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stock", required=True)
    ap.add_argument("--snapshot-dir")
    ap.add_argument("--out", default="evidence.json")
    args = ap.parse_args()
    evidence = fetch(args.stock, args.snapshot_dir)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(evidence, f, ensure_ascii=False, indent=1)
    q = evidence["quality"]
    print("evidence -> %s · quality %s(%s) cap=%s" %
          (args.out, q["score"], q["tier"], q["confidence_cap"]))
    for n in ALL_BLOCKS:
        b = evidence["blocks"].get(n, {})
        print("  %-13s %-13s %s" % (n, b.get("state", "missing"), b.get("source", "")))
    if evidence["blocks"]["daily_bars"]["state"] == "fetch_failed":
        sys.exit(2)


if __name__ == "__main__":
    main()
