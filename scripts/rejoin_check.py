"""Browser check: reload and rejoin in the lobby, and rejoin with host approval in a game.

Usage: uv run python scripts/rejoin_check.py OUTDIR [BASE_URL]
"""
import asyncio
import sys

from playwright.async_api import async_playwright

OUT = sys.argv[1]
BASE = sys.argv[2] if len(sys.argv) > 2 else "http://127.0.0.1:8777"
NAMES = ["Hana", "Ivo", "Jess", "Kofi", "Lena"]


async def main():
    async with async_playwright() as pw:
        b = await pw.chromium.launch()
        pages, errors = [], []
        for n in NAMES:
            ctx = await b.new_context(viewport={"width": 390, "height": 844})
            pg = await ctx.new_page()
            pg.on("pageerror", lambda e, n=n: errors.append(f"{n}: {e}"))
            pg.on("dialog", lambda d: asyncio.ensure_future(d.accept()))
            await pg.goto(BASE)
            pages.append(pg)
        host, jess = pages[0], pages[2]
        await host.fill("#name", "Hana")
        await host.click('[data-act="host"]')
        await host.wait_for_selector(".top .code")
        code = (await host.inner_text(".top .code")).strip()
        for pg, n in zip(pages[1:], NAMES[1:]):
            await pg.fill("#name", n)
            await pg.fill("#code", code)
            await pg.click('[data-act="joincode"]')
            await pg.wait_for_selector(".map")
        for _ in range(3):
            await host.click('[data-act="seats"][data-d="-1"]')
            await host.wait_for_timeout(250)
        for i, pg in enumerate(pages):
            await pg.click(f'.seat.empty[data-seat="{i}"]')
            await pg.wait_for_timeout(200)
        await host.screenshot(path=f"{OUT}/r1_lobby_options.png", full_page=True)

        # 1. A plain reload keeps the player in the lobby.
        await jess.reload()
        await jess.wait_for_selector(".map")
        print("reload keeps session:", "Leave my seat" in await jess.inner_text("#app"))

        # 2. Lost storage: join again with the same name, get the same seat back.
        await jess.evaluate("localStorage.clear()")
        await jess.reload()
        await jess.fill("#name", "jess")
        await jess.fill("#code", code)
        await jess.click('[data-act="joincode"]')
        await jess.wait_for_selector(".map")
        await jess.wait_for_timeout(300)
        print("lobby rejoin keeps seat:", "Leave my seat" in await jess.inner_text("#app"))

        # 3. In a game: rejoin needs the host.
        await host.click('[data-act="start"]')
        await host.wait_for_selector(".night")
        await jess.evaluate("localStorage.clear()")
        await jess.reload()
        await jess.fill("#name", "Jess")
        await jess.fill("#code", code)
        await jess.click('[data-act="joincode"]')
        await jess.wait_for_timeout(1500)
        print("waiting screen:", "Asking to rejoin" in await jess.inner_text("#app"))
        await host.wait_for_selector('[data-act="rejoin"][data-v="1"]')
        await host.screenshot(path=f"{OUT}/r2_host_approval.png")
        await host.click('[data-act="rejoin"][data-v="1"]')
        await jess.wait_for_selector(".top .code", timeout=10000)
        await jess.wait_for_timeout(500)
        await jess.screenshot(path=f"{OUT}/r3_back_in_game.png")
        print("back in game:", "Night 1" in await jess.inner_text("#app"))
        print("page errors:", errors or "none")
        await b.close()


asyncio.run(main())
