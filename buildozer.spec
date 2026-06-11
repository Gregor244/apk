[app]

title = StockScannerPro

package.name = stockscannerpro
package.domain = org.gregor244

source.dir = .

# (str) Icon of the application
icon.filename = %(source.dir)s/icon.png

source.include_exts = py,png,jpg,jpeg,kv,atlas,json

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

KLUCZOWE:

android.skip_update = False

WYMUSZENIE STABILNYCH BUILD TOOLS

android.build_tools = 34.0.0

STABILNOŚĆ

osx.python_version = 3
osx.kivy_version = 2.3.0

REDUKCJA CRASHY

warn_on_root = 1

LOGI

log_level = 2

[buildozer]

log_level = 2

warn_on_root = 1
