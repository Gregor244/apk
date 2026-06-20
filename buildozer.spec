[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml,java

icon.filename = %(source.dir)s/icon.png

version = 10.0

# -----------------------
# 🔥 CORE FIX (CRITICAL)
# -----------------------
requirements = python3==3.11.9,cython==0.29.36,kivy==2.3.0,kivymd==1.1.1,numpy==1.26.4,pandas==2.2.2,pillow,requests,aiohttp,websockets,yfinance,pytz,plyer

cython_version = 3.0.10

orientation = portrait
fullscreen = 0
allow_rotation = 0
log_level = 2

android.api = 34
android.minapi = 24
android.ndk_api = 26
android.ndk = 25b
android.build_tools_version = 34.0.0
android.sdk = 34

android.release_artifact = apk

android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = True

android.archs = arm64-v8a

android.services = ScannerService:service.py

android.wakelock = True

warn_on_root = 0

# -----------------------
# 🔥 FORCE STABLE p4a
# -----------------------
p4a.python_version = 3.10
p4a.extra_args = --disable-thorvg
osx.python_version = 3
p4a.bootstrap = sdl2
# (str) python-for-android branch to use, defaults to master
p4a.branch = stable
p4a.fork = kivy

# IMPORTANT: REMOVE custom fork
# p4a.url = (REMOVE THIS)
# p4a.fork = (REMOVE THIS)
