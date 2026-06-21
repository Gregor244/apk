[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml

version = 10.0

orientation = portrait
fullscreen = 0

#
# STABILNE REQUIREMENTS
#
requirements = \
    python3==3.11.0, \
    cython==0.29.36, \
    kivy==2.2.1, \
    kivymd==1.1.1, \
    numpy==1.26.4, \
    pandas==2.2.2, \
    pillow, \
    requests, \
    aiohttp, \
    websockets, \
    yfinance, \
    pytz, \
    plyer

#
# ANDROID
#
android.api = 34
android.minapi = 24
android.ndk_api = 24
android.sdk = 34
android.ndk = 25b
android.accept_sdk_license = True

android.permissions = INTERNET,VIBRATE,WAKE_LOCK,FOREGROUND_SERVICE

android.archs = arm64-v8a

#
# P4A
#
p4a.bootstrap = sdl2

#
# USUŃ CAŁKOWICIE:
# p4a.branch
# p4a.fork
# p4a.url
# cython_version
#

#
# BUILD
#
android.release_artifact = apk

log_level = 2
warn_on_root = 0
