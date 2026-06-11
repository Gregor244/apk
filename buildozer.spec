[app]

title = StockScannerPro

package.name = stockscannerpro
package.domain = org.gregor244

source.dir = .

source.include_exts = py,png,jpg,jpeg,kv,atlas,json,txt

version = 1.0

icon.filename = %(source.dir)s/icon.png

requirements = python3==3.10.11,kivy==2.3.0,kivymd==1.1.1,requests,urllib3,certifi,idna,chardet,plyer,cython==0.29.33

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

android.presplash_color = #101010

android.entrypoint = org.kivy.android.PythonActivity

android.services = stockscanner:service.py

android.build_tools_version = 34.0.0

android.release_artifact = apk

android.gradle_dependencies =

android.add_packaging_options =

# KLUCZOWE
p4a.fork = kivy
p4a.branch = stable

# STABILNOŚĆ
warn_on_root = 1

# BUILD CACHE
build_dir = .buildozer

[buildozer]

log_level = 2
warn_on_root = 1
