# =========================================
# STOCK SCANNER PRO - V10 MAIN.PY
# Android 14 + Foreground WS + Notifications
# =========================================

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
from html import unescape

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
except:
    from datetime import timezone

    class ZoneInfo:
        def __init__(self, name):
            self.tz = timezone.utc

        def __call__(self, *args, **kwargs):
            return self.tz
# =========================================
# CONFIG
# =========================================

HEADERS = {"User-Agent": "Mozilla/5.0"}
FINNHUB_KEY = "d82t3s1r01ql4onfbbngd82t3s1r01ql4onfbbo0"

HTTP_CLIENT = None

def get_http_client():
    global HTTP_CLIENT
    if HTTP_CLIENT is None:
        HTTP_CLIENT = httpx.AsyncClient(
            headers=HEADERS,
            timeout=httpx.Timeout(10.0),
            limits=httpx.Limits(
                max_connections=20,
                max_keepalive_connections=10
            ),
            http2=False,  # 🔥 Android safer than http2
            verify=certifi.where()
        )
    return HTTP_CLIENT

REQUEST_DELAY = 0.15
MAX_RETRIES = 2

REQUEST_CACHE = {}
REQUEST_CACHE_LOCK = threading.Lock()
REQUEST_CACHE_TTL = {
    "screener": 120,
    "ticker": 90,
    "company": 180,
    "news": 120,
    "finnhub_news": 120,
    "finnhub_earnings":300,
}

LAST_REQUEST_TIME = {}
RATE_LIMIT_LOCK = threading.Lock()

ASYNC_LOOP = None
ASYNC_LOOP_READY = threading.Event()

NASDAQ_CORE = [
    "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "GOOGL", "GOOG", "PLTR",
    "NFLX", "AVGO", "ORCL", "COST", "QCOM", "MU", "INTC", "CRM", "UBER", "SHOP",
    "PANW", "ADBE", "SNOW", "ARM", "LLY", "AMAT", "SMCI", "MSTR", "BABA", "RIVN",
]
GPW_CORE = [
    "CDR.WA", "PKO.WA", "PEO.WA", "PZU.WA", "PKN.WA", "DNP.WA", "LPP.WA", "ALE.WA",
    "JSW.WA", "KGH.WA", "MBK.WA", "SPL.WA", "BHW.WA", "CCC.WA", "OPL.WA", "ALE.WA",
]

CFD_ALIAS = {
    "US500": "^GSPC",
    "NAS100": "^NDX",
    "US30": "^DJI",
    "GER40": "^GDAXI",
    "UK100": "^FTSE",
    "XAUUSD": "XAUUSD=X",
    "XAGUSD": "XAGUSD=X",
}

CFD_FRIENDLY = {
    "US500": "S&P 500",
    "NAS100": "Nasdaq 100",
    "US30": "Dow Jones 30",
    "GER40": "DAX 40",
    "UK100": "FTSE 100",
    "XAUUSD": "Gold / USD",
    "XAGUSD": "Silver / USD",
    "^GSPC": "S&P 500",
    "^NDX": "Nasdaq 100",
    "^DJI": "Dow Jones 30",
    "^GDAXI": "DAX 40",
    "^FTSE": "FTSE 100",
    "XAUUSD=X": "Gold / USD",
    "XAGUSD=X": "Silver / USD",
}

FALLBACK_NAMES = {
    "AAPL": "Apple",
    "MSFT": "Microsoft",
    "NVDA": "NVIDIA",
    "AMZN": "Amazon",
    "META": "Meta",
    "TSLA": "Tesla",
    "AMD": "AMD",
    "GOOGL": "Alphabet",
    "GOOG": "Alphabet",
    "PLTR": "Palantir",
    "NFLX": "Netflix",
    "AVGO": "Broadcom",
    "ORCL": "Oracle",
    "COST": "Costco",
    "QCOM": "Qualcomm",
    "MU": "Micron",
    "INTC": "Intel",
    "CRM": "Salesforce",
    "UBER": "Uber",
    "SHOP": "Shopify",
    "PANW": "Palo Alto Networks",
    "ADBE": "Adobe",
    "SNOW": "Snowflake",
    "ARM": "Arm",
    "LLY": "Eli Lilly",
    "AMAT": "Applied Materials",
    "SMCI": "Super Micro",
    "MSTR": "MicroStrategy",
    "BABA": "Alibaba",
    "RIVN": "Rivian",
    "CDR.WA": "CD Projekt",
    "PKO.WA": "PKO BP",
    "PEO.WA": "Pekao",
    "PZU.WA": "PZU",
    "PKN.WA": "Orlen",
    "DNP.WA": "Dino Polska",
    "LPP.WA": "LPP",
    "ALE.WA": "Allegro",
    "JSW.WA": "JSW",
    "KGH.WA": "KGHM",
    "MBK.WA": "mBank",
    "SPL.WA": "Santander Bank Polska",
    "BHW.WA": "Bank Handlowy",
    "CCC.WA": "CCC",
    "OPL.WA": "Orange Polska",
}



LOCAL_TZ = ZoneInfo("Europe/Warsaw")
NY_TZ = ZoneInfo("America/New_York")

APP_CHANNEL_ID = "stock_scanner_alerts"
SERVICE_NAME = "ScannerService"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "v10_state.json")

def init_firebase():
    try:
        FirebaseMessaging = autoclass("com.google.firebase.messaging.FirebaseMessaging")
        FirebaseMessaging.getInstance().getToken()
    except:
        pass

# =========================================
# ASYNC LOOP
# =========================================

def start_async_loop():
    global ASYNC_LOOP
    try:
        ASYNC_LOOP = asyncio.new_event_loop()
        asyncio.set_event_loop(ASYNC_LOOP)
        ASYNC_LOOP_READY.set()

        # 🔥 watchdog wrapper (Android crash protection)
        ASYNC_LOOP.run_forever()

    except Exception as e:
        print("[ASYNC LOOP CRASH]", e)
    finally:
        try:
            ASYNC_LOOP.close()
        except:
            pass

# =========================================
# HELPERS
# =========================================

def safe(v, d=0.0):
    try:
        return float(v) if v is not None else d
    except Exception:
        return d

def safe_list(data):
    return [safe(x) for x in data if x is not None]

def fmt_num(value, digits=2, signed=False):
    v = safe(value, 0.0)
    return f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"

def color_wrap(text, color):
    return f"[color={color}]{text}[/color]"

SESSION_COLORS = {
    "PREMARKET": "#FF9900",
    "OTWARTY": "#00AA00",
    "POSTMARKET": "#001A66",
    "ZAMKNIĘTY": "#777777",
}

def color_for_session(session_state):
    return SESSION_COLORS.get((session_state or "").upper(), "#777777")

def session_label(session_state):
    return f"[color={color_for_session(session_state)}]{session_state}[/color]"

def format_datetime_ts(value):
    try:
        ts = int(float(value))
        return datetime.fromtimestamp(ts, NY_TZ).astimezone(LOCAL_TZ).strftime("%d.%m.%Y %H:%M:%S %Z")
    except Exception:
        return str(value) if value not in (None, "") else "N/A"

def format_earnings_value(value):
    if value in (None, "", 0, 0.0):
        return "N/A"
    return format_datetime_ts(value)

def format_money(value, digits=2):
    return f"{safe(value):.{digits}f}"

def format_pct(value, digits=2):
    return f"{safe(value):+.{digits}f}%"

def format_cap(v):
    v = safe(v)
    if v >= 1_000_000_000_000:
        return f"{v/1_000_000_000_000:.2f} T"
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f} B"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f} M"
    return f"{v:.2f}"

def timestamp_text():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def local_time_text():
    return datetime.now(LOCAL_TZ).strftime("%d.%m.%Y %H:%M:%S %Z")

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
    try:
        now_ny = datetime.now(NY_TZ)
        base_date = now_ny.date()
        pre_end = datetime(base_date.year, base_date.month, base_date.day, 9, 30, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        reg_end = datetime(base_date.year, base_date.month, base_date.day, 16, 0, tzinfo=NY_TZ).astimezone(LOCAL_TZ)
        return (
            "[b]Rynek USA — godziny sesji (ET / czas lokalny CET/CEST)[/b]\n"
            f"• [b]Pre-Market[/b]: 04:00–09:30 ET / ...–{pre_end.strftime('%H:%M %Z')}\n"
            f"• [b]Sesja główna[/b]: 09:30–16:00 ET / {pre_end.strftime('%H:%M')}–{reg_end.strftime('%H:%M %Z')}\n"
            "• [b]Weekend[/b]: rynek zamknięty"
        )
    except Exception:
        return "[b]Rynek USA[/b]: 09:30–16:00 ET"

def normalize_company_name(symbol, name=None):
    symbol = (symbol or "").strip().upper()
    cleaned = (name or "").strip()
    fallback = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "TSLA": "Tesla", "AMD": "AMD"}
    if cleaned and cleaned.upper() != symbol:
        return cleaned
    return fallback.get(symbol.replace(".WA", "").replace(".PL", ""), cleaned or symbol)

def safe_int(value, d=0):
    try:
        return int(float(value))
    except Exception:
        return d

def _dt_to_date_text(value):
    try:
        ts = int(float(value))
        return datetime.fromtimestamp(ts, NY_TZ).astimezone(LOCAL_TZ).strftime("%d.%m.%Y")
    except Exception:
        return "N/A"

def resolve_symbol(symbol):
    raw = (symbol or "").strip().upper()
    actual = CFD_ALIAS.get(raw, raw)
    return raw, actual

def finnhub_url(endpoint, params=None):
    params = dict(params or {})
    params["token"] = FINNHUB_KEY
    query = "&".join(f"{k}={quote_plus(str(v))}" for k, v in params.items())
    return f"https://finnhub.io/api/v1/{endpoint.lstrip('/')}?{query}"

async def fetch_json_cached(url, ttl, cache_key=None, timeout=8):
    key = cache_key or url
    now = time.time()

    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(key)
        if cached and now - cached["ts"] < ttl:
            return cached["data"]

    res = await safe_request_async(url, timeout=timeout)
    data = safe_json(res)

    with REQUEST_CACHE_LOCK:
        REQUEST_CACHE[key] = {"ts": now, "data": data}

    return data

def search_url_from_query(query):
    return f"https://www.google.com/search?q={quote_plus(query)}"

def safe_json(response):
    try:
        return response.json() if getattr(response, "status_code", 0) == 200 else {}
    except Exception:
        return {}

def make_tp_sl(price, tp_pct=0.03, sl_pct=0.02):
    price = safe(price, 0.0)
    return price * (1 + tp_pct), price * (1 - sl_pct)

def build_full_glossary():
    return (
        "[b]SŁOWNIK WSKAŹNIKÓW I POJĘĆ (V10)[/b]\n"
        "• [b]SMA30 / SMA90[/b] — średnia krocząca 30/90 okresów.\n"
        "• [b]RSI[/b] — poniżej 40 to wyprzedanie, powyżej 65 to wykupienie.\n"
        "• [b]MACD & Hist[/b] — momentum; rosnący histogram zwykle wzmacnia trend.\n"
        "• [b]TP / SL[/b] — Take Profit i Stop Loss.\n"
        "• [b]Pre/Post-Market[/b] — handel poza sesją główną.\n\n"
        "[b]ZAAWANSOWANE WSKAŹNIKI V10[/b]\n"
        "• [b]Regime[/b] — UP / DOWN / RANGE.\n"
        "• [b]Timing[/b] — IDEALNY_MOMENT / NEUTRALNY / CZEKAJ.\n"
        "• [b]AI Score[/b] — 0–100 siła sygnału.\n"
        "• [b]Orderflow[/b] — imbalance i absorpcja.\n"
    )

# =========================================
# V10 ENGINE
# =========================================

def google_news_rss_url(query):
    return (
        "https://news.google.com/rss/search?q="
        + quote_plus(query)
        + "&hl=en-US&gl=US&ceid=US:en"
    )

def parse_google_news_rss(xml_text, source_label="Google News", max_items=8):
    items = []
    if not xml_text:
        return items
    try:
        root = ET.fromstring(xml_text)
    except Exception:
        return items

    for item in root.findall(".//item")[:max_items]:
        title = unescape((item.findtext("title") or "").strip())
        link = (item.findtext("link") or "").strip()
        pub_date = (item.findtext("pubDate") or "").strip()
        source = (item.findtext("source") or "").strip() or source_label
        if not title:
            continue
        items.append({
            "title": title,
            "link": link,
            "source": source,
            "published": pub_date,
        })
    return items

def dedupe_items(items):
    seen = set()
    out = []
    for item in items:
        key = (item.get("link") or item.get("title") or "").strip().lower()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out

def news_item_row(title, link, meta=""):
    href = link if link.startswith("http") else search_url_from_query(title)
    meta_text = f" [color=#888888]{meta}[/color]" if meta else ""
    return f"[ref={href}][u]{title}[/u][/ref]{meta_text}"

async def fetch_rss_news(query, max_items=5, timeout=10):
    url = google_news_rss_url(query)
    res = await safe_request_async(url, timeout=timeout)
    if getattr(res, "status_code", 0) != 200:
        return []
    return parse_google_news_rss(getattr(res, "text", ""), max_items=max_items)

async def fetch_finnhub_earnings_calendar(days_ahead=7):
    start = datetime.now(NY_TZ).date()
    end = start + timedelta(days=days_ahead)
    url = (
        "https://finnhub.io/api/v1/calendar/earnings"
        f"?from={start.isoformat()}&to={end.isoformat()}&token={FINNHUB_KEY}"
    )
    res = await safe_request_async(url, timeout=10)
    if getattr(res, "status_code", 0) != 200:
        return []
    data = safe_json(res)
    items = []
    for row in data.get("earningsCalendar", []) or []:
        sym = (row.get("symbol") or "").strip().upper()
        if not sym:
            continue
        dt_text = row.get("date") or ""
        hour = row.get("hour") or ""
        eps_est = row.get("epsEstimate")
        row_title = f"{sym} — earnings {dt_text}{(' ' + hour) if hour else ''}"
        meta = []
        if eps_est not in (None, ""):
            meta.append(f"EPS est. {eps_est}")
        if row.get("revenueEstimate") not in (None, ""):
            meta.append(f"Rev est. {row.get('revenueEstimate')}")
        link = search_url_from_query(f"{sym} earnings {dt_text}")
        items.append({
            "title": row_title,
            "link": link,
            "source": "Finnhub earnings calendar",
            "published": dt_text,
            "meta": " • ".join(meta),
        })
    return items

async def fetch_market_news_items():
    queries = [
        "stock market earnings merger acquisition FDA PDUFA",
        "FDA PDUFA biotech stock",
        "earnings next week stock market",
        "merger acquisition takeover stock market",
        "strategic transformation company stock",
    ]
    tasks = [fetch_rss_news(q, max_items=5) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    items = []
    for q, res in zip(queries, results):
        if isinstance(res, Exception):
            continue
        for item in res:
            item["meta"] = q
            items.append(item)
    return dedupe_items(items)

async def fetch_catalyst_news_bundle():
    market_items = await fetch_market_news_items()
    earnings_items = await fetch_finnhub_earnings_calendar(days_ahead=7)
    return market_items, earnings_items

class TickNormalizer:
    def __init__(self):
        self.last_price = None
        self.last_ts = 0

    def normalize(self, tick):
        price = safe(tick.get("price"))
        ts = int(tick.get("timestamp", 0))
        if price <= 0:
            return None
        if price == self.last_price and ts == self.last_ts:
            return None
        if self.last_price:
            move = abs(price - self.last_price) / self.last_price
            if move > 0.03:
                return None
        bid = safe(tick.get("bid", price))
        ask = safe(tick.get("ask", price))
        if ask < bid:
            ask = bid
        normalized = {
            "price": round((bid + ask) / 2, 4),
            "volume": safe(tick.get("volume", 0.0)),
            "spread": round(ask - bid, 5),
            "timestamp": ts,
            "symbol": (tick.get("symbol") or "").upper(),
        }
        self.last_price = normalized["price"]
        self.last_ts = ts
        return normalized

class SmartOrderFlow:
    def __init__(self):
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.last_price = None
        self.delta_history = []
        self.volume_history = []

    def update(self, tick):
        price = tick["price"]
        volume = tick["volume"]
        if self.last_price is None:
            self.last_price = price
            return None

        if price > self.last_price:
            self.buy_volume += volume
            side = "BUY"
        elif price < self.last_price:
            self.sell_volume += volume
            side = "SELL"
        else:
            side = "NEUTRAL"

        delta = self.buy_volume - self.sell_volume
        self.delta_history.append(delta)
        self.volume_history.append(volume)
        self.delta_history = self.delta_history[-200:]
        self.volume_history = self.volume_history[-200:]
        self.last_price = price

        return {
            "side": side,
            "delta": delta,
            "buy_pressure": self.buy_volume,
            "sell_pressure": self.sell_volume,
            "imbalance": self.get_imbalance(),
            "absorption": self.detect_absorption(),
            "exhaustion": self.detect_exhaustion(),
        }

    def get_imbalance(self):
        total = self.buy_volume + self.sell_volume
        if total <= 0:
            return 0.0
        return round((self.buy_volume - self.sell_volume) / total, 4)

    def detect_absorption(self):
        if len(self.delta_history) < 20:
            return False
        recent = self.delta_history[-20:]
        return (max(recent) - min(recent)) > 5000

    def detect_exhaustion(self):
        if len(self.volume_history) < 10:
            return False
        recent = self.volume_history[-10:]
        avg = sum(recent) / len(recent)
        return recent[-1] < avg * 0.35

class AdaptiveAI:
    def __init__(self):
        self.prices = []
        self.volumes = []
        self.base_threshold = 65

    def update(self, tick, flow):
        self.prices.append(tick["price"])
        self.volumes.append(tick["volume"])
        self.prices = self.prices[-500:]
        self.volumes = self.volumes[-500:]

        score = self.calculate_score(tick, flow)
        threshold = self.dynamic_threshold()

        if score >= threshold:
            signal = "LONG"
        elif score <= (100 - threshold):
            signal = "SHORT"
        else:
            signal = None

        return {"score": score, "threshold": threshold, "signal": signal}

    def calculate_score(self, tick, flow):
        score = 50.0
        score += flow["imbalance"] * 40
        if flow["exhaustion"]:
            score -= 10
        if flow["absorption"]:
            score += 8
        if tick["spread"] > 0.05:
            score -= 15

        if len(self.prices) > 10:
            tail = self.prices[-10:]
            if tail[0] > 0:
                momentum = (tail[-1] - tail[0]) / tail[0]
                score += momentum * 100

        return max(0, min(100, round(score, 2)))

    def dynamic_threshold(self):
        if len(self.prices) < 50:
            return self.base_threshold
        diffs = [self.prices[i] - self.prices[i - 1] for i in range(1, len(self.prices))]
        if not diffs:
            return self.base_threshold
        mean = sum(diffs) / len(diffs)
        var = sum((x - mean) ** 2 for x in diffs) / len(diffs)
        volatility = var ** 0.5
        avg_volume = sum(self.volumes) / len(self.volumes) if self.volumes else 0.0
        threshold = self.base_threshold
        if volatility > 0.5:
            threshold += 8
        if avg_volume < 100:
            threshold += 5
        trend = self.prices[-1] - (sum(self.prices) / len(self.prices))
        if abs(trend) > 2:
            threshold -= 5
        return max(55, min(85, round(threshold)))

class LiveV10Engine:
    def __init__(self):
        self.normalizer = TickNormalizer()
        self.orderflow = SmartOrderFlow()
        self.ai = AdaptiveAI()
        self.last_signal = {}

    def process_raw_tick(self, raw_tick):
        tick = self.normalizer.normalize(raw_tick)
        if not tick:
            return None

        flow = self.orderflow.update(tick)
        if not flow:
            return None

        ai = self.ai.update(tick, flow)
        if ai["signal"]:
            return {
                "symbol": tick["symbol"],
                "price": tick["price"],
                "score": ai["score"],
                "threshold": ai["threshold"],
                "signal": ai["signal"],
                "flow": flow,
                "tick": tick,
            }
        return None

_last_ui_ping = time.time()

def ui_watchdog(dt):
    global _last_ui_ping
    if time.time() - _last_ui_ping > 10:
        print("[WARNING] UI stalled")

Clock.schedule_interval(ui_watchdog, 5)

# =========================================
# STATE
# =========================================

def read_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def write_state(data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

# =========================================
# HTTP / DATA FETCH
# =========================================

async def safe_request_async(url, timeout=8, retries=MAX_RETRIES):
    host = url.split("/")[2] if "://" in url else "default"
    client = get_http_client()

    for i in range(retries):
        try:
            async with RATE_LIMIT_LOCK:
                now = time.time()
                diff = now - LAST_REQUEST_TIME.get(host, 0)

                if diff < REQUEST_DELAY:
                    await asyncio.sleep(REQUEST_DELAY - diff)

                LAST_REQUEST_TIME[host] = time.time()

            response = await client.get(url, timeout=timeout)

            if response.status_code in (200, 404):
                return response

            if response.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(min(2 ** i, 8))
                continue

            return response

        except Exception:
            await asyncio.sleep(min(2 ** i, 8))
            continue

    return None
    
def _extract_chart_payload(yahoo_json):
    result = yahoo_json.get("chart", {}).get("result", [])
    if not result:
        return {}, {}
    return result[0], result[0].get("indicators", {}).get("quote", [{}])[0]

def _extract_intraday_session_prices(chart_payload, chart_quote):
    try:
        ts_list = chart_payload.get("timestamp", []) or []
        closes = chart_quote.get("close", []) or []
        n = min(len(ts_list), len(closes))
        if n <= 0:
            return 0.0, 0.0, 0.0

        tz_ny = ZoneInfo("America/New_York")
        pre_last = regular_last = post_last = 0.0

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

def _select_active_price(session_state, prev_close, pre_price, regular_price, post_price, last_trade, quote_price=0.0):
    pc = safe(prev_close)
    pre = safe(pre_price)
    reg = safe(regular_price)
    post = safe(post_price)
    last = safe(last_trade)
    quote = safe(quote_price)

    if session_state == "PREMARKET":
        return pre or quote or last or reg or pc
    if session_state == "POSTMARKET":
        return post or quote or last or reg or pc
    if session_state == "OTWARTY":
        return quote or last or reg or pc
    return quote or last or reg or pre or post or pc

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

def normalize_volumes(volumes):
    vols = safe_list(volumes)
    if not vols:
        return []
    avg = sum(vols) / len(vols)
    return [avg * 3 if v > avg * 10 else v for v in vols]

def build_v10_stats(closes, volumes, current_price, prev_close, regular_close=None):
    closes = safe_list(closes)
    volumes = normalize_volumes(volumes)
    cp = safe(current_price, 0.0)

    pc = safe(prev_close, 0.0)
    if pc <= 0 and len(closes) >= 2:
        pc = safe(closes[-2], 0.0)
    if pc <= 0 and len(closes) >= 1:
        pc = safe(closes[-1], 0.0)

    reg_close = safe(regular_close, 0.0)
    if reg_close <= 0:
        reg_close = cp if cp > 0 else pc

    rsi_val = calc_rsi(closes)
    macd_val, signal_val, hist = macd(closes)

    diff = cp - pc
    pct = (diff / pc * 100) if pc > 0 else 0.0

    scanner_diff = reg_close - pc
    scanner_pct = (scanner_diff / pc * 100) if pc > 0 else 0.0

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
        "price": cp,
        "prev_close": pc,
        "regular_close": reg_close,
        "diff": diff,
        "pct": pct,
        "scanner_diff": scanner_diff,
        "scanner_pct": scanner_pct,
        "rsi": rsi_val,
        "macd": macd_val,
        "sig": signal_val,
        "hist": hist,
        "sma14": sma(closes, 14),
        "sma30": sma(closes, 30),
        "sma90": sma(closes, 90),
        "regime": regime,
        "timing": timing,
        "prob": max(0, min(100, prob)),
        "confidence": max(0, min(100, prob)),
        "signal": raw_sig,
        "signal_color": sig_color,
    }

async def fetch_ticker(symbol):
    raw_symbol = (symbol or "").strip().upper()

    if not raw_symbol:
        return None

    actual_symbol = raw_symbol
    friendly = raw_symbol

    yahoo_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{actual_symbol}?interval=1d&range=1y"
    intraday_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{actual_symbol}?interval=1m&range=1d&includePrePost=true"
    quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={actual_symbol}"

    y_res, i_res, q_res = await asyncio.gather(
        safe_request_async(yahoo_url, timeout=8),
        safe_request_async(intraday_url, timeout=8),
        safe_request_async(quote_url, timeout=6),
    )

    closes, volumes, chart_meta = [], [], {}

    if getattr(y_res, "status_code", 0) == 200:
        payload, quote = _extract_chart_payload(safe_json(y_res))
        chart_meta = payload.get("meta", {})
        closes = [x for x in quote.get("close", []) if x is not None]
        volumes = [x for x in quote.get("volume", []) if x is not None]

    fh_q = safe_json(q_res).get("quoteResponse", {}).get("result", [])
    fh_q = fh_q[0] if fh_q else {}

    session_state = market_status()
    pre_p = post_p = reg_p = last_trade = 0.0
    quote_price = safe(fh_q.get("regularMarketPrice", 0.0))
    quote_prev_close = safe(fh_q.get("regularMarketPreviousClose", 0.0))

    if getattr(i_res, "status_code", 0) == 200:
        i_payload, i_quote = _extract_chart_payload(safe_json(i_res))
        i_meta = i_payload.get("meta", {})
        raw_state = str(i_meta.get("marketState", "") or "").upper().strip()

        if raw_state == "PRE":
            session_state = "PREMARKET"
        elif raw_state == "POST":
            session_state = "POSTMARKET"
        elif raw_state == "REGULAR":
            session_state = "OTWARTY"

        pre_scan, regular_scan, post_scan = _extract_intraday_session_prices(i_payload, i_quote)
        pre_p = pre_scan or safe(i_meta.get("preMarketPrice")) or safe(fh_q.get("preMarketPrice"))
        post_p = post_scan or safe(i_meta.get("postMarketPrice")) or safe(fh_q.get("postMarketPrice"))
        reg_p = regular_scan or safe(i_meta.get("regularMarketPrice")) or quote_price

        if i_quote.get("close"):
            last_trade = safe(i_quote.get("close", [])[-1])

    chart_prev_close = safe(chart_meta.get("previousClose")) or safe(chart_meta.get("chartPreviousClose"))
    prev_c = quote_prev_close or chart_prev_close or (closes[-2] if len(closes) >= 2 else 0.0)

    current_price = _select_active_price(session_state, prev_c, pre_p, reg_p, post_p, last_trade, quote_price)
    if current_price <= 0:
        current_price = quote_price or prev_c

    regular_close = reg_p or quote_prev_close or chart_prev_close or (closes[-1] if closes else 0.0)
    if regular_close <= 0:
        regular_close = prev_c

    v10_stats = build_v10_stats(closes, volumes, current_price, prev_c, regular_close=regular_close)

    day_high = safe(fh_q.get("regularMarketDayHigh", 0.0))
    day_low = safe(fh_q.get("regularMarketDayLow", 0.0))
    high52 = safe(fh_q.get("fiftyTwoWeekHigh", 0.0))
    low52 = safe(fh_q.get("fiftyTwoWeekLow", 0.0))
    market_cap = safe(fh_q.get("marketCap", 0.0))
    pe = fh_q.get("trailingPE", "N/A")
    eps = fh_q.get("epsTrailingTwelveMonths", "N/A")
    next_earnings = fh_q.get("earningsTimestamp", "N/A")
    analyst_rating = fh_q.get("recommendationKey", "Brak")

    name = normalize_company_name(
        raw_symbol,
        fh_q.get("shortName") or fh_q.get("longName"),
        display_name=CFD_FRIENDLY.get(raw_symbol),
    )

    return {
        "symbol": actual_symbol,
        "display_symbol": raw_symbol,
        "name": name,
        "session_state": session_state,
        "pre_price": safe(pre_p),
        "post_price": safe(post_p),
        "regular_price": safe(regular_close),
        "current_price": safe(current_price),
        "prev_close": safe(prev_c),
        "day_low": day_low,
        "day_high": day_high,
        "low52": low52,
        "high52": high52,
        "market_cap": market_cap,
        "pe": pe,
        "eps": eps,
        "next_earnings": next_earnings,
        "analyst_rating": analyst_rating,
        "v10": v10_stats,
    }

async def fetch_bulk(symbols, chunk_size=4):
    out = {}
    symbols = [s.strip().upper() for s in symbols if s and s.strip()]
    for i in range(0, len(symbols), chunk_size):
        chunk = symbols[i:i + chunk_size]
        results = await asyncio.gather(*(fetch_ticker(sym) for sym in chunk), return_exceptions=True)
        for sym, res in zip(chunk, results):
            if isinstance(res, Exception) or not res:
                continue
            out[sym] = res
    return out

async def fetch_top_gainers_by_type_async(kind="day_gainers"):
    url = f"https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved?count=20&scrIds={kind}"
    try:
        res = await safe_request_async(url, timeout=8)
        data = safe_json(res)
        result = data.get("finance", {}).get("result", [])
        if not result:
            return []
        quotes = result[0].get("quotes", [])
        return [q.get("symbol") for q in quotes if q.get("symbol")]
    except Exception:
        return []

async def fetch_market_news_general(hours_back=48, limit=40):
    data = await fetch_json_cached(
        finnhub_url("news", {"category": "general"}),
        REQUEST_CACHE_TTL["finnhub_news"],
        cache_key="finnhub_news:general",
        timeout=8,
    )
    cutoff = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    items = []
    for item in data or []:
        ts = safe_int(item.get("datetime"), 0)
        dt = datetime.fromtimestamp(ts, tz=timezone.utc) if ts else None
        if not dt or dt < cutoff:
            continue
        items.append(item)
    items.sort(key=lambda x: safe_int(x.get("datetime"), 0), reverse=True)
    return items[:limit]

async def fetch_company_news_window(symbols, days_back=2, limit_per_symbol=8):
    from_date = (datetime.now(NY_TZ) - timedelta(days=days_back)).date().isoformat()
    to_date = datetime.now(NY_TZ).date().isoformat()
    rows = []
    for sym in symbols:
        actual = resolve_symbol(sym)[1]
        if not actual or actual.startswith("^"):
            continue
        url = finnhub_url("company-news", {"symbol": actual, "from": from_date, "to": to_date})
        data = await fetch_json_cached(
            url,
            REQUEST_CACHE_TTL["finnhub_news"],
            cache_key=f"finnhub_company_news:{actual}:{from_date}:{to_date}",
            timeout=8,
        )
        if not isinstance(data, list):
            continue
        for item in data[:limit_per_symbol]:
            rows.append((actual, item))
    return rows

async def fetch_earnings_window(days_forward=7):
    from_date = datetime.now(NY_TZ).date().isoformat()
    to_date = (datetime.now(NY_TZ).date() + timedelta(days=days_forward)).isoformat()
    data = await fetch_json_cached(
        finnhub_url("calendar/earnings", {"from": from_date, "to": to_date}),
        REQUEST_CACHE_TTL["finnhub_earnings"],
        cache_key=f"finnhub_earnings:{from_date}:{to_date}",
        timeout=8,
    )
    if isinstance(data, dict):
        for key in ("earningsCalendar", "earnings", "data"):
            if isinstance(data.get(key), list):
                return data[key]
    if isinstance(data, list):
        return data
    return []

def run_coro(coro):
    global ASYNC_LOOP

    if not ASYNC_LOOP_READY.wait(timeout=5):
        return None

    if ASYNC_LOOP is None:
        return None

    try:
        future = asyncio.run_coroutine_threadsafe(coro, ASYNC_LOOP)
        return future.result(timeout=10)

    except Exception as e:
        print("[run_coro error]", e)
        return None

# =========================================
# UI
# =========================================

class DataCard(MDCard):
    text = StringProperty("")

    def _update_height(self, texture_h=0):
        try:
            self.height = max(dp(120), float(texture_h) + dp(28))
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
    height: _body.texture_size[1] + dp(28) if _body.texture_size[1] > 0 else dp(120)

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
        on_ref_press: app.handle_ref(ref)

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


class BaseTab(MDBoxLayout, MDTabsBase):
    def __init__(self, **kwargs):
        super().__init__(orientation="vertical", **kwargs)
        self.is_loaded = False
        self._loading = False
        self._request_serial = 0
        self.full_rows = []
        self.visible_count = 0
        self.batch_size = 12
        self.max_visible = 60
        self._scroll_trigger_ts = 0.0

        self.control_panel = MDBoxLayout(
            orientation="vertical",
            size_hint_y=None,
            height=dp(0),
            padding=[dp(8)],
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
        self.more_button.height = dp(36) if has_more else 0
        self.more_button.opacity = 1 if has_more else 0
        self.more_button.disabled = not has_more

    def _apply_visible_rows(self, scroll_top=False):
        self.rv.data = [{"text": r} for r in self.full_rows[:self.visible_count]]
        self._update_more_button()
        if scroll_top:
            Clock.schedule_once(lambda dt: setattr(self.rv, "scroll_y", 1), 0.15)

    def _set_rows_now(self, rows, scroll_top=False):
        self.full_rows = list(rows or [])
        self.visible_count = min(self.batch_size, len(self.full_rows))
        self._apply_visible_rows(scroll_top=scroll_top)

    def set_rows(self, rows, scroll_top=False):
        Clock.schedule_once(lambda dt: self._set_rows_now(rows, scroll_top=scroll_top), 0)

    def load_more(self, *args):
        def _apply(dt):
            if self.visible_count < len(self.full_rows):
                self.visible_count = min(len(self.full_rows), self.visible_count + self.batch_size, self.max_visible)
                self._apply_visible_rows(scroll_top=False)
        Clock.schedule_once(_apply, 0)

    def _on_scroll_y(self, instance, value):
        if not self._loading and self.visible_count < len(self.full_rows) and value < 0.08:
            if time.time() - self._scroll_trigger_ts > 0.4:
                self._scroll_trigger_ts = time.time()
                self.load_more()

    def load_data_if_needed(self):
        if not self.is_loaded:
            self.is_loaded = True
            self.refresh_data()

    def refresh_data(self, *args, **kwargs):
        if self._loading:
            return
        self._loading = True
        self._request_serial += 1
        serial = self._request_serial
        self._set_rows_now(["[b]Ładowanie danych...[/b]"], scroll_top=True)
        task = run_coro(self._safe_fetch(serial, *args, **kwargs))
        if task is None:
            self._loading = False

    async def _safe_fetch(self, serial, *args, **kwargs):
        try:
            rows = await self._fetch(*args, **kwargs)
            if serial == self._request_serial:
                self.set_rows(rows, scroll_top=True)
        except Exception as exc:
            if serial == self._request_serial:
                self.set_rows([f"[color=#FF0000][b]Błąd:[/b] {exc}[/color]"], scroll_top=True)
        finally:
            if serial == self._request_serial:
                self._loading = False

    async def _fetch(self, *args, **kwargs):
        return []

class InfoTab(BaseTab):
    title = "Info"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(76)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(
            MDRaisedButton(
                text="Sprawdź Status",
                on_release=lambda x: self.refresh_data(),
                pos_hint={"center_x": 0.5},
            )
        )
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        return [
            f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]\n\n"
            f"[b]RYNEK USA[/b]\nStatus: [color=#00AA00]{market_status()}[/color]\n"
            f"Czas lokalny: {local_time_text()}\nNastępne otwarcie: {next_us_market_open_text()}",
            us_market_hours_text_local(),
            build_full_glossary(),
        ]



class ScannerTab(BaseTab):
    title = "Skaner"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(156)
        self.control_panel.clear_widgets()
        self.static_tickers = ["AAPL", "MSFT", "NVDA", "TSLA", "AMD"]

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.input_field = MDTextField(hint_text="Dodaj ticker", mode="rectangle")
        input_row.add_widget(self.input_field)
        input_row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        input_row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(input_row)

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
        all_tickers = (await fetch_top_gainers_by_type_async("day_gainers"))[:20]
    else:
        all_tickers = list(dict.fromkeys(self.static_tickers + NASDAQ_CORE[:8]))

    if not all_tickers:
        return ["[color=#FF0000]Brak wyników.[/color]"]

    bulk_data = await fetch_bulk(all_tickers, chunk_size=4)
    rows = [f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]"]

    pre_gainers, post_gainers, open_gainers = [], [], []

    for sym, d in bulk_data.items():
        v = d["v10"]

        if v["scanner_pct"] > 0:
            if d["session_state"] == "PREMARKET":
                pre_gainers.append((v["scanner_pct"], sym))
            elif d["session_state"] == "POSTMARKET":
                post_gainers.append((v["scanner_pct"], sym))
            else:
                open_gainers.append((v["scanner_pct"], sym))

            color_pct = "#00AA00" if v["scanner_pct"] >= 0 else "#FF0000"

            rows.append(
                f"[b]{sym}[/b] — [color=#555555]{d['name']}[/color] | Sesja: [b]{d['session_state']}[/b]\n"
                f"Cena regular (close): [b]{d['regular_price']:.2f} USD[/b]\n"
                f"Zmiana (vs prev close): [color={color_pct}]{v['scanner_diff']:+.2f} USD | {v['scanner_pct']:+.2f}%[/color]\n"
                f"Pre: {d['pre_price']:.2f} | Post: {d['post_price']:.2f} | Kapitalizacja: {format_cap(d['market_cap'])}\n"
                f"SMA30: {d['v10']['sma30']} | SMA90: {d['v10']['sma90']}\n"
                f"RSI: [color={color_for_rsi(d['v10']['rsi'])}]{d['v10']['rsi']:.1f}[/color] | "
                f"MACD: [color={color_for_macd(d['v10']['macd'], d['v10']['sig'])}]{d['v10']['macd']:.3f}[/color] | "
                f"Hist: {format_histogram(d['v10']['hist'])}\n"
                f"Sygnał V10: [b][color={d['v10']['signal_color']}]{d['v10']['signal']}[/color][/b] "
                f"(AI Score: {d['v10']['prob']}%)"
            )

    leaders_text = "[b][color=#FF9900]🔥 LIDERZY WZROSTÓW WG. SESJI[/color][/b]\n"
    if pre_gainers:
        pre_gainers.sort(reverse=True)
        leaders_text += "PRE-MARKET: " + ", ".join([f"{s} (+{p:.1f}%)" for p, s in pre_gainers[:3]]) + "\n"
    if open_gainers:
        open_gainers.sort(reverse=True)
        leaders_text += "OTWARTA: " + ", ".join([f"{s} (+{p:.1f}%)" for p, s in open_gainers[:3]]) + "\n"
    if post_gainers:
        post_gainers.sort(reverse=True)
        leaders_text += "POST-MARKET: " + ", ".join([f"{s} (+{p:.1f}%)" for p, s in post_gainers[:3]]) + "\n"

    if pre_gainers or open_gainers or post_gainers:
        rows.insert(1, leaders_text)

    return rows


class TickerTab(BaseTab):
    title = "Ticker"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(88)
        self.control_panel.clear_widgets()
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.inp = MDTextField(hint_text="Ticker (np. TSLA)", mode="rectangle")
        row.add_widget(self.inp)
        row.add_widget(MDRaisedButton(text="Analizuj", on_release=lambda x: self.refresh_data(sym=self.inp.text)))
        self.control_panel.add_widget(row)
        self.control_panel.add_widget(self.more_button)

async def _fetch(self, *args, **kwargs):
    sym = (kwargs.get("sym") or "AAPL").strip().upper()
    if not sym:
        return ["[color=#888888]Wpisz ticker.[/color]"]

    d = await fetch_ticker(sym)
    if not d:
        return [f"[color=#FF0000]Brak danych dla: {sym}[/color]"]

    v = d["v10"]
    c_pct = "#00AA00" if v["pct"] >= 0 else "#FF0000"
    next_earnings = format_earnings_value(d["next_earnings"])

    return [(
        f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]\n\n"
        f"[b]{d['name']} ({sym})[/b] | Sesja: {d['session_state']}\n"
        f"-------------------------------------------------\n"
        f"[b]DANE RYNKOWE & FUNDAMENTALNE[/b]\n"
        f"Cena: [b]{v['price']:.2f} USD[/b] "
        f"([color={c_pct}]{v['diff']:+.2f} USD | {v['pct']:+.2f}%[/color])\n"
        f"Cena regular (close): [b]{d['regular_price']:.2f}[/b]\n"
        f"Pre-Market: {d['pre_price']:.2f} | Post-Market: {d['post_price']:.2f}\n"
        f"Zakres Dnia: {d['day_low']:.2f}-{d['day_high']:.2f} | 52W: {d['low52']:.2f}-{d['high52']:.2f}\n"
        f"Kapitalizacja: [b]{format_cap(d['market_cap'])}[/b] | P/E: [b]{d['pe']}[/b] | EPS: [b]{d['eps']}[/b]\n"
        f"Następne Wyniki: [b]{next_earnings}[/b]\n"
        f"Rekomendacja: [b]{d['analyst_rating']}[/b]\n\n"
        f"[b]V10 ANALIZA TECHNICZNA[/b]\n"
        f"RSI: [color={color_for_rsi(v['rsi'])}]{v['rsi']:.1f}[/color]\n"
        f"MACD: [color={color_for_macd(v['macd'], v['sig'])}]{v['macd']:.3f}[/color]\n"
        f"Sygnał: [b][color={v['signal_color']}]{v['signal']}[/color][/b] | AI Score: {v['prob']}%\n"
        f"Regime: [b]{v['regime']}[/b] | Timing: [b]{v['timing']}[/b]"
    )]    

def _news_headline_text(title, url):
    safe_title = html.escape(title or "").strip()
    safe_url = url or ""

    if safe_url:
        return f"[ref={safe_url}][u][b]{safe_title}[/b][/u][/ref]"

    return f"[b]{safe_title}[/b]"


def _news_line(source, title, url, dt_text, extra=""):
    extra_text = f" | {extra}" if extra else ""

    return (
        f"{dt_text}{extra_text}\n"
        f"{_news_headline_text(title, url)}\n"
        f"[color=#666666]{source}[/color]"
    )


def _news_window_sort_key(item):
    return safe_int(item.get("datetime"), 0)

class KatalizatoryTab(BaseTab):
    title = "Katalizatory"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(72)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(MDRaisedButton(text="Odśwież", on_release=lambda x: self.refresh_data()))
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        market_items, earnings_items = await fetch_catalyst_news_bundle()
        rows = [f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]"]

        recent_cutoff = datetime.now(timezone.utc) - timedelta(days=2)
        future_end = datetime.now(timezone.utc) + timedelta(days=7)

        general_news = await fetch_market_news_general(hours_back=48, limit=40)
        catalyst_items = []

        keywords = ("FDA", "PDUFA", "merger", "acquisition", "acquire", "earnings", "guidance", "spinoff", "transformation", "deal")
        for item in general_news:
            title = (item.get("headline") or item.get("summary") or "").strip()
            if not title:
                continue
            lower = title.lower()
            if any(k.lower() in lower for k in keywords):
                catalyst_items.append(("Market", item))


        company_news = await fetch_company_news_window(NASDAQ_CORE[:8], days_back=2, limit_per_symbol=6)
        for sym, item in company_news:
            catalyst_items.append((sym, item))

        catalyst_items = sorted(
            catalyst_items,
            key=lambda x: _news_window_sort_key(x[1]),
            reverse=True,
        )

        if catalyst_items:
            rows.append("[b][color=#FF9900]NEWSY / KATALIZATORY — OSTATNIE 2 DNI[/color][/b]")
            seen = set()
            for source_tag, item in catalyst_items[:30]:
                ts = safe_int(item.get("datetime"), 0)
                if ts and datetime.fromtimestamp(ts, tz=timezone.utc) < recent_cutoff:
                    continue
                title = (item.get("headline") or item.get("summary") or "").strip()
                url = item.get("url") or search_url_from_query(title)
                key = (title, url)
                if key in seen:
                    continue
                seen.add(key)
                dt_text = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(LOCAL_TZ).strftime("%d.%m %H:%M")
                source = item.get("source") or source_tag
                rows.append(_news_line(source, title, url, dt_text))
        else:
            rows.append("[color=#666666]Brak świeżych newsów w wybranym oknie.[/color]")

        earnings = await fetch_earnings_window(days_forward=7)
        future_rows = []
        for item in earnings:
            sym = (item.get("symbol") or item.get("ticker") or "").strip().upper()
            dte = item.get("date") or item.get("datetime") or item.get("earningsDate")
            if not sym or not dte:
                continue
            try:
                if isinstance(dte, (int, float)):
                    dt = datetime.fromtimestamp(int(dte), tz=timezone.utc).astimezone(NY_TZ).date()
                else:
                    dt = datetime.fromisoformat(str(dte)[:10])
            except Exception:
                continue
            if not (datetime.now(NY_TZ).date() <= dt <= (datetime.now(NY_TZ).date() + timedelta(days=7))):
                continue
            name = normalize_company_name(sym, item.get("companyName") or sym)
            url = search_url_from_query(f"{sym} earnings {dt.isoformat()}")
            future_rows.append(
                f"{dt.strftime('%d.%m.%Y')} — [b]{name} ({sym})[/b]\n"
                f"[ref={url}][u][b]Wyniki finansowe / earnings calendar[/b][/u][/ref]"
            )

        if future_rows:
            rows.append("\n[b][color=#00AA00]NASTĘPNE 7 DNI — KATALIZATORY[/color][/b]")
            rows.extend(future_rows[:25])

        return rows


class AkcjeTab(BaseTab):
    title = "Akcje"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(72)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(MDRaisedButton(text="Odśwież", on_release=lambda x: self.refresh_data()))
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        rows = [f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]"]
        for sym in NASDAQ_CORE[:10]:
            d = await fetch_ticker(sym)
            if not d:
                continue
            v = d["v10"]
            rows.append(
                f"[b]{d['name']} ({sym})[/b] | Sesja: {session_label(d['session_state'])}\n"
                f"Aktualna: [b]{v['price']:.2f} USD[/b] | Regular close: [b]{d['regular_price']:.2f} USD[/b]\n"
                f"Pre: {d['pre_price']:.2f} | Post: {d['post_price']:.2f}\n"
                f"Kapitalizacja: [b]{format_cap(d['market_cap'])}[/b] | P/E: [b]{d['pe']}[/b] | EPS: [b]{d['eps']}[/b]\n"
                f"Zakres dnia: {d['day_low']:.2f}-{d['day_high']:.2f} | 52W: {d['low52']:.2f}-{d['high52']:.2f}\n"
                f"Następne wyniki: [b]{format_earnings_value(d['next_earnings'])}[/b] | Rekomendacja: [b]{d['analyst_rating']}[/b]\n"
                f"Sygnał: [b][color={v['signal_color']}]{v['signal']}[/color][/b] | AI: {v['prob']}%"
            )
        return rows


class CFDTab(BaseTab):
    title = "CFD"

    def __init__(self, **kw):
        super().__init__(**kw)
        self.control_panel.height = dp(124)
        self.control_panel.clear_widgets()
        self.cfd_tickers = ["US500", "NAS100", "EURUSD=X", "GBPUSD=X", "USDPLN=X", "XAUUSD"]
        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.cfd_input = MDTextField(hint_text="Dodaj CFD / ticker", mode="rectangle")
        row.add_widget(self.cfd_input)
        row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(row)

        btn_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(40), spacing=dp(12))
        btn_row.add_widget(MDRaisedButton(text="Odśwież", on_release=lambda x: self.refresh_data()))
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
    rows = [f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]"]
    for sym in self.cfd_tickers:
        d = await fetch_ticker(sym)
        if not d:
            continue
        v = d["v10"]
        display_name = d["name"]
        display_symbol = d.get("display_symbol", sym)

        tp, sl = make_tp_sl(v["price"])
        tp_text = f"{tp:.2f}" if tp else "N/A"
        sl_text = f"{sl:.2f}" if sl else "N/A"

        rows.append(
            f"[b]{display_name} ({display_symbol})[/b]\n"
            f"Cena: [b]{v['price']:.4f}[/b] | Regular: {d['regular_price']:.4f}\n"
            f"RSI: [color={color_for_rsi(v['rsi'])}]{v['rsi']:.1f}[/color] | "
            f"MACD: [color={color_for_macd(v['macd'], v['sig'])}]{v['macd']:.3f}[/color] | "
            f"Hist: {format_histogram(v['hist'])}\n"
            f"TP/SL: [color=#00AA00]{tp_text}[/color] / [color=#FF3333]{sl_text}[/color]\n"
            f"Sygnał: [b][color={v['signal_color']}]{v['signal']}[/color][/b] | AI: {v['prob']}%"
        )
    return rows    
    
# =========================================
# APP MAIN
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

    def request_android_permissions(self):
        if not ANDROID:
            return
        try:
            request_permissions([
                Permission.INTERNET,
                Permission.FOREGROUND_SERVICE,
                Permission.POST_NOTIFICATIONS,
                Permission.WAKE_LOCK,
                Permission.VIBRATE,
                Permission.RECEIVE_BOOT_COMPLETED,
                Permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
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
            service_intent = Intent(activity, PythonService)
            service_intent.putExtra("serviceTitle", "Stock Scanner V10")
            service_intent.putExtra("serviceDescription", "Foreground WebSocket Engine")
            if hasattr(activity, "startForegroundService"):
                activity.startForegroundService(service_intent)
            else:
                activity.startService(service_intent)
        except Exception as e:
            print("Service start failed:", e)

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
        ASYNC_LOOP_READY.wait(timeout=5)
        self.start_foreground_service()
        init_firebase()
        self.request_battery_optimization_exception()
        Clock.schedule_once(lambda dt: self.info_tab.load_data_if_needed(), 0.2)

def on_stop(self):
    global HTTP_CLIENT

    try:
        client = HTTP_CLIENT
        HTTP_CLIENT = None

        if client:
            asyncio.run_coroutine_threadsafe(
                client.aclose(),
                ASYNC_LOOP
            )
    except:
        pass
    
if __name__ == "__main__":
    StockScanner().run()
