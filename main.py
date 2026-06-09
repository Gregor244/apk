import os
import json
import threading
import requests
import certifi
import webbrowser
import time
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

def safe_request(url, timeout=5, retries=3, headers=None, **kwargs):
    headers = headers or HEADERS
    last_exc = None
    for i in range(retries):
        try:
            return safe_request(url, headers=headers, timeout=timeout, **kwargs)
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
    url = f"https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds={scr_id}&count=20"
    try:
        res = safe_request(url, headers=HEADERS, timeout=5)
        if res.status_code == 200:
            result = res.json().get('finance', {}).get('result')
            if result and isinstance(result, list) and len(result) > 0:
                quotes = result[0].get('quotes', [])
                return [q['symbol'] for q in quotes if 'symbol' in q]
    except: pass
    return []


def fetch_ticker_data(ticker):
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

    return res_data

def fetch_bulk_ticker_data(tickers):
    bulk_results = {}
    def worker(ticker): return ticker, fetch_ticker_data(ticker)
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = executor.map(worker, tickers)
        for ticker, data in results:
            if data and data.get('price', 0.0) > 0: bulk_results[ticker] = data
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
    res_data = fetch_ticker_data(ticker)
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
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text="Pobieranie danych...", halign="center"))
        threading.Thread(target=self._safe_fetch, args=args, kwargs=kwargs, daemon=True).start()

    def _safe_fetch(self, *args, **kwargs):
        try:
            self._fetch(*args, **kwargs)
        except Exception as e:
            print(f"Błąd pobierania w zakładce: {e}")
            Clock.schedule_once(lambda dt: self._show_error("Błąd połączenia. Spróbuj później."))

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
        self.control_panel.height = dp(55)
        self.control_panel.add_widget(MDRaisedButton(
            text="Sprawdź Status Rynków", 
            on_release=lambda x: self.refresh_data(), 
            pos_hint={"center_x": 0.5}
        ))

    def _fetch(self, *args, **kwargs):
        try:
            url = f"https://finnhub.io/api/v1/stock/market-status?exchange=US&token={FINNHUB_KEY}"
            status_data = safe_request(url, timeout=5).json()
            is_open = status_data.get('isOpen', False)
        except:
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
                status = "[color=#00AA00]RYNKI OTWARTE (Dzień Roboczy)[/color]"
                details = (
                    "Godziny handlu (Czas PL):\n"
                    "• [b]Pre-Market[/b]: 10:00 - 15:30\n"
                    "• [b]Sesja Główna[/b]: 15:30 - 22:00\n"
                    "• [b]Post-Market[/b]: 22:00 - 02:00 (następnego dnia)"
                )
            outputs.append(f"[b]{day_name_pl}[/b] ({date_str})\n{status}\n{details}")
        Clock.schedule_once(lambda dt: self._render(outputs))

    def _render(self, lines):
        self.content.clear_widgets()
        for line in lines: self.content.add_widget(DataCard(text=line))


class SkanerTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Skaner"
        super().__init__(**kw)
        self.static_tickers = ["AAPL", "MSFT", "NVDA", "AMD", "SNDK", "MU", "AMZN", "ARM", "MRVL", "NOW", "QUCY"]
        self.control_panel.height = dp(115)

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
            except: pass

    def save_stored_data(self):
        app = MDApp.get_running_app()
        path = os.path.join(app.user_data_dir, "skaner_tickers.json")
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(self.static_tickers, f)
        except: pass

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
            gainers_pre = fetch_top_gainers_by_type("pre_market_gainers")[:5]
            gainers_open = fetch_top_gainers_by_type("day_gainers")[:5]
            gainers_post = fetch_top_gainers_by_type("after_hours_gainers")[:5]
        except:
            gainers_pre, gainers_open, gainers_post = [], [], []

        gainer_map = {}
        for s in gainers_pre: gainer_map[s] = "[color=#00FFFF][PRE-MARKET GAINER][/color]"
        for s in gainers_open: gainer_map[s] = "[color=#00FF00][ZYSKUJĄCE DZISIAJ][/color]"
        for s in gainers_post: gainer_map[s] = "[color=#CC33FF][POST-MARKET GAINER][/color]"

        all_tickers = list(dict.fromkeys(self.static_tickers + list(gainer_map.keys())))
        bulk_data = fetch_bulk_ticker_data(all_tickers)

        app = MDApp.get_running_app()
        with CACHE_LOCK:
            for sym, d in bulk_data.items():
                app.shared_cache[sym] = merge_with_cache(sym, d, app.shared_cache)
            app.cache_time = datetime.now()
            if len(app.shared_cache) > MAX_CACHE_SIZE:
                app.shared_cache = dict(list(app.shared_cache.items())[-MAX_CACHE_SIZE:])

        for sym in all_tickers:
            data = app.shared_cache.get(sym)
            if not data: continue

            name = normalize_company_name(sym, data.get('name', sym))
            display_ticker = f"{sym} ({name})" if name and name.upper() != sym.upper() else sym

            market_state = data.get('market_state', 'CLOSED').upper()
            regular_price = data.get('price', 0.0)

            if "PRE" in market_state and data.get('pre_price', 0) > 0:
                active_price = data['pre_price']
                chg_val = data.get('pre_change_amt', 0.0)
                chg_pct = data.get('pre_change_pct', 0.0)
                session_tag = "[color=#0000FF][b][PRE-MARKET][/b][/color]"
            elif market_state in ["POST", "POSTPOST", "CLOSED"] and data.get('post_price', 0) > 0 and data.get('post_price') != regular_price:
                active_price = data['post_price']
                chg_val = data.get('post_change_amt', 0.0)
                chg_pct = data.get('post_change_pct', 0.0)
                session_tag = "[color=#800080][b][POST-MARKET][/b][/color]"
            elif market_state == "REGULAR":
                active_price = regular_price
                chg_val = data.get('change_amt', 0.0)
                chg_pct = data.get('change_pct', 0.0)
                session_tag = "[color=#00AA00][b][MARKET OPEN][/b][/color]"
            else:
                active_price = regular_price
                chg_val = data.get('change_amt', 0.0)
                chg_pct = data.get('change_pct', 0.0)
                session_tag = "[color=#FF9900][b][ZAMKNIĘTY][/b][/color]"

            chg_color = "#00AA00" if chg_val >= 0 else "#FF0000"
            price_details = f"Cena: [b]{active_price:.2f} USD[/b] ([color={chg_color}]{chg_val:+.2f} USD | {chg_pct:+.2f}%[/color])\n"

            source_tag = "[color=#0000FF][WATCHLIST][/color]" if sym in self.static_tickers else gainer_map.get(sym, "[RYNEK]")
            closes = data.get('closes', [])

            rsi_val = calculate_rsi(closes, 14) if closes else 50.0
            if rsi_val <= 35: rsi_str = f"[color=#00AA00][b]{rsi_val:.1f} (Wyprzedanie)[/b][/color]"
            elif rsi_val >= 65: rsi_str = f"[color=#FF0000][b]{rsi_val:.1f} (Wykupienie)[/b][/color]"
            else: rsi_str = f"[color=#777777]{rsi_val:.1f} (Neutralny)[/color]"

            macd_v, sig_v, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
            macd_str = f"[color=#00AA00]{macd_v:.2f}[/color]" if macd_v > sig_v else f"[color=#FF0000]{macd_v:.2f}[/color]"

            vol_val = data.get('vol', 0)
            avg_vol_val = data.get('avg_vol', 0)
            cap_str = format_market_cap(data.get('market_cap', 0))
            pe_str = str(data.get('pe', 'N/A'))

            trade_signal = generate_signal(rsi_val, macd_v, sig_v)
            sma10 = calc_sma(closes, 10, active_price)
            sma50 = calc_sma(closes, 50, active_price)

            txt = (
                f"{session_tag} {source_tag} [color=#008080][b]{display_ticker}[/b][/color]\n"
                f"{price_details}"
                f"Wolumen: {vol_val:,} (Śred. 10D: {avg_vol_val:,}) \n"
                f"Kapitalizacja: {cap_str} | P/E: [b]{pe_str}[/b]\n"
                f"RSI: {rsi_str} | MACD: {macd_str} | SMA10: {sma10:.2f} | SMA50: {sma50:.2f}\n"
                f"Sygnał: {trade_signal}"
            )
            cards_data.append(txt)

        Clock.schedule_once(lambda dt: self._render(cards_data))

    def _render(self, cards):
        self.content.clear_widgets()
        for c in cards: self.content.add_widget(DataCard(text=c))


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
        if not data.get('found') or data.get('price') == 0.0:
            Clock.schedule_once(lambda dt: self._msg(f"Nie znaleziono danych dla: {ticker}", False))
            return

        p = data['price']
        closes = data.get('closes', [])
        volumes = data.get('volumes', []) 

        sma14 = calc_sma(closes, 14, p)
        sma30 = calc_sma(closes, 30, p)
        sma50 = calc_sma(closes, 50, p)
        sma90 = calc_sma(closes, 90, p)
        sma200 = calc_sma(closes, 200, p)

        rsi = calculate_rsi(closes, 14) if len(closes) > 14 else 50.0
        macd, sig, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
        trade_signal = generate_signal(rsi, macd, sig)

        vol_trend = "Brak"
        if len(volumes) > 5:
            avg_vol = sum(volumes[-5:]) / 5
            vol_trend = "[color=#00AA00]Powyżej śred.[/color]" if data.get('vol', 0) > avg_vol else "[color=#FF0000]Poniżej śred.[/color]"

        score = 0
        if rsi <= 42: score += 2
        elif rsi >= 68: score -= 2
        if macd > sig: score += 1
        else: score -= 1
        if p > sma200: score += 1
        if p < sma50: score += 0.5
        try:
            if data.get('pe') != "N/A" and 0 < float(data.get('pe', 0)) < 28: score += 1
        except:
            pass

        if score >= 2.5: rec_text = "[color=#00AA00][b]ZDECYDOWANIE TAK[/b][/color]"
        elif 0 <= score < 2.5: rec_text = "[color=#FF9900][b]NEUTRALNIE[/b][/color]"
        else: rec_text = "[color=#FF0000][b]NIE / RYZYKO[/b][/color]"

        days_to_earnings = "Brak danych"
        if data['next_earnings'] != "Brak danych":
            try:
                next_date = datetime.strptime(data['next_earnings'], '%Y-%m-%d')
                delta = (next_date - datetime.now()).days
                if delta >= 0: days_to_earnings = f"za {delta} dni"
                else: days_to_earnings = f"{abs(delta)} dni temu"
            except:
                pass

        cap_str = format_market_cap(data.get('market_cap', 0))
        news_section = "\n\n".join(data['news']) if data['news'] else "Brak najnowszych wiadomości."

        search_query = data['name'].replace(' ', '+')
        google_link = f"https://www.google.com/search?q={search_query}+stock"

        post_p = data.get('post_price', 0.0)
        post_market_str = f" | Post-Market: {post_p:.2f} USD" if post_p > 0 else ""

        name = normalize_company_name(ticker, data.get('name', ticker))
        display_ticker = f"{ticker} ({name})" if name and name.upper() != ticker.upper() else ticker

        output = (
            f"Spółka: [b][ref={google_link}][color=#0000FF]{display_ticker}[/color][/ref][/b]\n"
            f"Rekomendacja: {rec_text} | Sygnał: {trade_signal}\n"
            f"----------------------------------------------------\n"
            f"[b]📊 DANE RYNKOWE i WOLUMEN:[/b]\n"
            f"• Kurs główny: [b]{p:.2f} USD[/b]{post_market_str}\n"
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
            f"• SMA 14: {sma14:.2f} | SMA 30: {sma30:.2f} | SMA 50: {sma50:.2f}\n"
            f"• SMA 90: {sma90:.2f} | SMA 200: {sma200:.2f}\n"
            f"• RSI (14): {rsi:.1f} | MACD: {macd:.3f} (Sygnał: {sig:.3f})\n"
            f"----------------------------------------------------\n"
            f"[b]📰 NAJNOWSZE WIADOMOŚCI:[/b]\n{news_section}"
        )
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
        btn_test = MDRaisedButton(text="TEST Powiadomień", on_release=self.run_notification_test, md_bg_color=(0, 0.5, 0, 1))

        button_layout.add_widget(btn_refresh)
        button_layout.add_widget(btn_test)
        self.control_panel.add_widget(button_layout)
        self.last_notified_titles = []

    def get_category_tag(self, title):
        t = title.lower()
        if any(x in t for x in ['fda', 'pdufa', 'adcom', 'approval', 'approve', 'decision', 'clinical', 'trial', 'phase', 'biotech', 'nda', 'bla', 'crl', 'readout', 'topline']):
            return "FDA/PDUFA"
        if any(x in t for x in ['earnings', 'wyniki', 'raport', 'revenue']):
            return "WYNIKI"
        if any(x in t for x in ['merger', 'acquisition', 'fuzja', 'buyout']):
            return "FUZJE/M&A"
        return None

    def get_catalyst_context(self, title):
        t = title.lower()
        if any(x in t for x in ['fda', 'pdufa', 'adcom', 'approval', 'decision', 'nda', 'bla', 'crl']):
            return "Kontekst: decyzja regulacyjna FDA / PDUFA."
        if any(x in t for x in ['clinical', 'trial', 'phase', 'readout', 'topline']):
            return "Kontekst: wynik badania klinicznego / odczyt danych."
        if any(x in t for x in ['earnings', 'wyniki', 'raport', 'revenue']):
            return "Kontekst: raport wynikowy / publikacja finansowa."
        return ""

    def run_notification_test(self, *args):
        MDApp.get_running_app().send_notification(title="Test Powiadomienia", message="Test udany!")

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
        kat_tickers = []

        try:
            app = MDApp.get_running_app()
            watch_list = []
            if hasattr(app, 'tabs_instances'):
                skaner = next((t for t in app.tabs_instances if isinstance(t, SkanerTab)), None)
                if skaner:
                    watch_list = getattr(skaner, 'static_tickers', [])

            top_gainers = fetch_top_gainers_by_type("day_gainers")[:8]
            if top_gainers:
                for tg in top_gainers:
                    if tg not in kat_tickers:
                        kat_tickers.append(tg)
                gainer_q = " OR ".join(top_gainers)
                g_news_req = safe_request(f"https://query2.finance.yahoo.com/v1/finance/search?q={gainer_q}&newsCount=20", headers=HEADERS, timeout=5)
                if g_news_req.status_code == 200:
                    for n in g_news_req.json().get("news", []):
                        pub_time = n.get('providerPublishTime', 0)
                        if pub_time < timestamp_threshold:
                            continue
                        rel = n.get('relatedTickers', [])
                        if rel and rel[0] in top_gainers:
                            title = n.get('title', '')
                            cat = self.get_category_tag(title)
                            if cat:
                                raw_news_entries.append({'ticker': rel[0], 'title': title, 'link': n.get('link', ''), 'cat': cat})

            res_earn = safe_request(url_earnings, headers=HEADERS, timeout=5)
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

            search_query = "PDUFA calendar OR FDA approval upcoming OR clinical trial catalysts OR FDA decision"
            res_news = safe_request(f"https://query2.finance.yahoo.com/v1/finance/search?q={search_query}&newsCount=40", headers=HEADERS, timeout=5)
            if res_news.status_code == 200:
                for n in res_news.json().get("news", []):
                    pub_time = n.get('providerPublishTime', 0)
                    title = n.get('title', '')
                    cat = self.get_category_tag(title)

                    if cat:
                        is_calendar_article = any(k in title.lower() for k in ['calendar', 'upcoming', 'look ahead', 'catalyst', 'schedule'])
                        threshold = int((now - timedelta(days=14)).timestamp()) if is_calendar_article else timestamp_threshold
                        if pub_time < threshold:
                            continue

                        rel = n.get('relatedTickers', [])
                        ticker = rel[0] if rel else "RYNEK"
                        if ticker not in kat_tickers and ticker != "RYNEK": 
                            kat_tickers.append(ticker)

                        if is_auto and title not in self.last_notified_titles:
                            MDApp.get_running_app().send_notification(f"Katalizator: {ticker}", title)
                            self.last_notified_titles.append(title)

                        raw_news_entries.append({'ticker': ticker, 'title': title, 'link': n.get('link', ''), 'cat': cat})

            needed_tickers = [t for t in kat_tickers if t not in app.shared_cache]
            if needed_tickers:
                try:
                    new_bulk = fetch_bulk_ticker_data(needed_tickers)
                    with CACHE_LOCK:
                        app.shared_cache.update(new_bulk)
                except Exception as e:
                    print(f"needed_tickers update error: {e}")

            micro_cap_news = []
            for entry in raw_news_entries:
                ticker = entry['ticker']
                title = entry['title']
                link = entry['link']
                cat = entry['cat']
                catalyst_context = self.get_catalyst_context(title)

                if ticker != "RYNEK":
                    comp_name = normalize_company_name(ticker, app.shared_cache.get(ticker, {}).get('name', ticker))
                    cap_raw = app.shared_cache.get(ticker, {}).get('market_cap', 0)
                    cap_str = format_market_cap(cap_raw)
                    display_ticker = f"{ticker} ({comp_name})" if comp_name and comp_name.upper() != ticker.upper() else ticker
                    extra = f"\n{catalyst_context}" if catalyst_context else ""
                    card_text = f"[color=#FF33CC][b][{cat}][/b][/color] [color=#008080][b]{display_ticker}[/b][/color]\nKapitalizacja rynkowa: [b]{cap_str}[/b]{extra}\n[ref={link}]{title}[/ref]"
                else:
                    extra = f"\n{catalyst_context}" if catalyst_context else ""
                    card_text = f"[color=#FF33CC][b][{cat}][/b][/color] [color=#008080][b]RYNEK SEKTOROWY / BIO[/b][/color]{extra}\n[ref={link}]{title}[/ref]"

                if card_text not in micro_cap_news:
                    micro_cap_news.append(card_text)

            final_cal = {}
            for info in calendar_data.values():
                events_list = []
                for item in info["raw_items"]:
                    sym = item.get('symbol')
                    tag_color = "#0000FF" if sym in watch_list else "#00FFCC"
                    tag = "[WATCHLIST]" if sym in watch_list else "[MID/LARGE]"

                    comp_name = normalize_company_name(sym, app.shared_cache.get(sym, {}).get('name', sym))
                    display_ticker = f"{sym} ({comp_name})" if comp_name and comp_name.upper() != sym.upper() else sym

                    cap_raw = app.shared_cache.get(sym, {}).get('market_cap', 0)
                    cap_str = format_market_cap(cap_raw)

                    ev = f"[color={tag_color}]{tag}[/color] [b][ref=https://finance.yahoo.com/quote/{sym}/]{display_ticker}[/ref][/b]\nKapitalizacja: {cap_str} | Prognoza EPS: {item.get('epsEstimate')}"
                    if ev not in events_list:
                        events_list.append(ev)

                final_cal[info["label"]] = events_list if events_list else ["Brak raportów."]

            Clock.schedule_once(lambda dt: self._render(final_cal, micro_cap_news))
        except:
            pass

    def _render(self, calendar, micro_cap_news):
        self.content.clear_widgets()
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

    def _fetch(self, *args):
        app = MDApp.get_running_app()
        watch_list = []
        if hasattr(app, 'tabs_instances'):
            skaner = next((t for t in app.tabs_instances if isinstance(t, SkanerTab)), None)
            if skaner: watch_list = getattr(skaner, 'static_tickers', [])
        
        now = datetime.now()
        yesterday_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
        timestamp_threshold = int(yesterday_start.timestamp())
        
        watchlist_news = []
        if watch_list:
            query = " OR ".join(watch_list[:15])
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&newsCount=30"
            try:
                res = safe_request(url, headers=HEADERS, timeout=8)
                if res.status_code == 200:
                    for n in res.json().get("news", []):
                        pub_time = n.get('providerPublishTime', 0)
                        if pub_time < timestamp_threshold: continue
                        
                        rel = n.get('relatedTickers', [])
                        if any(t in watch_list for t in rel):
                            watchlist_news.append(f"[color=#00FFFF][b]{rel[0]}[/b][/color] | WATCHLIST\n[ref={n.get('link')}]{n.get('title')}[/ref]")
            except: pass

        if not watchlist_news:
            fallback_url = "https://query2.finance.yahoo.com/v1/finance/search?q=stocks market trading federal reserve economy&newsCount=20"
            try:
                res = safe_request(fallback_url, headers=HEADERS, timeout=5)
                if res.status_code == 200:
                    for n in res.json().get("news", []):
                        pub_time = n.get('providerPublishTime', 0)
                        if pub_time < timestamp_threshold: continue
                        
                        watchlist_news.append(f"[color=#FF9900][b]RYNEK GLOBALNY[/b][/color] | Wiadomości Ogólne\n[ref={n.get('link')}]{n.get('title')}[/ref]\n[color=#888888]Źródło: {n.get('publisher')}[/color]")
            except: pass

        Clock.schedule_once(lambda dt: self._render_news(watchlist_news))

    def _render_news(self, news_list):
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text="[b][color=#00FFFF]📰 AKTUALNOŚCI I NOWOŚCI RYNKOWE[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
        for news in news_list: self.content.add_widget(DataCard(text=news))


class CfdShortTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "CFD/Własne"
        super().__init__(**kw)
        self.custom_tickers = ["GC=F", "PLN=X", "BTC-USD"]
        self.control_panel.height = dp(115)

        self.load_stored_data()

        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(48), spacing=dp(8))
        self.input_field = MDTextField(hint_text="Ticker (np. AAPL)", size_hint_x=0.66, mode="rectangle")
        btn_add = MDRaisedButton(text="+", size_hint_x=0.17, on_release=self.add_ticker)
        btn_rem = MDRaisedButton(text="-", size_hint_x=0.17, on_release=self.remove_ticker)

        input_row.add_widget(self.input_field)
        input_row.add_widget(btn_add)
        input_row.add_widget(btn_rem)

        self.control_panel.add_widget(input_row)
        self.control_panel.add_widget(MDRaisedButton(text="Uruchom 4-Sekcyjną Analizę", on_release=lambda x: self.refresh_data(force=True), pos_hint={"center_x": 0.5}))

    def load_stored_data(self):
        app = MDApp.get_running_app()
        if not app: return
        path = os.path.join(app.user_data_dir, "cfd_tickers.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, list) and saved: self.custom_tickers = saved
            except: pass

    def save_stored_data(self):
        app = MDApp.get_running_app()
        path = os.path.join(app.user_data_dir, "cfd_tickers.json")
        try:
            with open(path, "w", encoding="utf-8") as f: json.dump(self.custom_tickers, f)
        except: pass

    def add_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        self.input_field.text = ""
        if t and t not in self.custom_tickers:
            self.custom_tickers.append(t)
            self.save_stored_data()
            self.refresh_data()

    def remove_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        self.input_field.text = ""
        if t in self.custom_tickers:
            self.custom_tickers.remove(t)
            self.save_stored_data()
            self.refresh_data()

    def refresh_data(self, *args, **kwargs):
        force = kwargs.get('force', False)
        if hasattr(super(), 'refresh_data'):
            super().refresh_data(*args, force=force)
        else:
            threading.Thread(target=self._fetch, kwargs={"force": force}, daemon=True).start()

    def _fetch(self, *args, **kwargs):
        force = kwargs.get('force', False)
        sec_a = [", ".join(self.custom_tickers) if self.custom_tickers else "Brak danych"]
        sec_b_temp, sec_c, sec_d_temp = [], [], []

        nasdaq_100_pool = [
            "TSLA", "AMZN", "GOOGL", "GOOG", "META", "NFLX", "AVGO", "COST", "PEP", "ADBE",
            "QCOM", "INTC", "AMD", "MSFT", "AAPL", "NVDA", "CRM", "NOW", "MU", "ARM",
            "MRVL", "TSM", "ISRG", "BKNG", "TXN", "LRCX", "PANW", "INTU", "HON", "CSCO"
        ]
        spolki_spoza_nasdaq = [
            "PLTR", "SOFI", "RIVN", "NIO", "SNOW", "UBER", "SHOP", "HOOD", "BABA", "CRWD",
            "ZS", "SMCI", "XPEV", "LI", "DBI", "LE", "UNFI", "MSTR", "SQ", "PYPL",
            "GE", "DIS", "JPM", "BAC", "XOM", "CVX", "WMT", "TGT", "NKE", "F",
            "GM", "COIN", "RIOT", "MARA", "SNAP", "PINS", "TTD", "ABNB", "LYFT",
            "CDPROJEKT.WA"
        ]

        required_tickers = list(dict.fromkeys(self.custom_tickers + nasdaq_100_pool + spolki_spoza_nasdaq))
        app = MDApp.get_running_app()

        is_cache_fresh = app.cache_time and (datetime.now() - app.cache_time).total_seconds() < 120 and not force

        if is_cache_fresh and all(sym in app.shared_cache for sym in required_tickers):
            bulk_data = app.shared_cache.copy()
        else:
            all_to_fetch = list(dict.fromkeys(required_tickers + list(app.shared_cache.keys())))
            bulk_data = fetch_bulk_ticker_data(all_to_fetch)
            app.shared_cache.update(bulk_data)
            app.cache_time = datetime.now()

        def get_sma_color_str(val, p):
            color = "#3399FF" if p > val else "#FF9900"
            return f"[color={color}]{val:.2f}[/color]"

        for sym in bulk_data:
            data = bulk_data.get(sym)
            if not data or data.get('price', 0.0) == 0.0:
                continue

            p = data['price']
            name = normalize_company_name(sym, data.get('name', sym))
            display_ticker = f"{sym} ({name})" if name and name.upper() != sym.upper() else sym

            hist_prices = data.get('closes', [])

            sma14 = calc_sma(hist_prices, 14, p)
            sma30 = calc_sma(hist_prices, 30, p)
            sma50 = calc_sma(hist_prices, 50, p)
            sma90 = calc_sma(hist_prices, 90, p)

            sma_info = (
                f"SMA [b]14[/b]: {get_sma_color_str(sma14, p)}, "
                f"[b]30[/b]: {get_sma_color_str(sma30, p)}, "
                f"[b]50[/b]: {get_sma_color_str(sma50, p)}, "
                f"[b]90[/b]: {get_sma_color_str(sma90, p)}"
            )

            rsi = calculate_rsi(hist_prices, 14) if hist_prices else 50.0
            macd_v, sig_v, _ = calculate_macd(hist_prices)

            c_rsi = "#00AA00" if rsi <= 40 else ("#FF0000" if rsi >= 60 else "#888888")
            c_macd = "#00AA00" if macd_v > sig_v else "#FF0000"
            trade_signal = generate_signal(rsi, macd_v, sig_v)
            ind_str = (
                f"Wskaźniki: [color={c_rsi}]RSI: {rsi:.1f}[/color] | "
                f"[color={c_macd}]MACD: {macd_v:.2f}[/color]\n"
                f"Sygnał: {trade_signal}"
            )

            if sym not in self.custom_tickers:
                diff = p - sma14
                if diff > 1:
                    sec_b_temp.append((diff, f"[b]{display_ticker}[/b]\nCena: {p:.2f}\n{sma_info}\n{ind_str}"))

            if sym in self.custom_tickers:
                precision = 4 if p < 10 else 2
                sec_c.append(
                    f"[b]{display_ticker}[/b]\nKurs: {p:.{precision}f}\n"
                    f"{sma_info}\n"
                    f"{ind_str}\n"
                    f"[color=#00AA00]TP (+3%): {p*1.03:.{precision}f}[/color] | "
                    f"[color=#FF3333]SL (-2%): {p*0.98:.{precision}f}[/color]"
                )

            if p < sma90:
                diff = sma90 - p
                if diff > 1:
                    sec_d_temp.append((diff, f"[b]{display_ticker}[/b]\nCena: {p:.2f}\n{sma_info}\nRóżnica do SMA90: {diff:.2f}\n{ind_str}"))

        sec_b_temp.sort(key=lambda x: x[0], reverse=True)
        sec_b = [item[1] for item in sec_b_temp]

        sec_d_temp.sort(key=lambda x: x[0], reverse=True)
        sec_d = [item[1] for item in sec_d_temp]

        if not sec_b: sec_b.append("Brak spółek spełniających warunki.")
        if not sec_c: sec_c.append("Brak danych.")
        if not sec_d: sec_d.append("Brak spółek poniżej średniej.")

        payload = {
            "A: ZAPISANE TICKERY": sec_a, 
            "B: ANALIZA TRANSAKCYJNA": sec_c, 
            "C: WYBICIE POWYŻEJ ŚREDNIEJ (SMA14)": sec_b, 
            "D: ODBICIE OD DNA PONIŻEJ (SMA90)": sec_d
        }
        Clock.schedule_once(lambda dt: self._render(payload))

    def _render(self, payload):
        self.content.clear_widgets()
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

        Clock.schedule_once(self.init_tabs_delayed, 0)
        
    def init_tabs_delayed(self, dt):
        self.tabs_instances = [InfoTab(), SkanerTab(), TickerTab(), KatalizatoryTab(), NewsTab(), CfdShortTab()]
        for tab in self.tabs_instances: self.tabs_container.add_widget(tab)
            
        if hasattr(self.tabs_instances[1], 'load_stored_data'): self.tabs_instances[1].load_stored_data()
        if hasattr(self.tabs_instances[5], 'load_stored_data'): self.tabs_instances[5].load_stored_data()
        
        self.app_ready = True
        Clock.schedule_once(lambda dt: self.tabs_instances[1].load_data_if_needed(), 0.5)
        if not IS_GITHUB:
            Clock.schedule_once(self.background_prefetch, 2.0)
            Clock.schedule_interval(self.cron_time_checker, 60)
    
    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if not getattr(self, 'app_ready', False): return
        if hasattr(instance_tab, 'load_data_if_needed'): instance_tab.load_data_if_needed()

    def background_prefetch(self, dt):
        delay = 0.5
        for i, tab in enumerate(self.tabs_instances[1:]):
            if hasattr(tab, 'is_loaded') and not tab.is_loaded:
                def make_callback(t): return lambda dt: t.load_data_if_needed()
                Clock.schedule_once(make_callback(tab), delay * (i + 1))

    def on_resume(self):
        if getattr(self, 'app_ready', False):
            for tab in self.tabs_instances: 
                if hasattr(tab, 'refresh_data'): tab.refresh_data()

    def cron_time_checker(self, dt):
        now = datetime.now()
        if now.weekday() in range(0, 5) and now.minute == 0:
            if now.hour in [11, 13, 15]:
                for tab in self.tabs_instances:
                    if not hasattr(tab, 'refresh_data'): continue
                    if isinstance(tab, KatalizatoryTab): tab.refresh_data(True)
                    else: tab.refresh_data()
                        
    def send_notification(self, title, message):
        try:
            if notification:
                notification.notify(title=title, message=message, app_name='StockScanner', timeout=10)
        except Exception as e: print(f"Błąd powiadomienia Plyer: {e}")
            
        try:
            Clock.schedule_once(lambda dt: MDSnackbar(
                MDLabel(text=f"🔔 [b]{title}:[/b] {message}", theme_text_color="Custom", text_color=[1, 1, 1, 1], markup=True),
                background_color=[0, 0.4, 0.4, 1], duration=5
            ).open())
        except Exception as ex: print(f"Błąd paska Snackbar: {ex}")

if __name__ == '__main__':
    StockScannerPro().run()
