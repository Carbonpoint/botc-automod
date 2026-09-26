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
import android.text.InputType;
import android.view.View;
import android.widget.ArrayAdapter;
import android.widget.Button;
import android.widget.EditText;
import android.widget.RadioButton;
import android.widget.RadioGroup;
import android.widget.Spinner;
import android.widget.Toast;

import com.chaquo.python.PyObject;
import com.chaquo.python.Python;
import com.chaquo.python.android.AndroidPlatform;

import org.json.JSONObject;
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

    private static final String[] KINDS = {"none", "packaged", "ollama", "cloud"};
    private static final String[] PROVIDERS = {"anthropic", "openai", "gemini", "openrouter", "custom"};
    private static final String[] PROVIDER_NAMES = {"Anthropic (Claude)", "OpenAI", "Google Gemini", "OpenRouter",
            "Other OpenAI-compatible server"};

    private TextView status, address, artistNow;
    private RadioGroup kind;
    private Spinner provider;
    private EditText url, model, key;
    private View ollamaBox, cloudBox;
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
        col.addView(artistSection());

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

    /** The Artist's question model: the phone version of the desktop's first-run questions. */
    private View artistSection() {
        LinearLayout box = new LinearLayout(this);
        box.setOrientation(LinearLayout.VERTICAL);
        box.setPadding(0, dp(28), 0, 0);
        TextView h = text("Artist questions", 20, TEXT);
        h.setTypeface(Typeface.DEFAULT_BOLD);
        box.addView(h);
        box.addView(text("An automated game needs a language model to read the Artist's yes/no question. "
                + "The game engine, not the model, decides the answer.", 13, MUTED));
        artistNow = text("", 14, GOLD);
        box.addView(artistNow);

        kind = new RadioGroup(this);
        String[] labels = {"No model (no Artist in automated games)", "Packaged model (runs on this phone)",
                "An Ollama server on this network", "A cloud AI service (needs an API key)"};
        for (int i = 0; i < labels.length; i++) {
            RadioButton rb = new RadioButton(this);
            rb.setId(1000 + i);
            rb.setText(labels[i]);
            rb.setTextColor(TEXT);
            kind.addView(rb);
        }
        box.addView(kind);

        LinearLayout ob = new LinearLayout(this);
        ob.setOrientation(LinearLayout.VERTICAL);
        url = field("Ollama address, e.g. http://192.168.1.20:11434", InputType.TYPE_TEXT_VARIATION_URI);
        ob.addView(url);
        ollamaBox = ob;
        box.addView(ob);

        LinearLayout cb = new LinearLayout(this);
        cb.setOrientation(LinearLayout.VERTICAL);
        provider = new Spinner(this);
        provider.setAdapter(new ArrayAdapter<>(this, android.R.layout.simple_spinner_dropdown_item, PROVIDER_NAMES));
        cb.addView(provider);
        key = field("API key (leave empty to keep the saved one)",
                InputType.TYPE_CLASS_TEXT | InputType.TYPE_TEXT_VARIATION_PASSWORD);
        cb.addView(key);
        cloudBox = cb;
        box.addView(cb);

        model = field("Model name (empty for the default)", InputType.TYPE_CLASS_TEXT);
        box.addView(model);
        kind.setOnCheckedChangeListener((g, id) -> showFields());

        Button save = button();
        save.setText("Save the Artist setting");
        save.setOnClickListener(v -> saveArtist());
        box.addView(save);
        loadArtist();
        return box;
    }

    private EditText field(String hint, int type) {
        EditText e = new EditText(this);
        e.setHint(hint);
        e.setHintTextColor(MUTED);
        e.setTextColor(TEXT);
        e.setInputType(type | (type == InputType.TYPE_TEXT_VARIATION_URI ? InputType.TYPE_CLASS_TEXT : 0));
        e.setSingleLine(true);
        return e;
    }

    private void showFields() {
        int k = kind.getCheckedRadioButtonId() - 1000;
        ollamaBox.setVisibility(k == 2 ? View.VISIBLE : View.GONE);
        cloudBox.setVisibility(k == 3 ? View.VISIBLE : View.GONE);
        model.setVisibility(k >= 2 ? View.VISIBLE : View.GONE);
    }

    private PyObject py() {
        if (!Python.isStarted()) Python.start(new AndroidPlatform(getApplicationContext()));
        return Python.getInstance().getModule("botc_automod.android");
    }

    private String dataDir() {
        return getFilesDir().getAbsolutePath() + "/data";
    }

    private void loadArtist() {
        try {
            JSONObject c = new JSONObject(py().callAttr("get_artist", dataDir()).toString());
            String k = c.optString("kind", "none");
            int i = 0;
            for (int j = 0; j < PROVIDERS.length; j++) {
                if (PROVIDERS[j].equals(k)) { i = 3; provider.setSelection(j); }
            }
            if (k.equals("packaged")) i = 1;
            if (k.equals("ollama")) i = 2;
            kind.check(1000 + i);
            url.setText(c.optString("url", ""));
            model.setText(c.optString("model", ""));
            artistNow.setText(c.optBoolean("has_key") ? "An API key is saved." : "");
        } catch (Exception e) {
            kind.check(1000);
        }
        showFields();
    }

    private void saveArtist() {
        try {
            int k = kind.getCheckedRadioButtonId() - 1000;
            JSONObject c = new JSONObject();
            c.put("kind", k == 3 ? PROVIDERS[provider.getSelectedItemPosition()] : KINDS[k]);
            if (k == 2) c.put("url", url.getText().toString().trim());
            if (k >= 2) c.put("model", model.getText().toString().trim());
            if (k == 3) c.put("api_key", key.getText().toString().trim());
            String said = py().callAttr("set_artist", dataDir(), c.toString()).toString();
            key.setText("");
            artistNow.setText("Saved: " + said);
            Toast.makeText(this, "Saved. Turn the server off and on to use it.", Toast.LENGTH_LONG).show();
        } catch (Exception e) {
            Toast.makeText(this, "Could not save: " + e.getMessage(), Toast.LENGTH_LONG).show();
        }
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
