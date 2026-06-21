[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml

version = 10.0

icon.filename = %(source.dir)s/icon.png

requirements = python3==3.11.9,kivy==2.2.1,kivymd==1.1.1,cython==0.29.36,numpy==1.26.4,pandas==2.2.2,pillow,requests,aiohttp,websockets,yfinance,pytz,plyer

orientation = portrait
fullscreen = 0
allow_rotation = 0

log_level = 2

android.api = 34
android.minapi = 24
android.ndk_api = 26
android.sdk = 34
android.ndk = 25b

android.accept_sdk_license = True
android.enable_androidx = True

android.archs = arm64-v8a

android.permissions = INTERNET,WAKE_LOCK,FOREGROUND_SERVICE,VIBRATE,POST_NOTIFICATIONS

android.wakelock = True

android.release_artifact = apk

p4a.bootstrap = sdl2
p4a.branch = master
p4a.extra_args = --ignore-setup-py --disable-thorvg

warn_on_root = 0
