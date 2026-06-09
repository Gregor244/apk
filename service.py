import os
import json
import time
from datetime import datetime

from kivy.utils import platform

# -------------------------------------------------
# POWIADOMIENIA
# -------------------------------------------------
try:
    from plyer import notification
except Exception:
    notification = None

# -------------------------------------------------
# ANDROID SERVICE
# -------------------------------------------------
if platform == "android":
    try:
        from android import AndroidService
    except Exception:
        AndroidService = None

    try:
        from android.storage import app_storage_path
        APP_DIR = app_storage_path()
    except Exception:
        APP_DIR = os.path.expanduser("~")
else:
    AndroidService = None
    APP_DIR = os.path.expanduser("~")

# -------------------------------------------------
# ŚCIEŻKI — MUSZĄ BYĆ IDENTYCZNE JAK W main.py
# -------------------------------------------------
SERVICE_DIR = os.path.join(APP_DIR, "service")

QUEUE_FILE = os.path.join(SERVICE_DIR, "queue.json")
ACK_FILE = os.path.join(SERVICE_DIR, "ack.json")
STATE_FILE = os.path.join(SERVICE_DIR, "state.json")
PING_FILE = os.path.join(SERVICE_DIR, "ping.json")

# -------------------------------------------------
# HELPERY
# -------------------------------------------------
def ensure_dirs():
    try:
        os.makedirs(SERVICE_DIR, exist_ok=True)
    except Exception:
        pass


def load_json(path, default=None):
    if default is None:
        default = {}

    try:
        if not os.path.exists(path):
            return default

        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return default


def save_json(path, data):
    try:
        ensure_dirs()

        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)

    except Exception:
        pass


# -------------------------------------------------
# STATE
# -------------------------------------------------
def load_state():
    state = load_json(
        STATE_FILE,
        {
            "processed": [],
            "last_date": "",
            "last_ping": "",
            "stats": {
                "notifications": 0
            }
        }
    )

    if not isinstance(state.get("processed"), list):
        state["processed"] = []

    return state


def save_state(state):
    save_json(STATE_FILE, state)


# -------------------------------------------------
# HEARTBEAT
# -------------------------------------------------
def write_ping():
    save_json(
        PING_FILE,
        {
            "alive": True,
            "ts": datetime.now().isoformat()
        }
    )


def write_ack(processed_count):
    save_json(
        ACK_FILE,
        {
            "ts": datetime.now().isoformat(),
            "processed_count": processed_count
        }
    )


# -------------------------------------------------
# POWIADOMIENIA
# -------------------------------------------------
def notify(title, message):
    if notification is None:
        return False

    try:
        notification.notify(
            title=title[:80],
            message=message[:250],
            app_name="SkanerGieldyUSA",
            timeout=10
        )
        return True

    except Exception as e:
        print("Notification error:", e)
        return False


# -------------------------------------------------
# KOLEJKA
# -------------------------------------------------
def read_queue():
    ensure_dirs()

    payload = load_json(
        QUEUE_FILE,
        {
            "date": datetime.now().date().isoformat(),
            "items": []
        }
    )

    if payload.get("date") != datetime.now().date().isoformat():
        payload = {
            "date": datetime.now().date().isoformat(),
            "items": []
        }

    if not isinstance(payload.get("items"), list):
        payload["items"] = []

    return payload


# -------------------------------------------------
# FILTROWANIE DUPLIKATÓW
# -------------------------------------------------
def should_skip_item(item, processed):
    key = item.get("key")

    if not key:
        return True

    if key in processed:
        return True

    return False


# -------------------------------------------------
# OBSŁUGA ALERTÓW
# -------------------------------------------------
def process_item(item, processed):
    key = item.get("key")

    title = item.get("title", "Alert")
    message = item.get("message", "")

    ok = notify(title, message)

    if ok:
        processed.add(key)

    return ok


# -------------------------------------------------
# GŁÓWNA PĘTLA
# -------------------------------------------------
def main():
    print("SERVICE START")

    ensure_dirs()

    # ---------------------------------------------
    # FOREGROUND SERVICE
    # ---------------------------------------------
    service = None

    if platform == "android" and AndroidService is not None:
        try:
            service = AndroidService(
                "Skaner Gieldy USA",
                "Powiadomienia działają w tle"
            )

            service.start(
                "Skaner Gieldy USA działa w tle"
            )

            print("Foreground service started")

        except Exception as e:
            print("Foreground service error:", e)

    # ---------------------------------------------
    # STATE
    # ---------------------------------------------
    state = load_state()

    # ---------------------------------------------
    # LOOP
    # ---------------------------------------------
    while True:
        try:
            now = datetime.now()
            today = now.date().isoformat()

            # -------------------------------------
            # RESET DZIENNY
            # -------------------------------------
            if state.get("last_date") != today:
                state["processed"] = []
                state["last_date"] = today

            processed = set(state.get("processed", []))

            # -------------------------------------
            # HEARTBEAT
            # -------------------------------------
            write_ping()

            # -------------------------------------
            # KOLEJKA
            # -------------------------------------
            payload = read_queue()
            items = payload.get("items", [])

            changed = False

            for item in items:
                try:
                    if should_skip_item(item, processed):
                        continue

                    ok = process_item(item, processed)

                    if ok:
                        changed = True

                        stats = state.get("stats", {})
                        stats["notifications"] = stats.get("notifications", 0) + 1
                        state["stats"] = stats

                except Exception as e:
                    print("Item processing error:", e)

            # -------------------------------------
            # ZAPIS
            # -------------------------------------
            if changed:
                state["processed"] = list(processed)

                save_state(state)

                write_ack(len(processed))

        except Exception as e:
            print("SERVICE LOOP ERROR:", e)

        # -----------------------------------------
        # SLEEP
        # -----------------------------------------
        time.sleep(10)


# -------------------------------------------------
# START
# -------------------------------------------------
if __name__ == "__main__":
    main()
