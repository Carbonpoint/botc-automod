"""Drive the join-list delete, pause, resume, crash reload, export, import and archive in browsers.

Usage: uv run --with playwright python scripts/archive_check.py OUTDIR [PORT]
Starts its own server with a fresh data folder in OUTDIR/data. Screenshots go to OUTDIR.
"""
import asyncio
import os
import shutil
import subprocess
import sys
from pathlib import Path

from playwright.async_api import async_playwright

OUT = Path(sys.argv[1])
PORT = sys.argv[2] if len(sys.argv) > 2 else "8777"
BASE = f"http://127.0.0.1:{PORT}"
DATA = OUT / "data"
NAMES = ["Hana", "Ivo", "Jess", "Kofi", "Lena"]
checks = []


def check(what, ok):
    checks.append((what, bool(ok)))
    print(("ok   " if ok else "FAIL ") + what)


def start_server():
    env = {**os.environ, "BOTC_DATA": str(DATA), "BOTC_ARTIST": "none"}
    p = subprocess.Popen([sys.executable, "-m", "botc_automod", "--port", PORT], env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    return p


async def wait_up(pg):
    for _ in range(60):
        try:
            await pg.request.get(BASE + "/api/games")
            return
        except Exception:
            await asyncio.sleep(0.5)


async def phase(pg):
    return await pg.evaluate("S && S.game.phase")


async def main():
    shutil.rmtree(DATA, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    server = start_server()
    try:
        async with async_playwright() as pw:
            b = await pw.chromium.launch()
            pages, errors = [], []
            for n in NAMES + ["Zed", "Other"]:
                ctx = await b.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                          accept_downloads=True)
                pg = await ctx.new_page()
                pg.on("pageerror", lambda e, n=n: errors.append(f"{n}: {e}"))
                pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
                pages.append(pg)
            await wait_up(pages[0])
            for pg in pages:
                await pg.goto(BASE)
            host, zed, other = pages[0], pages[5], pages[6]
            players = pages[:5]

            # 1. Delete a lobby from the join list.
            await zed.fill("#name", "Zed")
            await zed.click('[data-act="host"]')
            await zed.wait_for_selector(".top .code")
            await host.wait_for_selector('[data-act="delgame"]', timeout=8000)
            await host.screenshot(path=f"{OUT}/a1_join_list.png")
            await host.click('[data-act="delgame"]')
            await host.wait_for_selector(".modal")
            await host.screenshot(path=f"{OUT}/a2_delete_popup.png")
            await host.click('.modal [data-a="1"]')
            await host.wait_for_timeout(600)
            check("deleted game leaves the join list", not await host.locator('[data-act="delgame"]').count())
            await zed.wait_for_selector("#name", timeout=5000)
            check("the deleted lobby's host goes home", await zed.locator('[data-act="host"]').count())

            # 2. A game into day 1.
            await host.fill("#name", "Hana")
            await host.click('[data-act="host"]')
            await host.wait_for_selector(".top .code")
            code = (await host.inner_text(".top .code")).strip()
            for pg, n in zip(players[1:], NAMES[1:]):
                await pg.fill("#name", n)
                await pg.fill("#code", code)
                await pg.click('[data-act="joincode"]')
                await pg.wait_for_selector(".map")
            for _ in range(3):
                await host.click('[data-act="seats"][data-d="-1"]')
                await host.wait_for_timeout(250)
            for i, pg in enumerate(players):
                await pg.click(f'.seat.empty[data-seat="{i}"]')
                await pg.wait_for_timeout(200)
            await host.click('[data-act="start"]')
            await host.wait_for_selector(".night")
            for _ in range(40):
                if await host.evaluate("S.game.phase + '/' + S.game.stage") == "day/":
                    break
                await host.evaluate('send({type: "advance"})')
                await host.wait_for_timeout(300)
            check("game reaches day 1", await phase(host) == "day")
            await host.click('[data-act="tab"][data-v="host"]')
            await host.wait_for_timeout(300)
            await host.screenshot(path=f"{OUT}/b1_host_page.png", full_page=True)

            # 3. Export the game in play.
            async with host.expect_download() as dl:
                await host.click('[data-act="exportgame"]')
            running = Path(await (await dl.value).path()).read_text(encoding="utf-8")
            (OUT / "export_running.md").write_text(running, encoding="utf-8")
            check("export of a game in play is a running file", "status: running" in running and "botc-save" in running)
            check("export has no characters in the readable part", "Character" not in running.split("## Save data")[0])

            # 4. Pause.
            await host.click('[data-act="pausegame"]')
            await host.wait_for_selector(".modal")
            await host.screenshot(path=f"{OUT}/b2_pause_popup.png")
            await host.click('.modal [data-a="1"]')
            for pg in players:
                await pg.wait_for_selector('[data-act="archive"]', timeout=8000)
            await players[2].screenshot(path=f"{OUT}/b3_player_after_pause.png")
            check("a paused file exists", len(list((DATA / "games/paused").glob("*.md"))) == 1)
            check("no running file for the paused game", not (DATA / f"games/running/{code}.md").exists())

            # 5. Resume from the Archive.
            await host.click('[data-act="archive"]')
            await host.click('[data-act="archivetab"][data-v="paused"]')
            await host.wait_for_selector('[data-act="resumegame"]')
            await host.screenshot(path=f"{OUT}/c1_archive_paused.png", full_page=True)
            await host.click('[data-act="resumegame"]')
            await host.click('.modal [data-a="1"]')
            await host.wait_for_selector(".top .code")
            me = await host.evaluate("S.me.name + ' ' + S.me.is_host")
            check("the host resumes as the host", me == "Hana true")
            check("the timer waits after a resume", await host.evaluate("S.game.paused"))
            for pg in players[1:]:
                await pg.wait_for_selector('[data-act="join"]', timeout=8000)
            await players[1].screenshot(path=f"{OUT}/c2_rejoin_list.png")
            for pg in players[1:]:
                await pg.click(f'[data-act="join"][data-code="{code}"]')
                await pg.wait_for_selector(".top .code", timeout=8000)
            check("players return to their seats after the resume",
                  [await pg.evaluate("S.me.name") for pg in players] == NAMES)

            # 6. Crash: kill the server and start it again.
            server.kill()
            server.wait()
            server = start_server()
            await wait_up(host)
            await host.wait_for_timeout(9000)   # the pages reconnect by themselves
            check("all players are back after a restart",
                  [await pg.evaluate("S && S.me.name") for pg in players] == NAMES)
            check("the timer waits after a restart", await host.evaluate("S.game.paused"))

            # 7. End the game: it goes to Completed.
            await host.click('[data-act="tab"][data-v="host"]')
            await host.click('[data-act="end"]')
            await host.wait_for_selector(".winner")
            await host.wait_for_timeout(500)
            check("an ended game moves to completed", len(list((DATA / "games/completed").glob("*.md"))) == 1
                  and not (DATA / f"games/running/{code}.md").exists())
            await other.click('[data-act="archive"]')
            await other.wait_for_selector('[data-act="exportfile"]')
            await other.screenshot(path=f"{OUT}/d1_archive_completed.png", full_page=True)
            async with other.expect_download() as dl:
                await other.click('[data-act="exportfile"]')
            done = Path(await (await dl.value).path()).read_text(encoding="utf-8")
            (OUT / "export_completed.md").write_text(done, encoding="utf-8")
            check("completed export has the Grimoire", "status: completed" in done and "| Character |" in done)

            # 8. Import the running export: it lands in Paused.
            await other.click('[data-act="archivetab"][data-v="paused"]')
            await other.set_input_files("#importfile", str(OUT / "export_running.md"))
            await other.wait_for_selector('[data-act="resumegame"]', timeout=5000)
            await other.screenshot(path=f"{OUT}/d2_after_import.png", full_page=True)
            check("an imported game shows in Paused", len(list((DATA / "games/paused").glob("*.md"))) == 1)
            await other.click('[data-act="resumegame"]')
            await other.click('.modal [data-a="1"]')
            await other.wait_for_timeout(800)
            check("a stranger cannot resume someone's game", not await other.locator(".top .code").count())

            print("page errors:", errors or "none")
            await b.close()
    finally:
        server.kill()
    failed = [w for w, ok in checks if not ok]
    print(f"{len(checks) - len(failed)}/{len(checks)} checks passed")
    sys.exit(1 if failed or errors else 0)


asyncio.run(main())
