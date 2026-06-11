import json
import os
import sys
import time
import traceback
from datetime import datetime

try:
    from plyer import notification
except Exception:
    notification = None

SERVICE_NAME = "StockScannerService"
POLL_INTERVAL = 5.0


def _candidate_dirs():
    candidates = []

    env_dir = os.environ.get("SERVICE_BRIDGE_DIR")
    if env_dir:
        candidates.append(env_dir)

    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(base_dir, "service"))
    candidates.append(os.path.join(os.path.expanduser("~"), "service"))

    android_arg = os.environ.get("ANDROID_ARGUMENT")
    if android_arg:
        candidates.append(os.path.join(android_arg, "service"))
        candidates.append(os.path.join(android_arg, "files", "service"))

    deduped = []
    seen = set()
    for path in candidates:
        norm = os.path.normpath(path)
        if norm not in seen:
            seen.add(norm)
            deduped.append(norm)
    return deduped


def _paths():
    for base in _candidate_dirs():
        try:
            os.makedirs(base, exist_ok=True)
            return {
                "base": base,
                "queue": os.path.join(base, "queue.json"),
                "state": os.path.join(base, "state.json"),
                "ack": os.path.join(base, "ack.json"),
            }
        except Exception:
            continue

    fallback = os.path.join(os.path.expanduser("~"), "service")
    os.makedirs(fallback, exist_ok=True)
    return {
        "base": fallback,
        "queue": os.path.join(fallback, "queue.json"),
        "state": os.path.join(fallback, "state.json"),
        "ack": os.path.join(fallback, "ack.json"),
    }


def _safe_json_load(path, default=None):
    default = default if default is not None else {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _safe_json_dump(path, payload):
    try:
        tmp = f"{path}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def _notify(title, message):
    title = str(title or "").strip()[:80]
    message = str(message or "").strip()[:250]
    if not title and not message:
        return
    try:
        if notification:
            notification.notify(title=title or SERVICE_NAME, message=message, app_name=SERVICE_NAME, timeout=10)
    except Exception:
        pass


def _process_queue(paths):
    payload = _safe_json_load(paths["queue"], {"date": None, "items": []})
    if not isinstance(payload, dict):
        return

    items = payload.get("items", [])
    if not isinstance(items, list) or not items:
        return

    ack = _safe_json_load(paths["ack"], {})
    ack_keys = set(ack.get("keys", [])) if isinstance(ack, dict) else set()
    changed = False

    for item in items:
        if not isinstance(item, dict):
            continue
        key = item.get("key")
        if not key or key in ack_keys:
            continue

        _notify(item.get("title", ""), item.get("message", ""))
        ack_keys.add(key)
        changed = True

    if changed:
        _safe_json_dump(paths["ack"], {"ts": datetime.now().isoformat(), "keys": sorted(ack_keys)})


def main():
    paths = _paths()
    _safe_json_dump(paths["state"], {"running": True, "ts": datetime.now().isoformat()})

    while True:
        try:
            _process_queue(paths)
        except Exception:
            traceback.print_exc()
        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        traceback.print_exc()
        sys.exit(1)
