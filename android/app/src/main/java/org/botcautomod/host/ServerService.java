package org.botcautomod.host;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Context;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.net.wifi.WifiManager;
import android.os.Build;
import android.os.IBinder;
import android.os.PowerManager;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import java.net.Inet4Address;
import java.net.InetAddress;
import java.net.NetworkInterface;
import java.util.Collections;

/**
 * Runs the botc-automod game server as a foreground service, so it keeps
 * running while the host switches to the browser to play. A notification
 * shows the address and a Stop button.
 */
public class ServerService extends Service {
    static final int PORT = 8000;
    static final String ACTION_STOP = "org.botcautomod.host.STOP";
    private static final String CHANNEL = "server";

    // Read by MainActivity to draw its screen.
    static volatile String state = "stopped";   // stopped | starting | running | error
    static volatile String url = "";
    static volatile String error = "";
    static volatile Bitmap qr = null;

    private PowerManager.WakeLock wakeLock;
    private WifiManager.WifiLock wifiLock;

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopSelf();
            return START_NOT_STICKY;
        }
        if (!"stopped".equals(state) && !"error".equals(state)) {
            return START_NOT_STICKY;
        }
        startInForeground("Starting the game server…");
        PowerManager pm = (PowerManager) getSystemService(Context.POWER_SERVICE);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "botc:server");
        wakeLock.acquire();
        WifiManager wm = (WifiManager) getApplicationContext().getSystemService(Context.WIFI_SERVICE);
        wifiLock = wm.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "botc:server");
        wifiLock.acquire();

        state = "starting";
        error = "";
        new Thread(() -> {
            try {
                if (!Python.isStarted()) {
                    Python.start(new AndroidPlatform(getApplicationContext()));
                }
                PyObject mod = Python.getInstance().getModule("botc_automod.android");
                String ip = lanAddress();
                String pub = ip == null ? "" : "http://" + ip + ":" + PORT + "/";
                String dataDir = getFilesDir().getAbsolutePath() + "/data";
                String nativeDir = getApplicationInfo().nativeLibraryDir;
                url = mod.callAttr("start", dataDir, PORT, pub, nativeDir).toString();
                byte[] png = mod.callAttr("qr_png", url).toJava(byte[].class);
                qr = BitmapFactory.decodeByteArray(png, 0, png.length);
                state = "running";
                startInForeground("Players open " + url);
            } catch (Throwable t) {
                error = String.valueOf(t.getMessage());
                state = "error";
                stopSelf();
            }
        }, "botc-start").start();
        return START_NOT_STICKY;
    }

    @Override
    public void onDestroy() {
        new Thread(() -> {
            try {
                if (Python.isStarted()) {
                    Python.getInstance().getModule("botc_automod.android").callAttr("stop");
                }
            } catch (Throwable ignored) {
            }
            if (!"error".equals(state)) {
                state = "stopped";
            }
            qr = null;
        }, "botc-stop").start();
        if (wakeLock != null && wakeLock.isHeld()) wakeLock.release();
        if (wifiLock != null && wifiLock.isHeld()) wifiLock.release();
        super.onDestroy();
    }

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    private void startInForeground(String text) {
        NotificationManager nm = getSystemService(NotificationManager.class);
        nm.createNotificationChannel(new NotificationChannel(CHANNEL, "Game server", NotificationManager.IMPORTANCE_LOW));
        PendingIntent open = PendingIntent.getActivity(this, 0, new Intent(this, MainActivity.class),
                PendingIntent.FLAG_IMMUTABLE);
        PendingIntent stop = PendingIntent.getService(this, 1,
                new Intent(this, ServerService.class).setAction(ACTION_STOP), PendingIntent.FLAG_IMMUTABLE);
        Notification n = new Notification.Builder(this, CHANNEL)
                .setSmallIcon(R.drawable.ic_launcher)
                .setContentTitle("Clocktower game server is on")
                .setContentText(text)
                .setContentIntent(open)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(null, "Stop", stop).build())
                .build();
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(1, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        } else {
            startForeground(1, n);
        }
    }

    /** This phone's IPv4 address on Wi-Fi or its own hotspot, or null. */
    static String lanAddress() {
        String fallback = null;
        try {
            for (NetworkInterface ni : Collections.list(NetworkInterface.getNetworkInterfaces())) {
                if (!ni.isUp() || ni.isLoopback()) continue;
                String name = ni.getName();
                for (InetAddress a : Collections.list(ni.getInetAddresses())) {
                    if (!(a instanceof Inet4Address) || !a.isSiteLocalAddress()) continue;
                    if (name.startsWith("wlan") || name.startsWith("ap") || name.startsWith("swlan")) {
                        return a.getHostAddress();
                    }
                    if (fallback == null) fallback = a.getHostAddress();
                }
            }
        } catch (Exception ignored) {
        }
        return fallback;
    }
}
