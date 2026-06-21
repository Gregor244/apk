[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml,java

icon.filename = %(source.dir)s/icon.png

version = 10.0


requirements = python3,kivy==2.2.1,kivymd==1.1.1,numpy==1.26.4,pandas==2.2.2,pillow,requests,aiohttp,websockets,yfinance,pytz,plyer

orientation = portrait
fullscreen = 0
allow_rotation = 0

android.api = 34
android.minapi = 24
android.ndk_api = 26
android.ndk = 25b
android.sdk = 34

android.accept_sdk_license = True
android.enable_androidx = True

android.permissions = INTERNET,WAKE_LOCK,VIBRATE,FOREGROUND_SERVICE

android.archs = arm64-v8a

android.release_artifact = apk

p4a.bootstrap = sdl2
p4a.extra_args = --ignore-setup-py --debug --disable-thorvg

log_level = 2
warn_on_root = 0
