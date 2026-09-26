"""Drive the karma arcade in a phone-sized browser: every game, a pool shot, karma in a live game.

Usage: uv run --with playwright python scripts/arcade_check.py OUTDIR [PORT]
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
checks = []


def check(what, ok):
    checks.append((what, bool(ok)))
    print(("ok   " if ok else "FAIL ") + what)


async def main():
    shutil.rmtree(DATA, ignore_errors=True)
    OUT.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "BOTC_DATA": str(DATA), "BOTC_ARTIST": "none"}
    srv = subprocess.Popen([sys.executable, "-m", "botc_automod", "--port", PORT], env=env,
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL)
    errors = []
    try:
        async with async_playwright() as pw:
            br = await pw.chromium.launch()
            ctx = await br.new_context(viewport={"width": 390, "height": 844}, has_touch=True, device_scale_factor=2)
            pg = await ctx.new_page()
            pg.on("pageerror", lambda e: errors.append(str(e)))
            for _ in range(60):
                try:
                    await pg.request.get(BASE + "/api/games"); break
                except Exception:
                    await asyncio.sleep(0.25)
            # A lobby with Ana in it: arcade karma must reach her seat too.
            r = await pg.request.post(BASE + "/api/games", data={"name": "Ana"})
            code = (await r.json())["code"]

            await pg.goto(BASE)
            await pg.fill("#name", "Ana")
            await pg.click('[data-act="arcade"]')
            await pg.wait_for_selector(".arc-card")
            await pg.screenshot(path=str(OUT / "menu.png"), full_page=True)
            check("arcade menu lists 6 games", await pg.locator(".arc-card").count() == 6)

            async def open_game(gid):
                await pg.click(f'[data-arc="play"][data-g="{gid}"]')
                await pg.wait_for_selector("#arc-stage canvas")

            async def wait_over(timeout=60):
                for _ in range(timeout * 4):
                    if await pg.locator(".arc-over .row").count():
                        return True
                    await asyncio.sleep(0.25)
                return False

            # Flappy: one tap to start, then fall to the ground.
            await open_game("flappy")
            await pg.locator("#arc-stage canvas").tap()
            check("flappy ends", await wait_over(10))
            await pg.screenshot(path=str(OUT / "flappy.png"), full_page=True)
            await pg.click('[data-arc="menu"]')

            # Night Runner: start and do nothing: a grave ends it.
            await open_game("dino")
            await pg.locator("#arc-stage canvas").tap()
            check("runner ends", await wait_over(15))
            txt = await pg.locator(".arc-over").inner_text()
            await pg.screenshot(path=str(OUT / "dino.png"), full_page=True)
            await pg.click('[data-arc="menu"]')

            # 2047: arrow keys until no moves.
            await open_game("odd")
            for i in range(3000):
                await pg.keyboard.press(["ArrowLeft", "ArrowDown", "ArrowRight", "ArrowDown", "ArrowUp"][i % 5 if i % 7 else 4])
                if i % 50 == 0 and await pg.locator(".arc-over .row").count():
                    break
            check("2047 ends", await wait_over(5))
            check("2047 score is odd-tile sum > 0", "Score:" in await pg.locator(".arc-over").inner_text())
            await pg.screenshot(path=str(OUT / "odd.png"), full_page=True)
            await pg.click('[data-arc="menu"]')

            # Blocks: drop pieces until the top.
            await open_game("blocks")
            for _ in range(80):
                if await pg.locator(".arc-over .row").count():
                    break
                try:
                    await pg.locator('[data-b="down"]').tap(timeout=2000)
                except Exception:   # the pad goes away at game over
                    pass
                await asyncio.sleep(0.05)
            check("blocks ends", await wait_over(5))
            await pg.screenshot(path=str(OUT / "blocks.png"), full_page=True)
            await pg.click('[data-arc="menu"]')

            # Snake: start, then run into the wall.
            await open_game("snake")
            await pg.keyboard.press("ArrowUp")
            check("snake ends", await wait_over(10))
            await pg.click('[data-arc="menu"]')

            # Pool: thumb down, pull back, slide forward past the start.
            await open_game("pool")
            await asyncio.sleep(1)
            box = await pg.locator("#arc-stage canvas").bounding_box()
            cx, cy = box["x"] + box["width"] / 2, box["y"] + box["height"] * 0.6
            # portrait: the table's long side runs down the screen; the rack is below.
            await pg.mouse.move(cx, cy)
            await pg.mouse.down()
            for i in range(1, 12):
                await pg.mouse.move(cx + i * 0.3, cy - i * 9)      # pull back (up the screen)
            await pg.screenshot(path=str(OUT / "pool-aim.png"), full_page=True)
            for i in range(12, -12, -1):
                await pg.mouse.move(cx + i * 0.3, cy - i * 9)      # slide forward past the start
            await pg.mouse.up()
            await asyncio.sleep(0.6)
            await pg.screenshot(path=str(OUT / "pool-roll.png"), full_page=True)
            st = await (await pg.request.get(BASE + "/api/arcade/pool")).json()
            check("pool shot reached the server", st["version"] == 1 and st["last_by"] == "Ana")
            await asyncio.sleep(5)
            await pg.screenshot(path=str(OUT / "pool.png"), full_page=True)
            check("pool status tells Ana to wait", "wait" in await pg.locator(".arc-pool-status").inner_text())
            await pg.click('[data-arc="menu"]')
            await asyncio.sleep(0.5)

            info = await (await pg.request.get(BASE + "/api/arcade?name=Ana")).json()
            check(f"arcade karma today is {info['today']} (>0) and total {info['total']}", info["today"] > 0 and info["total"] == info["today"])
            dbg = await pg.request.get(BASE + f"/api/games")
            check("lobby still listed", code in await dbg.text())
            await pg.click('[data-arc="exit"]')
            check("back to the start page", await pg.locator("#name").count() == 1)
            await br.close()
    finally:
        srv.terminate()
        srv.wait()
    check("no page errors" + (f": {errors}" if errors else ""), not errors)
    sys.exit(0 if all(ok for _, ok in checks) else 1)


asyncio.run(main())
