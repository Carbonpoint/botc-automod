package org.botcautomod.host;

import android.Manifest;
import android.app.Activity;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.ViewGroup;
import android.widget.Button;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;

/**
 * The host's screen: turn the server on and off, show the join QR code and
 * address, and open the game in this phone's browser like everyone else.
 */
public class MainActivity extends Activity {
    private static final int BG = Color.rgb(0x14, 0x11, 0x1a);
    private static final int GOLD = Color.rgb(0xd9, 0xb4, 0x5b);
    private static final int TEXT = Color.rgb(0xec, 0xe6, 0xf5);
    private static final int MUTED = Color.rgb(0xa8, 0x9f, 0xb8);

    private TextView status, address;
    private ImageView qr;
    private Button toggle, open;
    private final Handler handler = new Handler(Looper.getMainLooper());
    private final Runnable tick = new Runnable() {
        @Override
        public void run() {
            refresh();
            handler.postDelayed(this, 700);
        }
    };

    @Override
    protected void onCreate(Bundle saved) {
        super.onCreate(saved);
        LinearLayout col = new LinearLayout(this);
        col.setOrientation(LinearLayout.VERTICAL);
        col.setGravity(Gravity.CENTER_HORIZONTAL);
        int pad = dp(20);
        col.setPadding(pad, dp(32), pad, pad);
        col.setBackgroundColor(BG);

        TextView title = text("Clocktower Host", 26, TEXT);
        title.setTypeface(Typeface.DEFAULT_BOLD);
        col.addView(title);
        col.addView(text("Run the game server on this phone. Players on the same Wi-Fi (or on this phone's "
                + "hotspot) scan the code to join.", 15, MUTED));

        status = text("", 18, TEXT);
        status.setPadding(0, dp(20), 0, dp(8));
        col.addView(status);

        qr = new ImageView(this);
        qr.setAdjustViewBounds(true);
        col.addView(qr, new LinearLayout.LayoutParams(dp(260), dp(260)));

        address = text("", 17, GOLD);
        address.setTypeface(Typeface.MONOSPACE);
        address.setTextIsSelectable(true);
        address.setPadding(0, dp(8), 0, dp(16));
        col.addView(address);

        toggle = button();
        toggle.setOnClickListener(v -> {
            if ("running".equals(ServerService.state) || "starting".equals(ServerService.state)) {
                startService(new Intent(this, ServerService.class).setAction(ServerService.ACTION_STOP));
            } else {
                startForegroundService(new Intent(this, ServerService.class));
            }
            handler.postDelayed(this::refresh, 200);
        });
        col.addView(toggle);

        open = button();
        open.setText("Open the game in my browser");
        open.setOnClickListener(v -> startActivity(new Intent(Intent.ACTION_VIEW,
                Uri.parse("http://127.0.0.1:" + ServerService.PORT + "/"))));
        col.addView(open);

        col.addView(text("The server keeps running while you play in the browser. Turn it off here or "
                + "from the notification when the game is over.", 13, MUTED));

        ScrollView scroll = new ScrollView(this);
        scroll.setBackgroundColor(BG);
        scroll.addView(col);
        setContentView(scroll);

        if (Build.VERSION.SDK_INT >= 33
                && checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, 1);
        }
    }

    @Override
    protected void onResume() {
        super.onResume();
        handler.post(tick);
    }

    @Override
    protected void onPause() {
        super.onPause();
        handler.removeCallbacks(tick);
    }

    private void refresh() {
        String s = ServerService.state;
        boolean on = "running".equals(s);
        switch (s) {
            case "running": status.setText("The server is on."); break;
            case "starting": status.setText("Starting…"); break;
            case "error": status.setText("Could not start: " + ServerService.error); break;
            default: status.setText("The server is off.");
        }
        toggle.setText(on || "starting".equals(s) ? "Turn the server off" : "Turn the server on");
        open.setEnabled(on);
        open.setAlpha(on ? 1f : 0.4f);
        qr.setImageBitmap(on ? ServerService.qr : null);
        address.setText(on ? ServerService.url : "");
    }

    private TextView text(String s, int sp, int color) {
        TextView t = new TextView(this);
        t.setText(s);
        t.setTextSize(sp);
        t.setTextColor(color);
        t.setGravity(Gravity.CENTER_HORIZONTAL);
        t.setPadding(0, dp(6), 0, dp(6));
        return t;
    }

    private Button button() {
        Button b = new Button(this);
        b.setTextSize(17);
        b.setAllCaps(false);
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.WRAP_CONTENT);
        lp.topMargin = dp(8);
        b.setLayoutParams(lp);
        return b;
    }

    private int dp(int v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }
}
