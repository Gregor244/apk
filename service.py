import time
import traceback

from jnius import autoclass

PythonService = autoclass('org.kivy.android.PythonService')

Context = autoclass('android.content.Context')

NotificationManager = autoclass(
    'android.app.NotificationManager'
)

NotificationChannel = autoclass(
    'android.app.NotificationChannel'
)

NotificationBuilder = autoclass(
    'android.app.Notification$Builder'
)

Build_VERSION = autoclass('android.os.Build$VERSION')

String = autoclass('java.lang.String')

CHANNEL_ID = "stockscanner_channel"
CHANNEL_NAME = "StockScanner"

service = PythonService.mService
context = service.getApplicationContext()


def create_notification():

    if Build_VERSION.SDK_INT >= 26:

        manager = context.getSystemService(
            Context.NOTIFICATION_SERVICE
        )

        channel = NotificationChannel(
            CHANNEL_ID,
            CHANNEL_NAME,
            NotificationManager.IMPORTANCE_LOW
        )

        manager.createNotificationChannel(channel)

        builder = NotificationBuilder(
            context,
            CHANNEL_ID
        )

    else:

        builder = NotificationBuilder(context)

    builder.setContentTitle(
        String("StockScanner")
    )

    builder.setContentText(
        String("Scanner running")
    )

    builder.setSmallIcon(
        context.getApplicationInfo().icon
    )

    builder.setOngoing(True)

    return builder.build()


def main():

    try:

        notification = create_notification()

        service.startForeground(
            1001,
            notification
        )

        while True:
            time.sleep(5)

    except Exception:
        traceback.print_exc()


if __name__ == "__main__":
    main()
