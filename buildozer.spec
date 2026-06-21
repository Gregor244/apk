[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml,java

icon.filename = %(source.dir)s/icon.png

version = 10.0

# --------------------------------
# REQUIREMENTS
# --------------------------------
requirements = python3==3.11.9,cython==0.29.36,kivy==2.2.1,kivymd==1.1.1,numpy==1.26.4,pandas==2.2.2,pillow,requests,aiohttp,websockets,yfinance,pytz,plyer

orientation = portrait
fullscreen = 0
allow_rotation = 0

log_level = 2

environment = CYTHON_IGNORE_WARNINGS=1

# --------------------------------
# ANDROID
# --------------------------------
android.api = 34
android.minapi = 27
android.ndk_api = 27

android.sdk = 34
android.ndk = 25b

android.release_artifact = apk

android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = True

android.archs = arm64-v8a

android.wakelock = True

warn_on_root = 0

# --------------------------------
# SERVICES
# --------------------------------
android.services = ScannerService:service.py

# --------------------------------
# PYTHON FOR ANDROID
# --------------------------------
p4a.bootstrap = sdl2
p4a.branch = master
p4a.extra_args = --disable-thorvg

# --------------------------------
# PERFORMANCE
# --------------------------------
android.copy_libs = 1

android.numeric_version = 100000
