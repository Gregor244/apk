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
import math
from datetime import datetime, timedelta, timezone, time as dt_time
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

WARSAW_TZ = ZoneInfo("Europe/Warsaw")
LONDON_TZ = ZoneInfo("Europe/London")
BERLIN_TZ = ZoneInfo("Europe/Berlin")
NEWYORK_TZ = ZoneInfo("America/New_York")

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
                "from": datetime.now(NY_TZ).date().isoformat(),
                "to": (datetime.now(NY_TZ).date() + timedelta(days=365)).isoformat()
            }
        )
        data = await fetch_json_cached(url, ttl=3600, cache_key=url)
        items = data.get("earningsCalendar", [])
        if items:
            return items[0].get("date")
    except Exception:
        pass
    return "N/A"

def detect_exchange(symbol: str):
    s = str(symbol).upper()
    if s.endswith(".WA"):
        return "GPW"
    if s.endswith(".L"):
        return "LSE"
    if s.endswith(".DE") or s.endswith(".F"):
        return "XETRA"
    return "USA"

def exchange_market_status(symbol):
    exch = detect_exchange(symbol)

    if exch == "GPW":
        now = datetime.now(WARSAW_TZ)
        start_h, start_m = 9, 0
        end_h, end_m = 17, 0
    elif exch == "LSE":
        now = datetime.now(LONDON_TZ)
        start_h, start_m = 8, 0
        end_h, end_m = 16, 30
    elif exch == "XETRA":
        now = datetime.now(BERLIN_TZ)
        start_h, start_m = 9, 0
        end_h, end_m = 17, 30
    else:
        now = datetime.now(NEWYORK_TZ)
        pre_start = dt_time(4, 0)
        regular_start = dt_time(9, 30)
        regular_end = dt_time(16, 0)
        post_end = dt_time(20, 0)

        ct = now.time()
        if pre_start <= ct < regular_start:
            return "PREMARKET"
        if regular_start <= ct < regular_end:
            return "OTWARTY"
        if regular_end <= ct < post_end:
            return "POSTMARKET"
        return "ZAMKNIĘTY"

    ct = now.time()
    market_open = dt_time(start_h, start_m)
    market_close = dt_time(end_h, end_m)

    if now.weekday() >= 5:
        return "ZAMKNIĘTY"

    if market_open <= ct <= market_close:
        return "OTWARTY"
    return "ZAMKNIĘTY"

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

LSE_CORE = ["VOD.L", "HSBA.L", "BP.L", "ULVR.L", "DGE.L", "BARC.L"]
GER_CORE = ["SAP.DE", "SIE.DE", "BMW.DE", "DTE.DE", "ALV.DE", "BAS.DE"]

EXCHANGE_SPECS = {
    "USA": {
        "label": "USA (NYSE/Nasdaq)",
        "tz": NY_TZ,
        "open_min": 9 * 60 + 30,
        "close_min": 16 * 60,
    },
    "GPW": {
        "label": "GPW (Warszawa)",
        "tz": LOCAL_TZ,
        "open_min": 9 * 60,
        "close_min": 17 * 60 + 5,
    },
    "LSE": {
        "label": "LSE (Londyn)",
        "tz": ZoneInfo("Europe/London"),
        "open_min": 8 * 60,
        "close_min": 16 * 60 + 30,
    },
    "GER": {
        "label": "GER / Xetra",
        "tz": ZoneInfo("Europe/Berlin"),
        "open_min": 9 * 60,
        "close_min": 17 * 60 + 30,
    },
}

def symbol_exchange(raw_symbol):
    sym = (raw_symbol or "").strip().upper()
    if sym.endswith(".WA"):
        return "GPW"
    if sym.endswith(".L"):
        return "LSE"
    if sym.endswith(".DE"):
        return "GER"
    return None

def exchange_current_state(exchange_code):
    spec = EXCHANGE_SPECS[exchange_code]
    now_local = datetime.now(spec["tz"])
    if now_local.weekday() >= 5:
        return "ZAMKNIĘTY"
    minutes = now_local.hour * 60 + now_local.minute
    return "OTWARTY" if spec["open_min"] <= minutes < spec["close_min"] else "ZAMKNIĘTY"

def exchange_session_state(raw_symbol, fallback_state=None):
    exch = symbol_exchange(raw_symbol)
    if not exch:
        return fallback_state or market_status()
    return exchange_current_state(exch)

def exchange_status_line(exchange_code):
    spec = EXCHANGE_SPECS[exchange_code]
    state = exchange_current_state(exchange_code)
    return f"[b]{spec['label']}[/b] | Stan: [b]{state}[/b]"

def exchange_hours_next_3_days_text(exchange_code):
    spec = EXCHANGE_SPECS[exchange_code]
    now_local = datetime.now(LOCAL_TZ)
    base_date = now_local.date()
    open_h, open_m = divmod(spec["open_min"], 60)
    close_h, close_m = divmod(spec["close_min"], 60)

    lines = [exchange_status_line(exchange_code)]
    for i in range(3):
        day = base_date + timedelta(days=i)
        day_name = day.strftime("%a")
        if day.weekday() >= 5:
            lines.append(f"• {day.strftime('%d.%m.%Y')} ({day_name}): zamknięta (weekend)")
            continue

        open_dt = datetime(day.year, day.month, day.day, open_h, open_m, tzinfo=spec["tz"]).astimezone(LOCAL_TZ)
        close_dt = datetime(day.year, day.month, day.day, close_h, close_m, tzinfo=spec["tz"]).astimezone(LOCAL_TZ)
        state_now = exchange_current_state(exchange_code)
        lines.append(
            f"• {day.strftime('%d.%m.%Y')} ({day_name}): "
            f"otwarcie {open_dt.strftime('%H:%M')} / zamknięcie {close_dt.strftime('%H:%M')} (PL) | "
            f"stan: {state_now}"
        )
    return "\n".join(lines)

def exchange_overview_text():
    return "\n\n".join(exchange_hours_next_3_days_text(code) for code in ("USA", "GPW", "LSE", "GER"))

def build_full_glossary():
    return (
        "[b][size=19]PEŁNY SŁOWNIK WSKAŹNIKÓW I POJĘĆ (V10 PRO)[/size][/b]\n\n"
        "[b]1. Analiza Techniczna i Momentum:[/b]\n"
        "• [b]SMA30 / SMA90[/b] — Średnie kroczące. Ukazują główny trend cenowy.\n"
        "• [b]RSI (14)[/b] — Poniżej 40 oznacza wyprzedanie (okazja), powyżej 65 oznacza wykupienie (ryzyko korekty).\n"
        "• [b]MACD & Histogram[/b] — Zielony, rosnący histogram potwierdza silną dominację popytu.\n\n"
        "[b]2. VWAP / Zmienność:[/b]\n"
        "• [b]VWAP[/b] — Średnia ceny ważona wolumenem.\n"
        "• [b]VWAP bandy[/b] — Pasmo wokół VWAP, które pokazuje, czy cena jest rozciągnięta.\n"
        "• [b]Zmienność[/b] — Pasma Bollingera. Pokazują, kiedy rynek się rozszerza albo uspokaja.\n"
        "• [b]ATR[/b] — Średni rzeczywisty zasięg ruchu. Pokazuje bieżącą zmienność.\n\n"
        "[b]3. Smart money / płynność:[/b]\n"
        "• [b]Płynność[/b] — Wybicie nad/doł lokalnego poziomu i szybki powrót.\n"
        "• [b]FVG[/b] — Luka między świecami po szybkim ruchu ceny.\n"
        "• [b]Strefa zleceń[/b] — Obszar, z którego ruszył silny ruch instytucjonalny.\n"
        "• [b]MSS / BOS / CHoCH[/b] — Zmiana struktury rynku i sygnał, że kierunek może się zmienić.\n"
        "• [b]Smart Money Score[/b] — Łączna ocena siły sygnałów instytucjonalnych.\n\n"
        "[b]4. Wskaźniki Fundamentalne:[/b]\n"
        "• [b]Kapitalizacja[/b] — Całkowita rynkowa wartość spółki (M=Miliony, B=Miliardy, T=Biliony).\n"
        "• [b]P/E Ratio (Cena do Zysku)[/b] — Niski wskaźnik sugeruje niedowartościowanie.\n"
        "• [b]EPS[/b] — Zysk netto wypracowany w przeliczeniu na jedną akcję.\n"
        "• [b]Konsensus Analityków[/b] — Średnia ocena z Wall Street (np. Strong Buy, Hold, Sell).\n\n"
        "[b]5. Fazy Rynku:[/b]\n"
        "• [b]PREMARKET / POSTMARKET[/b] — Handel poza głównymi godzinami.\n"
        "• [b]OTWARTY[/b] — Główna sesja giełdowa z najwyższą płynnością.\n\n"
        "[b]6. Predykcja AI:[/b]\n"
        "• [b]AI Score (0-100)[/b] — Zagregowana siła predykcyjna. >60 generuje sygnał LONG (Kupno).\n"
        "• [b]Regime / Timing[/b] — Środowisko rynkowe oraz ocena momentu wejścia.\n"
        "• [b]TP / SL[/b] — Model Take Profit i Stop Loss."
    )

# =========================================
# V10 MATH & INDICATOR ENGINE
# =========================================
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
    return round(sum(data[-period:]) / period, 2) if len(data) >= period else round(sum(data) / len(data), 2)

def macd(closes):
    closes = safe_list(closes)
    if len(closes) < 35:
        return 0.0, 0.0, 0.0
    ema12 = ema(closes, 12)
    ema26 = ema(closes, 26)
    min_len = min(len(ema12), len(ema26))
    macd_line = [ema12[i] - ema26[i] for i in range(-min_len, 0)]
    signal_line = ema(macd_line, 9)
    return round(macd_line[-1], 3), round(signal_line[-1], 3), round(macd_line[-1] - signal_line[-1], 3)

def calc_rsi(closes, period=14):
    closes = safe_list(closes)
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
    return round(100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))), 2)

def build_v10_stats(closes, current_price, prev_close, pre_price=0.0, post_price=0.0):
    closes = safe_list(closes)
    cp = safe(current_price, 0.0)
    pc = safe(prev_close, 0.0)

    diff_dnia = cp - pc
    pct_dnia = (diff_dnia / pc * 100) if pc > 0 else 0.0

    diff_pre = (pre_price - pc) if pre_price > 0 else 0.0
    pct_pre = (diff_pre / pc * 100) if pc > 0 and pre_price > 0 else 0.0

    diff_post = (post_price - pc) if post_price > 0 else 0.0
    pct_post = (diff_post / pc * 100) if pc > 0 and post_price > 0 else 0.0

    if pc <= 0 and len(closes) >= 1:
        pc = safe(closes[-1], 0.0)
    if pc <= 0:
        pc = cp

    rsi_val = calc_rsi(closes)
    macd_val, signal_val, hist = macd(closes)

    prob = 50
    if macd_val > signal_val:
        prob += 12
    else:
        prob -= 12
    if rsi_val < 40:
        prob += 10
    elif rsi_val > 65:
        prob -= 10
    if hist > 0:
        prob += 6

    regime = "Trend Wzrostowy (UP)" if rsi_val > 55 and macd_val > signal_val else "Trend Spadkowy (DOWN)" if rsi_val < 45 else "Stabilizacja (RANGE)"
    timing = "IDEALNY_MOMENT" if prob > 65 else "NEUTRALNY" if prob > 40 else "CZEKAJ"
    raw_sig = "KUPUJ" if prob > 65 else "SPRZEDAJ" if prob < 35 else "TRZYMAJ"
    sig_color = "#00AA00" if raw_sig == "KUPUJ" else "#FF0000" if raw_sig == "SPRZEDAJ" else "#888888"

    return {
        "pct_dnia": pct_dnia,
        "pct_pre": pct_pre,
        "pct_post": pct_post,
        "price": cp,
        "prev_close": pc,
        "diff": diff_dnia,
        "pct": pct_dnia,
        "rsi": rsi_val,
        "macd": macd_val,
        "sig": signal_val,
        "hist": hist,
        "sma30": sma(closes, 30),
        "sma90": sma(closes, 90),
        "regime": regime,
        "timing": timing,
        "prob": max(0, min(100, prob)),
        "signal": raw_sig,
        "signal_color": sig_color
    }

def _intraday_session_name_from_ts(ts_utc):
    try:
        dt = datetime.fromtimestamp(int(ts_utc), tz=timezone.utc).astimezone(NY_TZ)
        minutes = dt.hour * 60 + dt.minute
        if 240 <= minutes < 570:
            return "PREMARKET"
        if 570 <= minutes < 960:
            return "OTWARTY"
        if 960 <= minutes < 1200:
            return "POSTMARKET"
        return "OVERNIGHT"
    except Exception:
        return "OVERNIGHT"

def build_ohlcv_from_chart(payload, quote):
    try:
        ts_list = payload.get("timestamp") or []
        opens = quote.get("open") or []
        highs = quote.get("high") or []
        lows = quote.get("low") or []
        closes = quote.get("close") or []
        volumes = quote.get("volume") or []
        n = min(len(ts_list), len(opens), len(highs), len(lows), len(closes), len(volumes))
        if n <= 0:
            return []
        out = []
        for i in range(n):
            o = safe(opens[i], 0.0)
            h = safe(highs[i], 0.0)
            l = safe(lows[i], 0.0)
            c = safe(closes[i], 0.0)
            v = safe(volumes[i], 0.0)
            if c <= 0 or v < 0:
                continue
            if h <= 0:
                h = max(o, c)
            if l <= 0:
                l = min(o if o > 0 else c, c)
            if o <= 0:
                o = c
            out.append({
                "ts": ts_list[i],
                "open": o,
                "high": max(h, l, c, o),
                "low": min(l, h, c, o),
                "close": c,
                "volume": v,
            })
        return out
    except Exception:
        return []

def calc_vwap_from_ohlcv(ohlcv):
    if not ohlcv:
        return 0.0
    pv = 0.0
    vv = 0.0
    for bar in ohlcv:
        h = safe(bar.get("high"))
        l = safe(bar.get("low"))
        c = safe(bar.get("close"))
        v = safe(bar.get("volume"))
        if v <= 0:
            continue
        tp = (h + l + c) / 3.0
        pv += tp * v
        vv += v
    return round(pv / vv, 4) if vv > 0 else 0.0

def vwap_pro(ohlcv):
    if not ohlcv:
        return {"vwap": 0.0, "std": 0.0}
    tp_list = []
    pv = 0.0
    vol = 0.0
    for bar in ohlcv:
        h = safe(bar.get("high"))
        l = safe(bar.get("low"))
        c = safe(bar.get("close"))
        v = safe(bar.get("volume"))
        if v <= 0:
            continue
        tp = (h + l + c) / 3.0
        tp_list.append(tp)
        pv += tp * v
        vol += v
    if vol == 0 or not tp_list:
        return {"vwap": 0.0, "std": 0.0}
    vwap_val = pv / vol
    mean = sum(tp_list) / len(tp_list)
    var = sum((x - mean) ** 2 for x in tp_list) / len(tp_list)
    std = math.sqrt(var)
    return {"vwap": vwap_val, "std": std}

def vwap_bands_pro(vwap_data, mult=1.0):
    v = safe(vwap_data.get("vwap"))
    s = safe(vwap_data.get("std"))
    return {
        "vwap": round(v, 4),
        "upper": round(v + s * mult, 4),
        "lower": round(v - s * mult, 4),
    }

def bollinger_bands(closes, period=20, mult=2.0):
    closes = safe_list(closes)
    if len(closes) < period:
        return {"mid": 0.0, "upper": 0.0, "lower": 0.0}
    window = closes[-period:]
    mid = sum(window) / period
    std = math.sqrt(sum((x - mid) ** 2 for x in window) / period)
    return {
        "mid": round(mid, 4),
        "upper": round(mid + mult * std, 4),
        "lower": round(mid - mult * std, 4),
    }

def atr_from_ohlcv(ohlcv, period=14):
    if not ohlcv or len(ohlcv) < period + 1:
        return 0.0
    trs = []
    prev_close = None
    for bar in ohlcv:
        h = safe(bar.get("high"))
        l = safe(bar.get("low"))
        c = safe(bar.get("close"))
        if h <= 0 or l <= 0 or c <= 0:
            prev_close = c if c > 0 else prev_close
            continue
        if prev_close is None:
            tr = h - l
        else:
            tr = max(h - l, abs(h - prev_close), abs(l - prev_close))
        trs.append(tr)
        prev_close = c
    if not trs:
        return 0.0
    return round(sum(trs[-period:]) / min(period, len(trs)), 4)

def liquidity_sweep_detection(ohlcv, lookback=10, volume_mult=1.2):
    if not ohlcv or len(ohlcv) < max(lookback, 3):
        return {"signal": "NO_DATA", "strength": 0, "direction": "NEUTRAL", "level": 0.0}
    highs = [safe(b.get("high")) for b in ohlcv]
    lows = [safe(b.get("low")) for b in ohlcv]
    closes = [safe(b.get("close")) for b in ohlcv]
    volumes = [safe(b.get("volume")) for b in ohlcv]

    recent_slice = slice(max(0, len(ohlcv) - lookback - 1), len(ohlcv) - 1)
    recent_high = max(highs[recent_slice]) if highs[recent_slice] else 0.0
    recent_low = min(lows[recent_slice]) if lows[recent_slice] else 0.0

    current_high = highs[-1]
    current_low = lows[-1]
    current_close = closes[-1]
    current_volume = volumes[-1]
    avg_volume = sum(volumes[recent_slice]) / max(1, len(volumes[recent_slice]))

    if recent_high > 0 and current_high > recent_high and current_close < recent_high and current_volume > avg_volume * volume_mult:
        strength = min(100, int(((current_high - recent_high) / recent_high) * 10000))
        return {
            "signal": "BUY_SIDE_LIQUIDITY_SWEEP",
            "strength": strength,
            "direction": "BEARISH_REVERSAL",
            "level": round(recent_high, 4)
        }

    if recent_low > 0 and current_low < recent_low and current_close > recent_low and current_volume > avg_volume * volume_mult:
        strength = min(100, int(((recent_low - current_low) / recent_low) * 10000))
        return {
            "signal": "SELL_SIDE_LIQUIDITY_SWEEP",
            "strength": strength,
            "direction": "BULLISH_REVERSAL",
            "level": round(recent_low, 4)
        }

    if recent_high > 0 and current_close > recent_high and current_volume > avg_volume * 1.5:
        return {
            "signal": "VALID_BREAKOUT",
            "strength": 80,
            "direction": "BULLISH_CONTINUATION",
            "level": round(recent_high, 4)
        }

    if recent_low > 0 and current_close < recent_low and current_volume > avg_volume * 1.5:
        return {
            "signal": "VALID_BREAKDOWN",
            "strength": 80,
            "direction": "BEARISH_CONTINUATION",
            "level": round(recent_low, 4)
        }

    return {"signal": "NO_SWEEP", "strength": 0, "direction": "NEUTRAL", "level": 0.0}

def detect_fvg(ohlcv):
    if not ohlcv or len(ohlcv) < 3:
        return []
    gaps = []
    for i in range(2, len(ohlcv)):
        h1 = safe(ohlcv[i - 2].get("high"))
        l1 = safe(ohlcv[i - 2].get("low"))
        h3 = safe(ohlcv[i].get("high"))
        l3 = safe(ohlcv[i].get("low"))
        if l3 > h1:
            gaps.append({
                "type": "BULLISH_FVG",
                "top": round(l3, 4),
                "bottom": round(h1, 4),
                "index": i
            })
        elif h3 < l1:
            gaps.append({
                "type": "BEARISH_FVG",
                "top": round(l1, 4),
                "bottom": round(h3, 4),
                "index": i
            })
    return gaps[-5:]

def detect_order_blocks(ohlcv):
    if not ohlcv or len(ohlcv) < 4:
        return []
    obs = []
    opens = [safe(b.get("open")) for b in ohlcv]
    highs = [safe(b.get("high")) for b in ohlcv]
    lows = [safe(b.get("low")) for b in ohlcv]
    closes = [safe(b.get("close")) for b in ohlcv]

    for i in range(1, len(ohlcv)):
        prev_bearish = closes[i - 1] < opens[i - 1]
        prev_bullish = closes[i - 1] > opens[i - 1]
        if prev_bearish and closes[i] > highs[i - 1]:
            obs.append({
                "type": "BULLISH_OB",
                "high": round(highs[i - 1], 4),
                "low": round(lows[i - 1], 4),
                "index": i
            })
        if prev_bullish and closes[i] < lows[i - 1]:
            obs.append({
                "type": "BEARISH_OB",
                "high": round(highs[i - 1], 4),
                "low": round(lows[i - 1], 4),
                "index": i
            })
    return obs[-5:]

def detect_market_structure(ohlcv, lookback=10):
    if not ohlcv or len(ohlcv) < lookback:
        return {"signal": "NO_DATA", "direction": "NEUTRAL"}
    highs = [safe(b.get("high")) for b in ohlcv]
    lows = [safe(b.get("low")) for b in ohlcv]
    closes = [safe(b.get("close")) for b in ohlcv]
    recent_high = max(highs[-lookback:-1]) if len(highs) >= lookback else max(highs[:-1])
    recent_low = min(lows[-lookback:-1]) if len(lows) >= lookback else min(lows[:-1])
    current_close = closes[-1]
    mid = (recent_high + recent_low) / 2 if recent_high and recent_low else current_close

    if current_close > recent_high:
        return {"signal": "BOS_BULLISH", "direction": "UPTREND", "level": round(recent_high, 4)}
    if current_close < recent_low:
        return {"signal": "BOS_BEARISH", "direction": "DOWNTREND", "level": round(recent_low, 4)}
    if current_close > mid:
        return {"signal": "CHOCH_BULLISH", "direction": "POTENTIAL_UPTREND", "level": round(mid, 4)}
    return {"signal": "CHOCH_BEARISH", "direction": "POTENTIAL_DOWNTREND", "level": round(mid, 4)}

def smart_money_score(liquidity_signal, vwap_signal, structure_signal, rsi):
    score = 50
    liquidity_signal = (liquidity_signal or "").upper()
    vwap_signal = (vwap_signal or "").upper()
    structure_signal = (structure_signal or "").upper()

    if "SELL_SIDE" in liquidity_signal:
        score += 20
    if "BUY_SIDE" in liquidity_signal:
        score -= 20

    if vwap_signal == "OVERSOLD_DOWN":
        score += 10
    if vwap_signal == "OVEREXTENDED_UP":
        score -= 10

    if "BULLISH" in structure_signal:
        score += 15
    if "BEARISH" in structure_signal:
        score -= 15

    if rsi < 35:
        score += 10
    if rsi > 70:
        score -= 10

    score = max(0, min(100, score))
    if score >= 75:
        regime = "STRONG_LONG"
    elif score >= 60:
        regime = "LONG"
    elif score <= 25:
        regime = "STRONG_SHORT"
    elif score <= 40:
        regime = "SHORT"
    else:
        regime = "NEUTRAL"

    return {"score": score, "regime": regime}

def confluence_score_engine(
    current_price,
    vwap_signal,
    liquidity_signal,
    market_structure,
    smart_money_regime,
    rsi,
    bb_upper,
    bb_lower,
    atr_value,
):
    score = 50
    reasons = []
    vwap_signal = (vwap_signal or "").upper()
    liquidity_signal = (liquidity_signal or "").upper()
    market_structure = (market_structure or "").upper()
    smart_money_regime = (smart_money_regime or "").upper()

    if "OVEREXTENDED_UP" in vwap_signal:
        score += 8
        reasons.append("Cena nad VWAP")
    elif "OVERSOLD_DOWN" in vwap_signal:
        score -= 8
        reasons.append("Cena pod VWAP")

    if "SELL_SIDE" in liquidity_signal:
        score += 15
        reasons.append("Zabrano płynność po stronie sprzedających")
    elif "BUY_SIDE" in liquidity_signal:
        score -= 15
        reasons.append("Zabrano płynność po stronie kupujących")
    elif "VALID_BREAKOUT" in liquidity_signal:
        score += 10
        reasons.append("Potwierdzone wybicie")
    elif "VALID_BREAKDOWN" in liquidity_signal:
        score -= 10
        reasons.append("Potwierdzone wybicie w dół")

    if "BULLISH" in market_structure:
        score += 15
        reasons.append("Struktura rynku wzrostowa")
    elif "BEARISH" in market_structure:
        score -= 15
        reasons.append("Struktura rynku spadkowa")

    if "STRONG_LONG" in smart_money_regime:
        score += 20
        reasons.append("Smart money wspiera wzrost")
    elif "LONG" in smart_money_regime:
        score += 10
        reasons.append("Przewaga kupujących")
    elif "STRONG_SHORT" in smart_money_regime:
        score -= 20
        reasons.append("Smart money wspiera spadek")
    elif "SHORT" in smart_money_regime:
        score -= 10
        reasons.append("Przewaga sprzedających")

    if rsi < 30:
        score += 8
        reasons.append("Rynek wyprzedany")
    elif rsi > 70:
        score -= 8
        reasons.append("Rynek wykupiony")

    if safe(current_price) < safe(bb_lower):
        score += 4
        reasons.append("Cena poniżej pasma zmienności")
    elif safe(current_price) > safe(bb_upper):
        score -= 4
        reasons.append("Cena powyżej pasma zmienności")

    if atr_value > 0:
        reasons.append(f"ATR {atr_value:.4f}")

    score = max(0, min(100, score))
    if score >= 80:
        signal = "MOCNY KUP"
    elif score >= 65:
        signal = "KUP"
    elif score <= 20:
        signal = "MOCNA SPRZEDAŻ"
    elif score <= 35:
        signal = "SPRZEDAJ"
    else:
        signal = "NEUTRALNIE"

    confidence = round(abs(score - 50) * 2, 1)
    if "KUP" in signal:
        tp = safe(current_price) + max(atr_value, 0.0) * 2
        sl = safe(current_price) - max(atr_value, 0.0)
    elif "SPRZEDAJ" in signal:
        tp = safe(current_price) - max(atr_value, 0.0) * 2
        sl = safe(current_price) + max(atr_value, 0.0)
    else:
        tp = safe(current_price)
        sl = safe(current_price)

    if confidence >= 70:
        market_condition = "WYSOKA PEWNOŚĆ"
    elif confidence >= 40:
        market_condition = "ŚREDNIA PEWNOŚĆ"
    else:
        market_condition = "NISKA PEWNOŚĆ"

    return {
        "score": score,
        "signal": signal,
        "confidence": confidence,
        "tp": round(tp, 2),
        "sl": round(sl, 2),
        "market_condition": market_condition,
        "reasons": reasons[:5],
    }

def build_market_context(ohlcv, closes, current_price):
    closes = safe_list(closes)
    ohlcv = ohlcv or []

    vwap_raw = vwap_pro(ohlcv)
    vwap_band = vwap_bands_pro(vwap_raw, mult=1.0)
    bb = bollinger_bands(closes)
    atr_val = atr_from_ohlcv(ohlcv)
    sweep = liquidity_sweep_detection(ohlcv)
    fvg = detect_fvg(ohlcv)
    order_blocks = detect_order_blocks(ohlcv)
    structure = detect_market_structure(ohlcv)

    price = safe(current_price)
    if price > vwap_band["upper"]:
        vwap_signal = "OVEREXTENDED_UP"
    elif price < vwap_band["lower"]:
        vwap_signal = "OVERSOLD_DOWN"
    else:
        vwap_signal = "VWAP_MEAN_ZONE"

    sm_score = smart_money_score(sweep["signal"], vwap_signal, structure["signal"], calc_rsi(closes))
    confluence = confluence_score_engine(
        current_price=price,
        vwap_signal=vwap_signal,
        liquidity_signal=sweep["signal"],
        market_structure=structure["signal"],
        smart_money_regime=sm_score["regime"],
        rsi=calc_rsi(closes),
        bb_upper=bb["upper"],
        bb_lower=bb["lower"],
        atr_value=atr_val,
    )

    return {
        "vwap": {
            "vwap": vwap_band["vwap"],
            "upper": vwap_band["upper"],
            "lower": vwap_band["lower"],
            "std": round(vwap_raw.get("std", 0.0), 4),
        },
        "bollinger": bb,
        "atr": atr_val,
        "liquidity": sweep,
        "fvg": fvg,
        "order_blocks": order_blocks,
        "market_structure": structure,
        "vwap_signal": vwap_signal,
        "smart_money": sm_score,
        "confluence": confluence,
    }

def calc_vwap_sessions_from_ohlcv(ohlcv):
    if not ohlcv:
        return {
            "day": 0.0,
            "premarket": 0.0,
            "regular": 0.0,
            "postmarket": 0.0,
            "current": 0.0,
            "session": "N/A",
            "bias": "N/A",
            "diff": 0.0,
            "pct": 0.0,
            "upper": 0.0,
            "lower": 0.0,
            "bands_std": 0.0,
            "signal": "N/A",
        }

    buckets = {
        "PREMARKET": {"pv": 0.0, "v": 0.0},
        "OTWARTY": {"pv": 0.0, "v": 0.0},
        "POSTMARKET": {"pv": 0.0, "v": 0.0},
    }
    day_pv = day_v = 0.0

    for bar in ohlcv:
        price = safe(bar.get("close"), 0.0)
        volume = safe(bar.get("volume"), 0.0)
        if price <= 0 or volume <= 0:
            continue
        tp = (safe(bar.get("high")) + safe(bar.get("low")) + price) / 3.0
        day_pv += tp * volume
        day_v += volume
        sess = _intraday_session_name_from_ts(bar.get("ts"))
        if sess in buckets:
            buckets[sess]["pv"] += tp * volume
            buckets[sess]["v"] += volume

    def _vwap(bucket):
        return round(bucket["pv"] / bucket["v"], 4) if bucket["v"] > 0 else 0.0

    day_vwap = round(day_pv / day_v, 4) if day_v > 0 else 0.0
    pre_vwap = _vwap(buckets["PREMARKET"])
    reg_vwap = _vwap(buckets["OTWARTY"])
    post_vwap = _vwap(buckets["POSTMARKET"])

    vwap_raw = vwap_pro(ohlcv)
    upper = round(vwap_raw["vwap"] + vwap_raw["std"], 4) if vwap_raw["vwap"] > 0 else 0.0
    lower = round(vwap_raw["vwap"] - vwap_raw["std"], 4) if vwap_raw["vwap"] > 0 else 0.0
    return {
        "day": day_vwap,
        "premarket": pre_vwap,
        "regular": reg_vwap,
        "postmarket": post_vwap,
        "current": day_vwap,
        "session": "DAY",
        "bias": "N/A",
        "diff": 0.0,
        "pct": 0.0,
        "upper": upper,
        "lower": lower,
        "bands_std": round(vwap_raw.get("std", 0.0), 4),
        "signal": "N/A",
    }

def calc_vwap_from_intraday(payload, quote):
    try:
        ohlcv = build_ohlcv_from_chart(payload, quote)
        if not ohlcv:
            return {
                "day": 0.0,
                "premarket": 0.0,
                "regular": 0.0,
                "postmarket": 0.0,
                "current": 0.0,
                "session": "N/A",
                "bias": "N/A",
                "diff": 0.0,
                "pct": 0.0,
                "upper": 0.0,
                "lower": 0.0,
                "bands_std": 0.0,
                "signal": "N/A",
            }

        buckets = {
            "PREMARKET": {"pv": 0.0, "v": 0.0},
            "OTWARTY": {"pv": 0.0, "v": 0.0},
            "POSTMARKET": {"pv": 0.0, "v": 0.0},
        }
        day_pv = day_v = 0.0

        for bar in ohlcv:
            price = safe(bar.get("close"), 0.0)
            volume = safe(bar.get("volume"), 0.0)
            if price <= 0 or volume <= 0:
                continue
            tp = (safe(bar.get("high")) + safe(bar.get("low")) + price) / 3.0
            day_pv += tp * volume
            day_v += volume
            sess = _intraday_session_name_from_ts(bar.get("ts"))
            if sess in buckets:
                buckets[sess]["pv"] += tp * volume
                buckets[sess]["v"] += volume

        def _vwap(bucket):
            return round(bucket["pv"] / bucket["v"], 4) if bucket["v"] > 0 else 0.0

        day_vwap = round(day_pv / day_v, 4) if day_v > 0 else 0.0
        pre_vwap = _vwap(buckets["PREMARKET"])
        reg_vwap = _vwap(buckets["OTWARTY"])
        post_vwap = _vwap(buckets["POSTMARKET"])

        vwap_raw = vwap_pro(ohlcv)
        band_mult = 1.0
        upper = round(vwap_raw["vwap"] + vwap_raw["std"] * band_mult, 4) if vwap_raw["vwap"] > 0 else 0.0
        lower = round(vwap_raw["vwap"] - vwap_raw["std"] * band_mult, 4) if vwap_raw["vwap"] > 0 else 0.0

        return {
            "day": day_vwap,
            "premarket": pre_vwap,
            "regular": reg_vwap,
            "postmarket": post_vwap,
            "current": day_vwap,
            "session": "DAY",
            "bias": "N/A",
            "diff": 0.0,
            "pct": 0.0,
            "upper": upper,
            "lower": lower,
            "bands_std": round(vwap_raw.get("std", 0.0), 4),
            "signal": "N/A",
        }
    except Exception:
        return {
            "day": 0.0,
            "premarket": 0.0,
            "regular": 0.0,
            "postmarket": 0.0,
            "current": 0.0,
            "session": "N/A",
            "bias": "N/A",
            "diff": 0.0,
            "pct": 0.0,
            "upper": 0.0,
            "lower": 0.0,
            "bands_std": 0.0,
            "signal": "N/A",
        }

def format_vwap_line(vwap_data):
    v = vwap_data or {}
    day = safe(v.get("day"))
    current = safe(v.get("current"))
    bias = str(v.get("bias") or "N/A")
    diff = safe(v.get("diff"))
    pct = safe(v.get("pct"))
    upper = safe(v.get("upper"))
    lower = safe(v.get("lower"))
    return (
        f"VWAP: [b]{current:.2f}[/b] "
        f"([color={change_color(diff)}]{diff:+.2f} / {pct:+.2f}%[/color]) | "
        f"Day: {day:.2f} | Band: {lower:.2f}–{upper:.2f} | Bias: [b]{bias}[/b]"
    )

def format_compact_preview(symbol, name, current_price, vwap_data, signal=None):
    v = vwap_data or {}
    vwap = safe(v.get('current'))
    upper = safe(v.get("upper"))
    lower = safe(v.get("lower"))
    signal_txt = f" | {signal}" if signal else ""
    band_txt = f" | VWAP bandy {lower:.2f}-{upper:.2f}" if upper > 0 and lower > 0 else ""
    return f"[b]{symbol}[/b] {safe(current_price):.2f} | VWAP {vwap:.2f}{band_txt}{signal_txt} | {name}"

def format_pro_summary(d):
    vwap = d.get("vwap", {}) or {}
    bb = d.get("bollinger", {}) or {}
    liquidity = d.get("liquidity_signal", "N/A")
    sm_regime = d.get("smart_money_regime", "N/A")
    structure = d.get("market_structure", "N/A")
    direction = d.get("market_direction", "N/A")
    fvg_count = len(d.get("fvg") or [])
    ob_count = len(d.get("order_blocks") or [])
    return (
        f"{friendly_vwap_band_label()}: {safe(vwap.get('lower')):.2f}–{safe(vwap.get('upper')):.2f} | "
        f"{friendly_bb_label()}: {safe(bb.get('lower')):.2f}–{safe(bb.get('upper')):.2f} | "
        f"{friendly_liquidity_label()}: {friendly_liquidity(liquidity)}\n"
        f"FVG: {fvg_count} | {friendly_ob_label()}: {ob_count} | "
        f"{friendly_mss_label()}: {friendly_structure(structure)}\n"
        f"Kierunek: {friendly_direction(direction)} | "
        f"{friendly_smc_label()}: {friendly_regime(sm_regime)} ({d.get('smart_money_score', 0)})"
    )

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
        self.volumes = {}

    def update(self, tick):
        sym = tick.get("symbol")
        price = safe(tick.get("price"))
        volume = safe(tick.get("volume"), 0.0)
        if not sym:
            return None

        if sym not in self.prices:
            self.prices[sym] = deque(maxlen=50)
            self.volumes[sym] = deque(maxlen=50)

        self.prices[sym].append(price)
        self.volumes[sym].append(volume)
        closes = list(self.prices[sym])
        vols = list(self.volumes[sym])

        if len(closes) < 10:
            return None

        rsi = calc_rsi(closes)
        macd_val, sig, hist = macd(closes)
        momentum = (closes[-1] - closes[0]) / closes[0] * 100 if closes[0] else 0.0

        ohlcv = []
        for i, (p, v) in enumerate(zip(closes, vols)):
            if p <= 0:
                continue
            prev_p = closes[i - 1] if i > 0 else p
            ohlcv.append({
                "ts": time.time() - (len(closes) - i),
                "open": prev_p,
                "high": p,
                "low": p,
                "close": p,
                "volume": v if v > 0 else 1.0,
            })

        context = build_market_context(ohlcv, closes, price)
        vwap_info = context["vwap"]
        liquidity = context["liquidity"]
        structure = context["market_structure"]
        sm = context["smart_money"]

        score = 50
        if macd_val > sig:
            score += 15
        else:
            score -= 15
        if rsi < 35:
            score += 10
        elif rsi > 70:
            score -= 10
        if momentum > 0.5:
            score += 10
        elif momentum < -0.5:
            score -= 10
        if "SELL_SIDE" in liquidity["signal"]:
            score += 10
        if "BUY_SIDE" in liquidity["signal"]:
            score -= 10
        if "BULLISH" in structure["signal"]:
            score += 8
        if "BEARISH" in structure["signal"]:
            score -= 8

        score = max(0, min(100, score))
        signal = "KUPUJ" if score > 65 else "SPRZEDAJ" if score < 35 else "TRZYMAJ"
        confluence = context.get("confluence", {})

        return {
            "symbol": sym,
            "price": price,
            "volume": volume,
            "vwap": vwap_info["vwap"],
            "vwap_upper": vwap_info["upper"],
            "vwap_lower": vwap_info["lower"],
            "vwap_signal": context["vwap_signal"],
            "rsi": rsi,
            "macd": macd_val,
            "hist": hist,
            "score": score,
            "signal": signal,
            "momentum": momentum,
            "liquidity_signal": liquidity["signal"],
            "liquidity_strength": liquidity["strength"],
            "market_structure": structure["signal"],
            "smart_money_score": sm["score"],
            "smart_money_regime": sm["regime"],
            "confluence": confluence,
            "confluence_score": confluence.get("score", 0),
            "confluence_signal": confluence.get("signal", "NEUTRALNIE"),
            "confidence": confluence.get("confidence", 0),
            "tp": confluence.get("tp", price),
            "sl": confluence.get("sl", price),
            "market_condition": confluence.get("market_condition", "N/A"),
            "reasons": confluence.get("reasons", []),
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

def _daily_closes_by_date(payload, quote):
    try:
        ts_list = payload.get("timestamp") or []
        closes = quote.get("close") or []
        rows = []
        for ts, close in zip(ts_list, closes):
            price = safe(close, 0.0)
            if ts is None or price <= 0:
                continue
            dt = datetime.fromtimestamp(int(ts), tz=timezone.utc).astimezone(NY_TZ).date()
            rows.append((dt, price))
        if not rows:
            return []
        by_date = {}
        for dt, price in rows:
            by_date[dt] = price
        return [by_date[d] for d in sorted(by_date)]
    except Exception:
        return []

async def fetch_ticker(symbol):
    raw_symbol = (symbol or "").strip().upper()
    if not raw_symbol:
        return None

    actual_symbol = SMART_COMMODITIES.get(
        raw_symbol,
        CFD_ALIAS.get(raw_symbol, raw_symbol)
    )

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

    y_meta, y_payload, y_quote = {}, {}, {}
    closes = []
    if not isinstance(y_res, Exception) and getattr(y_res, "status_code", 0) == 200:
        try:
            y_json = _response_json(y_res)
            y_payload, y_quote = _extract_chart_payload(y_json)
            y_meta = y_payload.get("meta", {}) if "meta" in y_payload else _chart_meta_fallback(y_payload)
            closes = [x for x in (y_quote.get("close") or []) if x is not None]
        except Exception:
            pass

    i_meta, i_payload, i_quote = {}, {}, {}
    raw_state = ""
    pre_scan, regular_scan, post_scan = 0.0, 0.0, 0.0
    if not isinstance(i_res, Exception) and getattr(i_res, "status_code", 0) == 200:
        try:
            i_json = _response_json(i_res)
            i_payload, i_quote = _extract_chart_payload(i_json)
            i_meta = _chart_meta_fallback(i_payload)
            raw_state = i_meta.get("marketState", "")
            pre_scan, regular_scan, post_scan = _extract_intraday_session_prices(i_payload, i_quote)
        except Exception:
            pass

    fq = {}
    if not isinstance(q_res, Exception) and getattr(q_res, "status_code", 0) == 200:
        try:
            q_json = _response_json(q_res)
            res_list = q_json.get("quoteResponse", {}).get("result", []) or []
            fq = res_list[0] if res_list else {}
        except Exception:
            pass

    session_state = exchange_market_status(symbol)
    if "PRE" in raw_state:
        session_state = "PREMARKET"
    elif "POST" in raw_state:
        session_state = "POSTMARKET"
    elif "REGULAR" in raw_state:
        session_state = "OTWARTY"

    # Dla GPW / LSE / GER sesja zależy od ich lokalnych godzin, a nie od USA.
    session_state = exchange_session_state(raw_symbol, session_state)

    intraday_last = 0.0
    try:
        intraday_last = next((safe(x) for x in reversed(i_quote.get("close") or []) if safe(x) > 0), 0.0)
    except Exception:
        intraday_last = 0.0
    if intraday_last <= 0:
        try:
            intraday_last = next((safe(x) for x in reversed(y_quote.get("close") or []) if safe(x) > 0), 0.0)
        except Exception:
            intraday_last = 0.0

    quote_price = safe(fq.get("regularMarketPrice")) or safe(i_meta.get("regularMarketPrice")) or safe(y_meta.get("regularMarketPrice")) or regular_scan or intraday_last or 0.0
    open_price = safe(fq.get("regularMarketOpen")) or safe(i_meta.get("regularMarketOpen")) or safe(y_meta.get("regularMarketOpen")) or intraday_last or 0.0
    quote_prev_close = safe(fq.get("regularMarketPreviousClose")) or safe(i_meta.get("previousClose")) or safe(i_meta.get("chartPreviousClose")) or safe(y_meta.get("previousClose")) or 0.0
    pre_p = safe(fq.get("preMarketPrice")) or safe(i_meta.get("preMarketPrice")) or safe(y_meta.get("preMarketPrice")) or pre_scan or 0.0
    post_p = safe(fq.get("postMarketPrice")) or safe(i_meta.get("postMarketPrice")) or safe(y_meta.get("postMarketPrice")) or post_scan or 0.0

    reg_p = quote_price
    prev_c = quote_prev_close or (closes[-1] if closes else 0.0) or intraday_last
    daily_closes = _daily_closes_by_date(y_payload, y_quote)
    prev_prev_close = daily_closes[-2] if len(daily_closes) >= 2 else prev_c
    session_compare_close = prev_prev_close if session_state == "PREMARKET" and prev_prev_close > 0 else prev_c

    if session_state == "PREMARKET":
        current_price = pre_p or quote_price or intraday_last or prev_c
    elif session_state == "POSTMARKET":
        current_price = post_p or quote_price or intraday_last or prev_c
    else:
        current_price = quote_price or intraday_last or prev_c

    if current_price <= 0:
        current_price = prev_c or intraday_last

    reg_change_open = current_price - open_price if open_price > 0 else 0.0
    reg_pct_open = (reg_change_open / open_price * 100) if open_price > 0 else 0.0

    chart_payload = i_payload if i_payload else y_payload
    chart_quote = i_quote if i_quote else y_quote
    ohlcv = build_ohlcv_from_chart(chart_payload, chart_quote)
    session_vwap = calc_vwap_sessions_from_ohlcv(ohlcv)
    market_context = build_market_context(ohlcv, [bar.get("close") for bar in ohlcv] if ohlcv else closes, current_price)

    v10_stats = build_v10_stats(closes, current_price, prev_c, pre_p, post_p)

    current_vwap = safe(session_vwap.get({
        "PREMARKET": "premarket",
        "OTWARTY": "regular",
        "POSTMARKET": "postmarket",
    }.get(session_state, "day"))) or safe(session_vwap.get("day"))
    if current_vwap <= 0:
        current_vwap = current_price or prev_c or intraday_last
    vwap_diff = current_price - current_vwap if current_vwap > 0 else 0.0
    vwap_pct = (vwap_diff / current_vwap * 100) if current_vwap > 0 else 0.0
    vwap_bias = "Powyżej VWAP" if vwap_diff > 0 else "Poniżej VWAP" if vwap_diff < 0 else "Na VWAP"

    session_vwap.update({
        "current": current_vwap,
        "session": session_state,
        "bias": vwap_bias,
        "diff": vwap_diff,
        "pct": vwap_pct,
        "upper": market_context["vwap"]["upper"],
        "lower": market_context["vwap"]["lower"],
        "bands_std": market_context["vwap"]["std"],
        "signal": market_context["vwap_signal"],
    })

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
        datetime.fromtimestamp(next_earnings).strftime("%Y-%m-%d")
        if next_earnings != "N/A"
        else "N/A"
    )

    is_equity_like = not (
        actual_symbol.startswith("^")
        or actual_symbol.endswith("=F")
        or raw_symbol in CFD_ALIAS
    )

    if is_equity_like and (report_date == "N/A" or consensus == "N/A"):
        try:
            finhub_report = await fetch_finnhub_financial_report(clean_sym, days_forward=365)
            if report_date == "N/A" and finhub_report and finhub_report.get("date"):
                report_date = finhub_report.get("date", "N/A")
            if consensus == "N/A":
                finhub_consensus = await fetch_finnhub_consensus(clean_sym)
                if finhub_consensus != "N/A":
                    consensus = finhub_consensus
        except Exception:
            pass

    if is_equity_like and (
        market_cap <= 0 or pe == "N/A" or eps == "N/A"
    ):
        metric_url = finnhub_url("stock/metric", {"symbol": clean_sym, "metric": "all"})
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

    session_range = f"{fmt_num(day_low)} – {fmt_num(day_high)}" if day_low > 0 else "N/A"
    yearly_range = f"{fmt_num(low52)} – {fmt_num(high52)}" if low52 > 0 else "N/A"

    return {
        "symbol": actual_symbol,
        "display_symbol": raw_symbol,
        "session_price": current_price,
        "session_compare_close": session_compare_close,
        "prev_prev_close": prev_prev_close,
        "session_diff_prev_close": current_price - prev_c,
        "session_pct_prev_close": ((current_price - prev_c) / prev_c * 100) if prev_c > 0 else 0.0,
        "session_diff_compare": current_price - session_compare_close if session_compare_close > 0 else 0.0,
        "session_pct_compare": ((current_price - session_compare_close) / session_compare_close * 100) if session_compare_close > 0 else 0.0,
        "name": normalize_company_name(raw_symbol, fq.get("shortName") or fq.get("longName"), display_name=CFD_FRIENDLY.get(raw_symbol)),
        "exchange": symbol_exchange(raw_symbol) or "USA",
        "session_state": session_state,
        "pre_price": pre_p,
        "post_price": post_p,
        "regular_price": reg_p,
        "current_price": current_price,
        "prev_close": prev_c,
        "open_price": open_price,
        "session_change": reg_p - prev_c if prev_c > 0 else 0.0,
        "session_change_pct": ((reg_p - prev_c) / prev_c * 100) if prev_c > 0 else 0.0,
        "open_change": reg_p - open_price if open_price > 0 else 0.0,
        "open_change_pct": ((reg_p - open_price) / open_price * 100) if open_price > 0 else 0.0,
        "reg_change_open": reg_change_open,
        "reg_pct_open": reg_pct_open,
        "day_low": day_low,
        "day_high": day_high,
        "low52": low52,
        "high52": high52,
        "session_range": session_range,
        "yearly_range": yearly_range,
        "market_cap": format_cap(market_cap) if market_cap > 0 else "N/A",
        "pe": str(pe) if pe is not None else "N/A",
        "eps": str(eps) if eps is not None else "N/A",
        "consensus": str(consensus) if consensus is not None else "N/A",
        "next_earnings": report_date,
        "vwap_reference": "cena sesyjna",
        "vwap_trend": "wzrost" if vwap_diff > 0 else "spadek" if vwap_diff < 0 else "bez zmian",
        "ohlcv": ohlcv,
        "market_context": market_context,
        "vwap": {
            "day": session_vwap.get("day", 0.0),
            "premarket": session_vwap.get("premarket", 0.0),
            "regular": session_vwap.get("regular", 0.0),
            "postmarket": session_vwap.get("postmarket", 0.0),
            "current": current_vwap,
            "diff": vwap_diff,
            "pct": vwap_pct,
            "bias": vwap_bias,
            "upper": session_vwap.get("upper", 0.0),
            "lower": session_vwap.get("lower", 0.0),
            "bands_std": session_vwap.get("bands_std", 0.0),
            "signal": session_vwap.get("signal", "N/A"),
        },
        "vwap_upper": market_context["vwap"]["upper"],
        "vwap_lower": market_context["vwap"]["lower"],
        "vwap_signal": market_context["vwap_signal"],
        "bollinger": market_context["bollinger"],
        "atr": market_context["atr"],
        "liquidity_signal": market_context["liquidity"]["signal"],
        "liquidity_strength": market_context["liquidity"]["strength"],
        "liquidity_direction": market_context["liquidity"]["direction"],
        "liquidity_level": market_context["liquidity"]["level"],
        "fvg": market_context["fvg"],
        "order_blocks": market_context["order_blocks"],
        "market_structure": market_context["market_structure"]["signal"],
        "market_direction": market_context["market_structure"]["direction"],
        "market_structure_level": market_context["market_structure"].get("level", 0.0),
        "smart_money_score": market_context["smart_money"]["score"],
        "smart_money_regime": market_context["smart_money"]["regime"],
        "confluence": market_context.get("confluence", {}),
        "confluence_score": market_context.get("confluence", {}).get("score", 0),
        "confluence_signal": market_context.get("confluence", {}).get("signal", "NEUTRALNIE"),
        "confidence": market_context.get("confluence", {}).get("confidence", 0),
        "tp": market_context.get("confluence", {}).get("tp", safe(current_price)),
        "sl": market_context.get("confluence", {}).get("sl", safe(current_price)),
        "market_condition": market_context.get("confluence", {}).get("market_condition", "N/A"),
        "reasons": market_context.get("confluence", {}).get("reasons", []),
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

def friendly_vwap_signal(signal):
    signal = (signal or "").upper()
    return {
        "OVEREXTENDED_UP": "Cena powyżej VWAP",
        "OVERSOLD_DOWN": "Cena poniżej VWAP",
        "VWAP_MEAN_ZONE": "Przy VWAP",
    }.get(signal, signal or "N/A")

def friendly_liquidity(signal):
    signal = (signal or "").upper()
    return {
        "BUY_SIDE_LIQUIDITY_SWEEP": "Wyczyszczenie szczytów",
        "SELL_SIDE_LIQUIDITY_SWEEP": "Wyczyszczenie dołków",
        "VALID_BREAKOUT": "Prawdziwe wybicie w górę",
        "VALID_BREAKDOWN": "Prawdziwe wybicie w dół",
        "NO_SWEEP": "Brak płynności",
        "NO_DATA": "Brak danych",
    }.get(signal, signal or "N/A")

def friendly_structure(signal):
    signal = (signal or "").upper()
    return {
        "BOS_BULLISH": "Zmiana struktury w górę",
        "BOS_BEARISH": "Zmiana struktury w dół",
        "CHOCH_BULLISH": "Możliwa zmiana w górę",
        "CHOCH_BEARISH": "Możliwa zmiana w dół",
        "NO_DATA": "Brak danych",
    }.get(signal, signal or "N/A")

def friendly_direction(direction):
    direction = (direction or "").upper()
    return {
        "UPTREND": "Ruch wzrostowy",
        "DOWNTREND": "Ruch spadkowy",
        "POTENTIAL_UPTREND": "Możliwy ruch wzrostowy",
        "POTENTIAL_DOWNTREND": "Możliwy ruch spadkowy",
        "BULLISH_REVERSAL": "Odbicie w górę",
        "BEARISH_REVERSAL": "Odbicie w dół",
        "BULLISH_CONTINUATION": "Kontynuacja wzrostu",
        "BEARISH_CONTINUATION": "Kontynuacja spadku",
        "NEUTRAL": "Neutralnie",
    }.get(direction, direction or "N/A")

def friendly_regime(regime):
    regime = (regime or "").upper()
    return {
        "STRONG_LONG": "Mocne kupno",
        "LONG": "Kupno",
        "STRONG_SHORT": "Mocna sprzedaż",
        "SHORT": "Sprzedaż",
        "NEUTRAL": "Bez przewagi",
    }.get(regime, regime or "N/A")

def confluence_color(signal):
    sig = (signal or "").upper()
    if "MOCNY KUP" in sig or sig == "BUY":
        return "#00AA00"
    if "KUP" in sig:
        return "#22CC22"
    if "MOCNA SPRZEDAŻ" in sig or sig == "SELL":
        return "#FF0000"
    if "SPRZEDAJ" in sig:
        return "#FF5555"
    return "#AAAAAA"

def friendly_confluence_signal(signal):
    return {
        "MOCNY KUP": "Mocny kup",
        "KUP": "Kup",
        "MOCNA SPRZEDAŻ": "Mocna sprzedaż",
        "SPRZEDAJ": "Sprzedaj",
        "NEUTRALNIE": "Neutralnie",
    }.get((signal or "").upper(), signal or "N/A")

def ai_signal_color(sig):
    return confluence_color(sig)

def ai_signal_color_helper(sig):
    return ai_signal_color(sig)

def vwap_signal_color(signal):
    s = (signal or "").upper()
    if "OVEREXTENDED_UP" in s:
        return "#00AA00"
    if "OVERSOLD_DOWN" in s:
        return "#FF5555"
    return "#55AAFF"

def smart_money_color(value):
    try:
        v = float(value)
    except Exception:
        v = 0.0
    if v >= 75:
        return "#00AA00"
    if v >= 60:
        return "#22CC22"
    if v <= 25:
        return "#FF0000"
    if v <= 40:
        return "#FF5555"
    return "#AAAAAA"

def friendly_bb_label():
    return "Zmienność"

def friendly_vwap_band_label():
    return "VWAP bandy"

def friendly_liquidity_label():
    return "Płynność"

def friendly_mss_label():
    return "Zmiana struktury rynku"

def friendly_ob_label():
    return "Strefa zleceń"

def friendly_smc_label():
    return "Smart money"

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
            "[b]RYNKI USA / EU / PL — STAN I GODZINY (POLSKA)[/b]\n" + exchange_overview_text(),
            build_full_glossary()
        ]

class ScannerTab(BaseTab):
    title = "Skaner"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(220)
        self.control_panel.clear_widgets()
        self.market_mode = "USA"
        self.static_tickers = list(dict.fromkeys(NASDAQ_CORE[:12] + GPW_CORE[:6] + LSE_CORE[:6] + GER_CORE[:6]))

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.input_field = MDTextField(hint_text="Wpisz Ticker", mode="rectangle")
        row.add_widget(self.input_field)
        row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(row)

        market_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        for label, mode in [("USA", "USA"), ("GPW", "GPW"), ("LSE", "LSE"), ("GER", "GER"), ("ALL", "ALL")]:
            market_row.add_widget(MDRaisedButton(text=label, on_release=lambda x, m=mode: self._set_market_mode(m)))
        self.control_panel.add_widget(market_row)

        btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(12))
        btn_row.add_widget(MDRaisedButton(text="Skanuj", on_release=lambda x: self.refresh_data(mode="core")))
        btn_row.add_widget(MDRaisedButton(text="Top Gainers", on_release=lambda x: self.refresh_data(mode="gainers")))
        self.control_panel.add_widget(btn_row)
        self.control_panel.add_widget(self.more_button)

    def _set_market_mode(self, mode):
        self.market_mode = mode
        self.refresh_data(mode="core")

    def _match_market(self, symbol):
        s = (symbol or "").strip().upper()
        if self.market_mode == "ALL":
            return True
        if self.market_mode == "USA":
            return not (s.endswith(".WA") or s.endswith(".L") or s.endswith(".DE"))
        if self.market_mode == "GPW":
            return s.endswith(".WA")
        if self.market_mode == "LSE":
            return s.endswith(".L")
        if self.market_mode == "GER":
            return s.endswith(".DE")
        return True

    def _market_symbols(self):
        if self.market_mode == "USA":
            base = list(NASDAQ_CORE[:20])
        elif self.market_mode == "GPW":
            base = list(GPW_CORE[:20])
        elif self.market_mode == "LSE":
            base = list(LSE_CORE[:20])
        elif self.market_mode == "GER":
            base = list(GER_CORE[:20])
        else:
            base = list(dict.fromkeys(NASDAQ_CORE[:12] + GPW_CORE[:6] + LSE_CORE[:6] + GER_CORE[:6]))

        custom = [s for s in self.static_tickers if self._match_market(s)]
        return list(dict.fromkeys(base + custom))

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
            tkrs = self._market_symbols()

        if not tkrs:
            return ["[color=#FF0000]Brak aktywnych tickerów.[/color]"]

        bulk = await fetch_bulk(tkrs)
        rows = [f"[color=#888888]Skan ukończony: {timestamp_text()} | Rynek: {self.market_mode}[/color]"]
        pre_g, post_g, open_g = [], [], []

        for s, d in bulk.items():
            if not d:
                continue
            v = d.get("v10", {}) or {}
            regular_price = safe(d.get("regular_price"))
            current_price = safe(d.get("current_price"))
            prev_close = safe(d.get("prev_close"))
            pre_price = safe(d.get("pre_price"))
            post_price = safe(d.get("post_price"))
            exchange = detect_exchange(s)

            session_base = (
                safe(d.get("session_compare_close"))
                or safe(d.get("prev_close"))
                or prev_close
            )

            if exchange in ("GPW", "LSE", "XETRA"):
                session_price = current_price or regular_price or prev_close
            else:
                session_price = regular_price or current_price or prev_close

            session_diff, session_pct = calc_change(session_price, session_base)

            if abs(session_diff) < 0.0001:
                alt_diff, alt_pct = calc_change(current_price, prev_close)

                if abs(alt_diff) > abs(session_diff):
                    session_diff = alt_diff
                    session_pct = alt_pct

            pre_diff, pre_pct = calc_change(pre_price, regular_price)
            post_diff, post_pct = calc_change(post_price, regular_price)

            state = d.get("session_state")

            if state == "PREMARKET":
                pre_g.append((pre_pct, s))
            elif state == "POSTMARKET":
                post_g.append((post_pct, s))
            elif state == "OTWARTY":
                open_g.append((session_pct, s))

            vwap = d.get("vwap", {}) or {}
            ai_signal = str(d.get("confluence_signal") or v.get("signal") or "N/A")
            ai_col = ai_signal_color(ai_signal)
            vwap_sig = str(d.get("vwap_signal", "N/A"))
            vwap_col = vwap_signal_color(vwap_sig)

            conf = safe(d.get("confidence"))
            tp = safe(d.get("tp"))
            sl = safe(d.get("sl"))
            market_condition = d.get("market_condition", "N/A")
            smart_money = friendly_regime(d.get("smart_money_regime", "N/A"))
            reasons = d.get("reasons", []) or []
            reasons_text = " | ".join(reasons[:3]) if reasons else "Brak dodatkowych powodów"

            rows.append(
                f"[b]{s}[/b] — {d['name']} | Stan: [b]{state}[/b]\n"
                f"Cena sesyjna: [b]{session_price:.2f}[/b] ([color={change_color(session_diff)}]{session_diff:+.2f} / {session_pct:+.2f}%[/color]) | TP: [b]{tp:.2f}[/b] | SL: [b]{sl:.2f}[/b]\n"
                f"VWAP: [b]{safe(vwap.get('current')):.2f}[/b] ([color={change_color(safe(vwap.get('diff')))}]{safe(vwap.get('diff')):+.2f} / {safe(vwap.get('pct')):+.2f}%[/color]) | [color={vwap_col}]{friendly_vwap_signal(vwap_sig)}[/color]\n"
                f"Pre-Market: [b]{d.get('pre_price', 0):.2f}[/b] ([color={change_color(pre_diff)}]{pre_diff:+.2f} / {pre_pct:+.2f}%[/color]) | "
                f"Post-Market: [b]{d.get('post_price', 0):.2f}[/b] ([color={change_color(post_diff)}]{post_diff:+.2f} / {post_pct:+.2f}%[/color])\n"
                f"SMA30: [b]{safe(v.get('sma30')):.2f}[/b] | SMA90: [b]{safe(v.get('sma90')):.2f}[/b] | RSI: [color={color_for_rsi(v.get('rsi', 0))}]{v.get('rsi', 0):.1f}[/color] | MACD: {v.get('macd', 0):.3f} | Hist: {format_histogram(v.get('hist', 0))}\n"
                f"[b]AI / CONFLUENCE[/b]: [color={ai_col}]{friendly_confluence_signal(ai_signal)}[/color] | Pewność: [b]{conf:.0f}%[/b] | [color={ai_col}]{market_condition}[/color]\n"
                f"Smart Money: [b]{smart_money}[/b] | {friendly_liquidity_label()}: {friendly_liquidity(d.get('liquidity_signal', 'N/A'))}\n"
                f"Powody: {reasons_text}\n"
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

class TickerTab(BaseTab):
    title = "Ticker"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(136)
        self.control_panel.clear_widgets()

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.inp = MDTextField(hint_text="Wpisz np. TSLA, CDR.WA, VOD.L, SAP.DE, US500, XAUUSD", mode="rectangle")
        row.add_widget(self.inp)
        row.add_widget(MDRaisedButton(text="Analizuj", on_release=lambda x: self.refresh_data(sym=self.inp.text)))
        self.control_panel.add_widget(row)

        quick_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        for label, sym in [("GPW", "CDR.WA"), ("LSE", "VOD.L"), ("GER", "SAP.DE"), ("CFD", "US500")]:
            quick_row.add_widget(MDRaisedButton(text=label, on_release=lambda x, s=sym: self._set_symbol(s)))
        self.control_panel.add_widget(quick_row)
        self.control_panel.add_widget(self.more_button)

    def _set_symbol(self, symbol):
        self.inp.text = symbol
        self.refresh_data(sym=symbol)

    async def _fetch(self, *args, **kwargs):
        sym = (kwargs.get("sym") or "AAPL").strip().upper()
        if not sym:
            return ["[color=#888888]Wprowadź symbol identyfikacyjny.[/color]"]

        d = await fetch_ticker(sym)
        if not d:
            return [f"[color=#FF0000]Brak danych dla: {sym}[/color]"]

        v = d.get("v10", {}) or {}
        vwap = d.get("vwap", {}) or {}
        bb = d.get("bollinger", {}) or {}
        market_context = d.get("market_context", {}) or {}
        confluence = d.get("confluence", {}) or {}
        fvg = d.get("fvg") or []
        order_blocks = d.get("order_blocks") or []

        current_price = safe(d.get("current_price"))
        prev_close = safe(d.get("prev_close"))
        pre_price = safe(d.get("pre_price"))
        post_price = safe(d.get("post_price"))
        regular_price = safe(d.get("regular_price"))
        open_price = safe(d.get("open_price"))

        exchange = detect_exchange(sym)
            
        session_base = (
            safe(d.get("session_compare_close"))
            or safe(d.get("prev_close"))
            or prev_close
        )

        if exchange in ("GPW", "LSE", "XETRA"):
            session_price = current_price or regular_price or prev_close
        else:
            session_price = regular_price or current_price or prev_close

        session_diff, session_pct = calc_change(session_price, session_base)

        if abs(session_diff) < 0.0001:
            alt_diff, alt_pct = calc_change(current_price, prev_close)
            if abs(alt_diff) > abs(session_diff):
                session_diff = alt_diff
                session_pct = alt_pct

        pre_diff, pre_pct = calc_change(pre_price, regular_price)
        post_diff, post_pct = calc_change(post_price, regular_price)
        open_gap = open_price - prev_close if prev_close > 0 else 0.0
        open_gap_pct = (open_gap / prev_close * 100) if prev_close > 0 else 0.0

        vwap_sig = str(d.get("vwap_signal", "N/A"))
        vwap_col = vwap_signal_color(vwap_sig)
        vwap_trend = "wzrost" if safe(vwap.get("diff")) > 0 else "spadek" if safe(vwap.get("diff")) < 0 else "bez zmian"

        ai_signal = str(d.get("confluence_signal") or v.get("signal") or "N/A")
        ai_col = ai_signal_color(ai_signal)

        conf = safe(d.get("confidence", confluence.get("confidence", 0)))
        tp = safe(d.get("tp", confluence.get("tp", current_price)))
        sl = safe(d.get("sl", confluence.get("sl", current_price)))
        market_condition = d.get("market_condition", confluence.get("market_condition", "N/A"))
        smart_money = friendly_regime(d.get("smart_money_regime", "N/A"))
        reasons = d.get("reasons", confluence.get("reasons", [])) or []
        reasons_text = " | ".join(reasons[:3]) if reasons else "Brak dodatkowych powodów"
        
        report_date = d.get("next_earnings", "N/A")
        consensus = d.get("consensus", "N/A")
        fvg_count = len(fvg)
        ob_count = len(order_blocks)
        direction = d.get("market_direction", "N/A")
        sm_regime = d.get("smart_money_regime", "N/A")

        return [(
            f"[b]{d['name']} ({d['symbol']})[/b] | Faza sesji: {session_label(d.get('session_state', 'N/A'))}\n"
            f"-------------------------------------------------\n"
            f"[b]STRUKTURA WYCENY I DANE BAZOWE[/b]\n"
            f"Cena sesyjna: [b]{session_price:.2f} USD[/b] ([color={change_color(session_diff)}]{session_diff:+.2f} / {session_pct:+.2f}%[/color]) | TP: [b]{tp:.2f}[/b] | SL: [b]{sl:.2f}[/b]\n"
            f"Open: [b]{open_price:.2f}[/b] | Prev Close: [b]{prev_close:.2f}[/b] | Gapa otwarcia: [color={change_color(open_gap)}]{open_gap:+.2f} / {open_gap_pct:+.2f}%[/color]\n"
            f"Pre-Market: [b]{pre_price:.2f}[/b] ([color={change_color(pre_diff)}]{pre_diff:+.2f} / {pre_pct:+.2f}%[/color]) | Post-Market: [b]{post_price:.2f}[/b] ([color={change_color(post_diff)}]{post_diff:+.2f} / {post_pct:+.2f}%[/color])\n"
            f"Raport następny: [b]{report_date}[/b] | Konsensus: [b]{consensus}[/b]\n\n"
            f"[b]VWAP / ZMIENNOŚĆ[/b]\n"
            f"VWAP: [b]{safe(vwap.get('current')):.2f}[/b] ([color={change_color(safe(vwap.get('diff')))}]{safe(vwap.get('diff')):+.2f} / {safe(vwap.get('pct')):+.2f}%[/color])\n"
            f"VWAP bandy: [color={vwap_col}]{safe(vwap.get('lower')):.2f} – {safe(vwap.get('upper')):.2f}[/color] | Sygnał VWAP: [b][color={vwap_col}]{friendly_vwap_signal(vwap_sig)}[/color][/b] | Trend: [b]{vwap_trend}[/b]\n"
            f"Zmienność: [b]{safe(bb.get('lower')):.2f} – {safe(bb.get('upper')):.2f}[/b] | ATR: {safe(d.get('atr')):.4f}\n\n"
            f"[b]SMART MONEY / RYNEK[/b]\n"
            f"Płynność: [b]{friendly_liquidity(d.get('liquidity_signal', 'N/A'))}[/b] ({friendly_direction(d.get('liquidity_direction', 'N/A'))}, str. {d.get('liquidity_strength', 0)})\n"
            f"MSS: [b]{friendly_structure(d.get('market_structure', 'N/A'))}[/b]\n"
            f"Kierunek: {friendly_direction(direction)}\n"
            f"Smart money: [b]{friendly_regime(sm_regime)}[/b] | Score: {d.get('smart_money_score', 0)}\n"
            f"FVG: {fvg_count} | Strefy zleceń: {ob_count} | Smart money: {d.get('smart_money_score', 0)}\n\n"
            f"[b]TREND / SIŁA RUCHU[/b]\n"
            f"SMA30: {v.get('sma30', 'N/A')} | SMA90: {v.get('sma90', 'N/A')}\n"
            f"RSI: [color={color_for_rsi(v.get('rsi', 0))}]{v.get('rsi', 0):.1f}[/color] | MACD: {v.get('macd', 0):.3f} | Hist: {format_histogram(v.get('hist', 0))}\n"
            f"Regime: [b]{v.get('regime', 'N/A')}[/b] | Timing: [b]{v.get('timing', 'N/A')}[/b]\n\n"
            f"[b]SUGESTIA AI / CONFLUENCE[/b]\n"
            f"Sygnał AI: [b][color={ai_col}]{friendly_confluence_signal(ai_signal)}[/color][/b] | Pewność: [b]{conf:.0f}%[/b]\n"
            f"Confluence: [b][color={ai_col}]{friendly_confluence_signal(confluence.get('signal', 'NEUTRALNIE'))}[/color][/b] | TP: [b]{tp:.2f}[/b] | SL: [b]{sl:.2f}[/b] | Stan: [b]{market_condition}[/b]\n"
            f"Powody:\n{reasons_text}\n"
        )]

class AkcjeTab(BaseTab):
    title = "Akcje"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(132)
        self.control_panel.clear_widgets()
        self.market_mode = "ALL"

        market_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        for label, mode in [("USA", "USA"), ("GPW", "GPW"), ("LSE", "LSE"), ("GER", "GER"), ("ALL", "ALL")]:
            market_row.add_widget(MDRaisedButton(text=label, on_release=lambda x, m=mode: self._set_market_mode(m)))
        self.control_panel.add_widget(market_row)

        self.control_panel.add_widget(MDRaisedButton(text="Odśwież Portfel Core", on_release=lambda x: self.refresh_data()))
        self.control_panel.add_widget(self.more_button)

    def _set_market_mode(self, mode):
        self.market_mode = mode
        self.refresh_data()

    def _symbols_for_mode(self):
        if self.market_mode == "USA":
            return NASDAQ_CORE[:8]
        if self.market_mode == "GPW":
            return GPW_CORE[:8]
        if self.market_mode == "LSE":
            return LSE_CORE[:8]
        if self.market_mode == "GER":
            return GER_CORE[:8]
        return NASDAQ_CORE[:8] + GPW_CORE[:8] + LSE_CORE[:8] + GER_CORE[:8]

    async def _fetch(self, *args, **kwargs):
        rows = [f"[color=#888888]Aktualizacja: {timestamp_text()} | Rynek: {self.market_mode}[/color]"]
        bulk = await fetch_bulk(self._symbols_for_mode())

        top_smc = []
        shown = 0

        for s, d in bulk.items():
            if not d:
                continue
            if d.get("session_state") not in ("PREMARKET", "OTWARTY"):
                continue

            v = d.get("v10", {}) or {}
            vwap = d.get("vwap", {}) or {}
            regular_price = safe(d.get("regular_price"))
            current_price = safe(d.get("current_price"))
            session_price = regular_price or current_price
            pre_price = safe(d.get("pre_price"))
            post_price = safe(d.get("post_price"))
            prev_close = safe(d.get("prev_close"))
            open_price = safe(d.get("open_price"))
            exchange = detect_exchange(s)
            
            session_base = (
                safe(d.get("session_compare_close"))
                or safe(d.get("prev_close"))
                or prev_close
            )
            session_diff, session_pct = calc_change(session_price, session_base)

            if abs(session_diff) < 0.0001:
                alt_diff, alt_pct = calc_change(current_price, prev_close)

                if abs(alt_diff) > abs(session_diff):
                    session_diff = alt_diff
                    session_pct = alt_pct

            open_gap = safe(open_price) - prev_close if prev_close > 0 else 0.0
            open_gap_pct = (open_gap / prev_close * 100) if prev_close > 0 else 0.0
            pre_diff, pre_pct = calc_change(pre_price, regular_price)
            post_diff, post_pct = calc_change(post_price, regular_price)

            sm_score = safe(d.get("smart_money_score"))
            top_smc.append((sm_score, s))
            shown += 1

            sm_col = smart_money_color(sm_score)
            vwap_trend = "wzrost" if safe(vwap.get("diff")) > 0 else "spadek" if safe(vwap.get("diff")) < 0 else "bez zmian"

            rows.append(
                f"[b]{d['name']} ({s})[/b]| Sygnał AI: [b][color={v.get('signal_color', 'white')}] {v.get('signal', 'BRAK')}[/color][/b] | (Score: {v.get('prob', 0):.0f}%)\n \n"
                f"Sesja: {session_label(d['session_state'])}\n"
                f"Cena sesyjna: [b]{session_price:.2f}[/b] ([color={change_color(session_diff)}]{session_diff:+.2f} / {session_pct:+.2f}%[/color]) | "
                f"TP: [b]{make_tp_sl(session_price)[0]:.2f}[/b] | SL: [b]{make_tp_sl(session_price)[1]:.2f}[/b]\n"
                f"VWAP: {friendly_vwap_signal(d.get('vwap_signal', 'N/A'))} / {vwap_trend}\n"
                f"VWAP: [b]{safe(vwap.get('current')):.2f}[/b] | {friendly_vwap_band_label()}: {safe(vwap.get('lower')):.2f} – {safe(vwap.get('upper')):.2f}\n"
                f"{friendly_liquidity_label()}: {friendly_liquidity(d.get('liquidity_signal', 'N/A'))} | {friendly_mss_label()}: {friendly_structure(d.get('market_structure', 'N/A'))} | {friendly_smc_label()}: [color={sm_col}]{int(sm_score)}[/color]\n"
                f"SMA30: {v.get('sma30', 'N/A')} | SMA90: {v.get('sma90', 'N/A')}\n"
                f"RSI: [color={color_for_rsi(v.get('rsi', 0))}]{v.get('rsi', 0):.1f}[/color] | MACD: {v.get('macd', 0):.3f} | Hist: {format_histogram(v.get('hist', 0))}\n"
                f"Zmienność: {safe(d.get('bollinger', {}).get('lower')):.2f} – {safe(d.get('bollinger', {}).get('upper')):.2f} | ATR: {safe(d.get('atr')):.4f}"
            )

        if shown == 0:
            rows.append("[color=#666666]Brak akcji z aktywnej sesji premarket / otwartej dla tych rynków.[/color]")

        if top_smc:
            top_smc.sort(reverse=True)
            rows.insert(1, "[b][color=#FF9900]Top Smart Money:[/color][/b] " + ", ".join([f"{s} ({score:.0f})" for score, s in top_smc[:5]]))

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
            if not d:
                continue
            v = d.get("v10", {}) or {}
            vwap = d.get("vwap", {}) or {}

            if d.get("session_state") == "PREMARKET":
                pre_g.append((v.get("pct_pre", 0), s))
            elif d.get("session_state") == "POSTMARKET":
                post_g.append((v.get("pct_post", 0), s))
            else:
                open_g.append((d.get("reg_pct_open", 0), s))

            session_price = safe(d.get("regular_price")) or safe(d.get("current_price")) or safe(d.get("prev_close"))
            current_price = safe(d.get("current_price"))
            prev_close = safe(d.get("prev_close"))
            exchange = detect_exchange(s)
            
            session_base = (
                safe(d.get("session_compare_close"))
                or safe(d.get("prev_close"))
                or prev_close
            )
            session_diff, session_pct = calc_change(session_price, session_base)
            
            if abs(session_diff) < 0.0001:
                alt_diff, alt_pct = calc_change(current_price, prev_close)

                if abs(alt_diff) > abs(session_diff):
                    session_diff = alt_diff
                    session_pct = alt_pct
            
            tp, sl = make_tp_sl(session_price)

            vwap_trend = "wzrost" if safe(vwap.get("diff")) > 0 else "spadek" if safe(vwap.get("diff")) < 0 else "bez zmian"

            rows.append(
                f"[b]{d['name']} ({s})[/b] |Sygnał AI: [b][color={v.get('signal_color', 'white')}] {v.get('signal', 'BRAK')}[/color][/b] | "
                f"Score: {v.get('prob', 0):.0f}%\n"
                f"Cena sesyjna: [b]{session_price:.2f}[/b] ([color={change_color(session_diff)}]{session_diff:+.2f} / {session_pct:+.2f}%[/color]) |TP: {tp:.2f} | SL: {sl:.2f}\n"
                f"VWAP: {friendly_vwap_signal(d.get('vwap_signal', 'N/A'))} / {vwap_trend}\n"
                f"VWAP: [b]{safe(vwap.get('current')):.2f}[/b] | {friendly_vwap_band_label()}: {safe(vwap.get('lower')):.2f} – {safe(vwap.get('upper')):.2f}\n"
                f"{friendly_liquidity_label()}: {friendly_liquidity(d.get('liquidity_signal', 'N/A'))} | {friendly_mss_label()}: {friendly_structure(d.get('market_structure', 'N/A'))} | {friendly_smc_label()}: {int(safe(d.get('smart_money_score')))}"
            )

        if pre_g:
            pre_g.sort(reverse=True)
            rows.append("[b]PRE:[/b] " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in pre_g[:3]]))
        if open_g:
            open_g.sort(reverse=True)
            rows.append("[b]REG:[/b] " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in open_g[:3]]))
        if post_g:
            post_g.sort(reverse=True)
            rows.append("[b]POST:[/b] " + ", ".join([f"{s} ({p:+.1f}%)" for p, s in post_g[:3]]))

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
                if not title or not any(k.lower() in title.lower() for k in keywords):
                    continue
                url = item.get("url") or f"https://google.com/search?q={quote_plus(title)}"
                ts = safe(item.get("datetime"), 0)
                dt_str = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(LOCAL_TZ).strftime("%H:%M")
                rows.append(f"[{dt_str}] [ref={url}][u][b]{html.escape(title)}[/b][/u][/ref]\nŹródło: [color=#666666]{item.get('source','Finnhub')}[/color]")
                found_catalysts = True

        if not found_catalysts:
            rows.append("[color=#666666]Brak wykrytych zdarzeń o statusie katalizatora w ciągu ostatnich 48h.[/color]")

        cal = await fetch_earnings_window(days_forward=7)
        if cal:
            rows.append("\n[b][color=#00AA00]NADCHODZĄCE KALENDARIUM WYNIKÓW (7 DNI)[/color][/b]")
            for item in cal[:30]:
                s = (item.get("symbol") or item.get("ticker") or "").strip().upper()
                name = FALLBACK_NAMES.get(s, s)
                dt_text = item.get("date") or "N/A"
                eps_est = item.get("epsEstimate", "Brak")
                if s:
                    rows.append(f"• [b]{s} ({name})[/b] | {dt_text} | EPS: {eps_est}")
        else:
            rows.append("\n[color=#666666]Brak ważnych raportów finansowych w ciągu najbliższych 7 dni.[/color]")

        return rows

class LiveDataTab(MDBoxLayout, MDTabsBase):
    title = "Live data"

    def __init__(self, **kw):
        super().__init__(orientation="vertical", **kw)
        self.tickers = list(dict.fromkeys(["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "CDR.WA", "PKO.WA"]))
        self.history = {sym: deque(maxlen=5) for sym in self.tickers}
        self._lock = threading.Lock()

        self.padding = [dp(10), dp(10), dp(10), dp(10)]
        self.spacing = dp(10)

        # Zwiększono wysokość, aby pomieścić przyciski rynków
        self.control_panel = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(204),
            padding=[dp(12), dp(12), dp(12), dp(12)],
            spacing=dp(8),
        )
        self.add_widget(self.control_panel)

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(10))
        self.live_input = MDTextField(hint_text="Dodaj ticker: TSLA, CDR.WA, PKO.WA, XAUUSD", mode="rectangle")
        row.add_widget(self.live_input)
        row.add_widget(MDRaisedButton(text="+", size_hint_x=0.18, on_release=self.add_ticker))
        row.add_widget(MDRaisedButton(text="-", size_hint_x=0.18, on_release=self.remove_ticker))
        self.control_panel.add_widget(row)

        # NOWE: Rząd z wyborem rynków
        market_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(8))
        for label, mode in [("USA", "USA"), ("GPW", "GPW"), ("LSE", "LSE"), ("GER", "GER"), ("ALL", "ALL")]:
            market_row.add_widget(MDRaisedButton(text=label, on_release=lambda x, m=mode: self._set_market_mode(m)))
        self.control_panel.add_widget(market_row)

        btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(10))
        btn_row.add_widget(MDRaisedButton(text="Odśwież panel", on_release=lambda x: self.refresh_view()))
        btn_row.add_widget(MDRaisedButton(text="Reset domyślnych", on_release=self.reset_defaults))
        self.live_toggle_btn = MDRaisedButton(text="Live update: ON", on_release=self.toggle_live_updates)
        btn_row.add_widget(self.live_toggle_btn)
        self.control_panel.add_widget(btn_row)

        self.live_updates_enabled = True

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
        self._schedule_snapshot_fallback()

    def _normalize(self, symbol):
        return (symbol or "").strip().upper()

    def _active_symbols(self):
        if not getattr(self, "live_updates_enabled", True):
            return []
        return list(self.tickers)

    def _market_is_closed(self):
        return market_status() == "ZAMKNIĘTY"

    def _sync_engine_symbols(self):
        app = MDApp.get_running_app()
        if app and getattr(app, "engine", None):
            try:
                run_coro(app.engine.update_symbols(self._active_symbols()))
            except Exception:
                pass

    def toggle_live_updates(self, *args):
        self.live_updates_enabled = not getattr(self, "live_updates_enabled", True)
        self.live_toggle_btn.text = f"Live update: {'ON' if self.live_updates_enabled else 'OFF'}"
        self.status_label.text = (
            "[color=#00AA00]Live update włączony.[/color]"
            if self.live_updates_enabled
            else "[color=#FF9900]Live update wyłączony.[/color]"
        )
        self._sync_engine_symbols()

    def _set_market_mode(self, mode):
        with self._lock:
            if mode == "USA":
                self.tickers = list(dict.fromkeys(NASDAQ_CORE[:8]))
            elif mode == "GPW":
                self.tickers = list(dict.fromkeys(GPW_CORE[:8]))
            elif mode == "LSE":
                self.tickers = list(dict.fromkeys(LSE_CORE[:8]))
            elif mode == "GER":
                self.tickers = list(dict.fromkeys(GER_CORE[:8]))
            else: # ALL
                self.tickers = list(dict.fromkeys(["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "CDR.WA", "PKO.WA"]))
            
            for sym in self.tickers:
                if sym not in self.history:
                    self.history[sym] = deque(maxlen=5)

        self.status_label.text = f"[color=#888888]Zmieniono rynek na: {mode}[/color]"
        self.refresh_snapshot()
        self._sync_engine_symbols()

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
            self.tickers = list(dict.fromkeys(["AAPL", "MSFT", "NVDA", "TSLA", "AMD", "CDR.WA", "PKO.WA"]))
            self.history = {sym: deque(maxlen=5) for sym in self.tickers}
        self.status_label.text = "[color=#888888]Przywrócono domyślne tickery.[/color]"
        self.refresh_view()
        self._sync_engine_symbols()

    def add_live_entry(self, signal):
        if not self.live_updates_enabled and self._market_is_closed():
            return
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
                "vwap": safe(signal.get("vwap")),
                "vwap_upper": safe(signal.get("vwap_upper")),
                "vwap_lower": safe(signal.get("vwap_lower")),
                "score": int(safe(signal.get("score"))),
                "signal": signal.get("signal", "TRZYMAJ"),
                "rsi": safe(signal.get("rsi")),
                "macd": safe(signal.get("macd")),
                "hist": safe(signal.get("hist")),
                "momentum": safe(signal.get("momentum")),
                "liquidity_signal": signal.get("liquidity_signal", "N/A"),
                "smart_money_score": safe(signal.get("smart_money_score")),
                "smart_money_regime": signal.get("smart_money_regime", "N/A"),
                "vwap_signal": signal.get("vwap_signal", "N/A"),
                "confluence_signal": signal.get("confluence_signal", "NEUTRALNIE"),
                "confidence": safe(signal.get("confidence", 0)),
            })
        latest = self.history[symbol][0] if self.history.get(symbol) else {}
        self.status_label.text = f"[color=#00AA00]Ostatnia aktualizacja: {symbol} | VWAP: {latest.get('vwap', 0.0):.2f}[/color]"
        self.refresh_view()

    def _entry_text(self, entry, prev=None):
        if not entry:
            return "[color=#777777]Brak[/color]"
        ts = datetime.fromtimestamp(entry["ts"]).strftime("%H:%M:%S")
        signal = entry.get("signal", "TRZYMAJ")
        sig_color = "#00AA00" if signal == "KUPUJ" else "#FF0000" if signal == "SPRZEDAJ" else "#888888"
        prev_price = safe(prev.get("price")) if prev else 0.0
        price = safe(entry.get("price"))
        if prev and prev_price > 0:
            price_color = "#00AA00" if price > prev_price else "#FF0000" if price < prev_price else "#888888"
            price_line = f"[color={price_color}]Cena: {price:.2f} ({price - prev_price:+.2f})[/color]"
        else:
            price_line = f"Cena: {price:.2f}"
        vwap = safe(entry.get('vwap', 0.0))
        upper = safe(entry.get("vwap_upper"))
        lower = safe(entry.get("vwap_lower"))
        vwap_line = f"VWAP: {vwap:.2f}" if vwap > 0 else "VWAP: -"
        band_line = f"VWAP bandy: {lower:.2f}-{upper:.2f}" if upper > 0 and lower > 0 else "VWAP bandy: -"
        return (
            f"[b]{ts}[/b]\n"
            f"{price_line}\n"
            f"{vwap_line}\n"
            f"{band_line}\n"
            f"[color={sig_color}]{signal}[/color]\n"
            f"SMC {int(entry.get('smart_money_score', 0))}% | {friendly_liquidity(entry.get('liquidity_signal', 'N/A'))}"
        )

    def _build_ticker_card(self, symbol):
        entries = list(self.history.get(symbol, deque(maxlen=5)))
        while len(entries) < 5:
            entries.append(None)

        latest = entries[0]
        subtitle = ""
        if latest:
            # Przechwytujemy bezpiecznie dane AI/SMC, by uniknąć NameError
            c_sig = latest.get("confluence_signal", "NEUTRALNIE")
            c_conf = latest.get("confidence", 0)
            sm_regime = friendly_regime(latest.get("smart_money_regime", "N/A"))
            c_col = ai_signal_color(c_sig)

            subtitle = (
                f" | Cena: {latest.get('price', 0):.2f}"
                f" | VWAP: {latest.get('vwap', 0.0):.2f}"
                f" | VWAP bandy: {latest.get('vwap_lower', 0.0):.2f}-{latest.get('vwap_upper', 0.0):.2f}"
                f" | SMC: {latest.get('smart_money_score', 0)}%\n"
                f"AI / Confluence: [b][color={c_col}]{c_sig}[/color][/b] | Pewność: [b]{c_conf:.0f}%[/b] | Smart Money: [b]{sm_regime}[/b]"
            )

        card = MDCard(
            orientation="vertical",
            size_hint_y=None,
            height=dp(340),  # Podniesiono dla dodatkowej linijki
            padding=[dp(16), dp(18), dp(16), dp(18)],
            spacing=dp(16),
            radius=[14, 14, 14, 14],
            elevation=1,
            md_bg_color=(1, 1, 1, 1),
        )

        title_box = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(92), spacing=dp(6))
        title = MDLabel(
            text=f"[b]{symbol}[/b]",
            markup=True,
            size_hint_y=None,
            height=dp(26),
            halign="left",
            valign="middle",
        )
        title.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, None)))
        
        subtitle_lbl = MDLabel(
            text=subtitle or " ",
            markup=True,
            size_hint_y=None,
            height=dp(52),  # Podniesiono dla tekstów w dwóch linijkach
            halign="left",
            valign="middle",
            theme_text_color="Secondary" if hasattr(MDLabel, "theme_text_color") else None,
        )
        subtitle_lbl.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width, None)))
        
        title_box.add_widget(title)
        title_box.add_widget(subtitle_lbl)
        card.add_widget(title_box)

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(176), spacing=dp(14))
        for i, entry in enumerate(entries[:5]):
            prev = entries[i + 1] if i + 1 < len(entries) else None
            mini = MDCard(
                orientation="vertical",
                size_hint_x=0.2,
                size_hint_y=None,
                height=dp(168),
                padding=[dp(10), dp(12), dp(10), dp(12)],
                radius=[10, 10, 10, 10],
                elevation=0,
                md_bg_color=(0.96, 0.96, 0.96, 1),
            )
            lbl = MDLabel(
                text=self._entry_text(entry, prev),
                markup=True,
                halign="center",
                valign="middle",
            )
            lbl.bind(size=lambda inst, *_: setattr(inst, "text_size", (inst.width - dp(10), inst.height - dp(10))))
            mini.add_widget(lbl)
            row.add_widget(mini)

        card.add_widget(row)
        return card

    def _schedule_snapshot_fallback(self):
        if getattr(self, "_snapshot_fallback_started", False):
            return
        self._snapshot_fallback_started = True
        Clock.schedule_once(lambda dt: self.refresh_snapshot(), 1.0)
        Clock.schedule_interval(lambda dt: self.refresh_snapshot(), 45)

    def refresh_snapshot(self, *args):
        if getattr(self, "_snapshot_loading", False):
            return
        self._snapshot_loading = True
        task = run_coro(self._snapshot_fetch())
        if task is None:
            self._snapshot_loading = False

    async def _snapshot_fetch(self):
        try:
            if not self.live_updates_enabled and self._market_is_closed():
                self.status_label.text = "[color=#888888]Rynek zamknięty — live update wyłączony.[/color]"
                return
            with self._lock:
                tickers = list(self._active_symbols())
            if not tickers:
                return
            bulk = await fetch_bulk(tickers)
            with self._lock:
                for symbol, data in bulk.items():
                    if not data:
                        continue
                    v = data.get("v10", {}) or {}
                    price = safe(data.get("regular_price")) or safe(data.get("current_price")) or safe(data.get("prev_close"))
                    if price <= 0:
                        continue
                    if symbol not in self.history:
                        self.history[symbol] = deque(maxlen=5)
                        
                    self.history[symbol].appendleft({
                        "ts": time.time(),
                        "price": price,
                        "vwap": safe(data.get("vwap", {}).get("current")),
                        "vwap_upper": safe(data.get("vwap_upper")),
                        "vwap_lower": safe(data.get("vwap_lower")),
                        "score": int(safe(v.get("prob"))),
                        "signal": v.get("signal", "TRZYMAJ"),
                        "rsi": safe(v.get("rsi")),
                        "macd": safe(v.get("macd")),
                        "hist": safe(v.get("hist")),
                        "momentum": 0.0,
                        "liquidity_signal": data.get("liquidity_signal", "N/A"),
                        "smart_money_score": safe(data.get("smart_money_score")),
                        "smart_money_regime": data.get("smart_money_regime", "N/A"),
                        "vwap_signal": data.get("vwap_signal", "N/A"),
                        "confluence_signal": data.get("confluence_signal", "NEUTRALNIE"),
                        "confidence": safe(data.get("confidence", 0)),
                    })
            self.status_label.text = f"[color=#888888]Snapshot odświeżony: {timestamp_text()}[/color]"
            self.refresh_view()
        except Exception as e:
            self.status_label.text = f"[color=#FF0000]Snapshot error: {e}[/color]"
        finally:
            self._snapshot_loading = False

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


class StockScanner(MDApp):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.engine = None
        self.tabs = None
        self.info_tab = None
        self.scanner_tab = None
        self.ticker_tab = None
        self.akcje_tab = None
        self.katalizatory_tab = None
        self.cfd_tab = None
        self.live_tab = None

    def handle_ref(self, ref):
        ref = (ref or "").strip()
        if not ref:
            return
        try:
            if ref.startswith("http://") or ref.startswith("https://"):
                webbrowser.open(ref)
            else:
                webbrowser.open(f"https://www.google.com/search?q={quote_plus(ref)}")
        except Exception:
            pass

    def request_android_permissions(self):
        if not ANDROID:
            return
        try:
            request_permissions([
                Permission.INTERNET, Permission.FOREGROUND_SERVICE,
                Permission.POST_NOTIFICATIONS, Permission.WAKE_LOCK, Permission.VIBRATE,
                Permission.RECEIVE_BOOT_COMPLETED, Permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS
            ])
        except Exception:
            pass

    def request_battery_optimization_exception(self):
        if not ANDROID:
            return
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
        except Exception:
            pass

    def start_foreground_service(self):
        if not ANDROID:
            return
        try:
            PythonActivity = autoclass("org.kivy.android.PythonActivity")
            PythonService = autoclass("org.kivy.android.PythonService")
            Intent = autoclass("android.content.Intent")
            activity = PythonActivity.mActivity
            intent = Intent(activity, PythonService)
            intent.putExtra("serviceTitle", "StockScanner V10 Pro")
            intent.putExtra("serviceDescription", "Faza Foreground Engine WebSocket V4")
            if hasattr(activity, "startForegroundService"):
                activity.startForegroundService(intent)
            else:
                activity.startService(intent)
        except Exception as e:
            print("Foreground error:", e)

    def init_firebase(self):
        if not ANDROID:
            return
        try:
            FirebaseMessaging = autoclass("com.google.firebase.messaging.FirebaseMessaging")
            FirebaseMessaging.getInstance().getToken()
        except Exception:
            pass

    def start_v4_engine(self):
        self.engine = UltraEngineV4(ws_url=f"wss://ws.finnhub.io?token={FINNHUB_KEY}")
        self.engine.subscribe(self.on_live_signal)
        run_coro(self.engine.start())

    def update_live_symbols(self, symbols):
        if self.engine:
            run_coro(self.engine.update_symbols(symbols))

    def on_live_signal(self, signal):
        if hasattr(self, "live_tab") and self.live_tab:
            Clock.schedule_once(lambda dt: self.live_tab.add_live_entry(signal))

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
        self.live_tab = LiveDataTab()

        self.tabs.add_widget(self.info_tab)
        self.tabs.add_widget(self.scanner_tab)
        self.tabs.add_widget(self.ticker_tab)
        self.tabs.add_widget(self.akcje_tab)
        self.tabs.add_widget(self.katalizatory_tab)
        self.tabs.add_widget(self.cfd_tab)
        self.tabs.add_widget(self.live_tab)

        return screen

    def on_start(self):
        start_async_loop()
        Clock.schedule_once(lambda dt: self.start_foreground_service(), 0.1)
        Clock.schedule_once(lambda dt: self.init_firebase(), 0.2)
        Clock.schedule_once(lambda dt: self.request_battery_optimization_exception(), 0.3)
        Clock.schedule_once(lambda dt: self.info_tab.load_data_if_needed(), 0.5)
        Clock.schedule_once(lambda dt: self.start_v4_engine(), 1.0)
        if self.tabs:
            self.tabs.bind(on_tab_switch=self.on_tab_switch)
        Clock.schedule_once(lambda dt: self.update_live_symbols(getattr(self.live_tab, "tickers", [])), 1.2)
        Clock.schedule_once(lambda dt: self.live_tab.refresh_snapshot(), 1.6)
        # wczytaj startowe dane także dla pozostałych zakładek
        for tab in (self.scanner_tab, self.ticker_tab, self.akcje_tab, self.katalizatory_tab, self.cfd_tab):
            try:
                Clock.schedule_once(lambda dt, t=tab: t.load_data_if_needed(), 0.6)
            except Exception:
                pass

    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if hasattr(instance_tab, "load_data_if_needed"):
            instance_tab.load_data_if_needed()

    def on_stop(self):
        global HTTP_CLIENT
        try:
            if self.engine:
                self.engine.stop()
        except Exception:
            pass
        try:
            if HTTP_CLIENT and ASYNC_LOOP and ASYNC_LOOP.is_running():
                asyncio.run_coroutine_threadsafe(HTTP_CLIENT.aclose(), ASYNC_LOOP)
        except Exception:
            pass
        HTTP_CLIENT = None


if __name__ == "__main__":
    StockScanner().run()
