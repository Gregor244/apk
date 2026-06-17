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
requirements = kivy==2.2.1,kivymd==1.1.1,pillow,requests,plyer,httpx,websockets,certifi,urllib3,chardet,idna

cython_version = 0.29.36

orientation = portrait
fullscreen = 0
allow_rotation = 0
log_level = 2

android.api = 34
android.minapi = 26
android.ndk_api = 26
android.ndk = 25b
android.sdk = 34
android.build_tools_version = 34.0.0

android.release_artifact = apk

android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = True

android.archs = arm64-v8a,armeabi-v7a

android.services = ScannerService:service.py

android.wakelock = True

warn_on_root = 0

# -----------------------
# 🔥 FORCE STABLE p4a
# -----------------------
p4a.branch = release-2023.09.16
p4a.python_version = 3.10

# IMPORTANT: REMOVE custom fork
# p4a.url = (REMOVE THIS)
# p4a.fork = (REMOVE THIS)
