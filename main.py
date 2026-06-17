# ==============================================================================
# STOCK SCANNER PRO - V10 UNIFIED & FIXED (FULL VERSION)
# Android 14 + Foreground WS + Notifications + Smart Mappings
# ==============================================================================

import asyncio
import json
import os
import threading
import time
import webbrowser
import html
from datetime import datetime, timedelta, timezone
from urllib.parse import quote_plus
from xml.etree import ElementTree as ET
from collections import deque
import certifi
import httpx
import websockets

# Kivy and KivyMD Setup Engine Optimization
from kivy.config import Config
Config.set("graphics", "multisamples", "0")
Config.set("kivy", "maxfps", "60")

from kivy.clock import Clock
Clock.max_iteration = 120
from kivy.lang import Builder
from kivy.metrics import dp
from kivy.properties import StringProperty
from kivy.uix.recycleview import RecycleView
from kivy.uix.scrollview import ScrollView
from kivymd.app import MDApp
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.card import MDCard
from kivymd.uix.label import MDLabel
from kivymd.uix.screen import MDScreen
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.textfield import MDTextField

# Platform Context Resolvers (Android specific)
try:
    from android.permissions import Permission, request_permissions
    from jnius import autoclass
    ANDROID = True
except Exception:
    ANDROID = False
    Permission = None
    request_permissions = None
    autoclass = None

try:
    from zoneinfo import ZoneInfo
except ImportError:
    class ZoneInfo:
        def __init__(self, name):
            self.tz = timezone.utc
        def __call__(self, *args, **kwargs):
            return self.tz
        def utcoffset(self, dt=None):
            return timedelta(0)
        def tzname(self, dt=None):
            return "UTC"

# =========================================
# CONFIGURATION & CONSTANTS
# =========================================
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "en-US,en;q=0.9",
    "Referer": "https://finance.yahoo.com/",
}
FINNHUB_KEY = "d82t3s1r01ql4onfbbngd82t3s1r01ql4onfbbo0"
HTTP_CLIENT = None
REQUEST_DELAY = 0.15
MAX_RETRIES = 2

REQUEST_CACHE = {}
REQUEST_CACHE_LOCK = threading.Lock()
REQUEST_CACHE_TTL = {
    "screener": 60,
    "ticker": 30,
    "company": 180,
    "news": 120,
    "finnhub_news": 120,
    "finnhub_earnings": 300,
}

LAST_REQUEST_TIME = {}
RATE_LIMIT_LOCK = asyncio.Lock()
ASYNC_LOOP = None
ASYNC_LOOP_READY = threading.Event()

NASDAQ_CORE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "GOOGL", "PLTR",
    "NFLX", "AVGO", "ORCL", "COST", "QCOM", "MU", "INTC", "CRM", "UBER", "SHOP",
]
GPW_CORE = [
    "CDR.WA", "PKO.WA", "PEO.WA", "PZU.WA", "PKN.WA", "DNP.WA", "LPP.WA", "ALE.WA",
    "JSW.WA", "KGH.WA", "MBK.WA", "SPL.WA", "BHW.WA",
]

# Mapowanie indeksów CFD
CFD_ALIAS = {
    "US500": "^GSPC", "NAS100": "^NDX", "US30": "^DJI",
    "GER40": "^GDAXI", "UK100": "^FTSE",
}

# Inteligentne mapowanie surowców i towarów rolnych do rynków Futures (CME/COMEX/NYMEX)
SMART_COMMODITIES = {
    "COCOA": "CC=F", "KAKAOWIEC": "CC=F",
    "COFFEE": "KC=F", "KAWA": "KC=F",
    "SUGAR": "SB=F", "CUKIER": "SB=F",
    "CORN": "ZC=F", "KUKURYDZA": "ZC=F",
    "WHEAT": "ZW=F", "PSZENICA": "ZW=F",
    "COTTON": "CT=F", "BAWELNA": "CT=F",
    "NATGAS": "NG=F", "GAZ": "NG=F", "NATURAL GAS": "NG=F",
    "OIL": "CL=F", "ROPA": "CL=F", "CRUDE": "CL=F", "WTI": "CL=F",
    "BRENT": "BZ=F",
    "GOLD": "GC=F", "ZLOTO": "GC=F", "XAUUSD": "GC=F",
    "SILVER": "SI=F", "SREBRO": "SI=F", "XAGUSD": "SI=F",
    "COPPER": "HG=F", "MIEDZ": "HG=F",
    "PLATINUM": "PL=F", "PLATYNA": "PL=F",
    "PALLADIUM": "PA=F", "PALAD": "PA=F"
}

FALLBACK_NAMES = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "AMZN": "Amazon",
    "META": "Meta", "TSLA": "Tesla", "AMD": "AMD", "GOOGL": "Alphabet",
    "PLTR": "Palantir", "NFLX": "Netflix", "AVGO": "Broadcom", "ORCL": "Oracle",
    "CDR.WA": "CD Projekt", "PKO.WA": "PKO BP", "PEO.WA": "Pekao", "PZU.WA": "PZU",
    "PKN.WA": "Orlen", "DNP.WA": "Dino Polska", "LPP.WA": "LPP", "ALE.WA": "Allegro",
}

CFD_FRIENDLY = {
    "US500": "S&P 500", "NAS100": "Nasdaq 100", "US30": "Dow Jones 30",
    "GER40": "DAX 40", "UK100": "FTSE 100", 
    "GC=F": "Złoto (COMEX)", "SI=F": "Srebro (COMEX)", "CC=F": "Kakao (ICE)",
    "KC=F": "Kawa (ICE)", "CL=F": "Ropa WTI (NYMEX)", "NG=F": "Gaz Ziemny",
    "^GSPC": "S&P 500", "^NDX": "Nasdaq 100", "^DJI": "Dow Jones 30"
}

LOCAL_TZ = ZoneInfo("Europe/Warsaw")
NY_TZ = ZoneInfo("America/New_York")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "v10_state.json")

# =========================================
# HARDENED NETWORK SUBSYSTEM (HTTPX CORE)
# =========================================
def get_http_client():
    global HTTP_CLIENT
    if HTTP_CLIENT is None:
        try: verify_path = certifi.where()
        except Exception: verify_path = False
        HTTP_CLIENT = httpx.AsyncClient(
            headers=HEADERS, timeout=httpx.Timeout(12.0),
            limits=httpx.Limits(max_connections=25, max_keepalive_connections=15),
            http2=False, verify=verify_path
        )
    return HTTP_CLIENT



async def safe_request_async(url, timeout=10, retries=MAX_RETRIES):
    host = url.split("/")[2] if "://" in url else "default"
    client = get_http_client()
    for i in range(retries):
        try:
            async with RATE_LIMIT_LOCK:
                now = time.time()
                diff = now - LAST_REQUEST_TIME.get(host, 0)
                if diff < REQUEST_DELAY: await asyncio.sleep(REQUEST_DELAY - diff)
                LAST_REQUEST_TIME[host] = time.time()
            response = await client.get(url, timeout=timeout)
            if response.status_code in (200, 404): return response
            if response.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(min(2 ** i, 8))
                continue
            return response
        except Exception:
            await asyncio.sleep(min(2 ** i, 8))
            continue
    return None

def finnhub_url(endpoint, params=None):
    p = dict(params or {})
    p["token"] = FINNHUB_KEY
    return f"https://finnhub.io/api/v1/{endpoint.lstrip('/')}?{'&'.join(f'{k}={quote_plus(str(v))}' for k, v in p.items())}"

async def fetch_json_cached(url, ttl, cache_key=None, timeout=10):
    key = cache_key or url
    now = time.time()
    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(key)
        if cached and now - cached["ts"] < ttl: return cached["data"]
    res = await safe_request_async(url, timeout=timeout)
    data = {}
    if res and getattr(res, "status_code", 0) == 200:
        try: data = res.json()
        except Exception: pass
    if data:
        with REQUEST_CACHE_LOCK: REQUEST_CACHE[key] = {"ts": now, "data": data}
    return data



# =========================================
# HELPERS & FORMATTERS
# =========================================
def safe(v, d=0.0):
    try: return float(v) if v is not None else d
    except Exception: return d

def safe_list(data):
    return [safe(x) for x in data if data is not None]

def fmt_num(value, digits=2, signed=False):
    v = safe(value, 0.0)
    return f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"

def format_pct(value, digits=2):
    return f"{safe(value):+.{digits}f}%"

def color_wrap(text, color):
    return f"[color={color}]{text}[/color]"

def format_histogram(hist):
    if hist > 0: return color_wrap(fmt_num(hist, 3, signed=True), "#00AA00")
    if hist < 0: return color_wrap(fmt_num(hist, 3, signed=True), "#FF0000")
    return color_wrap(fmt_num(hist, 3, signed=True), "#888888")

def format_cap(v):
    v = safe(v)
    if v >= 1_000_000_000_000: return f"{v/1_000_000_000_000:.2f} T"
    if v >= 1_000_000_000: return f"{v/1_000_000_000:.2f} B"
    if v >= 1_000_000: return f"{v/1_000_000:.2f} M"
    return f"{v:.2f}"

def format_earnings_value(value):
    try:
        ts = int(float(value))
        return datetime.fromtimestamp(ts, NY_TZ).astimezone(LOCAL_TZ).strftime("%d.%m.%Y")
    except Exception:
        return str(value) if value not in (None, "") else "N/A"

def make_tp_sl(price, tp_pct=0.03, sl_pct=0.02):
    p = safe(price, 0.0)
    return p * (1 + tp_pct), p * (1 - sl_pct)

def color_for_rsi(rsi_val):
    if rsi_val <= 30: return "#006600"
    if rsi_val <= 40: return "#00AA00"
    if rsi_val >= 70: return "#FF0000"
    if rsi_val >= 60: return "#FF9900"
    return "#888888"

def session_label(state):
    colors = {
        "PREMARKET": "#FF9900",
        "OTWARTY": "#00AA00",
        "POSTMARKET": "#001A66",
        "OVERNIGHT": "#7A00CC",
        "ZAMKNIĘTY": "#777777",
    }
    state = (state or '').upper()
    return f"[color={colors.get(state, '#777777')}]{state}[/color]"

def timestamp_text():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def normalize_company_name(symbol, name=None, display_name=None):
    if display_name: return display_name
    symbol = (symbol or "").strip().upper()
    cleaned = (name or "").strip()
    if cleaned and cleaned.upper() != symbol: return cleaned
    return FALLBACK_NAMES.get(symbol.replace(".WA", "").replace(".PL", ""), symbol)

async def fetch_earnings_date(symbol):
    try:
        url = finnhub_url(
            "calendar/earnings",
            {
                "symbol": symbol,
                "from": today_ny(),
                "to": future_date_ny(365)
            }
        )

        data = await fetch_json_cached(
            url,
            ttl=3600,
            cache_key=url
        )

        items = data.get("earningsCalendar", [])

        if items:
            return items[0].get("date")

    except Exception:
        pass

    return "N/A"

# =========================================
# SYSTEMATIC GLOSSARY & TIMING
# =========================================
def market_status():
    ny = datetime.now(NY_TZ)
    if ny.weekday() >= 5:
        return "ZAMKNIĘTY"
    h = ny.hour + ny.minute / 60.0
    if 4.0 <= h < 9.5:
        return "PREMARKET"
    if 9.5 <= h < 16.0:
        return "OTWARTY"
    if 16.0 <= h < 20.0:
        return "POSTMARKET"
    return "OVERNIGHT"

def us_market_hours_text_local():
    try:
        now_ny = datetime.now(NY_TZ)
        base_date = now_ny.date()
        pre_end = datetime(base_date.year, base_date.month, base_date.day, 9, 30, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        reg_end = datetime(base_date.year, base_date.month, base_date.day, 16, 0, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        return (
            "[b]Rynek USA — godziny sesji (ET / CET)[/b]\n"
            f"• [b]Pre-Market[/b]: 04:00–09:30 ET / ...–{pre_end.strftime('%H:%M %Z')}\n"
            f"• [b]Sesja główna[/b]: 09:30–16:00 ET / {pre_end.strftime('%H:%M')}–{reg_end.strftime('%H:%M %Z')}\n"
            "• [b]Weekend[/b]: rynek zamknięty"
        )
    except Exception:
        return "[b]Rynek USA[/b]: 09:30–16:00 ET"

def build_full_glossary():
    return (
        "[b][size=19]PEŁNY SŁOWNIK WSKAŹNIKÓW I POJĘĆ (V10 PRO)[/size][/b]\n\n"
        "[b]1. Analiza Techniczna i Momentum:[/b]\n"
        "• [b]SMA30 / SMA90[/b] — Średnie kroczące. Ukazują główny trend cenowy.\n"
        "• [b]RSI (14)[/b] — Poniżej 40 oznacza wyprzedanie (okazja), powyżej 65 oznacza wykupienie (ryzyko korekty).\n"
        "• [b]MACD & Histogram[/b] — Zielony, rosnący histogram potwierdza silną dominację popytu.\n\n"
        "[b]2. Przepływ Zleceń (Order Flow - V4):[/b]\n"
        "• [b]Imbalance[/b] — Nierównowaga zleceń rynkowych Kupna/Sprzedaży.\n"
        "• [b]Absorption[/b] — Przejęcie kapitału na kluczowych poziomach. Zapowiada zwrot.\n"
        "• [b]Exhaustion[/b] — Spadek wolumenu transakcyjnego przy jednoczesnym wyhamowaniu ceny.\n\n"
        "[b]3. Wskaźniki Fundamentalne:[/b]\n"
        "• [b]Kapitalizacja[/b] — Całkowita rynkowa wartość spółki (M=Miliony, B=Miliardy, T=Biliony).\n"
        "• [b]P/E Ratio (Cena do Zysku)[/b] — Niski wskaźnik sugeruje niedowartościowanie.\n"
        "• [b]EPS[/b] — Zysk netto wypracowany w przeliczeniu na jedną akcję.\n"
        "• [b]Konsensus Analityków[/b] — Średnia ocena z Wall Street (np. Strong Buy, Hold, Sell).\n\n"
        "[b]4. Fazy Rynku:[/b]\n"
        "• [b]PREMARKET / POSTMARKET[/b] — Handel poza głównymi godzinami.\n"
        "• [b]OTWARTY[/b] — Główna sesja giełdowa z najwyższą płynnością.\n\n"
        "[b]5. Predykcja AI:[/b]\n"
        "• [b]AI Score (0-100)[/b] — Zagregowana siła predykcyjna. >60 generuje sygnał LONG (Kupno).\n"
        "• [b]Regime / Timing[/b] — Środowisko rynkowe oraz ocena momentu wejścia.\n"
        "• [b]TP / SL[/b] — Model Take Profit (+3.0%) i Stop Loss (-2.0%)."
    )

# =========================================
# V10 MATH & INDICATOR ENGINE
# =========================================
def ema(data, period):
    if not data: return []
    k = 2 / (period + 1)
    out = [data[0]]
    for price in data[1:]: out.append(price * k + out[-1] * (1 - k))
    return out

def sma(data, period):
    if not data: return 0.0
    return round(sum(data[-period:]) / period, 2) if len(data) >= period else round(sum(data) / len(data), 2)

def macd(closes):
    closes = safe_list(closes)
    if len(closes) < 35: return 0.0, 0.0, 0.0
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[i] - ema26[i] for i in range(-min_len, 0)]
    signal_line = ema(macd_line, 9)
    return round(macd_line[-1], 3), round(signal_line[-1], 3), round(macd_line[-1] - signal_line[-1], 3)

def calc_rsi(closes, period=14):
    closes = safe_list(closes)
    if len(closes) < period + 1: return 50.0
    deltas = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    return round(100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))), 2)

def build_v10_stats(closes, current_price, prev_close, pre_price=0.0, post_price=0.0):
    closes = safe_list(closes)
    cp = safe(current_price, 0.0)
    pc = safe(prev_close, 0.0)

    # Obliczenia poszczególnych zmian
    diff_dnia = cp - pc
    pct_dnia = (diff_dnia / pc * 100) if pc > 0 else 0.0
    
    diff_pre = (pre_price - pc) if pre_price > 0 else 0.0
    pct_pre = (diff_pre / pc * 100) if pc > 0 and pre_price > 0 else 0.0
    
    diff_post = (post_price - pc) if post_price > 0 else 0.0
    pct_post = (diff_post / pc * 100) if pc > 0 and post_price > 0 else 0.0    

    if pc <= 0 and len(closes) >= 1: pc = safe(closes[-1], 0.0)
    if pc <= 0: pc = cp
    
    rsi_val = calc_rsi(closes)
    macd_val, signal_val, hist = macd(closes)
    
    prob = 50
    if macd_val > signal_val: prob += 12
    else: prob -= 12
    if rsi_val < 40: prob += 10
    elif rsi_val > 65: prob -= 10
    if hist > 0: prob += 6
    
    regime = "Trend Wzrostowy (UP)" if rsi_val > 55 and macd_val > signal_val else "Trend Spadkowy (DOWN)" if rsi_val < 45 else "Stabilizacja (RANGE)"
    timing = "IDEALNY_MOMENT" if prob > 65 else "NEUTRALNY" if prob > 40 else "CZEKAJ"
    raw_sig = "KUPUJ" if prob > 65 else "SPRZEDAJ" if prob < 35 else "TRZYMAJ"
    sig_color = "#00AA00" if raw_sig == "KUPUJ" else "#FF0000" if raw_sig == "SPRZEDAJ" else "#888888"
    
    return {
        "pct_dnia": pct_dnia,
        "pct_pre": pct_pre,
        "pct_post": pct_post,
        "price": cp, "prev_close": pc, "diff": diff_dnia, "pct": pct_dnia,
        "rsi": rsi_val, "macd": macd_val, "sig": signal_val, "hist": hist,
        "sma30": sma(closes, 30), "sma90": sma(closes, 90), "regime": regime, "timing": timing,
        "prob": max(0, min(100, prob)), "signal": raw_sig, "signal_color": sig_color
    }

# =========================================
# V4 WEBSOCKET ENGINE (REAL-TIME DATA)
# =========================================

class LiveTickStreamV4:
    def __init__(self, ws_url):
        self.ws_url = ws_url
        self.subscribers = []
        self.running = False
        self.tick_buffer = deque(maxlen=5000)
        self.symbols_to_track = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD"]
        self.current_symbols = set()
        self.ws = None
        self._symbols_lock = asyncio.Lock()

    def subscribe(self, callback):
        self.subscribers.append(callback)

    async def _dispatch(self, tick):
        self.tick_buffer.append(tick)
        for cb in self.subscribers:
            try:
                cb(tick)
            except Exception as e:
                print("[WS callback error]", e)

    async def sync_symbols(self, new_symbols):
        cleaned = [s.strip().upper() for s in (new_symbols or []) if s and s.strip()]
        cleaned = list(dict.fromkeys(cleaned))
        async with self._symbols_lock:
            old = set(self.current_symbols)
            new = set(cleaned)
            self.symbols_to_track = cleaned
            if self.ws is None or not self.running:
                self.current_symbols = set(cleaned)
                return
            to_unsub = old - new
            to_sub = new - old
            for sym in sorted(to_unsub):
                try:
                    await self.ws.send(json.dumps({"type": "unsubscribe", "symbol": sym}))
                except Exception:
                    pass
            for sym in sorted(to_sub):
                try:
                    await self.ws.send(json.dumps({"type": "subscribe", "symbol": sym}))
                except Exception:
                    pass
            self.current_symbols = set(cleaned)

    async def connect(self):
        self.running = True
        retry_count = 0
        while self.running:
            try:
                async with websockets.connect(f"wss://ws.finnhub.io?token={FINNHUB_KEY}") as ws:
                    self.ws = ws
                    print("[V4 WS] Połączono")
                    retry_count = 0

                    async with self._symbols_lock:
                        initial = list(self.symbols_to_track)
                        self.current_symbols = set(initial)

                    for sym in initial:
                        await ws.send(json.dumps({"type": "subscribe", "symbol": sym}))

                    async for msg in ws:
                        response = json.loads(msg)
                        if response.get("type") == "ping":
                            continue
                        if response.get("type") == "trade":
                            for trade in response.get("data", []):
                                tick = {
                                    "symbol": trade.get("s"),
                                    "price": float(trade.get("p", 0)),
                                    "volume": float(trade.get("v", 0)),
                                    "ts": trade.get("t") / 1000.0
                                }
                                await self._dispatch(tick)
            except Exception as e:
                retry_count += 1
                wait_time = min(2 ** retry_count, 60)
                print(f"[WS reconnect] {e} - ponawianie za {wait_time}s")
                await asyncio.sleep(wait_time)
            finally:
                self.ws = None

    def stop(self):
        self.running = False

class RealTimeAIv4:

    def __init__(self):
        self.prices = {}

    def update(self, tick):
        sym = tick["symbol"]
        price = tick["price"]
        if not sym: return None
        if sym not in self.prices: self.prices[sym] = deque(maxlen=50)
        self.prices[sym].append(price)
        closes = list(self.prices[sym])
        if len(closes) < 10: return None

        rsi = calc_rsi(closes)
        macd_val, sig, hist = macd(closes)
        momentum = (closes[-1] - closes[0]) / closes[0] * 100

        score = 50
        if macd_val > sig: score += 15
        else: score -= 15
        if rsi < 35: score += 10
        elif rsi > 70: score -= 10
        if momentum > 0.5: score += 10
        elif momentum < -0.5: score -= 10

        score = max(0, min(100, score))
        signal = "KUPUJ" if score > 65 else "SPRZEDAJ" if score < 35 else "TRZYMAJ"
        return {
            "symbol": sym, "price": price, "rsi": rsi, "macd": macd_val,
            "hist": hist, "score": score, "signal": signal, "momentum": momentum
        }


class UltraEngineV4:
    def __init__(self, ws_url):
        self.stream = LiveTickStreamV4(ws_url)
        self.ai = RealTimeAIv4()
        self.last_signals = {}
        self.listeners = []
        self.stream.subscribe(self.on_tick)

    def subscribe(self, callback):
        self.listeners.append(callback)

    def on_tick(self, tick):
        result = self.ai.update(tick)
        if not result:
            return
        sym = result["symbol"]
        now = time.time()
        if now - self.last_signals.get(sym, 0) < 2:
            return
        self.last_signals[sym] = now
        for cb in self.listeners:
            try:
                cb(result)
            except Exception:
                pass

    async def start(self):
        await self.stream.connect()

    async def update_symbols(self, symbols):
        await self.stream.sync_symbols(symbols)

    def stop(self):
        self.stream.stop()

async def fetch_finnhub_financial_report(symbol, days_forward=365):
    sym = (symbol or "").strip().upper()
    if not sym:
        return None

    start_dt = datetime.now(NY_TZ).date()
    end_dt = start_dt + timedelta(days=days_forward)

    url = finnhub_url(
        "calendar/earnings",
        {"from": start_dt.isoformat(), "to": end_dt.isoformat()}
    )

    res = await safe_request_async(url, timeout=10)
    if not res or getattr(res, "status_code", 0) != 200:
        return None

    try:
        data = res.json()
    except Exception:
        return None

    items = data.get("earningsCalendar", []) or []
    for row in items:
        if (row.get("symbol") or "").strip().upper() == sym:
            return {
                "date": row.get("date", "N/A"),
                "hour": row.get("hour", "N/A"),
                "epsEstimate": row.get("epsEstimate", "N/A"),
                "revenueEstimate": row.get("revenueEstimate", "N/A"),
                "symbol": row.get("symbol", sym),
                "raw": row
            }

    return None


async def fetch_finnhub_consensus(symbol):
    """
    Zwraca prosty consensus z endpointu recommendation-trends.
    Finnhub zwraca zwykle: strongBuy, buy, hold, sell, strongSell.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        return "N/A"

    url = finnhub_url("stock/recommendation", {"symbol": sym})
    res = await safe_request_async(url, timeout=10)
    if not res or getattr(res, "status_code", 0) != 200:
        return "N/A"

    try:
        data = res.json()
    except Exception:
        return "N/A"

    trends = data if isinstance(data, list) else []
    if not trends:
        return "N/A"

    latest = trends[0]

    strong_buy = int(latest.get("strongBuy", 0) or 0)
    buy = int(latest.get("buy", 0) or 0)
    hold = int(latest.get("hold", 0) or 0)
    sell = int(latest.get("sell", 0) or 0)
    strong_sell = int(latest.get("strongSell", 0) or 0)

    total = strong_buy + buy + hold + sell + strong_sell
    if total <= 0:
        return "N/A"

    # Prosty, czytelny consensus do UI
    if strong_buy + buy >= max(hold, sell + strong_sell) * 1.5:
        return "Strong Buy"
    if buy >= hold and buy >= sell:
        return "Buy"
    if hold >= buy and hold >= sell:
        return "Hold"
    if sell + strong_sell > buy:
        return "Sell"

    return "N/A"

# =========================================
# DATA HARVESTING MODULES (YAHOO + FINNHUB) - SINGLE CLEAN VERSION
# =========================================
def _response_json(resp):
    try:
        return resp.json() if resp else {}
    except Exception:
        return {}

def _extract_chart_payload(yahoo_json):
    if not isinstance(yahoo_json, dict):
        return {}, {}
    res = yahoo_json.get("chart", {}).get("result", [])
    if not res:
        return {}, {}
    payload = res[0] or {}
    quote = (payload.get("indicators", {}).get("quote", [{}]) or [{}])[0] or {}
    return payload, quote

def _extract_intraday_session_prices(payload, quote):
    try:
        ts_list = payload.get("timestamp") or []
        closes = quote.get("close") or []

        n = min(len(ts_list), len(closes))
        if n <= 0:
            return 0.0, 0.0, 0.0

        pre_last = 0.0
        regular_last = 0.0
        post_last = 0.0

        for ts, price in zip(ts_list[:n], closes[:n]):
            if price is None:
                continue

            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(NY_TZ)
            minutes = dt.hour * 60 + dt.minute
            p = safe(price, 0.0)

            if 240 <= minutes < 570:          # 04:00–09:30
                pre_last = p
            elif 570 <= minutes < 960:        # 09:30–16:00
                regular_last = p
            elif 960 <= minutes < 1200:       # 16:00–20:00
                post_last = p

        return pre_last, regular_last, post_last
    except Exception:
        return 0.0, 0.0, 0.0


def _chart_meta_fallback(payload):
    meta = (payload or {}).get("meta", {}) or {}
    return {
        "regularMarketPrice": safe(meta.get("regularMarketPrice")),
        "regularMarketOpen": safe(meta.get("regularMarketOpen")),
        "regularMarketPreviousClose": safe(meta.get("previousClose") or meta.get("chartPreviousClose")),
        "preMarketPrice": safe(meta.get("preMarketPrice")),
        "postMarketPrice": safe(meta.get("postMarketPrice")),
        "regularMarketDayHigh": safe(meta.get("regularMarketDayHigh")),
        "regularMarketDayLow": safe(meta.get("regularMarketDayLow")),
        "fiftyTwoWeekHigh": safe(meta.get("fiftyTwoWeekHigh")),
        "fiftyTwoWeekLow": safe(meta.get("fiftyTwoWeekLow")),
        "marketCap": safe(meta.get("marketCap")),
        "shortName": meta.get("shortName"),
        "longName": meta.get("longName"),
        "marketState": str(meta.get("marketState") or "").upper().strip(),
    }


async def fetch_ticker(symbol):
    raw_symbol = (symbol or "").strip().upper()
    if not raw_symbol:
        return None

    actual_symbol = SMART_COMMODITIES.get(
        raw_symbol,
        CFD_ALIAS.get(raw_symbol, raw_symbol)
    )

    # -------------------------
    # Yahoo endpoints
    # -------------------------
    y_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{actual_symbol}?interval=1d&range=1y"
    i_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{actual_symbol}?interval=1m&range=1d&includePrePost=true"
    q_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={actual_symbol}"

    y_res, i_res, q_res = await asyncio.gather(
        safe_request_async(y_url),
        safe_request_async(i_url),
        safe_request_async(q_url),
        return_exceptions=True
    )

    clean_sym = actual_symbol.split('.')[0].replace("=X", "").replace("=F", "")

    # -------------------------
    # 1. PARSE y_res (Historia 1d/1y)
    # -------------------------
    y_meta, y_payload, y_quote = {}, {}, {}
    closes = []
    if not isinstance(y_res, Exception) and getattr(y_res, "status_code", 0) == 200:
        try:
            y_json = _response_json(y_res)
            y_payload, y_quote = _extract_chart_payload(y_json)
            # Metadane historyczne jako dobre źródło zapasowe dla Quote
            y_meta = y_payload.get("meta", {}) if "meta" in y_payload else _chart_meta_fallback(y_payload)
            closes = [x for x in (y_quote.get("close") or []) if x is not None]
        except Exception:
            pass

    # -------------------------
    # 2. PARSE i_res (Intraday)
    # -------------------------
    i_meta, i_payload, i_quote = {}, {}, {}
    raw_state = ""
    pre_scan, regular_scan, post_scan = 0.0, 0.0, 0.0
    
    if not isinstance(i_res, Exception) and getattr(i_res, "status_code", 0) == 200:
        try:
            i_json = _response_json(i_res)
            i_payload, i_quote = _extract_chart_payload(i_json)
            i_meta = _chart_meta_fallback(i_payload)
            raw_state = i_meta.get("marketState", "")
            
            # Skaner wykresu zepchnięty tylko do roli ostatecznego fallbacku
            pre_scan, regular_scan, post_scan = _extract_intraday_session_prices(i_payload, i_quote)
        except Exception:
            pass

    # -------------------------
    # 3. PARSE q_res (Główne Quote API)
    # -------------------------
    fq = {}
    if not isinstance(q_res, Exception) and getattr(q_res, "status_code", 0) == 200:
        try:
            q_json = _response_json(q_res)
            res_list = q_json.get("quoteResponse", {}).get("result", []) or []
            fq = res_list[0] if res_list else {}
        except Exception:
            pass

    # -------------------------
    # 4. SESSION STATE
    # -------------------------
    session_state = market_status() # default fallback
    if "PRE" in raw_state:
        session_state = "PREMARKET"
    elif "POST" in raw_state:
        session_state = "POSTMARKET"
    elif "REGULAR" in raw_state:
        session_state = "OTWARTY"

    # -------------------------
    # 5. CONSOLIDATE PRICES (Szukanie oficjalnej ceny "nad wykresem")
    # -------------------------
    # Hierarchia: Główne API (fq) -> Meta z Intraday (i_meta) -> Meta z Historii (y_meta) -> Ekstrapolacja z wykresu
    
    quote_price = safe(fq.get("regularMarketPrice")) or safe(i_meta.get("regularMarketPrice")) or safe(y_meta.get("regularMarketPrice")) or regular_scan or 0.0
    open_price = safe(fq.get("regularMarketOpen")) or safe(i_meta.get("regularMarketOpen")) or safe(y_meta.get("regularMarketOpen")) or 0.0
    
    # prev_close z różnych źródeł
    quote_prev_close = safe(fq.get("regularMarketPreviousClose")) or safe(i_meta.get("previousClose")) or safe(i_meta.get("chartPreviousClose")) or safe(y_meta.get("previousClose")) or 0.0

    # PRE i POST market rygorystycznie wyciągany z meta-nagłówków, aby odpowiadał stronie www
    pre_p = safe(fq.get("preMarketPrice")) or safe(i_meta.get("preMarketPrice")) or safe(y_meta.get("preMarketPrice")) or pre_scan or 0.0
    post_p = safe(fq.get("postMarketPrice")) or safe(i_meta.get("postMarketPrice")) or safe(y_meta.get("postMarketPrice")) or post_scan or 0.0
    
    reg_p = quote_price
    prev_c = quote_prev_close or (closes[-1] if closes else 0.0)

    # -------------------------
    # 6. GŁÓWNA CENA (CURRENT PRICE)
    # -------------------------
    if session_state == "PREMARKET":
        current_price = pre_p or quote_price or prev_c
    elif session_state == "POSTMARKET":
        current_price = post_p or quote_price or prev_c
    else:
        current_price = quote_price or prev_c

    if current_price <= 0:
        current_price = prev_c

    v10_stats = build_v10_stats(closes, current_price, prev_c, pre_p, post_p)

    reg_change_open = current_price - open_price if open_price > 0 else 0.0
    reg_pct_open = (reg_change_open / open_price * 100) if open_price > 0 else 0.0

    # -------------------------
    # 7. BASIC METRICS
    # -------------------------
    day_high = safe(fq.get("regularMarketDayHigh")) or safe(i_meta.get("regularMarketDayHigh")) or 0.0
    day_low = safe(fq.get("regularMarketDayLow")) or safe(i_meta.get("regularMarketDayLow")) or 0.0
    high52 = safe(fq.get("fiftyTwoWeekHigh", 0.0))
    low52 = safe(fq.get("fiftyTwoWeekLow", 0.0))
    market_cap = safe(fq.get("marketCap", 0.0))

    pe = fq.get("trailingPE", "N/A")
    eps = fq.get("epsTrailingTwelveMonths", "N/A")

    consensus = fq.get("averageAnalystRating", "N/A")
    next_earnings = fq.get("earningsTimestamp", "N/A")

    report_date = (
        format_earnings_value(next_earnings)
        if next_earnings != "N/A"
        else "N/A"
    )

    # -------------------------
    # FINNHUB FALLBACK
    # -------------------------
    if (
        (report_date == "N/A" or consensus == "N/A")
        and not raw_symbol.startswith("^")
        and "F" not in actual_symbol
    ):
        try:
            report_date = await fetch_earnings_date(clean_sym)

            if report_date in [None, "", "N/A"]:
                report_date = (
                    format_earnings_value(next_earnings)
                    if next_earnings != "N/A"
                    else "N/A"
                )
        except Exception:
            pass

    # -------------------------
    # FINNHUB FALLBACK METRICS
    # -------------------------
    if (
        (market_cap <= 0 or pe == "N/A" or eps == "N/A")
        and not raw_symbol.startswith("^")
        and "F" not in actual_symbol
    ):
        metric_url = finnhub_url(
            "stock/metric",
            {"symbol": clean_sym, "metric": "all"}
        )

        f_metric = await fetch_json_cached(metric_url, ttl=180, cache_key=metric_url) or {}

        if f_metric:
            metrics = f_metric.get("metric", {})

            if market_cap <= 0:
                market_cap = safe(metrics.get("marketCapitalization", 0)) * 1_000_000
            if pe == "N/A" and metrics.get("peTTM") is not None:
                pe = fmt_num(metrics.get("peTTM"))
            if eps == "N/A" and metrics.get("epsTTM") is not None:
                eps = fmt_num(metrics.get("epsTTM"))
            if low52 == 0:
                low52 = safe(metrics.get("52WeekLow", 0))
            if high52 == 0:
                high52 = safe(metrics.get("52WeekHigh", 0))

    # -------------------------
    # RANGES
    # -------------------------
    session_range = f"{fmt_num(day_low)} – {fmt_num(day_high)}" if day_low > 0 else "N/A"
    yearly_range = f"{fmt_num(low52)} – {fmt_num(high52)}" if low52 > 0 else "N/A"

    # -------------------------
    # RETURN
    # -------------------------
    return {
        "symbol": actual_symbol,
        "display_symbol": raw_symbol,
        "name": normalize_company_name(
            raw_symbol,
            fq.get("shortName") or fq.get("longName"),
            display_name=CFD_FRIENDLY.get(raw_symbol)
        ),
        "session_state": session_state,
        "pre_price": pre_p,
        "post_price": post_p,
        "regular_price": reg_p,
        "current_price": current_price,
        "prev_close": prev_c,
        "open_price": open_price,
        "reg_change_open": reg_change_open,
        "reg_pct_open": reg_pct_open,
        "day_low": day_low,
        "day_high": day_high,
        "low52": low52,
        "high52": high52,
        "session_range": session_range,
        "yearly_range": yearly_range,
        "market_cap": format_cap(market_cap) if market_cap > 0 else "N/A",
        "pe": str(pe),
        "eps": str(eps),
        "consensus": consensus,
        "next_earnings": report_date,
        "v10": v10_stats
    }

async def fetch_bulk(symbols, chunk_size=4):
    out = {}
    cleaned = [s.strip().upper() for s in symbols if s and s.strip()]

    for i in range(0, len(cleaned), chunk_size):
        chunk = cleaned[i:i + chunk_size]
        res = await asyncio.gather(*(fetch_ticker(sym) for sym in chunk), return_exceptions=True)
        for sym, data in zip(chunk, res):
            if data is not None and not isinstance(data, Exception):
                out[sym] = data
    return out

async def fetch_top_gainers_by_type_async(kind="day_gainers"):
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?count=20&scrIds={kind}"
    try:
        res = await safe_request_async(url)
        if not res or getattr(res, "status_code", 0) != 200:
            return []
        data = _response_json(res)
        quotes = data.get("finance", {}).get("result", [{}])[0].get("quotes", [])
        return [q.get("symbol") for q in quotes if q.get("symbol")]
    except Exception:
        return []
# =========================================
# CATALYSTS / NEWS (FINNHUB)
# =========================================
async def fetch_market_news_general(hours_back=48, limit=30):
    data = await fetch_json_cached(finnhub_url("news", {"category": "general"}), REQUEST_CACHE_TTL["finnhub_news"], "finnhub_news:general")
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    items = []
    for row in data or []:
        ts = safe(row.get("datetime"), 0)
        if ts and datetime.fromtimestamp(ts, tz=timezone.utc) >= cutoff: items.append(row)
    return items[:limit]

async def fetch_earnings_window(days_forward=7):
    start_dt = datetime.now(NY_TZ).date()
    end_dt = start_dt + timedelta(days=days_forward)
    url = finnhub_url("calendar/earnings", {"from": start_dt.isoformat(), "to": end_dt.isoformat()})
    
    res = await safe_request_async(url, timeout=10)
    if not res or getattr(res, 'status_code', 0) != 200: return []
    
    try:
        data = res.json()
    except Exception:
        return []
        
    items = []
    for row in data.get("earningsCalendar", []) or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym or "." in sym: continue
        
        eps_est = row.get("epsEstimate")
        rev_est = row.get("revenueEstimate")
        if eps_est is None and rev_est is None: continue 
        
        items.append(row)
        
    items.sort(key=lambda x: x.get("date", ""))
    return items

# =========================================
# ASYNC ENGINE LOOP
# =========================================
def start_async_loop():
    global ASYNC_LOOP
    try:
        ASYNC_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(ASYNC_LOOP)
        def _run():
            ASYNC_LOOP_READY.set()
            ASYNC_LOOP.run_forever()
        threading.Thread(target=_run, daemon=True).start()
    except Exception as e: print("[CRITICAL ENGINE ABORT]", e)

def run_coro(coro):
    if not ASYNC_LOOP_READY.wait(timeout=5) or ASYNC_LOOP is None: return None
    try: return asyncio.run_coroutine_threadsafe(coro, ASYNC_LOOP)
    except Exception: return None

def calc_change(current, base):
    current = safe(current, 0.0)
    base = safe(base, 0.0)
    diff = current - base
    pct = (diff / base * 100) if base > 0 else 0.0
    return diff, pct

def change_color(diff):
    return "#00AA00" if diff >= 0 else "#FF0000"

# =========================================
# UI SUBSYSTEM & BASE CLASSES
# =========================================
class DataCard(MDCard):
    text = StringProperty("")
    def _update_height(self, texture_h=0):
        try:
            self.height = max(dp(240), float(texture_h) + dp(90))
        except Exception:
            pass

class TabRV(RecycleView):
    pass

KV = '''
#:import dp kivy.metrics.dp
<DataCard>:
    orientation: "vertical"
    size_hint_y: None
    padding: dp(18)
    spacing: dp(10)
    radius: [12, 12, 12, 12]
    elevation: 1
    md_bg_color: 1, 1, 1, 1
    height: _body.texture_size[1] + dp(90) if _body.texture_size[1] > 0 else dp(240)
    MDLabel:
        id: _body
        text: root.text
        markup: True
        size_hint_y: None
        height: self.texture_size[1]
        text_size: self.width - dp(36), None
        halign: "left"
        valign: "top"
        color: 0, 0, 0, 1
        on_size: self.text_size = self.width - dp(36), None
        on_texture_size: root._update_height(self.texture_size[1])
        on_ref_press: app.handle_ref(ref)

<TabRV>:
    viewclass: "DataCard"
    scroll_type: ['bars', 'content']
    RecycleBoxLayout:
        default_size: None, dp(240)
        default_size_hint: 1, None
        size_hint_y: None
        height: self.minimum_height
        orientation: "vertical"
        spacing: dp(16)
        padding: dp(18)
'''
Builder.load_string(KV)

class BaseTab(MDBoxLayout, MDTabsBase):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.is_loaded = False
        self._loading = False
        self._serial = 0
        self.full_rows = []
        self.visible_count = 0
        self.batch_size = 12
        self.padding = [dp(10), dp(12), dp(10), dp(12)]
        self.spacing = dp(12)
        
        self.control_panel = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(0), padding=[dp(12), dp(12), dp(12), dp(12)], spacing=dp(8))
        self.add_widget(self.control_panel)
        self.more_button = MDRaisedButton(text="Pokaż więcej", size_hint_y=None, height=0, opacity=0, disabled=True, on_release=self.load_more)
        self.control_panel.add_widget(self.more_button)
        self.rv = TabRV()
        self.rv.bind(scroll_y=self._on_scroll_y)
        self.add_widget(self.rv)

    def _update_more_button(self):
        has_more = len(self.full_rows) > self.visible_count
        self.more_button.height = dp(36) if has_more else 0
        self.more_button.opacity = 1 if has_more else 0
        self.more_button.disabled = not has_more

    def _apply_visible_rows(self, scroll_top=False):
        self.rv.data = [{"text": r} for r in self.full_rows[:self.visible_count]]
        self._update_more_button()
        if scroll_top: Clock.schedule_once(lambda dt: setattr(self.rv, "scroll_y", 1.0), 0.15)

    def set_rows(self, rows, scroll_top=False):
        def _ui_set(dt):
            self.full_rows = list(rows or [])
            self.visible_count = min(self.batch_size, len(self.full_rows))
            self._apply_visible_rows(scroll_top=scroll_top)
        Clock.schedule_once(_ui_set, 0)

    def load_more(self, *args):
        if self.visible_count < len(self.full_rows):
            self.visible_count = min(len(self.full_rows), self.visible_count + self.batch_size)
            self._apply_visible_rows(scroll_top=False)

    def _on_scroll_y(self, instance, value):
        if not self._loading and self.visible_count < len(self.full_rows) and value < 0.08:
            self.load_more()

    def load_data_if_needed(self):
        if not self.is_loaded:
            self.is_loaded = True
            self.refresh_data()

    def refresh_data(self, *args, **kwargs):
        if self._loading: return
        self._loading = True
        self._serial += 1
        s = self._serial
        self.set_rows(["[b]Pobieranie najnowszych danych z rynku...[/b]"], scroll_top=True)
        task = run_coro(self._safe_fetch(s, *args, **kwargs))
        if task is None: self._loading = False

    async def _safe_fetch(self, serial, *args, **kwargs):
        try:
            r = await self._fetch(*args, **kwargs)
            if serial == self._serial: self.set_rows(r, scroll_top=True)
        except Exception as e:
            if serial == self._serial: self.set_rows([f"[color=#FF0000][b]Błąd pobierania danych:[/b] {e}[/color]"], scroll_top=True)
        finally:
            if serial == self._serial: self._loading = False

    async def _fetch(self, *args, **kwargs):
        return []

# =========================================
# SPECIFIC TABS IMPLEMENTATION
# =========================================
class InfoTab(BaseTab):
    title = "Info"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(92)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(MDRaisedButton(text="Sprawdź Status", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        return [
            f"[color=#888888]Aktualizacja systemowa: {timestamp_text()}[/color]\n\n"
            f"[b]STAN SESJI GLOBALNEJ[/b]\nIdentyfikator: {session_label(market_status())}\n",
            us_market_hours_text_local(),
            build_full_glossary()
        ]

class ScannerTab(BaseTab):
    title = "Skaner"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(176)
        self.control_panel.clear_widgets()
        self.static_tickers = list(dict.fromkeys(NASDAQ_CORE[:12]))

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.input_field = MDTextField(hint_text="Wpisz Ticker", mode="rectangle")
        row.add_widget(self.input_field)
        row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(row)

        btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(12))
        btn_row.add_widget(MDRaisedButton(text="Skanuj", on_release=lambda x: self.refresh_data(mode="core")))
        btn_row.add_widget(MDRaisedButton(text="Top Gainers", on_release=lambda x: self.refresh_data(mode="gainers")))
        self.control_panel.add_widget(btn_row)
        self.control_panel.add_widget(self.more_button)


    def add_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t and t not in self.static_tickers:
            self.static_tickers.append(t)
            self.refresh_data(mode="core")

    def remove_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t in self.static_tickers:
            self.static_tickers.remove(t)
            self.refresh_data(mode="core")

    async def _fetch(self, mode="core", **kwargs):
        if mode == "gainers":
            tkrs = (await fetch_top_gainers_by_type_async("day_gainers"))[:20]
        else:
            tkrs = list(dict.fromkeys(self.static_tickers + NASDAQ_CORE[:12]))

        if not tkrs:
            return ["[color=#FF0000]Brak aktywnych tickerów.[/color]"]

        bulk = await fetch_bulk(tkrs)
        rows = [f"[color=#888888]Skan ukończony: {timestamp_text()}[/color]"]
        pre_g, post_g, open_g = [], [], []

        for s, d in bulk.items():
            v = d["v10"]

            open_diff, open_pct = calc_change(d["regular_price"], d["prev_close"])
            session_base = d["open_price"] if d["open_price"] > 0 else d["prev_close"]
            pre_diff, pre_pct = calc_change(d["pre_price"],d["regular_price"])
            post_diff, post_pct = calc_change(d["post_price"], d["regular_price"])

            if d["session_state"] == "PREMARKET":
                pre_g.append((pre_pct, s))
            elif d["session_state"] == "POSTMARKET":
                post_g.append((post_pct, s))
            else:
                open_g.append((open_pct, s))

            rows.append(
                f"[b]{s}[/b] — {d['name']} | Stan: [b]{d['session_state']}[/b]\n"
                f"Sesja otwarta (Market): [b]{d['regular_price']:.2f}[/b] "
                f"([color={change_color(open_diff)}]{open_diff:+.2f} / {open_pct:+.2f}%[/color])\n"
                f"Pre-Market: [b]{d['pre_price']:.2f}[/b] "
                f"([color={change_color(pre_diff)}]{pre_diff:+.2f} / {pre_pct:+.2f}%[/color]) | "
                f"Post-Market: [b]{d['post_price']:.2f}[/b] "
                f"([color={change_color(post_diff)}]{post_diff:+.2f} / {post_pct:+.2f}%[/color])\n"
                f"RSI: [color={color_for_rsi(v['rsi'])}]{v['rsi']:.1f}[/color] | "
                f"MACD: {v['macd']:.3f} | Hist: {format_histogram(v['hist'])}\n"
                f"Sygnał: [b][color={v['signal_color']}]{v['signal']}[/color][/b] (AI Score: {v['prob']}%)"
            )

        leaders = "[b][color=#FF9900]🔥 LIDERZY ZMIAN WG. KATEGORII SESJI[/color][/b]\n"
        if pre_g:
            pre_g.sort(reverse=True)
            leaders += "PRE: " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in pre_g[:3]]) + "\n"
        if open_g:
            open_g.sort(reverse=True)
            leaders += "REG: " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in open_g[:3]]) + "\n"
        if post_g:
            post_g.sort(reverse=True)
            leaders += "POST: " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in post_g[:3]]) + "\n"

        if pre_g or open_g or post_g:
            rows.insert(1, leaders)

        return rows


class LiveDataTab(MDBoxLayout, MDTabsBase):
    title = "Live data"

    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self.tickers = list(dict.fromkeys(["AAPL", "MSFT", "NVDA", "TSLA", "AMD"]))
        self.history = {sym: deque(maxlen=5) for sym in self.tickers}
        self._lock = threading.Lock()

        self.padding = [dp(10), dp(10), dp(10), dp(10)]
        self.spacing = dp(10)

        self.control_panel = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(156),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            spacing=dp(8),
        )
        self.add_widget(self.control_panel)

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(10))
        self.live_input = MDTextField(hint_text="Dodaj / usuń ticker, np. TSLA", mode="rectangle")
        row.add_widget(self.live_input)
        row.add_widget(MDRaisedButton(text="+", size_hint_x=0.18, on_release=self.add_ticker))
        row.add_widget(MDRaisedButton(text="-", size_hint_x=0.18, on_release=self.remove_ticker))
        self.control_panel.add_widget(row)

        btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(10))
        btn_row.add_widget(MDRaisedButton(text="Odśwież panel", on_release=lambda x: self.refresh_view()))
        btn_row.add_widget(MDRaisedButton(text="Reset domyślnych", on_release=self.reset_defaults))
        self.control_panel.add_widget(btn_row)

        self.status_label = MDLabel(
            text="[color=#888888]Czekam na dane live...[/color]",
            markup=True,
            size_hint_y=None,
            height=dp(24),
            halign="left",
            valign="middle",
        )
        self.status_label.bind(size=lambda *_: setattr(self.status_label, "text_size", (self.status_label.width, None)))
        self.control_panel.add_widget(self.status_label)

        self.scroll = ScrollView(do_scroll_x=False)
        self.container = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            spacing=dp(12),
            padding=[dp(2), dp(2), dp(2), dp(14)],
        )
        self.container.bind(minimum_height=self.container.setter("height"))
        self.scroll.add_widget(self.container)
        self.add_widget(self.scroll)

        self.refresh_view()
        self._sync_engine_symbols()

    def _normalize(self, symbol):
        return (symbol or "").strip().upper()

    def _sync_engine_symbols(self):
        app = MDApp.get_running_app()
        if app and getattr(app, "engine", None):
            try:
                run_coro(app.engine.update_symbols(self.tickers))
            except Exception:
                pass

    def _ensure_ticker(self, symbol):
        symbol = self._normalize(symbol)
        if not symbol:
            return None
        with self._lock:
            if symbol not in self.tickers:
                self.tickers.append(symbol)
            if symbol not in self.history:
                self.history[symbol] = deque(maxlen=5)
        return symbol

    def add_ticker(self, *args):
        symbol = self._ensure_ticker(self.live_input.text)
        if symbol:
            self.live_input.text = ""
            self.status_label.text = f"[color=#00AA00]Dodano ticker: {symbol}[/color]"
            self.refresh_view()
            self._sync_engine_symbols()

    def remove_ticker(self, *args):
        symbol = self._normalize(self.live_input.text)
        with self._lock:
            if symbol in self.tickers:
                self.tickers.remove(symbol)
                self.history.pop(symbol, None)
                self.status_label.text = f"[color=#FF0000]Usunięto ticker: {symbol}[/color]"
                self.refresh_view()
                self._sync_engine_symbols()
            else:
                self.status_label.text = "[color=#888888]Ticker nie jest na liście.[/color]"

    def reset_defaults(self, *args):
        with self._lock:
            self.tickers = list(dict.fromkeys(["AAPL", "MSFT", "NVDA", "TSLA", "AMD"]))
            self.history = {sym: deque(maxlen=5) for sym in self.tickers}
        self.status_label.text = "[color=#888888]Przywrócono domyślne tickery.[/color]"
        self.refresh_view()
        self._sync_engine_symbols()

    def add_live_entry(self, signal):
        symbol = self._normalize(signal.get("symbol"))
        if not symbol:
            return
        with self._lock:
            if symbol not in self.tickers:
                self.tickers.append(symbol)
            if symbol not in self.history:
                self.history[symbol] = deque(maxlen=5)
            self.history[symbol].appendleft({
                "ts": time.time(),
                "price": safe(signal.get("price")),
                "score": int(safe(signal.get("score"))),
                "signal": signal.get("signal", "TRZYMAJ"),
                "rsi": safe(signal.get("rsi")),
                "macd": safe(signal.get("macd")),
                "hist": safe(signal.get("hist")),
                "momentum": safe(signal.get("momentum")),
            })
        self.status_label.text = f"[color=#00AA00]Ostatnia aktualizacja: {symbol}[/color]"
        self.refresh_view()

    def _entry_text(self, entry):
        if not entry:
            return "[color=#777777]Brak[/color]"
        ts = datetime.fromtimestamp(entry["ts"]).strftime("%H:%M:%S")
        signal = entry.get("signal", "TRZYMAJ")
        sig_color = "#00AA00" if signal == "KUPUJ" else "#FF0000" if signal == "SPRZEDAJ" else "#888888"
        return (
            f"[b]{ts}[/b]\n"
            f"{entry['price']:.2f}\n"
            f"[color={sig_color}]{signal}[/color]\n"
            f"Score {entry['score']}%"
        )

    def _build_ticker_card(self, symbol):
        entries = list(self.history.get(symbol, deque(maxlen=5)))
        while len(entries) < 5:
            entries.append(None)

        latest = entries[0]
        subtitle = ""
        if latest:
            subtitle = f" | Cena: {latest['price']:.2f} | Score: {latest['score']}%"
        card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            padding=[dp(14), dp(12), dp(14), dp(12)],
            spacing=dp(10),
            radius=[14, 14, 14, 14],
            elevation=1,
            md_bg_color=(1, 1, 1, 1),
        )

        title = MDLabel(
            text=f"[b]{symbol}[/b]{subtitle}",
            markup=True,
            size_hint_y=None,
            height=dp(26),
            halign="left",
            valign="middle",
        )
        title.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, None)))
        card.add_widget(title)

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(96), spacing=dp(8))
        for entry in entries[:5]:
            mini = MDCard(
                orientation="vertical",
                size_hint_x=0.2,
                padding=[dp(8), dp(8), dp(8), dp(8)],
                radius=[10, 10, 10, 10],
                elevation=0,
                md_bg_color=(0.96, 0.96, 0.96, 1),
            )
            lbl = MDLabel(
                text=self._entry_text(entry),
                markup=True,
                halign="center",
                valign="middle",
            )
            lbl.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width - dp(6), None)))
            mini.add_widget(lbl)
            row.add_widget(mini)

        card.add_widget(row)
        return card

    def refresh_view(self):
        def _ui(dt):
            self.container.clear_widgets()
            with self._lock:
                tickers = list(self.tickers)
            if not tickers:
                self.container.add_widget(MDLabel(
                    text="[color=#FF0000]Brak tickerów do wyświetlenia.[/color]",
                    markup=True,
                    size_hint_y=None,
                    height=dp(28),
                ))
                return
            for symbol in tickers:
                self.container.add_widget(self._build_ticker_card(symbol))
        Clock.schedule_once(_ui, 0)


class TickerTab(BaseTab):
    title = "Ticker"

    def __init__(self, **kw):
        super().__init__(**kw)

        self.control_panel.height = dp(100)
        self.control_panel.clear_widgets()

        row = MDBoxLayout(
            orientation="horizontal",
            size_hint_y=None,
            height=dp(52),
            spacing=dp(12)
        )

        self.inp = MDTextField(
            hint_text="Wpisz np. TSLA lub CDR.WA",
            mode="rectangle"
        )

        row.add_widget(self.inp)

        row.add_widget(
            MDRaisedButton(
                text="Analizuj",
                on_release=lambda x: self.refresh_data(sym=self.inp.text)
            )
        )

        self.control_panel.add_widget(row)
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):

        sym = (kwargs.get("sym") or "AAPL").strip().upper()

        if not sym:
            return [
                "[color=#888888]Wprowadź symbol identyfikacyjny.[/color]"
            ]

        d = await fetch_ticker(sym)

        if not d:
            return [
                f"[color=#FF0000]Brak danych dla: {sym}[/color]"
            ]

        v = d.get("v10", {}) or {}

        price = safe(d.get("current_price"))
        prev_close = safe(d.get("prev_close"))

        pre_price = safe(d.get("pre_price"))
        post_price = safe(d.get("post_price"))
        regular_price = safe(d.get("regular_price"))
        open_price = safe(d.get("open_price"))

        open_diff, open_pct = calc_change(
            price,
            prev_close
        )

        pre_diff, pre_pct = calc_change(
            pre_price,
            regular_price
        )

        post_diff, post_pct = calc_change(
            post_price,
            regular_price
        )

        rsi = safe(v.get("rsi"))
        macd = safe(v.get("macd"))
        sig = safe(v.get("sig"))
        hist = safe(v.get("hist"))
        prob = safe(v.get("prob"))

        signal = v.get("signal", "BRAK")
        signal_color = v.get("signal_color", "white")

        sma30 = v.get("sma30", "N/A")
        sma90 = v.get("sma90", "N/A")

        regime = v.get("regime", "N/A")
        timing = v.get("timing", "N/A")

        report_date = d.get("next_earnings", "N/A")
        consensus = d.get("consensus", "N/A")

        return [(
            f"[b]{d['name']} ({d['symbol']})[/b] | "
            f"Faza sesji: {d['session_state']}\n"

            f"-------------------------------------------------\n"

            f"[b]STRUKTURA WYCENY I DANE BAZOWE[/b]\n"

            f"Cena aktywna: [b]{price:.2f} USD[/b] "
            f"([color={change_color(open_diff)}]"
            f"{open_diff:+.2f} | "
            f"{open_pct:+.2f}%[/color])\n"

            f"Regular Market: {regular_price:.2f} | "
            f"Prev Close: {prev_close:.2f}\n"

            f"Pre-Market: {pre_price:.2f} "
            f"([color={change_color(pre_diff)}]"
            f"{pre_diff:+.2f} / "
            f"{pre_pct:+.2f}%[/color])\n"

            f"Post-Market: {post_price:.2f} "
            f"([color={change_color(post_diff)}]"
            f"{post_diff:+.2f} / "
            f"{post_pct:+.2f}%[/color])\n"

            f"Przedział sesji: {d['session_range']}\n"
            f"Roczny (52W): {d['yearly_range']}\n"

            f"Kapitalizacja: [b]{d['market_cap']}[/b]\n"

            f"P/E: {d['pe']} | "
            f"EPS: {d['eps']}\n"

            f"Raport finansowy: [b]{report_date}[/b]\n"
            f"Konsensus: [b]{consensus}[/b]\n\n"

            f"[b]ANALIZA TECHNICZNA V10 PRO[/b]\n"

            f"RSI (14d): "
            f"[color={color_for_rsi(rsi)}]"
            f"{rsi:.1f}"
            f"[/color]\n"

            f"SMA30: {sma30} | "
            f"SMA90: {sma90}\n"

            f"MACD: {macd:.3f}\n"
            f"Signal: {sig:.3f}\n"
            f"Histogram: {format_histogram(hist)}\n"

            f"Kondycja: [b]{regime}[/b]\n"
            f"Timing wejścia: [b]{timing}[/b]\n"

            f"Rekomendacja AI: "
            f"[b][color={signal_color}]"
            f"{signal}"
            f"[/color][/b] "

            f"(Score: {prob:.0f}%)"
        )]

class AkcjeTab(BaseTab):
    title = "Akcje"

    def __init__(self, **kw):
        super().__init__(**kw)

        self.control_panel.height = dp(88)
        self.control_panel.clear_widgets()

        self.control_panel.add_widget(
            MDRaisedButton(
                text="Odśwież Portfel Core",
                on_release=lambda x: self.refresh_data()
            )
        )

        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):

        rows = [
            f"[color=#888888]Aktualizacja: {timestamp_text()}[/color]"
        ]

        bulk = await fetch_bulk(
            NASDAQ_CORE[:10] + GPW_CORE[:10]
        )

        for s, d in bulk.items():

            if not d:
                continue

            v = d.get("v10", {}) or {}

            regular_price = safe(d.get("regular_price"))
            current_price = safe(d.get("current_price"))

            pre_price = safe(d.get("pre_price"))
            post_price = safe(d.get("post_price"))

            prev_close = safe(d.get("prev_close"))

            open_diff, open_pct = calc_change(
                current_price,
                prev_close
            )

            pre_diff, pre_pct = calc_change(
                pre_price,
                regular_price
            )

            post_diff, post_pct = calc_change(
                post_price,
                regular_price
            )

            rsi = safe(v.get("rsi"))
            macd = safe(v.get("macd"))
            hist = safe(v.get("hist"))
            prob = safe(v.get("prob"))

            signal = v.get("signal", "BRAK")
            signal_color = v.get("signal_color", "white")

            rows.append(
                f"[b]{d['name']} ({s})[/b]\n"

                f"Sesja: {session_label(d['session_state'])}\n"

                f"Cena aktywna: "
                f"[b]{current_price:.2f}[/b] "

                f"([color={change_color(open_diff)}]"
                f"{open_diff:+.2f} / "
                f"{open_pct:+.2f}%[/color])\n"

                f"Regular: {regular_price:.2f}\n"

                f"Pre-Market: [b]{pre_price:.2f}[/b] "

                f"([color={change_color(pre_diff)}]"
                f"{pre_diff:+.2f} / "
                f"{pre_pct:+.2f}%[/color])\n"

                f"Post-Market: [b]{post_price:.2f}[/b] "

                f"([color={change_color(post_diff)}]"
                f"{post_diff:+.2f} / "
                f"{post_pct:+.2f}%[/color])\n"

                f"RSI: "
                f"[color={color_for_rsi(rsi)}]"
                f"{rsi:.1f}"
                f"[/color]\n"

                f"MACD: {macd:.3f}\n"
                f"Histogram: {format_histogram(hist)}\n"

                f"Sygnał AI: "
                f"[b][color={signal_color}]"
                f"{signal}"
                f"[/color][/b] "

                f"(Score: {prob:.0f}%)"
            )

        return rows

class KatalizatoryTab(BaseTab):
    title = "Katalizatory"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(88)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(MDRaisedButton(text="Aktualizuj Katalizatory rynkowe", on_release=lambda x: self.refresh_data()))
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        rows = [f"[color=#888888]Wyszukiwanie zakończone: {timestamp_text()}[/color]"]
        
        news = await fetch_market_news_general(hours_back=48, limit=30)
        keywords = ("FDA", "PDUFA", "merger", "acquisition", "earnings", "guidance", "clinical", "buyout", "trial", "deal", "spinoff")
        found_catalysts = False
        
        if news:
            rows.append("[b][color=#FF9900]ISTOTNE ZDARZENIA I NEWSY RYNKOWE (48h)[/color][/b]")
            for item in news:
                title = (item.get("headline") or item.get("summary") or "").strip()
                if not title or not any(k.lower() in title.lower() for k in keywords): continue
                
                url = item.get("url") or f"https://google.com/search?q={quote_plus(title)}"
                ts = safe(item.get("datetime"), 0)
                dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(LOCAL_TZ).strftime("%H:%M")
                rows.append(f"[{dt_str}] [ref={url}][u][b]{html.escape(title)}[/b][/u][/ref]\nŹródło: [color=#666666]{item.get('source','Finnhub')}[/color]")
                found_catalysts = True
                
        if not found_catalysts: rows.append("[color=#666666]Brak wykrytych zdarzeń o statusie katalizatora w ciągu ostatnich 48h.[/color]")
        
        cal = await fetch_earnings_window(days_forward=7)
        if cal:
            rows.append("\n[b][color=#00AA00]NADCHODZĄCE KALENDARIUM WYNIKÓW (Kolejne 7 DNI)[/color][/b]")
            for item in cal[:30]:
                s = (item.get("symbol") or item.get("ticker") or "").strip().upper()
                name = FALLBACK_NAMES.get(s, s)
                dt_text = item.get("date") or "N/A"
                eps_est = item.get("epsEstimate", "Brak")
                if s: rows.append(f"• [b]{s} ({name})[/b] — Raport finansowy: [color=#001A66]{dt_text}[/color] (Est. EPS: {eps_est})")
        else:
            rows.append("\n[color=#666666]Brak ważnych raportów finansowych w ciągu najbliższych 7 dni.[/color]")
            
        return rows

class CFDTab(BaseTab):
    title = "CFD"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(140)
        self.control_panel.clear_widgets()

        self.cfd_tickers = ["US500", "NAS100", "XAUUSD", "XAGUSD"]

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.cfd_input = MDTextField(hint_text="Dodaj instrument makro", mode="rectangle")
        row.add_widget(self.cfd_input)
        row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(row)

        btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(12))
        btn_row.add_widget(MDRaisedButton(text="Odśwież CFD", on_release=lambda x: self.refresh_data()))
        self.control_panel.add_widget(btn_row)
        self.control_panel.add_widget(self.more_button)

    def add_ticker(self, *args):
        t = self.cfd_input.text.strip().upper()
        if t and t not in self.cfd_tickers:
            self.cfd_tickers.append(t)
            self.refresh_data()

    def remove_ticker(self, *args):
        t = self.cfd_input.text.strip().upper()
        if t in self.cfd_tickers:
            self.cfd_tickers.remove(t)
            self.refresh_data()

    async def _fetch(self, *args, **kwargs):
        rows = [f"[color=#888888]Odświeżenie CFD: {timestamp_text()}[/color]"]
        bulk = await fetch_bulk(self.cfd_tickers)

        pre_g, post_g, open_g = [], [], []

        for s, d in bulk.items():
            v = d["v10"]

            if d["session_state"] == "PREMARKET":
                pre_g.append((v["pct_pre"], s))
            elif d["session_state"] == "POSTMARKET":
                post_g.append((v["pct_post"], s))
            else:
                open_g.append((d["reg_pct_open"], s))

            c_reg = "#00AA00" if d["reg_change_open"] >= 0 else "#FF0000"
            c_pre = "#00AA00" if v["pct_pre"] >= 0 else "#FF0000"
            c_post = "#00AA00" if v["pct_post"] >= 0 else "#FF0000"

            tp, sl = make_tp_sl(v["price"])

            rows.append(
                f"[b]{d['name']} ({d['symbol']})[/b]\n"
                f"Stan: [b]{d['session_state']}[/b]\n"
                f"Cena rynkowa: [b]{v['price']:.2f}[/b] "
                f"([color={c_reg}]{v['diff']:+.2f} / {v['pct_dnia']:+.2f}%[/color])\n"
                f"RSI: [color={color_for_rsi(v['rsi'])}]{v['rsi']:.1f}[/color] | MACD: {v['macd']:.3f} | Hist: {format_histogram(v['hist'])}\n"
                f"SMA30: {v['sma30']} | SMA90: {v['sma90']}\n"
                f"TP: [color=#00AA00]{tp:.2f}[/color] | SL: [color=#FF3333]{sl:.2f}[/color]\n"
                f"Sygnał: [b][color={v['signal_color']}]{v['signal']}[/color][/b] (AI Score: {v['prob']}%)"
            )

        leaders = "[b][color=#FF9900]🔥 LIDERZY ZMIAN WG. KATEGORII SESJI[/color][/b]\n"
        if pre_g:
            pre_g.sort(reverse=True)
            leaders += "PRE: " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in pre_g[:3]]) + "\n"
        if open_g:
            open_g.sort(reverse=True)
            leaders += "REG: " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in open_g[:3]]) + "\n"
        if post_g:
            post_g.sort(reverse=True)
            leaders += "POST: " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in post_g[:3]]) + "\n"

        if pre_g or open_g or post_g:
            rows.insert(1, leaders)

        return rows
# =========================================
# SYSTEM APPLICATION & INTENTS
# =========================================
class StockScanner(MDApp):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine = None

    def handle_ref(self, ref):
        ref = (ref or "").strip()
        if not ref: return
        try:
            if ref.startswith("http://") or ref.startswith("https://"):
                webbrowser.open(ref)
            else:
                webbrowser.open(f"https://www.google.com/search?q={quote_plus(ref)}")
        except Exception: pass

    def request_android_permissions(self):
        if not ANDROID: return
        try:
            request_permissions([
                Permission.INTERNET, Permission.FOREGROUND_SERVICE,
                Permission.POST_NOTIFICATIONS, Permission.WAKE_LOCK, Permission.VIBRATE,
                Permission.RECEIVE_BOOT_COMPLETED, Permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
            ])
        except Exception: pass

    def request_battery_optimization_exception(self):
        if not ANDROID: return
        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            Intent = autoclass("android.content.Intent")
            Settings = autoclass("android.provider.Settings")
            Uri = autoclass("android.net.Uri")
            activity = PythonActivity.mActivity
            package_name = activity.getPackageName()
            intent = Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS)
            intent.setData(Uri.parse("package:" + package_name))
            activity.startActivity(intent)
        except Exception: pass

    def start_foreground_service(self):
        if not ANDROID: return
        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PythonService = autoclass("org.kivy.android.PythonService")
            Intent = autoclass("android.content.Intent")
            activity = PythonActivity.mActivity
            intent = Intent(activity, PythonService)
            intent.putExtra("serviceTitle", "StockScanner V10 Pro")
            intent.putExtra("serviceDescription", "Faza Foreground Engine WebSocket V4")
            if hasattr(activity, "startForegroundService"): activity.startForegroundService(intent)
            else: activity.startService(intent)
        except Exception as e: print("Foreground error:", e)

    def init_firebase(self):
        if not ANDROID: return
        try:
            FirebaseMessaging = autoclass("com.google.firebase.messaging.FirebaseMessaging")
            FirebaseMessaging.getInstance().getToken()
        except Exception: pass


def start_v4_engine(self):
    self.engine = UltraEngineV4(ws_url=f"wss://ws.finnhub.io?token={FINNHUB_KEY}")
    self.engine.subscribe(self.on_live_signal)
    run_coro(self.engine.start())

def update_live_symbols(self, symbols):
    if self.engine:
        run_coro(self.engine.update_symbols(symbols))

def on_live_signal(self, signal):
    Clock.schedule_once(lambda dt: self.live_tab.add_live_entry(signal) if hasattr(self, "live_tab") and self.live_tab else None)

def push_live_card(self, text):
    if hasattr(self, "live_tab") and self.live_tab:
        self.live_tab.status_label.text = text

def build(self):

        self.theme_cls.primary_palette = "Teal"
        self.theme_cls.theme_style = "Light"
        self.request_android_permissions()
        
        screen = MDScreen()
        self.tabs = MDTabs()
        screen.add_widget(self.tabs)
        
        self.info_tab = InfoTab()
        self.scanner_tab = ScannerTab()
        self.ticker_tab = TickerTab()
        self.akcje_tab = AkcjeTab()
        self.katalizatory_tab = KatalizatoryTab()
        self.cfd_tab = CFDTab()
        
        self.tabs.add_widget(self.info_tab)
        self.tabs.add_widget(self.scanner_tab)
        self.tabs.add_widget(self.ticker_tab)
        self.tabs.add_widget(self.akcje_tab)
        self.tabs.add_widget(self.katalizatory_tab)
        self.tabs.add_widget(self.cfd_tab)
        
        return screen


def on_start(self):
    start_async_loop()
    Clock.schedule_once(lambda dt: self.start_foreground_service(), 0.1)
    Clock.schedule_once(lambda dt: self.init_firebase(), 0.2)
    Clock.schedule_once(lambda dt: self.request_battery_optimization_exception(), 0.3)
    Clock.schedule_once(lambda dt: self.info_tab.load_data_if_needed(), 0.5)
    Clock.schedule_once(lambda dt: self.start_v4_engine(), 1.0)
    self.tabs.bind(on_tab_switch=self.on_tab_switch)
    Clock.schedule_once(lambda dt: self.update_live_symbols(getattr(self.live_tab, "tickers", [])), 1.2)


    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if hasattr(instance_tab, "load_data_if_needed"):
            instance_tab.load_data_if_needed()

    def on_stop(self):
        global HTTP_CLIENT
        try:
            if self.engine: self.engine.stop()
        except Exception: pass
        try:
            if HTTP_CLIENT and ASYNC_LOOP and ASYNC_LOOP.is_running():
                asyncio.run_coroutine_threadsafe(HTTP_CLIENT.aclose(), ASYNC_LOOP)
        except Exception: pass
        HTTP_CLIENT = None

if __name__ == "__main__":
    StockScanner().run()
