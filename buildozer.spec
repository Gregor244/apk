[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml

version = 10.0

orientation = portrait
fullscreen = 0

==================================================

PYTHON / KIVY

==================================================

requirements = python3,kivy==2.2.1,kivymd==1.1.1,pillow,requests,aiohttp==3.9.5,websockets==12.0,pytz,plyer

==================================================

ANDROID

==================================================

android.api = 34
android.minapi = 24
android.ndk_api = 24

android.sdk = 34
android.ndk = 25b

android.accept_sdk_license = True
android.enable_androidx = True

android.archs = arm64-v8a

android.permissions = INTERNET,VIBRATE,WAKE_LOCK,FOREGROUND_SERVICE

android.release_artifact = apk

==================================================

SERVICES

==================================================

android.services = ScannerService:service.py

==================================================

P4A

==================================================

p4a.bootstrap = sdl2
p4a.extra_args = --ignore-setup-py --debug

==================================================

LOGS

==================================================

log_level = 2
warn_on_root = 0
