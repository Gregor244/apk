# =========================================
# STOCK SCANNER PRO - V10 SERVICE.PY
# Foreground WebSocket + Local Push Alerts
# =========================================

import asyncio
import json
import os
import time

import websockets

from jnius import autoclass

PythonService = autoclass("org.kivy.android.PythonService")
NotificationChannel = autoclass("android.app.NotificationChannel")
NotificationManager = autoclass("android.app.NotificationManager")
NotificationCompat = autoclass("androidx.core.app.NotificationCompat")
ServiceCompat = autoclass("androidx.core.app.ServiceCompat")
Context = autoclass("android.content.Context")
Build = autoclass("android.os.Build")
ServiceInfo = autoclass("android.content.pm.ServiceInfo")

CHANNEL_ID = "stock_scanner_alerts"
FOREGROUND_ID = 1001

FINNHUB_KEY = "PUT_YOUR_FINNHUB_KEY_HERE"
WS_URL = f"wss://ws.finnhub.io?token={FINNHUB_KEY}"

WATCHLIST = ["AAPL", "NVDA", "TSLA", "MSFT", "AMD"]

STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "v10_state.json")

def safe(v, d=0.0):
    try:
        return float(v) if v is not None else d
    except Exception:
        return d

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
        elif price < self.last_price:
            self.sell_volume += volume

        delta = self.buy_volume - self.sell_volume
        self.delta_history.append(delta)
        self.volume_history.append(volume)
        self.delta_history = self.delta_history[-200:]
        self.volume_history = self.volume_history[-200:]
        self.last_price = price

        return {
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

def ensure_channel(service):
    manager = service.getSystemService(Context.NOTIFICATION_SERVICE)
    if Build.VERSION.SDK_INT >= Build.VERSION_CODES.O:
        channel = NotificationChannel(
            CHANNEL_ID,
            "Stock Scanner Alerts",
            NotificationManager.IMPORTANCE_HIGH,
        )
        channel.enableVibration(True)
        channel.setLockscreenVisibility(1)
        manager.createNotificationChannel(channel)

def build_notification(service, title, text, ongoing=False):
    builder = NotificationCompat.Builder(service, CHANNEL_ID)
    builder.setContentTitle(title)
    builder.setContentText(text)
    builder.setSmallIcon(service.getApplicationInfo().icon)
    builder.setPriority(NotificationCompat.PRIORITY_HIGH if not ongoing else NotificationCompat.PRIORITY_LOW)
    builder.setDefaults(NotificationCompat.DEFAULT_ALL)
    builder.setAutoCancel(not ongoing)
    builder.setOngoing(ongoing)
    return builder.build()

def write_state(data):
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        pass

def push_local_alert(service, title, text):
    manager = service.getSystemService(Context.NOTIFICATION_SERVICE)
    manager.notify(int(time.time()), build_notification(service, title, text, ongoing=False))

class WSService:
    def __init__(self):
        self.service = PythonService.mService
        self.normalizer = TickNormalizer()
        self.flow = SmartOrderFlow()
        self.ai = AdaptiveAI()
        self.last_alert_ts = {}

    def start_foreground(self):
        ensure_channel(self.service)
        notification = build_notification(
            self.service,
            "Stock Scanner V10",
            "Foreground WebSocket engine active",
            ongoing=True,
        )
        fg_type = ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC if Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q else 0
        ServiceCompat.startForeground(self.service, FOREGROUND_ID, notification, fg_type)

    async def websocket_loop(self):
        backoff = 2
        while True:
            try:
                async with websockets.connect(
                    WS_URL,
                    ping_interval=15,
                    ping_timeout=10,
                    close_timeout=5,
                    max_queue=2048,
                ) as ws:
                    for symbol in WATCHLIST:
                        await ws.send(json.dumps({"type": "subscribe", "symbol": symbol}))
                    backoff = 2

                    async for message in ws:
                        payload = json.loads(message)
                        if payload.get("type") != "trade":
                            continue

                        for trade in payload.get("data", []):
                            raw_tick = {
                                "symbol": trade.get("s", ""),
                                "price": trade.get("p", 0.0),
                                "volume": trade.get("v", 0.0),
                                "timestamp": trade.get("t", 0),
                                "bid": trade.get("p", 0.0),
                                "ask": trade.get("p", 0.0),
                            }
                            tick = self.normalizer.normalize(raw_tick)
                            if not tick:
                                continue

                            flow = self.flow.update(tick)
                            if not flow:
                                continue

                            ai = self.ai.update(tick, flow)

                            state = {
                                "symbol": tick["symbol"],
                                "price": tick["price"],
                                "score": ai["score"],
                                "threshold": ai["threshold"],
                                "signal": ai["signal"],
                                "flow": flow,
                                "timestamp": tick["timestamp"],
                            }
                            write_state(state)

                            if ai["signal"]:
                                key = f'{tick["symbol"]}:{ai["signal"]}'
                                now = time.time()
                                last = self.last_alert_ts.get(key, 0)
                                if now - last > 300:
                                    self.last_alert_ts[key] = now
                                    push_local_alert(
                                        self.service,
                                        f'{tick["symbol"]} {ai["signal"]}',
                                        f'Price {tick["price"]:.2f} | Score {ai["score"]} | Imb {flow["imbalance"]:+.2f}',
                                    )

            except Exception as e:
                print("WS reconnect:", e)
                try:
                    push_local_alert(self.service, "WS reconnect", str(e)[:120])
                except Exception:
                    pass
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 30)

    def run(self):
        self.start_foreground()
        asyncio.run(self.websocket_loop())

if __name__ == "__main__":
    WSService().run()
