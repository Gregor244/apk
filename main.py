# =========================================
# STOCK SCANNER PRO - V7 HYBRID ENGINE (UPDATED)
# =========================================

import asyncio
import re
import threading
import time
import webbrowser
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from urllib.parse import quote_plus

import certifi
import httpx

from kivy.config import Config
Config.set("graphics", "multisamples", "0")
Config.set("kivy", "maxfps", "60")

from kivy.clock import Clock, mainthread
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

NASDAQ_CORE = ["AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA", "AMD", "PLTR", "NFLX", "AVGO", "ORCL", "COST", "QCOM", "MU"]
GPW_CORE = ["CDR.WA", "PKO.WA", "PEO.WA", "PZU.WA", "PKN.WA", "DNP.WA", "LPP.WA", "ALE.WA", "JSW.WA", "KGH.WA", "MBK.WA", "SPL.WA", "BHW.WA", "CCC.WA"]

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
        try: coro.close()
        except Exception: pass
        return None
    return asyncio.run_coroutine_threadsafe(coro, ASYNC_LOOP)

# =========================================
# HELPERS
# =========================================

def safe(v, d=0.0):
    try: return float(v) if v is not None else d
    except Exception: return d

def safe_list(data):
    return [safe(x) for x in data if x is not None]

def fmt_num(value, digits=2, signed=False):
    v = safe(value, 0.0)
    return f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"

def fmt_change(change, pct):
    change = safe(change, 0.0)
    pct = safe(pct, 0.0)
    color = "#00AA00" if change >= 0 else "#FF0000"
    return color_wrap(f"{change:+.2f} USD | {pct:+.2f}%", color)

def schedule_ui(callback, *args, **kwargs):
    Clock.schedule_once(lambda dt: callback(*args, **kwargs), 0)
def color_wrap(text, color):
    return f"[color={color}]{text}[/color]"

def format_cap(v):
    v = safe(v)
    if v >= 1_000_000_000_000: return f"{v/1_000_000_000_000:.2f} T"
    if v >= 1_000_000_000: return f"{v/1_000_000_000:.2f} B"
    if v >= 1_000_000: return f"{v/1_000_000:.2f} M"
    return f"{v:.2f}"

LOCAL_TZ = ZoneInfo("Europe/Warsaw")
NY_TZ = ZoneInfo("America/New_York")

def timestamp_text():
    return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def local_time_text():
    return datetime.now(LOCAL_TZ).strftime("%d.%m.%Y %H:%M:%S %Z")

def next_us_market_open_text(now=None):
    try: now_ny = (now.astimezone(NY_TZ) if getattr(now, "tzinfo", None) else datetime.now(NY_TZ))
    except Exception: now_ny = datetime.now(NY_TZ)

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

def market_status():
    ny = datetime.now(NY_TZ)
    if ny.weekday() >= 5: return "ZAMKNIĘTY"
    h = ny.hour + ny.minute / 60
    if 4 <= h < 9.5: return "PREMARKET"
    if 9.5 <= h < 16: return "OTWARTY"
    if 16 <= h < 20: return "POSTMARKET"
    return "ZAMKNIĘTY"

def normalize_company_name(symbol, name=None):
    symbol = (symbol or "").strip().upper()
    cleaned = (name or "").strip()
    fallback = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "TSLA": "Tesla"}
    if cleaned and cleaned.upper() != symbol: return cleaned
    return fallback.get(symbol.replace(".WA", "").replace(".PL", ""), cleaned or symbol)

def search_url_from_query(query):
    return f"https://www.google.com/search?q={quote_plus(query)}"

def safe_json(response):
    try: return response.json() if getattr(response, "status_code", 0) == 200 else {}
    except Exception: return {}

def make_tp_sl(price, tp_pct=0.03, sl_pct=0.02):
    price = safe(price, 0.0)
    return price * (1 + tp_pct), price * (1 - sl_pct)

def build_full_glossary():
    return (
        "[b]SŁOWNIK WSKAŹNIKÓW I POJĘĆ[/b]\n"
        "• [b]SMA[/b] — Średnia krocząca; pokazuje główny kierunek trendu.\n"
        "• [b]RSI[/b] — Mierzy 'przegrzanie' rynku (0–100). Poniżej 30 to wyprzedanie (szansa na odbicie), powyżej 70 to wykupienie.\n"
        "• [b]MACD & Hist[/b] — Pokazuje dynamikę (momentum). Jeśli Histogram rośnie, trend przyspiesza.\n"
        "• [b]TP / SL[/b] — Take Profit (realizacja zysku) i Stop Loss (cięcie strat).\n"
        "• [b]Pre/Post-Market[/b] — Handel poza główną sesją (często bardziej ryzykowny).\n\n"
        "[b]ZAAWANSOWANE WSKAŹNIKI V7 (Przetłumaczone)[/b]\n"
        "• [b]Faza Rynku (Regime)[/b] — Czy jesteśmy w trendzie wzrostowym (TREND_UP), spadkowym (TREND_DOWN), stabilizacji (RANGE) czy akumulacji (ACCUMULATION).\n"
        "• [b]Moment Wejścia (Timing)[/b] — Czy to dobry moment na zakup? OPTIMAL_ENTRY oznacza idealne zgranie wskaźników.\n"
        "• [b]Szansa Ruchu (Probability)[/b] — Prawdopodobieństwo (w %), że rynek ruszy w kierunku sugerowanym przez sygnał.\n"
        "• [b]Pewność (Confidence)[/b] — Jak silny jest dany sygnał na podstawie wolumenu i dynamiki (0-100%).\n"
        "• [b]Ryzyko wahań (Volatility)[/b] — Jak bardzo cena może 'skakać'. Powyżej 4-5% oznacza rynek bardzo niespokojny."
    )

# Zabezpieczające metody tekstowe dla zakładki Katalizatory
def is_fda_pdufa_title(t):
    return any(x in t for x in ["fda", "pdufa", "adcom", "advisory committee", "crl", "clinical", "trial", "readout", "topline", "approval", "approved", "complete response letter", "nda", "bla", "panel"])

def is_merger_mna_title(t):
    return any(x in t for x in ["merger", "acquisition", "takeover", "buyout", "sale", "private"])

def is_buyout_interest_title(t):
    return any(x in t for x in ["interest", "exploring", "strategic alternatives"])

def is_contract_ai_title(t):
    return any(x in t for x in ["contract", "ai", "artificial intelligence", "deal", "partnership"])

# =========================================
# INDICATORS & MATH
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
    ema12, ema26 = ema(closes, 12), ema(closes, 26)
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
    avg_gain, avg_loss = sum(gains[:period]) / period, sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0: return 100.0
    return round(100.0 - (100.0 / (1.0 + (avg_gain / avg_loss))), 2)

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

# =========================================
# V7 ENGINE LOGIC
# =========================================

def normalize_volumes(volumes):
    vols = safe_list(volumes)
    if not vols: return []
    avg = sum(vols) / len(vols)
    return [avg * 3 if v > avg * 10 else v for v in vols]

def order_flow_pressure(closes, volumes):
    if len(closes) < 2 or len(volumes) < 2: return 0.0
    flow, total_vol = 0.0, 0.0
    for i in range(1, len(closes)):
        delta = closes[i] - closes[i-1]
        flow += delta * volumes[i]
        total_vol += volumes[i]
    if total_vol == 0: return 0.0
    return flow / (closes[-1] * total_vol)

def volatility_forecast(closes):
    if len(closes) < 2: return 0.0
    pct_changes = [(closes[i] - closes[i-1]) / closes[i-1] for i in range(1, len(closes)) if closes[i-1] > 0]
    if not pct_changes: return 0.0
    mean = sum(pct_changes) / len(pct_changes)
    var = sum((x - mean)**2 for x in pct_changes) / len(pct_changes)
    return var ** 0.5

def probability_of_move(rsi, macd_hist, pct, flow, regime):
    prob = 50.0
    if regime == "Trend wzrostowy (UP)": prob += 15
    elif regime == "Trend spadkowy (DOWN)": prob -= 15
    if macd_hist > 0: prob += 10
    else: prob -= 10
    if rsi < 40: prob += 10
    elif rsi > 60: prob -= 10
    if flow > 0: prob += 5
    return max(0.0, min(100.0, prob))

def better_regime(rsi, hist, pct, volatility, flow):
    score = 1 if pct > 0 else -1
    score += 1 if hist > 0 else -1
    score += 1 if flow > 0 else -1

    if volatility > 0.04: return "Wysokie wahania (VOLATILE)"
    if rsi > 65 and score > 0: return "Trend wzrostowy (UP)"
    if rsi < 35 and score < 0: return "Trend spadkowy (DOWN)"
    if abs(score) <= 1: return "Stabilizacja (RANGE)"
    return "Faza przejściowa (TRANSITION)"

def entry_timing_optimizer(rsi, hist, flow, volatility):
    score = 1 if hist > 0 else -1
    score += 1 if flow > 0.2 else -1 if flow < -0.2 else 0
    if 45 <= rsi <= 60: score += 1
    elif rsi > 70 or rsi < 30: score -= 1
    if volatility > 0.05: score -= 2
    
    if score >= 2: return "IDEALNY_MOMENT"
    if score <= -2: return "CZEKAJ"
    return "NEUTRALNY"

def calibrated_confidence(prob, regime, flow, volatility):
    base = abs(prob - 50) * 2
    if regime in ("Trend wzrostowy (UP)", "Trend spadkowy (DOWN)"): base *= 1.15
    elif regime == "Stabilizacja (RANGE)": base *= 0.85
    if abs(flow) > 0.5: base *= 1.2
    elif abs(flow) < 0.1: base *= 0.8
    if volatility > 0.04: base *= 0.75
    return max(0, min(100, round(base, 2)))

def position_size(confidence, volatility, capital):
    if confidence < 30 or volatility > 0.1: return 0.0
    risk_pct = 0.02
    size = capital * risk_pct * (confidence / 100) / max(0.01, volatility)
    return round(min(size, capital), 2)

def trading_signal(prob, config=None):
    if prob > 65: return "KUPUJ"
    if prob < 35: return "SPRZEDAJ"
    return "TRZYMAJ"

def analyze_v7(closes, volumes, current_price, prev_close):
    closes = safe_list(closes)
    volumes = normalize_volumes(volumes)
    cp = safe(current_price, 0.0)

    # Anchor change strictly to the last close.
    pc = safe(prev_close, 0.0)
    if pc <= 0 and len(closes) >= 2:
        pc = safe(closes[-2], 0.0)
    if pc <= 0 and len(closes) >= 1:
        pc = safe(closes[-1], 0.0)

    rsi_val = calc_rsi(closes)
    macd_val, signal_val, hist = macd(closes)

    diff = cp - pc
    pct = ((diff) / pc * 100) if pc > 0 else 0.0

    flow = order_flow_pressure(closes, volumes)
    volat = volatility_forecast(closes)
    regime = better_regime(rsi_val, hist, pct, volat, flow)
    prob = probability_of_move(rsi_val, hist, pct, flow, regime)
    conf = calibrated_confidence(prob, regime, flow, volat)
    raw_sig = trading_signal(prob)
    timing = entry_timing_optimizer(rsi_val, hist, flow, volat)
    pos_size = position_size(conf, volat, 10000)
    
    sig_color = "#00AA00" if raw_sig == "KUPUJ" else "#FF0000" if raw_sig == "SPRZEDAJ" else "#888888"

    return {
        "price": cp, "prev_close": pc, "diff": diff, "pct": pct,
        "rsi": rsi_val, "macd": macd_val, "sig": signal_val, "hist": hist,
        "sma14": sma(closes, 14), "sma30": sma(closes, 30), "sma90": sma(closes, 90),
        "flow": flow, "volatility": volat, "regime": regime, "prob": prob,
        "confidence": conf, "signal": raw_sig, "signal_color": sig_color,
        "timing": timing, "position_size": pos_size
    }

# =========================================
# HTTP & DATA FETCHING
# =========================================

async def safe_request_async(url, timeout=8, retries=MAX_RETRIES):
    host = url.split("/")[2] if "://" in url else "default"
    for i in range(retries):
        async with RATE_LIMIT_LOCK:
            now = time.time()
            diff = now - LAST_REQUEST_TIME.get(host, 0)
            if diff < REQUEST_DELAY: await asyncio.sleep(REQUEST_DELAY - diff)
            LAST_REQUEST_TIME[host] = time.time()
        try:
            response = await HTTP_CLIENT.get(url, timeout=timeout)
            if response.status_code in (200, 404): return response
            if response.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(1.1 * (i + 1))
                continue
            return response
        except Exception:
            await asyncio.sleep(0.8 * (i + 1))
    class Dummy: status_code = 0; json = lambda self: {}
    return Dummy()

def _extract_chart_payload(yahoo_json):
    result = yahoo_json.get("chart", {}).get("result", [])
    if not result:
        return {}, {}
    return result[0], result[0].get("indicators", {}).get("quote", [{}])[0]

def _extract_intraday_session_prices(chart_payload, chart_quote):
    """Return last observed prices for pre/regular/post session from 1m candles."""
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


def _select_active_price(session_state, prev_close, pre_price, regular_price, post_price, last_trade, quote_price=0.0):
    pc = safe(prev_close, 0.0)
    pre = safe(pre_price, 0.0)
    reg = safe(regular_price, 0.0)
    post = safe(post_price, 0.0)
    last = safe(last_trade, 0.0)
    quote = safe(quote_price, 0.0)

    if session_state == "PREMARKET":
        return pre or quote or last or reg or pc
    if session_state == "POSTMARKET":
        return post or quote or last or reg or pc
    if session_state == "OTWARTY":
        return quote or last or reg or pc

    return quote or last or reg or pre or post or pc


def _session_anchor_close(session_state, closes, chart_prev_close=0.0, quote_prev_close=0.0):
    closes = safe_list(closes)
    chart_prev_close = safe(chart_prev_close, 0.0)
    quote_prev_close = safe(quote_prev_close, 0.0)

    # Deterministic anchoring:
    # - OTWARTY -> previous daily close (closes[-2])
    # - PRE/POST -> latest close (closes[-1])
    # - only if closes are unavailable use chart/quote fallback
    if session_state == "OTWARTY":
        if len(closes) >= 2:
            return safe(closes[-2], 0.0), "closes[-2]"
        if closes:
            return safe(closes[-1], 0.0), "closes[-1]"
        if chart_prev_close > 0:
            return chart_prev_close, "chart_prev_close"
        if quote_prev_close > 0:
            return quote_prev_close, "quote_prev_close"
        return 0.0, "missing"

    if session_state in ("PREMARKET", "POSTMARKET"):
        if closes:
            return safe(closes[-1], 0.0), "closes[-1]"
        if chart_prev_close > 0:
            return chart_prev_close, "chart_prev_close"
        if quote_prev_close > 0:
            return quote_prev_close, "quote_prev_close"
        return 0.0, "missing"

    if chart_prev_close > 0:
        return chart_prev_close, "chart_prev_close"
    if quote_prev_close > 0:
        return quote_prev_close, "quote_prev_close"
    if len(closes) >= 2:
        return safe(closes[-2], 0.0), "closes[-2]"
    if closes:
        return safe(closes[-1], 0.0), "closes[-1]"
    return 0.0, "missing"

async def fetch_top_gainers_by_type_async(scr_id="day_gainers"):
    cache_key = ("screener", scr_id)
    with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (time.time() - cached.get("ts", 0)) < REQUEST_CACHE_TTL["screener"]:
            return list(cached.get("data", []))
    url = f"https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds={scr_id}&count=15"
    res = await safe_request_async(url, timeout=6)
    if res.status_code == 200:
        result = safe_json(res).get("finance", {}).get("result")
        if result and isinstance(result, list):
            symbols = [q["symbol"] for q in result[0].get("quotes", []) if "symbol" in q]
            with REQUEST_CACHE_LOCK: REQUEST_CACHE[cache_key] = {"ts": time.time(), "data": symbols}
            return symbols
    return []

async def fetch_dynamic_universe_async(limit=60):
    screeners = ["day_gainers", "most_actives", "day_losers"]
    results = await asyncio.gather(*[fetch_top_gainers_by_type_async(s) for s in screeners], return_exceptions=True)
    tickers = []
    for res in results:
        if isinstance(res, list): tickers.extend(res[:10])
    tickers.extend(NASDAQ_CORE + GPW_CORE)
    return list(dict.fromkeys(tickers))[:max(1, int(limit))]

async def fetch_company_names(symbols):
    unique = list(dict.fromkeys([s for s in [str(x).strip().upper() for x in symbols if x] if s]))
    async def _one(sym): return sym, normalize_company_name(sym, sym)
    results = await asyncio.gather(*[_one(sym) for sym in unique], return_exceptions=True)
    return {sym: name for item in results if not isinstance(item, Exception) for sym, name in [item]}

def get_catalyst_context(title):
    t = (title or "").lower()
    if is_fda_pdufa_title(t): return "Kontekst: decyzja regulacyjna FDA / PDUFA."
    if is_merger_mna_title(t): return "Kontekst: potencjalne przejęcie / wykup / M&A."
    if is_buyout_interest_title(t): return "Kontekst: rosnące zainteresowanie wykupem firmy."
    if any(x in t for x in ["clinical", "trial", "phase", "readout", "topline"]): return "Kontekst: wynik badania klinicznego / odczyt danych."
    if any(x in t for x in ["earnings", "wyniki", "raport", "revenue", "eps", "guidance", "beat", "miss"]): return "Kontekst: raport wynikowy / publikacja finansowa."
    if any(x in t for x in ["contract", "agreement", "deal", "award", "government", "ai", "transform"]): return "Kontekst: kontrakt / umowa / transformacja AI."
    return ""

def get_category_tag(title):
    t = (title or "").lower()
    if is_fda_pdufa_title(t): return "FDA/PDUFA"
    if is_merger_mna_title(t): return "WYKUP / M&A"
    if is_buyout_interest_title(t): return "ZAINTERESOWANIE WYKUPEM"
    if is_contract_ai_title(t):
        if any(x in t for x in ["government", "govt", "federal", "state", "rząd", "public sector", "municipal"]): return "UMOWA / RZĄD"
        if any(x in t for x in ["ai", "artificial intelligence", "transform", "genai"]): return "AI / TRANSFORMACJA"
        return "DUŻA UMOWA"
    if any(x in t for x in ["earnings", "wyniki", "raport", "revenue", "eps", "guidance", "beat", "miss"]): return "WYNIKI"
    return None

async def fetch_earnings():
    today = datetime.now().strftime("%Y-%m-%d")
    end = (datetime.now() + timedelta(days=7)).strftime("%Y-%m-%d")
    url = f"https://finnhub.io/api/v1/calendar/earnings?from={today}&to={end}&token={FINNHUB_KEY}"
    data = await safe_request_async(url, timeout=8)
    payload = safe_json(data)
    return payload.get("earningsCalendar", []) if isinstance(payload, dict) else []

async def fetch_prev_earnings_reaction(symbol):
    try:
        earnings_url = f"https://finnhub.io/api/v1/stock/earnings?symbol={symbol}&token={FINNHUB_KEY}"
        res = await safe_request_async(earnings_url, timeout=8)
        if res.status_code != 200: return "Brak danych"
        payload = safe_json(res)
        earnings_list = payload.get("earnings", []) if isinstance(payload, dict) else payload if isinstance(payload, list) else []
        if not earnings_list: return "Brak danych"
        latest = earnings_list[0]
        period = latest.get("period") or latest.get("date")
        if not period: return "Brak danych"
        try: e_date = datetime.strptime(period[:10], "%Y-%m-%d").date()
        except Exception: return "Brak danych"
        
        start_ts = int(datetime.combine(e_date - timedelta(days=2), datetime.min.time()).timestamp())
        end_ts = int(datetime.combine(e_date + timedelta(days=4), datetime.min.time()).timestamp())
        react_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?period1={start_ts}&period2={end_ts}&interval=1d"
        react_req = await safe_request_async(react_url, timeout=8)
        if react_req.status_code != 200: return "Brak danych"
        _, react_quote = _extract_chart_payload(safe_json(react_req))
        react_closes = [c for c in react_quote.get("close", []) if c is not None]
        if len(react_closes) < 2 or not react_closes[0]: return "Brak danych"
        r_pct = ((react_closes[-1] - react_closes[0]) / react_closes[0]) * 100
        return f"[b][color={'#00AA00' if r_pct > 0 else '#FF0000'}]{r_pct:+.2f}%[/color][/b]"
    except Exception:
        return "Brak danych"


async def fetch_ticker(symbol):
    symbol = (symbol or "").strip().upper()
    if not symbol:
        return None

    yahoo_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1y"
    intraday_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1m&range=1d&includePrePost=true"
    quote_url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
    profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={FINNHUB_KEY}"
    metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={symbol}&metric=all&token={FINNHUB_KEY}"
    earnings_cal_url = f"https://finnhub.io/api/v1/calendar/earnings?symbol={symbol}&from={(datetime.now()).strftime('%Y-%m-%d')}&to={(datetime.now()+timedelta(days=90)).strftime('%Y-%m-%d')}&token={FINNHUB_KEY}"

    yahoo_res, intraday_res, quote_res, profile_res, metrics_res, earnings_cal_res = await asyncio.gather(
        safe_request_async(yahoo_url, timeout=8),
        safe_request_async(intraday_url, timeout=8),
        safe_request_async(quote_url, timeout=6),
        safe_request_async(profile_url, timeout=6),
        safe_request_async(metrics_url, timeout=6),
        safe_request_async(earnings_cal_url, timeout=6),
    )

    closes, volumes = [], []
    chart_meta = {}
    if getattr(yahoo_res, "status_code", 0) == 200:
        payload, quote = _extract_chart_payload(safe_json(yahoo_res))
        chart_meta = payload.get("meta", {})
        closes = [x for x in quote.get("close", []) if x is not None]
        volumes = [x for x in quote.get("volume", []) if x is not None]

    quote_payload = safe_json(quote_res) if getattr(quote_res, "status_code", 0) == 200 else {}
    fh_q = quote_payload.get("quoteResponse", {}).get("result", []) or []
    fh_q = fh_q[0] if fh_q else {}

    profile = safe_json(profile_res) if getattr(profile_res, "status_code", 0) == 200 else {}
    metrics = safe_json(metrics_res) if getattr(metrics_res, "status_code", 0) == 200 else {}
    earnings_data = safe_json(earnings_cal_res) if getattr(earnings_cal_res, "status_code", 0) == 200 else {}

    session_state = market_status()
    raw_state = ""
    pre_p = post_p = reg_p = last_trade = 0.0

    quote_price = safe(fh_q.get("regularMarketPrice", 0.0))
    quote_prev_close = safe(fh_q.get("regularMarketPreviousClose", 0.0))

    if getattr(intraday_res, "status_code", 0) == 200:
        i_payload, i_quote = _extract_chart_payload(safe_json(intraday_res))
        i_meta = i_payload.get("meta", {})
        raw_state = str(i_meta.get("marketState", "") or "").upper().strip()

        if raw_state == "PRE":
            session_state = "PREMARKET"
        elif raw_state == "POST":
            session_state = "POSTMARKET"
        elif raw_state == "REGULAR":
            session_state = "OTWARTY"

        pre_scan, regular_scan, post_scan = _extract_intraday_session_prices(i_payload, i_quote)

        pre_p = pre_scan or safe(i_meta.get("preMarketPrice", 0.0)) or safe(fh_q.get("preMarketPrice", 0.0))
        post_p = post_scan or safe(i_meta.get("postMarketPrice", 0.0)) or safe(fh_q.get("postMarketPrice", 0.0))
        reg_p = regular_scan or safe(i_meta.get("regularMarketPrice", 0.0)) or quote_price

        if i_quote.get("close"):
            last_trade = safe(i_quote.get("close", [])[-1])

    chart_prev_close = safe(chart_meta.get("previousClose", 0.0)) or safe(chart_meta.get("chartPreviousClose", 0.0))
    prev_c, anchor_source = _session_anchor_close(session_state, closes, chart_prev_close, quote_prev_close)

    current_price = _select_active_price(session_state, prev_c, pre_p, reg_p, post_p, last_trade, quote_price)
    if current_price <= 0:
        current_price = quote_price or last_trade or reg_p or pre_p or post_p or prev_c

    v7_stats = analyze_v7(closes, volumes, current_price, prev_c)

    earnings_reaction = await fetch_prev_earnings_reaction(symbol)

    day_low = (
        safe(fh_q.get("regularMarketDayLow", 0.0))
        or safe(chart_meta.get("regularMarketDayLow", 0.0))
        or safe(profile.get("dayLow", 0.0))
    )
    day_high = (
        safe(fh_q.get("regularMarketDayHigh", 0.0))
        or safe(chart_meta.get("regularMarketDayHigh", 0.0))
        or safe(profile.get("dayHigh", 0.0))
    )
    low52 = (
        safe(fh_q.get("fiftyTwoWeekLow", 0.0))
        or safe(chart_meta.get("fiftyTwoWeekLow", 0.0))
        or safe(profile.get("yearLow", 0.0))
    )
    high52 = (
        safe(fh_q.get("fiftyTwoWeekHigh", 0.0))
        or safe(chart_meta.get("fiftyTwoWeekHigh", 0.0))
        or safe(profile.get("yearHigh", 0.0))
    )

    vol = safe(fh_q.get("regularMarketVolume", 0.0))
    if vol <= 0 and volumes:
        vol = safe(volumes[-1])

    if len(volumes) >= 10:
        avg_vol = int(sum(volumes[-10:]) / 10)
    else:
        avg_vol = int(safe(fh_q.get("averageDailyVolume10Day", 0.0)) or safe(fh_q.get("averageDailyVolume3Month", 0.0)))

    market_cap = safe(profile.get("marketCapitalization", 0.0)) * 1_000_000

    pe = "N/A"
    eps = "N/A"
    if isinstance(metrics, dict):
        metric = metrics.get("metric", {}) or {}
        pe_v = metric.get("peNormalizedAnnual") or metric.get("peExclExtraTTM") or metric.get("peTTM")
        eps_v = metric.get("epsTTM")
        if pe_v is not None:
            pe = f"{safe(pe_v):.2f}"
        if eps_v is not None:
            eps = f"{safe(eps_v):.2f}"

    next_earnings = "Brak danych"
    if isinstance(earnings_data, dict):
        cal = earnings_data.get("earningsCalendar", []) or []
        if cal:
            next_earnings = cal[0].get("date", "Brak danych")

    return {
        "symbol": symbol,
        "name": normalize_company_name(symbol, profile.get("name", symbol) if isinstance(profile, dict) else symbol),
        "session_state": session_state,
        "active_price": current_price,
        "session_price": current_price,
        "regular_price": reg_p or quote_price or last_trade or prev_c,
        "last_trade_price": last_trade,
        "quote_price": quote_price,
        "chart_prev_close": chart_prev_close,
        "quote_prev_close": quote_prev_close,
        "anchor_source": anchor_source,
        "prev_close": prev_c,
        "pre_price": pre_p,
        "post_price": post_p,
        "vol": vol,
        "avg_vol": avg_vol,
        "market_cap": market_cap,
        "pe": pe,
        "eps": eps,
        "next_earnings": next_earnings,
        "earnings_reaction": earnings_reaction,
        "day_low": day_low,
        "day_high": day_high,
        "low52": low52,
        "high52": high52,
        "closes": closes,
        "volumes": volumes,
        "v7": v7_stats,
    }


async def fetch_bulk(symbols, chunk_size=4):

    unique = [s for s in dict.fromkeys([str(x).strip().upper() for x in symbols if x]) if s]
    results = {}
    sem = asyncio.Semaphore(max(1, int(chunk_size)))

    async def _worker(sym):
        async with sem:
            try: return sym, await fetch_ticker(sym)
            except Exception: return sym, None

    gathered = await asyncio.gather(*[_worker(sym) for sym in unique], return_exceptions=True)
    for item in gathered:
        if not isinstance(item, Exception) and item[1]:
            results[item[0]] = item[1]
    return results


# =========================================
# RECYCLERVIEW
# =========================================

class DataCard(MDCard):
    text = StringProperty("")
    def _update_height(self, texture_h=0):
        try:
            from kivy.metrics import dp as _dp
            self.height = max(_dp(170), float(texture_h) + _dp(40))
        except Exception:
            pass

class TabRV(RecycleView):
    pass

KV = '''
#:import dp kivy.metrics.dp

<DataCard>:
    orientation: "vertical"
    size_hint_y: None
    padding: dp(14)
    spacing: dp(8)
    radius: [12, 12, 12, 12]
    elevation: 1
    md_bg_color: 1, 1, 1, 1
    height: _body.texture_size[1] + dp(40) if _body.texture_size[1] > 0 else dp(170)

    MDLabel:
        id: _body
        text: root.text
        markup: True
        size_hint_y: None
        height: self.texture_size[1]
        text_size: self.width - dp(28), None
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
        self.batch_size = 12
        self.max_visible = 60
        self._scroll_trigger_ts = 0.0

        self.control_panel = MDBoxLayout(
            orientation="vertical", size_hint_y=None, height=dp(0), padding=[dp(8)], spacing=dp(6)
        )
        self.add_widget(self.control_panel)

        self.more_button = MDRaisedButton(
            text="Pokaż więcej", size_hint_y=None, height=0, opacity=0, disabled=True, on_release=self.load_more
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

    def set_rows(self, rows):
        def _apply(dt):
            self.full_rows = list(rows or [])
            self.visible_count = min(self.batch_size, len(self.full_rows))
            self._apply_visible_rows(scroll_top=True)
        Clock.schedule_once(_apply, 0)

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
        Clock.schedule_once(lambda dt: self.set_rows(["[b]Ładowanie danych...[/b]"]), 0)
        if run_coro(self._safe_fetch(*args, **kwargs)) is None:
            self._loading = False

    async def _safe_fetch(self, *args, **kwargs):
        try:
            self.set_rows(await self._fetch(*args, **kwargs))
        except Exception as exc:
            self.set_rows([f"[color=#FF0000][b]Błąd:[/b] {exc}[/color]"])
        finally:
            self._loading = False

    async def _fetch(self, *args, **kwargs):
        return []

# =========================================
# TABS
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
        self.control_panel.add_widget(MDRaisedButton(text="Sprawdź Status", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        return [
            f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]\n\n"
            f"[b]RYNEK USA[/b]\nStatus: [color=#00AA00]{market_status()}[/color]\n"
            f"Czas lokalny: {local_time_text()}\nNastępne otwarcie: {next_us_market_open_text()}",
            us_market_hours_text_local(),
            build_full_glossary()
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

        rows = [f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]"]

        pre_gainers, post_gainers, open_gainers = [], [], []

        for sym, d in bulk_data.items():
            v7 = d["v7"]
            if v7["pct"] > 0:
                if d["session_state"] == "PREMARKET":
                    pre_gainers.append((v7["pct"], sym))
                elif d["session_state"] == "POSTMARKET":
                    post_gainers.append((v7["pct"], sym))
                else:
                    open_gainers.append((v7["pct"], sym))

            rows.append(
                f"[b]{sym}[/b] — [color=#555555]{d['name']}[/color] | Sesja: {d['session_state']}\n"
                f"Cena aktywa: [b]{v7['price']:.2f} USD[/b] "
                f"([color={'#00AA00' if v7['pct'] >= 0 else '#FF0000'}]{v7['diff']:+.2f} USD | {v7['pct']:+.2f}%[/color])\n"
                f"Regular: {d['regular_price']:.2f} | Pre: {d['pre_price']:.2f} | Post: {d['post_price']:.2f}\n"
                f"Wolumen: {int(d['vol']):,} | Śr. 10D: {int(d['avg_vol']):,} | Kapitalizacja: {format_cap(d['market_cap'])} | P/E: {d['pe']}\n"
                f"Zakres dnia: {d['day_low']:.2f}-{d['day_high']:.2f} | 52W: {d['low52']:.2f}-{d['high52']:.2f}\n"
                f"RSI: [color={color_for_rsi(v7['rsi'])}]{v7['rsi']:.1f}[/color] | "
                f"MACD: [color={color_for_macd(v7['macd'], v7['sig'])}]{v7['macd']:.3f}[/color] | "
                f"Hist: {format_histogram(v7['hist'])}\n"
                f"Sygnał V7: [b][color={v7['signal_color']}]{v7['signal']}[/color][/b] (Pewność: {v7['confidence']}%)\n"
                f"Faza rynku: {v7['regime']} | Wejście: {v7['timing']}"
            )

        leaders_text = "[b][color=#FF9900]🔥 TOP GAINERS W SESJI[/color][/b]\n"
        if pre_gainers:
            pre_gainers.sort(reverse=True)
            leaders_text += "PRE-MARKET: " + ", ".join([f"{s} (+{p:.1f}%)" for p, s in pre_gainers[:3]]) + "\n"
        if open_gainers:
            open_gainers.sort(reverse=True)
            leaders_text += "OTWARTA SESJA: " + ", ".join([f"{s} (+{p:.1f}%)" for p, s in open_gainers[:3]]) + "\n"
        if post_gainers:
            post_gainers.sort(reverse=True)
            leaders_text += "POST-MARKET: " + ", ".join([f"{s} (+{p:.1f}%)" for p, s in post_gainers[:3]]) + "\n"

        if not pre_gainers and not open_gainers and not post_gainers:
            leaders_text += "Brak gainerów w obecnych sesjach."

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

        v7 = d["v7"]
        return [(
            f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]\n\n"
            f"[b]{d['name']} ({sym})[/b] | Sesja: {d['session_state']}\n"
            f"-------------------------------------------------\n"
            f"[b]DANE RYNKOWE & WYCENA[/b]\n"
            f"Cena: [b]{v7['price']:.2f} USD[/b] "
            f"([color={'#00AA00' if v7['pct'] >= 0 else '#FF0000'}]{v7['diff']:+.2f} USD | {v7['pct']:+.2f}%[/color]) "
            f"[color=#888888](vs prev close: {d['prev_close']:.2f})[/color]\n"
            f"Regular: {d['regular_price']:.2f} | Pre-Market: {d['pre_price']:.2f} | Post-Market: {d['post_price']:.2f} | Last: {d['last_trade_price']:.2f}\n"
            f"Wolumen: [b]{int(d['vol']):,}[/b] | Śr. 10D: [b]{int(d['avg_vol']):,}[/b]\n"
            f"Zakres Dnia: {d['day_low']:.2f}-{d['day_high']:.2f} | 52W: {d['low52']:.2f}-{d['high52']:.2f}\n"
            f"Kapitalizacja: {format_cap(d['market_cap'])} | P/E: {d['pe']} | EPS: {d['eps']}\n"
            f"-------------------------------------------------\n"
            f"[b]KALENDARZ WYNIKÓW[/b]\n"
            f"Następny raport: {d['next_earnings']}\n"
            f"Reakcja rynku (poprzednio): {d['earnings_reaction']}\n"
            f"-------------------------------------------------\n"
            f"[b]ANALIZA V7 (QUANT & AI)[/b]\n"
            f"Sygnał główny: [b][color={v7['signal_color']}]{v7['signal']}[/color][/b] (Pewność: {v7['confidence']}%)\n"
            f"Faza rynku: {v7['regime']} | Moment wejścia: {v7['timing']}\n"
            f"Ryzyko wahań: {v7['volatility']*100:.2f}% | Szansa ruchu: {v7['prob']}%\n"
            f"Sugerowana wielkość pozycji (na 10k): {v7['position_size']} USD\n"
            f"-------------------------------------------------\n"
            f"[b]TECHNIKA BAZOWA[/b]\n"
            f"RSI: {v7['rsi']:.1f} | MACD: {v7['macd']:.3f}/{v7['sig']:.3f} | Hist: {v7['hist']:+.3f}\n"
            f"SMA: 14={v7['sma14']} | 30={v7['sma30']} | 90={v7['sma90']}\n"
        )]
        
 rel[:5]:
 
class KatalizatoryTab(BaseTab):
    title = "Katalizatory"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.initial_visible = 10
        self.batch_size = 10
        self.max_visible = 40
        self.control_panel.height = dp(76)
        self.control_panel.clear_widgets()
        self.control_panel.add_widget(MDRaisedButton(text="Pobierz", size_hint_y=None, height=dp(34), on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))
        self.control_panel.add_widget(self.more_button)

    async def _fetch(self, *args, **kwargs):
        # Pobieranie Newsów tak jak wcześniej, filtrujemy z wykorzystaniem darmowego Yahoo Search
        app = MDApp.get_running_app()
        watch_list = getattr(getattr(app, "scanner_tab", None), "static_tickers", []) or []
        universe = list(dict.fromkeys(NASDAQ_CORE + GPW_CORE + [s.strip().upper() for s in watch_list if s]))

        now = datetime.now()
        start_date = now.strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=7)).strftime("%Y-%m-%d")
        threshold = int((now - timedelta(days=30)).timestamp())

        catalyst_queries = [
            "FDA", "PDUFA", "PDUFDA", "approval", "clinical trial", "merger", "buyout",
            "acquisition", "contract", "partnership", "artificial intelligence",
            "earnings", "guidance", "results", "revenue", "EPS", "financial results"
        ]
        news_items = []
        seen = set()

        for q in catalyst_queries:
            q_enc = quote_plus(q)
            res = await safe_request_async(f"https://query2.finance.yahoo.com/v1/finance/search?q={q_enc}&newsCount=50", timeout=6)
            if res.status_code != 200: continue
            
            for n in safe_json(res).get("news", []):
                title = n.get("title", "")
                cat = get_category_tag(title)
                if not cat: continue
                pub = n.get("providerPublishTime", 0)
                if pub and pub < threshold: continue
                
                rel = n.get("relatedTickers", []) or []
                ticker = (rel[0] if rel else "RYNEK").strip().upper()
                key = re.sub(r"\s+", " ", f"{ticker}|{title}|{cat}".lower())
                if key in seen: continue
                seen.add(key)
                news_items.append({"ticker": ticker, "title": title, "link": n.get("link", ""), "cat": cat, "context": get_catalyst_context(title)})

        earnings_rows = []
        for sym in universe[:15]:
            try:
                res = await safe_request_async(f"https://finnhub.io/api/v1/calendar/earnings?symbol={sym}&from={start_date}&to={end_date}&token={FINNHUB_KEY}", timeout=4)
                if res.status_code == 200:
                    payload = safe_json(res).get("earningsCalendar", []) or []
                    for item in payload:
                        item_sym = (item.get("symbol") or sym).strip().upper()
                        if item_sym in universe: earnings_rows.append(item | {"symbol": item_sym})
            except Exception: pass

        if not earnings_rows:
            try:
                general = await fetch_earnings()
                for item in general or []:
                    item_sym = (item.get("symbol") or "").strip().upper()
                    if item_sym and item_sym in universe: earnings_rows.append(item | {"symbol": item_sym})
            except Exception: pass

        names = await fetch_company_names([item["ticker"] for item in news_items if item.get("ticker") and item["ticker"] != "RYNEK"] + [item.get("symbol", "") for item in earnings_rows])

        rows = [color_wrap(f"Ostatnia aktualizacja: {timestamp_text()}", "#888888")]
        fda_cards, mna_cards, ai_cards, other_cards = [], [], [], []

        for item in news_items:
            ticker = item["ticker"]
            title = item["title"]
            cat = item["cat"]
            display_name = names.get(ticker) or normalize_company_name(ticker, ticker)
            label = f"{ticker} ({display_name})" if display_name.upper() != ticker.upper() else ticker
            safe_link = item["link"] or search_url_from_query(title)
            
            card = (
                f"[ref={safe_link}][color=#FF33CC][b][{cat}][/b][/color][/ref] "
                f"[ref={safe_link}][color=#008080][b]{label}[/b][/color][/ref]\n"
                f"{item.get('context', '')}\n[ref={safe_link}]{title}[/ref]"
            )

            if cat == "FDA/PDUFA": fda_cards.append(card)
            elif cat in ("WYKUP / M&A", "ZAINTERESOWANIE WYKUPEM"): mna_cards.append(card)
            elif cat == "AI / TRANSFORMACJA": ai_cards.append(card)
            else: other_cards.append(card)

        if fda_cards:
            rows.append(f"[ref={search_url_from_query('FDA PDUFA stocks news')}][b][color=#ff9900]🩺 FDA / PDUFA / DECYZJE REGULACYJNE[/color][/b][/ref]")
            rows.extend(fda_cards[:10])
        if mna_cards:
            rows.append(f"[ref={search_url_from_query('merger acquisition buyout stocks news')}][b][color=#FF6666]🧩 WYKUPY / PRZEJĘCIA / ZAINTERESOWANIE WYKUPEM[/color][/b][/ref]")
            rows.extend(mna_cards[:10])
        if ai_cards:
            rows.append(f"[ref={search_url_from_query('artificial intelligence stock news')}][b][color=#00FFFF]🧠 AI / TRANSFORMACJA / UMOWY[/color][/b][/ref]")
            rows.extend(ai_cards[:10])
        if other_cards:
            rows.append(f"[ref={search_url_from_query('stock catalyst news earnings contract partnership')}][b][color=#FF33CC]🔥 INNE KATALIZATORY[/color][/b][/ref]")
            rows.extend(other_cards[:10])

        if earnings_rows:
            rows.append(f"[ref={search_url_from_query('earnings calendar stocks')}][b][color=#ff8c00]— KALENDARZ WYNIKÓW (7 DNI) —[/color][/b][/ref]")
            for item in earnings_rows[:15]:
                sym = item.get("symbol", "—")
                name = names.get(sym) or normalize_company_name(sym, sym)
                label = f"{sym} ({name})" if name.upper() != sym.upper() else sym
                rows.append(f"[color=#008080][b]{label}[/b][/color]\nData: {item.get('date', 'Brak daty')} | EPS est.: {item.get('epsEstimate', 'N/A')}")
        else:
            rows.append("[color=#888888]Brak aktywnych wyników w najbliższych dniach dla sledzonych rynków.[/color]")

        return rows[:120]
            
class CFDTab(BaseTab):
    title = "CFD/Własne"
    def __init__(self, **kw):
        super().__init__(**kw)
        self.initial_visible = 6
        self.batch_size = 6
        self.max_visible = 24
        self.control_panel.height = dp(156)
        self.control_panel.clear_widgets()

        self.static_tickers = ["BTC-USD", "GC=F", "NQ=F", "ES=F", "CL=F"] # Własne CFD

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(12))
        self.input_field = MDTextField(hint_text="Dodaj symbol CFD", mode="rectangle")
        input_row.add_widget(self.input_field)
        input_row.add_widget(MDRaisedButton(text="+", size_hint_x=0.2, on_release=self.add_ticker))
        input_row.add_widget(MDRaisedButton(text="-", size_hint_x=0.2, on_release=self.remove_ticker))
        self.control_panel.add_widget(input_row)

        self.control_panel.add_widget(MDRaisedButton(text="Analizuj", size_hint_y=None, height=dp(34), on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))
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
        bulk = await fetch_bulk(self.static_tickers, chunk_size=3)
        rows = [f"[color=#888888]Ostatnia aktualizacja: {timestamp_text()}[/color]"]

        sections = {
            "A: POTENCJAŁ WYBICIA (MACD/RSI/SMA)": [],
            "B: POST-MARKET / PRE-MARKET": [],
            "C: POZOSTAŁE": [],
        }

        for sym, d in bulk.items():
            v7 = d["v7"]
            tp, sl = make_tp_sl(v7["price"], 0.03, 0.02)

            session_state = d.get("session_state", "")
            is_breakout = (
                (v7["signal"] == "KUPUJ" and v7["rsi"] > 42 and v7["hist"] > 0)
                or (v7["price"] > v7["sma30"] and v7["hist"] > 0 and v7["pct"] > 0)
            )
            is_session_signal = session_state in ("PREMARKET", "POSTMARKET") and abs(v7["pct"]) > 0.02

            row = (
                f"[b]{d['name']} ({sym})[/b]\n"
                f"Cena: [b]{v7['price']:.2f}[/b] ([color={'#00AA00' if v7['pct'] >= 0 else '#FF0000'}]{v7['diff']:+.2f} USD | {v7['pct']:+.2f}%[/color])\n"
                f"Regular: {d['regular_price']:.2f} | Pre: {d['pre_price']:.2f} | Post: {d['post_price']:.2f} | Last: {d['last_trade_price']:.2f}\n"
                f"Sugerowane TP: [color=#00AA00]{tp:.2f}[/color] | SL: [color=#FF3333]{sl:.2f}[/color]\n"
                f"V7 Signal: [b][color={v7['signal_color']}]{v7['signal']}[/color][/b] | Faza: {v7['regime']}\n"
                f"RSI: {v7['rsi']:.1f} | SMA90: {v7['sma90']:.2f} | Hist: {format_histogram(v7['hist'])}"
            )

            if is_breakout:
                sections["A: POTENCJAŁ WYBICIA (MACD/RSI/SMA)"].append(row)
            elif is_session_signal:
                sections["B: POST-MARKET / PRE-MARKET"].append(row)
            else:
                sections["C: POZOSTAŁE"].append(row)

        for section, items in sections.items():
            rows.append(f"[b][color=#008080]{section}[/color][/b]")
            rows.extend(items if items else ["[color=#888888]Brak sygnałów w tej kategorii.[/color]"])

        return rows

