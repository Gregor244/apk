[app]

title = StockScannerV10
package.name = stockscannerv10
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt

version = 10.0

requirements = python3,kivy,kivymd,httpx,websockets,certifi,pyjnius,plyer

orientation = portrait
fullscreen = 0

# Android 14
android.api = 34
android.minapi = 26
android.sdk = 34
android.ndk = 25b

android.accept_sdk_license = True
android.enable_androidx = True

# Foreground service + notifications + vibration + boot + battery exemption
android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS


android.add_src = ./src/main/java
android.meta_data = \

com.google.firebase.messaging.default_notification_channel_id=sto ck_scanner_alerts
p4a.extra_manifest_xml = ./android_manifest.xml
# Foreground websocket service
services = ScannerService:service.py

# FCM dependency prepared for native Firebase wiring
android.gradle_dependencies = \
    com.google.firebase:firebase-messaging:24.1.0,\
    androidx.core:core:1.13.1

# Optional safety defaults
android.wakelock = True
log_level = 2
warn_on_root = 0

[buildozer]
log_level = 2
