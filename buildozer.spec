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
requirements = kivy==2.2.1,kivymd==1.1.1,pillow,requests,plyer,websockets

cython_version = 0.29.33

orientation = portrait
fullscreen = 0
allow_rotation = 0
log_level = 2

android.api = 31
android.minapi = 26
android.ndk_api = 21
android.ndk = 25b
android.sdk = 34
android.build_tools_version = 34.0.0

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
p4a.branch = master


# IMPORTANT: REMOVE custom fork
# p4a.url = (REMOVE THIS)
# p4a.fork = (REMOVE THIS)
