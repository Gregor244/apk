import os
import json
import time
from datetime import datetime

# -------------------------------------------------
# POWIADOMIENIA
# -------------------------------------------------
try:
    from plyer import notification
except Exception:
    notification = None

# -------------------------------------------------
# ANDROID SERVICE / STORAGE
# -------------------------------------------------
AndroidService = None
APP_DIR = os.path.expanduser("~")

try:
    from android import AndroidService as _AndroidService
    AndroidService = _AndroidService
except Exception:
    AndroidService = None

try:
    from android.storage import app_storage_path
    APP_DIR = app_storage_path()
except Exception:
    pass

# -------------------------------------------------
# ŚCIEŻKI — MUSZĄ BYĆ SPÓJNE Z main.py
# -------------------------------------------------
SERVICE_DIR_NAME = "service"

# Jeśli kiedyś zechcesz wymusić wspólną bazę między main.py i service.py,
# możesz ustawić SERVICE_BRIDGE_BASE w obu miejscach.
BASE_DIR = os.environ.get("SERVICE_BRIDGE_BASE", APP_DIR)
SERVICE_DIR = os.path.join(BASE_DIR, SERVICE_DIR_NAME)

QUEUE_FILE = os.path.join(SERVICE_DIR, "queue.json")
ACK_FILE = os.path.join(SERVICE_DIR, "ack.json")
STATE_FILE = os.path.join(SERVICE_DIR, "state.json")
PING_FILE = os.path.join(SERVICE_DIR, "ping.json")

# -------------------------------------------------
# USTAWIENIA
# -------------------------------------------------
SERVICE_NAME = "Skaner Gieldy USA"
SERVICE_TEXT = "Powiadomienia działają w tle"
LOOP_SLEEP_SECONDS = 5
MAX_NOTIFICATION_TITLE = 80
MAX_NOTIFICATION_MESSAGE = 250

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
    """
    Bezpieczny zapis przez plik tymczasowy + os.replace.
    Minimalizuje ryzyko uszkodzenia JSON przy ubiciu procesu.
    """
    try:
        ensure_dirs()
        tmp_path = f"{path}.tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)
        os.replace(tmp_path, path)
    except Exception:
        pass


def now_iso():
    return datetime.now().isoformat()


def today_iso():
    return datetime.now().date().isoformat()


def clamp_text(text, limit):
    text = "" if text is None else str(text)
    return text[:limit]


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

    if not isinstance(state.get("stats"), dict):
        state["stats"] = {"notifications": 0}

    if not isinstance(state["stats"].get("notifications"), int):
        state["stats"]["notifications"] = 0

    return state


def save_state(state):
    save_json(STATE_FILE, state)


# -------------------------------------------------
# HEARTBEAT / ACK
# -------------------------------------------------
def write_ping():
    save_json(
        PING_FILE,
        {
            "alive": True,
            "ts": now_iso()
        }
    )


def write_ack(processed_count):
    save_json(
        ACK_FILE,
        {
            "ts": now_iso(),
            "processed_count": int(processed_count or 0)
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
            title=clamp_text(title, MAX_NOTIFICATION_TITLE),
            message=clamp_text(message, MAX_NOTIFICATION_MESSAGE),
            app_name=SERVICE_NAME,
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
            "date": today_iso(),
            "items": []
        }
    )

    if payload.get("date") != today_iso():
        payload = {
            "date": today_iso(),
            "items": []
        }

    if not isinstance(payload.get("items"), list):
        payload["items"] = []

    return payload


def get_queue_mtime():
    try:
        return os.path.getmtime(QUEUE_FILE)
    except Exception:
        return 0.0


# -------------------------------------------------
# FILTROWANIE DUPLIKATÓW
# -------------------------------------------------
def should_skip_item(item, processed):
    if not isinstance(item, dict):
        return True

    key = item.get("key")
    if not key:
        return True

    return key in processed


def process_item(item, processed):
    if not isinstance(item, dict):
        return False

    key = item.get("key")
    if not key:
        return False

    title = item.get("title", "Alert")
    message = item.get("message", "")
    extra = item.get("extra", {})

    # Opcjonalnie: można tu rozszerzyć logikę o różne typy eventów.
    ok = notify(title, message)

    if ok:
        processed.add(key)

    return ok


# -------------------------------------------------
# FOREGROUND SERVICE
# -------------------------------------------------
def start_foreground_service():
    if AndroidService is None:
        return None

    try:
        service = AndroidService(SERVICE_NAME, SERVICE_TEXT)
        service.start(f"{SERVICE_NAME} działa w tle")
        return service
    except Exception as e:
        print("Foreground service error:", e)
        return None


# -------------------------------------------------
# GŁÓWNA PĘTLA
# -------------------------------------------------
def main():
    print("SERVICE START")
    ensure_dirs()

    service = start_foreground_service()

    state = load_state()
    last_queue_mtime = 0.0

    while True:
        try:
            now = datetime.now()
            today = now.date().isoformat()

            # -------------------------------------------------
            # RESET DZIENNY
            # -------------------------------------------------
            if state.get("last_date") != today:
                state["processed"] = []
                state["last_date"] = today

            processed = set(state.get("processed", []))

            # -------------------------------------------------
            # HEARTBEAT
            # -------------------------------------------------
            state["last_ping"] = now_iso()
            write_ping()

            # -------------------------------------------------
            # KOLEJKA — czytamy tylko gdy plik się zmienił
            # -------------------------------------------------
            queue_mtime = get_queue_mtime()
            if queue_mtime and queue_mtime != last_queue_mtime:
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
                            stats["notifications"] = int(stats.get("notifications", 0)) + 1
                            state["stats"] = stats

                    except Exception as e:
                        print("Item processing error:", e)

                if changed:
                    state["processed"] = list(processed)
                    save_state(state)
                    write_ack(len(processed))

                last_queue_mtime = queue_mtime

        except Exception as e:
            print("SERVICE LOOP ERROR:", e)

        time.sleep(LOOP_SLEEP_SECONDS)


# -------------------------------------------------
# START
# -------------------------------------------------
if __name__ == "__main__":
    main()
