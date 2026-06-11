[app]
# (str) Title of your application
title = StockScannerPro

# (str) Package name
package.name = stockscannerpro

# (str) Package domain
package.domain = org.gregor244

# (str) App version — wymagane przez Buildozer
version = 1.0

# (str) Source code where the main.py lives
source.dir = .

# (str) Source files to include
source.include_exts = py,png,jpg,jpeg,kv,atlas,json

# (list) Application requirements
requirements = python3,kivy,kivymd,requests,urllib3,certifi,plyer,idna,chardet

# (str) Supported orientation
orientation = portrait

# (bool) Start in fullscreen
fullscreen = 0

# (bool) Allow rotation
allow_rotation = 0

# (int) Log level
log_level = 2

# (str) Android entry point
android.entrypoint = org.kivy.android.PythonActivity

# (list) Permissions
android.permissions = INTERNET,ACCESS_NETWORK_STATE,POST_NOTIFICATIONS,FOREGROUND_SERVICE,WAKE_LOCK

# (list) Android architectures
android.archs = arm64-v8a,armeabi-v7a

# (str) Android API
android.api = 34

# (str) Android minimum API
android.minapi = 24

# (str) Android SDK version
android.sdk = 24

# (str) Android NDK version
android.ndk = 25b

# (str) Services
android.services = stockscanner:service.py

[buildozer]
# (int) Log level
log_level = 2

# (bool) Warn on root usage
warn_on_root = 1

[app:android]
# (str) Preset name for Android packaging
android.p4a_dir =
