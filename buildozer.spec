[app]
title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml

version = 10.0
orientation = portrait
fullscreen = 0

requirements = python3,kivy,kivymd,pillow,requests,plyer,certifi,httpx,pytz,pyjnius

# =========================
# ANDROID (STABLE BASE)
# =========================
android.api = 33
android.minapi = 24
android.ndk_api = 24
android.ndk = 25b

android.archs = arm64-v8a
android.enable_androidx = True
android.accept_sdk_license = True

android.permissions = INTERNET,VIBRATE,WAKE_LOCK,FOREGROUND_SERVICE

# =========================
# 🔥 SERVICES (FIXED PRO VERSION)
# =========================
android.services = scanner:service.py

# Android 12–16 requirement
android.foreground_service_type = dataSync

# =========================
# PYTHON-FOR-ANDROID STABILITY
# =========================
p4a.branch = develop

# ❌ HARD FIX FOR CRASHES
android.disable_recipes = libthorvg

# =========================
# LOGGING
# =========================
log_level = 2
warn_on_root = 0
