[app]
title = StockScannerPro

package.name = stockscannerpro
package.domain = org.gregor244

source.dir = .

icon.filename = %(source.dir)s/icon.png
presplash.filename = %(source.dir)s/presplash.png

source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt

version = 1.0

requirements = python3,kivy,kivymd,requests,urllib3,certifi,idna,chardet,plyer

orientation = portrait
fullscreen = 0
allow_rotation = 0
log_level = 2

android.api = 34
android.minapi = 24
android.sdk = 34
android.ndk = 25b
android.accept_sdk_license = True

android.archs = arm64-v8a,armeabi-v7a

android.permissions = INTERNET,ACCESS_NETWORK_STATE,POST_NOTIFICATIONS,WAKE_LOCK,FOREGROUND_SERVICE

android.allow_backup = True
android.enable_androidx = True

android.gradle_dependencies =

android.add_packaging_options =

android.presplash_color = #101010

android.entrypoint = org.kivy.android.PythonActivity

android.services = stockscanner:service.py

p4a.branch = master

warn_on_root = 1

[buildozer]
log_level = 2
warn_on_root = 1
