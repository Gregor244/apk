# =========================================
# STOCK SCANNER PRO
# FULL ASYNC VERSION — OPTIMIZED & STABLE
# RecycleView + Live Market + Scanner + News Filters
# =========================================

import asyncio
import threading
import time
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import certifi
import httpx

from kivy.config import Config
Config.set("graphics", "multisamples", "0")

from kivy.lang import Builder
from kivy.clock import Clock
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.recycleview import RecycleView

from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.textfield import MDTextField
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel

# =========================================
# CONFIG
# =========================================

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

FINNHUB_KEY = "d82t3s1r01ql4onfbbngd82t3s1r01ql4onfbbo0"

HTTP_CLIENT = httpx.AsyncClient(
    headers=HEADERS,
    verify=certifi.where(),
    timeout=10.0,
    limits=httpx.Limits(max_connections=15, max_keepalive_connections=5),
    http2=True,
)

REQUEST_DELAY = 0.2
MAX_RETRIES = 2

REQUEST_CACHE = {}
REQUEST_CACHE_LOCK = threading.Lock()
REQUEST_CACHE_TTL = {
    "screener": 125,
    "ticker": 90,
    "finnhub": 120,
    "company": 180,
    "news": 180,
}

LAST_REQUEST_TIME = {}
RATE_LIMIT_LOCK = asyncio.Lock()

ASYNC_LOOP = None
ASYNC_LOOP_READY = threading.Event()

Clock.max_iteration = 100

# =========================================
# HELPERS
# =========================================

def safe(v, d=0.0):
    try:
        if v is None:
            return d
        return float(v)
    except Exception:
        return d

def fmt_num(value, digits=2, signed=False):
    v = safe(value, 0.0)
    return f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"

def color_wrap(text, color):
    return f"[color={color}]{text}[/color]"

def format_cap(v):
    v = safe(v)
    if v >= 1_000_000_000_000:
        return f"{v/1_000_000_000_000:.2f} T"
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f} B"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f} M"
    return str(round(v, 2))

def market_status():
    ny = datetime.now(ZoneInfo("America/New_York"))
    if ny.weekday() >= 5:
        return "ZAMKNIĘTY"
    h = ny.hour + ny.minute / 60
    if 4 <= h < 9.5:
        return "PREMARKET"
    if 9.5 <= h < 16:
        return "OTWARTY"
    if 16 <= h < 20:
        return "POSTMARKET"
    return "ZAMKNIĘTY"

def get_session_snapshot(data):
    session = str(data.get("session_state") or market_status()).upper().strip()
    prev_close = safe(data.get("prev_close"), 0.0)
    regular = safe(data.get("price"), 0.0)
    pre = safe(data.get("pre_price"), safe(data.get("pre"), 0.0))
    post = safe(data.get("post_price"), safe(data.get("post"), 0.0))
    session_price = safe(data.get("session_price"), 0.0)

    if session == "PREMARKET":
        active = pre or session_price or regular
    elif session == "POSTMARKET":
        active = post or session_price or regular
    else:
        active = regular or session_price or prev_close

    change_amt = active - prev_close if prev_close else 0.0
    change_pct = (change_amt / prev_close) * 100 if prev_close else 0.0

    labels = {
        "PREMARKET": "[color=#0000FF][b][PRE-MARKET][/b][/color]",
        "OTWARTY": "[color=#00AA00][b][MARKET OPEN][/b][/color]",
        "POSTMARKET": "[color=#800080][b][POST-MARKET][/b][/color]",
        "ZAMKNIĘTY": "[color=#FF9900][b][ZAMKNIĘTY][/b][/color]",
    }

    return {
        "session": session,
        "session_label": labels.get(session, labels["ZAMKNIĘTY"]),
        "active_price": active,
        "change_amt": change_amt,
        "change_pct": change_pct,
        "prev_close": prev_close,
    }

def ema(data, period):
    if not data:
        return []
    result = [data[0]]
    k = 2 / (period + 1)
    for price in data[1:]:
        result.append(price * k + result[-1] * (1 - k))
    return result

def macd(closes):
    if len(closes) < 35:
        return 0.0, 0.0, 0.0
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    min_len = min(len(ema12), len(ema26))
    if min_len == 0:
        return 0.0, 0.0, 0.0
    macd_line = [ema12[i] - ema26[i] for i in range(-min_len, 0)]
    signal_line = ema(macd_line, 9)
    if not macd_line or not signal_line:
        return 0.0, 0.0, 0.0
    macd_val = macd_line[-1]
    signal_val = signal_line[-1]
    hist = macd_val - signal_val
    return round(macd_val, 3), round(signal_val, 3), round(hist, 3)

def color_for_rsi(rsi):
    if rsi <= 30:
        return "#006600"
    if rsi <= 40:
        return "#00AA00"
    if rsi >= 70:
        return "#FF0000"
    if rsi >= 60:
        return "#FF9900"
    return "#888888"

def color_for_macd(macd_val, signal_val):
    return "#00AA00" if macd_val > signal_val else "#FF0000"

def format_histogram(hist):
    if hist > 0:
        return color_wrap(fmt_num(hist, 3, signed=True), "#00AA00")
    if hist < 0:
        return color_wrap(fmt_num(hist, 3, signed=True), "#FF0000")
    return color_wrap(fmt_num(hist, 3, signed=True), "#888888")

def get_signal_info(rsi_val, macd_v, sig_v, hist_v):
    if rsi_val <= 35 and macd_v > sig_v and hist_v > 0:
        return "MOCNE KUP", "#006600"
    elif rsi_val <= 45 and macd_v > sig_v:
        return "KUP", "#00AA00"
    elif rsi_val >= 65 and macd_v < sig_v and hist_v < 0:
        return "MOCNE SPRZEDAJ", "#FF0000"
    elif rsi_val >= 55 and macd_v < sig_v:
        return "SPRZEDAJ", "#FF9900"
    else:
        return "NEUTRALNE", "#888888"

def safe_json(response):
    try:
        if not response or getattr(response, "status_code", 0) != 200:
            return {}
        return response.json()
    except Exception:
        return {}

def normalize_company_name(symbol, name=None):
    symbol = (symbol or "").strip().upper()
    cleaned = (name or "").strip()
    fallback = {
        "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA",
        "AMD": "Advanced Micro Devices", "META": "Meta Platforms",
        "TSLA": "Tesla", "PLTR": "Palantir Technologies", "AMZN": "Amazon",
    }
    if cleaned and cleaned.upper() != symbol:
        return cleaned
    return fallback.get(symbol, cleaned or symbol)

def build_full_glossary():
    return (
        "[b]SŁOWNIK WSKAŹNIKÓW I POJĘĆ[/b]\n"
        "• [b]SMA[/b] — średnia krocząca.\n"
        "• [b]EMA[/b] — wykładnicza średnia krocząca.\n"
        "• [b]RSI[/b] — oscylator 0–100; p. 30 wyprzedanie, pow. 70 wykupienie.\n"
        "• [b]MACD[/b] — różnica między średnimi EMA.\n"
        "• [b]Histogram[/b] — MACD minus sygnał.\n"
        "• [b]Market Cap[/b] — kapitalizacja rynkowa.\n"
        "• [b]Prev Close[/b] — zamknięcie poprzedniej sesji.\n\n"
        "[b]KOLORY[/b]\n"
        "• Zielony — popyt / sygnał wzrostowy.\n"
        "• Czerwony — podaż / sygnał spadkowy."
    )

def make_tp_sl(price, tp_pct=0.03, sl_pct=0.02):
    price = safe(price, 0.0)
    return price * (1 + tp_pct), price * (1 - sl_pct)

def run_coro(coro):
    if ASYNC_LOOP is None or not ASYNC_LOOP.is_running():
        return None
    return asyncio.run_coroutine_threadsafe(coro, ASYNC_LOOP)

def start_async_loop():
    global ASYNC_LOOP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ASYNC_LOOP = loop
    ASYNC_LOOP_READY.set()
    loop.run_forever()

threading.Thread(target=start_async_loop, daemon=True).start()

# =========================================
# ASYNC HTTP WITH FIXES
# =========================================

async def safe_request_async(url, timeout=10, retries=MAX_RETRIES):
    host = url.split("/")[2] if "://" in url else "default"

    for i in range(retries):
        delay = 0
        async with RATE_LIMIT_LOCK:
            now = time.time()
            diff = now - LAST_REQUEST_TIME.get(host, 0)
            if diff < REQUEST_DELAY:
                delay = REQUEST_DELAY - diff
                LAST_REQUEST_TIME[host] = now + delay
            else:
                LAST_REQUEST_TIME[host] = now

        if delay > 0:
            await asyncio.sleep(delay)

        try:
            response = await HTTP_CLIENT.get(url, timeout=timeout)
            if response.status_code == 200 or response.status_code == 404:
                return response
            if response.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(1.0 * (i + 1))
                continue
            return response
        except Exception:
            await asyncio.sleep(0.5 * (i + 1))

    class Dummy:
        status_code = 0
        def json(self): return {}
    return Dummy()

# =========================================
# FINNHUB/YAHOO FETCH
# =========================================

async def fetch_top_gainers_by_type_async(scr_id="day_gainers"):
    cache_key = ("screener", scr_id)
    now_ts = time.time()

    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (now_ts - cached.get("ts", 0)) < REQUEST_CACHE_TTL["screener"]:
            return list(cached.get("data", []))

    count = 15
    url = (
        "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved"
        f"?formatted=true&lang=en-US&region=US&scrIds={scr_id}&count={count}"
    )

    res = await safe_request_async(url, timeout=6)
    if res.status_code == 200:
        result = safe_json(res).get("finance", {}).get("result")
        if result and isinstance(result, list):
            symbols = [q["symbol"] for q in result[0].get("quotes", []) if "symbol" in q]
            with REQUEST_CACHE_LOCK:
                REQUEST_CACHE[cache_key] = {"ts": now_ts, "data": symbols}
            return symbols
    return []

async def fetch_dynamic_universe_async(limit=30):
    screeners = ["day_gainers", "most_actives"]
    results = await asyncio.gather(*[fetch_top_gainers_by_type_async(s) for s in screeners], return_exceptions=True)

    tickers = []
    for res in results:
        if isinstance(res, list):
            tickers.extend(res[:12])

    tickers.extend(["AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "PLTR"])
    return list(dict.fromkeys(tickers))[:max(1, int(limit))]

def _extract_chart_payload(yahoo_json):
    result = yahoo_json.get("chart", {}).get("result", [])
    if not result:
        return {}, []
    payload = result[0]
    quote = payload.get("indicators", {}).get("quote", [{}])[0]
    return payload, quote

async def fetch_prev_earnings_reaction(symbol):
    try:
        earnings_url = f"https://finnhub.io/api/v1/stock/earnings?symbol={symbol}&token={FINNHUB_KEY}"
        res = await safe_request_async(earnings_url, timeout=6)
        if res.status_code != 200:
            return "Brak danych"

        payload = safe_json(res)
        earnings_list = []
        if isinstance(payload, dict):
            earnings_list = payload.get("earnings", []) or payload.get("data", []) or []
        elif isinstance(payload, list):
            earnings_list = payload

        if not earnings_list:
            return "Brak danych"

        latest = earnings_list[0]
        period = latest.get("period") or latest.get("date")
        if not period:
            return "Brak danych"

        e_date = datetime.strptime(period[:10], "%Y-%m-%d").date()
        start_ts = int((datetime.combine(e_date - timedelta(days=2), datetime.min.time())).timestamp())
        end_ts = int((datetime.combine(e_date + timedelta(days=4), datetime.min.time())).timestamp())

        react_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start_ts}&period2={end_ts}&interval=1d"
        react_req = await safe_request_async(react_url, timeout=6)
        if react_req.status_code != 200:
            return "Brak danych"

        react_payload, react_quote = _extract_chart_payload(safe_json(react_req))
        react_closes = [c for c in react_quote.get("close", []) if c is not None]
        if len(react_closes) < 2 or not react_closes[0]:
            return "Brak danych"

        r_pct = ((react_closes[-1] - react_closes[0]) / react_closes[0]) * 100
        r_sign = "+" if r_pct > 0 else ""
        return f"[b][color={'#00AA00' if r_pct > 0 else '#FF0000'}]{r_sign}{r_pct:.2f}%[/color][/b]"
    except Exception:
        return "Brak danych"

async def fetch_ticker(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return {}

    cache_key = ("ticker", symbol)
    now_ts = time.time()

    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (now_ts - cached.get("ts", 0)) < REQUEST_CACHE_TTL["ticker"]:
            return dict(cached.get("data", {}))

    yahoo_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1y"
    intraday_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d&includePrePost=true"
    quote_url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={FINNHUB_KEY}"
    profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={FINNHUB_KEY}"
    metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={FINNHUB_KEY}"
    earnings_url = f"https://finnhub.io/api/v1/calendar/earnings?symbol={symbol}&from={(datetime.now()).strftime('%Y-%m-%d')}&to={(datetime.now()+timedelta(days=90)).strftime('%Y-%m-%d')}&token={FINNHUB_KEY}"

    yahoo_res, intraday_res, quote_res, profile_res, metrics_res, earnings_res = await asyncio.gather(
        safe_request_async(yahoo_url, timeout=6),
        safe_request_async(intraday_url, timeout=6),
        safe_request_async(quote_url, timeout=5),
        safe_request_async(profile_url, timeout=5),
        safe_request_async(metrics_res, timeout=6),
        safe_request_async(earnings_url, timeout=6),
        return_exceptions=True,
    )

    closes, volumes = [], []
    price, prev_close, session_price = 0.0, 0.0, 0.0
    session_state = market_status()
    day_high, day_low, year_high, year_low = 0.0, 0.0, 0.0, 0.0
    pre_price, post_price = 0.0, 0.0

    if getattr(yahoo_res, "status_code", 0) == 200:
        payload, quote = _extract_chart_payload(safe_json(yahoo_res))
        meta = payload.get("meta", {})
        closes = [x for x in quote.get("close", []) if x is not None]
        volumes = [x for x in quote.get("volume", []) if x is not None]
        price = safe(meta.get("regularMarketPrice", 0.0))
        prev_close = safe(meta.get("previousClose", meta.get("chartPreviousClose", 0.0)))
        day_high = safe(meta.get("regularMarketDayHigh", meta.get("dayHigh", 0.0)))
        day_low = safe(meta.get("regularMarketDayLow", meta.get("dayLow", 0.0)))
        year_high = safe(meta.get("fiftyTwoWeekHigh", 0.0))
        year_low = safe(meta.get("fiftyTwoWeekLow", 0.0))
        pre_price = safe(meta.get("preMarketPrice", 0.0))
        post_price = safe(meta.get("postMarketPrice", 0.0))

    if getattr(intraday_res, "status_code", 0) == 200:
        intraday_payload, intraday_quote = _extract_chart_payload(safe_json(intraday_res))
        intraday_meta = intraday_payload.get("meta", {})
        session_state = str(intraday_meta.get("marketState", session_state) or session_state).upper().strip()
        if prev_close <= 0:
            prev_close = safe(intraday_meta.get("previousClose", intraday_meta.get("chartPreviousClose", 0.0)))
        if session_state == "PREMARKET":
            session_price = safe(intraday_meta.get("preMarketPrice", 0.0))
        elif session_state == "POSTMARKET":
            session_price = safe(intraday_meta.get("postMarketPrice", 0.0))
        else:
            session_price = safe(intraday_meta.get("regularMarketPrice", 0.0))

        if session_price <= 0:
            closes_i = [x for x in intraday_quote.get("close", []) if x is not None]
            if closes_i: session_price = safe(closes_i[-1])
        if price <= 0 and session_price > 0: price = session_price
        if pre_price <= 0: pre_price = safe(intraday_meta.get("preMarketPrice", 0.0))
        if post_price <= 0: post_price = safe(intraday_meta.get("postMarketPrice", 0.0))

    fh_q = safe_json(quote_res) if getattr(quote_res, "status_code", 0) == 200 else {}
    if fh_q.get("c", 0) > 0:
        if price <= 0: price = safe(fh_q.get("c", 0.0))
        if prev_close <= 0: prev_close = safe(fh_q.get("pc", 0.0))
        if day_high <= 0: day_high = safe(fh_q.get("h", 0.0))
        if day_low <= 0: day_low = safe(fh_q.get("l", 0.0))

    profile = safe_json(profile_res) if getattr(profile_res, "status_code", 0) == 200 else {}
    metrics = safe_json(metrics_res) if getattr(metrics_res, "status_code", 0) == 200 else {}
    earnings_data = safe_json(earnings_res) if getattr(earnings_res, "status_code", 0) == 200 else {}

    market_cap = safe(profile.get("marketCapitalization", 0.0)) * 1_000_000 if isinstance(profile, dict) else 0.0

    pe, eps = "N/A", "N/A"
    if isinstance(metrics, dict):
        metric = metrics.get("metric", {}) or {}
        pe_v = metric.get("peNormalizedAnnual") or metric.get("peExclExtraTTM") or metric.get("peTTM")
        eps_v = metric.get("epsTTM")
        if pe_v is not None: pe = f"{safe(pe_v):.2f}"
        if eps_v is not None: eps = f"{safe(eps_v):.2f}"

    next_earnings = "Brak danych"
    if isinstance(earnings_data, dict):
        cal = earnings_data.get("earningsCalendar", []) or []
        if cal: next_earnings = cal[0].get("date", "Brak danych")

    active_for_change = session_price or price
    change = active_for_change - prev_close if prev_close else 0.0
    pct = (change / prev_close * 100) if prev_close else 0.0
    m, s, h = macd(closes)
    earnings_reaction = await fetch_prev_earnings_reaction(symbol)

    result = {
        "symbol": symbol,
        "name": normalize_company_name(symbol, profile.get("name", symbol) if isinstance(profile, dict) else symbol),
        "price": price, "session_price": session_price, "session_state": session_state, "prev_close": prev_close,
        "vol": safe(volumes[-1]) if volumes else safe(fh_q.get("v", 0.0)),
        "avg_vol": int(sum(volumes[-10:]) / 10) if len(volumes) >= 10 else (int(sum(volumes) / len(volumes)) if volumes else 0),
        "change": change, "pct": pct, "market_cap": market_cap, "pe": pe, "eps": eps, "high52": year_high, "low52": year_low,
        "day_high": day_high, "day_low": day_low, "pre_price": pre_price, "post_price": post_price, "pre": pre_price, "post": post_price,
        "macd": m, "signal": s, "hist": h, "closes": closes, "year_high": year_high, "year_low": year_low,
        "prev_earnings_period": "Brak danych", "prev_earnings_surprise": "Brak danych", "earnings_reaction": earnings_reaction, "next_earnings": next_earnings,
    }

    with REQUEST_CACHE_LOCK:
        REQUEST_CACHE[cache_key] = {"ts": now_ts, "data": dict(result)}
    return result

async def fetch_bulk(symbols):
    unique = [s for s in dict.fromkeys([str(x).strip().upper() for x in symbols if x]) if s]
    sem = asyncio.Semaphore(3)
    
    async def throttled_fetch(s):
        async with sem:
            return await fetch_ticker(s)

    tasks = [throttled_fetch(s) for s in unique]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    out = {}
    for sym, res in zip(unique, results):
        if isinstance(res, Exception) or not res:
            continue
        out[sym] = res
    return out

async def fetch_earnings():
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={end}&token={FINNHUB_KEY}"
    data = await safe_request_async(url, timeout=7)
    payload = safe_json(data)
    return payload.get("earningsCalendar", []) if isinstance(payload, dict) else []

async def fetch_market_news_async():
    cache_key = "general_news"
    now_ts = time.time()

    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (now_ts - cached.get("ts", 0)) < REQUEST_CACHE_TTL["news"]:
            return cached.get("data", [])

    url = f"https://finnhub.io/api/v1/news?category=general&token={FINNHUB_KEY}"
    res = await safe_request_async(url, timeout=7)
    data = safe_json(res)
    if isinstance(data, list):
        with REQUEST_CACHE_LOCK:
            REQUEST_CACHE[cache_key] = {"ts": now_ts, "data": data}
        return data
    return []

# =========================================
# DATA CARD + RV
# =========================================

class DataCard(MDCard):
    text = StringProperty("")

class RV(RecycleView):
    pass

KV = '''
#:import dp kivy.metrics.dp

<DataCard>:
    orientation: "vertical"
    size_hint_y: None
    height: max(lbl.texture_size[1] + dp(24), dp(45))
    padding: dp(12)
    spacing: dp(8)
    radius: [12, 12, 12, 12]
    elevation: 1
    md_bg_color: 1, 1, 1, 1

    MDLabel:
        id: lbl
        text: root.text
        markup: True
        size_hint_y: None
        height: self.texture_size[1]
        theme_text_color: "Primary"
        text_size: self.width, None
        valign: "middle"

<RV>:
    viewclass: "DataCard"
    scroll_type: ['bars', 'content']
    bar_width: dp(6)

    RecycleBoxLayout:
        default_size: None, None
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: "vertical"
        spacing: dp(12)
        padding: dp(12)
'''

Builder.load_string(KV)

# =========================================
# BASE TAB
# =========================================

class BaseTab(MDBoxLayout, MDTabsBase):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.is_loaded = False
        self._loading = False

        self.control_panel = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(0),
            padding=[dp(12), dp(12), dp(12), dp(8)],
            spacing=dp(8),
        )
        self.add_widget(self.control_panel)
        self.rv = RV()
        self.add_widget(self.rv)

    def set_rows(self, rows):
        data = [{"text": r} for r in (rows or [])]
        def _apply(_dt):
            self.rv.data = data
            self.rv.scroll_y = 1
        Clock.schedule_once(_apply, 0)

    def load_data_if_needed(self):
        if not self.is_loaded:
            self.is_loaded = True
            self.refresh_data()

    def refresh_data(self, *args, **kwargs):
        if self._loading:
            return
        self._loading = True
        self.set_rows(["[b]Ładowanie danych...[/b]"])
        run_coro(self._safe_fetch(*args, **kwargs))

    async def _safe_fetch(self, *args, **kwargs):
        try:
            rows = await self._fetch(*args, **kwargs)
            if rows is None: rows = []
            Clock.schedule_once(lambda dt: self.set_rows(rows), 0)
        except Exception as exc:
            Clock.schedule_once(lambda dt: self.set_rows([f"[color=#FF0000][b]Błąd pobierania:[/b][/color] {exc}"]), 0)
        finally:
            Clock.schedule_once(lambda dt: setattr(self, "_loading", False), 0)

    async def _fetch(self, *args, **kwargs):
        return []

# =========================================
# INFO TAB
# =========================================

class InfoTab(BaseTab):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(58)
        self.control_panel.add_widget(
            MDRaisedButton(
                text="Sprawdź Status Rynków",
                on_release=lambda x: self.refresh_data(),
                pos_hint={"center_x": 0.5},
            )
        )

    async def _fetch(self, *args, **kwargs):
        res = await safe_request_async(f"https://finnhub.io/api/v1/stock/market-status?exchange=US&token={FINNHUB_KEY}", timeout=6)
        payload = safe_json(res)
        is_open = bool(payload.get("isOpen", False)) if isinstance(payload, dict) else False

        rows = [
            "[b]RYNEK USA[/b]\nPre-Market: 04:00-09:30 ET\nSesja Główna: 09:30-16:00 ET\nPost-Market: 16:00-20:00 ET\n"
            f"Status teraz: [color=#00AA00]{'OTWARTY' if is_open else 'ZAMKNIĘTY'}[/color]",
            build_full_glossary(),
        ]

        now = datetime.now()
        for i in range(3):
            check_date = now + timedelta(days=i)
            day_name = check_date.strftime("%A")
            day_name_pl = {"Monday": "PONIEDZIAŁEK", "Tuesday": "WTOREK", "Wednesday": "ŚRODA", "Thursday": "CZWARTEK", "Friday": "PIĄTEK", "Saturday": "SOBOTA", "Sunday": "NIEDZIELA"}.get(day_name, day_name)

            if check_date.weekday() >= 5:
                rows.append(f"[b]{day_name_pl}[/b]\n[color=#FF0000]RYNKI ZAMKNIĘTE (weekend)[/color]")
            else:
                rows.append(f"[b]{day_name_pl}[/b]\n[color=#00AA00]{'OTWARTE' if i == 0 and is_open else 'PLANOWANE'}[/color]\nPre-Market: 04:00-09:30 ET | Sesja: 09:30-16:00 ET")
        return rows

# =========================================
# SCANNER TAB
# =========================================

class ScannerTab(BaseTab):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.static_tickers = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "PLTR", "AMZN"]
        self.control_panel.height = dp(118)

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        self.input_field = MDTextField(hint_text="Dodaj ticker", mode="rectangle")
        input_row.add_widget(self.input_field)
        input_row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        input_row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(input_row)

        self.control_panel.add_widget(MDRaisedButton(text="Skanuj", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    def add_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t and t not in self.static_tickers:
            self.static_tickers.append(t)
            self.refresh_data()

    def remove_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t in self.static_tickers:
            self.static_tickers.remove(t)
            self.refresh_data()

    async def _fetch(self, *args, **kwargs):
        gainers, actives = await asyncio.gather(
            fetch_top_gainers_by_type_async("day_gainers"),
            fetch_top_gainers_by_type_async("most_actives"),
        )

        all_tickers = list(dict.fromkeys(self.static_tickers + gainers[:12] + actives[:12]))[:35]
        bulk_data = await fetch_bulk(all_tickers)

        rows = []
        for sym in all_tickers:
            d = bulk_data.get(sym)
            if not d: continue

            comp_name = d.get("name", sym)
            price = safe(d.get("price", 0.0))
            change = safe(d.get("change", 0.0))
            pct = safe(d.get("pct", 0.0))
            vol = int(safe(d.get("vol", 0.0), 0.0))
            avg_vol = int(safe(d.get("avg_vol", 0.0), 0.0))
            cap = d.get("market_cap", 0.0)
            pe = d.get("pe", "N/A")
            session = get_session_snapshot(d)

            pre_p = safe(d.get("pre_price", d.get("pre", 0.0)))
            post_p = safe(d.get("post_price", d.get("post", 0.0)))
            macd_v = safe(d.get("macd", 0.0))
            sig_v = safe(d.get("signal", 0.0))
            hist_v = safe(d.get("hist", 0.0))

            rsi_val = 50.0
            closes = d.get("closes", [])
            if len(closes) >= 15:
                deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
                gains = [x if x > 0 else 0 for x in deltas]
                losses = [-x if x < 0 else 0 for x in deltas]
                period = 14
                avg_gain = sum(gains[:period]) / period if len(gains) >= period else 0
                avg_loss = sum(losses[:period]) / period if len(losses) >= period else 0
                if avg_loss == 0 and avg_gain > 0: rsi_val = 100.0
                elif avg_loss > 0: rsi_val = 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

            sig_txt, sig_col = get_signal_info(rsi_val, macd_v, sig_v, hist_v)

            rows.append(
                f"{session['session_label']} [color=#008080][b]{sym}[/b][/color] [color=#555555]({comp_name})[/color]\n"
                f"Sygnał: [b][color={sig_col}]{sig_txt}[/color][/b]\n"
                f"Cena: [b]{price:.2f} USD[/b] ([color={'#00AA00' if change >= 0 else '#FF0000'}{change:+.2f} | {pct:+.2f}%[/color])\n"
                f"Pre-Market: [b]{pre_p:.2f} USD[/b] | Post-Market: [b]{post_p:.2f} USD[/b]\n"
                f"Wolumen: {vol:,} (Śred. 10D: {avg_vol:,})\n"
                f"Kapitalizacja: {format_cap(cap)} | P/E: [b]{pe}[/b]\n"
                f"RSI: {color_wrap(fmt_num(rsi_val, 1), color_for_rsi(rsi_val))} | MACD: {color_wrap(fmt_num(macd_v, 3), color_for_macd(macd_v, sig_v))} | Hist: {format_histogram(hist_v)}"
            )
        return rows

# =========================================
# TICKER TAB
# =========================================

class TickerTab(BaseTab):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.control_panel.height = dp(58)
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        self.inp = MDTextField(hint_text="Ticker (np. TSLA)", mode="rectangle")
        row.add_widget(self.inp)
        row.add_widget(MDRaisedButton(text="Analizuj", on_release=self._on_search))
        self.control_panel.add_widget(row)

    def _on_search(self, *args):
        sym = self.inp.text.strip().upper()
        if sym: self.refresh_data(sym=sym)

    async def _fetch(self, *args, **kwargs):
        sym = (kwargs.get("sym") or self.inp.text.strip().upper() or "AAPL").strip().upper()
        d = await fetch_ticker(sym)

        if safe(d.get("price", 0.0)) == 0.0 and not d.get("closes"):
            return [f"[color=#FF0000]Nie znaleziono danych dla: {sym}[/color]"]

        price = safe(d.get("price", 0.0))
        change = safe(d.get("change", 0.0))
        pct = safe(d.get("pct", 0.0))
        vol = int(safe(d.get("vol", 0.0), 0.0))
        avg_vol = int(safe(d.get("avg_vol", 0.0), 0.0))
        cap = d.get("market_cap", 0.0)
        pe = d.get("pe", "N/A")
        eps = d.get("eps", "N/A")
        high52, low52 = safe(d.get("high52", 0.0)), safe(d.get("low52", 0.0))
        day_high, day_low = safe(d.get("day_high", 0.0)), safe(d.get("day_low", 0.0))
        prev_close = safe(d.get("prev_close", 0.0))

        closes = d.get("closes", [])
        macd_v, sig_v, hist_v = macd(closes)
        session = get_session_snapshot(d)

        rsi_val = 50.0
        if len(closes) >= 15:
            deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
            gains = [x if x > 0 else 0 for x in deltas]
            losses = [-x if x < 0 else 0 for x in deltas]
            period = 14
            avg_gain = sum(gains[:period]) / period if len(gains) >= period else 0
            avg_loss = sum(losses[:period]) / period if len(losses) >= period else 0
            if avg_loss == 0 and avg_gain > 0: rsi_val = 100.0
            elif avg_loss > 0: rsi_val = 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

        signal_text, signal_color = get_signal_info(rsi_val, macd_v, sig_v, hist_v)
        earnings_reaction = d.get("earnings_reaction", "Brak danych")

        row = (
            f"[b][color=#0000FF]{d.get('name', sym)} ({sym})[/color][/b]\n"
            f"Sesja: {session['session_label']}\n"
            f"Zmiana: [b][color={'#00AA00' if change >= 0 else '#FF0000'}{change:+.2f} USD | {pct:+.2f}%[/color][/b]\n"
            f"Rekomendacja: [b][color={signal_color}]{signal_text}[/color][/b]\n"
            f"-------------------------------------------------\n"
            f"[b]DANE RYNKOWE[/b]\nCena sesyjna: [b]{price:.2f} USD[/b]\nPrev Close: {prev_close:.2f}\n"
            f"Wolumen: [b]{vol:,}[/b] | Średni 10D: [b]{avg_vol:,}[/b]\n"
            f"Zakres Dzień: {day_low:.2f} - {day_high:.2f} USD | Zakres 52W: {low52:.2f} - {high52:.2f} USD\n"
            f"Pre-Market: {safe(d.get('pre_price')):.2f} | Post-Market: {safe(d.get('post_price')):.2f}\n"
            f"-------------------------------------------------\n"
            f"[b]FUNDAMENTY[/b]\nKapitalizacja: {format_cap(cap)} | P/E: {pe} | EPS: {eps}\n"
            f"-------------------------------------------------\n"
            f"[b]WYNIKI I REAKCJA[/b]\nNastępny raport: {d.get('next_earnings', 'Brak danych')}\n"
            f"Reakcja po poprzednim raporcie: {earnings_reaction}\n"
            f"-------------------------------------------------\n"
            f"[b]TECHNIKA[/b]\nRSI: [color={color_for_rsi(rsi_val)}]{rsi_val:.1f}[/color] | MACD: {macd_v:.3f} | Hist: {format_histogram(hist_v)}"
        )
        return [row]

# =========================================
# EARNINGS + NEWS TABS
# =========================================

class EarningsTab(BaseTab):
    async def _fetch(self, *args, **kwargs):
        earnings = await fetch_earnings()
        if not earnings: return ["Brak zaplanowanych wyników w ciągu najbliższych 7 dni."]
        rows = ["[b][color=#00AA00]Kalendarz wyników — następne 7 dni[/color][/b]"]
        earnings = sorted(earnings, key=lambda x: (x.get("date", ""), x.get("symbol", "")))
        for e in earnings[:30]:
            rows.append(f"• [b]{e.get('date', '—')}[/b] — [color=#008080]{e.get('symbol', '—')}[/color] | EPS est.: {e.get('epsEstimate', 'N/A')}")
        return rows

class NewsFilteredTab(BaseTab):
    def __init__(self, keywords, **kw):
        self.keywords = [k.lower() for k in keywords]
        super().__init__(**kw)
        self.control_panel.height = dp(58)
        self.control_panel.add_widget(MDRaisedButton(text=f"Odśwież", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    async def _fetch(self, *args, **kwargs):
        news_list = await fetch_market_news_async()
        filtered = []
        for n in news_list:
            text_to_search = (str(n.get("headline", "")) + " " + str(n.get("summary", ""))).lower()
            if any(kw in text_to_search for kw in self.keywords): filtered.append(n)

        if not filtered: return ["Brak nowych wiadomości rynkowych dla tej kategorii."]
        rows = []
        for n in filtered[:20]:
            dt = datetime.fromtimestamp(n.get('datetime', time.time())).strftime('%Y-%m-%d %H:%M')
            rows.append(f"[b][color=#0000FF]{n.get('headline', '')}[/color][/b]\n[color=#888888]{dt} | Żródło: {n.get('source', 'Unknown')}[/color]\n{n.get('summary', '')}\n")
        return rows

# =========================================
# CFD TAB
# =========================================

class CFDTab(BaseTab):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.control_panel.height = dp(58)
        self.control_panel.add_widget(MDRaisedButton(text="Analizuj Rynek CFD", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    async def _fetch(self, *args, **kwargs):
        universe = await fetch_dynamic_universe_async(limit=20)
        cfd_universe = ["CL=F", "GC=F", "NQ=F", "ES=F", "BTC-USD", "EURUSD=X"]
        required = list(dict.fromkeys(universe + cfd_universe))[:30]

        bulk_data = await fetch_bulk(required)
        rows = []

        for sym in required:
            d = bulk_data.get(sym)
            if not d: continue
            price = safe(d.get("price", 0.0))
            if price <= 0: continue

            closes = d.get("closes", [])
            tp, sl = make_tp_sl(price, 0.03, 0.02)
            macd_v, sig_v, hist_v = macd(closes)

            rsi_val = 50.0
            if len(closes) >= 15:
                deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
                gains = [x if x > 0 else 0 for x in deltas]
                losses = [-x if x < 0 else 0 for x in deltas]
                period = 14
                avg_gain = sum(gains[:period]) / period if len(gains) >= period else 0
                avg_loss = sum(losses[:period]) / period if len(losses) >= period else 0
                if avg_loss > 0: rsi_val = 100.0 - (100.0 / (1.0 + (avg_gain / avg_loss)))

            sig_txt, sig_col = get_signal_info(rsi_val, macd_v, sig_v, hist_v)
            if sig_txt == "NEUTRALNE": continue

            rows.append(
                f"[b][color={sig_col}]{sig_txt}[/color][/b] | [b]{d.get('name', sym)} ({sym})[/b]\n"
                f"Cena: {price:.2f} | TP: [color=#00AA00]{tp:.2f}[/color] | SL: [color=#FF3333]{sl:.2f}[/color]\n"
                f"RSI: {rsi_val:.1f} | MACD: {macd_v:.3f} | Hist: {hist_v:.3f}"
            )
        return rows if rows else ["Brak silnych sygnałów technicznych w tym momencie."]

# =========================================
# MAIN APP
# =========================================

class StockScanner(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.theme_style = "Light"

        self._scheduler_started = False
        self._scheduler_running = False
        self.app_ready = False

        screen = MDScreen()
        self.tabs = MDTabs()
        screen.add_widget(self.tabs)

        self.info_tab = InfoTab(title="Info")
        self.scanner_tab = ScannerTab(title="Skaner")
        self.ticker_tab = TickerTab(title="Ticker")
        self.earnings_tab = EarningsTab(title="Wyniki")
        self.cfd_tab = CFDTab(title="CFD/Własne")

        self.news_pr_tab = NewsFilteredTab(title="Kat PR", keywords=['partnership', 'press release', 'announces', 'revenue', 'catalyst'])
        self.news_ai_tab = NewsFilteredTab(title="Kat AI", keywords=['ai', 'artificial intelligence', 'chatgpt', 'nvidia'])
        self.news_ma_tab = NewsFilteredTab(title="Kat M&A", keywords=['merger', 'acquisition', 'buyout', 'acquires'])
        self.news_fda_tab = NewsFilteredTab(title="Kat FDA", keywords=['fda', 'clinical', 'trial', 'phase', 'biotech', 'approval'])

        self.tabs.add_widget(self.info_tab)
        self.tabs.add_widget(self.scanner_tab)
        self.tabs.add_widget(self.ticker_tab)
        self.tabs.add_widget(self.earnings_tab)
        self.tabs.add_widget(self.news_pr_tab)
        self.tabs.add_widget(self.news_ai_tab)
        self.tabs.add_widget(self.news_ma_tab)
        self.tabs.add_widget(self.news_fda_tab)
        self.tabs.add_widget(self.cfd_tab)
        return screen

    def on_start(self):
        self.app_ready = True
        self.info_tab.load_data_if_needed()
        self.scanner_tab.load_data_if_needed()
        self.cfd_tab.load_data_if_needed()

        self._start_background_scheduler()
        Clock.schedule_interval(self._refresh_ticker_if_needed, 60)

    def _scheduler_loop(self):
        while self._scheduler_running:
            try:
                if self.app_ready:
                    Clock.schedule_once(self.refresh_all_tabs, 0)
            except Exception as exc:
                print(f"scheduler error: {exc}")
            time.sleep(60)

    def _start_background_scheduler(self):
        if self._scheduler_started: return
        self._scheduler_started = True
        self._scheduler_running = True
        threading.Thread(target=self._scheduler_loop, daemon=True).start()

    def refresh_all_tabs(self, dt):
        if not getattr(self, "app_ready", False): return

        delay = 0.0
        for tab in getattr(self, "tabs_instances", []):
            if isinstance(tab, (TickerTab, NewsFilteredTab)):
                continue
            if hasattr(tab, "refresh_data"):
                Clock.schedule_once(lambda dt, t=tab: t.refresh_data(), delay)
                delay += 3.0

    def _refresh_ticker_if_needed(self, dt):
        sym = self.ticker_tab.inp.text.strip().upper()
        if sym: self.ticker_tab.refresh_data(sym=sym)

    def on_stop(self):
        self._scheduler_running = False
        try:
            if ASYNC_LOOP and ASYNC_LOOP.is_running():
                run_coro(HTTP_CLIENT.aclose())
        except Exception:
            pass

    @property
    def tabs_instances(self):
        return [
            self.info_tab, self.scanner_tab, self.ticker_tab, self.earnings_tab,
            self.news_pr_tab, self.news_ai_tab, self.news_ma_tab, self.news_fda_tab, self.cfd_tab,
        ]

if __name__ == "__main__":
    StockScanner().run()
