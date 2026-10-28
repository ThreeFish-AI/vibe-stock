#!/usr/bin/env python3
"""fetch.py · vibe-stock 证据取数层（蓝本：DSA data_provider 多源回退链）。

机制（与 references/01-evidence.md 同源）：
  - 市场分流：A 股链 em_quote(akshare→efinance 簇内次选)→qq(腾讯 qfq)→yfinance；
    港股链 em_quote(akshare)→yfinance。
  - 回退链逐源尝试；任一成功即继续，状态标 available/fallback。
  - 熔断：按上游服务簇（非库名）计账，单簇连续 3 次失败停 300s（半开放行单次
    探测）；连接失败冷却 15s。状态持久化在 ~/.vibe-stock/fetch_state.json
    （真实时钟，秒）；旧库名键自然过期，不迁移不删除。
  - 八态标注：每个数据块独立标 available/missing/not_supported/fallback/stale/
    estimated/partial/fetch_failed——缺什么写什么，绝不静默消失。
  - 技术指标（MA/RSI/MACD/量比等）由日 K 纯标准库推导，不依赖三方库。
  - 快照模式：--snapshot-dir 提供预置 JSON（无网兜底），状态按文件声明或 estimated。

用法（联网全量）：
  uv run --no-project --with akshare --with efinance --with yfinance \
      scripts/fetch.py --stock 600519 --out evidence.json
  uv run --no-project --with akshare --with yfinance \
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
STALE_DAYS = {"quote": 1, "daily_bars": 5, "news": 3, "fundamentals": 120, "chip": 5}

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
    # —— 0.2.0 扩容（六簇 → 十四簇）——
    "em-fin": "em_datacenter",  # 东财数据中心簇 · 财务主指标（datacenter*/securities/api）
    "em-notice": "em_notice",   # 东财公告簇 · np-anotice-stock 子域
    "cninfo-disc": "cninfo",    # 巨潮簇 · 公告权威回退（www.cninfo.com.cn）
    "em-report": "em_report",   # 东财研报簇 · reportapi 子域
    "dc-respredict": "em_datacenter",   # 评级共识+目标价（datacenter-web 直连）
    "dc-forecast": "em_datacenter",     # 业绩预告+披露日历（同簇两条 reportName）
    "dc-unlock": "em_datacenter",       # 解禁批次
    "dc-holder": "em_datacenter",       # 股东户数
    "sina-flow": "sina_flow",   # 新浪行情流量簇 · 资金流/个股资讯/申万归属（vip.stock 子域）
    "sina-news": "sina_flow",   # 新闻第三源（同子域，共担熔断）
    "sina-industry": "sina_flow",  # 申万行业归属（同子域）
    "qt-snap": "qt",            # 腾讯快照簇 · qt.gtimg.cn 主机（与 qq 日K 主机粒度分簇）
    "qq-news": "qq_news",       # 腾讯资讯簇 · proxy.finance.qq.com 主机
    "baidu-val": "baidu_gushitong",  # 百度股市通 · 历史估值序列
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
    if re.fullmatch(r"(sh|sz)?\d{6}", s):
        return "cn", re.sub(r"^(sh|sz)", "", s)
    m = re.fullmatch(r"(?:hk)?(\d{4,5})(?:\.hk)?", s)
    if m:
        return "hk", m.group(1)
    raise SystemExit("无法识别市场，示例：600519 / 0601888 / sz000001 / hk00700 / 0700.HK")


def yf_ticker(market, code):
    if market == "hk":
        return str(int(code)).zfill(4) + ".HK"  # Yahoo 港码 4 位：00700→0700.HK
    return code + (".SS" if code.startswith(("6", "9", "5")) else ".SZ")


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
    56=每股股息TTM(元) 64=股息率TTM(%) 72=流通股本 73=总股本。
    位序漂移防护（无条件全局规则：qt 无官方文档、字段序随版本漂移）：流通股本
    双路推导交叉校验——市值/现价 与 成交量(手→股)/换手率 相对误差 >2% 即弃
    股本字段（chip 自算随之降级），绝不硬编码信任单一位序。"""
    body = text[text.index('"') + 1:text.rindex('"')]
    f = body.split("~")

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
    return {"name": f[1], "price": price, "prev_close": num(4), "open": num(5),
            "volume_hand": vol, "amount_wan": num(37), "turnover_pct": turnover,
            "pe_ttm": num(39), "float_mv_yi": float_mv, "total_mv_yi": num(45),
            "pb": num(46), "dps_ttm": num(56), "dividend_yield_ttm": num(64),
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
            sym = ("sh" if code.startswith(("6", "9", "5")) else "sz") + code
            full = _parse_qt_full(_http_text("https://qt.gtimg.cn/q=" + sym))
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
    volume 列要求 akshare ≥2025-10 版；单位为股（em 系源为手），仅用于源内
    比值 vol_ratio_5，单位相消。
    """
    import akshare as ak  # noqa: 延迟导入，缺库不致命
    pfx = "sh" if code.startswith(("6", "9", "5")) else "sz"
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
           else ("sh" if code.startswith(("6", "9", "5")) else "sz") + code)
    text = _http_text("https://proxy.finance.qq.com/ifzqgtimg/appstock/"
                      "news/info/search?page=1&symbol=%s&n=20&type=2" % sym)
    arr = (json.loads(text).get("data") or {}).get("data") or []
    items = [{"title": str(a.get("title", "")), "content": str(
        a.get("summary", ""))[:150], "time": str(a.get("time", "")),
        "src": str(a.get("src", ""))} for a in arr if a.get("title")]
    if not items:
        raise ValueError("empty news")
    return items[:10]


def _news_via_sina(code):
    """新浪流量簇（直连 F10 个股资讯页，GB2312 HTML，标题级末位回退）：
    无内容摘要无来源名，仅 A 股；页面含弱相关条目，如实进包由意见层甄别。"""
    sym = ("sh" if code.startswith(("6", "9", "5")) else "sz") + code
    text = _http_text("https://vip.stock.finance.sina.com.cn/corp/go.php/"
                      "vCB_AllNewsStock/symbol/%s.phtml" % sym)
    rows = re.findall(
        r"(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\s*<a[^>]*href=\"([^\"]+)\"[^>]*>([^<]+)</a>",
        text)
    items = [{"title": t.strip(), "content": "", "time": tm, "url": u}
             for tm, u, t in rows]
    if not items:
        raise ValueError("empty news")
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
        except ImportError:
            tried.append((name, "import_missing"))  # 缺库不记熔断（环境问题非源问题）
        except Exception as e:
            record(st, cluster, False, str(e), now)
            tried.append((name, "fail: %s" % type(e).__name__))
    return {"state": "fetch_failed", "source": "", "note": "all_failed", "tried": tried}


def _fund_via_em(code):
    """东财数据中心簇（0.2.0 链首，经 akshare）：一表全含——四概念键对齐既有
    口径，另带扩展键（毛利率/净利率/ROIC/扣非/单季环比，近 4 报告期）。
    列名为接口 raw 英文列（REPORT_DATE/EPSJB/ROEJQ/…），最新期在前。
    SECUCODE 后缀：沪 6/9/5 → .SH，北交 8/4 → .BJ，其余 → .SZ。"""
    import akshare as ak
    suf = ".SH" if code.startswith(("6", "9", "5")) else (
        ".BJ" if code.startswith(("8", "4")) else ".SZ")
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
            # v == v 滤 NaN：_num("--")→nan 非 None，全占位不算成功（勿重置簇计数）
            if not any(v is not None and v == v for v in data.values()):
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


def derive_chip(bars, float_shares, bars_source=""):
    """筹码分布本地自算（CYQ 三角分布换手衰减，与 akshare stock_cyq_em 同算法，
    输出列名与官方接口全同）。状态由调用方标 estimated。
    坑位：①volume 单位陷阱——yf 源为股、em/qq 系源为手，按 bars_source 判定
    归一；②历史换手率以当前流通股本回溯，增发/解禁/回购期误差放大；③一字板
    （high==low）单点全量堆积。"""
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
        data = {k: (None if k not in row else _num(row[k])) for k in keys}
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


# ---------------------------------------------------------------- 质量分（与 adjudicate.evidence_cap 同源）

BLOCK_WEIGHTS = [("quote", 25), ("daily_bars", 25), ("technical", 25),
                 ("news", 10), ("fundamentals", 10), ("chip", 5)]
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
    for name, _w in BLOCK_WEIGHTS:
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
        qt_full, _ = _qt_batch(market, code, st, now)  # 指数部分 0.2.0 扩展块消费
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
    for n, _w in BLOCK_WEIGHTS:
        b = evidence["blocks"].get(n, {})
        print("  %-13s %-13s %s" % (n, b.get("state", "missing"), b.get("source", "")))
    if evidence["blocks"]["daily_bars"]["state"] == "fetch_failed":
        sys.exit(2)


if __name__ == "__main__":
    main()
