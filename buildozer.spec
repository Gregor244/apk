[app]

title = StockScanner

package.name = stockscanner
package.domain = org.gregor

source.dir = .

source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt

version = 1.0

requirements = python3==3.10.11,kivy==2.2.1,kivymd==1.1.1,pillow,requests,plyer,certifi,httpx,pytz,pyjnius

orientation = portrait

hostpython = python3.10

fullscreen = 0

android.api = 33
android.minapi = 24

android.ndk = 25b

android.archs = arm64-v8a

p4a.bootstrap = sdl2

services = SyncService:service.py

android.permissions = INTERNET,FOREGROUND_SERVICE,WAKE_LOCK

android.accept_sdk_license = True

android.enable_androidx = True

log_level = 2

warn_on_root = 0
