import json
import os
import sys
import time
import traceback
from datetime import datetime

# Importy dla kompatybilności z silnikiem V9 (dla przyszłych tasków w tle)
try:
    import httpx
    import certifi
except ImportError:
    httpx = None
    certifi = None

try:
    from plyer import notification
except Exception:
    notification = None

SERVICE_NAME = "StockScannerService"
POLL_INTERVAL = 5.0

# =========================================
# PATH MANAGEMENT
# =========================================

def _candidate_dirs():
    candidates = []
    env_dir = os.environ.get("SERVICE_BRIDGE_DIR")
    if env_dir: candidates.append(env_dir)
    
    base_dir = os.path.dirname(os.path.abspath(__file__))
    candidates.append(os.path.join(base_dir, "service"))
    
    android_arg = os.environ.get("ANDROID_ARGUMENT")
    if android_arg:
        candidates.append(os.path.join(android_arg, "service"))
        candidates.append(os.path.join(android_arg, "files", "service"))

    return list(dict.fromkeys(candidates))

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
    fallback = os.path.join(os.getcwd(), "service")
    os.makedirs(fallback, exist_ok=True)
    return {"base": fallback, "queue": os.path.join(fallback, "queue.json"), "state": os.path.join(fallback, "state.json"), "ack": os.path.join(fallback, "ack.json")}

# =========================================
# UTILS
# =========================================

def _safe_json_load(path, default=None):
    try:
        if not os.path.exists(path): return default or {}
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default or {}

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
    if not notification: return
    try:
        notification.notify(
            title=str(title or SERVICE_NAME),
            message=str(message or ""),
            app_name=SERVICE_NAME,
            timeout=10
        )
    except Exception:
        pass

# =========================================
# LOGIC
# =========================================

def _process_queue(paths):
    """
    Sprawdza kolejkę zadań wysłaną z głównej aplikacji (np. powiadomienia o sygnałach).
    """
    payload = _safe_json_load(paths["queue"], {"items": []})
    items = payload.get("items", [])
    if not items: return

    ack = _safe_json_load(paths["ack"], {"keys": []})
    ack_keys = set(ack.get("keys", []))
    changed = False

    for item in items:
        key = item.get("key")
        if not key or key in ack_keys: continue

        _notify(item.get("title", "Sygnał V9"), item.get("message", "Nowe zdarzenie na rynku"))
        ack_keys.add(key)
        changed = True

    if changed:
        _safe_json_dump(paths["ack"], {"ts": datetime.now().isoformat(), "keys": sorted(list(ack_keys))[-100:]})

def main():
    paths = _paths()
    # Zapis stanu startowego dla monitoringu
    _safe_json_dump(paths["state"], {"running": True, "ts": datetime.now().isoformat(), "version": "V9.0"})

    while True:
        try:
            # 1. Przetwarzanie powiadomień
            _process_queue(paths)
            
            # 2. Aktualizacja statusu usługi co 30s
            if int(time.time()) % 30 == 0:
                _safe_json_dump(paths["state"], {"running": True, "ts": datetime.now().isoformat()})
                
        except Exception:
            # Nie przerywamy usługi, tylko logujemy błąd
            with open(os.path.join(paths["base"], "error.log"), "a") as f:
                traceback.print_exc(file=f)
        
        time.sleep(POLL_INTERVAL)

if __name__ == "__main__":
    main()
