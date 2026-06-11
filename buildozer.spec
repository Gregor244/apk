[app]
title = SkanerGieldyUSA
package.name = skanergieldy
package.domain = org.test

source.dir = .
source.include_exts = py,png,jpg,jpeg,kv,atlas,json

version = 1.2

icon.filename = %(source.dir)s/icon.png

requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,requests,plyer,certifi

orientation = portrait
fullscreen = 0
allow_rotation = 0
log_level = 2

buildozer.requirements = cython==0.29.36
android.api = 33
android.minapi = 24
android.ndk_api = 24
android.ndk = 23b
android.sdk = 33
android.build_tools_version = 33.0.2
android.release_artifact = apk
android.enable_aab = False
android.permissions = INTERNET,ACCESS_NETWORK_STATE,POST_NOTIFICATIONS,VIBRATE,WAKE_LOCK,FOREGROUND_SERVICE,RECEIVE_BOOT_COMPLETED

android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = True

android.presplash_color = #101010
android.entrypoint = org.kivy.android.PythonActivity

android.archs = arm64-v8a,armeabi-v7a

services = ScanerService:service.py

p4a.branch = stable

[buildozer]
