[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml

version = 10.0

orientation = portrait
fullscreen = 0

#==================================================

PYTHON / KIVY

#==================================================

requirements = hostpython3==3.11.8,python3==3.11.8,kivy==2.3.0,kivymd==1.2.0,pillow,aiohttp==3.9.5,websockets==12.0,requests,plyer,certifi,httpx,jnius,urllib3,chardet,idna
#==================================================

ANDROID

#==================================================

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

#==================================================

SERVICES

#==================================================

android.services = ScannerService:service.py

#==================================================

P4A

#==================================================

p4a.bootstrap = sdl2
p4a.extra_args = --ignore-setup-py --debug
# WAŻNE DLA STABILNOŚCI
environment = LANG=en_US.UTF-8
#==================================================

LOGS

#==================================================

log_level = 2
warn_on_root = 0
