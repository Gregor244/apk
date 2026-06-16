[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml,java

icon.filename = %(source.dir)s/icon.png

version = 10.0

cython_version=0.29.36

requirements = python3,kivy==2.3.0,kivymd==1.2.0,pillow,requests,plyer,certifi,urllib3,chardet,idna,httpx,websockets,certifi,pyjnius,plyer

orientation = portrait
fullscreen = 0
allow_rotation = 0
log_level = 2

android.api = 34
android.minapi = 24
android.ndk_api = 24
android.ndk = 25b
android.sdk = 34
android.build_tools_version = 34.0.0
android.release_artifact = apk

android.accept_sdk_license = True
android.enable_androidx = True
android.allow_backup = True

android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.add_src = ./src/main/java

android.extra_manifest_xml = ./android_manifest.xml

android.google_services_json = google-services.json

android.meta_data = com.google.firebase.messaging.default_notification_channel_id=stock_scanner_alerts

p4a.extra_manifest_xml = ./android_manifest.xml

services = ScannerService:service.py

android.gradle_dependencies = com.google.firebase:firebase-messaging:23.4.1,com.google.firebase:firebase-analytics:21.6.2

p4a.fork = kivy
p4a.url = https://github.com/kivy/python-for-android.git

android.wakelock = True

log_level = 2
warn_on_root = 0

[buildozer]
log_level = 2
