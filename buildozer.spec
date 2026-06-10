[app]
title = SkanerGieldyPro
package.name = skanergieldypro
package.domain = org.test

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json

version = 1.2

requirements = kivy==2.3.0,kivymd==1.2.0,pillow,requests,plyer,certifi,urllib3,chardet,idna

orientation = portrait
fullscreen = 0

icon.filename = %(source.dir)s/icon.png

# ANDROID
android.api = 34
android.minapi = 24
android.ndk_api = 24
android.ndk = 25b

# UPRAWNIENIA
android.permissions = INTERNET,ACCESS_NETWORK_STATE,POST_NOTIFICATIONS,VIBRATE,WAKE_LOCK,FOREGROUND_SERVICE,RECEIVE_BOOT_COMPLETED

# FOREGROUND SERVICE
services = ScanerService:service.py

# STABILNOŚĆ
android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = False

# P4A
p4a.bootstrap = sdl2

# LOGI
log_level = 2

# OPTYMALIZACJA
warn_on_root = 0

# SPLASH
presplash.color = #101010
android.presplash_color = #101010

# WAŻNE DLA STABILNOŚCI
android.release_artifact = apk
environment = LANG=en_US.UTF-8

[buildozer]
warn_on_root = 0
