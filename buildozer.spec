[app]
# (str) Title of your application
title = StockScannerPro

# (str) Package name
package.name = stockscannerpro

# (str) Package domain
package.domain = org.gregor244

# (str) Source code where the main.py lives
source.dir = .

# (str) Source files to include
source.include_exts = py,png,jpg,jpeg,kv,atlas,json

# (list) Application requirements
requirements = python3,kivy,kivymd,requests,certifi,plyer

# (str) Supported orientation
orientation = portrait

# (bool) Preserve logcat output
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

# (bool) Fullscreen
fullscreen = 0

# (bool) Allow rotation
allow_rotation = 0

[buildozer]
# (int) Log level
log_level = 2

# (str) Warn on root usage
warn_on_root = 1

[app:android]
# (str) Preset name for Android packaging
android.p4a_dir = 
