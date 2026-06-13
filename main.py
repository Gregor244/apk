# =========================================
# STOCK SCANNER PRO - LIGHT HYBRID VERSION
# RecycleView per tab + incremental loading
# =========================================

import asyncio
import re
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus
from urllib.parse import quote_plus

import certifi
import httpx

from kivy.config import Config
Config.set("graphics", "multisamples", "0")
Config.set("kivy", "maxfps", "60")

from kivy.clock import Clock
Clock.max_iteration = 120

from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.recycleview import RecycleView

from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.textfield import MDTextField

# =========================================
# CONFIG
# =========================================

HEADERS = {"User-Agent": "Mozilla/5.0"}
FINNHUB_KEY = "d82t3s1r01ql4onfbbngd82t3s1r01ql4onfbbo0"

HTTP_CLIENT = httpx.AsyncClient(
    headers=HEADERS,
    verify=certifi.where(),
    timeout=10.0,
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    http2=True,
)

REQUEST_DELAY = 0.15
MAX_RETRIES = 2

REQUEST_CACHE = {}
REQUEST_CACHE_LOCK = threading.Lock()
REQUEST_CACHE_TTL = {
    "screener": 120,
    "ticker": 90,
    "company": 180,
    "news": 120,
}

LAST_REQUEST_TIME = {}
RATE_LIMIT_LOCK = asyncio.Lock()

ASYNC_LOOP = None
ASYNC_LOOP_READY = threading.Event()

NASDAQ_CORE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD",
    "PLTR", "NFLX", "AVGO", "ORCL", "COST", "QCOM", "MU"
]

GPW_CORE = [
    "CDR.WA", "PKO.WA", "PEO.WA", "PZU.WA", "PKN.WA",
    "DNP.WA", "LPP.WA", "ALE.WA", "JSW.WA", "KGH.WA",
    "MBK.WA", "SPL.WA", "BHW.WA", "CCC.WA"
]

# =========================================
# ASYNC LOOP
# =========================================

def start_async_loop():
    global ASYNC_LOOP
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    ASYNC_LOOP = loop
    ASYNC_LOOP_READY.set()
    loop.run_forever()

threading.Thread(target=start_async_loop, daemon=True).start()

def run_coro(coro):
    if ASYNC_LOOP is None or not ASYNC_LOOP.is_running():
        try:
            coro.close()
        except Exception:
            pass
        return None
    return asyncio.run_coroutine_threadsafe(coro, ASYNC_LOOP)

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
    return f"{v:.2f}"

LOCAL_TZ = ZoneInfo("Europe/Warsaw")
NY_TZ = ZoneInfo("America/New_York")

def timestamp_text():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def local_time_text():
    return datetime.now(LOCAL_TZ).strftime("%d.%m.%Y %H:%M:%S %Z")

def next_us_market_open_text(now=None):
    try:
        now_ny = (now.astimezone(NY_TZ) if getattr(now, "tzinfo", None) else datetime.now(NY_TZ))
    except Exception:
        now_ny = datetime.now(NY_TZ)

    next_open = now_ny.replace(hour=9, minute=30, second=0, microsecond=0)
    if now_ny.weekday() >= 5 or now_ny >= next_open:
        days = 1 if now_ny.weekday() < 4 else (7 - now_ny.weekday())
        next_open = (now_ny + timedelta(days=days)).replace(hour=9, minute=30, second=0, microsecond=0)
        while next_open.weekday() >= 5:
            next_open += timedelta(days=1)

    local_open = next_open.astimezone(LOCAL_TZ)
    return f"{local_open.strftime('%d.%m.%Y %H:%M:%S %Z')} (ET: {next_open.strftime('%d.%m.%Y %H:%M:%S %Z')})"

def us_market_hours_text_local():
    """Render the U.S. session hours in ET and local CET/CEST time."""
    try:
        now_ny = datetime.now(NY_TZ)
        base_date = now_ny.date()
        pre_start = datetime(base_date.year, base_date.month, base_date.day, 4, 0, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        pre_end = datetime(base_date.year, base_date.month, base_date.day, 9, 30, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        reg_end = datetime(base_date.year, base_date.month, base_date.day, 16, 0, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        post_end = datetime(base_date.year, base_date.month, base_date.day, 20, 0, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        return (
            "[b]Rynek USA — godziny sesji (ET / czas lokalny CET/CEST)[/b]\n"
            f"• [b]Pre-Market[/b]: 04:00–09:30 ET / {pre_start.strftime('%H:%M')}–{pre_end.strftime('%H:%M %Z')}\n"
            f"• [b]Sesja główna[/b]: 09:30–16:00 ET / {pre_end.strftime('%H:%M')}–{reg_end.strftime('%H:%M %Z')}\n"
            f"• [b]Post-Market[/b]: 16:00–20:00 ET / {reg_end.strftime('%H:%M')}–{post_end.strftime('%H:%M %Z')}\n"
            "• [b]Weekend[/b]: rynek zamknięty"
        )
    except Exception:
        return (
            "[b]Rynek USA — godziny sesji[/b]\n"
            "• [b]Pre-Market[/b]: 04:00–09:30 ET\n"
            "• [b]Sesja główna[/b]: 09:30–16:00 ET\n"
            "• [b]Post-Market[/b]: 16:00–20:00 ET\n"
            "• [b]Weekend[/b]: rynek zamknięty"
        )

def market_status():
    ny = datetime.now(NY_TZ)
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

def normalize_company_name(symbol, name=None):
    symbol = (symbol or "").strip().upper()
    cleaned = (name or "").strip()
    base = symbol.replace(".WA", "").replace(".PL", "")
    fallback = {
        "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA",
        "AMD": "Advanced Micro Devices", "META": "Meta Platforms",
        "TSLA": "Tesla", "PLTR": "Palantir Technologies", "AMZN": "Amazon",
        "CDR": "CD Projekt", "PKO": "PKO BP", "PEO": "Bank Pekao",
        "PZU": "PZU", "PKN": "Orlen", "DNP": "Dino Polska",
        "LPP": "LPP", "ALE": "Allegro", "JSW": "JSW", "KGH": "KGHM",
        "MBK": "mBank", "SPL": "Santander Bank Polska",
        "BHW": "Bank Handlowy", "CCC": "CCC",
    }
    if cleaned and cleaned.upper() != symbol:
        return cleaned
    return fallback.get(base, cleaned or base or symbol)

def make_tp_sl(price, tp_pct=0.03, sl_pct=0.02):
    price = safe(price, 0.0)
    return price * (1 + tp_pct), price * (1 - sl_pct)

def safe_json(response):
    try:
        if not response or getattr(response, "status_code", 0) != 200:
            return {}
        return response.json()
    except Exception:
        return {}

def ema(data, period):
    if not data:
        return []
    k = 2 / (period + 1)
    out = [data[0]]
    for price in data[1:]:
        out.append(price * k + out[-1] * (1 - k))
    return out

def sma(data, period):
    if not data:
        return 0.0
    if len(data) >= period:
        return round(sum(data[-period:]) / period, 2)
    return round(sum(data) / len(data), 2)

def macd(closes):
    closes = [safe(x) for x in closes if x is not None]
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
    macd_v = macd_line[-1]
    sig_v = signal_line[-1]
    hist = macd_v - sig_v
    return round(macd_v, 3), round(sig_v, 3), round(hist, 3)

def calc_rsi(closes, period=14):
    closes = [safe(x) for x in closes if x is not None]
    if len(closes) < period + 1:
        return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100.0 - (100.0 / (1.0 + rs)), 2)

def color_for_rsi(rsi):
    if rsi <= 30: return "#006600"
    if rsi <= 40: return "#00AA00"
    if rsi >= 70: return "#FF0000"
    if rsi >= 60: return "#FF9900"
    return "#888888"

def color_for_macd(macd_val, signal_val):
    return "#00AA00" if macd_val > signal_val else "#FF0000"

def format_histogram(hist):
    if hist > 0: return color_wrap(fmt_num(hist, 3, signed=True), "#00AA00")
    if hist < 0: return color_wrap(fmt_num(hist, 3, signed=True), "#FF0000")
    return color_wrap(fmt_num(hist, 3, signed=True), "#888888")

def build_full_glossary():
    return (
        "[b]SŁOWNIK WSKAŹNIKÓW I POJĘĆ[/b]\n"
        "• [b]SMA[/b] — średnia krocząca; cena powyżej SMA zwykle wskazuje przewagę trendu wzrostowego.\n"
        "• [b]EMA[/b] — wykładnicza średnia krocząca; szybciej reaguje niż SMA.\n"
        "• [b]RSI[/b] — oscylator 0–100; poniżej 30 często wyprzedanie, powyżej 70 wykupienie.\n"
        "• [b]MACD[/b] — różnica między dwiema średnimi EMA; nad linią sygnału wzmacnia scenariusz wzrostowy.\n"
        "• [b]Histogram[/b] — MACD minus sygnał; dodatni pokazuje przewagę momentum.\n"
        "• [b]P/E[/b] — cena do zysku; niższy bywa atrakcyjny, ale porównuj spółki z tej samej branży.\n"
        "• [b]EPS[/b] — zysk na akcję.\n"
        "• [b]Market Cap[/b] — kapitalizacja rynkowa spółki.\n"
        "• [b]Volume[/b] — wolumen, liczba akcji/kontraktów w obrocie.\n"
        "• [b]Prev Close[/b] — cena zamknięcia poprzedniej sesji.\n"
        "• [b]Pre-Market[/b] — handel przed sesją główną.\n"
        "• [b]Post-Market[/b] — handel po sesji głównej.\n"
        "• [b]TP[/b] — take profit, poziom realizacji zysku.\n"
        "• [b]SL[/b] — stop loss, poziom ograniczenia straty.\n"
    )

US_MARKET_HOURS_TEXT = (
    "[b]Rynek USA — godziny sesji (czas Eastern / Nowy Jork)[/b]\n"
    "• [b]Pre-Market[/b]: 04:00–09:30\n"
    "• [b]Sesja główna[/b]: 09:30–16:00\n"
    "• [b]Post-Market[/b]: 16:00–20:00\n"
    "• [b]Weekend[/b]: rynek zamknięty"
)

def get_pl_session_hint(now=None):
    try:
        tz = ZoneInfo("America/New_York")
        now = now.astimezone(tz) if getattr(now, "tzinfo", None) else datetime.now(tz)
    except Exception:
        now = now or datetime.now()
    if now.weekday() >= 5:
        return "ZAMKNIĘTY"
    minutes = now.hour * 60 + now.minute
    if 4 * 60 <= minutes < 9 * 60 + 30:
        return "PREMARKET"
    if 9 * 60 + 30 <= minutes < 16 * 60:
        return "OTWARTY"
    if 16 * 60 <= minutes < 20 * 60:
        return "POSTMARKET"
    return "ZAMKNIĘTY"

def build_catalyst_heading(title, query):
    return f"[ref={search_url_from_query(query)}][b]{title}[/b][/ref]"


def search_url_from_query(query):
    return f"https://www.google.com/search?q={quote_plus(query)}"

def sanitize_prev_close(price, prev_close, closes):
    price = safe(price, 0.0)
    prev_close = safe(prev_close, 0.0)
    closes = [safe(x) for x in closes if x is not None and safe(x) > 0]
    if prev_close <= 0 and len(closes) >= 2:
        prev_close = closes[-2]
    if price > 0 and prev_close > 0:
        ratio = price / prev_close
        if ratio > 3.0 or ratio < 0.33:
            if len(closes) >= 2 and closes[-2] > 0:
                prev_close = closes[-2]
    return prev_close

def run_async_if_ready(coro):
    if ASYNC_LOOP is None or not ASYNC_LOOP.is_running():
        try:
            coro.close()
        except Exception:
            pass
        return None
    return asyncio.run_coroutine_threadsafe(coro, ASYNC_LOOP)

def add_cache_items(app, items, visible_symbols=None, keep_symbols=None):
    visible_symbols = list(dict.fromkeys(visible_symbols or items.keys()))
    keep_symbols = list(dict.fromkeys(keep_symbols or []))
    with REQUEST_CACHE_LOCK:
        old = getattr(app, "shared_cache", {})
        new = {}
        for sym in visible_symbols:
            if sym in items:
                new[sym] = items[sym]
            elif sym in old:
                new[sym] = old[sym]
        for sym in keep_symbols:
            if sym in old:
                new[sym] = old[sym]
        app.shared_cache = new
        if len(app.shared_cache) > 300:
            trimmed = list(app.shared_cache.items())[-300:]
            app.shared_cache = dict(trimmed)
        app.cache_time = datetime.now()

def resolve_company_name_for_tab(app, symbol):
    symbol = (symbol or "").strip().upper()
    cache = getattr(app, "shared_cache", {}) or {}
    if symbol in cache and cache[symbol].get("name"):
        return cache[symbol].get("name")
    return normalize_company_name(symbol, symbol)

# Zabezpieczające metody tekstowe dla zakładki Katalizatory
def is_fda_pdufa_title(t):
    return any(x in t for x in ["fda", "pdufa", "adcom", "advisory committee", "crl", "clinical", "trial", "readout", "topline"])

def is_merger_mna_title(t):
    return any(x in t for x in ["merger", "acquisition", "takeover", "buyout", "sale", "private"])

def is_buyout_interest_title(t):
    return any(x in t for x in ["interest", "exploring", "strategic alternatives"])

def is_contract_ai_title(t):
    return any(x in t for x in ["contract", "ai", "artificial intelligence", "deal", "partnership"])

# =========================================
# HTTP
# =========================================

async def safe_request_async(url, timeout=8, retries=MAX_RETRIES):
    host = url.split("/")[2] if "://" in url else "default"
    for i in range(retries):
        async with RATE_LIMIT_LOCK:
            now = time.time()
            diff = now - LAST_REQUEST_TIME.get(host, 0)
            if diff < REQUEST_DELAY:
                await asyncio.sleep(REQUEST_DELAY - diff)
            LAST_REQUEST_TIME[host] = time.time()
        try:
            response = await HTTP_CLIENT.get(url, timeout=timeout)
            if response.status_code == 200:
                return response
            if response.status_code == 404:
                return response
            if response.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(1.1 * (i + 1))
                continue
            return response
        except Exception:
            await asyncio.sleep(0.8 * (i + 1))
    class Dummy:
        status_code = 0
        def json(self):
            return {}
    return Dummy()

def _extract_chart_payload(yahoo_json):
    result = yahoo_json.get("chart", {}).get("result", [])
    if not result:
        return {}, {}
    payload = result[0]
    quote = payload.get("indicators", {}).get("quote", [{}])[0]
    return payload, quote

def _extract_intraday_session_prices(chart_payload, chart_quote):
    """Derive pre-market / regular / post-market prices from 1m intraday data."""
    try:
        ts_list = chart_payload.get("timestamp", []) or []
        closes = chart_quote.get("close", []) or []
        n = min(len(ts_list), len(closes))
        if n <= 0:
            return 0.0, 0.0, 0.0

        tz_ny = ZoneInfo("America/New_York")
        pre_last = 0.0
        regular_last = 0.0
        post_last = 0.0

        for ts, close in zip(ts_list[:n], closes[:n]):
            if close is None:
                continue
            try:
                dt = datetime.fromtimestamp(int(ts), ZoneInfo("UTC")).astimezone(tz_ny)
            except Exception:
                continue
            if dt.weekday() >= 5:
                continue
            minutes = dt.hour * 60 + dt.minute
            price = safe(close, 0.0)
            if 4 * 60 <= minutes < 9 * 60 + 30:
                pre_last = price
            elif 9 * 60 + 30 <= minutes < 16 * 60:
                regular_last = price
            elif 16 * 60 <= minutes < 20 * 60:
                post_last = price

        return pre_last, regular_last, post_last
    except Exception:
        return 0.0, 0.0, 0.0

def _fmt_session_price(v):
    v = safe(v, 0.0)
    return f"{v:.2f} USD" if v > 0 else "—"

def session_change_tv(session_state, prev_close, pre_price=0.0, post_price=0.0, last_trade_price=0.0):
    pc = safe(prev_close, 0.0)
    pre = safe(pre_price, 0.0)
    post = safe(post_price, 0.0)
    last = safe(last_trade_price, 0.0)

    if pc <= 0:
        return 0.0, 0.0

    # 1. wybór najlepszej dostępnej ceny w zależności od sesji
    if session_state == "PREMARKET":
        price = pre or last or pc

    elif session_state == "OTWARTY":
        # TradingView-like: zawsze ostatni trade
        price = last or pre or pc

    elif session_state == "POSTMARKET":
        price = post or last or pc

    else:
        price = pc

    # 2. fallback bezpieczeństwa
    if price <= 0:
        return 0.0, 0.0

    # 3. real-time change vs prev close
    diff = price - pc
    pct = (diff / pc) * 100

    return round(diff, 4), round(pct, 2)
# =========================================
# FEEDS
# =========================================

async def fetch_top_gainers_by_type_async(scr_id="day_gainers"):
    cache_key = ("screener", scr_id)
    now_ts = time.time()
    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (now_ts - cached.get("ts", 0)) < REQUEST_CACHE_TTL["screener"]:
            return list(cached.get("data", []))
    count = 15 if "gainers" in scr_id else 18
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

async def fetch_dynamic_universe_async(limit=60):
    screeners = ["day_gainers", "most_actives", "day_losers"]
    results = await asyncio.gather(*[fetch_top_gainers_by_type_async(s) for s in screeners], return_exceptions=True)
    tickers = []
    for res in results:
        if isinstance(res, list):
            tickers.extend(res[:10])
    tickers.extend(NASDAQ_CORE + GPW_CORE)
    return list(dict.fromkeys(tickers))[:max(1, int(limit))]

async def fetch_company_names(symbols):
    unique = list(dict.fromkeys([s for s in [str(x).strip().upper() for x in symbols if x] if s]))
    async def _one(sym):
        return sym, await fetch_ticker_name(sym)
    results = await asyncio.gather(*[_one(sym) for sym in unique], return_exceptions=True)
    out = {}
    for item in results:
        if isinstance(item, Exception):
            continue
        sym, name = item
        out[sym] = name
    return out
# ================================
# MARKET DATA ENGINE v3 (CORE)
# ================================

def build_price_state(prev_close, pre_price=0.0, post_price=0.0, last_trade=0.0, regular_price=0.0):
    return {
        "prev_close": safe(prev_close),
        "pre": safe(pre_price),
        "post": safe(post_price),
        "last": safe(last_trade),
        "regular": safe(regular_price)
    }


def get_session_state(raw_state):
    s = str(raw_state or "").upper().strip()
    if s == "PRE":
        return "PREMARKET"
    if s == "POST":
        return "POSTMARKET"
    if s == "REGULAR":
        return "OTWARTY"
    return market_status()


def select_active_price(session_state, ps):
    pc = ps["prev_close"]
    if pc <= 0:
        return 0.0

    if session_state == "PREMARKET":
        return ps["pre"] or ps["last"] or pc

    if session_state == "OTWARTY":
        return ps["last"] or ps["regular"] or pc

    if session_state == "POSTMARKET":
        return ps["post"] or ps["last"] or pc

    return pc


def calc_change(ps, session_state):
    pc = ps["prev_close"]
    price = select_active_price(session_state, ps)

    if pc <= 0 or price <= 0:
        return 0.0, 0.0

    diff = price - pc
    pct = (diff / pc) * 100

    return round(diff, 4), round(pct, 2)


def compute_momentum(ind, pct, session_state):
    score = 0

    if ind["rsi"] < 30:
        score += 2
    elif ind["rsi"] > 70:
        score -= 2
    else:
        score += 0.5 if ind["rsi"] > 50 else -0.5

    score += 2 if ind["hist"] > 0 else -2
    score += 1 if pct > 0 else -1

    if session_state in ("PREMARKET", "POSTMARKET"):
        score *= 0.8

    return round(score, 2)


def detect_regime(ind, pct):
    if ind["rsi"] > 70 and ind["hist"] < 0:
        return "DISTRIBUTION"
    if ind["rsi"] < 30 and ind["hist"] > 0:
        return "ACCUMULATION"
    if abs(pct) < 0.3:
        return "SIDEWAYS"
    return "TREND"
    
async def fetch_ticker_name(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return symbol
    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(("company", symbol))
        if cached and (time.time() - cached.get("ts", 0)) < REQUEST_CACHE_TTL["company"]:
            return cached.get("data", symbol)
    q = await safe_request_async(f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}", timeout=6)
    name = symbol
    if q.status_code == 200:
        payload = safe_json(q)
        quote_items = payload.get("quoteResponse", {}).get("result", []) if isinstance(payload, dict) else []
        if quote_items:
            item = quote_items[0]
            name = item.get("shortName") or item.get("longName") or symbol
    with REQUEST_CACHE_LOCK:
        REQUEST_CACHE[("company", symbol)] = {"ts": time.time(), "data": name}
    return normalize_company_name(symbol, name)

async def fetch_prev_earnings_reaction(symbol):
    try:
        earnings_url = f"https://finnhub.io/api/v1/stock/earnings?symbol={symbol}&token={FINNHUB_KEY}"
        res = await safe_request_async(earnings_url, timeout=8)
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
        try:
            e_date = datetime.strptime(period[:10], "%Y-%m-%d").date()
        except Exception:
            return "Brak danych"
        start_ts = int(datetime.combine(e_date - timedelta(days=2), datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(e_date + timedelta(days=4), datetime.min.time()).timestamp())
        react_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start_ts}&period2={end_ts}&interval=1d"
        react_req = await safe_request_async(react_url, timeout=8)
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
        return {
            "symbol": "", "name": "", "price": 0.0, "session_price": 0.0, "session_state": "ZAMKNIĘTY",
            "prev_close": 0.0, "vol": 0.0, "avg_vol": 0.0, "change": 0.0, "pct": 0.0,
            "market_cap": 0.0, "pe": "N/A", "eps": "N/A", "high52": 0.0, "low52": 0.0,
            "day_high": 0.0, "day_low": 0.0, "pre_price": 0.0, "post_price": 0.0,
            "pre": 0.0, "post": 0.0, "macd": 0.0, "signal": 0.0, "hist": 0.0,
            "closes": [], "year_high": 0.0, "year_low": 0.0, "next_earnings": "Brak danych",
            "prev_earnings_period": "Brak danych", "prev_earnings_surprise": "Brak danych",
            "earnings_reaction": "Brak danych",
        }

    cache_key = ("ticker", symbol)
    now_ts = time.time()
    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (now_ts - cached.get("ts", 0)) < REQUEST_CACHE_TTL["ticker"]:
            return dict(cached.get("data", {}))

    yahoo_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1y"
    intraday_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d&includePrePost=true"
    quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
    profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={FINNHUB_KEY}"
    metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={FINNHUB_KEY}"
    earnings_url = f"https://finnhub.io/api/v1/calendar/earnings?symbol={symbol}&from={(datetime.now()).strftime('%Y-%m-%d')}&to={(datetime.now()+timedelta(days=90)).strftime('%Y-%m-%d')}&token={FINNHUB_KEY}"

    yahoo_res, intraday_res, quote_res, profile_res, metrics_res, earnings_res = await asyncio.gather(
        safe_request_async(yahoo_url, timeout=8),
        safe_request_async(intraday_url, timeout=8),
        safe_request_async(quote_url, timeout=6),
        safe_request_async(profile_url, timeout=6),
        safe_request_async(metrics_url, timeout=8),
        safe_request_async(earnings_url, timeout=8),
    )

    closes = []
    volumes = []
    regular_price = 0.0
    prev_close = 0.0
    session_price = 0.0
    session_state = market_status()
    day_high = 0.0
    day_low = 0.0
    year_high = 0.0
    year_low = 0.0
    pre_price = 0.0
    post_price = 0.0
    market_cap = 0.0
    pe = "N/A"
    eps = "N/A"
    next_earnings = "Brak danych"

    if getattr(yahoo_res, "status_code", 0) == 200:
        payload, quote = _extract_chart_payload(safe_json(yahoo_res))
        meta = payload.get("meta", {})
        closes = [x for x in quote.get("close", []) if x is not None]
        volumes = [x for x in quote.get("volume", []) if x is not None]
        regular_price = safe(meta.get("regularMarketPrice", 0.0))
        day_high = safe(meta.get("regularMarketDayHigh", meta.get("dayHigh", 0.0)))
        day_low = safe(meta.get("regularMarketDayLow", meta.get("dayLow", 0.0)))
        year_high = safe(meta.get("fiftyTwoWeekHigh", 0.0))
        year_low = safe(meta.get("fiftyTwoWeekLow", 0.0))
        pre_price = safe(meta.get("preMarketPrice", 0.0))
        post_price = safe(meta.get("postMarketPrice", 0.0))

    if getattr(intraday_res, "status_code", 0) == 200:
        intraday_payload, intraday_quote = _extract_chart_payload(safe_json(intraday_res))
        intraday_meta = intraday_payload.get("meta", {})
        raw_state = str(intraday_meta.get("marketState", "") or "").upper().strip()
        if raw_state == "PRE":
            session_state = "PREMARKET"
        elif raw_state == "POST":
            session_state = "POSTMARKET"
        elif raw_state == "REGULAR":
            session_state = "OTWARTY"

        prev_close = sanitize_prev_close(
            regular_price,
            safe(intraday_meta.get("previousClose", intraday_meta.get("chartPreviousClose", 0.0))),
            closes
        )

        pre_scan, regular_scan, post_scan = _extract_intraday_session_prices(intraday_payload, intraday_quote)

        meta_pre = safe(intraday_meta.get("preMarketPrice", 0.0))
        meta_post = safe(intraday_meta.get("postMarketPrice", 0.0))
        meta_regular = safe(intraday_meta.get("regularMarketPrice", 0.0))

        pre_price = pre_scan or meta_pre or pre_price
        post_price = post_scan or meta_post or post_price
        if regular_scan > 0:
            regular_price = regular_scan
        elif regular_price <= 0:
            regular_price = meta_regular

        if session_state == "PREMARKET":
            session_price = pre_price or meta_pre or meta_regular
        elif session_state == "POSTMARKET":
            session_price = post_price or meta_post or meta_regular
        else:
            session_price = meta_regular or regular_price

        if session_price <= 0:
            closes_i = [x for x in intraday_quote.get("close", []) if x is not None]
            if closes_i:
                session_price = safe(closes_i[-1])

        if regular_price <= 0 and session_price > 0:
            regular_price = session_price

        # If pre/post are still missing from intraday, prefer quote endpoint values.
        if pre_price <= 0:
            pre_price = safe(intraday_meta.get("preMarketPrice", 0.0))
        if post_price <= 0:
            post_price = safe(intraday_meta.get("postMarketPrice", 0.0))

    fh_q = {}
    if getattr(quote_res, "status_code", 0) == 200:
        q_payload = safe_json(quote_res)
        if isinstance(q_payload, dict):
            quote_items = q_payload.get("quoteResponse", {}).get("result", []) or []
            if quote_items:
                fh_q = quote_items[0]
                if regular_price <= 0:
                    regular_price = safe(fh_q.get("regularMarketPrice", 0.0))
                if prev_close <= 0:
                    prev_close = safe(fh_q.get("regularMarketPreviousClose", 0.0))
                if day_high <= 0:
                    day_high = safe(fh_q.get("regularMarketDayHigh", 0.0))
                if day_low <= 0:
                    day_low = safe(fh_q.get("regularMarketDayLow", 0.0))
                if pre_price <= 0:
                    pre_price = safe(fh_q.get("preMarketPrice", 0.0))
                if post_price <= 0:
                    post_price = safe(fh_q.get("postMarketPrice", 0.0))

    profile = safe_json(profile_res) if getattr(profile_res, "status_code", 0) == 200 else {}
    metrics = safe_json(metrics_res) if getattr(metrics_res, "status_code", 0) == 200 else {}
    earnings_data = safe_json(earnings_res) if getattr(earnings_res, "status_code", 0) == 200 else {}

    if isinstance(profile, dict):
        market_cap = safe(profile.get("marketCapitalization", 0.0)) * 1_000_000
    if isinstance(metrics, dict):
        metric = metrics.get("metric", {}) or {}
        pe_v = metric.get("peNormalizedAnnual") or metric.get("peExclExtraTTM") or metric.get("peTTM")
        eps_v = metric.get("epsTTM")
        if pe_v is not None:
            pe = f"{safe(pe_v):.2f}"
        if eps_v is not None:
            eps = f"{safe(eps_v):.2f}"

    if isinstance(earnings_data, dict):
        cal = earnings_data.get("earningsCalendar", []) or []
        if cal:
            next_earnings = cal[0].get("date", "Brak danych")

    active_price = session_price if session_price > 0 else regular_price
    if active_price <= 0:
        active_price = prev_close

   
    earnings_reaction = await fetch_prev_earnings_reaction(symbol)

    result = {
        "symbol": symbol,
        "name": normalize_company_name(symbol, profile.get("name", symbol) if isinstance(profile, dict) else symbol),
        "price": active_price,
        "regular_price": regular_price,
        "session_price": active_price,
        "session_state": session_state,
        "prev_close": prev_close,
        "vol": safe(volumes[-1]) if volumes else safe(fh_q.get("regularMarketVolume", 0.0)),
        "avg_vol": int(sum(volumes[-10:]) / 10) if len(volumes) >= 10 else (int(sum(volumes) / len(volumes)) if volumes else 0),
        "change": change,
        "pct": pct,
        "market_cap": market_cap,
        "pe": pe,
        "eps": eps,
        "high52": year_high,
        "low52": year_low,
        "day_high": day_high,
        "day_low": day_low,
        "pre_price": pre_price,
        "post_price": post_price,
        "pre": pre_price,
        "post": post_price,
        "macd": m,
        "signal": s,
        "hist": h,
        "closes": closes,
        "year_high": year_high,
        "year_low": year_low,
        "prev_earnings_period": "Brak danych",
        "prev_earnings_surprise": "Brak danych",
        "earnings_reaction": earnings_reaction,
        "next_earnings": next_earnings,
    }

    with REQUEST_CACHE_LOCK:
        REQUEST_CACHE[cache_key] = {"ts": now_ts, "data": dict(result)}

    snapshot = build_snapshot(symbol, {
    "prev_close": prev_close,
    "pre_price": pre_price,
    "post_price": post_price,
    "session_price": session_price,
    "regular_price": regular_price,
    "closes": closes,
    "raw_state": raw_state
})

result.update(snapshot)

async def fetch_bulk(symbols, chunk_size=4):
    unique = [s for s in dict.fromkeys([str(x).strip().upper() for x in symbols if x]) if s]
    results = {}
    sem = asyncio.Semaphore(max(1, int(chunk_size)))

    async def _worker(sym):
        async with sem:
            try:
                return sym, await fetch_ticker(sym)
            except Exception:
                return sym, None

    gathered = await asyncio.gather(*[_worker(sym) for sym in unique], return_exceptions=True)
    for item in gathered:
        if isinstance(item, Exception):
            continue
        sym, data = item
        if data:
            results[sym] = data
    return results

async def fetch_earnings():
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={end}&token={FINNHUB_KEY}"
    data = await safe_request_async(url, timeout=8)
    payload = safe_json(data)
    return payload.get("earningsCalendar", []) if isinstance(payload, dict) else []

# =========================================
# PRICE ENGINE
# =========================================

class PriceEngine:
    CACHE = {}
    LOCK = threading.Lock()
    TTL = 60

    @staticmethod
    def analyze(sym, closes, price, vol=0, avg_vol=0):
        now = time.time()
        key = (sym, len(closes), round(safe(price), 4))
        with PriceEngine.LOCK:
            cached = PriceEngine.CACHE.get(key)
            if cached and now - cached["ts"] < PriceEngine.TTL:
                return cached["data"]
        rsi = calc_rsi(closes)
        macd_v, sig_v, hist_v = macd(closes)
        sma14 = sma(closes, 14)
        sma30 = sma(closes, 30)
        sma50 = sma(closes, 50)
        sma90 = sma(closes, 90)
        score, signal_text, signal_color = PriceEngine.signal(
            rsi, macd_v, sig_v, hist_v, price, sma14, sma30, sma90, vol, avg_vol
        )
        result = {
            "rsi": rsi, "macd": macd_v, "sig": sig_v, "hist": hist_v,
            "sma14": sma14, "sma30": sma30, "sma50": sma50, "sma90": sma90,
            "score": score, "signal_text": signal_text, "signal_color": signal_color,
        }
        with PriceEngine.LOCK:
            PriceEngine.CACHE[key] = {"ts": now, "data": result}
        return result

    @staticmethod
    def signal(rsi, macd_v, sig_v, hist, price, sma14, sma30, sma90, volume, avg_volume):
        score = 0.0
        if rsi <= 30: score += 3
        elif rsi <= 40: score += 2
        elif rsi >= 70: score -= 3
        if macd_v > sig_v: score += 2
        else: score -= 1.5
        if hist > 0: score += 1
        else: score -= 1
        if price > sma14: score += 0.75
        if price > sma30: score += 0.5
        if price > sma90: score += 0.75
        if avg_volume > 0:
            if volume >= avg_volume: score += 0.5
            else: score -= 0.25
        bullish = sum([rsi <= 40, macd_v > sig_v, hist > 0, price > sma14, price > sma30])
        if score >= 5 and bullish >= 4: return score, "MOCNE KUP", "#006600"
        if score >= 2: return score, "KUP", "#00AA00"
        if score <= -4: return score, "MOCNE SPRZEDAJ", "#FF0000"
        if score <= -1: return score, "SPRZEDAJ", "#FF9900"
        return score, "NEUTRALNE", "#888888"

def build_snapshot(symbol, raw):
    closes = raw.get("closes", [])

    macd_v, signal_v, hist = macd(closes)

    ind = {
        "rsi": calc_rsi(closes),
        "macd": macd_v,
        "signal": signal_v,
        "hist": hist
    }

    ps = build_price_state(
        raw.get("prev_close"),
        raw.get("pre_price"),
        raw.get("post_price"),
        raw.get("session_price"),
        raw.get("regular_price")
    )

    session_state = get_session_state(raw.get("raw_state"))

    price = select_active_price(session_state, ps)
    diff, pct = calc_change(ps, session_state)

    return {
        "price": round(price, 4),
        "change": diff,
        "pct": pct,
        "momentum": compute_momentum(ind, pct, session_state),
        "regime": detect_regime(ind, pct),

        # keep indicators for UI tabs
        **ind
    }


# =========================================
# RECYCLERVIEW
# =========================================

class DataCard(MDCard):
    text = StringProperty("")

    def _update_height(self, texture_h=0):
        try:
            from kivy.metrics import dp as _dp
            self.height = max(_dp(84), float(texture_h) + _dp(22))
        except Exception:
            pass

class TabRV(RecycleView):
    pass

KV = '''
#:import dp kivy.metrics.dp

<DataCard>:
    orientation: "vertical"
    size_hint_y: None
    padding: dp(10)
    spacing: dp(6)
    radius: [12, 12, 12, 12]
    elevation: 1
    md_bg_color: 1, 1, 1, 1
    height: _body.texture_size[1] + dp(24) if _body.texture_size[1] > 0 else dp(84)

    MDLabel:
        id: _body
        text: root.text
        markup: True
        size_hint_y: None
        height: self.texture_size[1]
        text_size: self.width - dp(20), None
        halign: "left"
        valign: "top"
        color: 0, 0, 0, 1
        on_texture_size: root._update_height(self.texture_size[1])

<TabRV>:
    viewclass: "DataCard"
    scroll_type: ['bars', 'content']

    RecycleBoxLayout:
        default_size: None, dp(84)
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: "vertical"
        spacing: dp(8)
        padding: dp(8)
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
        self.full_rows = []
        self.visible_count = 0
        self.initial_visible = 12
        self.batch_size = 12
        self.max_visible = 60
        self._scroll_trigger_ts = 0.0

        self.control_panel = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(0),
            padding=[dp(8), dp(8), dp(8), dp(4)],
            spacing=dp(6),
        )
        self.add_widget(self.control_panel)

        self.more_button = MDRaisedButton(
            text="Pokaż więcej",
            size_hint_y=None,
            height=0,
            opacity=0,
            disabled=True,
            on_release=self.load_more,
        )
        self.control_panel.add_widget(self.more_button)

        self.rv = TabRV()
        self.rv.bind(scroll_y=self._on_scroll_y)
        self.add_widget(self.rv)

    def _update_more_button(self):
        has_more = len(self.full_rows) > self.visible_count
        if has_more:
            self.more_button.height = dp(36)
            self.more_button.opacity = 1
            self.more_button.disabled = False
        else:
            self.more_button.height = 0
            self.more_button.opacity = 0
            self.more_button.disabled = True

    def _apply_visible_rows(self, scroll_top=False):
        data = [{"text": r} for r in self.full_rows[:self.visible_count]]
        def _apply(_dt):
            self.rv.data = data
            self._update_more_button()
            if scroll_top:
                def _scroll_top(_dt2):
                    try:
                        self.rv.scroll_y = 1
                        self.rv.scroll_x = 0
                    except Exception:
                        pass
                Clock.schedule_once(_scroll_top, 0.15)
        Clock.schedule_once(_apply, 0)

    def set_rows(self, rows, reset=True):
        rows = list(rows or [])
        self.full_rows = rows
        if reset:
            self.visible_count = min(self.initial_visible, len(self.full_rows)) if self.initial_visible else len(self.full_rows)
        self.visible_count = min(self.visible_count, self.max_visible) if self.max_visible else self.visible_count
        if self.visible_count <= 0 and self.full_rows:
            self.visible_count = min(1, len(self.full_rows))
        self._apply_visible_rows(scroll_top=True)

    def load_more(self, *args):
        if not self.full_rows:
            return
        if self.visible_count >= len(self.full_rows):
            self._update_more_button()
            return
        self.visible_count = min(len(self.full_rows), self.visible_count + self.batch_size, self.max_visible or len(self.full_rows))
        self._apply_visible_rows(scroll_top=False)

    def _on_scroll_y(self, instance, value):
        if self._loading:
            return
        if self.visible_count >= len(self.full_rows):
            return
        if value < 0.08:
            now = time.time()
            if now - self._scroll_trigger_ts > 0.4:
                self._scroll_trigger_ts = now
                self.load_more()

    def load_data_if_needed(self):
        if not self.is_loaded:
            self.is_loaded = True
            self.refresh_data()

    def refresh_data(self, *args, **kwargs):
        if self._loading:
            return
        self._loading = True
        self.set_rows(["[b]Ładowanie danych...[/b]"], reset=True)
        fut = run_async_if_ready(self._safe_fetch(*args, **kwargs))
        if fut is None:
            self._loading = False

    async def _safe_fetch(self, *args, **kwargs):
        try:
            rows = await self._fetch(*args, **kwargs)
            if rows is None:
                rows = []
            self.set_rows(rows, reset=True)
        except Exception as exc:
            self.set_rows([f"[color=#FF0000][b]Błąd pobierania:[/b][/color] {exc}"], reset=True)
        finally:
            self._loading = False

    async def _fetch(self, *args, **kwargs):
        return []

# =========================================
# INFO TAB
# =========================================

class InfoTab(BaseTab):
    title = "Info"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.initial_visible = 4
        self.batch_size = 4
        self.max_visible = 12
        self.control_panel.height = dp(76)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(
            MDRaisedButton(
                text="Sprawdź Status Rynków",
                on_release=lambda x: self.refresh_data(),
                pos_hint={"center_x": 0.5},
            )
        )
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        res = await safe_request_async(
            f"https://finnhub.io/api/v1/stock/market-status?exchange=US&token={FINNHUB_KEY}",
            timeout=8
        )
        payload = safe_json(res)
        is_open = bool(payload.get("isOpen", False)) if isinstance(payload, dict) else False

        rows = [
            "[b]RYNEK USA[/b]\n\n"
            f"Status teraz: [color=#00AA00]{'OTWARTY' if is_open else 'ZAMKNIĘTY'}[/color]\n"
            f"Czas lokalny: {local_time_text()}\n"
            f"Następne otwarcie: {next_us_market_open_text()}",
            us_market_hours_text_local(),
            build_full_glossary(),
            "[b]TABY[/b]\n"
            "• Info — status rynku i słowniczek.\n"
            "• Skaner — tickerów z rynku.\n"
            "• Ticker — pełna analiza jednego instrumentu.\n"
            "• Katalizatory — FDA / M&A / AI / wyniki.\n"
            "• CFD/Własne — sygnały, TP/SL i trend.",
        ]
        return rows

# =========================================
# SCANNER TAB
# =========================================

class ScannerTab(BaseTab):
    title = "Skaner"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.initial_visible = 12
        self.batch_size = 12
        self.max_visible = 96
        self.static_tickers = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "PLTR"]
        self.control_panel.height = dp(156)
        self.control_panel.clear_widgets()

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.input_field = MDTextField(hint_text="Dodaj ticker", mode="rectangle")
        input_row.add_widget(self.input_field)
        input_row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        input_row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(input_row)

        self.control_panel.add_widget(MDRaisedButton(text="Skanuj", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))
        self.control_panel.add_widget(self.more_button)

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
        all_tickers = list(dict.fromkeys(self.static_tickers + gainers[:10] + actives[:10]))[:30]
        bulk_data = await fetch_bulk(all_tickers, chunk_size=4)

        app = MDApp.get_running_app()
        if app:
            add_cache_items(app, bulk_data, visible_symbols=all_tickers)

        rows = []
        for sym in all_tickers:
            d = bulk_data.get(sym)
            if not d:
                continue
            comp_name = d.get("name", sym)
            price = safe(d.get("session_price", d.get("price", 0.0)))
            change = safe(d.get("change", 0.0))
            pct = safe(d.get("pct", 0.0))
            vol = int(safe(d.get("vol", 0.0), 0.0))
            avg_vol = int(safe(d.get("avg_vol", 0.0), 0.0))
            cap = d.get("market_cap", 0.0)
            pe = d.get("pe", "N/A")
            session = d.get("session_state", get_pl_session_hint())
            pre_p = safe(d.get("pre_price", d.get("pre", 0.0)))
            post_p = safe(d.get("post_price", d.get("post", 0.0)))
            prev_close = safe(d.get("prev_close", 0.0))
            tech = PriceEngine.analyze(sym, d.get("closes", []), price, vol, avg_vol)
            change_p, change_p_pct = session_change_p(session, price, pre_p, post_p)

            rows.append(
                f"[b]{sym}[/b] — [color=#555555]{comp_name}[/color]\n"
                f"Sesja: {session}\n"
                f"Cena sesyjna: [b]{price:.2f} USD[/b]\n"
                f"Zmiana: [color={'#00AA00' if change >= 0 else '#FF0000'}]{change:+.2f} USD | {pct:+.2f}%[/color]\n"
                f"Zmiana P: [color={'#00AA00' if change_p >= 0 else '#FF0000'}]{change_p:+.2f} USD | {change_p_pct:+.2f}%[/color]\n"
                f"Pre-Market: {_fmt_session_price(pre_p)} | Post-Market: {_fmt_session_price(post_p)}\n"
                f"Wolumen: {vol:,} (Śred. 10D: {avg_vol:,})\n"
                f"Kapitalizacja: {format_cap(cap)} | P/E: [b]{pe}[/b]\n"
                f"RSI: {color_wrap(fmt_num(tech['rsi'], 1), color_for_rsi(tech['rsi']))}\n"
                f"MACD: {color_wrap(fmt_num(tech['macd'], 3), color_for_macd(tech['macd'], tech['sig']))} | "
                f"Signal: {color_wrap(fmt_num(tech['sig'], 3), color_for_macd(tech['macd'], tech['sig']))} | "
                f"Hist: {format_histogram(tech['hist'])}"
            )
        return rows[:50]

# =========================================
# TICKER TAB
# =========================================

class TickerTab(BaseTab):
    title = "Ticker"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.initial_visible = 1
        self.batch_size = 1
        self.max_visible = 1
        self.control_panel.height = dp(88)
        self.control_panel.clear_widgets()

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.inp = MDTextField(hint_text="Ticker (np. TSLA)", mode="rectangle")
        row.add_widget(self.inp)
        row.add_widget(MDRaisedButton(text="Analizuj", on_release=self._on_search))
        self.control_panel.add_widget(row)
        self.control_panel.add_widget(self.more_button)

    def _on_search(self, *args):
        sym = self.inp.text.strip().upper()
        self.refresh_data(sym=sym)

    async def _fetch(self, *args, **kwargs):
        sym = (kwargs.get("sym") or self.inp.text.strip().upper() or "AAPL").strip().upper()
        if not sym:
            return ["[color=#888888]Wpisz ticker i kliknij Analizuj.[/color]"]

        d = await fetch_ticker(sym)
        if safe(d.get("price", 0.0)) == 0.0 and not d.get("closes"):
            return [f"[color=#FF0000]Nie znaleziono danych dla: {sym}[/color]"]

        price = safe(d.get("session_price", d.get("price", 0.0)))
        change = safe(d.get("change", 0.0))
        pct = safe(d.get("pct", 0.0))
        vol = int(safe(d.get("vol", 0.0), 0.0))
        avg_vol = int(safe(d.get("avg_vol", 0.0), 0.0))
        cap = d.get("market_cap", 0.0)
        pe = d.get("pe", "N/A")
        eps = d.get("eps", "N/A")
        high52 = safe(d.get("high52", 0.0))
        low52 = safe(d.get("low52", 0.0))
        day_high = safe(d.get("day_high", 0.0))
        day_low = safe(d.get("day_low", 0.0))
        prev_close = safe(d.get("prev_close", 0.0))
        session_label = d.get("session_state", get_pl_session_hint())
        tech = PriceEngine.analyze(sym, d.get("closes", []), price, vol, avg_vol)

        if tech["rsi"] <= 35 and tech["macd"] > tech["sig"]:
            signal_text = "MOCNE KUP"
            signal_color = "#006600"
        elif tech["rsi"] <= 45 and tech["macd"] > tech["sig"]:
            signal_text = "KUP"
            signal_color = "#00AA00"
        elif tech["rsi"] >= 65:
            signal_text = "MOCNE SPRZEDAJ"
            signal_color = "#FF0000"
        elif tech["rsi"] >= 55:
            signal_text = "SPRZEDAJ"
            signal_color = "#FF9900"
        else:
            signal_text = "NEUTRALNE"
            signal_color = "#888888"

        next_earnings = d.get("next_earnings", "Brak danych")
        prev_earnings_period = d.get("prev_earnings_period", "Brak danych")
        prev_earnings_surprise = d.get("prev_earnings_surprise", "Brak danych")
        earnings_reaction = d.get("earnings_reaction", "Brak danych")
        pre_price = safe(d.get("pre_price", d.get("pre", 0.0)))
        post_price = safe(d.get("post_price", d.get("post", 0.0)))

        change_p, change_p_pct = session_change_p(session_label, prev_close, pre_price, post_price)

        row = (
            f"[b]{d.get('name', sym)} ({sym})[/b] | Sesja: {session_label} | [color={signal_color}]{signal_text}[/color]\n"
            f"Cena sesyjna: [b]{price:.2f} USD[/b]\n"
            f"Zmiana: [color={'#00AA00' if change >= 0 else '#FF0000'}]{change:+.2f} USD | {pct:+.2f}%[/color] | "
            f"Zmiana P: [color={'#00AA00' if change_p >= 0 else '#FF0000'}]{change_p:+.2f} USD | {change_p_pct:+.2f}%[/color]\n"
            f"Pre-Market: {_fmt_session_price(pre_price)} | Post-Market: {_fmt_session_price(post_price)}\n"
            f"Wolumen: [b]{vol:,}[/b] | Śr. 10D: [b]{avg_vol:,}[/b] | Dzień: {day_low:.2f}-{day_high:.2f} | 52W: {low52:.2f}-{high52:.2f}\n"
            f"Kapitalizacja: {format_cap(cap)} | P/E: {pe} | EPS: {eps}\n"
            f"Następny raport: {next_earnings}\n"
            f"Reakcja po raporcie: {earnings_reaction}\n"
            f"RSI: [color={color_for_rsi(tech['rsi'])}]{tech['rsi']:.1f}[/color] | "
            f"MACD: [color={color_for_macd(tech['macd'], tech['sig'])}]{tech['macd']:.3f}[/color] | "
            f"Signal: [color={color_for_macd(tech['macd'], tech['sig'])}]{tech['sig']:.3f}[/color] | "
            f"Hist: {format_histogram(tech['hist'])}\n"
            f"SMA14: {fmt_num(tech['sma14'], 2)} | SMA30: {fmt_num(tech['sma30'], 2)} | SMA90: {fmt_num(tech['sma90'], 2)}\n"
        )
        return [row]

# =========================================
# KATALIZATORY TAB
# =========================================

class KatalizatoryTab(BaseTab):
    title = "Katalizatory"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.initial_visible = 10
        self.batch_size = 10
        self.max_visible = 40
        self.control_panel.height = dp(76)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(MDRaisedButton(text="Pobierz Dane", size_hint_y=None, height=dp(34), on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))
        self.control_panel.add_widget(self.more_button)

    def get_category_tag(self, title):
        t = (title or "").lower()
        if is_fda_pdufa_title(t):
            return "FDA/PDUFA"
        if is_merger_mna_title(t):
            return "WYKUP / M&A"
        if is_buyout_interest_title(t):
            return "ZAINTERESOWANIE WYKUPEM"
        if is_contract_ai_title(t):
            if any(x in t for x in ["government", "govt", "federal", "state", "rząd", "public sector", "municipal"]):
                return "UMOWA / RZĄD"
            if any(x in t for x in ["ai", "artificial intelligence", "transform", "genai"]):
                return "AI / TRANSFORMACJA"
            return "DUŻA UMOWA"
        if any(x in t for x in ["earnings", "wyniki", "raport", "revenue", "eps"]):
            return "WYNIKI"
        return None

    def get_catalyst_context(self, title):
        t = (title or "").lower()
        if is_fda_pdufa_title(t):
            return "Kontekst: decyzja regulacyjna FDA / PDUFA."
        if is_merger_mna_title(t):
            return "Kontekst: potencjalne przejęcie / wykup / M&A."
        if is_buyout_interest_title(t):
            return "Kontekst: rosnące zainteresowanie wykupem firmy."
        if any(x in t for x in ["clinical", "trial", "phase", "readout", "topline"]):
            return "Kontekst: wynik badania klinicznego / odczyt danych."
        if any(x in t for x in ["earnings", "wyniki", "raport", "revenue", "eps"]):
            return "Kontekst: raport wynikowy / publikacja finansowa."
        if any(x in t for x in ["contract", "agreement", "deal", "award", "government", "ai", "transform"]):
            return "Kontekst: kontrakt / umowa / transformacja AI."
        return ""

    async def _fetch(self, *args, **kwargs):
        app = MDApp.get_running_app()
        if not app:
            return ["Brak aplikacji."]

        watch_list = getattr(getattr(app, "scanner_tab", None), "static_tickers", []) or []
        universe = list(dict.fromkeys(NASDAQ_CORE + GPW_CORE + [s.strip().upper() for s in watch_list if s]))

        now = datetime.now()
        start_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        threshold = int((now - timedelta(days=7)).timestamp())

        catalyst_queries = [
            "FDA",
            "PDUFA",
            "adcom",
            "clinical trial",
            "topline",
            "readout",
            "merger",
            "acquisition",
            "takeover",
            "buyout",
            "strategic alternatives",
            "contract",
            "award",
            "partnership",
            "artificial intelligence",
            "AI",
            "earnings",
            "guidance",
        ]

        news_items = []
        seen = set()

        for q in catalyst_queries:
            q_enc = quote_plus(q)
            res = await safe_request_async(
                f"https://query2.finance.yahoo.com/v1/finance/search?q={q_enc}&newsCount=50",
                timeout=6
            )
            if res.status_code != 200:
                continue
            for n in safe_json(res).get("news", []):
                title = n.get("title", "")
                cat = self.get_category_tag(title)
                if not cat:
                    continue
                pub = n.get("providerPublishTime", 0)
                if pub and pub < threshold:
                    continue
                rel = n.get("relatedTickers", []) or []
                ticker = (rel[0] if rel else "RYNEK").strip().upper()
                key = re.sub(r"\s+", " ", f"{ticker}|{title}|{cat}".lower())
                if key in seen:
                    continue
                seen.add(key)
                news_items.append({
                    "ticker": ticker,
                    "title": title,
                    "link": n.get("link", ""),
                    "cat": cat,
                    "context": self.get_catalyst_context(title),
                })

        earnings_rows = []
        for sym in universe[:30]:
            try:
                res = await safe_request_async(
                    f"https://finnhub.io/api/v1/calendar/earnings?symbol={sym}&from={start_date}&to={end_date}&token={FINNHUB_KEY}",
                    timeout=4
                )
                if res.status_code == 200:
                    payload = safe_json(res).get("earningsCalendar", []) or []
                    for item in payload:
                        item_sym = (item.get("symbol") or sym).strip().upper()
                        if item_sym not in universe:
                            continue
                        earnings_rows.append(item | {"symbol": item_sym})
            except Exception:
                pass

        if not earnings_rows:
            try:
                general = await fetch_earnings()
                for item in general or []:
                    item_sym = (item.get("symbol") or "").strip().upper()
                    if item_sym and item_sym in universe:
                        earnings_rows.append(item | {"symbol": item_sym})
            except Exception:
                pass

        names = await fetch_company_names(
            [item["ticker"] for item in news_items if item.get("ticker") and item["ticker"] != "RYNEK"]
            + [item.get("symbol", "") for item in earnings_rows]
        )

        rows = [color_wrap(f"Ostatnia aktualizacja: {timestamp_text()}", "#888888")]

        fda_cards, mna_cards, ai_cards, other_cards = [], [], [], []
        for item in news_items:
            ticker = item["ticker"]
            title = item["title"]
            link = item["link"]
            cat = item["cat"]
            context = item.get("context", "")

            display_name = names.get(ticker) or resolve_company_name_for_tab(app, ticker)
            label = f"{ticker} ({display_name})" if display_name and display_name.upper() != ticker.upper() else ticker

            safe_link = link or search_url_from_query(title)
            card = (
                f"[ref={safe_link}][color=#FF33CC][b][{cat}][/b][/color][/ref] "
                f"[ref={safe_link}][color=#008080][b]{label}[/b][/color][/ref]\n"
                f"{context}\n"
                f"[ref={safe_link}]{title}[/ref]"
            )

            if cat == "FDA/PDUFA":
                fda_cards.append(card)
            elif cat in ("WYKUP / M&A", "ZAINTERESOWANIE WYKUPEM"):
                mna_cards.append(card)
            elif cat == "AI / TRANSFORMACJA":
                ai_cards.append(card)
            else:
                other_cards.append(card)

        if fda_cards:
            rows.append(f"[ref={search_url_from_query('FDA PDUFA stocks news')}][b][color=#ff9900]🩺 FDA / PDUFA / DECYZJE REGULACYJNE[/color][/b][/ref]")
            rows.extend(fda_cards[:12])
        if mna_cards:
            rows.append(f"[ref={search_url_from_query('merger acquisition buyout stocks news')}][b][color=#FF6666]🧩 WYKUPY / PRZEJĘCIA / ZAINTERESOWANIE WYKUPEM[/color][/b][/ref]")
            rows.extend(mna_cards[:12])
        if ai_cards:
            rows.append(f"[ref={search_url_from_query('artificial intelligence stock news')}][b][color=#00FFFF]🧠 AI / TRANSFORMACJA / UMOWY[/color][/b][/ref]")
            rows.extend(ai_cards[:12])
        if other_cards:
            rows.append(f"[ref={search_url_from_query('stock catalyst news earnings contract partnership')}][b][color=#FF33CC]🔥 INNE KATALIZATORY[/color][/b][/ref]")
            rows.extend(other_cards[:10])

        if earnings_rows:
            rows.append(f"[ref={search_url_from_query('earnings calendar stocks')}][b][color=#ff8c00]— KALENDARZ WYNIKÓW (7 DNI) —[/color][/b][/ref]")
            for item in earnings_rows[:20]:
                sym = item.get("symbol", "—")
                name = names.get(sym) or resolve_company_name_for_tab(app, sym)
                label = f"{sym} ({name})" if name and name.upper() != sym.upper() else sym
                rows.append(
                    f"[color=#008080][b]{label}[/b][/color]\n"
                    f"Data: {item.get('date', 'Brak daty')} | EPS est.: {item.get('epsEstimate', 'N/A')} | Revenue est.: {item.get('revenueEstimate', 'N/A')}"
                )
        else:
            rows.append("[color=#888888]Brak aktywnych wyników w ciągu 7 dni dla NASDAQ / GPW.[/color]")

        return rows[:120]

# =========================================
# CFD TAB
# =========================================

class CFDTab(BaseTab):
    title = "CFD/Własne"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.initial_visible = 6
        self.batch_size = 6
        self.max_visible = 24
        self.control_panel.height = dp(76)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(MDRaisedButton(text="Analizuj Rynek", size_hint_y=None, height=dp(34), on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))
        self.control_panel.add_widget(self.more_button)

    def _cfd_universe(self):
        return ["BTC-USD", "GC=F", "CL=F", "NQ=F", "ES=F"]

    async def _fetch(self, *args, **kwargs):
        app = MDApp.get_running_app()
        universe = await fetch_dynamic_universe_async(limit=20)
        cfd_universe = self._cfd_universe()
        required = list(dict.fromkeys(universe + cfd_universe))
        bulk_data = await fetch_bulk(required, chunk_size=5)
        if app:
            add_cache_items(app, bulk_data, visible_symbols=required)

        rows = []
        sections = {
            "A: BREAKOUTY / PRE-POST GAINERS": [],
            "B: TREND": [],
            "C: CFD": [],
        }

        for sym, d in bulk_data.items():
            name = normalize_company_name(sym, d.get("name", sym))
            price = safe(d.get("price", 0.0))
            closes = d.get("closes", [])
            if price <= 0:
                continue
            vol = int(safe(d.get("vol", 0.0), 0.0))
            avg_vol = int(safe(d.get("avg_vol", 0.0), 0.0))
            tech = PriceEngine.analyze(sym, closes, price, vol, avg_vol)
            tp, sl = make_tp_sl(price, 0.03, 0.02)
            session_state = d.get("session_state", get_pl_session_hint())
            pre_price = safe(d.get("pre_price", d.get("pre", 0.0)))
            post_price = safe(d.get("post_price", d.get("post", 0.0)))
            prev_close = safe(d.get("prev_close", 0.0))
            change_p, change_p_pct = session_change_p(session_state, price, pre_price, post_price)

            row = (
                f"[b]{name} ({sym})[/b]\n"
                f"Cena: [b]{price:.2f}[/b] | TP: [color=#00AA00]{tp:.2f}[/color] | SL: [color=#FF3333]{sl:.2f}[/color]\n"
                f"Zmiana P: [color={'#00AA00' if change_p >= 0 else '#FF0000'}]{change_p:+.2f} USD | {change_p_pct:+.2f}%[/color]\n"
                f"RSI {tech['rsi']:.1f} | MACD {tech['macd']:.3f}/{tech['sig']:.3f} | Hist {tech['hist']:+.3f}\n"
                f"SMA14 {fmt_num(tech['sma14'], 2)} | SMA30 {fmt_num(tech['sma30'], 2)} | SMA90 {fmt_num(tech['sma90'], 2)} | "
                f"[color={tech['signal_color']}]{tech['signal_text']}[/color]"
            )
            if sym in cfd_universe:
                sections["C: CFD"].append(row)
            elif tech["score"] >= 2:
                sections["A: BREAKOUTY"].append(row)
            else:
                sections["B: TREND"].append(row)

        rows.append(color_wrap(f"Ostatnia aktualizacja: {timestamp_text()}", "#888888"))

        ranked = sorted(
            [
                (
                    safe(d.get("pct", 0.0)),
                    sym,
                    normalize_company_name(sym, d.get("name", sym)),
                    safe(d.get("session_price", d.get("price", 0.0))),
                    safe(d.get("prev_close", 0.0)),
                    safe(d.get("pre_price", d.get("pre", 0.0))),
                    safe(d.get("post_price", d.get("post", 0.0))),
                )
                for sym, d in bulk_data.items()
                if safe(d.get("price", 0.0)) > 0
            ],
            reverse=True
        )

        top_gainers = ranked[:5]
        rows.append(f"[b][color=#008080]A: BREAKOUTY / PRE-POST GAINERS[/color][/b]")
        if top_gainers:
            for pct_v, sym, name, price_v, prev_v, pre_v, post_v in top_gainers:
                rows.append(
                    f"[b]{name} ({sym})[/b] | {price_v:.2f} USD | "
                    f"Zmiana: [color={'#00AA00' if pct_v >= 0 else '#FF0000'}]{pct_v:+.2f}%[/color] | "
                    f"Pre: {_fmt_session_price(pre_v)} | Post: {_fmt_session_price(post_v)}"
                )
        else:
            rows.append("[color=#888888]Brak danych[/color]")

        for section, items in sections.items():
            if section.startswith("A:"):
                rows.extend(items[:10])
                continue
            rows.append(f"[b][color=#008080]{section}[/color][/b]")
            rows.extend(items[:10] if items else ["[color=#888888]Brak danych[/color]"])
        return rows[:120]

# =========================================
# APP
# =========================================

class StockScanner(MDApp):
    def handle_ref(self, ref):
        ref = (ref or "").strip()
        if not ref:
            return
        if ref.startswith("http://") or ref.startswith("https://"):
            try:
                webbrowser.open(ref)
            except Exception:
                pass
            return
        try:
            webbrowser.open(search_url_from_query(ref))
        except Exception:
            pass

    def build(self):
        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.theme_style = "Light"
        self.app_ready = False
        self.shared_cache = {}
        self.cache_time = None

        screen = MDScreen()
        self.tabs = MDTabs()
        self.tabs.bind(on_tab_switch=self._on_tab_switch)
        screen.add_widget(self.tabs)

        self.info_tab = InfoTab()
        self.scanner_tab = ScannerTab()
        self.ticker_tab = TickerTab()
        self.katalizatory_tab = KatalizatoryTab()
        self.cfd_tab = CFDTab()

        self.tabs.add_widget(self.info_tab)
        self.tabs.add_widget(self.scanner_tab)
        self.tabs.add_widget(self.ticker_tab)
        self.tabs.add_widget(self.katalizatory_tab)
        self.tabs.add_widget(self.cfd_tab)

        return screen

    def on_start(self):
        ASYNC_LOOP_READY.wait(timeout=5)

        self.info_tab.load_data_if_needed()
        self.scanner_tab.load_data_if_needed()
        self.katalizatory_tab.load_data_if_needed()

        Clock.schedule_interval(lambda dt: self.scanner_tab.refresh_data(), 90)
        Clock.schedule_interval(lambda dt: self.cfd_tab.refresh_data(), 90)

        self.app_ready = True

    def _on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if hasattr(instance_tab, "load_data_if_needed"):
            instance_tab.load_data_if_needed()

    def on_stop(self):
        try:
            if ASYNC_LOOP and ASYNC_LOOP.is_running():
                run_async_if_ready(HTTP_CLIENT.aclose())
        except Exception:
            pass

if __name__ == "__main__":
    StockScanner().run()
