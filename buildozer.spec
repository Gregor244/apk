[app]
title = SkanerGieldyUSA
package.name = skanergieldy
package.domain = org.test

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json

version = 1.2

icon.filename = %(source.dir)s/icon.png

# ZAKTUALIZOWANE REQUIREMENTS:
# Dodano httpx, certifi, anyio (dla obsługi asynchronicznych requestów w Python 3)
requirements = python==3.11,kivy==2.3.0,kivymd==1.2.0,pillow,httpx,certifi,anyio,idna,sniffio,h11,h2,httpcore

orientation = portrait
fullscreen = 0
allow_rotation = 0
log_level = 2

android.api = 33
android.minapi = 24
android.ndk_api = 24
android.ndk = 25c
android.sdk = 33
android.build_tools_version = 33.0.2

android.release_artifact = apk

android.permissions = INTERNET,ACCESS_NETWORK_STATE,POST_NOTIFICATIONS,VIBRATE,WAKE_LOCK,FOREGROUND_SERVICE,RECEIVE_BOOT_COMPLETED

android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = True

android.presplash_color = #101010
android.entrypoint = org.kivy.android.PythonActivity

# Pozostawione puste, chyba że potrzebujesz specyficznych bibliotek Java
android.gradle_dependencies = 

android.archs = arm64-v8a,armeabi-v7a

android.python_version = 3.11

# Jeśli faktycznie używasz zewnętrznego pliku service.py:
services = ScanerService:service.py

p4a.fork = kivy
p4a.branch = develop

[buildozer]
log_level = 2
warn_on_root = 1
