"""Browser check of the Artist question flow and the seat path, with a stand-in model.

Starts a fake OpenAI-compatible model on :8790 that reads "is NAME evil" and
refuses anything else, and a botc-automod server on :8777 using it (debug on).
Usage: uv run python scripts/artist_ui_check.py OUTDIR
"""
import asyncio
import http.server
import json
import os
import re
import subprocess
import sys
import threading
import time
import urllib.request

from playwright.async_api import async_playwright

OUT = sys.argv[1]


class Fake(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        user = body["messages"][-1]["content"]
        q = user.split("Question:")[-1]
        m = re.search(r"is (\w+) evil", q, re.I)
        query = {"op": "is_team", "player": m[1], "team": "evil"} if m else {"op": "unanswerable"}
        out = json.dumps({"choices": [{"message": {"content": json.dumps({"query": query})}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(out)

    def log_message(self, *a):
        pass


def post(url, body=None):
    req = urllib.request.Request(url, json.dumps(body or {}).encode(), {"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req))


async def main():
    threading.Thread(target=http.server.HTTPServer(("127.0.0.1", 8790), Fake).serve_forever, daemon=True).start()
    env = {**os.environ, "BOTC_ARTIST": "custom", "BOTC_ARTIST_URL": "http://127.0.0.1:8790/v1",
           "BOTC_ARTIST_MODEL": "fake", "BOTC_DEBUG": "1", "BOTC_DATA": os.path.join(OUT, "data")}
    srv = subprocess.Popen([sys.executable, "-u", "-m", "botc_automod", "--port", "8777", "--no-qr"], env=env,
                           stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    time.sleep(4)
    try:
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            names = ["Hana", "Ivo", "Jess", "Kofi", "Lena", "Milo", "Nia"]
            pages, errors = [], []
            for n in names:
                ctx = await b.new_context(viewport={"width": 390, "height": 844})
                pg = await ctx.new_page()
                pg.on("pageerror", lambda e, n=n: errors.append(f"{n}: {e}"))
                pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
                await pg.goto("http://127.0.0.1:8777/")
                pages.append(pg)
            host = pages[0]
            await host.fill("#name", "Hana")
            await host.click('[data-act="host"]')
            await host.wait_for_selector(".top .code")
            code = (await host.inner_text(".top .code")).strip()
            await host.click('[data-act="pref"][data-k="edition"][data-v="snv"]')
            for pg, n in zip(pages[1:], names[1:]):
                await pg.fill("#name", n)
                await pg.fill("#code", code)
                await pg.click('[data-act="joincode"]')
                await pg.wait_for_selector(".map")
            await host.click('[data-act="seats"][data-d="-1"]')
            for i, pg in enumerate(pages):
                await pg.click(f'.seat.empty[data-seat="{i}"]')
                await pg.wait_for_timeout(150)
            await host.screenshot(path=f"{OUT}/a1_lobby_path.png", full_page=True)
            await host.click('[data-act="start"]')
            await host.wait_for_selector(".night")
            post(f"http://127.0.0.1:8777/api/debug/{code}/role?player=Jess&role=artist")
            jess = pages[2]
            for _ in range(60):  # finish the night
                if not await host.locator(".night").count():
                    break
                for pg in pages:
                    for sel in ('[data-act="decoy"]', '[data-act="ack"]', '[data-act="none"]', '[data-act="submitchar"]'):
                        if await pg.locator(sel).count():
                            await pg.locator(sel).first.click()
                            break
                    else:
                        if await pg.locator('[data-act="pick"]').count():
                            picks = pg.locator('[data-act="pick"]')
                            await picks.nth(0).click()
                            if "/2 chosen" in await pg.inner_text(".night"):
                                await picks.nth(1).click()
                            await pg.click('[data-act="submit"]')
                await asyncio.sleep(1)
            await jess.click('[data-act="tab"][data-v="town"]')
            if not await jess.locator("#da-artist-text").count():
                t = await jess.inner_text("#app")
                i = t.find("Artist")
                print("PAGE ERRORS:", errors)
                print("STATE:", await jess.evaluate("JSON.stringify({a: S.me.day_actions.map(x => [x.key, x.free_text]), role: S.me.role && S.me.role.id, phase: S.game.phase, ready: S.game.artist_ready, alive: S.me.alive})"))
                print("NO ARTIST BOX. Screen:", t[max(0, i - 200):i + 400])
                print("HTML:", (await jess.inner_html("#app"))[(await jess.inner_html("#app")).find("Artist") - 300:][:900])
                print(json.dumps(json.load(urllib.request.urlopen(f"http://127.0.0.1:8777/api/debug/{code}")))[:800])
            await jess.fill("#da-artist-text", "Who is the demon?")
            await jess.click('[data-act="artistcheck"]')
            await jess.wait_for_timeout(1500)
            print("UI:", await jess.evaluate("JSON.stringify({busy: ui.artistBusy, pv: ui.artistPreview, open: wsOpen})"))
            print("refusal shown:", "cannot answer that yes or no" in await jess.inner_text("#app"))
            await jess.fill("#da-artist-text", "is Kofi evil or what")
            await jess.click('[data-act="artistcheck"]')
            await jess.wait_for_selector('[data-act="artistask"]')
            await jess.screenshot(path=f"{OUT}/a2_artist_reading.png", full_page=True)
            await jess.click('[data-act="artistask"]')
            await jess.wait_for_timeout(600)
            await jess.click('[data-act="tab"][data-v="me"]')
            text = await jess.inner_text("#app")
            print("answer in notebook:", "The Storyteller read it as: Kofi is evil" in text)
            await jess.screenshot(path=f"{OUT}/a3_notebook.png", full_page=True)
            await jess.click('[data-act="tab"][data-v="town"]')
            await jess.screenshot(path=f"{OUT}/a4_town_path.png")
            print("page errors:", errors or "none")
            await b.close()
    except Exception as e:
        print("FAILED:", repr(e)[:300])
    finally:
        srv.terminate()
        print(srv.communicate(timeout=5)[0][-600:])


asyncio.run(main())
