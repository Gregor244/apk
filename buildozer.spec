[app]

title = StockScannerV10
package.name = stockscanner
package.domain = org.gregor

source.dir = .
source.include_exts = py,kv,png,jpg,json,txt,xml,java

icon.filename = %(source.dir)s/icon.png

version = 10.0

requirements = hostpython3==3.10.14,python3==3.10.14,kivy==2.2.1,kivymd==1.1.1,httpx,websockets,certifi,pyjnius,plyer
cython_version=0.29.36
orientation = portrait
fullscreen = 0

android.api = 34
android.minapi = 26
android.ndk_api= 26
android.sdk = 34
android.ndk = 25b
android.bootstrap = sdl2
android.build_tools_version = 34.0.0

p4a.branch= master
android.archs = arm64-v8a
p4a.python_version=3.10

android.accept_sdk_license = True
android.enable_androidx = True

android.permissions = INTERNET,POST_NOTIFICATIONS,FOREGROUND_SERVICE,FOREGROUND_SERVICE_DATA_SYNC,WAKE_LOCK,VIBRATE,RECEIVE_BOOT_COMPLETED,REQUEST_IGNORE_BATTERY_OPTIMIZATIONS

android.add_src = ./src/main/java

android.extra_manifest_xml = ./android_manifest.xml

android.google_services_json = google-services.json

android.meta_data = com.google.firebase.messaging.default_notification_channel_id=stock_scanner_alerts

p4a.extra_manifest_xml = ./android_manifest.xml

services = ScannerService:service.py

android.gradle_dependencies = com.google.firebase:firebase-messaging:23.4.1,com.google.firebase:firebase-analytics:21.6.2

android.release_artifact = apk

p4a.fork = kivy
p4a.url = https://github.com/kivy/python-for-android.git

android.wakelock = True

log_level = 2
warn_on_root = 0

[buildozer]
log_level = 2
