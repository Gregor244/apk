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

from kivy.clock import Clock
from kivy.utils import platform
from kivy.metrics import dp
from kivymd.app import MDApp
from kivymd.uix.screen import MDScreen
from kivymd.uix.tab import MDTabs, MDTabsBase
from kivymd.uix.boxlayout import MDBoxLayout
from kivymd.uix.label import MDLabel
from kivymd.uix.card import MDCard
from kivymd.uix.button import MDRaisedButton
from kivymd.uix.textfield import MDTextField
from kivy.uix.scrollview import ScrollView
from kivymd.uix.snackbar import MDSnackbar

os.environ['SSL_CERT_FILE'] = certifi.where()

# Bezpieczny import plyer (zapobiega crashowi w przypadku braku biblioteki)
try:
    from plyer import notification
except ImportError:
    notification = None

# Importy specyficzne dla Androida
if platform == 'android':
    from android.permissions import request_permissions, Permission

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
FINNHUB_KEY = "d82t3s1r01ql4onfbbngd82t3s1r01ql4onfbbo0"

PL_DAYS = {
    "Monday": "PONIEDZIAŁEK", "Tuesday": "WTOREK", "Wednesday": "ŚRODA",
    "Thursday": "CZWARTEK", "Friday": "PIĄTEK", "Saturday": "SOBOTA", "Sunday": "NIEDZIELA"
}

# ---------------------------------------------------------
# FUNKCJE POBIERAJĄCE DANE (YAHOO FINANCE - SKANER / CFD)
# ---------------------------------------------------------

def fetch_top_gainers():
    url = "https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds=day_gainers&count=15"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        if res.status_code == 200:
            result = res.json().get('finance', {}).get('result')
            if result and isinstance(result, list) and len(result) > 0:
                return result[0].get('quotes', [])
    except: pass
    return []

def fetch_top_gainers_by_type(scr_id="day_gainers"):
    url = f"https://query2.finance.yahoo.com/v1/finance/screener/predefined/saved?formatted=true&lang=en-US&region=US&scrIds={scr_id}&count=20"
    try:
        res = requests.get(url, headers=HEADERS, timeout=5)
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
        'volume': 0, 'volume_trend': "[color=#888888]Brak danych[/color]", 'market_state': "REGULAR",
        'pre_price': None, 'pre_change_pct': 0.0, 'pre_change_amt': 0.0,
        'post_price': None, 'post_change_pct': 0.0, 'post_change_amt': 0.0,
        'closes': [], 'high': 0.0, 'low': 0.0, 'open': 0.0,
        'pe': "N/A", 'day_low': 0.0, 'day_high': 0.0, 'year_low': 0.0, 'year_high': 0.0
    }
    
    try:
        rq = requests.get(quote_url, headers=HEADERS, timeout=5)
        if rq.status_code == 200:
            q_res = rq.json().get('quoteResponse', {}).get('result', [])
            if q_res:
                q = q_res[0]
                res_data['name'] = q.get('longName') or q.get('shortName') or ticker
                res_data['price'] = q.get('regularMarketPrice', 0.0)
                res_data['prev_close'] = q.get('regularMarketPreviousClose', 0.0)
                res_data['volume'] = q.get('regularMarketVolume', 0)
                res_data['market_state'] = q.get('marketState', 'REGULAR')
                
                res_data['pe'] = q.get('trailingPE', "N/A")
                res_data['day_low'] = q.get('regularMarketDayLow', 0.0)
                res_data['day_high'] = q.get('regularMarketDayHigh', 0.0)
                res_data['year_low'] = q.get('fiftyTwoWeekLow', 0.0)
                res_data['year_high'] = q.get('fiftyTwoWeekHigh', 0.0)
                
                if q.get('preMarketPrice'):
                    res_data['pre_price'] = q.get('preMarketPrice')
                    res_data['pre_change_pct'] = q.get('preMarketChangePercent', 0.0)
                    res_data['pre_change_amt'] = q.get('preMarketChange', 0.0)
                if q.get('postMarketPrice'):
                    res_data['post_price'] = q.get('postMarketPrice')
                    res_data['post_change_pct'] = q.get('postMarketChangePercent', 0.0)
                    res_data['post_change_amt'] = q.get('postMarketChange', 0.0)
    except: pass
        
    try:
        rc = requests.get(chart_url, headers=HEADERS, timeout=5)
        if rc.status_code == 200:
            c_res = rc.json().get('chart', {}).get('result', [])
            if c_res:
                indicators = c_res[0].get('indicators', {}).get('quote', [{}])[0]
                closes = [c for c in indicators.get('close', []) if c is not None]
                volumes = [v for v in indicators.get('volume', []) if v is not None]
                opens = [o for o in indicators.get('open', []) if o is not None]
                highs = [h for h in indicators.get('high', []) if h is not None]
                lows = [l for l in indicators.get('low', []) if l is not None]
                
                res_data['closes'] = closes
                if opens: res_data['open'] = opens[-1]
                if highs: res_data['high'] = highs[-1]
                if lows: res_data['low'] = lows[-1]
                
                if len(volumes) >= 2:
                    if volumes[-1] > volumes[-2]:
                        res_data['volume_trend'] = "[color=#00AA00]Rosnący 📈[/color]"
                    else:
                        res_data['volume_trend'] = "[color=#FF0000]Spadający 📉[/color]"
    except: pass
        
    return res_data
    
def fetch_bulk_ticker_data(tickers):
    bulk_results = {}
    def worker(ticker):
        return ticker, fetch_ticker_data(ticker)
        
    with ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(worker, tickers)
        for ticker, data in results:
            if data and data.get('price', 0.0) > 0:
                bulk_results[ticker] = data
    return bulk_results

# ---------------------------------------------------------
# ZMODYFIKOWANA FUNKCJA POBIERAJĄCA DANE (FINNHUB - TICKER TAB)
# ---------------------------------------------------------

def fetch_finnhub_ticker_data(ticker):
    base_url = "https://finnhub.io/api/v1"
    params = {"symbol": ticker, "token": FINNHUB_KEY}
    
    res_data = {
        'symbol': ticker, 'name': ticker, 'price': 0.0, 'pe': "N/A", 
        'market_cap': "N/A", 'day_low': 0.0, 'day_high': 0.0, 'closes': [],
        'volume': 0, 'eps': "N/A", 'div_yield': "N/A", 
        'week52_high': 0.0, 'week52_low': 0.0, 'volumes': [],
        'next_earnings': "Brak danych", 'prev_earnings_period': "Brak",
        'prev_earnings_surprise': "Brak danych", 'news': [],
        'earnings_reaction': "Brak danych"
    }
    
    try:
        quote = requests.get(f"{base_url}/quote", params=params, timeout=5).json()
        if 'c' in quote and quote['c'] != 0:
            res_data['price'] = quote['c']
            res_data['day_high'] = quote['h']
            res_data['day_low'] = quote['l']
            
        profile = requests.get(f"{base_url}/stock/profile2", params=params, timeout=5).json()
        res_data['name'] = profile.get('name', ticker)
        
        # NAPRAWIONO: Finnhub podaje market cap w milionach, dzielimy przez 1000 aby uzyskać miliardy (mld)
        market_cap = profile.get('marketCapitalization', 0)
        if market_cap:
            res_data['market_cap'] = f"{market_cap / 1000:.2f} mld USD"
        else:
            res_data['market_cap'] = "Brak danych"
        
        metrics = requests.get(f"{base_url}/stock/metric", params={"symbol": ticker, "metric": "all", "token": FINNHUB_KEY}, timeout=5).json()
        if 'metric' in metrics:
            m = metrics['metric']
            pe = m.get('peBasicAnnual', 'N/A')
            res_data['pe'] = f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A"
            eps = m.get('epsTTM', 'N/A')
            res_data['eps'] = f"{eps:.2f}" if isinstance(eps, (int, float)) else "N/A"
            div = m.get('dividendYieldIndicatedAnnual', 'N/A')
            res_data['div_yield'] = f"{div:.2f}%" if isinstance(div, (int, float)) else "Brak"
            res_data['week52_high'] = m.get('52WeekHigh', 0.0)
            res_data['week52_low'] = m.get('52WeekLow', 0.0)
            
        now = int(time.time())
        past = now - (500 * 86400)  # NAPRAWIONO: Zwiększono zakres do 500 dni, by zapewnić odpowiednią ilość świec (>200)
        candles = requests.get(f"{base_url}/stock/candle", params={"symbol": ticker, "resolution": "D", "from": past, "to": now, "token": FINNHUB_KEY}, timeout=5).json()
        
        if candles.get('s') == 'ok' and candles.get('c'):
            res_data['closes'] = candles.get('c', [])
            res_data['volumes'] = candles.get('v', [])
            if res_data['volumes']:
                # NAPRAWIONO: Pobieranie ostatniego niezerowego wolumenu (zapobiega 0 w pre-market/weekendy)
                valid_vols = [v for v in res_data['volumes'] if v > 0]
                res_data['volume'] = valid_vols[-1] if valid_vols else res_data['volumes'][-1]
        else:
            # NAPRAWIONO: Niezawodny FALLBACK do Yahoo Finance Chart, gdy Finnhub nie ma lub blokuje świece historyczne
            try:
                fallback_url = f"https://query2.finance.yahoo.com/v8/finance/chart/{ticker}?interval=1d&range=1y"
                rc = requests.get(fallback_url, headers=HEADERS, timeout=5)
                if rc.status_code == 200:
                    c_res = rc.json().get('chart', {}).get('result', [])
                    if c_res:
                        indicators = c_res[0].get('indicators', {}).get('quote', [{}])[0]
                        res_data['closes'] = [c for c in indicators.get('close', []) if c is not None]
                        res_data['volumes'] = [v for v in indicators.get('volume', []) if v is not None]
                        if res_data['volumes']:
                            valid_vols = [v for v in res_data['volumes'] if v > 0]
                            res_data['volume'] = valid_vols[-1] if valid_vols else res_data['volumes'][-1]
            except Exception as ex:
                print(f"Błąd fallback Yahoo: {ex}")
                
        today = datetime.now().date()
        future = today + timedelta(days=90)
        
        past_earn = requests.get(f"{base_url}/stock/earnings", params=params, timeout=5).json()
        if past_earn and isinstance(past_earn, list):
            last_e = past_earn[0]
            res_data['prev_earnings_period'] = last_e.get('period', 'Nieznany')
            actual = last_e.get('actual')
            est = last_e.get('estimate')
            if actual is not None and est is not None:
                surprise_pct = ((actual - est) / abs(est)) * 100 if est != 0 else 0
                znak = "+" if surprise_pct > 0 else ""
                res_data['prev_earnings_surprise'] = f"{znak}{surprise_pct:.1f}% (Akt: {actual:.2f}, Szac: {est:.2f})"
        
        earn_cal = requests.get(f"{base_url}/calendar/earnings", params={"symbol": ticker, "from": today.strftime('%Y-%m-%d'), "to": future.strftime('%Y-%m-%d'), "token": FINNHUB_KEY}, timeout=5).json()
        if 'earningsCalendar' in earn_cal and earn_cal['earningsCalendar']:
            res_data['next_earnings'] = earn_cal['earningsCalendar'][0].get('date', 'Brak danych')

        past_week = today - timedelta(days=7)
        news = requests.get(f"{base_url}/company-news", params={"symbol": ticker, "from": past_week.strftime('%Y-%m-%d'), "to": today.strftime('%Y-%m-%d'), "token": FINNHUB_KEY}, timeout=5).json()
        if isinstance(news, list):
            for n in news[:3]:
                title = n.get('headline', '')
                url = n.get('url', '')
                if title and url:
                    res_data['news'].append(f"• {title}\n  Link: {url}")
            
        res_data['found'] = True
    except Exception as e:
        print(f"Błąd Finnhub: {e}")
        res_data['found'] = False
        
    return res_data

# ---------------------------------------------------------
# ANALIZA TECHNICZNA
# ---------------------------------------------------------

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

# ---------------------------------------------------------
# INTERFEJS GRAFICZNY I KOMPONENTY
# ---------------------------------------------------------

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
        self.lbl.bind(on_ref_press=lambda instance, ref: webbrowser.open(ref))
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
            orientation="vertical", 
            size_hint_y=None, 
            height=dp(0),
            padding=[dp(12), dp(16), dp(12), dp(12)], # NAPRAWIONO: Zwiększony padding paneli górnych
            spacing=dp(10)
        )
        self.add_widget(self.control_panel)
        
        self.scroll = ScrollView()
        self.content = MDBoxLayout(
            orientation="vertical", 
            spacing=dp(8), 
            size_hint_y=None,
            padding=[dp(8), dp(8)]
        )
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

    def _fetch(self, *args, **kwargs):
        pass

    def _show_error(self, message):
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(
            text=f"[color=#FF0000][b]{message}[/b][/color]", 
            markup=True, 
            halign="center"
        ))
        btn = MDRaisedButton(text="Ponów próbę", on_release=self.refresh_data)
        self.content.add_widget(btn)

# ---------------------------------------------------------
#  ZAKŁADKA_INFO
# --------------------------------------------------------

class InfoTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Info"
        super().__init__(**kw)
        self.control_panel.height = dp(65)
        self.control_panel.add_widget(MDRaisedButton(
            text="Sprawdź Status Rynków", 
            on_release=lambda x: self.refresh_data(), 
            pos_hint={"center_x": 0.5}
        ))

    def _fetch(self, *args, **kwargs):
        try:
            url = f"https://finnhub.io/api/v1/stock/market-status?exchange=US&token={FINNHUB_KEY}"
            status_data = requests.get(url, timeout=5).json()
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
        for line in lines: 
            self.content.add_widget(DataCard(text=line))

        
# ---------------------------------------------------------
# ZAKŁADKA_SKANER_TAB
# ---------------------------------------------------------

class SkanerTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Skaner"
        super().__init__(**kw)
        self.static_tickers = ["AAPL", "MSFT", "NVDA", "AMD", "SNDK", "MU", "AMZN", "ARM", "MRVL", "NOW", "QUCY"]
        self.control_panel.height = dp(140) # NAPRAWIONO: Zwiększona wysokość pod paski UI
        
        self.load_stored_data()
        
        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8))
        # NAPRAWIONO: mode="outline" zapobiega nakładaniu się etykiet hint_text
        self.input_field = MDTextField(hint_text="Wpisz ticker (np. TSLA)", size_hint_x=0.66, mode="outline")
        btn_add = MDRaisedButton(text="+", size_hint_x=0.17, on_release=self.add_ticker)
        btn_rem = MDRaisedButton(text="-", size_hint_x=0.17, on_release=self.remove_ticker)
        
        input_row.add_widget(self.input_field)
        input_row.add_widget(btn_add)
        input_row.add_widget(btn_rem)
        
        self.control_panel.add_widget(input_row)
        self.control_panel.add_widget(MDRaisedButton(text="Skanuj rynki + Wskaźniki", on_release=self.refresh_data, pos_hint={"center_x": 0.5}))

    def load_stored_data(self):
        app = MDApp.get_running_app()
        if not app: return
        path = os.path.join(app.user_data_dir, "skaner_tickers.json")
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                    if isinstance(saved, list) and saved: 
                        self.static_tickers = saved
            except Exception: 
                pass

    def save_stored_data(self):
        app = MDApp.get_running_app()
        path = os.path.join(app.user_data_dir, "skaner_tickers.json")
        try:
            with open(path, "w", encoding="utf-8") as f: 
                json.dump(self.static_tickers, f)
        except Exception: 
            pass

    def add_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t and t not in self.static_tickers:
            self.static_tickers.append(t)
            self.save_stored_data()
            self.input_field.text = ""
            self.refresh_data()

    def remove_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t in self.static_tickers:
            self.static_tickers.remove(t)
            self.save_stored_data()
            self.input_field.text = ""
            self.refresh_data()

    def is_market_open(self):
        now = datetime.now()
        return 15 <= now.hour < 22 and now.weekday() < 5

    def _fetch(self, *args, **kwargs):
        cards_data = []
        try:
            gainers_pre = fetch_top_gainers_by_type("pre_market_gainers")[:5]
            gainers_open = fetch_top_gainers_by_type("day_gainers")[:5]
            gainers_post = fetch_top_gainers_by_type("after_hours_gainers")[:5]
        except Exception:
            gainers_pre, gainers_open, gainers_post = [], [], []
        
        gainer_map = {}
        for s in gainers_pre: gainer_map[s] = "[color=#00FFFF][PRE-MARKET][/color]"
        for s in gainers_open: gainer_map[s] = "[color=#00FF00][MARKET OPEN][/color]"
        for s in gainers_post: gainer_map[s] = "[color=#CC33FF][POST-MARKET][/color]"
        
        all_tickers = list(dict.fromkeys(self.static_tickers + list(gainer_map.keys())))
        bulk_data = fetch_bulk_ticker_data(all_tickers)

        app = MDApp.get_running_app()
        app.shared_cache.update(bulk_data)
        app.cache_time = datetime.now()

        for sym in all_tickers:
            data = bulk_data.get(sym)
            if not data: 
                continue
            
            name = data.get('name', sym)
            market_state = data.get('market_state', 'REGULAR')
            regular_price = data.get('price', 0.0)
            prev_close = data.get('prev_close')
            
            chg_reg_val = (regular_price - prev_close) if prev_close else 0.0
            chg_reg_pct = ((regular_price - prev_close) / prev_close * 100) if prev_close and prev_close != 0 else 0.0
            price_details = f"Aktualny Kurs: [b]{regular_price:.2f} USD[/b] ({chg_reg_val:+.2f} USD | {chg_reg_pct:+.2f}%)\n"
                
            post_p = data.get('post_price')
            if post_p and post_p > 0:
                chg_post_val = (post_p - prev_close) if prev_close else data.get('post_change_amt', 0.0)
                chg_post_pct = ((post_p - prev_close) / prev_close * 100) if prev_close and prev_close != 0 else data.get('post_change_pct', 0.0)
                price_details += f"Post-Market: [b]{post_p:.2f} USD[/b] ({chg_post_val:+.2f} USD | {chg_post_pct:+.2f}%)\n"

            if market_state == "PRE": session_tag = "[color=#0000FF][b][PRE][/b][/color]"
            elif market_state == "POST": session_tag = "[color=#800080][b][POST][/b][/color]"
            elif self.is_market_open(): session_tag = "[color=#00FF00][b][AKTYWNY][/b][/color]"
            else: session_tag = "[color=#FF9900][b][ZAMKNIĘTY][/b][/color]"

            source_tag = "[color=#0000FF][WATCHLIST][/color]" if sym in self.static_tickers else gainer_map.get(sym, "[MARKET]")
            closes = data.get('closes', [])
            
            rsi_val = calculate_rsi(closes, 14) if closes else 50.0
            if rsi_val <= 35: rsi_str = f"[color=#00AA00][b]{rsi_val:.1f} (Wyprzedanie - KUP)[/b][/color]"
            elif rsi_val >= 65: rsi_str = f"[color=#FF0000][b]{rsi_val:.1f} (Wykupienie - SPRZEDAJ)[/b][/color]"
            else: rsi_str = f"[color=#777777]{rsi_val:.1f} (Neutralny)[/color]"

            macd_v, sig_v, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
            macd_str = f"[color=#00AA00]{macd_v:.2f}[/color]" if macd_v > sig_v else f"[color=#FF0000]{macd_v:.2f}[/color]"
            
            vol_trend = data.get('volume_trend', "Brak")
            trade_signal = generate_signal(rsi_val, macd_v, sig_v)
            
            sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else regular_price
            sma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else regular_price
            
            pe_val = data.get('pe', 'N/A')
            pe_str = f"{pe_val:.2f}" if isinstance(pe_val, (int, float)) else str(pe_val)

            txt = (
                f"{session_tag} {source_tag} [color=#008080][b]{sym} - {name}[/b][/color]\n"
                f"{price_details}"
                f"Wolumen: {data.get('volume', 0):,} ({vol_trend}) | P/E: [b]{pe_str}[/b]\n"
                f"RSI: {rsi_str} | MACD: {macd_str}\n"
                f"SMA50: {sma50:.2f} USD | SMA200: {sma200:.2f} USD\n"
                f"Sygnał: {trade_signal}"
            )
            cards_data.append(txt)

        Clock.schedule_once(lambda dt: self._render(cards_data))

    def _render(self, cards):
        self.content.clear_widgets()
        for c in cards: 
            self.content.add_widget(DataCard(text=c))

# ---------------------------------------------------------
#  ZAKŁADKA_TICKER
# --------------------------------------------------------

class TickerTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Ticker"
        super().__init__(**kw)
        self.control_panel.height = dp(140) # NAPRAWIONO: Zwiększono wysokość panelu
        
        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8))
        # NAPRAWIONO: mode="outline" usuwa problem nakładania się tekstu podpowiedzi na ramkę wejściową
        self.inp = MDTextField(hint_text="Wpisz ticker (np. TSLA)", size_hint_x=0.70, mode="outline")
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
        
        sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else p
        sma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else p
        rsi = calculate_rsi(closes, 14) if len(closes) > 14 else 50.0
        macd, sig, _ = calculate_macd(closes) if len(closes) > 35 else (0.0, 0.0, 0.0)
        trade_signal = generate_signal(rsi, macd, sig)
        
        vol_trend = "Brak"
        if len(volumes) > 5:
            avg_vol = sum(volumes[-5:]) / 5
            vol_trend = "Powyżej śred." if data['volume'] > avg_vol else "Poniżej śred."

        score = 0
        if rsi <= 42: score += 2
        elif rsi >= 68: score -= 2
        if macd > sig: score += 1
        else: score -= 1
        if p > sma200: score += 1
        if p < sma50: score += 0.5
        try:
            if 0 < float(data.get('pe', 0)) < 28: score += 1
        except: pass
            
        if score >= 2.5: rec_text = "[color=#00AA00][b]ZDECYDOWANIE TAK[/b][/color]"
        elif 0 <= score < 2.5: rec_text = "[color=#FF9900][b]NEUTRALNIE[/b][/color]"
        else: rec_text = "[color=#FF0000][b]NIE / RYZYKO[/b][/color]"

        news_section = "\n\n".join(data['news']) if data['news'] else "Brak najnowszych wiadomości."

        output = (
            f"Spółka: [b]{data['name']}[/b] ({data['symbol']})\n"
            f"Rekomendacja: {rec_text} | Sygnał: {trade_signal}\n"
            f"----------------------------------------------------\n"
            f"[b]DANE RYNKOWE:[/b]\n"
            f"• Kurs: [b]{p:.2f} USD[/b] | Wolumen: {int(data['volume']):,} ({vol_trend})\n"
            f"• Zakres 1D: {data['day_low']:.2f} - {data['day_high']:.2f} USD\n"
            f"• Zakres 52W: {data['week52_low']:.2f} - {data['week52_high']:.2f} USD\n"
            f"----------------------------------------------------\n"
            f"[b]WYNIKI (EARNINGS):[/b]\n"
            f"• Następny: [b]{data['next_earnings']}[/b]\n"
            f"• Poprzedni ({data['prev_earnings_period']}): {data['prev_earnings_surprise']}\n"
            f"----------------------------------------------------\n"
            f"[b]FUNDAMENTY:[/b]\n"
            f"• Kap.: {data['market_cap']} | P/E: [b]{data['pe']}[/b]\n"
            f"• EPS: {data['eps']} | Dyw.: {data.get('div_yield', 'N/A')}\n"
            f"----------------------------------------------------\n"
            f"[b]TECHNICZNIE:[/b]\n"
            f"• SMA 50: {sma50:.2f} | SMA 200: {sma200:.2f}\n"
            f"• RSI: {rsi:.1f} | MACD: {macd:.3f} (Syg: {sig:.3f})\n"
            f"----------------------------------------------------\n"
            f"[b]NEWSY:[/b]\n{news_section}"
        )
        
        Clock.schedule_once(lambda dt: self._msg(output, True))

    def _msg(self, txt, is_card=False):
        self.content.clear_widgets()
        if is_card: 
            self.content.add_widget(DataCard(text=txt))
        else: 
            self.content.add_widget(MDLabel(text=txt, halign="center"))

# ---------------------------------------------------------
#  ZAKŁADKA_KATALIZATORY
# --------------------------------------------------------

class KatalizatoryTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Katalizatory"
        super().__init__(**kw)
        self.control_panel.height = dp(65)
        button_layout = MDBoxLayout(orientation='horizontal', spacing=dp(10), pos_hint={"center_x": 0.5}, size_hint_x=None)
        button_layout.bind(minimum_width=button_layout.setter('width'))
        
        btn_refresh = MDRaisedButton(text="Pobierz Dane", on_release=self.refresh_data)
        btn_test = MDRaisedButton(text="TEST Powiadomień", on_release=self.run_notification_test, md_bg_color=(0, 0.5, 0, 1))
        
        button_layout.add_widget(btn_refresh)
        button_layout.add_widget(btn_test)
        self.control_panel.add_widget(button_layout)
        self.last_notified_titles = []
        
    def run_notification_test(self, *args):
        MDApp.get_running_app().send_notification(
            title="Test Powiadomienia", 
            message="Test udany! Jeśli nie ma baneru, system używa awaryjnego paska Snackbar na dole."
        )

    def _fetch(self, *args, **kwargs):
        is_auto = args[0] if (args and isinstance(args[0], bool)) else False
        now = datetime.now()
        start_date = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        end_date = (now + timedelta(days=10)).strftime("%Y-%m-%d")
        
        url_earnings = f"https://finnhub.io/api/v1/calendar/earnings?from={start_date}&to={end_date}&token={FINNHUB_KEY}"
        calendar_data = { (now + timedelta(days=i)).strftime("%Y-%m-%d"): {"label": f"{PL_DAYS.get((now + timedelta(days=i)).strftime('%A'), (now + timedelta(days=i)).strftime('%A')).upper()}, {(now + timedelta(days=i)).strftime('%d %B').upper()}", "events": []} for i in range(7) }
        micro_cap_news = []

        try:
            res_earn = requests.get(url_earnings, headers=HEADERS, timeout=5)
            app = MDApp.get_running_app()
            watch_list = []
            if app and hasattr(app, 'tabs_instances') and len(app.tabs_instances) > 1:
                skaner = app.tabs_instances[1]
                watch_list = getattr(skaner, 'static_tickers', [])

            if res_earn.status_code == 200:
                for item in res_earn.json().get('earningsCalendar', []):
                    date_str = item.get('date')
                    if date_str in calendar_data:
                        sym = item.get('symbol')
                        rev = item.get('revenueEstimate') or 0
                        if sym in watch_list or rev >= 250000000:
                            tag_color = "#0000FF" if sym in watch_list else "#00FFCC"
                            tag = "[WATCHLIST]" if sym in watch_list else "[MID/LARGE]"
                            ev = f"[color={tag_color}]{tag}[/color] [b][ref=https://finance.yahoo.com/quote/{sym}/]{sym}[/ref][/b]\nPrognoza EPS: {item.get('epsEstimate')}"
                            if ev not in calendar_data[date_str]["events"]: calendar_data[date_str]["events"].append(ev)

            search_query = "FDA OR biotech trial OR AI catalyst OR semiconductor OR space"
            res_news = requests.get(f"https://query2.finance.yahoo.com/v1/finance/search?q={search_query}&newsCount=10", headers=HEADERS, timeout=5)
            if res_news.status_code == 200:
                for n in res_news.json().get("news", []):
                    rel = n.get('relatedTickers', [])
                    if rel:
                        title = n.get('title')
                        ticker = rel[0]
                        if is_auto and title not in self.last_notified_titles:
                            MDApp.get_running_app().send_notification(f"Katalizator: {ticker}", title)
                            self.last_notified_titles.append(title)
                        micro_cap_news.append(f"[color=#000000][b]{ticker}[/b][/color] | [color=#FF9900][b]KATALIZATOR[/b][/color]\n[ref={n.get('link')}]{title}[/ref]")

            final_cal = {info["label"]: (info["events"] if info["events"] else ["Brak raportów."]) for info in calendar_data.values()}
            Clock.schedule_once(lambda dt: self._render(final_cal, micro_cap_news))
        except Exception as e:
            print(f"Błąd katalizatorów: {e}")

    def _render(self, calendar, micro_cap_news):
        self.content.clear_widgets()
        if micro_cap_news:
            self.content.add_widget(MDLabel(text="[b][color=#FF33CC]🔥 POTENCJALNE SKOKI (Wydarzenia rynkowe)[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
            for news in micro_cap_news: self.content.add_widget(DataCard(text=news))
        for day, events in calendar.items():
            self.content.add_widget(MDLabel(text=f"[b][color=#ff8c00]— KALENDARZ: {day} —[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
            for ev in events: self.content.add_widget(DataCard(text=ev))


# ---------------------------------------------------------
#  ZAKŁADKA_NEWS
# --------------------------------------------------------

class NewsTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "Newsy"
        super().__init__(**kw)
        self.control_panel.height = dp(65)
        self.control_panel.add_widget(MDRaisedButton(text="Odśwież Wiadomości", on_release=self.refresh_data, pos_hint={"center_x": 0.5}))

    def _fetch(self, *args, **kwargs):
        app = MDApp.get_running_app()
        watch_list = []
        if app and hasattr(app, 'tabs_instances') and app.tabs_instances:
            watch_list = getattr(app.tabs_instances[1], 'static_tickers', [])
        
        watchlist_news = []
        if watch_list:
            query = " OR ".join(watch_list[:15])
            url = f"https://query2.finance.yahoo.com/v1/finance/search?q={query}&newsCount=25"
            try:
                res = requests.get(url, headers=HEADERS, timeout=8)
                if res.status_code == 200:
                    for n in res.json().get("news", []):
                        rel = n.get('relatedTickers', [])
                        if any(t in watch_list for t in rel):
                            watchlist_news.append(f"[color=#00FFFF][b]{rel[0]}[/b][/color] | WATCHLIST\n[ref={n.get('link')}]{n.get('title')}[/ref]")
            except: pass

        if not watchlist_news:
            fallback_url = "https://query2.finance.yahoo.com/v1/finance/search?q=stocks market trading federal reserve economy&newsCount=15"
            try:
                res = requests.get(fallback_url, headers=HEADERS, timeout=5)
                if res.status_code == 200:
                    for n in res.json().get("news", []):
                        watchlist_news.append(f"[color=#FF9900][b]RYNEK GLOBALNY[/b][/color] | Wiadomości Ogólne\n[ref={n.get('link')}]{n.get('title')}[/ref]\n[color=#888888]Źródło: {n.get('publisher')}[/color]")
            except: pass

        Clock.schedule_once(lambda dt: self._render_news(watchlist_news))

    def _render_news(self, news_list):
        self.content.clear_widgets()
        self.content.add_widget(MDLabel(text="[b][color=#00FFFF]📰 AKTUALNOŚCI I NOWOŚCI RYNKOWE[/color][/b]", markup=True, size_hint_y=None, height=dp(40)))
        for news in news_list: self.content.add_widget(DataCard(text=news))


# ---------------------------------------------------------
#  ZAKŁADKA CFD/WLASNE
# --------------------------------------------------------

class CfdShortTab(ScrollableTab):
    def __init__(self, **kw):
        kw['title'] = "CFD/Własne"
        super().__init__(**kw)
        self.custom_tickers = ["GC=F", "PLN=X", "BTC-USD"]
        self.control_panel.height = dp(140) # NAPRAWIONO: Zwiększona wysokość
        
        self.load_stored_data()
        
        input_row = MDBoxLayout(orientation="horizontal", size_hint_y=None, height=dp(52), spacing=dp(8))
        # NAPRAWIONO: mode="outline"
        self.input_field = MDTextField(hint_text="Ticker (np. AAPL)", size_hint_x=0.66, mode="outline")
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
                    if isinstance(saved, list) and saved: 
                        self.custom_tickers = saved
            except Exception: 
                pass

    def save_stored_data(self):
        app = MDApp.get_running_app()
        path = os.path.join(app.user_data_dir, "cfd_tickers.json")
        try:
            with open(path, "w", encoding="utf-8") as f: 
                json.dump(self.custom_tickers, f)
        except Exception: 
            pass

    def add_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t and t not in self.custom_tickers:
            self.custom_tickers.append(t)
            self.save_stored_data()
            self.input_field.text = ""
            self.refresh_data()

    def remove_ticker(self, *a):
        t = self.input_field.text.strip().upper()
        if t in self.custom_tickers:
            self.custom_tickers.remove(t)
            self.save_stored_data()
            self.input_field.text = ""
            self.refresh_data()

    def refresh_data(self, *args, force=False):
        super().refresh_data(*args, force=force)

    def _fetch(self, *args, **kwargs):
        force = kwargs.get('force', False)
        
        sec_a = [", ".join(self.custom_tickers) if self.custom_tickers else "Brak danych"]
        sec_b, sec_c, sec_d = [], [], []
        
        nasdaq_100_pool = ["TSLA", "AMZN", "GOOGL", "META", "NFLX", "AVGO", "COST", "PEP", "ADBE", "QCOM", "INTC"]
        spolki_spoza_nasdaq = ["PLTR", "SOFI", "RIVN", "NIO", "CDPROJEKT.WA"]
        
        required_tickers = list(dict.fromkeys(self.custom_tickers + nasdaq_100_pool + spolki_spoza_nasdaq))
        
        app = MDApp.get_running_app()
        is_cache_fresh = app.cache_time and (datetime.now() - app.cache_time).total_seconds() < 120 and not force
        
        if is_cache_fresh and all(sym in app.shared_cache for sym in required_tickers):
            print("DEBUG [CFD]: Dane w cache są kompletne.")
            bulk_data = app.shared_cache
        else:
            print("DEBUG [CFD]: Pobieram nową paczkę danych.")
            all_to_fetch = list(dict.fromkeys(required_tickers + list(app.shared_cache.keys())))
            bulk_data = fetch_bulk_ticker_data(all_to_fetch)
            
            app.shared_cache.update(bulk_data)
            app.cache_time = datetime.now()

        for sym in bulk_data:
            data = bulk_data.get(sym)
            if not data: 
                continue
            
            p = data.get('price', 0.0)
            if p == 0.0:
                continue
                
            name = data.get('name', sym)
            hist_prices = data.get('closes', [])
            
            sma14 = sum(hist_prices[-14:]) / 14 if len(hist_prices) >= 14 else p
            sma90 = sum(hist_prices[-90:]) / 90 if len(hist_prices) >= 90 else p
            rsi = calculate_rsi(hist_prices, 14) if hist_prices else 50.0

            if sym not in self.custom_tickers and p < sma14:
                sec_b.append(f"[b]{name} - {sym}[/b]\nCena: {p:.2f} | SMA14: {sma14:.2f}\nRSI: {rsi:.1f}")

            if sym in self.custom_tickers:
                precision = 4 if p < 10 else 2
                sec_c.append(
                    f"[b]{name} - {sym}[/b]\nKurs: {p:.{precision}f}\n"
                    f"[color=#00AA00]TP (+3%): {p*1.03:.{precision}f}[/color] | "
                    f"[color=#FF3333]SL (-2%): {p*0.98:.{precision}f}[/color]"
                )
                
            if p < sma90:
                sec_d.append(f"[b]{name} - {sym}[/b]\nCena: {p:.2f} | SMA90: {sma90:.2f}")

        if not sec_b: sec_b.append("Brak spółek spełniających warunki.")
        if not sec_c: sec_c.append("Brak danych.")
        if not sec_d: sec_d.append("Brak spółek poniżej amerykańskiej średniej.")

        payload = {
            "A: ZAPISANE TICKERY": sec_a, 
            "B: WYBICIE (SMA14)": sec_b, 
            "C: ANALIZA TRANSAKCYJNA": sec_c, 
            "D: PONIŻEJ ŚREDNIEJ (SMA90)": sec_d
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
                
# ---------------------------------------------------------
#  APLIKACJA
# --------------------------------------------------------

class StockScannerPro(MDApp):
    def build(self):
        from kivy.core.window import Window
        Window.clearcolor = (1, 1, 1, 1)

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
                request_permissions([
                    Permission.INTERNET,
                    Permission.POST_NOTIFICATIONS,
                    Permission.VIBRATE
                ])
        except Exception as e:
            print(f"Błąd przy żądaniu uprawnień: {e}")

        self.tabs_instances = [InfoTab(), SkanerTab(), TickerTab(), KatalizatoryTab(), NewsTab(), CfdShortTab()]
        
        for tab in self.tabs_instances: 
            self.tabs_container.add_widget(tab)
            
        if hasattr(self.tabs_instances[1], 'load_stored_data'): 
            self.tabs_instances[1].load_stored_data()
        if hasattr(self.tabs_instances[5], 'load_stored_data'): 
            self.tabs_instances[5].load_stored_data()
        
        self.app_ready = True
        Clock.schedule_once(lambda dt: self.tabs_instances[1].load_data_if_needed(), 0.5)
        Clock.schedule_once(self.background_prefetch, 2.0)
        Clock.schedule_interval(self.cron_time_checker, 60)
    
    def on_tab_switch(self, instance_tabs, instance_tab, instance_tab_label, tab_text):
        if not getattr(self, 'app_ready', False):
            return
        if hasattr(instance_tab, 'load_data_if_needed'): 
            instance_tab.load_data_if_needed()

    def background_prefetch(self, dt):
        delay = 0.5
        for i, tab in enumerate(self.tabs_instances[1:]):
            if hasattr(tab, 'is_loaded') and not tab.is_loaded:
                def make_callback(t):
                    return lambda dt: t.load_data_if_needed()
                Clock.schedule_once(make_callback(tab), delay * (i + 1))

    def on_resume(self):
        if getattr(self, 'app_ready', False):
            for tab in self.tabs_instances: 
                if hasattr(tab, 'refresh_data'):
                    tab.refresh_data()

    def cron_time_checker(self, dt):
        now = datetime.now()
        if now.weekday() in range(0, 5) and now.minute == 0:
            if now.hour in [11, 13, 15]:
                for tab in self.tabs_instances:
                    if not hasattr(tab, 'refresh_data'):
                        continue
                    if isinstance(tab, KatalizatoryTab): 
                        tab.refresh_data(True)
                    else: 
                        tab.refresh_data()
                        
    def send_notification(self, title, message):
        if notification:
            try:
                notification.notify(
                    title=title, message=message,
                    app_name='StockScanner', timeout=10
                )
            except Exception as e:
                print(f"Błąd powiadomienia Plyer: {e}")
        else:
            print(f"Powiadomienie (brak plyer): {title} - {message}")
            
        try:
            Clock.schedule_once(lambda dt: MDSnackbar(
                MDLabel(text=f"🔔 [b]{title}:[/b] {message}", theme_text_color="Custom", text_color=[1, 1, 1, 1], markup=True),
                background_color=[0, 0.4, 0.4, 1],
                duration=5
            ).open())
        except Exception as ex:
            print(f"Błąd paska Snackbar: {ex}")

if __name__ == '__main__':
    StockScannerPro().run()
