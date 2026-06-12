import os
import json
import random
import time
import re
import copy
import asyncio
import httpx
import certifi
import webbrowser
from datetime import datetime, timedelta
from collections import deque
from zoneinfo import ZoneInfo

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

# ==============================
#      USTAWIENIA & API
# ==============================

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"}
FINNHUB_KEY = "d82t3s1r01ql4onfbbngd82t3s1r01ql4onfbbo0"

MAX_CACHE_SIZE = 250
REQUEST_DELAY = 0.15
MAX_RETRIES = 2

REQUEST_CACHE = {}
REQUEST_CACHE_LOCK = asyncio.Lock()
LAST_REQUEST_TIME = {}
RATE_LIMIT_LOCK = asyncio.Lock()

REQUEST_CACHE_TTL = {"screener": 120, "ticker": 90, "finnhub": 120, "company": 180}

PL_DAYS = {"Monday": "PONIEDZIAŁEK", "Tuesday": "WTOREK", "Wednesday": "ŚRODA", "Thursday": "CZWARTEK", "Friday": "PIĄTEK", "Saturday": "SOBOTA", "Sunday": "NIEDZIELA"}

# Globalny asynchroniczny klient
HTTP_CLIENT = httpx.AsyncClient(headers=HEADERS, verify=certifi.where(), timeout=12.0)

# ==============================
#         PRICE ENGINE
# ==============================

class PriceEngine:
    CACHE = {}
    TTL = 60

    @staticmethod
    def analyze(sym, closes, price, vol=0, avg_vol=0):
        now = time.time()
        key = (sym, len(closes), round(safe_number(price), 4))
        cached = PriceEngine.CACHE.get(key)
        if cached and now - cached["ts"] < PriceEngine.TTL:
            return cached["data"]

        rsi = PriceEngine.rsi(closes)
        macd, sig, hist = PriceEngine.macd(closes)
        sma14 = PriceEngine.sma(closes, 14, price)
        sma30 = PriceEngine.sma(closes, 30, price)
        sma50 = PriceEngine.sma(closes, 50, price)
        sma90 = PriceEngine.sma(closes, 90, price)

        score, signal_text, signal_color = PriceEngine.signal(rsi, macd, sig, hist, price, sma14, sma30, sma90, vol, avg_vol)

        result = {
            "rsi": rsi, "macd": macd, "sig": sig, "hist": hist,
            "sma14": sma14, "sma30": sma30, "sma50": sma50, "sma90": sma90,
            "score": score, "signal_text": signal_text, "signal_color": signal_color,
        }
        PriceEngine.CACHE[key] = {"ts": now, "data": result}
        return result

    @staticmethod
    def rsi(prices, period=14):
        try:
            if len(prices) < period + 1: return 50.0
            deltas = [prices[i] - prices[i - 1] for i in range(1, len(prices))]
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
        except Exception: return 50.0

    @staticmethod
    def ema(prices, period):
        if not prices: return []
        ema = [prices[0]]
        k = 2 / (period + 1)
        for p in prices[1:]: ema.append(p * k + ema[-1] * (1 - k))
        return ema

    @staticmethod
    def macd(prices):
        try:
            if len(prices) < 35: return 0.0, 0.0, 0.0
            ema12 = PriceEngine.ema(prices, 12)
            ema26 = PriceEngine.ema(prices, 26)
            min_len = min(len(ema12), len(ema26))
            macd_line = [ema12[i] - ema26[i] for i in range(-min_len, 0)]
            signal_line = PriceEngine.ema(macd_line, 9)
            macd_val = macd_line[-1]
            sig_val = signal_line[-1]
            hist = macd_val - sig_val
            return round(macd_val, 3), round(sig_val, 3), round(hist, 3)
        except Exception: return 0.0, 0.0, 0.0

    @staticmethod
    def sma(prices, period, fallback=0.0):
        if not prices: return fallback
        if len(prices) >= period: return sum(prices[-period:]) / period
        return sum(prices) / len(prices)

    @staticmethod
    def signal(rsi, macd, sig, hist, price, sma14, sma30, sma90, volume, avg_volume):
        score = 0.0
        if rsi <= 30: score += 3
        elif rsi <= 40: score += 2
        elif rsi >= 70: score -= 3

        if macd > sig: score += 2
        else: score -= 1.5
        if hist > 0: score += 1
        else: score -= 1

        if price > sma14: score += 0.75
        if price > sma30: score += 0.5
        if price > sma90: score += 0.75

        if avg_volume > 0:
            if volume >= avg_volume: score += 0.5
            else: score -= 0.25

        bullish = sum([rsi <= 40, macd > sig, hist > 0, price > sma14, price > sma30])
        if score >= 5 and bullish >= 4: return score, "MOCNE KUP", "#006600"
        elif score >= 2: return score, "KUP", "#00AA00"
        elif score <= -4: return score, "MOCNE SPRZEDAJ", "#FF0000"
        elif score <= -1: return score, "SPRZEDAJ", "#FF9900"
        else: return score, "NEUTRALNE", "#888888"

# ==============================
#      NARZĘDZIA POMOCNICZE
# ==============================

def format_market_cap(val):
    try:
        val = float(val)
        if val == 0: return "Brak"
        if val >= 1_000_000_000_000: return f"{val/1_000_000_000_000:.2f} bln USD"
        if val >= 1_000_000_000: return f"{val/1_000_000_000:.2f} mld USD"
        if val >= 1_000_000: return f"{val/1_000_000:.2f} mln USD"
        if val >= 1000: return f"{val/1000:.0f} tys. USD"
        return f"{val:.0f} USD"
    except Exception: return "Brak"

def safe_number(val, default=0.0):
    try: return float(val) if val is not None else default
    except Exception: return default

def get_pl_session_hint(now=None):
    try:
        tz = ZoneInfo("America/New_York")
        now = now.astimezone(tz) if getattr(now, "tzinfo", None) else datetime.now(tz)
    except Exception: now = now or datetime.now()

    if now.weekday() >= 5: return "CLOSED"
    minutes = now.hour * 60 + now.minute
    if 4 * 60 <= minutes < 9 * 60 + 30: return "PRE"
    if 9 * 60 + 30 <= minutes < 16 * 60: return "REGULAR"
    if 16 * 60 <= minutes < 20 * 60: return "POST"
    return "CLOSED"

def resolve_active_price(data):
    session = str(data.get("session_state") or get_pl_session_hint()).upper().strip()
    prev_close = safe_number(data.get("prev_close"), 0.0)
    regular = safe_number(data.get("price"), 0.0)
    pre = safe_number(data.get("pre_price"), 0.0)
    post = safe_number(data.get("post_price"), 0.0)
    session_price = safe_number(data.get("session_price"), 0.0)
    nat_chg_amt = safe_number(data.get("change_amt"), 0.0)

    if session == "PRE": active = pre or session_price or regular
    elif session == "POST": active = post or session_price or regular
    else: active = regular or session_price or prev_close

    c_amt = active - prev_close if prev_close else 0.0
    if abs(c_amt) < 0.0001 and nat_chg_amt != 0: c_amt = nat_chg_amt
    c_pct = (c_amt / prev_close) * 100 if prev_close else 0.0

    return {"session": session, "active_price": active, "prev_close": prev_close, "change_amt": c_amt, "change_pct": c_pct}

def get_session_snapshot(data):
    r = resolve_active_price(data)
    labels = {"PRE": "[color=#0000FF][b][PRE-MARKET][/b][/color]", "REGULAR": "[color=#00AA00][b][MARKET OPEN][/b][/color]", "POST": "[color=#800080][b][POST-MARKET][/b][/color]", "CLOSED": "[color=#FF9900][b][ZAMKNIĘTY][/b][/color]"}
    return {"session": r["session"], "session_label": labels.get(r["session"], labels["CLOSED"]), "price": r["active_price"], "change_amt": r["change_amt"], "change_pct": r["change_pct"]}

def normalize_company_name(symbol, name=None):
    symbol = (symbol or "").strip().upper()
    cleaned = (name or "").strip()
    fallback = {"AAPL": "Apple", "TSLA": "Tesla", "MSFT": "Microsoft", "NVDA": "NVIDIA", "PLTR": "Palantir"}
    if cleaned and cleaned.upper() != symbol: return cleaned
    return fallback.get(symbol, cleaned or symbol)

def timestamp_text(): return datetime.now().strftime("%d.%m.%Y %H:%M:%S")

def color_wrap(text, color): return f"[color={color}]{text}[/color]"

def fmt_num(value, digits=2, signed=False):
    v = safe_number(value)
    return f"{v:+.{digits}f}" if signed else f"{v:.{digits}f}"

def format_price_line(value, benchmark=None):
    v = safe_number(value)
    color = "#888888" if benchmark is None else "#00AA00" if v > safe_number(benchmark) else "#FF0000" if v < safe_number(benchmark) else "#888888"
    return color_wrap(fmt_num(v, 2), color)

def color_for_rsi(rsi): return "#006600" if rsi <= 30 else "#00AA00" if rsi <= 40 else "#FF0000" if rsi >= 70 else "#FF9900" if rsi >= 60 else "#888888"
def color_for_macd(macd, signal): return "#00AA00" if macd > signal else "#FF0000"
def format_histogram(hist): return color_wrap(fmt_num(hist, 3, signed=True), "#00AA00" if hist > 0 else "#FF0000" if hist < 0 else "#888888")
def chunked_list(values, size):
    lst = list(values)
    for i in range(0, len(lst), max(1, size)): yield lst[i:i + size]

# ==============================
#      ASYNCHRONICZNE API
# ==============================

async def safe_request_async(url, timeout=8, retries=MAX_RETRIES):
    host = url.split("/")[2] if "//" in url else "default"
    for i in range(retries):
        async with RATE_LIMIT_LOCK:
            now = time.time()
            diff = now - LAST_REQUEST_TIME.get(host, 0)
            if diff < REQUEST_DELAY: await asyncio.sleep(REQUEST_DELAY - diff)
            LAST_REQUEST_TIME[host] = time.time()
        try:
            response = await HTTP_CLIENT.get(url, timeout=timeout)
            if response.status_code == 200: return response
            if response.status_code == 404: break # Nie ma sensu ponawiać 404
            if response.status_code in (429, 500, 502, 503, 504):
                await asyncio.sleep(1.2 * (i + 1))
                continue
            return response
        except Exception:
            await asyncio.sleep(1.0 * (i + 1))
    class Dummy:
        status_code = 0
        def json(self): return {}
    return Dummy()

def _safe_json(response):
    try: return response.json()
    except Exception: return {}

async def fetch_top_gainers_by_type_async(scr_id="day_gainers"):
    cache_key = ("screener", scr_id)
    now_ts = time.time()
    async with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (now_ts - cached.get("ts", 0)) < REQUEST_CACHE_TTL["screener"]:
            return list(cached.get("data", []))

    count = 15 if "gainers" in scr_id else 18
    url = f"https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds={scr_id}&count={count}"
    
    res = await safe_request_async(url, timeout=5)
    if res.status_code == 200:
        result = _safe_json(res).get('finance', {}).get('result')
        if result and isinstance(result, list) and len(result) > 0:
            symbols = [q['symbol'] for q in result[0].get('quotes', []) if 'symbol' in q]
            async with REQUEST_CACHE_LOCK:
                REQUEST_CACHE[cache_key] = {"ts": now_ts, "data": symbols}
            return symbols
    return []

async def fetch_dynamic_universe_async(limit=90):
    # Usunięto 'trending_tickers', który zwraca błąd 404.
    screeners = ["day_gainers", "most_actives", "day_losers"]
    tasks = [fetch_top_gainers_by_type_async(s) for s in screeners]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    tickers = []
    for res in results:
        if isinstance(res, list): tickers.extend(res[:15])
    tickers.extend(["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD", "NFLX", "PLTR", "SMCI"])
    return list(dict.fromkeys(tickers))[:max(1, int(limit))]

async def fetch_ticker_data_async(ticker):
    ticker = (ticker or "").strip().upper()
    if not ticker: return {'price': 0.0, 'closes': []}

    cache_key = ("ticker", ticker)
    now_ts = time.time()
    async with REQUEST_CACHE_LOCK:
        cached = REQUEST_CACHE.get(cache_key)
        if cached and (now_ts - cached.get("ts", 0)) < REQUEST_CACHE_TTL["ticker"]:
            return dict(cached.get("data", {}))

    d_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
    i_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1m&range=1d&includePrePost=true"

    res_data = {'symbol': ticker, 'name': ticker, 'price': 0.0, 'session_price': 0.0, 'session_state': get_pl_session_hint(), 'prev_close': 0.0, 'vol': 0, 'avg_vol': 0, 'change_amt': 0.0, 'change_pct': 0.0, 'closes': [], 'volumes': [], 'market_cap': 0, 'pe': "N/A", 'eps': "N/A"}

    d_res, i_res = await asyncio.gather(safe_request_async(d_url), safe_request_async(i_url))

    if d_res.status_code == 200:
        c_res = _safe_json(d_res).get('chart', {}).get('result', [])
        if c_res:
            meta = c_res[0].get('meta', {})
            res_data['price'] = safe_number(meta.get('regularMarketPrice', 0.0))
            inds = c_res[0].get('indicators', {}).get('quote', [{}])[0]
            volumes = [v for v in inds.get('volume', []) if v is not None]
            res_data['closes'] = [c for c in inds.get('close', []) if c is not None]
            res_data['volumes'] = volumes
            if volumes:
                res_data['vol'] = volumes[-1]
                res_data['avg_vol'] = int(sum(volumes[-10:]) / 10) if len(volumes) >= 10 else int(sum(volumes) / len(volumes))

    session_state = get_pl_session_hint()
    if i_res.status_code == 200:
        result = _safe_json(i_res).get('chart', {}).get('result', [])
        if result:
            meta = result[0].get('meta', {})
            correct_prev = safe_number(meta.get('previousClose', meta.get('chartPreviousClose', 0.0)))
            if correct_prev > 0: res_data['prev_close'] = correct_prev
            # Pobierzmy po prostu aktualną cene dla uproszczenia
            live = safe_number(meta.get('regularMarketPrice', 0.0))
            if session_state == 'PRE' and meta.get('preMarketPrice'): live = meta.get('preMarketPrice')
            elif session_state == 'POST' and meta.get('postMarketPrice'): live = meta.get('postMarketPrice')
            if live > 0:
                res_data['session_price'] = live
                if res_data['price'] == 0.0: res_data['price'] = live
            
    res_data['session_state'] = session_state
    
    if res_data['price'] == 0.0 or res_data['market_cap'] == 0:
        fh_q = await safe_request_async(f"https://finnhub.io/api/v1/quote?symbol={ticker}&token={FINNHUB_KEY}")
        if fh_q.status_code == 200:
            fh_data = _safe_json(fh_q)
            if fh_data.get('c', 0) > 0:
                res_data['price'] = fh_data['c']
                res_data['prev_close'] = fh_data.get('pc', res_data['prev_close'])
        
        prof = await safe_request_async(f"https://finnhub.io/api/v1/stock/profile2?symbol={ticker}&token={FINNHUB_KEY}")
        if prof.status_code == 200:
            p_data = _safe_json(prof)
            if p_data.get('name'): res_data['name'] = normalize_company_name(ticker, p_data['name'])
            if p_data.get('marketCapitalization'): res_data['market_cap'] = p_data['marketCapitalization'] * 1_000_000

    res_data['name'] = normalize_company_name(ticker, res_data['name'])
    async with REQUEST_CACHE_LOCK: REQUEST_CACHE[cache_key] = {"ts": now_ts, "data": dict(res_data)}
    return res_data

async def fetch_bulk_ticker_data_serial_async(tickers, chunk_size=6):
    results = {}
    unique = [t for t in dict.fromkeys([str(x).strip().upper() for x in tickers if x]) if t]
    sem = asyncio.Semaphore(chunk_size)
    async def fetch_w_sem(ticker):
        async with sem:
            data = await fetch_ticker_data_async(ticker)
            if data and data.get('price', 0) > 0: results[ticker] = data
    await asyncio.gather(*(fetch_w_sem(t) for t in unique), return_exceptions=True)
    return results

async def fetch_finnhub_ticker_data_async(ticker):
    ticker = (ticker or "").strip().upper()
    data = await fetch_ticker_data_async(ticker)
    data['div_yield'] = "N/A"
    data['next_earnings'] = "Brak danych"
    data['news'] = []

    metrics_url = f"https://finnhub.io/api/v1/stock/metric?symbol={ticker}&metric=all&token={FINNHUB_KEY}"
    news_url = f"https://finnhub.io/api/v1/company-news?symbol={ticker}&from={(datetime.now()-timedelta(days=7)).strftime('%Y-%m-%d')}&to={datetime.now().strftime('%Y-%m-%d')}&token={FINNHUB_KEY}"
    earn_url = f"https://finnhub.io/api/v1/calendar/earnings?symbol={ticker}&from={datetime.now().strftime('%Y-%m-%d')}&to={(datetime.now()+timedelta(days=90)).strftime('%Y-%m-%d')}&token={FINNHUB_KEY}"

    m_res, n_res, e_res = await asyncio.gather(
        safe_request_async(metrics_url),
        safe_request_async(news_url),
        safe_request_async(earn_url)
    )

    if m_res.status_code == 200:
        m = _safe_json(m_res).get('metric', {})
        eps = m.get('epsTTM')
        if eps: data['eps'] = f"{eps:.2f}"
        div = m.get('dividendYieldIndicatedAnnual')
        if div: data['div_yield'] = f"{div:.2f}%"
        pe = m.get('peNormalizedAnnual') or m.get('peExclExtraTTM')
        if pe: data['pe'] = f"{pe:.2f}"

    if e_res.status_code == 200:
        e_cal = _safe_json(e_res).get('earningsCalendar', [])
        if e_cal: data['next_earnings'] = e_cal[0].get('date', 'Brak danych')

    if n_res.status_code == 200:
        news_list = _safe_json(n_res)
        if isinstance(news_list, list):
            for n in news_list[:5]:
                if n.get('headline') and n.get('url'):
                    data['news'].append(f"• [ref={n['url']}][color=#0000FF]{n['headline']}[/color][/ref]")
    return data

# ==============================
#      INTERFEJS GRAFICZNY
# ==============================

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

class ScrollableTab(MDTabsBase, MDBoxLayout):
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.orientation = "vertical"
        self.md_bg_color = [1, 1, 1, 1]
        self.is_loaded = False
        self._loading = False
        
        self.control_panel = MDBoxLayout(orientation="vertical", size_hint_y=None, height=dp(0), padding=[dp(12), dp(14), dp(12), dp(6)], spacing=dp(8))
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
        if self._loading: return
        self._loading = True
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text="Pobieranie danych...", halign="center"))
        # Użycie asynchronicznego zadania na pętli Kivy
        asyncio.create_task(self._safe_fetch(*args, **kwargs))

    async def _safe_fetch(self, *args, **kwargs):
        try:
            await self._fetch(*args, **kwargs)
        except Exception as exc:
            print(f"Błąd pobierania w zakładce: {exc}")
            self.content.clear_widgets()
            self.content.add_widget(MDLabel(text=f"[color=#FF0000][b]Błąd połączenia. Spróbuj później.\n{exc}[/b][/color]", markup=True, halign="center"))
        finally:
            self._loading = False

    async def _fetch(self, *args, **kwargs): pass

    def _render_cards(self, cards_data, title=None):
        self.content.clear_widgets()
        if title:
            self.content.add_widget(MDLabel(text=color_wrap(f"Aktualizacja: {timestamp_text()}", "#888888"), markup=True, size_hint_y=None, height=dp(24)))
            self.content.add_widget(MDLabel(text=title, markup=True, size_hint_y=None, height=dp(40)))
        else:
            self.content.add_widget(MDLabel(text=color_wrap(f"Aktualizacja: {timestamp_text()}", "#888888"), markup=True, size_hint_y=None, height=dp(24)))
            
        for c in cards_data:
            self.content.add_widget(DataCard(text=c))

# ==============================
#           ZAKŁADKI
# ==============================

class InfoTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Info"
        super().__init__(**kw)
        self.control_panel.height = dp(55)
        self.control_panel.add_widget(MDRaisedButton(text="Sprawdź Status Rynków", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    async def _fetch(self, *args, **kwargs):
        res = await safe_request_async(f"https://finnhub.io/api/v1/stock/market-status?exchange=US&token={FINNHUB_KEY}")
        is_open = _safe_json(res).get('isOpen', False)

        outputs = ["[b]Słowniczek:[/b]\n[b]SMA[/b] - średnia krocząca, wyznacza trend.\n[b]RSI[/b] - >70 to wykupienie (spadki), <30 to wyprzedanie (wzrosty).\n[b]MACD[/b] - przecięcie linii określa silne wejście.\n"]
        now = datetime.now()
        for i in range(3):
            check_date = now + timedelta(days=i)
            day_name = PL_DAYS.get(check_date.strftime("%A"), check_date.strftime("%A"))
            if check_date.weekday() >= 5: outputs.append(f"[b]{day_name}[/b]\n[color=#FF0000]ZAMKNIĘTE (Weekend)[/color]")
            else: outputs.append(f"[b]{day_name}[/b]\n[color=#00AA00]RYNKI {'OTWARTE' if is_open and i==0 else 'ZAPLANOWANE'}[/color]\nPre: 10:00-15:30 | Sesja: 15:30-22:00")
        
        self._render_cards(outputs)

class SkanerTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Skaner"
        super().__init__(**kw)
        self.static_tickers = ["AAPL", "MSFT", "NVDA", "AMD", "TSLA", "PLTR"]
        self.control_panel.height = dp(115)

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        self.input_field = MDTextField(hint_text="Dodaj Ticker", size_hint_x=0.66, mode="rectangle")
        input_row.add_widget(self.input_field)
        input_row.add_widget(MDRaisedButton(text="+", size_hint_x=0.17, on_release=self.add_ticker))
        input_row.add_widget(MDRaisedButton(text="-", size_hint_x=0.17, on_release=self.remove_ticker))
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
        # 404 handled gracefully now!
        gainers_pre, gainers_open = await asyncio.gather(
            fetch_top_gainers_by_type_async("day_gainers"),
            fetch_top_gainers_by_type_async("most_actives")
        )

        all_tickers = list(dict.fromkeys(self.static_tickers + gainers_pre[:10] + gainers_open[:10]))[:30]
        bulk_data = await fetch_bulk_ticker_data_serial_async(all_tickers, chunk_size=8)

        cards = []
        for sym in all_tickers:
            data = bulk_data.get(sym)
            if not data or len(data.get("closes", [])) < 10: continue

            comp_name = data.get("name", sym)
            p = data.get("price", 0.0)
            vol, avg_vol = data.get("vol", 0), data.get("avg_vol", 0)

            analysis = PriceEngine.analyze(sym, data["closes"], p, vol, avg_vol)
            sig_txt = color_wrap(f"[b]{analysis['signal_text']}[/b]", analysis['signal_color'])
            
            s_info = get_session_snapshot(data)
            
            txt = (
                f"{s_info['session_label']} [color=#008080][b]{comp_name}[/b][/color]\n"
                f"Cena: [b]{p:.2f} USD[/b] ({s_info['change_amt']:+.2f} USD)\n"
                f"Wolumen: {int(vol):,} (Śred. {int(avg_vol):,})\n"
                f"RSI: {color_wrap(f'{analysis['rsi']:.1f}', color_for_rsi(analysis['rsi']))} | MACD: {color_wrap(f'{analysis['macd']:.2f}', color_for_macd(analysis['macd'], analysis['sig']))}\n"
                f"SMA30: {format_price_line(analysis['sma30'], p)} | SMA90: {format_price_line(analysis['sma90'], p)}\n"
                f"Sygnał: {sig_txt}"
            )
            cards.append(txt)

        self._render_cards(cards)

class TickerTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Ticker"
        super().__init__(**kw)
        self.control_panel.height = dp(60)
        self.is_loaded = True 

        row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        self.inp = MDTextField(hint_text="Ticker (np. TSLA)", size_hint_x=0.70, mode="rectangle")
        row.add_widget(self.inp)
        row.add_widget(MDRaisedButton(text="Analizuj", size_hint_x=0.30, on_release=lambda x: self.refresh_data(sym=self.inp.text.strip().upper())))
        self.control_panel.add_widget(row)

    async def _fetch(self, *args, **kwargs):
        sym = kwargs.get('sym')
        if not sym: return
        
        data = await fetch_finnhub_ticker_data_async(sym)
        if safe_number(data.get('price')) == 0:
            self._render_cards([f"[color=#FF0000]Nie znaleziono danych dla: {sym}[/color]"])
            return

        p = data["price"]
        closes = data.get('closes', [])
        analysis = PriceEngine.analyze(sym, closes, p, data.get('vol',0), data.get('avg_vol',0))

        news_txt = "\n".join(data['news']) if data.get('news') else "Brak wiadomości."
        
        txt = (
            f"[b][color=#0000FF]{data['name']} ({sym})[/color][/b]\n"
            f"Cena: [b]{p:.2f} USD[/b] ({data['change_pct']:+.2f}%)\n"
            f"-------------------------------------------------\n"
            f"[b]FUNDAMENTY:[/b]\nKapitalizacja: {format_market_cap(data['market_cap'])} | P/E: {data['pe']} | EPS: {data['eps']}\n"
            f"Następne wyniki: {data['next_earnings']}\n"
            f"-------------------------------------------------\n"
            f"[b]TECHNIKA:[/b]\nRSI: {analysis['rsi']} | Sygnał: [b][color={analysis['signal_color']}]{analysis['signal_text']}[/color][/b]\n"
            f"SMA14: {format_price_line(analysis['sma14'], p)} | SMA50: {format_price_line(analysis['sma50'], p)}\n"
            f"-------------------------------------------------\n"
            f"[b]NEWSY:[/b]\n{news_txt}"
        )
        self._render_cards([txt])

class KatalizatoryTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Katalizator"
        super().__init__(**kw)
        self.control_panel.height = dp(55)
        self.control_panel.add_widget(MDRaisedButton(text="Pobierz Katalizatory", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    async def _fetch(self, *args, **kwargs):
        # Asynchroniczne pobieranie wiadomości z Yahoo po słowach kluczowych
        q_fda = "FDA decision OR PDUFA OR approval"
        q_mna = "merger OR acquisition OR buyout"
        
        res_fda, res_mna = await asyncio.gather(
            safe_request_async(f"https://query2.finance.yahoo.com/v1/finance/search?q={q_fda}&newsCount=10"),
            safe_request_async(f"https://query2.finance.yahoo.com/v1/finance/search?q={q_mna}&newsCount=10")
        )
        
        cards = []
        if res_fda.status_code == 200:
            for n in _safe_json(res_fda).get('news', []):
                t = n.get('relatedTickers', ['RYNEK'])[0]
                cards.append(f"[color=#ff9900][b]FDA / PDUFA - {t}[/b][/color]\n[ref={n.get('link')}]{n.get('title')}[/ref]")
                
        if res_mna.status_code == 200:
            for n in _safe_json(res_mna).get('news', []):
                t = n.get('relatedTickers', ['RYNEK'])[0]
                cards.append(f"[color=#FF6666][b]M&A / PRZEJĘCIA - {t}[/b][/color]\n[ref={n.get('link')}]{n.get('title')}[/ref]")

        if not cards: cards = ["Brak nowych ważnych katalizatorów."]
        self._render_cards(cards, title="[b][color=#FF33CC]Wydarzenia Katalityczne[/color][/b]")

class NewsTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Newsy"
        super().__init__(**kw)
        self.control_panel.height = dp(55)
        self.control_panel.add_widget(MDRaisedButton(text="Odśwież Wiadomości", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    async def _fetch(self, *args, **kwargs):
        res = await safe_request_async("https://query2.finance.yahoo.com/v1/finance/search?q=stocks market trading AI&newsCount=20")
        cards = []
        if res.status_code == 200:
            for n in _safe_json(res).get('news', []):
                t = n.get('relatedTickers', ['RYNEK'])[0]
                cards.append(f"[color=#00FFFF][b]{t}[/b][/color] - {n.get('publisher', 'News')}\n[ref={n.get('link')}]{n.get('title')}[/ref]")
        
        if not cards: cards = ["Brak wiadomości rynkowych."]
        self._render_cards(cards, title="[b][color=#00FFFF]Wiadomości Rynkowe[/color][/b]")

class CfdShortTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "CFD/Własne"
        super().__init__(**kw)
        self.control_panel.height = dp(55)
        self.control_panel.add_widget(MDRaisedButton(text="Analizuj Rynek", on_release=lambda x: self.refresh_data(), pos_hint={"center_x": 0.5}))

    async def _fetch(self, *args, **kwargs):
        universe = await fetch_dynamic_universe_async(limit=30)
        cfd_universe = ["CL=F", "GC=F", "NQ=F", "ES=F", "BTC-USD"]
        required = list(dict.fromkeys(universe + cfd_universe))

        bulk_data = await fetch_bulk_ticker_data_serial_async(required, chunk_size=8)
        cards = []
        
        for sym, data in bulk_data.items():
            closes, p = data.get("closes", []), data.get("price", 0.0)
            if len(closes) < 20 or p <= 0: continue
            
            analysis = PriceEngine.analyze(sym, closes, p, data.get("vol", 0), data.get("avg_vol", 0))
            if analysis["score"] >= 4.0 or analysis["score"] <= -3.0:
                tag = "[b][color=#00AA00]MOCNY SYGNAŁ KUPNA[/color][/b]" if analysis["score"] > 0 else "[b][color=#FF0000]MOCNY SYGNAŁ SPRZEDAŻY[/color][/b]"
                txt = f"{tag}\n[b]{data.get('name', sym)} ({sym})[/b] | Cena: {p:.2f}\nRSI: {analysis['rsi']:.1f} | MACD: {analysis['macd']:.2f}\nSygnał techniczny: {analysis['signal_text']}"
                cards.append(txt)
                
        if not cards: cards = ["Brak silnych sygnałów rynkowych w tym momencie."]
        self._render_cards(cards, title="[b][color=#ff8c00]Sygnały dla CFD i Dynamicznych Tickerów[/color][/b]")

# ==============================
#            APP CLASS
# ==============================

class StockScannerPro(MDApp):
    def build(self):
        self.theme_cls.theme_style = "Light"
        self.theme_cls.primary_palette = "Teal"

        screen = MDScreen()
        self.tabs_container = MDTabs()
        self.tabs_container.bind(on_tab_switch=self.on_tab_switch)
        screen.add_widget(self.tabs_container)
        return screen

    def on_start(self):
        # Inicjalizacja wszystkich 6 wymaganych zakładek
        self.tabs_instances = [InfoTab(), SkanerTab(), TickerTab(), KatalizatoryTab(), NewsTab(), CfdShortTab()]
        for tab in self.tabs_instances:
            self.tabs_container.add_widget(tab)

        Clock.schedule_once(lambda dt: self.tabs_instances[0].load_data_if_needed(), 0.5)
        Clock.schedule_once(lambda dt: self.tabs_instances[1].load_data_if_needed(), 1.0)

    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if hasattr(instance_tab, 'load_data_if_needed'):
            instance_tab.load_data_if_needed()

if __name__ == '__main__':
    # Pełne uruchomienie Kivy z asynchroniczną pętlą asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(StockScannerPro().async_run())
