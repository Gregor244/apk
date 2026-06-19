[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml

version = 10.0

requirements = python3==3.11.9,hostpython3==3.11.9,kivy==2.3.0,kivymd==1.2.0,pillow,requests,plyer,websockets

orientation = portrait
fullscreen = 0

# Android
android.ndk_path = /usr/local/lib/android/sdk/ndk/27.3.13750724
android.api = 33
android.minapi = 24
android.ndk_api = 24

android.accept_sdk_license = True
android.enable_androidx = True

android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.archs = arm64-v8a

# Service
android.services = ScannerService:service.py

# Buildozer / p4a
p4a.bootstrap = sdl2
p4a.branch = develop
p4a.extra_args = --disable-thorvg

log_level = 2
warn_on_root = 0
