[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml,java

version = 10.0
requirements = python3==3.11.9,kivy==2.3.0,kivymd==1.1.1,httpx,websockets,certifi,pyjnius,plyer,openssl

orientation = portrait
fullscreen = 0

# Android 14
android.api = 34
android.minapi = 26
android.sdk = 34
android.ndk = 25b
android.ard_src = src/main/java

android.accept_sdk_license = True
android.enable_androidx = True

# Permissions
android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.google_services_json = google-services.json

android.add_src = ./src/main/java
android.meta_data = com.google.firebase.messaging.default_notification_channel_id=stock_scanner_alerts
p4a.extra_manifest_xml = ./android_manifest.xml

android.add_aars = 
# Foreground websocket service
services = ScannerService:service.py

android.gradle_dependencies = \
    com.google.firebase:firebase-messaging:24.1.0,\
    com.google.firebase:firebase-analytics:22.1.0,\
    androidx.core:core:1.13.1

android.wakelock = True
log_level = 2
warn_on_root = 0

[buildozer]
log_level = 2
