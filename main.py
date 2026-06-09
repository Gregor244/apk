import os
import json
import threading
import requests
import certifi
import webbrowser
import time
import re
import copy
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor

from kivy.config import Config
Config.set('graphics', 'multisamples', '0')

from kivy.core.window import Window
Window.clearcolor = (1, 1, 1, 1)

from kivy.clock import Clock
from kivy.utils import platform
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivy.uix.boxlayout import BoxLayout
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.textfield import MDTextField
from kivy.uix.scrollview import ScrollView
from kivymd.uix.snackbar import MDSnackbar
try:
    from android import mActivity
    from android import AndroidService
except Exception:
    mActivity = None
    AndroidService = None

try:
    from plyer import notification
except ImportError:
    notification = None

try:
    from plyer import browser as plyer_browser
except Exception:
    plyer_browser = None

if platform == 'android':
    from android.permissions import request_permissions, Permission

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
FINNHUB_KEY = "d82t3s1r01ql4onfbbngd82t3s1r01ql4onfbbo0"

IS_GITHUB = os.getenv("GITHUB_ACTIONS") == "true"
CACHE_LOCK = threading.Lock()
MAX_CACHE_SIZE = 250
REQUEST_SESSION = requests.Session()
REQUEST_SESSION.headers.update(HEADERS)

# Lightweight TTL caches to reduce repeated network load and crashes
QUICK_TICKER_CACHE = {}   # ticker -> {"ts": ..., "data": {...}}
QUICK_META_CACHE = {}      # ticker -> {"ts": ..., "data": {...}}
QUICK_GAINER_CACHE = {}    # screener_id -> {"ts": ..., "data": [...]}

PL_DAYS = {
    "Monday": "PONIEDZIAŁEK", "Tuesday": "WTOREK", "Wednesday": "ŚRODA",
    "Thursday": "CZWARTEK", "Friday": "PIĄTEK", "Saturday": "SOBOTA", "Sunday": "NIEDZIELA"
}

# --- NARZĘDZIA POMOCNICZE ---

def format_market_cap(val):
    try:
        val = float(val)
        if val == 0: return "Brak"
        if val >= 1_000_000_000_000: return f"{val/1_000_000_000_000:.2f} bln USD"
        if val >= 1_000_000_000: return f"{val/1_000_000_000:.2f} mld USD"
        if val >= 1_000_000: return f"{val/1_000_000:.2f} mln USD"
        if val >= 1000: return f"{val/1000:.0f} tys. USD"
        return f"{val:.0f} USD"
    except: return "Brak"



def safe_number(val, default=0.0):
    try:
        if val is None:
            return default
        return float(val)
    except Exception:
        return default


def get_pl_session_hint(now=None):
    now = now or datetime.now()
    if now.weekday() >= 5:
        return "CLOSED"
    minutes = now.hour * 60 + now.minute
    pre_start = 10 * 60
    regular_start = 15 * 60 + 30
    post_start = 22 * 60
    post_end = 2 * 60

    if pre_start <= minutes < regular_start:
        return "PRE"
    if regular_start <= minutes < post_start:
        return "REGULAR"
    if minutes >= post_start or minutes < post_end:
        return "POST"
    return "CLOSED"


def timestamp_text():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")


def update_banner(text=None):
    stamp = text or timestamp_text()
    return MDLabel(
        text=color_wrap(f"Ostatnia aktualizacja: {stamp}", "#888888"),
        markup=True,
        size_hint_y=None,
        height=dp(24),
        halign="left",
    )


def fmt_num(value, digits=2, signed=False):
    value = safe_number(value, 0.0)
    if signed:
        return f"{value:+.{digits}f}"
    return f"{value:.{digits}f}"


def color_wrap(text, color):
    return f"[color={color}]{text}[/color]"


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


def color_for_macd(macd, signal):
    return "#00AA00" if macd > signal else "#FF0000"


def color_for_hist(hist):
    if hist > 0:
        return "#00AA00"
    if hist < 0:
        return "#FF0000"
    return "#888888"


def calculate_histogram(macd, signal_line):
    try:
        return round(float(macd) - float(signal_line), 3)
    except Exception:
        return 0.0


def format_histogram(hist):
    hist = safe_number(hist, 0.0)
    return color_wrap(fmt_num(hist, 3, signed=True), color_for_hist(hist))


def format_price_line(value, benchmark=None):
    value = safe_number(value, 0.0)
    if benchmark is None:
        color = "#888888"
    else:
        benchmark = safe_number(benchmark, 0.0)
        color = "#00AA00" if value > benchmark else "#FF0000" if value < benchmark else "#888888"
    return color_wrap(fmt_num(value, 2), color)


def calculate_signal_strength(rsi, macd, signal_line, hist=None, price=None, sma14=None, sma90=None):
    score = 0
    if rsi <= 30:
        score += 3
    elif rsi <= 40:
        score += 2
    elif rsi <= 50:
        score += 1
    elif rsi >= 70:
        score -= 3
    elif rsi >= 60:
        score -= 2

    hist = calculate_histogram(macd, signal_line) if hist is None else hist
    if macd > signal_line:
        score += 2
    else:
        score -= 1

    if hist > 0:
        score += 1
    else:
        score -= 0.5

    if price is not None and sma14 is not None:
        if price > sma14:
            score += 0.5
        else:
            score -= 0.25

    if price is not None and sma90 is not None:
        if price > sma90:
            score += 0.5
        else:
            score -= 0.25

    if score >= 4.5:
        label, color = "MOCNE KUP", "#006600"
    elif score >= 2.0:
        label, color = "KUP", "#00AA00"
    elif score >= 0.0:
        label, color = "TRZYMAJ", "#888888"
    elif score >= -2.0:
        label, color = "SPRZEDAJ", "#FF9900"
    else:
        label, color = "MOCNE SPRZEDAJ", "#FF0000"
    return score, label, color



def get_session_snapshot(data):
    market_state = str(data.get("market_state", "REGULAR") or "REGULAR").upper()
    regular_price = safe_number(data.get("price", 0.0), 0.0)
    prev_close = safe_number(data.get("prev_close", 0.0), 0.0)
    pre_price = safe_number(data.get("pre_price", 0.0), 0.0)
    post_price = safe_number(data.get("post_price", 0.0), 0.0)

    hint = get_pl_session_hint()

    if any(k in market_state for k in ("PRE",)) or (hint == "PRE" and pre_price > 0):
        session = "PRE"
        session_label = "[color=#0000FF][b][PRE-MARKET][/b][/color]"
        price = pre_price if pre_price > 0 else prev_close if prev_close > 0 else regular_price
    elif any(k in market_state for k in ("POST",)) or (hint == "POST" and post_price > 0):
        session = "POST"
        session_label = "[color=#800080][b][POST-MARKET][/b][/color]"
        price = post_price if post_price > 0 else prev_close if prev_close > 0 else regular_price
    elif market_state in ("REGULAR", "OPEN") or hint == "REGULAR":
        session = "REGULAR"
        session_label = "[color=#00AA00][b][MARKET OPEN][/b][/color]"
        price = regular_price if regular_price > 0 else prev_close
    else:
        session = "CLOSED"
        session_label = "[color=#FF9900][b][ZAMKNIĘTY][/b][/color]"
        price = regular_price if regular_price > 0 else prev_close

    if price <= 0 and prev_close > 0:
        price = prev_close

    if prev_close > 0 and price > 0:
        change_amt = price - prev_close
        change_pct = (change_amt / prev_close) * 100 if prev_close else 0.0
    else:
        change_amt = safe_number(data.get("change_amt", 0.0), 0.0)
        change_pct = safe_number(data.get("change_pct", 0.0), 0.0)

    return {
        "session": session,
        "session_label": session_label,
        "price": price,
        "change_amt": change_amt,
        "change_pct": change_pct,
        "prev_close": prev_close,
    }

def add_cache_items(app, items: dict, visible_symbols=None, keep_symbols=None):
    visible_symbols = list(dict.fromkeys([s for s in (visible_symbols or items.keys()) if s]))
    keep_symbols = list(dict.fromkeys([s for s in (keep_symbols or []) if s]))

    with CACHE_LOCK:
        old_cache = dict(getattr(app, "shared_cache", {}))
        new_cache = {}

        for sym in visible_symbols:
            if sym in items:
                new_cache[sym] = merge_with_cache(sym, items[sym], old_cache)
            elif sym in old_cache:
                new_cache[sym] = old_cache[sym]

        for sym in keep_symbols:
            if sym in old_cache and sym not in new_cache:
                new_cache[sym] = old_cache[sym]

        app.shared_cache = new_cache
        if len(app.shared_cache) > MAX_CACHE_SIZE:
            keys = list(app.shared_cache.keys())[-MAX_CACHE_SIZE:]
            app.shared_cache = {k: app.shared_cache[k] for k in keys}
        app.cache_time = datetime.now()


def make_tp_sl(price, tp_pct=0.03, sl_pct=0.02):
    price = safe_number(price, 0.0)
    return price * (1 + tp_pct), price * (1 - sl_pct)


def safe_ticker_label(symbol):
    return normalize_company_name(symbol, symbol)


def chunked_list(values, size):
    values = list(values)
    if size <= 0:
        size = 1
    for i in range(0, len(values), size):
        yield values[i:i + size]


def session_source_tag(session, sym, pre_set, day_set, post_set):
    if session == "PRE" and sym in pre_set:
        return "[color=#00FFFF][PRE-MARKET GAINER][/color]"
    if session == "POST" and sym in post_set:
        return "[color=#CC33FF][POST-MARKET GAINER][/color]"
    if session == "REGULAR" and sym in day_set:
        return "[color=#00FF00][ZYSKUJĄCE DZISIAJ][/color]"
    return "[color=#777777][RYNEK][/color]"


def company_display(sym, data):
    data = data or {}
    name = normalize_company_name(sym, data.get("name", sym))
    market_cap = safe_number(data.get("market_cap", 0), 0.0)
    if (not name or name.upper() == sym.upper() or market_cap <= 0) and sym:
        data = enrich_company_meta(sym, data)
        name = normalize_company_name(sym, data.get("name", sym))
    return f"{sym} ({name})" if name and name.upper() != sym.upper() else sym


def enrich_company_meta(sym, data=None, force=False):
    data = dict(data or {})
    name = normalize_company_name(sym, data.get("name", sym))
    market_cap = safe_number(data.get("market_cap", 0), 0.0)

    if not force:
        cached = _ttl_hit(QUICK_META_CACHE, sym, 21600)  # 6h
        if cached:
            merged = dict(data)
            merged.update({k: v for k, v in cached.items() if v not in (None, "", 0)})
            return merged

    if (name == sym or not name or market_cap <= 0) and sym:
        try:
            prof = safe_request(f"https://finnhub.io/api/v1/stock/profile2?symbol={sym}&token={FINNHUB_KEY}", timeout=4).json()
            if isinstance(prof, dict):
                if (name == sym or not name) and prof.get("name"):
                    data["name"] = normalize_company_name(sym, prof["name"])
                if market_cap <= 0 and prof.get("marketCapitalization"):
                    data["market_cap"] = float(prof["marketCapitalization"]) * 1_000_000
            _ttl_set(QUICK_META_CACHE, sym, data)
        except Exception:
            pass
    return data

def is_pr_news_title(title):
    t = (title or "").lower()
    return any(k in t for k in [
        "contract", "agreement", "deal", "partnership", "collaboration", "award",
        "government", "federal", "state", "rząd", "ai", "artificial intelligence",
        "transform", "launch", "expands", "expansion", "license", "mou", "memorandum"
    ])


def is_fda_pdufa_title(title):
    t = (title or "").lower()
    regulatory = any(k in t for k in ["fda", "pdufa", "adcom", "crl", "nda", "bla", "approval", "approved", "approves", "approve"])
    biotech_context = any(k in t for k in ["biotech", "pharma", "drug", "therapy", "treatment", "clinical", "trial", "phase", "readout", "topline"])
    return regulatory and (("fda" in t or "pdufa" in t or "adcom" in t or "crl" in t or "nda" in t or "bla" in t) or biotech_context)


def is_contract_ai_title(title):
    t = (title or "").lower()
    contract = any(k in t for k in ["contract", "agreement", "deal", "award", "won", "wins", "large deal", "major contract", "government", "govt", "federal", "state", "military"])
    ai = any(k in t for k in ["ai", "artificial intelligence", "machine learning", "genai", "generative ai", "transform"])
    return contract or ai


def is_merger_mna_title(title):
    t = (title or "").lower()
    return any(k in t for k in ["merger", "acquisition", "buyout", "takeover", "tender offer"])


def safe_request(url, timeout=5, retries=3, headers=None, **kwargs):
    headers = headers or HEADERS
    last_exc = None
    for i in range(retries):
        try:
            return requests.get(url, headers=headers, timeout=timeout, **kwargs)
        except Exception as e:
            last_exc = e
            time.sleep(1.2 * (i + 1))
    print(f"safe_request failed: {url} | {last_exc}")
    class _DummyResponse:
        status_code = 0
        def json(self):
            return {}
        text = ""

    return _DummyResponse()


# --- SERVICE BRIDGE ---

SERVICE_BRIDGE_SUBDIR = "service"
SERVICE_QUEUE_FILENAME = "queue.json"
SERVICE_STATE_FILENAME = "state.json"
SERVICE_ACK_FILENAME = "ack.json"

def _service_paths():
    app = MDApp.get_running_app()
    base_dir = os.path.join(app.user_data_dir, SERVICE_BRIDGE_SUBDIR) if app else os.path.join(os.path.expanduser("~"), SERVICE_BRIDGE_SUBDIR)
    os.makedirs(base_dir, exist_ok=True)
    return {
        "base": base_dir,
        "queue": os.path.join(base_dir, SERVICE_QUEUE_FILENAME),
        "state": os.path.join(base_dir, SERVICE_STATE_FILENAME),
        "ack": os.path.join(base_dir, SERVICE_ACK_FILENAME),
    }

def init_service_bridge():
    return _service_paths()

def queue_service_event(event_type, title, message, key, extra=None):
    paths = _service_paths()
    today = datetime.now().date().isoformat()
    payload = {"date": today, "items": []}

    try:
        if os.path.exists(paths["queue"]):
            with open(paths["queue"], "r", encoding="utf-8") as f:
                existing = json.load(f)
            if existing.get("date") == today and isinstance(existing.get("items"), list):
                payload = existing
    except Exception:
        pass

    if not key:
        key = f"{event_type}|{title}|{message}"

    if any(item.get("key") == key for item in payload["items"]):
        return False

    payload["items"].append({
        "type": event_type,
        "key": key,
        "title": title,
        "message": message,
        "extra": extra or {},
        "ts": datetime.now().isoformat(),
    })

    try:
        with open(paths["queue"], "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        return True
    except Exception as e:
        print(f"queue_service_event error: {e}")
        return False

def read_service_ack():
    paths = _service_paths()
    if not os.path.exists(paths["ack"]):
        return {}
    try:
        with open(paths["ack"], "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def start_foreground_service():
    if platform != "android" or AndroidService is None:
        return False
    try:
        service = AndroidService(
            "Skaner Gieldy USA",
            "Powiadomienia i alarmy działają w tle"
        )
        service.start("Skaner Gieldy USA działa w tle")
        return True
    except Exception as e:
        print(f"start_foreground_service error: {e}")
        return False


def normalize_company_name(symbol, name=None):
    """Ujednolica nazwę spółki, gdy API zwraca sam ticker albo pusty opis."""
    symbol = (symbol or "").strip().upper()
    cleaned = (name or "").strip()
    fallback_names = {
        "DBI": "Designer Brands",
        "LE": "Lands' End",
        "UNFI": "United Natural Foods",
        "RIVN": "Rivian Automotive",
        "PEP": "PepsiCo",
        "PLTR": "Palantir Technologies",
        "SOFI": "SoFi Technologies",
        "NIO": "NIO Inc.",
        "MSTR": "Strategy",
        "SQ": "Block",
        "PYPL": "PayPal Holdings",
        "UBER": "Uber Technologies",
        "SHOP": "Shopify",
        "HOOD": "Robinhood Markets",
        "CRWD": "CrowdStrike",
        "ZS": "Zscaler",
        "SMCI": "Super Micro Computer",
        "ARM": "Arm Holdings",
        "AMD": "Advanced Micro Devices",
        "AAPL": "Apple",
        "MSFT": "Microsoft",
        "NVDA": "NVIDIA",
        "AMZN": "Amazon",
        "GOOGL": "Alphabet",
        "GOOG": "Alphabet",
        "META": "Meta Platforms",
        "PEP": "PepsiCo",
        "INTC": "Intel",
        "QCOM": "Qualcomm",
        "MRVL": "Marvell Technology",
        "TSM": "Taiwan Semiconductor Manufacturing",
        "COST": "Costco Wholesale",
        "AVGO": "Broadcom",
        "PANW": "Palo Alto Networks",
        "CRM": "Salesforce",
        "NOW": "ServiceNow",
        "MU": "Micron Technology",
        "LRCX": "Lam Research",
        "ISRG": "Intuitive Surgical",
        "BKNG": "Booking Holdings",
        "TXN": "Texas Instruments",
        "INTU": "Intuit",
        "HON": "Honeywell",
        "CSCO": "Cisco Systems",
        "GE": "GE Aerospace",
        "DIS": "The Walt Disney Company",
        "JPM": "JPMorgan Chase",
        "BAC": "Bank of America",
        "XOM": "Exxon Mobil",
        "CVX": "Chevron",
        "WMT": "Walmart",
        "TGT": "Target",
        "NKE": "Nike",
        "F": "Ford Motor",
        "GM": "General Motors",
        "COIN": "Coinbase Global",
        "RIOT": "Riot Platforms",
        "MARA": "Marathon Digital",
        "SNAP": "Snap",
        "PINS": "Pinterest",
        "TTD": "The Trade Desk",
        "ABNB": "Airbnb",
        "LYFT": "Lyft",
        "BABA": "Alibaba Group",
        "XPEV": "XPeng",
        "LI": "Li Auto",
        "CDPROJEKT.WA": "CD Projekt",
        "CDR.WA": "CD Projekt",
        "CL=F": "Crude Oil",
        "NG=F": "Natural Gas",
        "GC=F": "Gold",
        "SI=F": "Silver",
        "CC=F": "Cocoa",
        "ZC=F": "Corn",
        "BTC-USD": "Bitcoin",
        "DX-Y.NYB": "Dollar Index",
        "6E=F": "Euro FX",
        "ES=F": "S&P 500 E-mini",
        "NQ=F": "Nasdaq 100 E-mini",
        "YM=F": "Dow E-mini",
        "RTY=F": "Russell 2000 E-mini",
    }
    if cleaned and cleaned.upper() != symbol:
        return cleaned
    return fallback_names.get(symbol, cleaned or symbol)


def calc_sma(prices, period, fallback=0.0):
    if not prices:
        return fallback
    if len(prices) >= period:
        return sum(prices[-period:]) / period
    return sum(prices) / len(prices)

def fetch_top_gainers_by_type(scr_id="day_gainers"):
    url = f"https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds={scr_id}&count=12"
    try:
        res = safe_request(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            result = res.json().get('finance', {}).get('result')
            if result and isinstance(result, list) and len(result) > 0:
                quotes = result[0].get('quotes', [])
                return [q['symbol'] for q in quotes if 'symbol' in q]
    except: pass
    return []


def fetch_ticker_data(ticker, force=False):
    quote_url = f"https://query2.finance.yahoo.com/v7/finance/quote?symbols={ticker}"
    chart_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"

    res_data = {
        'symbol': ticker, 'name': ticker, 'price': 0.0, 'prev_close': 0.0,
        'vol': 0, 'avg_vol': 0, 'volume_trend': "[color=#888888]Brak danych[/color]", 'market_state': "REGULAR",
        'change_amt': 0.0, 'change_pct': 0.0,
        'pre_price': 0.0, 'pre_change_pct': 0.0, 'pre_change_amt': 0.0,
        'post_price': 0.0, 'post_change_pct': 0.0, 'post_change_amt': 0.0,
        'closes': [], 'volumes': [], 'high': 0.0, 'low': 0.0, 'open': 0.0,
        'pe': "N/A", 'market_cap': 0, 'day_low': 0.0, 'day_high': 0.0, 'year_low': 0.0, 'year_high': 0.0
    }


    if not force:
        cached = _ttl_hit(QUICK_TICKER_CACHE, ticker, 90)
        if cached is not None:
            return cached
    try:
        rq = safe_request(quote_url, headers=HEADERS, timeout=5)
        if rq.status_code == 200:
            q_res = rq.json().get('quoteResponse', {}).get('result', [])
            if q_res:
                q = q_res[0]
                name = q.get('longName') or q.get('shortName') or q.get('displayName')
                res_data['name'] = normalize_company_name(ticker, name)
                res_data['price'] = float(q.get('regularMarketPrice', 0.0))
                res_data['prev_close'] = float(q.get('regularMarketPreviousClose', 0.0))
                res_data['vol'] = int(q.get('regularMarketVolume', 0))
                res_data['avg_vol'] = int(q.get('averageDailyVolume10Day', 0))

                res_data['market_state'] = q.get('marketState', 'REGULAR')

                res_data['change_amt'] = float(q.get('regularMarketChange', 0.0))
                res_data['change_pct'] = float(q.get('regularMarketChangePercent', 0.0))

                pe_val = q.get('trailingPE', q.get('forwardPE'))
                res_data['pe'] = f"{float(pe_val):.2f}" if pe_val else "N/A"

                market_cap = q.get('marketCap', 0) or 0
                if not market_cap and res_data['price'] > 0:
                    shares = q.get('sharesOutstanding') or q.get('impliedSharesOutstanding') or 0
                    try:
                        market_cap = float(shares) * float(res_data['price'])
                    except Exception:
                        market_cap = 0
                res_data['market_cap'] = market_cap

                res_data['day_low'] = float(q.get('regularMarketDayLow', 0.0))
                res_data['day_high'] = float(q.get('regularMarketDayHigh', 0.0))
                res_data['year_low'] = float(q.get('fiftyTwoWeekLow', 0.0))
                res_data['year_high'] = float(q.get('fiftyTwoWeekHigh', 0.0))

                res_data['pre_price'] = float(q.get('preMarketPrice', 0.0))
                res_data['pre_change_pct'] = float(q.get('preMarketChangePercent', 0.0))
                res_data['pre_change_amt'] = float(q.get('preMarketChange', 0.0))
                res_data['post_price'] = float(q.get('postMarketPrice', 0.0))
                res_data['post_change_pct'] = float(q.get('postMarketChangePercent', 0.0))
                res_data['post_change_amt'] = float(q.get('postMarketChange', 0.0))
    except:
        pass

    try:
        rc = safe_request(chart_url, headers=HEADERS, timeout=5)
        if rc.status_code == 200:
            c_res = rc.json().get('chart', {}).get('result', [])
            if c_res:
                meta = c_res[0].get('meta', {})
                if res_data['price'] == 0.0: res_data['price'] = meta.get('regularMarketPrice', 0.0)
                if res_data['prev_close'] == 0.0: res_data['prev_close'] = meta.get('chartPreviousClose', 0.0)

                indicators = c_res[0].get('indicators', {}).get('quote', [{}])[0]
                closes = [c for c in indicators.get('close', []) if c is not None]
                volumes = [v for v in indicators.get('volume', []) if v is not None]
                opens = [o for o in indicators.get('open', []) if o is not None]
                highs = [h for h in indicators.get('high', []) if h is not None]
                lows = [l for l in indicators.get('low', []) if l is not None]

                res_data['closes'] = closes
                res_data['volumes'] = volumes
                if opens: res_data['open'] = opens[-1]
                if highs: res_data['high'] = highs[-1]
                if lows: res_data['low'] = lows[-1]

                if len(volumes) >= 2:
                    if volumes[-1] > volumes[-2]: res_data['volume_trend'] = "[color=#00AA00]Rosnący 📈[/color]"
                    else: res_data['volume_trend'] = "[color=#FF0000]Spadający 📉[/color]"
    except:
        pass

    # Zapasowe pobieranie (Agresywny Fallback) z Finnhub
    if res_data['price'] == 0.0 or res_data['name'] == ticker or res_data['market_cap'] == 0:
        try:
            fh_q = safe_request(f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_KEY}", timeout=3).json()
            if fh_q and fh_q.get('c', 0) > 0:
                if res_data['price'] == 0.0: res_data['price'] = float(fh_q.get('c', 0.0))
                if res_data['prev_close'] == 0.0: res_data['prev_close'] = float(fh_q.get('pc', 0.0))
                if res_data['day_high'] == 0.0: res_data['day_high'] = float(fh_q.get('h', 0.0))
                if res_data['day_low'] == 0.0: res_data['day_low'] = float(fh_q.get('l', 0.0))
                if res_data['change_amt'] == 0.0: res_data['change_amt'] = float(fh_q.get('d', 0.0))
                if res_data['change_pct'] == 0.0: res_data['change_pct'] = float(fh_q.get('dp', 0.0))

            prof = safe_request(f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_KEY}", timeout=3).json()
            if prof:
                if prof.get('name'): res_data['name'] = normalize_company_name(ticker, prof['name'])
                if prof.get('marketCapitalization') and res_data['market_cap'] == 0:
                    res_data['market_cap'] = prof['marketCapitalization'] * 1000000
            if res_data['pe'] == "N/A":
                metrics = safe_request(f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_KEY}", timeout=3).json()
                if metrics and 'metric' in metrics:
                    pe_v = metrics['metric'].get('peNormalizedAnnual') or metrics['metric'].get('peExclExtraTTM')
                    if pe_v: res_data['pe'] = f"{pe_v:.2f}"
        except:
            pass

    # Wymuszenie statusu zamkniętego i wolumenu w dni wolne / brak aktualizacji
    if datetime.now().weekday() >= 5:
        res_data['market_state'] = "CLOSED"
    if res_data['vol'] == 0 and res_data['volumes']:
        res_data['vol'] = res_data['volumes'][-1]

    if res_data['name'] == ticker:
        res_data['name'] = normalize_company_name(ticker, res_data['name'])

    _ttl_set(QUICK_TICKER_CACHE, ticker, res_data)
    return res_data

def fetch_bulk_ticker_data(tickers, force=False):
    bulk_results = {}
    unique = [t for t in dict.fromkeys([str(x).strip().upper() for x in tickers if x]) if t]
    if not unique:
        return bulk_results

    # Smaller chunks reduce peak load and Android crashes
    chunk_size = 8 if len(unique) > 8 else max(1, len(unique))
    for chunk in chunked_list(unique, chunk_size):
        max_workers = min(2, len(chunk))
        if max_workers < 1:
            max_workers = 1

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            results = executor.map(lambda ticker: (ticker, fetch_ticker_data(ticker, force=force)), chunk)
            for ticker, data in results:
                if data and safe_number(data.get('price', 0.0), 0.0) > 0:
                    bulk_results[ticker] = data
    return bulk_results


def merge_with_cache(sym, new_data, cache):
    """Zabezpiecza przed nadpisaniem istniejących danych (np. nazwy, kapitalizacji) pustymi wartościami podczas zminimalizowania lub ucięcia API."""
    if sym not in cache:
        return new_data
    old_data = cache[sym]
    
    if new_data.get('name') == sym and old_data.get('name', sym) != sym:
        new_data['name'] = old_data['name']
    if new_data.get('pe') == "N/A" and old_data.get('pe', "N/A") != "N/A":
        new_data['pe'] = old_data['pe']
    if new_data.get('market_cap', 0) == 0 and old_data.get('market_cap', 0) > 0:
        new_data['market_cap'] = old_data['market_cap']
    if new_data.get('vol', 0) == 0 and old_data.get('vol', 0) > 0:
        new_data['vol'] = old_data['vol']
    if new_data.get('avg_vol', 0) == 0 and old_data.get('avg_vol', 0) > 0:
        new_data['avg_vol'] = old_data['avg_vol']
        
    return new_data
    

def fetch_finnhub_ticker_data(ticker):
    base_url = "https://finnhub.io/api/v1"
    params = {"symbol": ticker, "token": FINNHUB_KEY}
    res_data = fetch_ticker_data(ticker, force=False)
    res_data['eps'] = "N/A"
    res_data['div_yield'] = "N/A"
    res_data['next_earnings'] = "Brak danych"
    res_data['prev_earnings_period'] = "Brak"
    res_data['prev_earnings_surprise'] = "Brak danych"
    res_data['news'] = []
    res_data['earnings_reaction'] = "Brak danych"

    try:
        metrics = safe_request(f"{base_url}/stock/metric", params={"symbol": ticker, "metric": "all", "token": FINNHUB_KEY}, timeout=5).json()
        if 'metric' in metrics:
            m = metrics['metric']
            eps = m.get('epsTTM', 'N/A')
            res_data['eps'] = f"{eps:.2f}" if isinstance(eps, (int, float)) else "N/A"
            div = m.get('dividendYieldIndicatedAnnual', 'N/A')
            res_data['div_yield'] = f"{div:.2f}%" if isinstance(div, (int, float)) else "Brak"

            if res_data['year_high'] == 0.0: res_data['year_high'] = m.get('52WeekHigh', 0.0)
            if res_data['year_low'] == 0.0: res_data['year_low'] = m.get('52WeekLow', 0.0)
            if res_data['pe'] == "N/A": 
                pe_v = m.get('peNormalizedAnnual') or m.get('peExclExtraTTM')
                if pe_v: res_data['pe'] = f"{pe_v:.2f}"

        today = datetime.now().date()
        future = today + timedelta(days=90)
        past_week = today - timedelta(days=7)

        past_earn = safe_request(f"{base_url}/stock/earnings", params=params, timeout=5).json()
        if past_earn and isinstance(past_earn, list):
            last_e = past_earn[0]
            period_str = last_e.get('period', '')
            res_data['prev_earnings_period'] = period_str or 'Nieznany'
            actual = last_e.get('actual')
            est = last_e.get('estimate')
            if actual is not None and est is not None:
                surprise_pct = ((actual - est) / abs(est)) * 100 if est != 0 else 0
                znak = "+" if surprise_pct > 0 else ""
                res_data['prev_earnings_surprise'] = f"{znak}{surprise_pct:.1f}% (Akt: {actual:.2f}, Szac: {est:.2f})"

            if period_str:
                try:
                    e_date = datetime.strptime(period_str, '%Y-%m-%d')
                    start_ts = int((e_date - timedelta(days=2)).timestamp())
                    end_ts = int((e_date + timedelta(days=4)).timestamp())
                    react_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?period1={start_ts}&period2={end_ts}&interval=1d"
                    react_req = safe_request(react_url, headers=HEADERS, timeout=5)
                    if react_req.status_code == 200:
                        react_data = react_req.json().get('chart', {}).get('result', [])[0]
                        react_closes = react_data.get('indicators', {}).get('quote', [{}])[0].get('close', [])
                        valid_c = [c for c in react_closes if c is not None]
                        if len(valid_c) >= 2:
                            r_pct = ((valid_c[-1] - valid_c[0]) / valid_c[0]) * 100
                            r_znak = "+" if r_pct > 0 else ""
                            res_data['earnings_reaction'] = f"[b][color={'#00AA00' if r_pct>0 else '#FF0000'}]{r_znak}{r_pct:.2f}%[/color][/b]"
                except:
                    pass

        earn_cal = safe_request(f"{base_url}/calendar/earnings", params={"symbol": ticker, "from": today.strftime('%Y-%m-%d'), "to": future.strftime('%Y-%m-%d'), "token": FINNHUB_KEY}, timeout=5).json()
        if 'earningsCalendar' in earn_cal and earn_cal['earningsCalendar']:
            res_data['next_earnings'] = earn_cal['earningsCalendar'][0].get('date', 'Brak danych')

        now = datetime.now()
        yesterday_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        timestamp_threshold = int(yesterday_start.timestamp())

        news = safe_request(f"{base_url}/company-news", params={"symbol": ticker, "from": past_week.strftime('%Y-%m-%d'), "to": today.strftime('%Y-%m-%d'), "token": FINNHUB_KEY}, timeout=5).json()
        if isinstance(news, list):
            for n in news:
                if len(res_data['news']) >= 5: break
                pub_time = n.get('datetime', 0)
                if pub_time < timestamp_threshold: continue
                title = n.get('headline', '')
                url = n.get('url', '')
                if title and url:
                    res_data['news'].append(f"• [ref={url}][color=#0000FF]{title}[/color][/ref]")

        res_data['found'] = True
    except Exception as e:
        print(f"Błąd Finnhub: {e}")
        res_data['found'] = res_data['price'] > 0

    if res_data['name'] == ticker:
        res_data['name'] = normalize_company_name(ticker, res_data['name'])

    return res_data

# --- ANALIZA TECHNICZNA ---

def calculate_rsi(prices, period=14):
    try:
        if len(prices) < period + 1: return 50.0
        deltas = [prices[i] - prices[i-1] for i in range(1, len(prices))]
        gains = [d if d > 0 else 0 for d in deltas]
        losses = [-d if d < 0 else 0 for d in deltas]
        avg_gain = sum(gains[:period]) / period
        avg_loss = sum(losses[:period]) / period
        for i in range(period, len(deltas)):
            avg_gain = (avg_gain * (period - 1) + gains[i]) / period
            avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        if avg_loss == 0: return 100.0
        rs = avg_gain / avg_loss
        return round(100.0 - (100.0 / (1.0 + rs)), 2)
    except: return 50.0

def calculate_ema(prices, period):
    if not prices: return []
    ema = [prices[0]]
    k = 2 / (period + 1)
    for price in prices[1:]:
        ema.append(price * k + ema[-1] * (1 - k))
    return ema

def calculate_macd(prices):
    try:
        if len(prices) < 35: return 0.0, 0.0, 0.0
        ema12 = calculate_ema(prices, 12)
        ema26 = calculate_ema(prices, 26)
        macd_line = [e12 - e26 for e12, e26 in zip(ema12[-len(ema26):], ema26)]
        signal_line = calculate_ema(macd_line, 9)
        return round(macd_line[-1], 3), round(signal_line[-1], 3), round(macd_line[-1] - signal_line[-1], 3)
    except: return 0.0, 0.0, 0.0

def generate_signal(rsi, macd, signal_line):
    macd_bullish = macd > signal_line
    if rsi <= 35 and macd_bullish:
        return "[color=#006600][b]MOCNE KUP (STRONG BUY)[/b][/color]"
    elif rsi <= 45 or macd_bullish:
        return "[color=#00AA00][b]KUPUJ (BUY)[/b][/color]"
    elif rsi >= 65:
        return "[color=#FF0000][b]MOCNE SPRZEDAJ (STRONG SELL)[/b][/color]"
    else:
        return "[color=#FF0000][b]SPRZEDAJ (SELL)[/b][/color]"

# --- INTERFEJS GRAFICZNY ---

class DataCard(MDCard):
    def __init__(self, text, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.size_hint_y = None
        self.padding = [dp(12), dp(12), dp(12), dp(12)]
        self.radius = [dp(8), dp(8), dp(8), dp(8)]
        self.elevation = 1
        self.lbl = MDLabel(text=text, markup=True, size_hint_y=None, theme_text_color="Primary", halign="left")
        self.lbl.bind(width=lambda instance, value: setattr(instance, 'text_size', (value, None)))
        self.lbl.bind(texture_size=self._update_height)
        self.lbl.bind(on_ref_press=lambda instance, ref: (plyer_browser.open(ref) if plyer_browser else webbrowser.open(ref)))
        self.add_widget(self.lbl)

    def _update_height(self, instance, size):
        self.lbl.height = size[1]
        self.height = size[1] + dp(24)

class ScrollableTab(MDBoxLayout, MDTabsBase):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.md_bg_color = [1, 1, 1, 1]
        self.is_loaded = False
        self._loading = False
        self.last_update_text = ""
        
        self.control_panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, height=dp(0),
            padding=[dp(12), dp(14), dp(12), dp(6)], spacing=dp(8)
        )
        self.add_widget(self.control_panel)
        
        self.scroll = ScrollView()
        self.content = MDBoxLayout(orientation="vertical", spacing=dp(8), size_hint_y=None, padding=[dp(8), dp(8)])
        self.content.bind(minimum_height=self.content.setter('height'))
        self.scroll.add_widget(self.content)
        self.add_widget(self.scroll)

    def load_data_if_needed(self):
        if not self.is_loaded:
            self.refresh_data()
            self.is_loaded = True

    def refresh_data(self, *args, **kwargs):
        if self._loading:
            return
        self._loading = True
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text="Pobieranie danych...", halign="center"))
        threading.Thread(target=self._safe_fetch, args=args, kwargs=kwargs, daemon=True).start()

    def _safe_fetch(self, *args, **kwargs):
        try:
            self._fetch(*args, **kwargs)
        except Exception as e:
            print(f"Błąd pobierania w zakładce: {e}")
            Clock.schedule_once(lambda dt: self._show_error("Błąd połączenia. Spróbuj później."))
        finally:
            Clock.schedule_once(lambda dt: setattr(self, '_loading', False), 0)

    def _fetch(self, *args, **kwargs): pass

    def _show_error(self, message):
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text=f"[color=#FF0000][b]{message}[/b][/color]", markup=True, halign="center"))
        btn = MDRaisedButton(text="Ponów próbę", on_release=self.refresh_data)
        self.content.add_widget(btn)


class InfoTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Info"
        super().__init__(**kw)
        self.control_panel.height = dp(105)
        self._status_cache = {"ts": 0.0, "lines": []}
        self._glossary_visible = False
        self._glossary_full_height = dp(1)

        self.content.clear_widgets()
        self.status_container = MDBoxLayout(
            orientation="vertical",
            spacing=dp(8),
            size_hint_y=None,
            padding=[dp(8), dp(8)],
        )
        self.status_container.bind(minimum_height=self.status_container.setter('height'))
        self.content.add_widget(self.status_container)

        self.tabs_desc_card = DataCard(text=self._tabs_description_text())
        self.content.add_widget(self.tabs_desc_card)

        self.glossary_card = DataCard(text=self._glossary_text())
        self.content.add_widget(self.glossary_card)
        Clock.schedule_once(self._cache_glossary_height, 0)
        self._hide_glossary(initial=True)

        row1 = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        btn_status = MDRaisedButton(text="Sprawdź Status Rynków", on_release=lambda x: self.refresh_data(force=True))
        btn_glossary = MDRaisedButton(text="Słowniczek", on_release=lambda x: self.toggle_glossary())
        btn_test = MDRaisedButton(text="TEST Powiadomień", on_release=lambda x: self.run_notification_test(), md_bg_color=(0, 0.5, 0, 1))
        row1.add_widget(btn_status)
        row1.add_widget(btn_glossary)
        row1.add_widget(btn_test)
        self.control_panel.add_widget(row1)

    def _tabs_description_text(self):
        return (
            "[b]Info[/b]\n"
            "Pokazuje status rynku US i podstawowe godziny sesji. Zawiera też stały słowniczek oraz opis każdej zakładki.\n\n"
            "[b]Skaner[/b]\n"
            "Skanuje wybrane spółki i dynamiczne gainery, pokazując cenę sesyjną, wolumen oraz wskaźniki techniczne.\n\n"
            "[b]Ticker[/b]\n"
            "Analizuje jeden ticker dokładniej: fundamenty, earnings, zmianę względem prev close i wskaźniki techniczne.\n\n"
            "[b]Katalizatory[/b]\n"
            "Zbiera wydarzenia przedkatalityczne, oficjalne katalizatory i kalendarz wyników. Pomaga wyłapywać ruch przed sesją.\n\n"
            "[b]Newsy[/b]\n"
            "Pokazuje najnowsze newsy dla watchlisty oraz newsy rynkowe. PR newsy small/micro cap są utrzymywane do końca dnia.\n\n"
            "[b]CFD/Własne[/b]\n"
            "Buduje dynamiczne listy spółek i CFD na podstawie screenersów oraz filtrów technicznych. Sekcje wskazują potencjał wybicia i miejsce względem średnich."
        )

    def _glossary_text(self):
        return (
            "[b]SMA[/b] — średnia krocząca; cena powyżej SMA zwykle oznacza silniejszy trend, poniżej może sugerować słabość.\n"
            "[b]RSI[/b] — 0-100; poniżej 30 to często wyprzedanie, powyżej 70 wykupienie.\n"
            "[b]MACD[/b] — porównuje krótszy i dłuższy trend; MACD nad sygnałem wzmacnia scenariusz wzrostowy.\n"
            "[b]Histogram[/b] — MACD minus sygnał; dodatni zwykle wspiera kupno, ujemny osłabia momentum.\n"
            "[b]P/E[/b] — cena do zysku; niższe bywa tańsze, ale porównuj tylko spółki z podobnej branży.\n\n"
            "[b]Jak czytać kolory[/b]\n"
            "Zielony oznacza zwykle sygnał wzrostowy / lepszą pozycję względem średniej.\n"
            "Czerwony sygnalizuje presję spadkową lub słabszy sygnał, a szary neutralne / brak przewagi."
        )

    def _cache_glossary_height(self, dt):
        self._glossary_full_height = max(self.glossary_card.height, dp(220))

    def _hide_glossary(self, initial=False):
        self.glossary_card.opacity = 0 if not self._glossary_visible else 1
        self.glossary_card.disabled = not self._glossary_visible
        self.glossary_card.height = 0 if not self._glossary_visible else self._glossary_full_height
        self.glossary_card.size_hint_y = None
        if not initial:
            self.glossary_card.texture_update()

    def toggle_glossary(self):
        self._glossary_visible = not self._glossary_visible
        self.glossary_card.opacity = 1 if self._glossary_visible else 0
        self.glossary_card.disabled = not self._glossary_visible
        self.glossary_card.height = self._glossary_full_height if self._glossary_visible else 0

    def run_notification_test(self):
        MDApp.get_running_app().send_notification(title="Test Powiadomienia", message="Test udany!")

    def _should_refresh_cache(self, force=False):
        return force or not self._status_cache.get("lines")

    def refresh_data(self, *args, **kwargs):
        force = kwargs.get('force', False)
        if not self._should_refresh_cache(force=force):
            self._render(self._status_cache.get("lines", []))
            return
        self.status_container.clear_widgets()
        self.status_container.add_widget(MDLabel(text="Pobieranie statusu rynku...", halign="center"))
        threading.Thread(target=self._safe_fetch, kwargs={"force": force}, daemon=True).start()

    def _fetch(self, *args, **kwargs):
        try:
            status_data = safe_request(f"https://finnhub.io/api/v1/stock/market-status?exchange=US&token={FINNHUB_KEY}", timeout=5).json()
            is_open = bool(status_data.get('isOpen', False))
        except Exception:
            is_open = False

        outputs = []
        now = datetime.now()
        for i in range(3):
            check_date = now + timedelta(days=i)
            day_name_pl = PL_DAYS.get(check_date.strftime("%A"), check_date.strftime("%A"))
            date_str = check_date.strftime("%d.%m.%Y")
            if check_date.weekday() >= 5:
                status = "[color=#FF0000]RYNKI ZAMKNIĘTE (Weekend)[/color]"
                details = "Brak sesji giełdowej."
            else:
                market_status = "OTWARTE" if is_open and i == 0 else "OTWARTE / ZAPLANOWANE"
                status = f"[color=#00AA00]RYNKI {market_status}[/color]"
                details = (
                    "Godziny handlu (Czas PL):\n"
                    "• [b]Pre-Market[/b]: 10:00 - 15:30\n"
                    "• [b]Sesja Główna[/b]: 15:30 - 22:00\n"
                    "• [b]Post-Market[/b]: 22:00 - 02:00 (następnego dnia)"
                )
            outputs.append(f"[b]{day_name_pl}[/b] ({date_str})\n{status}\n{details}")
        self._status_cache = {"ts": time.time(), "lines": outputs}
        self.last_update_text = timestamp_text()
        Clock.schedule_once(lambda dt: self._render(outputs))

    def _render(self, lines):
        self.status_container.clear_widgets()
        self.status_container.add_widget(MDLabel(text=color_wrap(f"Ostatnia aktualizacja: {getattr(self, 'last_update_text', timestamp_text())}", "#888888"), markup=True, size_hint_y=None, height=dp(24), halign="left"))
        for line in lines:
            self.status_container.add_widget(DataCard(text=line))

class SkanerTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Skaner"
        super().__init__(**kw)
        self.static_tickers = ["AAPL", "MSFT", "NVDA", "AMD", "SNDK", "MU", "AMZN", "ARM", "MRVL", "NOW", "QUCY"]
        self.control_panel.height = dp(115)
        self._last_scan_signature = None

        self.load_stored_data()

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        self.input_field = MDTextField(hint_text="Wpisz ticker (np. TSLA)", size_hint_x=0.66, mode="rectangle")
        btn_add = MDRaisedButton(text="+", size_hint_x=0.17, on_release=self.add_ticker)
        btn_rem = MDRaisedButton(text="-", size_hint_x=0.17, on_release=self.remove_ticker)

        input_row.add_widget(self.input_field)
        input_row.add_widget(btn_add)
        input_row.add_widget(btn_rem)

        self.control_panel.add_widget(input_row)
        self.control_panel.add_widget(MDRaisedButton(text="Skanuj rynki + Wskaźniki", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    def load_stored_data(self):
        app = MDApp.get_running_app()
        if not app: return
        path = os.path.join(app.user_data_dir, "skaner_tickers.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, list) and saved: self.static_tickers = saved
            except Exception as e:
                print(f"load_stored_data skaner: {e}")

    def save_stored_data(self):
        app = MDApp.get_running_app()
        path = os.path.join(app.user_data_dir, "skaner_tickers.json")
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(self.static_tickers, f)
        except Exception as e:
            print(f"save_stored_data skaner: {e}")

    def add_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        self.input_field.text = ""
        if t and t not in self.static_tickers:
            self.static_tickers.append(t)
            self.save_stored_data()
            self.refresh_data()

    def remove_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        self.input_field.text = ""
        if t in self.static_tickers:
            self.static_tickers.remove(t)
            self.save_stored_data()
            self.refresh_data()

    def _fetch(self, *args, **kwargs):
        cards_data = []
        try:
            gainers_pre = fetch_top_gainers_by_type("pre_market_gainers")[:10]
            gainers_open = fetch_top_gainers_by_type("day_gainers")[:10]
            gainers_post = fetch_top_gainers_by_type("after_hours_gainers")[:10]
        except Exception as e:
            print(f"Skaner screener error: {e}")
            gainers_pre, gainers_open, gainers_post = [], [], []

        pre_set = set(gainers_pre)
        day_set = set(gainers_open)
        post_set = set(gainers_post)

        all_tickers = list(dict.fromkeys(self.static_tickers + gainers_pre + gainers_open + gainers_post))
        bulk_data = fetch_bulk_ticker_data(all_tickers)

        app = MDApp.get_running_app()
        add_cache_items(app, bulk_data, visible_symbols=required)

        signature = tuple(sorted([s for s in all_tickers if s in bulk_data]))

        for sym in all_tickers:
            data = app.shared_cache.get(sym)
            if not data:
                continue

            comp_name = company_display(sym, data)
            session_info = get_session_snapshot(data)
            session = session_info["session"]
            active_price = session_info["price"]
            chg_val = session_info["change_amt"]
            chg_pct = session_info["change_pct"]
            session_label = session_info["session_label"]

            source_tag = session_source_tag(session, sym, pre_set, day_set, post_set)
            closes = data.get('closes', [])
            macd_v, sig_v, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
            hist = calculate_histogram(macd_v, sig_v)

            rsi_val = calculate_rsi(closes, 14) if closes else 50.0
            rsi_str = (
                color_wrap(f"{rsi_val:.1f} (Wyprzedanie)", "#00AA00") if rsi_val <= 35 else
                color_wrap(f"{rsi_val:.1f} (Wykupienie)", "#FF0000") if rsi_val >= 65 else
                color_wrap(f"{rsi_val:.1f} (Neutralny)", "#777777")
            )

            macd_v, sig_v, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
            macd_str = color_wrap(f"{macd_v:.2f}", color_for_macd(macd_v, sig_v))
            hist_str = format_histogram(hist)

            vol_val = data.get('vol', 0)
            avg_vol_val = data.get('avg_vol', 0)
            cap_str = format_market_cap(data.get('market_cap', 0))
            pe_str = str(data.get('pe', 'N/A'))

            trade_score, trade_signal_text, trade_signal_color = calculate_signal_strength(
                rsi_val, macd_v, sig_v, hist=hist, price=active_price,
                sma14=calc_sma(closes, 14, active_price), sma90=calc_sma(closes, 90, active_price)
            )
            trade_signal = color_wrap(f"[b]{trade_signal_text}[/b]", trade_signal_color)

            sma14 = calc_sma(closes, 14, active_price)
            sma50 = calc_sma(closes, 50, active_price)

            txt = (
                f"{session_label} {source_tag} [color=#008080][b]{comp_name}[/b][/color]\n"
                f"Cena: [b]{active_price:.2f} USD[/b] ([color={'#00AA00' if chg_val >= 0 else '#FF0000'}]{chg_val:+.2f} USD | {chg_pct:+.2f}%[/color])\n"
                f"Wolumen: {vol_val:,} (Śred. 10D: {avg_vol_val:,})\n"
                f"Kapitalizacja: {cap_str} | P/E: [b]{pe_str}[/b]\n"
                f"RSI: {rsi_str} | MACD: {macd_str} | Histogram: {hist_str}\n"
                f"SMA14: {format_price_line(sma14, active_price)} | SMA50: {format_price_line(sma50, active_price)}\n"
                f"Sygnał: {trade_signal}"
            )
            cards_data.append(txt)

        if signature and signature != self._last_scan_signature:
            self._last_scan_signature = signature
            try:
                app.send_notification("Skaner", f"Zaktualizowano wyniki dla {len(signature)} spółek.")
            except Exception as e:
                print(f"Skaner notification error: {e}")

        self.last_update_text = timestamp_text()
        Clock.schedule_once(lambda dt: self._render(cards_data))

    def _render(self, cards):
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text=color_wrap(f"Ostatnia aktualizacja: {getattr(self, 'last_update_text', timestamp_text())}", "#888888"), markup=True, size_hint_y=None, height=dp(24), halign="left"))
        for c in cards:
            self.content.add_widget(DataCard(text=c))


class TickerTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Ticker"
        super().__init__(**kw)
        self.control_panel.height = dp(115)

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        self.inp = MDTextField(hint_text="Wpisz ticker (np. TSLA)", size_hint_x=0.70, mode="rectangle")
        btn_search = MDRaisedButton(text="Analizuj", size_hint_x=0.30, on_release=lambda x: self.refresh_data(self.inp.text.strip().upper()))

        input_row.add_widget(self.inp)
        input_row.add_widget(btn_search)
        self.control_panel.add_widget(input_row)

    def refresh_data(self, sym=None, *args, **kwargs):
        if not sym: return
        self._msg("Pobieranie danych API... Proszę czekać.", is_card=False)
        threading.Thread(target=self._safe_fetch, args=(sym,), daemon=True).start()

    def _fetch(self, ticker, *args, **kwargs):
        data = fetch_finnhub_ticker_data(ticker)
        if not data.get('found') or (safe_number(data.get('price', 0.0), 0.0) == 0.0 and safe_number(data.get('prev_close', 0.0), 0.0) == 0.0):
            Clock.schedule_once(lambda dt: self._msg(f"Nie znaleziono danych dla: {ticker}", False))
            return

        comp_name = company_display(ticker, data)
        session_info = get_session_snapshot(data)
        p = session_info["price"]
        chg_amt = session_info["change_amt"]
        chg_pct = session_info["change_pct"]
        session_label = session_info["session_label"]

        closes = data.get('closes', [])
        volumes = data.get('volumes', [])

        sma14 = calc_sma(closes, 14, p)
        sma30 = calc_sma(closes, 30, p)
        sma50 = calc_sma(closes, 50, p)
        sma90 = calc_sma(closes, 90, p)
        sma200 = calc_sma(closes, 200, p)

        rsi = calculate_rsi(closes, 14) if len(closes) > 14 else 50.0
        macd, sig, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
        hist = calculate_histogram(macd, sig)
        trade_score, trade_signal_text, trade_signal_color = calculate_signal_strength(rsi, macd, sig, hist=hist, price=p, sma14=sma14, sma90=sma90)
        trade_signal = color_wrap(f"[b]{trade_signal_text}[/b]", trade_signal_color)

        vol_trend = "Brak"
        if len(volumes) > 5:
            avg_vol = sum(volumes[-5:]) / 5
            vol_trend = color_wrap("Powyżej śred.", "#00AA00") if data.get('vol', 0) > avg_vol else color_wrap("Poniżej śred.", "#FF0000")

        rec_text = color_wrap("[b]ZDECYDOWANIE TAK[/b]", "#00AA00") if trade_score >= 4.5 else (
            color_wrap("[b]NEUTRALNIE[/b]", "#FF9900") if trade_score >= 0 else color_wrap("[b]NIE / RYZYKO[/b]", "#FF0000")
        )

        days_to_earnings = "Brak danych"
        if data.get('next_earnings') != "Brak danych":
            try:
                next_date = datetime.strptime(data['next_earnings'], '%Y-%m-%d')
                delta = (next_date - datetime.now()).days
                days_to_earnings = f"za {delta} dni" if delta >= 0 else f"{abs(delta)} dni temu"
            except Exception:
                pass

        cap_str = format_market_cap(data.get('market_cap', 0))
        news_section = "\n\n".join(data['news']) if data.get('news') else "Brak najnowszych wiadomości."

        google_link = f"https://www.google.com/search?q={ticker}+stock"

        output = (
            f"Spółka: [b][ref={google_link}][color=#0000FF]{comp_name}[/color][/ref][/b]\n"
            f"Sesja: {session_label}\n"
            f"Rekomendacja: {rec_text} | Sygnał: {trade_signal}\n"
            f"----------------------------------------------------\n"
            f"[b]📊 DANE RYNKOWE i WOLUMEN:[/b]\n"
            f"• Kurs sesji: [b]{p:.2f} USD[/b]\n"
            f"• Zmiana vs prev close: [b]{chg_amt:+.2f} USD | {chg_pct:+.2f}%[/b]\n"
            f"• Wolumen bieżący: {int(data.get('vol', 0)):,} Trend: ({vol_trend})\n"
            f"• Zakres dzienny 1D: {data.get('day_low', 0.0):.2f} - {data.get('day_high', 0.0):.2f} USD\n"
            f"• Zakres roczny 52W: {data.get('year_low', 0.0):.2f} - {data.get('year_high', 0.0):.2f} USD\n"
            f"----------------------------------------------------\n"
            f"[b]💰 FUNDAMENTY I WYCENA:[/b]\n"
            f"• Kapitalizacja rynkowa: [b]{cap_str}[/b]\n"
            f"• Wskaźnik P/E (Cena/Zysk): [b]{data['pe']}[/b]\n"
            f"• EPS (Zysk na akcję TTM): {data['eps']} | Dywidenda: {data.get('div_yield', 'N/A')}\n"
            f"----------------------------------------------------\n"
            f"[b]📆 WYNIKI FINANSOWE (EARNINGS):[/b]\n"
            f"• Następny raport: [b]{data['next_earnings']}[/b] ({days_to_earnings})\n"
            f"• Poprzedni ({data['prev_earnings_period']}): {data['prev_earnings_surprise']}\n"
            f"• Reakcja ceny po poprz. raporcie: {data['earnings_reaction']}\n"
            f"----------------------------------------------------\n"
            f"[b]📈 ANALIZA TECHNICZNA:[/b]\n"
            f"• SMA 14: {format_price_line(sma14, p)} | SMA 30: {format_price_line(sma30, p)} | SMA 50: {format_price_line(sma50, p)}\n"
            f"• SMA 90: {format_price_line(sma90, p)} | SMA 200: {format_price_line(sma200, p)}\n"
            f"• RSI (14): [color={color_for_rsi(rsi)}]{rsi:.1f}[/color] | MACD: [color={color_for_macd(macd, sig)}]{macd:.3f}[/color] (Sygnał: [color={color_for_macd(macd, sig)}]{sig:.3f}[/color])\n"
            f"• Histogram: {format_histogram(hist)}\n"
            f"----------------------------------------------------\n"
            f"[b]📰 NAJNOWSZE WIADOMOŚCI:[/b]\n{news_section}"
        )
        self.last_update_text = timestamp_text()
        output = f"[color=#888888]Ostatnia aktualizacja: {self.last_update_text}[/color]\n\n" + output
        Clock.schedule_once(lambda dt: self._msg(output, True))

    def _msg(self, txt, is_card=False):
        self.content.clear_widgets()
        if is_card: self.content.add_widget(DataCard(text=txt))
        else: self.content.add_widget(MDLabel(text=txt, halign="center"))



class KatalizatoryTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Katalizatory"
        super().__init__(**kw)
        self.control_panel.height = dp(55)
        button_layout = MDBoxLayout(orientation='horizontal', spacing=dp(10), pos_hint={"center_x": 0.5}, size_hint_x=None)
        button_layout.bind(minimum_width=button_layout.setter('width'))

        btn_refresh = MDRaisedButton(text="Pobierz Dane", on_release=self.refresh_data)
        button_layout.add_widget(btn_refresh)
        self.control_panel.add_widget(button_layout)
        self.last_notified_titles = []

    def get_category_tag(self, title):
        t = (title or "").lower()
        if is_fda_pdufa_title(t):
            return "FDA/PDUFA"
        if any(x in t for x in ['earnings', 'wyniki', 'raport', 'revenue', 'eps']):
            return "WYNIKI"
        if is_merger_mna_title(t):
            return "FUZJE/M&A"
        if is_contract_ai_title(t):
            if any(x in t for x in ["government", "govt", "federal", "state", "rząd", "public sector", "municipal"]):
                return "UMOWA/RZĄD"
            if any(x in t for x in ["ai", "artificial intelligence", "transform", "genai"]):
                return "AI / TRANSFORMACJA"
            return "DUŻA UMOWA"
        return None

    def get_catalyst_context(self, title):
        t = (title or "").lower()
        if is_fda_pdufa_title(t):
            return "Kontekst: decyzja regulacyjna FDA / PDUFA."
        if any(x in t for x in ['clinical', 'trial', 'phase', 'readout', 'topline']):
            return "Kontekst: wynik badania klinicznego / odczyt danych."
        if any(x in t for x in ['earnings', 'wyniki', 'raport', 'revenue', 'eps']):
            return "Kontekst: raport wynikowy / publikacja finansowa."
        if any(x in t for x in ['contract', 'agreement', 'deal', 'award', 'government', 'ai', 'transform']):
            return "Kontekst: kontrakt / umowa / transformacja AI."
        return ""

    def _unique_key(self, ticker, title, cat):
        title_key = re.sub(r"\s+", " ", (title or "").strip().lower())
        return f"{title_key}|{cat}"

    def _fetch(self, *args, **kwargs):
        is_auto = args[0] if (args and isinstance(args[0], bool)) else False
        now = datetime.now()

        days_back = 4 if now.weekday() >= 5 else 1
        yesterday_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=days_back)
        timestamp_threshold = int(yesterday_start.timestamp())

        start_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=10)).strftime("%Y-%m-%d")

        url_earnings = f"https://finnhub.io/api/v1/calendar/earnings?from={start_date}&to={end_date}&token={FINNHUB_KEY}"
        calendar_data = {(now + timedelta(days=i)).strftime("%Y-%m-%d"): {
            "label": f"{PL_DAYS.get((now + timedelta(days=i)).strftime('%A'), (now + timedelta(days=i)).strftime('%A')).upper()}, {(now + timedelta(days=i)).strftime('%d %B').upper()}",
            "raw_items": []
        } for i in range(7)}

        raw_news_entries = []
        extra_news_entries = []
        kat_tickers = []
        seen_pre = set()
        seen_official = set()
        seen_all = set()

        try:
            app = MDApp.get_running_app()
            watch_list = []
            if hasattr(app, 'tabs_instances'):
                skaner = next((t for t in app.tabs_instances if isinstance(t, SkanerTab)), None)
                if skaner:
                    watch_list = getattr(skaner, 'static_tickers', [])

            top_gainers = fetch_top_gainers_by_type("day_gainers")[:8]
            if top_gainers:
                kat_tickers.extend([tg for tg in top_gainers if tg not in kat_tickers])

            catalyst_queries = [
                "government contract OR contract award OR large contract OR major contract OR deal",
                "AI transformation OR artificial intelligence OR AI strategy OR generative AI OR transform",
                "partnership OR agreement OR collaboration OR strategic deal OR new contract",
            ]
            for q in catalyst_queries:
                res_news = safe_request(f"https://query2.finance.yahoo.com/v1/finance/search?q={q}&newsCount=12", headers=HEADERS, timeout=6)
                if res_news.status_code != 200:
                    continue
                for n in res_news.json().get("news", []):
                    pub_time = n.get('providerPublishTime', 0)
                    if pub_time < timestamp_threshold:
                        continue
                    title = n.get('title', '')
                    cat = self.get_category_tag(title)
                    if not cat:
                        continue
                    rel = n.get('relatedTickers', [])
                    ticker = rel[0] if rel else "RYNEK"
                    key = self._unique_key(ticker, title, cat)
                    if key in seen_all:
                        continue
                    seen_all.add(key)
                    if ticker != "RYNEK" and ticker not in kat_tickers:
                        kat_tickers.append(ticker)
                    if ticker != "RYNEK":
                        extra_news_entries.append({
                            'ticker': ticker, 'title': title, 'link': n.get('link', ''), 'cat': cat, 'context': self.get_catalyst_context(title)
                        })

            res_earn = safe_request(url_earnings, headers=HEADERS, timeout=6)
            if res_earn.status_code == 200:
                for item in res_earn.json().get('earningsCalendar', []):
                    date_str = item.get('date')
                    if date_str in calendar_data:
                        sym = item.get('symbol')
                        rev = item.get('revenueEstimate') or 0
                        if sym in watch_list or rev >= 250000000:
                            if sym not in kat_tickers:
                                kat_tickers.append(sym)
                            calendar_data[date_str]["raw_items"].append(item)

            search_query = "PDUFA OR FDA approval OR clinical trial OR earnings OR merger OR acquisition OR contract OR AI transformation"
            res_news = safe_request(f"https://query2.finance.yahoo.com/v1/finance/search?q={search_query}&newsCount=15", headers=HEADERS, timeout=6)
            if res_news.status_code == 200:
                for n in res_news.json().get("news", []):
                    pub_time = n.get('providerPublishTime', 0)
                    title = n.get('title', '')
                    cat = self.get_category_tag(title)
                    if not cat:
                        continue
                    is_calendar_article = any(k in title.lower() for k in ['calendar', 'upcoming', 'look ahead', 'catalyst', 'schedule'])
                    threshold = int((now - timedelta(days=14)).timestamp()) if is_calendar_article else timestamp_threshold
                    if pub_time < threshold:
                        continue
                    rel = n.get('relatedTickers', [])
                    ticker = rel[0] if rel else "RYNEK"
                    key = self._unique_key(ticker, title, cat)
                    if key in seen_all:
                        continue
                    seen_all.add(key)
                    if ticker not in kat_tickers and ticker != "RYNEK":
                        kat_tickers.append(ticker)
                    if is_auto and title not in self.last_notified_titles:
                        MDApp.get_running_app().send_notification(f"Katalizator: {ticker}", title)
                        self.last_notified_titles.append(title)
                    raw_news_entries.append({'ticker': ticker, 'title': title, 'link': n.get('link', ''), 'cat': cat, 'context': self.get_catalyst_context(title)})

            needed_tickers = [t for t in kat_tickers if t not in app.shared_cache]
            if needed_tickers:
                try:
                    new_bulk = fetch_bulk_ticker_data(needed_tickers)
                    add_cache_items(app, new_bulk, visible_symbols=kat_tickers)
                except Exception as e:
                    print(f"Katalizatory bulk error: {e}")

            micro_cap_news = []
            mna_cards = []
            for entry in raw_news_entries:
                ticker = entry['ticker']
                title = entry['title']
                link = entry['link']
                cat = entry['cat']
                catalyst_context = entry.get('context', self.get_catalyst_context(title))
                key = self._unique_key(ticker, title, cat)
                if key in seen_official:
                    continue
                seen_official.add(key)

                data = enrich_company_meta(ticker, app.shared_cache.get(ticker, {}))
                comp_name = normalize_company_name(ticker, data.get('name', ticker))
                cap_raw = data.get('market_cap', 0)
                cap_str = format_market_cap(cap_raw)
                display_ticker = f"{ticker} ({comp_name})" if comp_name and comp_name.upper() != ticker.upper() else ticker
                extra = f"\n{catalyst_context}" if catalyst_context else ""
                card_text = f"[color=#FF33CC][b][{cat}][/b][/color] [color=#008080][b]{display_ticker}[/b][/color]\nKapitalizacja rynkowa: [b]{cap_str}[/b]{extra}\n[ref={link}]{title}[/ref]"
                if cat == "FUZJE/M&A":
                    if card_text not in mna_cards:
                        mna_cards.append(card_text)
                    continue
                if card_text not in micro_cap_news:
                    micro_cap_news.append(card_text)

            pre_catalyst_cards = []
            for entry in extra_news_entries:
                ticker = entry['ticker']
                title = entry['title']
                cat = entry['cat']
                key = self._unique_key(ticker, title, cat)
                if key in seen_pre:
                    continue
                seen_pre.add(key)
                data = enrich_company_meta(ticker, app.shared_cache.get(ticker, {}))
                comp_name = normalize_company_name(ticker, data.get('name', ticker))
                cap_raw = data.get('market_cap', 0)
                cap_str = format_market_cap(cap_raw)
                display_ticker = f"{ticker} ({comp_name})" if comp_name and comp_name.upper() != ticker.upper() else ticker
                pre_catalyst_cards.append(
                    f"[color=#00FFCC][b]{entry['cat']}[/b][/color] [b]{display_ticker}[/b]\n"
                    f"Kapitalizacja: [b]{cap_str}[/b]\n"
                    f"[ref={entry['link']}]{title}[/ref]"
                )

            final_cal = {}
            for info in calendar_data.values():
                events_list = []
                for item in info["raw_items"]:
                    sym = item.get('symbol')
                    tag_color = "#0000FF" if sym in watch_list else "#00FFCC"
                    tag = "[WATCHLIST]" if sym in watch_list else "[MID/LARGE]"
                    data = enrich_company_meta(sym, app.shared_cache.get(sym, {}))
                    comp_name = normalize_company_name(sym, data.get('name', sym))
                    display_ticker = f"{sym} ({comp_name})" if comp_name and comp_name.upper() != sym.upper() else sym
                    cap_raw = data.get('market_cap', 0)
                    cap_str = format_market_cap(cap_raw)
                    ev = f"[color={tag_color}]{tag}[/color] [b][ref=https://finance.yahoo.com/quote/{sym}/]{display_ticker}[/ref][/b]\nKapitalizacja: {cap_str} | Prognoza EPS: {item.get('epsEstimate')}"
                    if ev not in events_list:
                        events_list.append(ev)
                final_cal[info["label"]] = events_list if events_list else ["Brak raportów."]

            self.last_update_text = timestamp_text()
            Clock.schedule_once(lambda dt: self._render(final_cal, micro_cap_news, pre_catalyst_cards, mna_cards))
        except Exception as e:
            print(f"Katalizatory error: {e}")

    def _render(self, calendar, micro_cap_news, pre_catalyst_cards, mna_cards):
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text=color_wrap(f"Ostatnia aktualizacja: {getattr(self, 'last_update_text', timestamp_text())}", "#888888"), markup=True, size_hint_y=None, height=dp(24), halign="left"))
        if mna_cards:
            self.content.add_widget(MDLabel(text="[b][color=#FF6666]🧩 POTENCJALNE PRZEJĘCIA / WYKUPY[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
            for card in mna_cards[:20]:
                self.content.add_widget(DataCard(text=card))
        if pre_catalyst_cards:
            self.content.add_widget(MDLabel(text="[b][color=#00FFFF]🧠 PRZED-KATALITYCZNE: UMOWY / AI / DUŻE KONTRAKTY[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
            for card in pre_catalyst_cards[:20]:
                self.content.add_widget(DataCard(text=card))
        if micro_cap_news:
            self.content.add_widget(MDLabel(text="[b][color=#FF33CC]🔥 OFICJALNE KATALIZATORY (WSTECZ & 7D W PRZÓD)[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
            for news in micro_cap_news:
                self.content.add_widget(DataCard(text=news))
        for day, events in calendar.items():
            self.content.add_widget(MDLabel(text=f"[b][color=#ff8c00]— KALENDARZ WYNIKÓW: {day} —[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
            for ev in events:
                self.content.add_widget(DataCard(text=ev))


class NewsTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Newsy"
        super().__init__(**kw)
        self.control_panel.height = dp(55)
        self.control_panel.add_widget(MDRaisedButton(text="Odśwież Wiadomości", on_release=self.refresh_data, pos_hint={"center_x": 0.5}))
        self._daily_items = []

    def _store_path(self):
        app = MDApp.get_running_app()
        return os.path.join(app.user_data_dir, "pr_news_store.json") if app else None

    def _load_daily_items(self):
        path = self._store_path()
        today = datetime.now().date().isoformat()
        if not path or not os.path.exists(path):
            self._daily_items = []
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("date") == today and isinstance(payload.get("items"), list):
                self._daily_items = payload["items"]
            else:
                self._daily_items = []
        except Exception:
            self._daily_items = []

    def _save_daily_items(self):
        path = self._store_path()
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump({"date": datetime.now().date().isoformat(), "items": self._daily_items[-40:]}, f, ensure_ascii=False)
        except Exception as e:
            print(f"News save error: {e}")

    def _pr_key(self, ticker, title):
        return f"{(ticker or 'RYNEK').strip().upper()}|{(title or '').strip().lower()}"

    def _is_pr_catalyst(self, title):
        return is_contract_ai_title(title) or is_fda_pdufa_title(title)

    def _append_unique(self, item):
        key = item.get("key")
        if not key:
            return False
        if any(existing.get("key") == key for existing in self._daily_items):
            return False
        self._daily_items.append(item)
        return True

    def _fetch(self, *args):
        app = MDApp.get_running_app()
        watch_list = []
        if hasattr(app, 'tabs_instances'):
            skaner = next((t for t in app.tabs_instances if isinstance(t, SkanerTab)), None)
            if skaner:
                watch_list = getattr(skaner, 'static_tickers', [])

        self._load_daily_items()
        now = datetime.now()
        yesterday_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        timestamp_threshold = int(yesterday_start.timestamp())

        new_notifications = []
        seen_new = set()

        def add_news(ticker, title, link, publisher, category, cap_raw=0, notify=False):
            if not title or not link:
                return
            key = self._pr_key(ticker, title)
            if key in seen_new:
                return
            seen_new.add(key)
            item = {
                "key": key,
                "ticker": ticker,
                "title": title,
                "link": link,
                "publisher": publisher,
                "category": category,
                "cap": safe_number(cap_raw, 0.0),
                "ts": int(time.time()),
            }
            if self._append_unique(item):
                new_notifications.append(item)
                if notify and (safe_number(cap_raw, 0.0) <= 2_000_000_000 or ticker in watch_list):
                    queued = queue_service_event(
                        "pr_news",
                        f"PR / Catalyst: {ticker}",
                        title,
                        key,
                        item,
                    )
                    if not queued:
                        try:
                            app.send_notification(f"PR / Catalyst: {ticker}", title)
                        except Exception as e:
                            print(f"PR notification error: {e}")

        # PR / watchlist news
        if watch_list:
            query = " OR ".join(watch_list[:12])
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&newsCount=20"
            try:
                res = safe_request(url, headers=HEADERS, timeout=8)
                if res.status_code == 200:
                    for n in res.json().get("news", []):
                        pub_time = n.get('providerPublishTime', 0)
                        if pub_time < timestamp_threshold:
                            continue
                        rel = n.get('relatedTickers', [])
                        ticker = rel[0] if rel else "RYNEK"
                        title = n.get('title', '')
                        link = n.get('link', '')
                        publisher = n.get('publisher', '')
                        cap_raw = app.shared_cache.get(ticker, {}).get('market_cap', 0) if ticker != "RYNEK" else 0
                        if ticker != "RYNEK" and self._is_pr_catalyst(title):
                            add_news(ticker, title, link, publisher, "PR / WATCHLIST", cap_raw, notify=True)
                        elif any(t in watch_list for t in rel):
                            add_news(ticker, title, link, publisher, "WATCHLIST", cap_raw, notify=False)
            except Exception as e:
                print(f"News watchlist error: {e}")

        # General market fallback + PR retention
        fallback_url = "https://query2.finance.yahoo.com/v1/finance/search?q=stocks market trading federal reserve economy&newsCount=20"
        try:
            res = safe_request(fallback_url, headers=HEADERS, timeout=6)
            if res.status_code == 200:
                for n in res.json().get("news", []):
                    pub_time = n.get('providerPublishTime', 0)
                    if pub_time < timestamp_threshold:
                        continue
                    rel = n.get('relatedTickers', [])
                    ticker = rel[0] if rel else "RYNEK"
                    title = n.get('title', '')
                    link = n.get('link', '')
                    publisher = n.get('publisher', '')
                    cap_raw = app.shared_cache.get(ticker, {}).get('market_cap', 0) if ticker != "RYNEK" else 0
                    if ticker != "RYNEK" and self._is_pr_catalyst(title):
                        add_news(ticker, title, link, publisher, "PR", cap_raw, notify=True)
                    elif ticker != "RYNEK":
                        add_news(ticker, title, link, publisher, "RYNEK", cap_raw, notify=False)
        except Exception as e:
            print(f"News fallback error: {e}")

        self._save_daily_items()
        self.last_update_text = timestamp_text()
        Clock.schedule_once(lambda dt: self._render_news())

    def _render_news(self):
        app = MDApp.get_running_app()
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text=color_wrap(f"Ostatnia aktualizacja: {getattr(self, 'last_update_text', timestamp_text())}", "#888888"), markup=True, size_hint_y=None, height=dp(24), halign="left"))
        self.content.add_widget(MDLabel(text="[b][color=#00FFFF]📰 AKTUALNOŚCI I NOWOŚCI RYNKOWE[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))

        # PR items stay visible until end of day
        pr_items = [x for x in self._daily_items if x.get("category", "").startswith("PR")]
        other_items = [x for x in self._daily_items if not x.get("category", "").startswith("PR")]

        if pr_items:
            self.content.add_widget(MDLabel(text="[b][color=#FF9900]PR / SMALL & MICRO CAP (do końca dnia)[/color][/b]", markup=True, size_hint_y=None, height=dp(34)))
            seen = set()
            for item in reversed(pr_items):
                key = item.get("key")
                if key in seen:
                    continue
                seen.add(key)
                ticker = item.get("ticker", "RYNEK")
                title = item.get("title", "")
                link = item.get("link", "")
                cap_raw = item.get("cap", 0)
                cap_str = format_market_cap(cap_raw)
                comp_name = normalize_company_name(ticker, app.shared_cache.get(ticker, {}).get('name', ticker)) if ticker != "RYNEK" else "RYNEK"
                display = f"{ticker} ({comp_name})" if ticker != "RYNEK" and comp_name and comp_name.upper() != ticker.upper() else ticker
                txt = f"[color=#00FFFF][b]{display}[/b][/color]\nKapitalizacja: [b]{cap_str}[/b]\n[ref={link}]{title}[/ref]"
                self.content.add_widget(DataCard(text=txt))

        if other_items:
            self.content.add_widget(MDLabel(text="[b][color=#888888]Pozostałe newsy[/color][/b]", markup=True, size_hint_y=None, height=dp(34)))
            seen = set()
            for item in reversed(other_items):
                key = item.get("key")
                if key in seen:
                    continue
                seen.add(key)
                ticker = item.get("ticker", "RYNEK")
                title = item.get("title", "")
                link = item.get("link", "")
                cap_raw = item.get("cap", 0)
                cap_str = format_market_cap(cap_raw)
                comp_name = normalize_company_name(ticker, app.shared_cache.get(ticker, {}).get('name', ticker)) if ticker != "RYNEK" else "RYNEK"
                display = f"{ticker} ({comp_name})" if ticker != "RYNEK" and comp_name and comp_name.upper() != ticker.upper() else ticker
                txt = f"[color=#FF9900][b]{display}[/b][/color]\nKapitalizacja: [b]{cap_str}[/b]\n[ref={link}]{title}[/ref]"
                self.content.add_widget(DataCard(text=txt))
class CfdShortTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "CFD/Własne"
        super().__init__(**kw)
        self.control_panel.height = dp(55)
        self._last_section_a_signature = None

        btn_refresh = MDRaisedButton(text="Analizuj CFD", on_release=lambda x: self.refresh_data(force=True), pos_hint={"center_x": 0.5})
        self.control_panel.add_widget(btn_refresh)

    def _screeners_universe(self):
        screeners = ["pre_market_gainers", "day_gainers", "after_hours_gainers", "most_actives", "day_losers", "trending_tickers"]
        tickers = []
        for scr in screeners:
            try:
                tickers.extend(fetch_top_gainers_by_type(scr)[:12])
            except Exception as e:
                print(f"screeners universe error {scr}: {e}")
        tickers.extend(["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "AVGO"])
        return list(dict.fromkeys(tickers))

    def _cfd_universe(self):
        return [
            "CL=F", "ZC=F", "SI=F", "GC=F", "CC=F", "BTC-USD", "NG=F", "HG=F",
            "DX-Y.NYB", "6E=F", "ES=F", "NQ=F", "YM=F", "RTY=F", "PA=F", "PL=F",
            "KC=F", "ZW=F", "ZR=F"
        ]

    def _fetch(self, *args, **kwargs):
        force = kwargs.get('force', False)
        app = MDApp.get_running_app()

        universe = self._screeners_universe()[:32]
        cfd_universe = self._cfd_universe()[:18]
        required = list(dict.fromkeys(universe + cfd_universe))
        is_cache_fresh = app.cache_time and (datetime.now() - app.cache_time).total_seconds() < 180 and not force

        if is_cache_fresh and all(sym in app.shared_cache for sym in required):
            bulk_data = {k: app.shared_cache[k] for k in required if k in app.shared_cache}
        else:
            bulk_data = fetch_bulk_ticker_data(required)
            add_cache_items(app, bulk_data, visible_symbols=required)

        a_candidates = []
        b_candidates = []
        c_candidates = []
        d_list = []

        for sym in required:
            data = app.shared_cache.get(sym)
            if not data or safe_number(data.get("price", 0.0), 0.0) <= 0:
                continue

            p = safe_number(data.get("price", 0.0), 0.0)
            closes = data.get("closes", [])
            if len(closes) < 10:
                continue

            comp_name = company_display(sym, data)
            vol = int(data.get("vol", 0) or 0)
            sma14 = calc_sma(closes, 14, p)
            sma30 = calc_sma(closes, 30, p)
            sma50 = calc_sma(closes, 50, p)
            sma90 = calc_sma(closes, 90, p)
            rsi = calculate_rsi(closes, 14)
            macd, sig, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
            hist = calculate_histogram(macd, sig)
            score, signal_text, signal_color = calculate_signal_strength(rsi, macd, sig, hist=hist, price=p, sma14=sma14, sma90=sma90)
            signal = color_wrap(f"[b]{signal_text}[/b]", signal_color)
            cap = safe_number(data.get("market_cap", 0), 0.0)

            if cap >= 50_000_000 and p >= 30 and rsi < 40 and macd > sig and hist > 0:
                a_score = (40 - rsi) + max(hist, 0) * 10 + (macd - sig) * 5 + (p / max(sma30, 1)) * 0.1
                a_candidates.append({
                    "sym": sym, "name": comp_name, "vol": vol, "p": p, "sma14": sma14, "sma30": sma30,
                    "rsi": rsi, "macd": macd, "sig": sig, "hist": hist, "signal": signal, "score": a_score
                })

            dist14 = sma14 - p
            if p < sma14 and dist14 > 1:
                b_score = dist14 + max(hist, 0) * 5 + max(0, 40 - rsi) * 0.2
                tp, sl = make_tp_sl(p, 0.03, 0.02)
                b_candidates.append({
                    "sym": sym, "name": comp_name, "vol": vol, "p": p, "sma14": sma14, "sma30": sma30,
                    "rsi": rsi, "macd": macd, "sig": sig, "hist": hist, "signal": signal, "score": b_score,
                    "tp": tp, "sl": sl
                })

            dist90 = sma90 - p
            if p < sma90 and dist90 > 1:
                c_score = dist90 + max(hist, 0) * 3 + max(0, 45 - rsi) * 0.1
                c_candidates.append({
                    "sym": sym, "name": comp_name, "vol": vol, "p": p, "sma14": sma14, "sma30": sma30,
                    "rsi": rsi, "macd": macd, "sig": sig, "hist": hist, "signal": signal, "score": c_score,
                    "dist": dist90
                })

        for sym in cfd_universe:
            data = app.shared_cache.get(sym)
            if not data or safe_number(data.get("price", 0.0), 0.0) <= 0:
                continue
            p = safe_number(data.get("price", 0.0), 0.0)
            closes = data.get("closes", [])
            if len(closes) < 10:
                continue
            comp_name = company_display(sym, data)
            vol = int(data.get("vol", 0) or 0)
            sma14 = calc_sma(closes, 14, p)
            sma30 = calc_sma(closes, 30, p)
            sma90 = calc_sma(closes, 90, p)
            rsi = calculate_rsi(closes, 14)
            macd, sig, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
            hist = calculate_histogram(macd, sig)
            diff = abs(p - sma90)
            if diff <= 1:
                continue
            score, signal_text, signal_color = calculate_signal_strength(rsi, macd, sig, hist=hist, price=p, sma14=sma14, sma90=sma90)
            tp, sl = make_tp_sl(p, 0.03, 0.02)
            d_list.append({
                "sym": sym, "name": comp_name, "vol": vol, "p": p, "sma14": sma14, "sma30": sma30, "sma90": sma90,
                "rsi": rsi, "macd": macd, "sig": sig, "hist": hist, "signal": color_wrap(f"[b]{signal_text}[/b]", signal_color),
                "score": score, "tp": tp, "sl": sl, "diff": diff
            })

        a_candidates.sort(key=lambda x: x["score"], reverse=True)
        b_candidates.sort(key=lambda x: x["score"], reverse=True)
        c_candidates.sort(key=lambda x: x["dist"], reverse=True)
        d_list.sort(key=lambda x: x["score"], reverse=True)

        signature = tuple(x["sym"] for x in a_candidates[:10])
        if signature and signature != self._last_section_a_signature:
            self._last_section_a_signature = signature
            try:
                title = "CFD/Własne - Sekcja A"
                message = f"Znaleziono {len(signature)} spółek spełniających warunki."
                queue_service_event(
                    "cfd_alarm",
                    title,
                    message,
                    f"{title}|{len(signature)}|{'|'.join(signature[:5])}",
                    {"symbols": list(signature), "count": len(signature)},
                )
                MDApp.get_running_app().send_notification(title, message)
            except Exception as e:
                print(f"Notification error: {e}")

        def suggestion_from_group(rows):
            if not rows:
                return "Brak danych"
            avg = sum(r["score"] for r in rows) / len(rows)
            if avg >= 4.5:
                return "MOCNE KUP"
            if avg >= 2.0:
                return "KUP"
            if avg >= 0.0:
                return "TRZYMAJ"
            if avg >= -2.0:
                return "SPRZEDAJ"
            return "MOCNE SPRZEDAJ"

        def format_row(row, show_tp_sl=False, show_diff=False):
            p = row["p"]
            vol = row["vol"]
            name = row["name"]
            sma14 = row.get("sma14", p)
            sma30 = row.get("sma30", p)
            sma90 = row.get("sma90", p)
            rsi = row["rsi"]
            macd = row["macd"]
            sig = row["sig"]
            hist = row["hist"]

            lines = [
                f"[b]{name}[/b]",
                f"Ticker: [b]{row['sym']}[/b] | Wolumen: {vol:,} | Cena: [b]{p:.2f}[/b]",
                f"SMA14: {format_price_line(sma14, p)} | SMA30: {format_price_line(sma30, p)}",
                f"RSI: [color={color_for_rsi(rsi)}]{rsi:.1f}[/color] | MACD: [color={color_for_macd(macd, sig)}]{macd:.3f}[/color] | Histogram: {format_histogram(hist)}",
                f"Sygnał: {row['signal']}",
            ]
            if show_diff:
                lines.append(f"SMA90: {format_price_line(sma90, p)} | Różnica: [b]{row['diff']:.2f}[/b]")
            if show_tp_sl:
                lines.append(f"TP: [color=#00AA00]{row['tp']:.2f}[/color] | SL: [color=#FF3333]{row['sl']:.2f}[/color]")
            return "\n".join(lines)

        sec_a = [f"{format_row(r)}" for r in a_candidates[:10]]
        sec_b = [f"{format_row(r, show_tp_sl=True)}" for r in b_candidates[:10]]
        sec_c = [f"{format_row(r, show_diff=True)}" for r in c_candidates[:10]]
        sec_d = [f"{format_row(r, show_tp_sl=True)}" for r in d_list[:12]]

        if not sec_a:
            sec_a = ["Brak spółek spełniających warunki."]
        if not sec_b:
            sec_b = ["Brak spółek poniżej SMA14."]
        if not sec_c:
            sec_c = ["Brak spółek poniżej SMA90."]
        if not sec_d:
            sec_d = ["Brak danych CFD."]

        summary_a = suggestion_from_group(a_candidates[:10])
        summary_b = suggestion_from_group(b_candidates[:10])
        summary_c = suggestion_from_group(c_candidates[:10])
        summary_d = suggestion_from_group(d_list[:10])

        payload = {
            f"A: DYNAMICZNE BREAKOUTY | OSTATECZNA SUGESTIA: {summary_a}": sec_a,
            f"B: WYBICIE PONIŻEJ SMA14 | OSTATECZNA SUGESTIA: {summary_b}": sec_b,
            f"C: PONIŻEJ SMA90 | OSTATECZNA SUGESTIA: {summary_c}": sec_c,
            f"D: CFD | OSTATECZNA SUGESTIA: {summary_d}": sec_d,
        }
        self.last_update_text = timestamp_text()
        Clock.schedule_once(lambda dt: self._render(payload))

    def _render(self, payload):
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text=color_wrap(f"Ostatnia aktualizacja: {getattr(self, 'last_update_text', timestamp_text())}", "#888888"), markup=True, size_hint_y=None, height=dp(24), halign="left"))
        headers_colors = {"A": "#008080", "B": "#00FFCC", "C": "#ff8c00", "D": "#FF6666"}
        for sec_name, items in payload.items():
            color = headers_colors.get(sec_name[0], "#ff8c00")
            self.content.add_widget(MDLabel(text=f"[color={color}][b]SEKCJA {sec_name}[/b][/color]", markup=True, size_hint_y=None, height=dp(40)))
            for item in items:
                self.content.add_widget(DataCard(text=item))

class StockScannerPro(MDApp):
    def build(self):
        self.shared_cache = {}
        self.cache_time = None
        self.app_ready = False
        self._scheduler_started = False
        self._scheduler_running = False
        self._scheduled_slots = set()
        self._scheduler_lock = threading.Lock()
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Teal"

        screen = MDScreen()
        self.tabs_container = MDTabs()
        self.tabs_container.bind(on_tab_switch=self.on_tab_switch)
        screen.add_widget(self.tabs_container)
        self.tabs_instances = []
        return screen

    def on_start(self):
        try:
            if platform == 'android':
                request_permissions(["android.permission.POST_NOTIFICATIONS"])
        except Exception as e:
            print(f"Błąd przy żądaniu uprawnień: {e}")

        init_service_bridge()
        start_foreground_service()
        Clock.schedule_once(self.init_tabs_delayed, 0)

    def init_tabs_delayed(self, dt):
        self.tabs_instances = [InfoTab(), SkanerTab(), TickerTab(), KatalizatoryTab(), NewsTab(), CfdShortTab()]
        for tab in self.tabs_instances:
            self.tabs_container.add_widget(tab)

        if hasattr(self.tabs_instances[1], 'load_stored_data'):
            self.tabs_instances[1].load_stored_data()
        if hasattr(self.tabs_instances[5], 'load_stored_data'):
            self.tabs_instances[5].load_stored_data()

        self.app_ready = True
        Clock.schedule_once(lambda dt: self.tabs_instances[1].load_data_if_needed(), 0.5)
        self._start_background_scheduler()

    def _start_background_scheduler(self):
        if self._scheduler_started:
            return
        self._scheduler_started = True
        self._scheduler_running = True
        threading.Thread(target=self._scheduler_loop, daemon=True).start()
        if not IS_GITHUB:
            Clock.schedule_interval(self.cron_time_checker, 30)

    def _scheduler_loop(self):
        while self._scheduler_running:
            try:
                self.cron_time_checker(0)
            except Exception as e:
                print(f"Scheduler loop error: {e}")
            time.sleep(30)

    def _find_tab(self, cls):
        for tab in getattr(self, 'tabs_instances', []):
            if isinstance(tab, cls):
                return tab
        return None

    def _maybe_fire_scheduled_updates(self):
        now = datetime.now()
        if now.weekday() >= 5:
            return
        if now.hour not in [11, 13, 15] or now.minute > 4:
            return
        slot = now.strftime('%Y-%m-%d %H')
        with self._scheduler_lock:
            if slot in self._scheduled_slots:
                return
            self._scheduled_slots.add(slot)

        kat = self._find_tab(KatalizatoryTab)
        news = self._find_tab(NewsTab)

        def _do_refresh(_dt):
            try:
                if kat:
                    kat.refresh_data(True)
            except Exception as e:
                print(f"Scheduled katalizatory refresh error: {e}")
            try:
                if news:
                    news.refresh_data()
            except Exception as e:
                print(f"Scheduled news refresh error: {e}")

        Clock.schedule_once(_do_refresh, 0)

    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if not getattr(self, 'app_ready', False):
            return
        if hasattr(instance_tab, 'load_data_if_needed'):
            instance_tab.load_data_if_needed()

    def background_prefetch(self, dt):
        return

    def on_pause(self):
        return True

    def on_resume(self):
        self._maybe_fire_scheduled_updates()
        return True

    def cron_time_checker(self, dt):
        self._maybe_fire_scheduled_updates()

    def send_notification(self, title, message):
        try:
            if notification:
                notification.notify(title=title, message=message, app_name='StockScanner', timeout=10)
        except Exception as e:
            print(f"Błąd powiadomienia Plyer: {e}")

        try:
            Clock.schedule_once(lambda dt: MDSnackbar(
                MDLabel(text=f"🔔 [b]{title}:[/b] {message}", theme_text_color="Custom", text_color=[1, 1, 1, 1], markup=True),
                background_color=[0, 0.4, 0.4, 1], duration=5
            ).open())
        except Exception as ex:
            print(f"Błąd paska Snackbar: {ex}")

if __name__ == '__main__':
    StockScannerPro().run()
